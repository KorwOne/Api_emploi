"""
Scraper jobup.ch pour le projet Api_Emploi - VERSION DEBUG
"""
from playwright.sync_api import sync_playwright
import json
from urllib.parse import quote


def _construire_url(mot_cle, region_code=None, page=1):
    base = "https://www.jobup.ch/fr/emplois/"
    params = f"?term={quote(mot_cle)}"
    if region_code:
        params += f"&region={region_code}"
    if page > 1:
        params += f"&page={page}"
    return base + params


def debug_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        url = _construire_url("Directeur Infrastructure", 24)
        print(f"Chargement : {url}")
        page.goto(url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        tous_liens = page.query_selector_all("a")
        print(f"Nombre total de liens <a> sur la page : {len(tous_liens)}")

        selecteurs = [
            "a[href*='/fr/emplois/detail/']",
            "a[href*='/fr/vacancies/detail/']",
            "a[href*='detail']",
            "[class*='JobLink']",
            "[class*='job-link']",
            "article a",
            "[data-testid*='job']",
        ]
        for sel in selecteurs:
            elements = page.query_selector_all(sel)
            print(f"Selecteur '{sel}' -> {len(elements)} elements")

        hrefs_pertinents = set()
        for lien in tous_liens:
            href = lien.get_attribute("href")
            if href and ("emploi" in href.lower() or "job" in href.lower() or "vacanc" in href.lower()):
                hrefs_pertinents.add(href)
        print(f"\nHrefs contenant emploi/job/vacancy ({len(hrefs_pertinents)} uniques) :")
        for h in list(hrefs_pertinents)[:20]:
            print(" ", h)

        html = page.content()
        with open("debug_jobup.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("\nHTML sauvegarde dans debug_jobup.html")

        browser.close()


if __name__ == "__main__":
    debug_page()