import re


import re


def extraire_salaire_min(salaire_texte):
    if not salaire_texte:
        return None

    texte = salaire_texte.lower().replace(",", ".")

    nombres_k = re.findall(r"(\d+(?:\.\d+)?)\s*k\s*€", texte)
    if nombres_k:
        salaire = min(float(n) * 1000 for n in nombres_k)
        return salaire * 12 if "/ mois" in texte else salaire

    nombres_euros = re.findall(r"(\d{4,6})\s*€", texte)
    if nombres_euros:
        salaire = min(float(n) for n in nombres_euros)
        return salaire * 12 if "/ mois" in texte else salaire

    return None


def offre_respecte_salaire_min(salaire_texte, salaire_min):
    if not salaire_min:
        return True

    salaire_detecte = extraire_salaire_min(salaire_texte)
    if salaire_detecte is None:
        return True

    return salaire_detecte >= salaire_min


def offre_respecte_mots_cles(titre, mots_inclus):
    if not mots_inclus:
        return True
    titre_lower = titre.lower()
    return any(mc.lower() in titre_lower for mc in mots_inclus)


def offre_contient_mot_exclu(titre, mots_exclus):
    if not mots_exclus:
        return False
    titre_lower = titre.lower()
    return any(me.lower() in titre_lower for me in mots_exclus)