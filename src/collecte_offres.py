# src/collecte_offres.py
from typing import List, Dict

from scraper_jobspy import scraper_jobspy
from filtre_ollama import filtrer_offres_avec_ollama


def collecter_offres_pour_profil(profil_dict: Dict) -> List[Dict]:
    """
    Collecte toutes les offres d'emploi pour un profil donné :
    - appelle les moteurs (jobspy, autres à venir)
    - applique le filtre sémantique Ollama
    - renvoie une liste d'offres normalisées prêtes à être enregistrées/envoyées
    """

    offres: List[Dict] = []

    # 1) Offres via jobspy (Indeed + LinkedIn)
    offres_jobspy = scraper_jobspy(profil_dict)
    offres.extend(offres_jobspy)

    # 2) TODO : ajouter ici d'autres moteurs si tu les réactives (jobup, navigateur, etc.)
    # exemples :
    # offres_browser = scraper_browser(profil_dict)
    # offres.extend(offres_browser)

    # 3) Filtre sémantique commun via Ollama
    offres_filtrees = filtrer_offres_avec_ollama(offres)

    return offres_filtrees