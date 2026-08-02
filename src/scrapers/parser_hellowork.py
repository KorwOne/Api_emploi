import re
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup


SALAIRE_RE = re.compile(
    r"(?:(\d[\d\s]*)\s*-\s*(\d[\d\s]*)|(\d[\d\s]*))\s*€\s*/\s*(an|mois)",
    re.IGNORECASE,
)

CONTRATS = ("CDI", "CDD", "Freelance", "Intérim", "Alternance", "Stage")


def _nettoyer_texte(texte):
    return " ".join((texte or "").split())


def _normaliser_url(url):
    if not url:
        return ""

    parsed = urlparse(url)
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, "", "", "")
    )


def _extraire_salaire(texte):
    match = SALAIRE_RE.search(texte or "")
    return match.group(0) if match else ""

def _extraire_lieu(lignes):
    for ligne in lignes[2:]:
        if re.search(r"\b\d{2}\b", ligne):
            lieu = re.split(
                r"\s+\b(?:CDI|CDD|Freelance|Intérim|Alternance|Stage)\b",
                ligne,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]
            return _nettoyer_texte(lieu)

    return ""


def _decoder_url_hellowork(url):
    """
    Les liens d'email HelloWork contiennent l'URL finale encodée
    dans leur dernier segment.
    """
    try:
        dernier_segment = url.rstrip("/").split("/")[-1]
        padding = "=" * (-len(dernier_segment) % 4)

        import base64
        contenu = base64.urlsafe_b64decode(
            dernier_segment + padding
        ).decode("utf-8", errors="ignore")

        position = contenu.find("https://www.hellowork.com/")
        if position == -1:
            return url

        return _normaliser_url(contenu[position:])
    except Exception:
        return url
    

def _trouver_carte_offre(lien):
    """
    Dans l'email HelloWork actuel, la table grand-parent de niveau 6
    contient toutes les informations d'une offre.
    """
    parent = lien
    for _ in range(6):
        parent = parent.parent
        if parent is None:
            return None

    if parent.name == "table":
        return parent

    return lien.find_parent("table")


def _lignes_utiles(carte):
    """
    Chaque information visible est portée par une cellule de l'email HTML.
    On déduplique tout en conservant l'ordre d'apparition.
    """
    lignes = []
    for cellule in carte.find_all("td"):
        texte = _nettoyer_texte(cellule.get_text(" ", strip=True))
        if not texte or texte == "Voir l’offre":
            continue
        if texte not in lignes:
            lignes.append(texte)
    return lignes


def _extraire_infos(carte):
    texte = _nettoyer_texte(carte.get_text(" ", strip=True))
    texte = texte.replace("Voir l’offre", "").strip()

    salaire = _extraire_salaire(texte)

    contrat = ""
    for valeur in CONTRATS:
        if re.search(rf"\b{re.escape(valeur)}\b", texte, re.IGNORECASE):
            contrat = valeur
            break

    lignes = _lignes_utiles(carte)

    titre = lignes[0] if len(lignes) >= 1 else ""
    entreprise = lignes[1] if len(lignes) >= 2 else ""

    lieu = _extraire_lieu(lignes)

    return {
        "titre": titre,
        "entreprise": entreprise,
        "lieu": lieu,
        "contrat": contrat,
        "salaire_texte": salaire,
    }


def parser_offres_hellowork(html):
    soup = BeautifulSoup(html or "", "html.parser")
    offres = []
    urls_vues = set()

    for lien in soup.find_all("a", href=True):
        libelle = _nettoyer_texte(lien.get_text(" ", strip=True))
        url = _normaliser_url(lien["href"])

        if libelle.lower() != "voir l’offre":
            continue

        if "hellowork.com" not in url:
            continue

        carte = _trouver_carte_offre(lien)
        if carte is None:
            continue

        urls_vues.add(url)
        infos = _extraire_infos(carte)

        url_finale = _decoder_url_hellowork(url)

        if url_finale in urls_vues:
            continue

        urls_vues.add(url_finale)
        infos = _extraire_infos(carte)

        offres.append(
            {
                "source": "hellowork_email",
                "job_id": url_finale,
                "url": url_finale,
                **infos,
            }
        )

    return offres