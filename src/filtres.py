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


# Mots grammaticaux + vocabulaire courant des intitulés de poste en français.
# Utilisé pour repérer un titre "entièrement en anglais" par absence de tout
# marqueur français, plutôt que par une classification LLM (testé peu fiable sur
# cette tâche précise : le modèle confondait "Director"/"Directeur" et
# considérait "of" comme un mot français).
_MARQUEURS_FRANCAIS = {
    "de", "des", "du", "le", "la", "les", "un", "une", "et", "ou", "à", "au", "aux",
    "pour", "chez", "dans", "sur", "sous", "avec", "entre", "en", "d", "l",
    "directeur", "directrice", "responsable", "chef", "cheffe", "adjoint", "adjointe",
    "gestionnaire", "conseiller", "conseillere", "assistant", "assistante",
    "charge", "chargee", "groupe", "societe", "entreprise", "national", "nationale",
    "regional", "regionale", "france", "francais", "francaise",
}
_CARACTERES_ACCENTUES_FR = "éèêëàâäùûüôöîïçœ"


def titre_entierement_anglais(titre):
    """Un titre est considéré 'entièrement en anglais' seulement s'il ne contient
    AUCUN marqueur français identifiable (mot grammatical/vocabulaire courant
    français, caractère accentué, ou mention 'H/F'/'F/H'). Un titre mixte (ex:
    'Directeur IT - Head of Infrastructure', 'Responsable SI (CIO)') reste donc
    considéré comme non-anglais dès qu'un seul marqueur apparaît."""
    if not titre:
        return False
    titre_lower = titre.lower()
    if any(c in titre_lower for c in _CARACTERES_ACCENTUES_FR):
        return False
    if "h/f" in titre_lower or "f/h" in titre_lower:
        return False
    mots = re.findall(r"[a-zà-ÿ']+", titre_lower)
    return not any(mot in _MARQUEURS_FRANCAIS for mot in mots)


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
    "la defense": "92", "saint-ouen": "93", "saint-ouen-sur-seine": "93",
    "neuilly-plaisance": "93",
}

# Noms de départements d'Île-de-France parfois utilisés seuls par JobSpy
# (ex: "Essonne, Île-de-France, France").
DEPARTEMENTS_IDF_PAR_NOM = {
    "paris": "75", "seine-et-marne": "77", "yvelines": "78", "essonne": "91",
    "hauts-de-seine": "92", "seine-saint-denis": "93", "val-de-marne": "94",
    "val-d'oise": "95",
}

# Régions -> départements. Sert à rejeter une offre dont seule la région est
# identifiable (cas fréquent chez JobSpy : "Senlis, HDF, FR", "Lyon,
# Auvergne-Rhône-Alpes, France") quand aucun département autorisé n'en fait partie.
DEPARTEMENTS_PAR_REGION = {
    "ile-de-france": ["75", "77", "78", "91", "92", "93", "94", "95"],
    "hauts-de-france": ["02", "59", "60", "62", "80"],
    "grand est": ["08", "10", "51", "52", "54", "55", "57", "67", "68", "88"],
    "normandie": ["14", "27", "50", "61", "76"],
    "bretagne": ["22", "29", "35", "56"],
    "pays de la loire": ["44", "49", "53", "72", "85"],
    "centre-val de loire": ["18", "28", "36", "37", "41", "45"],
    "bourgogne-franche-comte": ["21", "25", "39", "58", "70", "71", "89", "90"],
    "auvergne-rhone-alpes": ["01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"],
    "nouvelle-aquitaine": ["16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87"],
    "occitanie": ["09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"],
    "provence-alpes-cote d'azur": ["04", "05", "06", "13", "83", "84"],
    "corse": ["2A", "2B"],
}

