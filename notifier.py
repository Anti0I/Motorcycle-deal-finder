import logging
import requests
from config import WEBHOOK_URL


def send_discord_notification(title, price, year, url, image_url, deal_type="NORMAL DEAL", analysis=""):
    """Wysyła powiadomienie na Discord przez webhook."""
    if not WEBHOOK_URL or WEBHOOK_URL == "TWÓJ_WEBHOOK_DISCORD":
        return

    colors = {
        "GREAT DEAL": 0x2ECC71,
        "BARGAIN": 0xBF40BF
    }

    display_title = f"[{deal_type}] {title} ({year})"[:256]

    embed = {
        "title": display_title,
        "color": colors.get(deal_type, 0x2ECC71),
        "description": f"**Cena:** {price}\n**Rocznik:** {year}\n\n**Analiza pod profit:**\n{analysis}"[:4096]
    }

    if url and str(url).startswith('http'):
        embed["url"] = url
    if image_url and str(image_url).startswith('http'):
        embed["thumbnail"] = {"url": image_url}

    data = {
        "username": "Monitor AI - OKAZJE",
        "embeds": [embed]
    }
    try:
        requests.post(WEBHOOK_URL, json=data)
    except Exception as e:
        logging.error(f"Błąd Discord: {e}")
