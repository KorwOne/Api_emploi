import re
import time
import threading
import pandas as pd
from jobspy import scrape_jobs
from filtre_ollama import filtrer_offres_avec_ollama

TIMEOUT_SCRAPE = 60  # secondes : LinkedIn en particulier peut se bloquer sans jamais
# renvoyer d'erreur (anti-bot silencieux). Au-delà, on abandonne cet appel et on
# passe au suivant plutôt que de rester figé indéfiniment.


def _scrape_jobs_avec_timeout(timeout, **kwargs):
    resultat = {}

    def _run():
        try:
            resultat["df"] = scrape_jobs(**kwargs)
        except Exception as e:
            resultat["erreur"] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if t.is_alive():
        return None, TimeoutError(f"pas de réponse après {timeout}s")
    if "erreur" in resultat:
        return None, resultat["erreur"]
    return resultat.get("df"), None


def contient_mot(texte, liste_mots):
    if not liste_mots:
        return False
    texte = (texte or "").lower()
    return any(re.search(rf"\b{re.escape(mot.lower())}\b", texte) for mot in liste_mots)


def filtrer_offres_pertinentes(df, niveau, domaine, mots_exclus, mots_inclus=None):

    niveau = niveau or []
    domaine = domaine or []
    mots_exclus = mots_exclus or []
    mots_inclus = mots_inclus or []

    if df.empty:
        return df

    titres = df["title"].fillna("").str.lower()

    mask_niveau = titres.apply(lambda t: contient_mot(t, niveau))
    mask_domaine = titres.apply(lambda t: contient_mot(t, domaine))
    mask_exclus = titres.apply(lambda t: contient_mot(t, mots_exclus))

    # Indeed/LinkedIn font une recherche plein texte sur le terme (mots_inclus) : le
    # titre lui-même ne contient pas forcément ce terme. On revérifie ici que le titre
    # correspond bien à un des mots_inclus du profil, sinon niveau+domaine seuls
    # laissent passer des postes trop génériques (ex: "Responsable support technique").
    if mots_inclus:
        mask_inclus = titres.apply(lambda t: contient_mot(t, mots_inclus))
    else:
        mask_inclus = True

    return df[mask_niveau & mask_domaine & mask_inclus & ~mask_exclus]
 
def normaliser_offre(row):
    job_url = row.get("job_url")
    title = row.get("title")

    if not job_url or not title:
        return None

    salaire_min = row.get("min_amount")
    if salaire_min is not None:
        try:
            salaire_min = float(salaire_min)
        except (ValueError, TypeError):
            salaire_min = None

    max_amount = row.get("max_amount")
    currency = row.get("currency") or ""
    if salaire_min and max_amount:
        salaire_texte = f"{int(salaire_min)}-{int(max_amount)} {currency}".strip()
    elif salaire_min:
        salaire_texte = f"{int(salaire_min)}+ {currency}".strip()
    else:
        salaire_texte = ""

    date_posted = row.get("date_posted")

    return {
        "job_id": job_url,
        "titre": title,
        "description": row.get("description") or "",
        "url": job_url,
        "salaire_min": salaire_min,
        "salaire": salaire_texte,
        "localisation": row.get("location"),
        "entreprise": row.get("company"),
        "date_publication": "" if pd.isna(date_posted) else str(date_posted),
    }


PAYS_JOBSPY = {
    # Glassdoor et Google ont été testés et retirés : Glassdoor bloque
    # systématiquement la résolution de localisation (protection anti-bot, HTTP 400,
    # 0 résultat) et Google échoue à trouver son curseur de pagination (0 résultat).
    # Les deux tournaient à vide en consommant du temps de cycle pour rien.
    #
    # "location" est la valeur par défaut pour FR : un profil ciblant tout le
    # territoire (ex: profil "DSI", type "region" avec plusieurs villes) garde une
    # recherche nationale. Un profil restreint à une zone précise (type "ville" dans
    # son champ "localisation", ex: profil "Chef de projet" → Paris/IDF) doit
    # utiliser une localisation ciblée sinon Indeed/LinkedIn renvoient des offres de
    # toute la France, et le filtrage géographique en aval (offre_respecte_zone)
    # laisse passer par défaut toute localisation qu'il n'identifie pas positivement.
    "FR": {"location": "France", "country_indeed": "France", "sites": ["indeed", "linkedin"]},
    "BE": {"location": "Belgium", "country_indeed": "Belgium", "sites": ["indeed"]},
    "LU": {"location": "Luxembourg", "country_indeed": "Luxembourg", "sites": ["indeed"]},
}


