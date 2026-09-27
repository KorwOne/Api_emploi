from typing import List, Dict
from classifier_ollama import classifier_offre_ollama
from filtres import titre_entierement_anglais

USE_OLLAMA = True  # passe à True quand test_ollama.py fonctionnera

def filtrer_offres_avec_ollama(offres: List[Dict], profil_dict: Dict) -> List[Dict]:
    """
    Applique le filtre sémantique Ollama sur une liste d'offres normalisées,
    en tenant compte des mots_inclus / mots_exclus du profil.
    Chaque offre est un dict avec au minimum 'titre' et optionnellement 'description'.
    """

    if not USE_OLLAMA:
        return offres

    offres_finales: List[Dict] = []

    # Critères du profil
    mots_inclus = profil_dict.get("mots_inclus", [])
    mots_exclus = profil_dict.get("mots_exclus", [])

    for o in offres:
        titre = o.get("titre") or ""
        description = o.get("description") or ""
        source = o.get("source", "?")

        classification = classifier_offre_ollama(
            titre=titre,
            description=description,
            mots_inclus=mots_inclus,
            mots_exclus=mots_exclus,
        )
        if classification is None:
            print(f"[ollama] rejet par défaut ({source}) : '{titre}' -> Ollama injoignable/erreur")
            continue

        if classification.pertinent:
            offres_finales.append(o)
        else:
            print(f"[ollama] rejet ({source}) : '{titre}' -> {classification.raison}")

    return offres_finales


def filtrer_titres_anglais(offres: List[Dict], profil_dict: Dict) -> List[Dict]:
    """Si le profil a 'exclure_titres_anglais' activé, écarte les offres dont le
    titre est rédigé ENTIÈREMENT en anglais. Les titres français contenant un
    terme anglais isolé (ex: 'Head of IT', 'CIO') sont conservés — voir
    filtres.titre_entierement_anglais pour la règle exacte (heuristique
    déterministe, pas Ollama : testé peu fiable sur cette tâche précise)."""
    if not profil_dict.get("exclure_titres_anglais"):
        return offres

    offres_finales: List[Dict] = []
    for o in offres:
        titre = o.get("titre") or ""
        source = o.get("source", "?")

        if titre_entierement_anglais(titre):
            print(f"[langue] rejet ({source}) : '{titre}' -> titre entièrement en anglais")
        else:
            offres_finales.append(o)

    return offres_finales