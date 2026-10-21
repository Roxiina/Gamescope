"""Source 2 - API REST Steam Store : fiche détaillée et avis récents de chaque jeu.

Endpoints publics, sans clé :
- /api/appdetails?appids=<id>  : prix, genres, plateformes, Metacritic...
- /appreviews/<id>?json=1      : avis des joueurs (données personnelles !)
"""
import logging

from extraction import config
from extraction.utils import (RateLimiter, append_jsonl, build_session,
                              pseudonymize, read_done_ids, throttled_get)

log = logging.getLogger("extraction.steam_api")

DETAILS_OUTPUT = config.RAW_DIR / "steam_appdetails.jsonl"
REVIEWS_OUTPUT = config.RAW_DIR / "steam_reviews_api.jsonl"


def parse_details(appid: int, data: dict) -> dict:
    """Ne garde que les champs utiles au projet (la description HTML est exclue)."""
    price = data.get("price_overview") or {}
    return {
        "appid": appid,
        "name": data.get("name"),
        "type": data.get("type"),
        "required_age": data.get("required_age"),
        "is_free": data.get("is_free"),
        "price_initial_cents": price.get("initial"),
        "price_final_cents": price.get("final"),
        "currency": price.get("currency"),
        "release_date": (data.get("release_date") or {}).get("date"),
        "coming_soon": (data.get("release_date") or {}).get("coming_soon"),
        "developers": data.get("developers", []),
        "publishers": data.get("publishers", []),
        "genres": [g["description"] for g in data.get("genres", [])],
        "categories": [c["description"] for c in data.get("categories", [])],
        "platforms": [p for p, ok in (data.get("platforms") or {}).items() if ok],
        "metacritic_score": (data.get("metacritic") or {}).get("score"),
        "recommendations": (data.get("recommendations") or {}).get("total"),
        "dlc_count": len(data.get("dlc", [])),
    }


def parse_review(appid: int, review: dict) -> dict:
    """Minimisation RGPD : steamid pseudonymisé, pseudo/avatar/profil non collectés."""
    author = review.get("author", {})
    return {
        "review_id": review.get("recommendationid"),
        "appid": appid,
        "author_hash": pseudonymize(author.get("steamid", "")),
        "author_playtime_min": author.get("playtime_at_review"),
        "author_num_reviews": author.get("num_reviews"),
        "language": review.get("language"),
        "review_text": review.get("review"),
        "voted_up": review.get("voted_up"),
        "votes_up": review.get("votes_up"),
        "timestamp_created": review.get("timestamp_created"),
        "steam_purchase": review.get("steam_purchase"),
        "received_for_free": review.get("received_for_free"),
    }


def extract(appids: list[int]) -> None:
    """Extrait fiches et avis ; reprend là où une exécution précédente s'est arrêtée."""
    session = build_session()
    limiter = RateLimiter(config.STEAM_DELAY)
    done_details = read_done_ids(DETAILS_OUTPUT)
    done_reviews = read_done_ids(REVIEWS_OUTPUT)
    todo = [a for a in appids if a not in done_details or a not in done_reviews]
    log.info("Steam API : %d jeux à traiter (%d déjà faits)", len(todo), len(appids) - len(todo))

    errors = 0
    for i, appid in enumerate(todo, 1):
        try:
            if appid not in done_details:
                resp = throttled_get(
                    session, limiter, config.STEAM_APPDETAILS_URL, log,
                    params={"appids": appid, "cc": config.STEAM_COUNTRY, "l": config.STEAM_LANGUAGE},
                )
                entry = (resp.json() or {}).get(str(appid), {})
                if entry.get("success"):
                    append_jsonl(DETAILS_OUTPUT, parse_details(appid, entry["data"]))
                else:
                    # Jeu retiré de la vente ou indisponible en France : tracé, pas bloquant
                    append_jsonl(DETAILS_OUTPUT, {"appid": appid, "unavailable": True})
                    log.warning("appdetails indisponible pour %s", appid)

            if appid not in done_reviews:
                resp = throttled_get(
                    session, limiter, config.STEAM_APPREVIEWS_URL.format(appid=appid), log,
                    params={"json": 1, "num_per_page": config.REVIEWS_PER_GAME,
                            "language": "all", "filter": "recent", "purchase_type": "all"},
                )
                for review in resp.json().get("reviews", []):
                    append_jsonl(REVIEWS_OUTPUT, parse_review(appid, review))
                # Marqueur de fin : permet la reprise même pour un jeu sans avis
                append_jsonl(REVIEWS_OUTPUT, {"appid": appid, "marker": "done"})

        except Exception as exc:  # une erreur sur un jeu ne doit pas arrêter la collecte
            errors += 1
            log.error("Échec pour l'appid %s : %s", appid, exc)

        if i % 50 == 0:
            log.info("Steam API : %d/%d jeux traités", i, len(todo))

    log.info("Steam API terminé : %d erreurs", errors)
