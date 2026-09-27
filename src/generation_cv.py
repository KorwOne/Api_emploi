"""Génère un CV .docx adapté à une offre d'emploi, à partir de data/cv/cv_source.json.

Principe : ce module ne fait que SÉLECTIONNER, RÉORDONNER et — si nécessaire pour
tenir dans le budget de pages — RÉDUIRE du contenu déjà écrit (bullets, compétences,
projets, formation). Ollama n'est utilisé que pour extraire les mots-clés du texte de
l'offre — jamais pour générer ou reformuler le contenu du CV. Le titre affiché reprend
tel quel l'intitulé de l'annonce (nettoyé des suffixes H/F). Rien n'est inventé.
"""
import json
import logging
import re
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import ollama
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from pydantic import BaseModel

from classifier_ollama import DEFAULT_OLLAMA_HOST, DEFAULT_OLLAMA_TIMEOUT

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
CV_SOURCE_PATH = BASE_DIR / "data" / "cv" / "cv_source.json"
# .docx de travail (nécessaire à _compter_pages pendant l'ajustement du budget de
# pages) : reste en local, pas besoin de synchro pour ce fichier intermédiaire.
DOSSIER_TRAVAIL = BASE_DIR / "data" / "cv" / "generes"
# PDF final, déposé dans le dossier iCloud Drive synchronisé : apparaît directement
# dans l'app Fichiers de l'iPhone, sans étape d'envoi manuelle. Le PDF est préféré
# au .docx pour la version finale : ouverture directe sans l'app Word, mise en
# page garantie identique à ce qui a été validé (Word peut re-paginer différemment
# un .docx selon la police par défaut de l'appareil qui l'ouvre).
SORTIE_DIR = Path(r"D:\iCloudDrive\iCloudDrive\CV")

PAGES_MAX_DEFAUT = 2

# Palette : bleu foncé pour les titres/accents, gris pour les métadonnées (dates,
# contexte d'entreprise, contact) afin de créer une hiérarchie visuelle claire.
COULEUR_ACCENT = RGBColor(0x1F, 0x4E, 0x79)
COULEUR_GRIS = RGBColor(0x59, 0x59, 0x59)

# Paliers de réduction du contenu, du plus complet au plus condensé. On génère le
# document avec le premier palier, on compte les pages réellement obtenues (via Word),
# et si ça dépasse le budget on passe au palier suivant, jusqu'à tenir ou épuiser
# la liste (dans ce dernier cas on garde le résultat le plus condensé).
PALIERS_BUDGET = [
    {"bullets_max": 5, "categories_max": 9, "projets_max": 3, "formation_max": 99},
    {"bullets_max": 4, "categories_max": 8, "projets_max": 2, "formation_max": 99},
    {"bullets_max": 4, "categories_max": 7, "projets_max": 2, "formation_max": 2},
    {"bullets_max": 3, "categories_max": 6, "projets_max": 1, "formation_max": 2},
    {"bullets_max": 3, "categories_max": 5, "projets_max": 1, "formation_max": 2},
    {"bullets_max": 2, "categories_max": 4, "projets_max": 0, "formation_max": 1},
]

_client = ollama.Client(host=DEFAULT_OLLAMA_HOST, timeout=DEFAULT_OLLAMA_TIMEOUT)

_SUFFIXE_HF_RE = re.compile(r"\s*[\(\[]?\s*[HF]\s*/\s*[HF]\s*[\)\]]?\s*$", re.IGNORECASE)


class MotsClesOffre(BaseModel):
    mots_cles: List[str]


def nettoyer_titre_offre(titre: str) -> str:
    """Reprend l'intitulé de l'annonce tel quel, juste débarrassé du suffixe H/F."""
    titre_propre = _SUFFIXE_HF_RE.sub("", titre or "").strip(" -–—")
    return titre_propre or (titre or "").strip() or "Poste"


def _slugifier(texte: str, defaut: str, longueur_max: int = 40) -> str:
    """Nom de fichier lisible à partir d'un texte libre (entreprise, intitulé de
    poste) : utilisé pour retrouver à quelle offre correspond un CV généré rien
    qu'en regardant le nom du fichier dans l'app Fichiers."""
    slug = "".join(c if c.isalnum() else "_" for c in (texte or "")).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug[:longueur_max].strip("_") or defaut


def charger_cv_source(path: Path = CV_SOURCE_PATH) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def extraire_mots_cles_offre(
    titre: str, description: str, model: str = "qwen2.5:7b-instruct"
) -> List[str]:
    """Demande à Ollama d'extraire les mots-clés techniques/compétences d'une offre.
    N'analyse que le texte de l'offre, jamais le CV."""
    prompt = f"""Tu extrais les mots-clés d'une offre d'emploi pour aider à adapter un CV.

Titre : {titre}
Description : {description[:3000]}

Liste les mots-clés pertinents pour un CV : technologies, outils, méthodologies,
certifications, secteurs d'activité, responsabilités (management, budget, etc.).
Un mot-clé court par item (pas de phrase complète). Maximum 40 mots-clés."""

    try:
        response = _client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            format=MotsClesOffre.model_json_schema(),
            options={"temperature": 0},
        )
        parsed = MotsClesOffre.model_validate_json(response["message"]["content"])
        return [m.strip() for m in parsed.mots_cles if m.strip()]
    except Exception as e:
        logger.error("Erreur extraction mots-clés Ollama pour '%s' : %s", titre, e)
        return []


