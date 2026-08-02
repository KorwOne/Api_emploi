import os
from pathlib import Path

from dotenv import load_dotenv
from imap_tools import AND, MailBox

from scrapers.parser_hellowork import parser_offres_hellowork


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env"

EXPEDITEUR_HELLOWORK = "notification@emails.hellowork.com"


def scraper_hellowork_email():
    load_dotenv(ENV_PATH)

    host = os.environ["GMAIL_IMAP_HOST"]
    port = int(os.environ.get("GMAIL_IMAP_PORT", "993"))
    email_addr = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    folder = os.environ.get("GMAIL_IMAP_FOLDER", "Veille emploi")

    offres = []

    with MailBox(host, port=port).login(email_addr, password) as mailbox:
        mailbox.folder.set(folder)

        messages = mailbox.fetch(
            AND(from_=EXPEDITEUR_HELLOWORK),
            mark_seen=False,
            reverse=True,
        )

        for msg in messages:
            offres.extend(parser_offres_hellowork(msg.html))

    return offres