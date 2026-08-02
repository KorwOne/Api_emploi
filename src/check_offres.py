import sqlite3
conn = sqlite3.connect('../data/job_alerts.db')
cur = conn.cursor()
cur.execute("SELECT profil_id, source, titre, notification_envoyee FROM offre_vue WHERE source='france_travail'")
for row in cur.fetchall():
    print(row)