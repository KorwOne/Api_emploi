import time
from jobspy import scrape_jobs

termes = ["DSI", "CTO", "Directeur informatique", "Responsable infrastructure"]

resultats = {}
toutes_offres = []

for terme in termes:
    print(f"DEBUG >>> site_name=['linkedin'] search_term='{terme}'")
    try:
        df = scrape_jobs(
            site_name=["linkedin"],
            search_term=terme,
            location="France",
            results_wanted=15,
            hours_old=48,
        )
        print(f"DEBUG >>> '{terme}' -> {len(df)} ligne(s) brutes")
        resultats[terme] = len(df)

        if not df.empty:
            toutes_offres.append(df)

    except Exception as e:
        print(f"DEBUG >>> '{terme}' -> ERREUR : {type(e).__name__} — {e}")
        resultats[terme] = f"ERREUR: {e}"

    time.sleep(35)

if toutes_offres:
    import pandas as pd
    df_final = pd.concat(toutes_offres, ignore_index=True)
    df_final = df_final.drop_duplicates(subset=["job_url"])
    print(f"{len(df_final)} offre(s) trouvée(s) au total après dédup.")
    print("-" * 60)
    for _, row in df_final.iterrows():
        salaire = row.get("min_amount")
        salaire_str = f"{salaire:.0f}€" if pd.notna(salaire) else "N/A"
        print(f"{row['title']} | {row['company']} | {row['location']} | salaire min: {salaire_str}")
        print("-" * 60)
else:
    print("0 offre(s) trouvée(s) au total.")

print(resultats)