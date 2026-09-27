"""CLI : génère un CV .docx adapté à une offre d'emploi.

Exemples :
  python scripts/generer_cv.py --profil-id 2 --titre "Directeur Infrastructure" \\
      --fichier offre.txt --entreprise "Acme"

  python scripts/generer_cv.py --profil-id 2 --titre "DSI" \\
      --description "Texte complet de l'offre..." --angle dsi
"""
import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from generation_cv import generer_cv_pour_offre  # noqa: E402
from filtres import offre_est_a_paris  # noqa: E402

CONFIG_PROFILS_PATH = BASE_DIR / "config" / "config_profils.json"


def charger_profil(profil_id: int) -> dict:
    with CONFIG_PROFILS_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    for p in data.get("profils", []):
        if p.get("profil_id") == profil_id:
            return p
    raise ValueError(f"Profil {profil_id} introuvable dans {CONFIG_PROFILS_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Génère un CV .docx adapté à une offre d'emploi.")
    parser.add_argument("--profil-id", type=int, required=True, help="ID du profil (voir config_profils.json)")
    parser.add_argument("--titre", required=True, help="Titre de l'offre")
    parser.add_argument("--entreprise", default=None, help="Nom de l'entreprise (pour le nom du fichier généré)")
    parser.add_argument("--angle", default=None, help="Forcer un angle (ex: dsi, infra) au lieu de la détection auto")
    parser.add_argument("--titre-cv", default=None, help="Forcer le titre affiché sur le CV (par défaut : titre de l'annonce, nettoyé du H/F)")
    parser.add_argument("--pages-max", type=int, default=2, help="Nombre de pages maximum du CV généré (défaut : 2)")
    parser.add_argument("--numero", type=int, default=None, help="Numéro d'annonce à préfixer au nom du fichier généré (ex: 12 -> 0012_CV_...)")
    parser.add_argument("--localisation", default=None, help="Localisation de l'offre (ex: 'Paris - 75', 'Lyon'), utilisée pour décider si l'adresse doit être masquée")
    groupe_desc = parser.add_mutually_exclusive_group(required=True)
    groupe_desc.add_argument("--description", help="Texte de la description de l'offre")
    groupe_desc.add_argument("--fichier", help="Chemin d'un fichier texte contenant la description de l'offre")
    args = parser.parse_args()

    profil = charger_profil(args.profil_id)
    cv_config = profil.get("cv")
    if not cv_config:
        print(f"Le profil '{profil['nom']}' (id {args.profil_id}) n'a pas de CV associé (cv: null).")
        sys.exit(1)

    if args.description:
        description = args.description
    else:
        description = Path(args.fichier).read_text(encoding="utf-8")

    masquer_adresse = bool(profil.get("masquer_adresse_hors_paris")) and not offre_est_a_paris(
        args.localisation
    )

    resultat = generer_cv_pour_offre(
        titre_offre=args.titre,
        description_offre=description,
        angles_autorises=cv_config["angles"],
        entreprise=args.entreprise,
        angle_force=args.angle,
        titre_cv_force=args.titre_cv,
        pages_max=args.pages_max,
        cv_source_path=BASE_DIR / cv_config["source"],
        masquer_adresse=masquer_adresse,
        numero_offre=args.numero,
    )

    print(f"Adresse masquée sur le CV : {'oui' if masquer_adresse else 'non'}")
    print(f"Angle choisi : {resultat['angle']}")
    print(f"Titre affiché sur le CV : {resultat['titre_cv']}")
    print(f"Mots-clés détectés ({len(resultat['mots_cles_offre'])}) : {', '.join(resultat['mots_cles_offre'])}")
    pages_info = resultat["nb_pages"] if resultat["nb_pages"] is not None else "non vérifié"
    print(f"Pages du CV généré : {pages_info} (budget max demandé : {args.pages_max})")
    if resultat["chemin_pdf"]:
        print(f"PDF (iCloud) : {resultat['chemin_pdf']}")
    else:
        print("Export PDF impossible (Word indisponible) — seul le .docx de travail existe.")
    print(f"Fichier de travail (.docx) : {resultat['chemin_docx']}")


if __name__ == "__main__":
    main()
