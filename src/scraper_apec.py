import datetime
import requests
from filtres import offre_respecte_salaire_min, offre_respecte_mots_cles, offre_contient_mot_exclu

APEC_API_URL = "https://www.apec.fr/cms/webservices/rechercheOffre"

# Fenêtre de fraîcheur alignée sur celle de France Travail : l'API de recherche
# apec.fr n'expose pas de paramètre de date, donc chaque cycle renvoie
# intégralement les mêmes annonces tant qu'elles restent en ligne (déjà vues et
# écartées par la contrainte UNIQUE en base, mais reclassées inutilement par
# Ollama à chaque exécution). Filtrer ici sur datePublication réduit ce travail
# redondant.
FENETRE_FRAICHEUR = datetime.timedelta(hours=48)


def _offre_est_recente(date_publication_texte):
    """Une date absente ou dans un format inattendu laisse passer l'offre plutôt
    que de risquer un faux rejet (même logique que offre_respecte_zone)."""
    if not date_publication_texte:
        return True
    try:
        date_publication = datetime.datetime.strptime(date_publication_texte, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        return True
    return (datetime.datetime.now(datetime.UTC) - date_publication) <= FENETRE_FRAICHEUR

HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Origin": "https://www.apec.fr",
    "Referer": "https://www.apec.fr/candidat/recherche-emploi.html/emploi",
}


def _rechercher_mot_cle(mot_cle, lieux, range_size=20):
    payload = {
        "lieux": lieux,
        "fonctions": [],
        "statutPoste": [],
        "typesContrat": [],
        "typesConvention": ["143684", "143685", "143686", "143687", "143706"],
        "niveauxExperience": [],
        "idsEtablissement": [],
        "secteursActivite": [],
        "typesTeletravail": [],
        "idNomZonesDeplacement": [],
        "positionNumbersExcluded": [],
        "typeClient": "CADRE",
        "sorts": [{"type": "SCORE", "direction": "DESCENDING"}],
        "pagination": {"range": range_size, "startIndex": 0},
        "activeFiltre": True,
        "pointGeolocDeReference": {"distance": 0},
        "motsCles": mot_cle,
    }

    response = requests.post(APEC_API_URL, json=payload, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response.json().get("resultats", [])


def scraper_apec(profil_dict, range_size=20):
    mots_cles_list = profil_dict.get("mots_inclus", [])
    mots_exclus_list = profil_dict.get("mots_exclus", [])
    salaire_min = profil_dict.get("salaire_min")
    # Codes numériques internes apec.fr pour "lieux" (aucune API publique pour les
    # résoudre : récupérés en observant le champ de localisation sur apec.fr).
    # 711 = Île-de-France. Défaut si le profil ne précise rien.
    lieux = profil_dict.get("apec_lieux") or ["711"]

    if not mots_cles_list:
        return []

    resultats_par_id = {}
    for mot_cle in mots_cles_list:
        try:
            resultats = _rechercher_mot_cle(mot_cle, lieux, range_size)
        except requests.RequestException as e:
            print(f"[apec] Erreur pour le mot-clé '{mot_cle}': {e}")
            continue
        for item in resultats:
            resultats_par_id[item["id"]] = item

    offres = []
    for item in resultats_par_id.values():
        numero_offre = item.get("numeroOffre")
        titre = item.get("intitule") or "(Titre non renseigné)"
        entreprise = item.get("nomCommercial", "")
        salaire_texte = item.get("salaireTexte", "")
        localisation = item.get("lieuTexte", "")
        date_publication = item.get("datePublication", "")

        if not offre_respecte_mots_cles(titre, mots_cles_list):
            continue
        if offre_contient_mot_exclu(titre, mots_exclus_list):
            continue
        if not offre_respecte_salaire_min(salaire_texte, salaire_min):
            continue
        if not _offre_est_recente(date_publication):
            continue

        url = f"https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/{numero_offre}"

        offres.append({
            "job_id": numero_offre,
            "titre": titre,
            "description": item.get("texteOffre", ""),
            "entreprise": entreprise,
            "salaire": salaire_texte,
            "localisation": localisation,
            "date_publication": date_publication,
            "url": url,
        })

    return offres