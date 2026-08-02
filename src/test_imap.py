import os
from pathlib import Path

from dotenv import load_dotenv
from imap_tools import MailBox, AND
from bs4 import BeautifulSoup
from scrapers.parser_hellowork import parser_offres_hellowork

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

host = os.environ["GMAIL_IMAP_HOST"]
port = int(os.environ.get("GMAIL_IMAP_PORT", "993"))
email_addr = os.environ["GMAIL_ADDRESS"]
password = os.environ["GMAIL_APP_PASSWORD"]
folder = os.environ.get("GMAIL_IMAP_FOLDER", "Veille emploi")

with MailBox(host, port=port).login(email_addr, password) as mailbox:
    dossiers = [item.name for item in mailbox.folder.list()]
    print("Dossiers IMAP disponibles :")
    for dossier in dossiers:
        print(f" - {dossier}")

    if folder not in dossiers:
        raise RuntimeError(
            f"\nLibellé introuvable : {folder!r}\n"
            "Crée-le dans Gmail, ou reporte son nom IMAP exact dans .env."
        )

    mailbox.folder.set(folder)
    messages = list(mailbox.fetch(AND(all=True), limit=20, reverse=True,
        mark_seen=False))

    print(f"\nEmails trouvés dans « {folder} » : {len(messages)}")
    for msg in messages:
        print("-" * 60)
        offres = parser_offres_hellowork(msg.html)

        print("\n--- OFFRES HELLOWORK EXTRAITES ---")
        for offre in offres:
            print(offre["url"])
        print(f"Total : {len(offres)}")
        
        print(f"UID       : {msg.uid}")
        print(f"Date      : {msg.date}")
        print(f"Expéditeur: {msg.from_}")
        print(f"Sujet     : {msg.subject}")
        print(f"Lu        : {'\\Seen' in msg.flags}")
        soup = BeautifulSoup(msg.html or "", "html.parser")

        print("\n--- TEXTE NETTOYÉ ---")
        texte = soup.get_text(" ", strip=True)
        print(texte[:5000])

        print("\n--- LIENS TROUVÉS ---")
        for lien in soup.find_all("a", href=True):
            libelle = lien.get_text(" ", strip=True)
            url = lien["href"]
            print(f"TEXTE : {libelle}")
            print(f"URL   : {url}")
            print("-" * 60)

        offres = parser_offres_hellowork(msg.html)

        print("\n--- DIAGNOSTIC PREMIER LIEN D'OFFRE ---")

        premier_lien = None
        for lien in soup.find_all("a", href=True):
            libelle = " ".join(lien.get_text(" ", strip=True).split())
            if libelle.lower() == "voir l’offre":
                premier_lien = lien
                break

        if premier_lien:
            for niveau in range(1, 9):
                parent = premier_lien
                for _ in range(niveau):
                    parent = parent.parent

                if parent is None:
                    break

                texte_parent = " ".join(parent.get_text(" ", strip=True).split())
                print(f"\nNIVEAU {niveau}")
                print(f"TEXTE : {texte_parent[:1200]}")
                print(f"BALISE : {parent.name}")
                print(f"CLASSES : {parent.get('class')}")
                
                offres = parser_offres_hellowork(msg.html)

        print("\n--- OFFRES HELLOWORK EXTRAITES ---")
        for offre in offres:
            print("-" * 60)
            print(f"Titre      : {offre['titre']}")
            print(f"Entreprise : {offre['entreprise']}")
            print(f"Lieu       : {offre['lieu']}")
            print(f"Contrat    : {offre['contrat']}")
            print(f"Salaire    : {offre['salaire_texte']}")
            print(f"URL        : {offre['url']}")
        print(f"Total : {len(offres)}")