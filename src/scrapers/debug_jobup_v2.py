"""Debug v2 - afficher les vrais liens detail et la structure autour"""
from playwright.sync_api import sync_playwright
from urllib.parse import quote


def debug_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        url = f"https://www.jobup.ch/fr/emplois/?term={quote('Directeur Infrastructure')}&region=24"
        print(f"Chargement : {url}")
        page.goto(url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        liens_detail = page.query_selector_all("a[href*='detail']")
        print(f"\n--- {len(liens_detail)} liens 'detail' trouves ---")
        for lien in liens_detail:
            href = lien.get_attribute("href")
            texte = lien.inner_text().strip()
            print(f"HREF: {href}")
            print(f"TEXTE: {repr(texte)}")
            print("---")

        print("\n--- Recherche de conteneurs de resultats ---")
        for sel in ["[class*='result']", "[class*='Result']", "[class*='card']", "[class*='Card']",
                    "[class*='listing']", "[class*='Listing']", "[data-cy]", "[data-test]", "li"]:
            els = page.query_selector_all(sel)
            print(f"{sel} -> {len(els)}")

        body_text = page.inner_text("body")
        if "aucun" in body_text.lower() or "no result" in body_text.lower():
            print("\n[ATTENTION] Possible message 'aucun resultat' detecte sur la page")

        print(f"\nOccurrences de 'infrastructure' dans le texte : {body_text.lower().count('infrastructure')}")
        print(f"Occurrences de 'directeur' dans le texte : {body_text.lower().count('directeur')}")

        browser.close()


if __name__ == "__main__":
    debug_page()