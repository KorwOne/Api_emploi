from pathlib import Path
from db_init import init_db, get_db_connection
from datetime import datetime, timezone
from html import escape as escape_html
from scrapers.jobup_scraper import scraper_offres
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from mailtrap_api import send_email_html_via_mailtrap
from scraper_france_travail import scraper_france_travail
from scraper_apec import scraper_apec
from scraper_jobspy import scraper_jobspy
from collecte_offres import collecter_offres_pour_profil
from filtre_ollama import filtrer_offres_avec_ollama
from filtres import offre_respecte_zone

import smtplib
import sqlite3
import json

# Dossier racine du projet : D:\Work\Python\Api_Emploi
BASE_DIR = Path(__file__).resolve().parent.parent
EMAIL_TEMPLATE_PATH = BASE_DIR / "templates" / "email_template.html"
SMTP_CONFIG_PATH = BASE_DIR / "config" / "smtp_config.json"

CONFIG_DIR = BASE_DIR / "config"
CONFIG_PATH = CONFIG_DIR / "config_profils.json"
MAILTRAP_CONFIG_PATH = CONFIG_DIR / "mailtrap_config.json"

JOBSPY_ACTIF = True


def load_profils():
    """Lire le fichier config_profils.json et retourner la liste des profils."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Fichier de configuration introuvable : {CONFIG_PATH}")

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    profils = data.get("profils", [])
    return profils

def load_mailtrap_config():
    with MAILTRAP_CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)
    
def filtrer_par_salaire(offres, salaire_min):
    if not salaire_min:
        return offres

    offres_filtrees = []
    for off in offres:
        salaire_offre = off.get("salaire_min")

        # Si le salaire est inconnu, on laisse passer l'offre
        if salaire_offre is None:
            offres_filtrees.append(off)
            continue

        if salaire_offre >= salaire_min:
            offres_filtrees.append(off)

    return offres_filtrees

def filtrer_par_zone(offres, zones_autorisees):
    if not zones_autorisees:
        return offres
    return [off for off in offres if offre_respecte_zone(off.get("localisation"), zones_autorisees)]

def charger_zones_autorisees(profil_dict):
    valeur = profil_dict.get("zones_autorisees")
    if isinstance(valeur, str):
        return json.loads(valeur) if valeur else {}
    return valeur or {}

def sync_profils_with_db():
    profils = load_profils()
    conn = get_db_connection()
    cur = conn.cursor()

    for p in profils:
        profil_id = p["profil_id"]
        nom = p["nom"]
        email = p["email"]
        actif = 1 if p.get("actif", True) else 0
        salaire_min = p.get("salaire_min")
        mots_inclus = json.dumps(p.get("mots_inclus", []), ensure_ascii=False)
        mots_exclus = json.dumps(p.get("mots_exclus", []), ensure_ascii=False)
        niveau = json.dumps(p.get("niveau", []), ensure_ascii=False)
        domaine = json.dumps(p.get("domaine", []), ensure_ascii=False)
        moteurs = json.dumps(p.get("moteurs", []), ensure_ascii=False)
        localisation = json.dumps(p.get("localisation", {}), ensure_ascii=False)
        codes_rome = json.dumps(p.get("codes_rome", []), ensure_ascii=False)
        pays_cibles = json.dumps(p.get("pays_cibles", ["FR"]), ensure_ascii=False)
        zones_autorisees = json.dumps(p.get("zones_autorisees", {}), ensure_ascii=False)
        apec_lieux = json.dumps(p.get("apec_lieux", []), ensure_ascii=False)

        cur.execute(
            """
            INSERT INTO profil (
                id, nom, email, salaire_min, mots_inclus, mots_exclus,
                niveau, domaine, moteurs, localisation, codes_rome, pays_cibles,
                zones_autorisees, apec_lieux, actif
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                nom=excluded.nom,
                email=excluded.email,
                salaire_min=excluded.salaire_min,
                mots_inclus=excluded.mots_inclus,
                mots_exclus=excluded.mots_exclus,
                niveau=excluded.niveau,
                domaine=excluded.domaine,
                moteurs=excluded.moteurs,
                localisation=excluded.localisation,
                codes_rome=excluded.codes_rome,
                pays_cibles=excluded.pays_cibles,
                zones_autorisees=excluded.zones_autorisees,
                apec_lieux=excluded.apec_lieux,
                actif=excluded.actif
            """,
            (
                profil_id, nom, email, salaire_min, mots_inclus, mots_exclus,
                niveau, domaine, moteurs, localisation, codes_rome, pays_cibles,
                zones_autorisees, apec_lieux, actif
            ),
        )

    conn.commit()
    conn.close()
    
def load_smtp_config():
    with SMTP_CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def send_email_html(smtp_config, to_email, subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_config["from_email"]
    msg["To"] = to_email

    part_html = MIMEText(html_body, "html", _charset="utf-8")
    msg.attach(part_html)

    with smtplib.SMTP(smtp_config["host"], smtp_config["port"]) as server:
        if smtp_config.get("use_tls", True):
            server.starttls()
        server.login(smtp_config["user"], smtp_config["password"])
        server.sendmail(smtp_config["from_email"], [to_email], msg.as_string())
        
def load_email_template():
    with EMAIL_TEMPLATE_PATH.open("r", encoding="utf-8") as f:
        return f.read()


SOURCES_META = {
    "jobup.ch": {"label": "JobUp.ch", "color": "#0b5ed7", "emoji": "🇨🇭"},
    "france_travail": {"label": "France Travail", "color": "#000091", "emoji": "🇫🇷"},
    "apec": {"label": "Apec", "color": "#7c3aed", "emoji": "🎓"},
    "indeed_jobspy": {"label": "Indeed", "color": "#2557a7", "emoji": "🔎"},
    "moteur_fictif": {"label": "Test", "color": "#6b7280", "emoji": "🧪"},
}


def _formater_date_vue(date_vue):
    try:
        return datetime.fromisoformat(date_vue).strftime("%d/%m à %H:%M")
    except (TypeError, ValueError):
        return date_vue or ""


def _formater_date_publication(date_publication):
    """Les sources renvoient des formats hétérogènes : ISO (APEC/France Travail),
    texte libre (jobup, ex: "Il y a 2 semaines"), ou une date brute (jobspy).
    On tente un parsing ISO, sinon on affiche tel quel."""
    if not date_publication:
        return ""
    try:
        return datetime.fromisoformat(date_publication.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except (ValueError, TypeError, AttributeError):
        return date_publication


def render_email_html(template, nom_profil, offres_rows):
    date_generation = datetime.now().strftime("%d/%m/%Y à %H:%M")
    nb_offres = len(offres_rows)

    groupes = {}
    for row in offres_rows:
        groupes.setdefault(row["source"], []).append(row)

    sections_html = []
    for source, rows in groupes.items():
        meta = SOURCES_META.get(source, {"label": source, "color": "#374151", "emoji": "📌"})

        items_html = []
        for row in rows:
            titre = escape_html(row["titre"] or "(Titre non renseigné)")
            url = row["url"] or "#"
            date_vue = _formater_date_vue(row["date_vue"])

            entreprise = escape_html(row["entreprise"]) if row["entreprise"] else ""
            localisation = escape_html(row["localisation"]) if row["localisation"] else ""
            salaire = escape_html(row["salaire"]) if row["salaire"] else ""
            date_pub = escape_html(_formater_date_publication(row["date_publication"]))

            details = []
            if entreprise:
                details.append(f"🏢 {entreprise}")
            if localisation:
                details.append(f"📍 {localisation}")
            if salaire:
                details.append(f"💰 {salaire}")
            if date_pub:
                details.append(f"📅 Publié {date_pub}")
            ligne_details = (
                f'<p style="margin:0 0 6px; font-size:12px; color:#374151 !important;">{" &nbsp;·&nbsp; ".join(details)}</p>'
                if details else ""
            )

            items_html.append(f"""
            <div style="background-color:#ffffff; border:1px solid #e5e7eb; border-radius:6px; padding:12px 14px; margin-top:8px;">
                <p style="margin:0 0 4px; font-size:14px; font-weight:600; color:#111827 !important;">{titre}</p>
                {ligne_details}
                <p style="margin:0 0 8px; font-size:11px; color:#9ca3af !important;">Vu le {date_vue}</p>
                <a class="job-link" href="{url}" target="_blank" rel="noopener noreferrer" style="display:inline-block; font-size:13px; font-weight:600; color:#ffffff !important; background-color:#2563eb; text-decoration:none; padding:6px 12px; border-radius:5px;">Voir l'offre →</a>
            </div>
            """)

        sections_html.append(f"""
        <div style="border-left:4px solid {meta['color']}; background-color:#f9fafb; border-radius:6px; margin-top:18px; padding:14px 16px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                    <td align="left">
                        <span style="display:inline-block; color:#ffffff !important; background-color:{meta['color']}; font-size:12px; font-weight:600; padding:3px 10px; border-radius:999px;">{meta['emoji']} {meta['label']}</span>
                    </td>
                    <td align="right" style="font-size:12px; color:#6b7280 !important;">{len(rows)} offre(s)</td>
                </tr>
            </table>
            {''.join(items_html)}
        </div>
        """)

    liste_offres_html = "\n".join(sections_html)

    html = (
        template.replace("{{ nom_profil }}", nom_profil)
        .replace("{{ nb_offres }}", str(nb_offres))
        .replace("{{ date_generation }}", date_generation)
        .replace("{{ liste_offres_html }}", liste_offres_html)
    )
    return html

def enregistrer_offre_si_nouvelle(conn, profil_id, source, job_id, titre, url,
                                   entreprise=None, salaire=None, localisation=None,
                                   date_publication=None):
    """
    Enregistrer une offre en base si elle n'existe pas encore pour ce profil.
    Retourne True si l'offre est nouvelle, False sinon.
    """
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    try:
        cur.execute(
            """
            INSERT INTO offre_vue (
                profil_id, source, job_id, titre, url, date_vue, notification_envoyee,
                entreprise, salaire, localisation, date_publication
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
            """,
            (profil_id, source, job_id, titre, url, now,
             entreprise, salaire, localisation, date_publication),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # L'offre existe déjà (contrainte UNIQUE (profil_id, source, job_id))
        return False

def get_offres_non_notifiees(conn, profil_id):
    """Récupérer les offres d'un profil qui n'ont pas encore été incluses dans un mail."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, source, job_id, titre, url, date_vue,
               entreprise, salaire, localisation, date_publication
        FROM offre_vue
        WHERE profil_id = ? AND notification_envoyee = 0
        ORDER BY date_vue ASC
        """,
        (profil_id,),
    )
    return cur.fetchall()


def marquer_offres_notifiees(conn, offre_ids):
    """Marquer une liste d'offres comme déjà notifiées."""
    if not offre_ids:
        return
    cur = conn.cursor()
    cur.executemany(
        "UPDATE offre_vue SET notification_envoyee = 1 WHERE id = ?",
        [(oid,) for oid in offre_ids],
    )
    conn.commit()


def moteur_fictif_pour_profil(conn, profil_row):
    """
    Génère quelques offres factices pour un profil donné.
    - profil_row est une ligne issue de la table profil (sqlite3.Row)
    - Les offres sont marquées comme provenant de 'moteur_fictif'
    """
    profil_id = profil_row["id"]
    nom_profil = profil_row["nom"]

    # On génère 3 offres de test
    offres_fictives = [
        {
            "job_id": f"{profil_id}-TEST-1",
            "titre": f"{nom_profil} – Poste de test 1",
            "url": f"https://exemple.local/offre/{profil_id}-TEST-1"
        },
        {
            "job_id": f"{profil_id}-TEST-2",
            "titre": f"{nom_profil} – Poste de test 2",
            "url": f"https://exemple.local/offre/{profil_id}-TEST-2"
        },
        {
            "job_id": f"{profil_id}-TEST-3",
            "titre": f"{nom_profil} – Poste de test 3",
            "url": f"https://exemple.local/offre/{profil_id}-TEST-3"
        }
    ]

    nb_nouvelles = 0
    for off in offres_fictives:
        ok = enregistrer_offre_si_nouvelle(
            conn=conn,
            profil_id=profil_id,
            source="moteur_fictif",
            job_id=off["job_id"],
            titre=off["titre"],
            url=off["url"],
        )
        if ok:
            nb_nouvelles += 1

    print(f"[moteur_fictif] Profil {profil_id} ({nom_profil}) : {nb_nouvelles} nouvelle(s) offre(s) ajoutée(s).")

def moteur_jobup_pour_profil(conn, profil_row):
    profil_id = profil_row["id"]
    nom_profil = profil_row["nom"]

    offres = scraper_offres(profil_row)

    nb_nouvelles = 0
    for off in offres:
        ok = enregistrer_offre_si_nouvelle(
            conn=conn,
            profil_id=profil_id,
            source="jobup.ch",
            job_id=off["job_id"],
            titre=off["titre"],
            url=off["url"],
            entreprise=off.get("entreprise"),
            localisation=off.get("localisation"),
            date_publication=off.get("date_publication"),
        )
        if ok:
            nb_nouvelles += 1

    print(f"[jobup] Profil {profil_id} ({nom_profil}) : {nb_nouvelles} nouvelle(s) offre(s) ajoutée(s).")
    
def afficher_profils(profils):
    """Afficher les profils de manière lisible dans le terminal."""
    if not profils:
        print("Aucun profil trouvé dans la configuration.")
        return

    print(f"{len(profils)} profil(s) chargé(s) :")
    print("-" * 40)

    for p in profils:
        print(f"profil_id : {p.get('profil_id')}")
        print(f"nom       : {p.get('nom')}")
        print(f"email     : {p.get('email')}")
        print(f"salaire_min : {p.get('salaire_min')}")
        print(f"moteurs   : {', '.join(p.get('moteurs', []))}")
        print("mots_inclus :")
        for mot in p.get("mots_inclus", []):
            print(f"  - {mot}")
        print("mots_exclus :")
        for mot in p.get("mots_exclus", []):
            print(f"  - {mot}")
        print("-" * 40)

def moteur_jobspy_pour_profil(conn, profil_row):
    profil_id = profil_row["id"]
    nom_profil = profil_row["nom"]

    profil_dict = dict(profil_row)

    for champ in ("mots_inclus", "mots_exclus", "niveau", "domaine", "pays_cibles"):
        valeur = profil_dict.get(champ)
        if isinstance(valeur, str):
            profil_dict[champ] = json.loads(valeur) if valeur else []
        elif valeur is None:
            profil_dict[champ] = []

    if "FR" not in profil_dict.get("pays_cibles", ["FR"]):
        print(f"[jobspy] Profil {profil_id} ({nom_profil}) ignoré (pas de cible FR).")
        return

    offres = scraper_jobspy(profil_dict)
    offres = filtrer_par_salaire(offres, profil_dict.get("salaire_min"))

    zones_autorisees = charger_zones_autorisees(profil_dict)
    offres = filtrer_par_zone(offres, zones_autorisees)

    if not offres:
        print(f"[jobspy] Profil {profil_id} ({nom_profil}) : aucune offre après filtre salaire/zone.")
        return

    # Tagger la source pour Ollama / logs
    for off in offres:
        off["source"] = "indeed_jobspy"

    # Filtre sémantique Ollama
    offres = filtrer_offres_avec_ollama(offres, profil_dict)

    if not offres:
        print(f"[jobspy] Profil {profil_id} ({nom_profil}) : aucune offre après filtre Ollama.")
        return

    nb_nouvelles = 0
    for off in offres:
        print("[JOBSPY]", off["titre"], off.get("salaire_min"), "profil seuil =", profil_dict.get("salaire_min"))
        ok = enregistrer_offre_si_nouvelle(
            conn=conn,
            profil_id=profil_id,
            source=off.get("source", "indeed_jobspy"),
            job_id=off["job_id"],
            titre=off["titre"],
            url=off["url"],
            entreprise=off.get("entreprise"),
            salaire=off.get("salaire"),
            localisation=off.get("localisation"),
            date_publication=off.get("date_publication"),
        )
        if ok:
            nb_nouvelles += 1

    print(f"[jobspy] Profil {profil_id} ({nom_profil}) : {nb_nouvelles} nouvelle(s) offre(s) ajoutée(s).")
        
def main():
    # 1. S'assurer que la base et les tables existent
    init_db()
    sync_profils_with_db()

    smtp_config = load_smtp_config()
    mailtrap_config = load_mailtrap_config()
    template = load_email_template()

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM profil WHERE actif = 1 ORDER BY id")
    profils_rows = cur.fetchall()

    # 2. jobup / moteur fictif
    for profil_row in profils_rows:
        if profil_row["nom"] == "DSI":
            moteur_jobup_pour_profil(conn, profil_row)
        else:
            moteur_fictif_pour_profil(conn, profil_row)

    # 2b. Indeed via JobSpy
    if JOBSPY_ACTIF:
        for profil_row in profils_rows:
            try:
                moteur_jobspy_pour_profil(conn, profil_row)
            except Exception as e:
                print(f"[jobspy] Profil {profil_row['id']} ({profil_row['nom']}) : ERREUR — {e}")
    else:
        print("[jobspy] Désactivé (JOBSPY_ACTIF = False) — étape ignorée.")
            
    # 3. France Travail
    for profil_row in profils_rows:
        profil_dict = dict(profil_row)
        profil_id = profil_dict["id"]

        # Localisation / codes ROME / pays cibles
        profil_dict["localisation"] = json.loads(profil_dict["localisation"]) if isinstance(profil_dict.get("localisation"), str) else profil_dict.get("localisation", {})
        profil_dict["codes_rome"] = json.loads(profil_dict["codes_rome"]) if isinstance(profil_dict.get("codes_rome"), str) else profil_dict.get("codes_rome", [])
        profil_dict["pays_cibles"] = json.loads(profil_dict["pays_cibles"]) if isinstance(profil_dict.get("pays_cibles"), str) else profil_dict.get("pays_cibles", ["FR"])

        if "FR" not in profil_dict["pays_cibles"]:
            print(f"[france_travail] Profil {profil_id} ({profil_dict['nom']}) ignoré (pas de cible FR).")
            continue

        # Mots inclus / exclus depuis le profil
        profil_dict["mots_inclus"] = json.loads(profil_dict["mots_inclus"]) if isinstance(profil_dict.get("mots_inclus"), str) else profil_dict.get("mots_inclus", [])
        profil_dict["mots_exclus"] = json.loads(profil_dict["mots_exclus"]) if isinstance(profil_dict.get("mots_exclus"), str) else profil_dict.get("mots_exclus", [])

        # 3.1 Scraper France Travail + filtrage salaire/zone
        offres = scraper_france_travail(profil_dict)
        offres = filtrer_par_salaire(offres, profil_dict.get("salaire_min"))
        offres = filtrer_par_zone(offres, charger_zones_autorisees(profil_dict))

        # 3.2 Tagger la source pour Ollama
        for off in offres:
            off["source"] = "france_travail"

        # 3.3 Filtre sémantique Ollama avec les mots_inclus/exclus du profil
        offres = filtrer_offres_avec_ollama(offres, profil_dict)

        # 3.4 Enregistrement en base
        nb_nouvelles = 0
        for off in offres:
            print("[FRANCE_TRAVAIL]", off["titre"], off.get("salaire_min"), "profil seuil =", profil_dict.get("salaire_min"))

            ok = enregistrer_offre_si_nouvelle(
                conn=conn,
                profil_id=profil_id,
                source="france_travail",
                job_id=off["job_id"],
                titre=off["titre"],
                url=off["url"],
                entreprise=off.get("entreprise"),
                salaire=off.get("salaire"),
                localisation=off.get("localisation"),
                date_publication=off.get("date_publication"),
            )
            if ok:
                nb_nouvelles += 1

        print(f"[france_travail] Profil {profil_id} ({profil_dict['nom']}) : {nb_nouvelles} nouvelle(s) offre(s) ajoutée(s).")
                
     # 3b. APEC pour chaque profil
    for profil_row in profils_rows:
        profil_dict = dict(profil_row)
        profil_id = profil_dict["id"]

        # Reconstruction des listes à partir du JSON texte
        for champ in ("mots_inclus", "mots_exclus", "apec_lieux"):
            valeur = profil_dict.get(champ)
            if isinstance(valeur, str):
                profil_dict[champ] = json.loads(valeur) if valeur else []
            elif valeur is None:
                profil_dict[champ] = []

        try:
            offres = scraper_apec(profil_dict)
            offres = filtrer_par_salaire(offres, profil_dict.get("salaire_min"))
            offres = filtrer_par_zone(offres, charger_zones_autorisees(profil_dict))

            # Tagger la source pour Ollama
            for off in offres:
                off["source"] = "apec"

            # Filtre sémantique Ollama avec les mots_inclus/exclus du profil
            offres = filtrer_offres_avec_ollama(offres, profil_dict)

            nb_nouvelles = 0
            for off in offres:
                print("[APEC]", off["titre"], off.get("salaire_min"), "profil seuil =", profil_dict.get("salaire_min"))

                ok = enregistrer_offre_si_nouvelle(
                    conn=conn,
                    profil_id=profil_id,
                    source="apec",
                    job_id=off["job_id"],
                    titre=off["titre"],
                    url=off["url"],
                    entreprise=off.get("entreprise"),
                    salaire=off.get("salaire"),
                    localisation=off.get("localisation"),
                    date_publication=off.get("date_publication"),
                )
                if ok:
                    nb_nouvelles += 1

            print(f"[apec] Profil {profil_id} ({profil_dict['nom']}) : {nb_nouvelles} nouvelle(s) offre(s) ajoutée(s).")
        except Exception as e:
            print(f"[apec] Profil {profil_id} ({profil_dict['nom']}) : ERREUR — {e}")
                                    
    # 4. Envoi du digest email par profil
    for profil_row in profils_rows:
        profil_id = profil_row["id"]
        nom_profil = profil_row["nom"]
        email = profil_row["email"]

        offres_non_notifiees = get_offres_non_notifiees(conn, profil_id)

        if not offres_non_notifiees:
            print(f"[digest] Profil {profil_id} ({nom_profil}) : aucune nouvelle offre à notifier.")
            continue

        html_body = render_email_html(template, nom_profil, offres_non_notifiees)
        subject = f"[Job Alerts] {len(offres_non_notifiees)} nouvelle(s) offre(s) pour {nom_profil}"

        try:
            send_email_html(smtp_config, email, subject, html_body)
            offre_ids = [row["id"] for row in offres_non_notifiees]
            marquer_offres_notifiees(conn, offre_ids)
            print(f"[digest] Profil {profil_id} ({nom_profil}) : {len(offres_non_notifiees)} offre(s) envoyée(s) par email à {email}.")
        except Exception as e:
            print(f"[digest] Profil {profil_id} ({nom_profil}) : ERREUR lors de l'envoi — {e}")

    conn.close()


if __name__ == "__main__":
    main()