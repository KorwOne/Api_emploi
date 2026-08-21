import re
import unicodedata


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


def _normaliser_texte(texte):
    if not texte:
        return ""
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii").lower()
    texte = re.sub(r"\bst\.?-", "saint-", texte)
    texte = re.sub(r"\bste\.?-", "sainte-", texte)
    return texte


# Communes usuelles d'Île-de-France -> code département. Utilisé uniquement en
# secours quand la source ne fournit pas de code département explicite dans le
# texte de localisation (cas de JobSpy/Indeed/LinkedIn, ex: "Villepinte,
# Île-de-France, France"). Liste non exhaustive : une commune absente de ce
# dict n'est pas considérée comme hors zone, cf. offre_respecte_zone.
COMMUNES_IDF_VERS_DEPARTEMENT = {
    "paris": "75",
    "meaux": "77", "melun": "77", "chelles": "77", "torcy": "77",
    "marne-la-vallee": "77", "provins": "77", "fontainebleau": "77",
    "coulommiers": "77", "roissy-en-brie": "77", "pontault-combault": "77",
    "champs-sur-marne": "77", "noisiel": "77", "lognes": "77",
    "bussy-saint-georges": "77", "serris": "77", "ferrieres-en-brie": "77",
    "nangis": "77", "moissy-cramayel": "77", "savigny-le-temple": "77",
    "combs-la-ville": "77",
    "versailles": "78", "saint-germain-en-laye": "78", "sartrouville": "78",
    "poissy": "78", "mantes-la-jolie": "78", "rambouillet": "78",
    "montigny-le-bretonneux": "78", "trappes": "78", "guyancourt": "78",
    "elancourt": "78", "plaisir": "78", "conflans-sainte-honorine": "78",
    "les mureaux": "78", "chatou": "78", "le chesnay": "78",
    "velizy-villacoublay": "78",
    "evry": "91", "corbeil-essonnes": "91", "massy": "91", "palaiseau": "91",
    "savigny-sur-orge": "91", "sainte-genevieve-des-bois": "91",
    "draveil": "91", "athis-mons": "91", "juvisy-sur-orge": "91",
    "longjumeau": "91", "les ulis": "91", "viry-chatillon": "91",
    "ris-orangis": "91", "bretigny-sur-orge": "91",
    "nanterre": "92", "boulogne-billancourt": "92", "puteaux": "92",
    "courbevoie": "92", "colombes": "92", "asnieres-sur-seine": "92",
    "levallois-perret": "92", "clichy": "92", "rueil-malmaison": "92",
    "issy-les-moulineaux": "92", "neuilly-sur-seine": "92", "antony": "92",
    "clamart": "92", "meudon": "92", "suresnes": "92", "gennevilliers": "92",
    "bagneux": "92", "chatenay-malabry": "92", "le plessis-robinson": "92",
    "vanves": "92", "sevres": "92", "chaville": "92", "montrouge": "92",
    "fontenay-aux-roses": "92",
    "saint-denis": "93", "aubervilliers": "93", "bobigny": "93",
    "montreuil": "93", "aulnay-sous-bois": "93", "drancy": "93",
    "noisy-le-grand": "93", "sevran": "93", "pantin": "93",
    "epinay-sur-seine": "93", "le blanc-mesnil": "93", "rosny-sous-bois": "93",
    "bondy": "93", "villepinte": "93", "tremblay-en-france": "93",
    "stains": "93", "la courneuve": "93", "livry-gargan": "93",
    "neuilly-sur-marne": "93", "gagny": "93", "le raincy": "93",
    "clichy-sous-bois": "93", "bagnolet": "93", "les lilas": "93",
    "creteil": "94", "vitry-sur-seine": "94", "champigny-sur-marne": "94",
    "saint-maur-des-fosses": "94", "ivry-sur-seine": "94", "villejuif": "94",
    "maisons-alfort": "94", "vincennes": "94", "charenton-le-pont": "94",
    "fontenay-sous-bois": "94", "nogent-sur-marne": "94", "choisy-le-roi": "94",
    "alfortville": "94", "le kremlin-bicetre": "94", "l'hay-les-roses": "94",
    "cachan": "94", "bry-sur-marne": "94", "joinville-le-pont": "94",
    "saint-maurice": "94",
    "cergy": "95", "argenteuil": "95", "sarcelles": "95",
    "garges-les-gonesse": "95", "ermont": "95", "franconville": "95",
    "goussainville": "95", "enghien-les-bains": "95",
    "roissy-en-france": "95", "pontoise": "95", "herblay": "95",
    "eaubonne": "95", "domont": "95", "bezons": "95",
}


def offre_respecte_zone(localisation_texte, zones_autorisees):
    """
    Vérifie qu'une offre correspond aux départements/villes autorisés pour le
    profil (champ "zones_autorisees" du config). Le rejet ne s'applique que
    lorsqu'on peut positivement identifier la localisation de l'offre comme
    hors zone (code département détecté dans le texte, ou commune reconnue) :
    une localisation absente ou non identifiable laisse passer l'offre plutôt
    que de risquer un faux rejet.
    """
    if not zones_autorisees:
        return True

    departements = zones_autorisees.get("departements") or []
    villes = zones_autorisees.get("villes") or []

    if not departements and not villes:
        return True

    if not localisation_texte:
        return True

    texte = localisation_texte.strip()

    # Code département explicite dans le texte (formats observés :
    # APEC "Ville - 77", France Travail "77 - VILLE").
    match = re.search(r"^(\d{2})\s*-", texte) or re.search(r"-\s*(\d{2})\b", texte)
    if match and departements:
        return match.group(1) in departements

    texte_norm = _normaliser_texte(texte)

    # Ville explicitement autorisée par le profil.
    for ville in villes:
        if _normaliser_texte(ville) in texte_norm:
            return True

    # Secours : commune reconnue dans la table Île-de-France (utile pour
    # JobSpy/Indeed/LinkedIn, dont le texte ne contient pas de code département).
    if departements:
        premiere_ville = _normaliser_texte(texte.split(",")[0])
        dept_trouve = COMMUNES_IDF_VERS_DEPARTEMENT.get(premiere_ville)
        if dept_trouve:
            return dept_trouve in departements

    # Localisation non identifiable : on ne rejette pas.
    return True