def _score_texte(mots_cles_offre: List[str], texte: str) -> int:
    texte_lower = texte.lower()
    return sum(1 for mc in mots_cles_offre if mc.lower() in texte_lower)


def _score_items(mots_cles_offre: List[str], items: List[str]) -> int:
    return sum(_score_texte(mots_cles_offre, item) for item in items)


# Intitulés qui indiquent sans ambiguïté l'angle voulu. Sert à éviter qu'un CV
# affiche un titre d'un angle (repris tel quel de l'offre, cf. nettoyer_titre_offre)
# avec un profil/accroche d'un autre angle — une incohérence bien plus visible
# pour un recruteur qu'un simple écart de pertinence sur des mots-clés secondaires.
_INDICATEURS_ANGLE = {
    "dsi": [
        "directeur des systèmes d'information", "directeur des systemes d'information",
        "directrice des systèmes d'information", "directrice des systemes d'information",
        "responsable des systèmes d'information", "responsable des systemes d'information",
        " dsi", "dsi ", "dsi,", "dsi-", " rsi", "cio", "chief information officer",
        "directeur informatique", "directeur si", "directeur du système d'information",
        "directeur du systeme d'information",
    ],
    "infra": [
        "responsable infrastructure", "responsable infrastructures",
        "directeur infrastructure", "directeur infrastructures",
        "directeur des infrastructures", "responsable des infrastructures",
        "infrastructure manager", "head of infrastructure",
        "responsable production informatique", "responsable exploitation",
        "responsable it infrastructure",
    ],
}


def _angle_indique_par_titre(titre_offre: str, angles_autorises: List[str]) -> Optional[str]:
    """Si le titre de l'offre contient explicitement un intitulé propre à un seul
    angle, retourne cet angle (prioritaire sur le score par mots-clés). Retourne
    None si le titre est ambigu (aucun indicateur, ou indicateurs des deux
    angles) — on retombe alors sur selectionner_angle."""
    titre_lower = f" {(titre_offre or '').lower()} "
    angles_trouves = {
        angle
        for angle, indicateurs in _INDICATEURS_ANGLE.items()
        if angle in angles_autorises and any(ind in titre_lower for ind in indicateurs)
    }
    return angles_trouves.pop() if len(angles_trouves) == 1 else None


# Indicateurs de niveau DIRECTION (Directeur/DSI/CIO) pour le WORDING des intitulés
# de poste passés — volontairement plus étroit que _INDICATEURS_ANGLE["dsi"] : une
# offre "Responsable des Systèmes d'Information" (RSI) est topicalement proche de
# l'angle dsi mais reste un poste de "Responsable", pas de "Directeur" — elle ne
# doit donc PAS déclencher le wording Directeur/Adjoint DSI (cf. _niveau_intitule_poste).
_INDICATEURS_NIVEAU_DIRECTION = [
    "directeur des systèmes d'information", "directeur des systemes d'information",
    "directrice des systèmes d'information", "directrice des systemes d'information",
    "directeur informatique", "directeur si", "directeur du système d'information",
    "directeur du systeme d'information", "directeur infrastructure",
    "directeur infrastructures", "directeur des infrastructures",
    " dsi", "dsi ", "dsi,", "dsi-", "cio", "chief information officer",
]


def _niveau_intitule_poste(titre_offre: str) -> str:
    """Détermine quel wording utiliser pour les intitulés de poste passés :
    'dsi' (Directeur Infrastructure Groupe, Adjoint au DSI) si le titre de
    l'offre indique explicitement un niveau Directeur/DSI/CIO, sinon 'infra'
    (Responsable Infrastructure Groupe, sans mention Adjoint DSI) par défaut —
    y compris pour une offre 'Responsable des Systèmes d'Information' (RSI)."""
    titre_lower = f" {(titre_offre or '').lower()} "
    if any(ind in titre_lower for ind in _INDICATEURS_NIVEAU_DIRECTION):
        return "dsi"
    return "infra"


def selectionner_angle(
    cv_data: Dict, mots_cles_offre: List[str], angles_autorises: List[str]
) -> str:
    """Choisit, parmi les angles réellement écrits pour ce CV, celui dont les
    compétences recoupent le mieux les mots-clés de l'offre."""
    scores = {}
    for angle in angles_autorises:
        items_angle = [
            item
            for cat in cv_data.get("competences", [])
            if cat.get("angle") == angle
            for item in cat.get("items", [])
        ]
        scores[angle] = _score_items(mots_cles_offre, items_angle)
    return max(scores, key=scores.get)