# Abréviations observées chez Indeed/LinkedIn (sigles actuels, anciens codes
# FIPS des 22 régions, noms anglais), comparées à un segment entier du texte.
ALIAS_REGIONS = {
    "idf": "ile-de-france", "a8": "ile-de-france",
    "hdf": "hauts-de-france", "b4": "hauts-de-france", "b6": "hauts-de-france",
    "ges": "grand est", "a4": "grand est", "b2": "grand est", "c1": "grand est",
    "n": "normandie", "nor": "normandie", "a7": "normandie", "normandy": "normandie",
    "bre": "bretagne", "a2": "bretagne", "brittany": "bretagne",
    "pdl": "pays de la loire", "b5": "pays de la loire",
    "cvl": "centre-val de loire", "a3": "centre-val de loire",
    "bfc": "bourgogne-franche-comte", "a1": "bourgogne-franche-comte", "a6": "bourgogne-franche-comte",
    "ara": "auvergne-rhone-alpes", "b9": "auvergne-rhone-alpes",
    "na": "nouvelle-aquitaine", "naq": "nouvelle-aquitaine", "b7": "nouvelle-aquitaine", "b1": "nouvelle-aquitaine",
    "occ": "occitanie", "b3": "occitanie", "a9": "occitanie",
    "pac": "provence-alpes-cote d'azur", "paca": "provence-alpes-cote d'azur", "b8": "provence-alpes-cote d'azur",
    "cor": "corse", "a5": "corse",
}


def _region_de_segment(segment_norm):
    if segment_norm in DEPARTEMENTS_PAR_REGION:
        return segment_norm
    return ALIAS_REGIONS.get(segment_norm)


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
        segments = [s.strip() for s in texte_norm.split(",")]
        dept_trouve = COMMUNES_IDF_VERS_DEPARTEMENT.get(segments[0])
        if dept_trouve:
            return dept_trouve in departements

        # Nom de département seul (ex: "Essonne, Île-de-France, France").
        for segment in segments:
            dept_trouve = DEPARTEMENTS_IDF_PAR_NOM.get(segment)
            if dept_trouve:
                return dept_trouve in departements

        # Seule la région est identifiable (ex: "Senlis, HDF, FR") : rejet si
        # aucun département autorisé n'appartient à cette région.
        for segment in segments:
            region = _region_de_segment(segment)
            if region:
                return any(d in departements for d in DEPARTEMENTS_PAR_REGION[region])

    # Localisation non identifiable : on ne rejette pas.
    return True


def deduire_site_jobspy(url):
    """JobSpy interroge à la fois Indeed et LinkedIn sous l'étiquette interne
    unique 'indeed_jobspy' (cf. scraper_jobspy.PAYS_JOBSPY) : distingue les deux
    via le domaine du lien de l'offre. Retourne None si indéterminable, plutôt
    que de deviner (utilisé pour l'étiquette affichée en email et dans la fiche
    Obsidian, pas pour un filtrage qui rejetterait l'offre)."""
    url_lower = (url or "").lower()
    if "linkedin.com" in url_lower:
        return "linkedin"
    if "indeed.com" in url_lower:
        return "indeed"
    return None


def offre_est_a_paris(localisation_texte):
    """Détermine si une offre est située à Paris intra-muros (département 75),
    à partir du même texte de localisation que offre_respecte_zone. Une
    localisation absente ou non identifiable est considérée par défaut comme
    PAS à Paris (usage : masquer l'adresse perso sur le CV envoyé hors Paris —
    en cas de doute, on préfère masquer plutôt que risquer d'exposer l'adresse)."""
    if not localisation_texte:
        return False

    texte = localisation_texte.strip()

    match = re.search(r"^(\d{2})\s*-", texte) or re.search(r"-\s*(\d{2})\b", texte)
    if match:
        return match.group(1) == "75"

    texte_norm = _normaliser_texte(texte)
    if "paris" in texte_norm:
        return True

    premiere_ville = _normaliser_texte(texte.split(",")[0])
    return COMMUNES_IDF_VERS_DEPARTEMENT.get(premiere_ville) == "75"