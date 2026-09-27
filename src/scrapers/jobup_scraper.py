"""
Scraper jobup.ch pour le projet Api_Emploi.
Respecte l'interface attendue par job_alerts.py :
  scraper_offres(profil_row) -> list[dict{job_id, titre, url}]
"""
from playwright.sync_api import sync_playwright
import json
import re
import time
import random
from urllib.parse import quote
from filtres import offre_respecte_mots_cles, offre_contient_mot_exclu

REGIONS_ROMANDIE = {
    "vaud": 24,
    "geneve": 25,
    "valais": 26,
    "fribourg": 27,
    "neuchatel": 28,
    "jura": 29,
}

SYNONYMES_TITRES_CIBLES = [
    "dsi", "directeur des systèmes d'information", "directeur systeme d'information",
    "rsi", "responsable systèmes d'information", "responsable systeme d'information",
    "cto", "chief technology officer", "chief technical officer",
    "chief information officer", "cio",
    "directeur infrastructure", "directeur infrastructures",
    "responsable infrastructure", "responsable infrastructures",
    "it director", "head of it",
    "infrastructure engineer", "infrastructure manager",
    "it infrastructure", "cloud infrastructure",
    "teamlead it", "team lead it",
    "it security manager", "security manager",
    "workplace & infrastructure", "workplace infrastructure",
    "project manager it infrastructure", "senior project manager it",
]


def _construire_url(mot_cle, region_code=None, page=1):
    base = "https://www.jobup.ch/fr/emplois/"
    params = f"?term={quote(mot_cle)}"
    if region_code:
        params += f"&region={region_code}"
    if page > 1:
        params += f"&page={page}"
    return base + params


def _extraire_titre_propre(blocs):
    """Extrait le titre pur depuis les blocs du texte complet du lien."""
    if len(blocs) < 2:
        return ""
    titre = blocs[1].split("\nLieu de travail:")[0].strip()
    return titre if titre else "(Titre non detecte)"


def _extraire_localisation(blocs):
    """Le lieu de travail est toujours le bloc juste après 'Titre\\nLieu de travail:'."""
    return blocs[2].strip() if len(blocs) > 2 else ""


def _extraire_date_publication(blocs):
    """Premier bloc : indicateur de récence jobup (ex: 'Il y a 2 semaines', 'Nouveau')."""
    return blocs[0].strip() if blocs else ""


def _extraire_entreprise(blocs):
    """
    L'entreprise suit toujours la valeur de 'Type de contrat:'. On ancre dessus plutôt
    que de prendre l'avant-dernier bloc : quand jobup ajoute un badge en fin de carte
    (ex: "Candidature simplifiée"), l'avant-dernier bloc n'est plus l'entreprise.
    """
    for i, b in enumerate(blocs):
        if b.strip() == "Type de contrat:" and i + 2 < len(blocs):
            return blocs[i + 2].strip()
    return blocs[-2].strip() if len(blocs) >= 2 else ""


def _extraire_offres_page(page):
    """Extrait les offres visibles sur la page jobup.ch actuellement chargee."""
    offres = []
    liens = page.query_selector_all("a[href*='/fr/emplois/detail/']")

    for lien in liens:
        href = lien.get_attribute("href")
        if not href:
            continue
        if not href.startswith("http"):
            href = "https://www.jobup.ch" + href

        texte_brut = lien.inner_text().strip()
        blocs = texte_brut.split("\n\n")
        titre = _extraire_titre_propre(blocs)
        entreprise = _extraire_entreprise(blocs)
        localisation = _extraire_localisation(blocs)
        date_publication = _extraire_date_publication(blocs)

        match_id = re.search(r"/detail/([a-zA-Z0-9\-]+)", href)
        job_id = match_id.group(1) if match_id else href

        offres.append({
            "job_id": job_id,
            "titre": titre,
            "entreprise": entreprise,
            "localisation": localisation,
            "date_publication": date_publication,
            "url": href,
        })

    vus = set()
    offres_uniques = []
    for o in offres:
        if o["job_id"] not in vus:
            vus.add(o["job_id"])
            offres_uniques.append(o)
    return offres_uniques