def selectionner_contenu(
    cv_data: Dict, angle: str, mots_cles_offre: List[str], angle_intitule: Optional[str] = None
) -> Dict:
    """Score et trie le contenu existant en fonction des mots-clés de l'offre. Ne
    modifie et n'invente aucun texte — retourne tout le contenu disponible, trié,
    avec ses scores. La réduction pour tenir dans le budget de pages se fait
    séparément (voir _appliquer_budget), jamais en supprimant une expérience entière
    (l'historique factuel doit rester complet).

    `angle_intitule` (par défaut = `angle`) choisit la formulation du poste occupé
    (ex: 'Directeur Infrastructure Groupe' vs 'Responsable Infrastructure Groupe')
    indépendamment de l'angle de compétences retenu : une offre 'Responsable des
    Systèmes d'Information' reste topicalement proche de l'angle 'dsi'
    (gouvernance, stratégie) mais ne doit pas gonfler les intitulés passés en
    'Directeur' / 'Adjoint au DSI' — seul un titre d'offre explicitement
    Directeur/DSI/CIO doit déclencher ce wording (voir _niveau_intitule_poste)."""
    angle_intitule = angle_intitule or angle

    categories = [
        cat for cat in cv_data.get("competences", []) if cat.get("angle") in (angle, "commun")
    ]
    categories_triees = sorted(
        categories,
        key=lambda cat: _score_items(mots_cles_offre, cat.get("items", [])),
        reverse=True,
    )

    experiences = []
    for exp in cv_data.get("experiences", []):
        bullets = list(exp.get("bullets", {}).get(angle, []))
        bullets_tries = sorted(
            bullets, key=lambda b: _score_texte(mots_cles_offre, b), reverse=True
        )
        experiences.append(
            {
                "id": exp["id"],
                "entreprise": exp["entreprise"],
                "lieu": exp.get("lieu"),
                "periode": exp["periode"],
                "contexte": exp.get("contexte"),
                "poste": exp["poste"].get(
                    angle_intitule, exp["poste"].get(angle, next(iter(exp["poste"].values())))
                ),
                "bullets": bullets_tries,
            }
        )

    projets = [p for p in cv_data.get("projets_marquants", []) if p.get("angle") == angle]
    projets_tries = sorted(
        projets,
        key=lambda p: _score_texte(
            mots_cles_offre,
            p.get("titre", "") + " " + p.get("texte", "") + " " + " ".join(p.get("mots_cles", [])),
        ),
        reverse=True,
    )

    # Formation : l'ordre du JSON reflète déjà une priorité (diplôme le plus
    # significatif en premier), on la conserve telle quelle pour la réduction.
    formation = list(cv_data.get("formation", []))

    return {
        "categories": categories_triees,
        "experiences": experiences,
        "projets": projets_tries,
        "formation": formation,
    }


def _appliquer_budget(contenu: Dict, palier: Dict) -> Dict:
    return {
        "categories": contenu["categories"][: palier["categories_max"]],
        "experiences": [
            {**exp, "bullets": exp["bullets"][: palier["bullets_max"]]}
            for exp in contenu["experiences"]
        ],
        "projets": contenu["projets"][: palier["projets_max"]],
        "formation": contenu["formation"][: palier["formation_max"]],
    }


def _taille_etat(contenu_complet: Dict, etat: Dict) -> int:
    """Volume de texte réellement inclus par un état de remplissage — sert à
    comparer deux stratégies de remplissage et garder la plus généreuse."""
    total = sum(
        len(exp["bullets"][j])
        for exp, n in zip(contenu_complet["experiences"], etat["bullets_par_exp"])
        for j in range(n)
    )
    for p in contenu_complet["projets"][: etat["projets_max"]]:
        total += len(p.get("titre", "")) + len(p.get("texte", ""))
    for c in contenu_complet["categories"][: etat["categories_max"]]:
        total += len(c["categorie"]) + sum(len(it) for it in c["items"])
    for f in contenu_complet["formation"][: etat["formation_max"]]:
        total += len(f.get("diplome", ""))
    return total


