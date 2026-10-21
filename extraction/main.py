"""Point de lancement de l'extraction GameScope.

Usage :
    python -m extraction.main                       # toutes les sources, 2000 jeux
    python -m extraction.main --limit 20            # test rapide
    python -m extraction.main --sources file database

Étapes : initialisation -> SteamSpy (liste des jeux de référence) -> sources
demandées -> bilan. Chaque source sauvegarde ses résultats dans data/raw/.
Une source en échec est journalisée sans empêcher les suivantes.

Prérequis pour database et bigdata : docker compose up -d
"""
import argparse
import sys
import time

from extraction import (bigdata_reviews, config, db_partner, file_vgsales,
                        steam_scraper, steam_store_api, steamspy)
from extraction.utils import setup_logging

SOURCES = ("api", "scraping", "file", "database", "bigdata")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extraction des données GameScope")
    parser.add_argument("--limit", type=int, default=config.DEFAULT_GAME_LIMIT,
                        help="nombre de jeux à collecter (défaut : %(default)s)")
    parser.add_argument("--sources", nargs="+", choices=SOURCES, default=list(SOURCES))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log = setup_logging()
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    log.info("=== Début de l'extraction : %d jeux, sources %s ===", args.limit, args.sources)

    try:
        # La liste de référence des jeux vient de SteamSpy : sans elle, rien à faire
        games = steamspy.extract(args.limit)
    except Exception:
        log.exception("Erreur fatale : liste de jeux SteamSpy indisponible")
        return 1
    appids = [g["appid"] for g in games]

    steps = {
        "api": lambda: steam_store_api.extract(appids),
        "scraping": lambda: steam_scraper.extract(appids),
        "file": file_vgsales.extract,
        "database": lambda: db_partner.extract(appids),
        "bigdata": bigdata_reviews.extract,
    }
    failed = []
    for name in SOURCES:
        if name not in args.sources:
            continue
        try:
            steps[name]()
        except KeyboardInterrupt:
            log.warning("Interruption manuelle : relancer la commande reprendra la collecte")
            return 130
        except Exception:
            failed.append(name)
            log.exception("Source '%s' en échec", name)

    log.info("=== Extraction terminée en %.0f s, sources en échec : %s ===",
             time.monotonic() - start, failed or "aucune")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
