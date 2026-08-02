import json
from pathlib import Path
from mailtrap_api import send_email_html_via_mailtrap

BASE_DIR = Path(__file__).resolve().parent.parent
MAILTRAP_CONFIG_PATH = BASE_DIR / "config" / "mailtrap_config.json"

with MAILTRAP_CONFIG_PATH.open("r", encoding="utf-8") as f:
    config = json.load(f)

result = send_email_html_via_mailtrap(
    token=config["token"],
    from_email=config["from_email"],
    from_name=config["from_name"],
    to_email="xavier.kervagoret@outlook.fr",
    subject="Test Mailtrap - Job Alerts",
    html_body="<h1>Ça fonctionne !</h1><p>Ceci est un test d'envoi via Mailtrap.</p>",
)

print("Réponse Mailtrap :", result)