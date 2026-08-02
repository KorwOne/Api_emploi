from jobspy import scrape_jobs


def scraper_jobspy(search_terms, location="France", hours_old=48, results_wanted=15):
    if isinstance(search_terms, str):
        search_terms = [search_terms]

    offres = []
    urls_vues = set()

    for terme in search_terms:
        print(f"DEBUG >>> site_name=['indeed'] search_term={terme!r}")

        jobs_df = scrape_jobs(
            site_name=["indeed"],
            search_term=terme,
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
            country_indeed="France",
        )

        print(f"DEBUG >>> {terme!r} -> {len(jobs_df)} ligne(s)")

        for _, row in jobs_df.iterrows():
            url = row.get("job_url", "")
            if not url or url in urls_vues:
                continue
            urls_vues.add(url)

            salaire_texte = ""
            if row.get("min_amount") or row.get("max_amount"):
                salaire_texte = f"{row.get('min_amount', '')} - {row.get('max_amount', '')} {row.get('currency', '')}"

            offres.append(
                {
                    "source": f"jobspy_{row.get('site', 'inconnu')}",
                    "job_id": url,
                    "url": url,
                    "titre": row.get("title", "") or "",
                    "entreprise": row.get("company", "") or "",
                    "lieu": row.get("location", "") or "",
                    "contrat": row.get("job_type", "") or "",
                    "salaire_texte": salaire_texte,
                    "date_publication": str(row.get("date_posted", "")) or None,
                }
            )

    return offres