def _location_jobspy(pays, profil_dict):
    """Localisation à envoyer à jobspy pour un pays donné. Pour la France, si le
    profil restreint sa recherche à une ou plusieurs villes précises (champ
    "localisation"."FR"."type" == "ville"), on cible la première ville plutôt que
    tout le pays."""
    if pays == "FR":
        loc_fr = (profil_dict.get("localisation") or {}).get("FR", {})
        if loc_fr.get("type") == "ville":
            valeurs = loc_fr.get("valeurs") or []
            if valeurs:
                return f"{valeurs[0]}, France"
    return PAYS_JOBSPY[pays]["location"]


def scraper_jobspy(profil_dict):
    if not profil_dict.get("actif", True):
        return []

    mots_inclus = profil_dict.get("mots_inclus", [])
    niveau = profil_dict.get("niveau", [])
    domaine = profil_dict.get("domaine", [])
    mots_exclus = profil_dict.get("mots_exclus", [])
    pays_cibles = profil_dict.get("pays_cibles", ["FR"])

    # Indeed/LinkedIn font une recherche floue : pas besoin d'envoyer les 19 variantes
    # de titre une par une (utiles pour le matching exact d'APEC/France Travail).
    # Un profil peut définir "mots_inclus_jobspy" avec une poignée de termes génériques
    # pour réduire le nombre d'appels ; sinon on retombe sur la liste complète.
    # Le filtrage par mots_inclus (liste complète) reste appliqué sur les résultats.
    termes_recherche = profil_dict.get("mots_inclus_jobspy") or mots_inclus

    pays_actifs = [p for p in pays_cibles if p in PAYS_JOBSPY]
    if not pays_actifs:
        return []

    if not mots_inclus or not niveau or not domaine:
        return []

    toutes_offres = []

    for terme in termes_recherche:
        for pays in pays_actifs:
            cfg = PAYS_JOBSPY[pays]
            for site in cfg["sites"]:
                print(f"[DEBUG] appel jobspy site={site} pays={pays} terme={repr(terme)} niveau={niveau} domaine={domaine}")

                df, err = _scrape_jobs_avec_timeout(
                    TIMEOUT_SCRAPE,
                    site_name=[site],
                    search_term=terme,
                    location=_location_jobspy(pays, profil_dict),
                    results_wanted=15,
                    # ne pas passer country_indeed pour LinkedIn/Google (non pertinent pour ces sites)
                    **({"country_indeed": cfg["country_indeed"]} if site in ("indeed", "glassdoor") else {}),
                    hours_old=48,
                )
                if err:
                    print(f"[jobspy] site='{site}' pays='{pays}' terme='{terme}' : ERREUR — {err}")
                    continue

                df_filtre = filtrer_offres_pertinentes(df, niveau, domaine, mots_exclus, mots_inclus)

                if not df_filtre.empty:
                    toutes_offres.append(df_filtre)

                time.sleep(30 if site == "linkedin" else 20)

    if not toutes_offres:
        return []

    df_final = pd.concat(toutes_offres, ignore_index=True)

    if "job_url" in df_final.columns:
        df_final = df_final.drop_duplicates(subset=["job_url"])
    else:
        df_final = df_final.drop_duplicates()

    offres = []
    for _, row in df_final.iterrows():
        offre = normaliser_offre(row)
        if offre:
            offres.append(offre)

    return offres