def _remplir_glouton(
    cv_data: Dict, angle: str, titre_cv: str, contenu_complet: Dict,
    palier_depart: Dict, chemin_sortie: Path, pages_max: int, plus_gros_dabord: bool,
    masquer_adresse: bool = False,
) -> tuple:
    """Regarnit le contenu au-delà du palier de départ tant que ça tient dans le
    budget de pages. À chaque étape, essaie soit le plus gros soit le plus petit
    ajout encore disponible (bullet, projet, catégorie ou diplôme suivant) selon
    `plus_gros_dabord` ; un ajout qui dépasse le budget est écarté définitivement
    pour ce candidat précis (ajouter du contenu ne peut que resserrer l'espace
    disponible, jamais l'agrandir)."""
    experiences_completes = contenu_complet["experiences"]

    bullets_par_exp = [
        min(palier_depart["bullets_max"], len(exp["bullets"])) for exp in experiences_completes
    ]
    projets_n = min(palier_depart["projets_max"], len(contenu_complet["projets"]))
    categories_n = min(palier_depart["categories_max"], len(contenu_complet["categories"]))
    formation_n = min(palier_depart["formation_max"], len(contenu_complet["formation"]))

    bloques = set()
    nb_pages_courant = None

    def _generer_et_compter():
        contenu = {
            "categories": contenu_complet["categories"][:categories_n],
            "experiences": [
                {**exp, "bullets": exp["bullets"][:n]}
                for exp, n in zip(experiences_completes, bullets_par_exp)
            ],
            "projets": contenu_complet["projets"][:projets_n],
            "formation": contenu_complet["formation"][:formation_n],
        }
        generer_docx(cv_data, angle, titre_cv, contenu, chemin_sortie, masquer_adresse)
        return _compter_pages(chemin_sortie)

    def _candidats():
        candidats = []
        for i, exp in enumerate(experiences_completes):
            if ("bullet", i) in bloques or bullets_par_exp[i] >= len(exp["bullets"]):
                continue
            texte = exp["bullets"][bullets_par_exp[i]]
            candidats.append((len(texte), "bullet", i))
        if "projet" not in bloques and projets_n < len(contenu_complet["projets"]):
            p = contenu_complet["projets"][projets_n]
            taille = len(p.get("titre", "")) + len(p.get("texte", ""))
            candidats.append((taille, "projet", None))
        if "categorie" not in bloques and categories_n < len(contenu_complet["categories"]):
            cat = contenu_complet["categories"][categories_n]
            taille = len(cat["categorie"]) + sum(len(it) for it in cat["items"])
            candidats.append((taille, "categorie", None))
        if "formation" not in bloques and formation_n < len(contenu_complet["formation"]):
            f = contenu_complet["formation"][formation_n]
            taille = len(f.get("diplome", ""))
            candidats.append((taille, "formation", None))
        candidats.sort(key=lambda c: c[0], reverse=plus_gros_dabord)
        return candidats

    while True:
        candidats = _candidats()
        if not candidats:
            break
        _, type_, idx = candidats[0]

        if type_ == "bullet":
            bullets_par_exp[idx] += 1
        elif type_ == "projet":
            projets_n += 1
        elif type_ == "categorie":
            categories_n += 1
        elif type_ == "formation":
            formation_n += 1

        pages = _generer_et_compter()
        if pages is not None and pages <= pages_max:
            nb_pages_courant = pages
            continue

        # Échec : on annule cet ajout et on écarte définitivement ce candidat.
        if type_ == "bullet":
            bullets_par_exp[idx] -= 1
            bloques.add(("bullet", idx))
        elif type_ == "projet":
            projets_n -= 1
            bloques.add("projet")
        elif type_ == "categorie":
            categories_n -= 1
            bloques.add("categorie")
        elif type_ == "formation":
            formation_n -= 1
            bloques.add("formation")

    etat = {
        "bullets_par_exp": bullets_par_exp,
        "projets_max": projets_n,
        "categories_max": categories_n,
        "formation_max": formation_n,
    }
    return etat, nb_pages_courant


def _remplir_round_robin(
    cv_data: Dict, angle: str, titre_cv: str, contenu_complet: Dict,
    palier_depart: Dict, chemin_sortie: Path, pages_max: int,
    masquer_adresse: bool = False,
) -> tuple:
    """Troisième stratégie de remplissage : une passe à la fois, un ajout par
    expérience (dans l'ordre chronologique du CV) puis un projet/catégorie/diplôme,
    en recommençant tant qu'au moins un ajout de la passe a réussi. Empiriquement,
    cet ordre trouve parfois une meilleure combinaison que les deux stratégies
    "par taille" (cf. _remplir_glouton) sur certains contenus."""
    experiences_completes = contenu_complet["experiences"]

    bullets_par_exp = [
        min(palier_depart["bullets_max"], len(exp["bullets"])) for exp in experiences_completes
    ]
    projets_n = min(palier_depart["projets_max"], len(contenu_complet["projets"]))
    categories_n = min(palier_depart["categories_max"], len(contenu_complet["categories"]))
    formation_n = min(palier_depart["formation_max"], len(contenu_complet["formation"]))

    exp_bloquees = set()
    projets_bloque = categories_bloque = formation_bloque = False
    nb_pages_courant = None

    def _generer_et_compter():
        contenu = {
            "categories": contenu_complet["categories"][:categories_n],
            "experiences": [
                {**exp, "bullets": exp["bullets"][:n]}
                for exp, n in zip(experiences_completes, bullets_par_exp)
            ],
            "projets": contenu_complet["projets"][:projets_n],
            "formation": contenu_complet["formation"][:formation_n],
        }
        generer_docx(cv_data, angle, titre_cv, contenu, chemin_sortie, masquer_adresse)
        return _compter_pages(chemin_sortie)

    progres = True
    while progres:
        progres = False

        for i, exp in enumerate(experiences_completes):
            if i in exp_bloquees or bullets_par_exp[i] >= len(exp["bullets"]):
                continue
            bullets_par_exp[i] += 1
            pages = _generer_et_compter()
            if pages is not None and pages <= pages_max:
                nb_pages_courant = pages
                progres = True
            else:
                bullets_par_exp[i] -= 1
                exp_bloquees.add(i)

        if not projets_bloque and projets_n < len(contenu_complet["projets"]):
            projets_n += 1
            pages = _generer_et_compter()
            if pages is not None and pages <= pages_max:
                nb_pages_courant = pages
                progres = True
            else:
                projets_n -= 1
                projets_bloque = True

        if not categories_bloque and categories_n < len(contenu_complet["categories"]):
            categories_n += 1
            pages = _generer_et_compter()
            if pages is not None and pages <= pages_max:
                nb_pages_courant = pages
                progres = True
            else:
                categories_n -= 1
                categories_bloque = True

        if not formation_bloque and formation_n < len(contenu_complet["formation"]):
            formation_n += 1
            pages = _generer_et_compter()
            if pages is not None and pages <= pages_max:
                nb_pages_courant = pages
                progres = True
            else:
                formation_n -= 1
                formation_bloque = True

    etat = {
        "bullets_par_exp": bullets_par_exp,
        "projets_max": projets_n,
        "categories_max": categories_n,
        "formation_max": formation_n,
    }
    return etat, nb_pages_courant


