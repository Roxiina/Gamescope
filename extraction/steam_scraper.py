"""Source 3 - Web scraping des pages du Steam Store.

Données absentes des API : tags attribués par les joueurs, résumé des avis
récents (30 derniers jours), nombre de langues, prix affiché.

Contraintes respectées :
- robots.txt (https://store.steampowered.com/robots.txt) n'interdit pas /app/
- page de vérification d'âge contournée par les cookies standard du site
- délai entre requêtes pour ne pas surcharger le serveur
"""
import logging
import re

from bs4 import BeautifulSoup

from extraction import config
from extraction.utils import (RateLimiter, append_jsonl, build_session, read_done_ids,
                              throttled_get)

log = logging.getLogger("extraction.scraper")

OUTPUT = config.RAW_DIR / "steam_store_pages.jsonl"

# Cookies qui évitent la page "Veuillez saisir votre date de naissance"
AGE_COOKIES = {"birthtime": "0", "wants_mature_content": "1", "lastagecheckage": "1-0-1990"}

# "81% of the 16,730 user reviews in the last 30 days are positive."
RECENT_RE = re.compile(r"(\d+)% of the ([\d,]+) user reviews in the last 30 days")


def parse_page(appid: int, html: str) -> dict:
    """Parse le HTML d'une page jeu en un dictionnaire de champs utiles."""
    soup = BeautifulSoup(html, "html.parser")

    recent_desc = recent_pct = recent_count = None
    for row in soup.select(".user_reviews_summary_row"):
        tooltip = row.get("data-tooltip-html") or ""
        match = RECENT_RE.search(tooltip)
        if match:
            summary = row.select_one(".game_review_summary")
            recent_desc = summary.get_text(strip=True) if summary else None
            recent_pct = int(match.group(1))
            recent_count = int(match.group(2).replace(",", ""))
            break

    price = soup.select_one(".game_purchase_price, .discount_final_price")
    release = soup.select_one(".release_date .date")
    return {
        "appid": appid,
        "tags": [a.get_text(strip=True) for a in soup.select("a.app_tag")],
        "recent_review_desc": recent_desc,
        "recent_review_pct": recent_pct,
        "recent_review_count": recent_count,
        # Gardés bruts ("49,99€", "18 May, 2015") : normalisés à l'étape C3
        "price_text": price.get_text(strip=True) if price else None,
        "release_date_text": release.get_text(strip=True) if release else None,
        "languages_count": max(len(soup.select("#languageTable tr")) - 1, 0),
    }


def extract(appids: list[int]) -> None:
    session = build_session()
    session.cookies.update(AGE_COOKIES)
    limiter = RateLimiter(config.STEAM_DELAY)
    done = read_done_ids(OUTPUT)
    todo = [a for a in appids if a not in done]
    log.info("Scraping : %d pages à télécharger (%d déjà faites)", len(todo), len(done))

    errors = 0
    for i, appid in enumerate(todo, 1):
        try:
            resp = throttled_get(
                session, limiter, config.STEAM_STORE_PAGE_URL.format(appid=appid), log,
                params={"l": config.STEAM_LANGUAGE, "cc": config.STEAM_COUNTRY},
            )
            # Un jeu retiré redirige vers l'accueil du Store
            if f"/app/{appid}" not in resp.url:
                append_jsonl(OUTPUT, {"appid": appid, "unavailable": True})
                log.warning("Page indisponible (redirection) pour %s", appid)
                continue
            append_jsonl(OUTPUT, parse_page(appid, resp.text))
        except Exception as exc:
            errors += 1
            log.error("Scraping échoué pour %s : %s", appid, exc)

        if i % 50 == 0:
            log.info("Scraping : %d/%d pages", i, len(todo))

    log.info("Scraping terminé : %d erreurs", errors)
