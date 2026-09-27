"""Génère une lettre de motivation .pdf à partir d'un texte déjà rédigé et validé.

Usage :
  python scripts/generer_lettre_motivation.py --fichier lettre.txt \\
      --entreprise "Informadis" --titre "Directeur Technique IT/Infrastructure"

Le texte (un paragraphe par ligne non vide) est simplement mis en page et exporté
en PDF via Word (COM) — aucune génération de contenu ici, le texte est fourni tel
quel par l'appelant.
"""
import argparse
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from docx import Document  # noqa: E402
from docx.shared import Cm, Pt  # noqa: E402

from generation_cv import _exporter_pdf, _slugifier  # noqa: E402

SORTIE_DIR = Path(r"D:\iCloudDrive\iCloudDrive\CV")


def generer_lettre_pdf(texte: str, entreprise: str, titre_poste: str) -> dict:
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(10)
    normal.paragraph_format.line_spacing = 1.15

    for ligne in texte.splitlines():
        ligne = ligne.strip()
        if ligne:
            doc.add_paragraph(ligne)

    slug_entreprise = _slugifier(entreprise, defaut="entreprise")
    slug_titre = _slugifier(titre_poste, defaut="poste")
    nom_base = f"Lettre_Motivation_Xavier_Kervagoret_{slug_entreprise}_{slug_titre}_{date.today().isoformat()}"

    chemin_docx = SORTIE_DIR / f"{nom_base}.docx"
    chemin_pdf = SORTIE_DIR / f"{nom_base}.pdf"
    SORTIE_DIR.mkdir(parents=True, exist_ok=True)
    doc.save(chemin_docx)

    pdf_ok = _exporter_pdf(chemin_docx, chemin_pdf)

    return {"chemin_docx": str(chemin_docx), "chemin_pdf": str(chemin_pdf) if pdf_ok else None}


def main():
    parser = argparse.ArgumentParser(description="Génère une lettre de motivation .pdf.")
    parser.add_argument("--entreprise", required=True)
    parser.add_argument("--titre", required=True, help="Titre du poste visé")
    groupe = parser.add_mutually_exclusive_group(required=True)
    groupe.add_argument("--texte")
    groupe.add_argument("--fichier")
    args = parser.parse_args()

    texte = args.texte if args.texte else Path(args.fichier).read_text(encoding="utf-8")

    resultat = generer_lettre_pdf(texte, args.entreprise, args.titre)

    if resultat["chemin_pdf"]:
        print(f"PDF (iCloud) : {resultat['chemin_pdf']}")
    else:
        print("Export PDF impossible (Word indisponible) — seul le .docx existe.")
    print(f"Fichier .docx : {resultat['chemin_docx']}")


if __name__ == "__main__":
    main()