def _affiner_palier(
    cv_data: Dict, angle: str, titre_cv: str, contenu_complet: Dict,
    palier_depart: Dict, chemin_sortie: Path, pages_max: int,
    masquer_adresse: bool = False,
) -> tuple:
    """Essaie plusieurs ordres de remplissage glouton (plus gros d'abord, plus
    petit d'abord, round-robin par expérience) — aucun n'est fiablement meilleur
    que les autres selon le contenu (constaté empiriquement), donc on garde celui
    qui inclut le plus de contenu réel au final plutôt que de parier sur un seul."""
    strategies = [
        _remplir_glouton(
            cv_data, angle, titre_cv, contenu_complet, palier_depart, chemin_sortie, pages_max,
            plus_gros_dabord=True, masquer_adresse=masquer_adresse,
        ),
        _remplir_glouton(
            cv_data, angle, titre_cv, contenu_complet, palier_depart, chemin_sortie, pages_max,
            plus_gros_dabord=False, masquer_adresse=masquer_adresse,
        ),
        _remplir_round_robin(
            cv_data, angle, titre_cv, contenu_complet, palier_depart, chemin_sortie, pages_max,
            masquer_adresse=masquer_adresse,
        ),
    ]

    etat_final, nb_pages = max(
        strategies, key=lambda resultat: _taille_etat(contenu_complet, resultat[0])
    )

    # Régénère le fichier final avec l'état retenu (le dernier essai généré sur
    # disque peut correspondre à l'autre stratégie).
    contenu_final = {
        "categories": contenu_complet["categories"][: etat_final["categories_max"]],
        "experiences": [
            {**exp, "bullets": exp["bullets"][:n]}
            for exp, n in zip(contenu_complet["experiences"], etat_final["bullets_par_exp"])
        ],
        "projets": contenu_complet["projets"][: etat_final["projets_max"]],
        "formation": contenu_complet["formation"][: etat_final["formation_max"]],
    }
    generer_docx(cv_data, angle, titre_cv, contenu_final, chemin_sortie, masquer_adresse)

    return etat_final, nb_pages


def _bordure_basse(element, couleur="1F4E79", taille=6, espace=3) -> None:
    """Ajoute un filet fin sous un paragraphe ou un style (séparateur visuel),
    en manipulant directement le XML — python-docx n'expose pas les bordures
    de paragraphe via son API haut niveau."""
    p_pr = element.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(taille))
    bottom.set(qn("w:space"), str(espace))
    bottom.set(qn("w:color"), couleur)
    p_bdr.append(bottom)
    p_pr.append(p_bdr)


def _configurer_mise_en_page(doc: Document) -> None:
    """Mise en page compacte mais aérée : couleurs d'accent, séparateurs fins sous
    les titres de section, gris pour les métadonnées — pour éviter l'effet
    'mur de texte' tout en gardant le contenu dense sur 2 pages."""
    section = doc.sections[0]
    section.top_margin = Cm(1.4)
    section.bottom_margin = Cm(1.4)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.05

    if "List Bullet" in styles:
        lb = styles["List Bullet"]
        lb.font.size = Pt(10)
        lb.paragraph_format.space_before = Pt(0)
        lb.paragraph_format.space_after = Pt(2)
        lb.paragraph_format.line_spacing = 1.05
        # Pas de justification par défaut sur ce style : dans le tableau 2
        # colonnes des compétences, la colonne est trop étroite et le texte
        # justifié sur les lignes courtes qui retournent à la ligne donne un
        # espacement disgracieux. Les bullets d'expériences (pleine largeur,
        # texte long) sont justifiés individuellement à la génération.

    if "Title" in styles:
        titre_style = styles["Title"]
        titre_style.font.size = Pt(20)
        titre_style.font.color.rgb = COULEUR_ACCENT
        titre_style.paragraph_format.space_after = Pt(2)

    if "Heading 1" in styles:
        h1 = styles["Heading 1"]
        h1.font.size = Pt(12)
        h1.font.color.rgb = COULEUR_ACCENT
        h1.paragraph_format.space_before = Pt(10)
        h1.paragraph_format.space_after = Pt(4)
        _bordure_basse(h1.paragraph_format._element)

    if "Heading 2" in styles:
        h2 = styles["Heading 2"]
        h2.font.size = Pt(10.5)
        h2.font.color.rgb = COULEUR_ACCENT
        h2.paragraph_format.space_before = Pt(6)
        h2.paragraph_format.space_after = Pt(2)


