"""Configure Uptime Kuma : compte administrateur, sonde /health, page de statut.

Usage (après `docker compose up -d --wait api uptime-kuma`) :
    python scripts/setup_monitoring.py

Idempotent : un élément déjà configuré n'est pas recréé.
Identifiants lus dans .env (UPTIME_KUMA_USER, UPTIME_KUMA_PASSWORD).
Page de statut publique : http://localhost:3001/status/gamescope
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from uptime_kuma_api import MonitorType, UptimeKumaApi

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

KUMA_URL = os.getenv("UPTIME_KUMA_URL", "http://localhost:3001")
MONITOR_NAME = "GameScope API - /health"
# Uptime Kuma tourne dans le réseau Docker : l'API y est joignable par son nom de service
HEALTH_URL = "http://api:8000/health"
SLUG = "gamescope"


def main() -> int:
    user, password = os.environ["UPTIME_KUMA_USER"], os.environ["UPTIME_KUMA_PASSWORD"]
    with UptimeKumaApi(KUMA_URL) as kuma:
        if kuma.need_setup():
            kuma.setup(user, password)
            print(f"Compte administrateur '{user}' créé")
        kuma.login(user, password)

        monitor = next((m for m in kuma.get_monitors() if m["name"] == MONITOR_NAME), None)
        if monitor is None:
            monitor_id = kuma.add_monitor(
                type=MonitorType.HTTP, name=MONITOR_NAME, url=HEALTH_URL,
                interval=60,          # une vérification par minute
                maxretries=2,         # alerte après 2 échecs consécutifs (évite les fausses alertes)
                accepted_statuscodes=["200-299"],  # /health renvoie 503 si la base est injoignable
            )["monitorID"]
            print(f"Sonde '{MONITOR_NAME}' créée")
        else:
            monitor_id = monitor["id"]

        if not any(p["slug"] == SLUG for p in kuma.get_status_pages()):
            kuma.add_status_page(SLUG, "GameScope")
        kuma.save_status_page(
            SLUG, title="GameScope", description="Disponibilité de l'API GameScope et de sa base",
            publicGroupList=[{"name": "API REST", "monitorList": [{"id": monitor_id}]}],
        )
    print(f"Page de statut : {KUMA_URL}/status/{SLUG}")
    print("Alertes : à brancher dans Settings > Notifications (e-mail, Discord...)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
