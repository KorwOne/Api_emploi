from pathlib import Path
import json
import datetime
import requests
from filtres import offre_respecte_mots_cles, offre_contient_mot_exclu

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "france_travail_config.json"

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"


CODES_DEPARTEMENT_VILLES = {
    "paris": "75",
    "lille": "59",
    "lyon": "69",
    "nantes": "44",
    "montpellier": "34",
    "toulouse": "31",
}

def load_ft_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)

def get_access_token():
    cfg = load_ft_config()
    data = {
        "grant_type": "client_credentials",
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "scope": "api_offresdemploiv2 o2dsoffre",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(TOKEN_URL, data=data, headers=headers)
    resp.raise_for_status()
    return resp.json()["access_token"]

def scraper_france_travail(profil):
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    mots_inclus = profil.get("mots_inclus", [])
    mots_exclus = profil.get("mots_exclus", [])
    salaire_min = profil.get("salaire_min")
    codes_rome = profil.get("codes_rome", [])
    pays_cibles = profil.get("pays_cibles", ["FR"])
    localisation_par_pays = profil.get("localisation", {})

    if "FR" not in pays_cibles:
        return []

    zones_autorisees = profil.get("zones_autorisees") or {}
    if isinstance(zones_autorisees, str):
        zones_autorisees = json.loads(zones_autorisees) if zones_autorisees else {}

    # Priorité aux départements explicitement listés dans zones_autorisees : c'est
    # la source de vérité du profil pour la couverture géographique. La déduction
    # via CODES_DEPARTEMENT_VILLES (à partir des noms de ville dans "localisation")
    # ne sert qu'en repli, car elle ne couvre qu'une poignée de villes connues et
    # peut restreindre la recherche à un seul département (ex: profil autorisant
    # 75/78/92/94 mais dont "localisation" ne mentionne que "Paris" et "Ile de
    # France" — seul "Paris" est reconnu, ce qui exclurait 78/92/94 de la
    # recherche API elle-même, avant même le filtrage géographique en aval).
    departements_zone = zones_autorisees.get("departements") or []
    if departements_zone:
        codes_departements = list(dict.fromkeys(departements_zone))
    else:
        loc_fr = localisation_par_pays.get("FR", {})
        villes = loc_fr.get("valeurs", []) if loc_fr.get("type") == "ville" else []
        codes_departements = list({CODES_DEPARTEMENT_VILLES[v.lower()] for v in villes if v.lower() in CODES_DEPARTEMENT_VILLES})

    end_dt = datetime.datetime.now(datetime.UTC)
    start_dt = end_dt - datetime.timedelta(hours=48)

    offres_par_id = {}

    zones = codes_departements if codes_departements else [None]

    for mot in mots_inclus:
        for dept in zones:
            params = {
                "motsCles": mot,
                "minCreationDate": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "maxCreationDate": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            if salaire_min:
                params["salaireMin"] = str(salaire_min)
            if codes_rome:
                params["codeROME"] = ",".join(codes_rome)
            if dept:
                params["departement"] = dept

            resp = requests.get(SEARCH_URL, headers=headers, params=params)

            if resp.status_code == 204:
                continue
            if resp.status_code not in (200, 206):
                print(f"[france_travail] Erreur API pour '{mot}' / departement {dept} : {resp.status_code} - {resp.text[:200]}")
                continue

            resultats = resp.json().get("resultats", [])
            for r in resultats:
                titre = r.get("intitule", "")

                # L'API francetravail.io matche motsCles sur toute l'annonce (description
                # comprise), pas seulement le titre : on revérifie ici que le titre
                # correspond bien à un des mots_inclus du profil, sinon on écarte l'offre.
                if offre_contient_mot_exclu(titre, mots_exclus):
                    continue
                if mots_inclus and not offre_respecte_mots_cles(titre, mots_inclus):
                    continue

                job_id = r.get("id")
                salaire = r.get("salaire") or {}
                offres_par_id[job_id] = {
                    "job_id": job_id,
                    "titre": titre,
                    "description": r.get("description", ""),
                    "entreprise": (r.get("entreprise") or {}).get("nom", ""),
                    "salaire": salaire.get("libelle") or salaire.get("commentaire") or "",
                    "localisation": (r.get("lieuTravail") or {}).get("libelle", ""),
                    "date_publication": r.get("dateCreation", ""),
                    "url": r.get("origineOffre", {}).get("urlOrigine") or f"https://candidat.francetravail.fr/offres/recherche/detail/{job_id}",
                }

    return list(offres_par_id.values())
def get_ft_client():
    token = get_access_token()
    return token is not None