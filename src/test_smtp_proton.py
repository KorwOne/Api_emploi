from pathlib import Path
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

BASE_DIR = Path(__file__).resolve().parent.parent
SMTP_CONFIG_PATH = BASE_DIR / "config" / "smtp_config.json"


def load_smtp_config():
    with SMTP_CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def send_test_email():
    smtp_config = load_smtp_config()

    to_email = "xavier.kervagoret@outlook.fr" #smtp_config["from_email"]  # on s'envoie un mail à soi-même
    subject = "[Job Alerts] Test Proton Mail Bridge"
    body_text = "Ceci est un email de test envoyé depuis le script Python via Proton Mail Bridge."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_config["from_email"]
    msg["To"] = to_email

    part_text = MIMEText(body_text, "plain", _charset="utf-8")
    msg.attach(part_text)

    print(f"Connexion à {smtp_config['host']}:{smtp_config['port']} ...")
    with smtplib.SMTP(smtp_config["host"], smtp_config["port"]) as server:
        if smtp_config.get("use_tls", True):
            print("Démarrage de STARTTLS ...")
            server.starttls()
        print("Authentification ...")
        server.login(smtp_config["user"], smtp_config["password"])
        print("Envoi de l'email de test ...")
        server.sendmail(smtp_config["from_email"], [to_email], msg.as_string())

    print("Email de test envoyé.")


if __name__ == "__main__":
    send_test_email()