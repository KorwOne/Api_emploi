# classifier_ollama.py
import logging
import os
from typing import Optional, List

import ollama
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_HOST = "http://192.168.1.156:11434"

# Client explicite plutôt que ollama.chat() + variable d'env OLLAMA_HOST : cette
# dernière peut être définie ailleurs sur la machine (ex: 0.0.0.0 par une install
# locale d'Ollama) et écraserait silencieusement l'hôte distant voulu ici.
_client = ollama.Client(host=DEFAULT_OLLAMA_HOST)


class ClassificationOffre(BaseModel):
    pertinent: bool
    raison: str


def _build_prompt(
    titre: str,
    description: str,
    mots_inclus: List[str],
    mots_exclus: List[str],
    nom_profil: str = "",
) -> str:
    inclus_str = ", ".join(mots_inclus) if mots_inclus else "aucun"
    exclus_str = ", ".join(mots_exclus) if mots_exclus else "aucun"

    return f"""Tu es un assistant de tri d'offres d'emploi pour un profil cible précis.

Profil cible : {nom_profil or "non précisé"}

- Mots à inclure (ou très proches) dans le poste ciblé : {inclus_str}
- Mots à exclure absolument : {exclus_str}

Règles de décision :

1) Réponds pertinent = true uniquement si le poste correspond au profil cible,
   en t'appuyant sur les mots à inclure. Tu peux accepter des variantes proches
   (synonymes, abréviations raisonnables), mais le sens doit rester cohérent.

2) Réponds pertinent = false si le titre contient un mot à exclure
   (exemple : alternance, stage, freelance, marketing, produit, RH, etc.).

3) Si le poste semble être dans l'IT mais clairement en dessous du niveau du profil
   (par exemple technicien, ingénieur, support, développeur pour un profil de direction),
   réponds pertinent = false.

4) Si tu hésites, sois plutôt strict et réponds pertinent = false.

Titre : {titre}
Description (facultative) : {description[:600]}
"""

def classifier_offre_ollama(
    titre: str,
    description: str = "",
    mots_inclus: Optional[List[str]] = None,
    mots_exclus: Optional[List[str]] = None,
    nom_profil: str = "",
    model: str = "qwen2.5:7b-instruct",
) -> Optional[ClassificationOffre]:
    mots_inclus = mots_inclus or []
    mots_exclus = mots_exclus or []

    # ICI : n’envoie que 4 arguments
    prompt = _build_prompt(titre, description, mots_inclus, mots_exclus)


    try:
        response = _client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            format=ClassificationOffre.model_json_schema(),
            options={"temperature": 0},
        )
    except Exception as e:
        logger.error("Erreur appel Ollama pour le titre '%s' : %s", titre, e)
        return None

    try:
        return ClassificationOffre.model_validate_json(response["message"]["content"])
    except Exception as e:
        logger.error("Erreur de validation Pydantic pour '%s' : %s", titre, e)
        return None