def _ajouter_competences(doc: Document, categories: List[Dict]) -> None:
    """Affiche les catégories de compétences en 2 colonnes plutôt qu'empilées en
    une seule liste verticale : plus compact et plus lisible qu'un mur de puces."""
    if not categories:
        return

    doc.add_heading("Compétences", level=1)

    moitie = (len(categories) + 1) // 2
    colonnes = [categories[:moitie], categories[moitie:]]

    table = doc.add_table(rows=1, cols=2)
    table.autofit = True
    cellules = table.rows[0].cells

    for cellule, cats in zip(cellules, colonnes):
        premier = True
        for cat in cats:
            p = cellule.paragraphs[0] if premier else cellule.add_paragraph()
            premier = False
            p.paragraph_format.space_before = Pt(0) if p is cellule.paragraphs[0] else Pt(6)
            p.paragraph_format.space_after = Pt(2)
            r = p.add_run(cat["categorie"])
            r.bold = True
            r.font.size = Pt(10)
            r.font.color.rgb = COULEUR_ACCENT
            for item in cat["items"]:
                p_item = cellule.add_paragraph(item, style="List Bullet")
                p_item.paragraph_format.space_after = Pt(1)


def generer_docx(
    cv_data: Dict, angle: str, titre_cv: str, contenu: Dict, chemin_sortie: Path,
    masquer_adresse: bool = False,
) -> None:
    identite = cv_data["identite"]
    en_tete = next(e for e in cv_data["en_tete"] if e["angle"] == angle)
    profil = next(p for p in cv_data["profil"] if p["angle"] == angle)

    doc = Document()
    _configurer_mise_en_page(doc)

    doc.add_heading(identite["nom"], level=0)

    p_titre = doc.add_paragraph()
    r_titre = p_titre.add_run(f"{titre_cv} - {identite['contrat_recherche']}")
    r_titre.bold = True
    r_titre.font.size = Pt(11)
    p_titre.paragraph_format.space_after = Pt(2)

    parties_contact = [] if masquer_adresse else [identite["adresse"]]
    parties_contact += [identite.get("telephone", ""), identite["email"], identite.get("linkedin", "")]
    contact = " · ".join(p for p in parties_contact if p)
    if identite.get("disponibilite"):
        contact += f" · Disponibilité : {identite['disponibilite']}"
    p_contact = doc.add_paragraph()
    r_contact = p_contact.add_run(contact)
    r_contact.font.size = Pt(9)
    r_contact.font.color.rgb = COULEUR_GRIS
    p_contact.paragraph_format.space_after = Pt(2)

    p_accroche = doc.add_paragraph()
    r_accroche = p_accroche.add_run(en_tete["accroche"])
    r_accroche.italic = True
    r_accroche.font.color.rgb = COULEUR_ACCENT
    p_accroche.paragraph_format.space_after = Pt(8)
    _bordure_basse(p_accroche._p)

    doc.add_heading("Profil", level=1)
    p_profil = doc.add_paragraph(profil["texte"])
    p_profil.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    if contenu["experiences"]:
        doc.add_heading("Expériences professionnelles", level=1)
        for i, exp in enumerate(contenu["experiences"]):
            p = doc.add_paragraph()
            if i > 0:
                p.paragraph_format.space_before = Pt(8)
            # Empêche l'intitulé de poste de se retrouver seul en bas de page,
            # séparé de son contexte/ses puces par un saut de page : Word
            # pousse alors tout le bloc (intitulé + paragraphe suivant) sur la
            # page suivante plutôt que de le couper.
            p.paragraph_format.keep_with_next = True
            r_poste = p.add_run(exp["poste"])
            r_poste.bold = True
            r_poste.font.color.rgb = COULEUR_ACCENT
            p.add_run(f" — {exp['entreprise']} ({exp['lieu']}) — {exp['periode']}")
            if exp.get("contexte"):
                p_ctx = doc.add_paragraph()
                p_ctx.paragraph_format.space_after = Pt(2)
                p_ctx.paragraph_format.keep_with_next = True
                r_ctx = p_ctx.add_run(exp["contexte"])
                r_ctx.italic = True
                r_ctx.font.size = Pt(9)
                r_ctx.font.color.rgb = COULEUR_GRIS
            for bullet in exp["bullets"]:
                p_bullet = doc.add_paragraph(bullet, style="List Bullet")
                p_bullet.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    if len(contenu["projets"]) >= 2:
        # Une section "Projets marquants" avec un seul item détonne
        # visuellement (titre de section pour une seule ligne) : on ne
        # l'affiche qu'à partir de 2 projets retenus.
        doc.add_heading("Projets marquants", level=1)
        for proj in contenu["projets"]:
            p = doc.add_paragraph()
            r = p.add_run(proj["titre"])
            r.bold = True
            r.font.color.rgb = COULEUR_ACCENT
            p_proj = doc.add_paragraph(proj["texte"])
            p_proj.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    _ajouter_competences(doc, contenu["categories"])

    if contenu["formation"]:
        doc.add_heading("Formation", level=1)
        for f in contenu["formation"]:
            ligne = f["diplome"]
            if f.get("etablissement"):
                ligne += f" — {f['etablissement']}"
            if f.get("periode"):
                ligne += f" ({f['periode']})"
            doc.add_paragraph(ligne, style="List Bullet")

    doc.add_heading("Langues", level=1)
    for l in cv_data.get("langues", []):
        doc.add_paragraph(f"{l['langue']} : {l['niveau']}", style="List Bullet")

    chemin_sortie.parent.mkdir(parents=True, exist_ok=True)
    doc.save(chemin_sortie)


