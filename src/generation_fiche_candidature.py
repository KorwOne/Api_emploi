import re
from datetime import date
from pathlib import Path

from filtres import deduire_site_jobspy

# Vault Obsidian de l'utilisateur (hors dépôt) : template de fiche de candidature
# et dossier de destination des offres à traiter.
OBSIDIAN_BASE = Path(r"D:\iCloudDrive\iCloudDrive\iCloud~md~obsidian\Xav")
TEMPLATE_PATH = OBSIDIAN_BASE / "99-Datas" / "Modèles" / "Candidature.md"
DOSSIER_A_POSTULER = OBSIDIAN_BASE / "2-Areas" / "Carrière-Formation" / "Emploi" / "A postuler"

# Champs du frontmatter du template remplacés par les données de l'offre.
# "statut" et "date_alerte" sont traités à part (valeur fixe / date du jour, pas
# tirée de l'offre).
_SOURCES_AFFICHAGE = {
    "france_travail": "France Travail",
    "apec": "APEC",
    "jobup.ch": "JobUp",
}


def _source_affichage(source, url):
    """Libellé de la source à afficher dans le frontmatter Obsidian. JobSpy
    interroge à la fois Indeed et LinkedIn sous l'étiquette interne unique
    'indeed_jobspy' : on distingue les deux via le domaine du lien de l'offre."""
    if source == "indeed_jobspy":
        site = deduire_site_jobspy(url)
        if site == "linkedin":
            return "LinkedIn"
        if site == "indeed":
            return "Indeed"
        return "Indeed/LinkedIn"
    return _SOURCES_AFFICHAGE.get(source, source or "")


def _valeur_yaml(valeur):
    return str(valeur).replace('"', "'") if valeur else ""


def _nom_fichier_valide(texte):
    """Retire les caractères interdits dans un nom de fichier Windows."""
    return re.sub(r'[\\/:*?"<>|]', "", texte or "").strip()


def _remplacer_ligne_frontmatter(ligne, valeurs):
    for champ, valeur in valeurs.items():
        if re.match(rf"^{re.escape(champ)}\s*:", ligne):
            return f'{champ}: "{valeur}"'
    if re.match(r"^date_alerte\s*:", ligne):
        return f"date_alerte: {date.today().isoformat()}"
    return ligne


def generer_fiche_candidature(off, numero_offre, source, cv_filename=None):
    """Génère, à partir du template Obsidian Candidature.md, une fiche de
    candidature pour l'offre et l'enregistre dans le dossier "A postuler" du
    vault. Le corps du template (sections Entretien(s)/Notes) est repris tel
    quel. Retourne le chemin du fichier créé, ou None si le template est
    introuvable (le vault n'est pas forcément accessible sur toutes les
    machines exécutant le pipeline).

    `source` est l'identifiant de moteur tel qu'enregistré en base (ex:
    "jobup.ch", "apec", "france_travail", "indeed_jobspy") : il n'est pas
    toujours présent dans `off` (le scraper JobUp par exemple ne le renseigne
    pas), donc transmis explicitement par l'appelant plutôt que déduit de
    l'offre."""
    if not TEMPLATE_PATH.exists():
        print(f"[fiche_candidature] Template introuvable : {TEMPLATE_PATH}")
        return None

    valeurs = {
        "entreprise": _valeur_yaml(off.get("entreprise")),
        "poste": _valeur_yaml(off.get("titre")),
        "source": _valeur_yaml(_source_affichage(source, off.get("url"))),
        "lieu": _valeur_yaml(off.get("localisation")),
        "salaire": _valeur_yaml(off.get("salaire")),
        "lien": _valeur_yaml(off.get("url")),
        "cv_utilise": _valeur_yaml(cv_filename),
        "statut": "A postuler",
    }

    lignes_template = TEMPLATE_PATH.read_text(encoding="utf-8").splitlines()
    lignes_generees = [_remplacer_ligne_frontmatter(ligne, valeurs) for ligne in lignes_template]

    DOSSIER_A_POSTULER.mkdir(parents=True, exist_ok=True)

    entreprise_nom = _nom_fichier_valide(off.get("entreprise")) or "Entreprise inconnue"
    poste_nom = _nom_fichier_valide(off.get("titre")) or "Poste"
    nom_fichier = f"{numero_offre} - {entreprise_nom} - {poste_nom}.md"

    chemin = DOSSIER_A_POSTULER / nom_fichier
    chemin.write_text("\n".join(lignes_generees) + "\n", encoding="utf-8")
    return chemin
