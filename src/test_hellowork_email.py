from scrapers.scraper_hellowork_email import scraper_hellowork_email


offres = scraper_hellowork_email()

print(f"{len(offres)} offre(s) HelloWork extraite(s).")

for offre in offres:
    print("-" * 60)
    print(f"Titre      : {offre['titre']}")
    print(f"Entreprise : {offre['entreprise']}")
    print(f"Lieu       : {offre['lieu']}")
    print(f"Contrat    : {offre['contrat']}")
    print(f"Salaire    : {offre['salaire_texte']}")
    print(f"URL        : {offre['url']}")