# Instance Word partagée pendant la génération d'un CV (cf. _session_word). Sans
# elle, chaque comptage de pages lançait puis quittait Word (~6 s), soit 3-4 min
# par CV avec les dizaines de comptages de _affiner_palier : l'exécution planifiée
# dépassait alors les 30 min et les suivantes étaient sautées.
_word_partage = None


@contextmanager
def _session_word():
    """Ouvre une instance Word dédiée (DispatchEx : n'interfère pas avec un Word
    ouvert par l'utilisateur) réutilisée par _compter_pages/_exporter_pdf, puis la
    ferme. Si Word n'est pas disponible, ces fonctions gardent leur comportement
    d'origine (une instance par appel)."""
    global _word_partage
    try:
        import pythoncom
        import win32com.client as win32
    except ImportError:
        yield
        return

    pythoncom.CoInitialize()
    try:
        try:
            _word_partage = win32.DispatchEx("Word.Application")
            _word_partage.Visible = False
            _word_partage.DisplayAlerts = 0
        except Exception as e:
            logger.warning("Impossible d'ouvrir une instance Word partagée : %s", e)
            _word_partage = None
        yield
    finally:
        if _word_partage is not None:
            try:
                _word_partage.Quit()
            except Exception:
                pass
            _word_partage = None
        pythoncom.CoUninitialize()


def _compter_pages(chemin: Path, tentatives: int = 3) -> Optional[int]:
    """Compte les pages réelles du document via Word (COM). Retourne None si Word
    n'est pas disponible (ex: environnement sans Office) plutôt que de faire échouer
    toute la génération. Les appels COM à Word peuvent échouer de façon transitoire
    (RPC_E_CALL_REJECTED) au premier appel : on retente quelques fois."""
    if _word_partage is not None:
        try:
            doc = _word_partage.Documents.Open(str(chemin.resolve()))
            try:
                return doc.ComputeStatistics(2)  # wdStatisticPages
            finally:
                doc.Close(False)
        except Exception as e:
            logger.warning("Instance Word partagée en échec (%s) : repli sur une instance dédiée.", e)

    try:
        import time
        import pythoncom
        import win32com.client as win32
    except ImportError:
        logger.warning("pywin32 indisponible : impossible de vérifier le nombre de pages.")
        return None

    derniere_erreur = None
    for tentative in range(1, tentatives + 1):
        try:
            pythoncom.CoInitialize()
            word = win32.Dispatch("Word.Application")
            word.Visible = False
            try:
                doc = word.Documents.Open(str(chemin.resolve()))
                try:
                    return doc.ComputeStatistics(2)  # wdStatisticPages
                finally:
                    doc.Close(False)
            finally:
                word.Quit()
        except Exception as e:
            derniere_erreur = e
            time.sleep(1.5)
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    logger.warning(
        "Impossible de compter les pages via Word après %d tentative(s) : %s",
        tentatives, derniere_erreur,
    )
    return None


def _exporter_pdf(chemin_docx: Path, chemin_pdf: Path, tentatives: int = 3) -> bool:
    """Exporte le .docx final en PDF via Word (COM). Retourne False (sans lever
    d'exception) si Word n'est pas disponible ou si l'export échoue après
    plusieurs tentatives — l'appelant garde alors le .docx comme seul livrable."""
    if _word_partage is not None:
        try:
            chemin_pdf.parent.mkdir(parents=True, exist_ok=True)
            doc = _word_partage.Documents.Open(str(chemin_docx.resolve()))
            try:
                doc.SaveAs(str(chemin_pdf.resolve()), FileFormat=17)  # wdFormatPDF
                return True
            finally:
                doc.Close(False)
        except Exception as e:
            logger.warning("Instance Word partagée en échec (%s) : repli sur une instance dédiée.", e)

    try:
        import time
        import pythoncom
        import win32com.client as win32
    except ImportError:
        logger.warning("pywin32 indisponible : export PDF impossible.")
        return False

    chemin_pdf.parent.mkdir(parents=True, exist_ok=True)
    derniere_erreur = None
    for tentative in range(1, tentatives + 1):
        try:
            pythoncom.CoInitialize()
            word = win32.Dispatch("Word.Application")
            word.Visible = False
            try:
                doc = word.Documents.Open(str(chemin_docx.resolve()))
                try:
                    doc.SaveAs(str(chemin_pdf.resolve()), FileFormat=17)  # wdFormatPDF
                    return True
                finally:
                    doc.Close(False)
            finally:
                word.Quit()
        except Exception as e:
            derniere_erreur = e
            time.sleep(1.5)
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    logger.warning(
        "Impossible d'exporter en PDF via Word après %d tentative(s) : %s",
        tentatives, derniere_erreur,
    )
    return False


