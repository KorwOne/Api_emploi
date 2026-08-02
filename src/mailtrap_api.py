"""Envoi d'emails via l'API HTTP de Mailtrap (Sending API)."""
import requests

MAILTRAP_API_URL = "https://send.api.mailtrap.io/api/send"


def send_email_html_via_mailtrap(token, from_email, from_name, to_email, subject, html_body):
    headers = {
        "Api-Token": token,
        "Content-Type": "application/json",
    }
    payload = {
        "from": {"email": from_email, "name": from_name},
        "to": [{"email": to_email}],
        "subject": subject,
        "html": html_body,
        "category": "Job Alerts",
    }
    response = requests.post(MAILTRAP_API_URL, headers=headers, json=payload, timeout=15)
    print("Status code:", response.status_code)
    print("Response body:", response.text)
    response.raise_for_status()
    return response.json()