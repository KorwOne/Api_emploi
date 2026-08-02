from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "jobalerts.db"


def get_db_connection():
    """Retourne une connexion SQLite vers jobalerts.db."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Créer les tables nécessaires si elles n'existent pas encore."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Table des profils
    cur.execute("""
        CREATE TABLE IF NOT EXISTS profil (
            id                          INTEGER PRIMARY KEY,
            nom                         TEXT NOT NULL,
            email                       TEXT NOT NULL,
            salaire_min                 INTEGER,
            mots_inclus                 TEXT,
            mots_exclus                 TEXT,
            niveau                      TEXT,
            domaine                     TEXT,
            moteurs                     TEXT,
            localisation                TEXT,
            codes_rome                  TEXT,
            pays_cibles                 TEXT,
            actif                       INTEGER NOT NULL DEFAULT 1,
            date_derniere_notification  TEXT
        )
    """)

    # Table des offres déjà vues / envoyées
    cur.execute("""
        CREATE TABLE IF NOT EXISTS offre_vue (
            id                      INTEGER PRIMARY KEY,
            profil_id               INTEGER NOT NULL,
            source                  TEXT NOT NULL,
            job_id                  TEXT NOT NULL,
            titre                   TEXT,
            url                     TEXT,
            date_vue                TEXT NOT NULL,
            notification_envoyee    INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (profil_id) REFERENCES profil(id),
            UNIQUE (profil_id, source, job_id)
        )
    """)

    # Migration : ajout des colonnes détail (entreprise/salaire/localisation/date de
    # publication) sur une base déjà existante. SQLite n'a pas de "ADD COLUMN IF NOT
    # EXISTS" : on ignore l'erreur si la colonne existe déjà.
    for colonne in ("entreprise", "salaire", "localisation", "date_publication"):
        try:
            cur.execute(f"ALTER TABLE offre_vue ADD COLUMN {colonne} TEXT")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Base initialisée : {DB_PATH}")