def generer_cv_pour_offre(
    titre_offre: str,
    description_offre: str,
    angles_autorises: List[str],
    entreprise: Optional[str] = None,
    angle_force: Optional[str] = None,
    titre_cv_force: Optional[str] = None,
    pages_max: int = PAGES_MAX_DEFAUT,
    cv_source_path: Path = CV_SOURCE_PATH,
    dossier_travail: Path = DOSSIER_TRAVAIL,
    dossier_sortie: Path = SORTIE_DIR,
    masquer_adresse: bool = False,
    numero_offre: Optional[int] = None,
) -> Dict:
    cv_data = charger_cv_source(cv_source_path)

    mots_cles_offre = extraire_mots_cles_offre(titre_offre, description_offre)
    if not mots_cles_offre:
        logger.warning(
            "Aucun mot-clé extrait pour '%s' (Ollama injoignable/erreur) : "
            "sélection de secours sans priorisation.",
            titre_offre,
        )

    angle = (
        angle_force
        or _angle_indique_par_titre(titre_offre, angles_autorises)
        or selectionner_angle(cv_data, mots_cles_offre, angles_autorises)
    )
    if angle not in angles_autorises:
        raise ValueError(
            f"Angle '{angle}' non disponible pour ce profil (angles autorisés : {angles_autorises})"
        )

    titre_cv = titre_cv_force or nettoyer_titre_offre(titre_offre)

    angle_intitule = _niveau_intitule_poste(titre_offre)
    if angle_intitule not in angles_autorises:
        angle_intitule = angle
    contenu_complet = selectionner_contenu(cv_data, angle, mots_cles_offre, angle_intitule)

    slug_entreprise = _slugifier(entreprise, defaut="offre")
    slug_titre = _slugifier(titre_cv, defaut="poste")
    # Le numéro d'annonce (id de l'offre en base, unique et croissant) est préfixé
    # en tout premier dans le nom de fichier pour pouvoir relier un CV généré à
    # l'annonce correspondante d'un simple coup d'œil dans l'app Fichiers.
    prefixe_numero = f"{numero_offre:04d}_" if numero_offre is not None else ""
    nom_base = f"{prefixe_numero}CV_Xavier_Kervagoret_{angle}_{slug_entreprise}_{slug_titre}_{date.today().isoformat()}"
    chemin_sortie = dossier_travail / f"{nom_base}.docx"

    nb_pages = None
    palier_utilise = None
    verification_possible = True
    with _session_word():
        for i, palier in enumerate(PALIERS_BUDGET):
            contenu = _appliquer_budget(contenu_complet, palier)
            generer_docx(cv_data, angle, titre_cv, contenu, chemin_sortie, masquer_adresse)

            nb_pages = _compter_pages(chemin_sortie)
            palier_utilise = i
            if nb_pages is None:
                # Pas de vérification possible : on garde le 2e palier (raisonnable
                # par défaut) et on prévient que ce n'est pas garanti.
                verification_possible = False
                logger.warning(
                    "Nombre de pages non vérifié pour '%s' : contenu réduit par précaution "
                    "(palier %d/%d) sans confirmation.",
                    chemin_sortie.name, i + 1, len(PALIERS_BUDGET),
                )
                break
            if nb_pages <= pages_max:
                break
        else:
            logger.warning(
                "Impossible de tenir dans %d page(s) même au palier le plus réduit "
                "(résultat : %s page(s)).",
                pages_max, nb_pages,
            )

        # Une fois un palier sûr trouvé, on regarnit le contenu pour combler l'espace
        # restant plutôt que de laisser une page à moitié vide.
        if verification_possible and nb_pages is not None and nb_pages <= pages_max:
            _, nb_pages_affine = _affiner_palier(
                cv_data, angle, titre_cv, contenu_complet,
                PALIERS_BUDGET[palier_utilise], chemin_sortie, pages_max,
                masquer_adresse=masquer_adresse,
            )
            if nb_pages_affine is not None:
                nb_pages = nb_pages_affine

        chemin_pdf = dossier_sortie / f"{nom_base}.pdf"
        pdf_ok = _exporter_pdf(chemin_sortie, chemin_pdf)

    return {
        "angle": angle,
        "titre_cv": titre_cv,
        "mots_cles_offre": mots_cles_offre,
        "chemin_docx": str(chemin_sortie),
        "chemin_pdf": str(chemin_pdf) if pdf_ok else None,
        "nb_pages": nb_pages,
        "palier_reduction": palier_utilise,
        "numero_offre": numero_offre,
    }