def _extraire_description_detail(page, href, timeout=15000):
    """Visite la page détail d'une offre pour récupérer sa description complète
    (non disponible depuis la carte de la liste). Retourne une chaîne vide en cas
    d'échec plutôt que de faire échouer tout le scraping — seules les offres qui
    passent déjà le filtre titre sont visitées, pour limiter le nombre de requêtes."""
    try:
        page.goto(href, timeout=timeout, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        el = page.query_selector("[data-cy='vacancy-description']")
        if not el:
            return ""
        texte = el.inner_text()
        # La section contient aussi un widget "match" jobup avant le vrai texte
        # de l'offre ; on ne garde que ce qui suit ce marqueur s'il est présent.
        marqueur = "À propos de cette offre"
        if marqueur in texte:
            texte = texte.split(marqueur, 1)[1]
        return texte.strip()
    except Exception as e:
        print(f"[jobup] Erreur récupération description ({href}) : {e}")
        return ""


def _correspond_criteres(titre, mots_inclus, mots_exclus):
    if offre_contient_mot_exclu(titre, mots_exclus):
        return False
    if mots_inclus:
        return offre_respecte_mots_cles(titre, mots_inclus)
    return any(syn in titre.lower() for syn in SYNONYMES_TITRES_CIBLES)



def scraper_offres(profil_row, max_pages=1, delai_min=2, delai_max=5):
    """
    profil_row : sqlite3.Row avec au moins mots_inclus (JSON), mots_exclus (JSON),
                 localisation (JSON, ex: {"cantons": ["vaud", "geneve"]})
    Retourne une liste de dicts {job_id, titre, url}
    """
    mots_inclus = json.loads(profil_row["mots_inclus"] or "[]")
    mots_exclus = json.loads(profil_row["mots_exclus"] or "[]")

    try:
        localisation = json.loads(profil_row["localisation"] or "{}")
    except (TypeError, json.JSONDecodeError):
        localisation = {}

    cantons = localisation.get("valeurs", []) if isinstance(localisation, dict) else []
    cantons = [c.lower() for c in cantons]
    mots_cles_recherche = mots_inclus if mots_inclus else [""]

    toutes_offres = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

        regions_a_scanner = [REGIONS_ROMANDIE[c] for c in cantons if c in REGIONS_ROMANDIE] or [None]

        for mot_cle in mots_cles_recherche:
            for region_code in regions_a_scanner:
                for page_num in range(1, max_pages + 1):
                    url = _construire_url(mot_cle, region_code, page_num)
                    print(f"[jobup] Scan : {url}")

                    try:
                        page.goto(url, timeout=20000, wait_until="domcontentloaded")
                        page.wait_for_timeout(2000)
                    except Exception as e:
                        print(f"[jobup] Erreur de chargement : {e}")
                        continue

                    offres_page = _extraire_offres_page(page)
                    if not offres_page:
                        break

                    for off in offres_page:
                        print(f"  -> Titre detecte: {off['titre']} | {off.get('entreprise', '')}")
                        if _correspond_criteres(off["titre"], mots_inclus, mots_exclus):
                            off["job_id"] = f"jobup-{off['job_id']}"
                            off["description"] = _extraire_description_detail(page, off["url"])
                            time.sleep(random.uniform(1, 2))
                            toutes_offres.append(off)

                    time.sleep(random.uniform(delai_min, delai_max))

        browser.close()

    vus = set()
    resultat = []
    for o in toutes_offres:
        if o["job_id"] not in vus:
            vus.add(o["job_id"])
            resultat.append(o)

    print(f"[jobup] Total offres retenues apres filtrage : {len(resultat)}")
    return resultat


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "..")
    from job_alerts import load_profils

    profils = load_profils()
    for p in profils:
        if p["nom"] != "DSI":
            continue
        class FakeRow(dict):
            def __getitem__(self, key):
                return dict.get(self, key)
        profil_row = FakeRow({
            "mots_inclus": json.dumps(p["mots_inclus"]),
            "mots_exclus": json.dumps(p["mots_exclus"]),
            "localisation": json.dumps(p["localisation"]),
        })
        resultats = scraper_offres(profil_row)
        for r in resultats:
            print(r)