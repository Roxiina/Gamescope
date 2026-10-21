"""Source 1 - API REST SteamSpy : liste des jeux les plus possédés sur Steam.

Doc : https://steamspy.com/api.php
`request=all&page=N` renvoie 1000 jeux par page, triés par nombre de
propriétaires. Limite : 1 appel par minute pour cette requête.
"""
import json
import logging

from extraction import config
from extraction.utils import RateLimiter, build_session

log = logging.getLogger("extraction.steamspy")

OUTPUT = config.RAW_DIR / "steamspy_games.json"

# Champs utiles conservés (filtrage dès l'extraction)
FIELDS = (
    "appid", "name", "developer", "publisher", "positive", "negative",
    "owners", "average_forever", "median_forever", "price", "initialprice",
    "discount", "ccu",
)


def extract(limit: int) -> list[dict]:
    """Récupère les `limit` jeux les plus populaires et les sauvegarde."""
    if OUTPUT.exists():
        games = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if len(games) >= limit:
            log.info("SteamSpy déjà extrait (%d jeux), réutilisation du cache", len(games))
            return games[:limit]

    session = build_session()
    limiter = RateLimiter(config.STEAMSPY_ALL_DELAY)
    games: list[dict] = []
    page = 0
    while len(games) < limit:
        limiter.wait()
        log.info("SteamSpy : page %d", page)
        resp = session.get(config.STEAMSPY_URL, params={"request": "all", "page": page}, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        if not payload:
            break  # plus de pages disponibles
        games.extend({k: g.get(k) for k in FIELDS} for g in payload.values())
        page += 1

    # Pages complètes mises en cache : une relance avec un --limit plus grand
    # ne retélécharge que les pages manquantes... ou aucune.
    OUTPUT.write_text(json.dumps(games, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("SteamSpy : %d jeux sauvegardés dans %s", len(games), OUTPUT.name)
    return games[:limit]
