"""Import du jeu de données final (data/clean/) dans la base PostgreSQL GameScope.

Usage (après `docker compose up -d --wait gamescope-db`) :
    python -m database.import_db

- Une seule transaction : en cas d'erreur, rien n'est importé (pas d'état partiel)
- Idempotent : relancer l'import met à jour les lignes existantes (UPSERT)
  au lieu de créer des doublons
- Ordre imposé par les clés étrangères : référentiels -> jeux -> associations
  -> auteurs -> avis -> ventes
"""
import logging
import os
import sys
import time

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from extraction import config
from extraction.utils import setup_logging

log = logging.getLogger("import_db")

CLEAN_DIR = config.DATA_DIR / "clean"
PAGE = 5000  # lignes envoyées par requête INSERT

GAME_COLUMNS = [
    "app_id", "name", "release_date", "price_eur", "price_initial_eur", "discount_pct",
    "is_free", "required_age", "owners_min", "owners_max", "metacritic_score",
    "positive_reviews", "negative_reviews", "pct_positive", "recent_review_pct",
    "recent_review_count", "recent_review_desc", "avg_playtime_min", "median_playtime_min",
    "peak_ccu", "dlc_count", "achievements", "recommendations", "languages_count",
]
# (colonne liste dans games.parquet, table référentiel, colonne id, table d'association)
LINKS = [
    ("developers", "developer", "developer_id", "game_developer"),
    ("publishers", "publisher", "publisher_id", "game_publisher"),
    ("genres", "genre", "genre_id", "game_genre"),
    ("categories", "category", "category_id", "game_category"),
    ("tags", "tag", "tag_id", "game_tag"),
    ("platforms", "operating_system", "os_id", "game_os"),
]


def connect():
    return psycopg2.connect(
        host=os.getenv("GAMESCOPE_DB_HOST", "localhost"),
        port=int(os.getenv("GAMESCOPE_DB_PORT", 5436)),
        dbname="gamescope",
        user=os.environ["GAMESCOPE_DB_USER"],
        password=os.environ["GAMESCOPE_DB_PASSWORD"],
    )


def records(df: pd.DataFrame, columns: list[str]) -> list[tuple]:
    """Tuples prêts pour psycopg2 : NaN / NA / NaT pandas -> NULL SQL."""
    out = df[columns].astype(object)
    return list(out.where(out.notna(), None).itertuples(index=False, name=None))


def upsert(cur, table: str, columns: list[str], rows: list[tuple], conflict: str) -> None:
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c not in conflict)
    action = f"DO UPDATE SET {updates}" if updates else "DO NOTHING"
    execute_values(cur, f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
                        f"ON CONFLICT ({conflict}) {action}", rows, page_size=PAGE)


def reference_ids(cur, table: str, id_col: str, names: set[str], name_col: str = "name") -> dict:
    """Insère les valeurs manquantes d'un référentiel et renvoie {valeur: id}."""
    execute_values(cur, f"INSERT INTO {table} ({name_col}) VALUES %s ON CONFLICT DO NOTHING",
                   [(v,) for v in sorted(names)], page_size=PAGE)
    cur.execute(f"SELECT {name_col}, {id_col} FROM {table}")
    return dict(cur.fetchall())


def import_games(cur, games: pd.DataFrame) -> None:
    games = games.copy()
    for col in ("discount_pct", "recent_review_pct"):
        games[col] = games[col].round().astype("Int64")
    upsert(cur, "game", GAME_COLUMNS, records(games, GAME_COLUMNS), "app_id")
    cur.execute("UPDATE game SET updated_at = now() WHERE app_id = ANY(%s)", (games["app_id"].tolist(),))
    log.info("game : %d jeux", len(games))

    app_ids = games["app_id"].tolist()
    for list_col, table, id_col, link_table in LINKS:
        ids = reference_ids(cur, table, id_col, {v for values in games[list_col] for v in values})
        # Associations remplacées : un tag retiré côté Steam disparaît aussi ici
        cur.execute(f"DELETE FROM {link_table} WHERE app_id = ANY(%s)", (app_ids,))
        if link_table == "game_tag":
            rows = [(a, ids[v], rank) for a, values in zip(app_ids, games[list_col])
                    for rank, v in enumerate(values, 1)]
            sql = f"INSERT INTO {link_table} (app_id, {id_col}, tag_rank) VALUES %s"
        else:
            rows = [(a, ids[v]) for a, values in zip(app_ids, games[list_col]) for v in values]
            sql = f"INSERT INTO {link_table} (app_id, {id_col}) VALUES %s"
        execute_values(cur, sql, rows, page_size=PAGE)
        log.info("%s : %d valeurs, %d liens", table, len(ids), len(rows))

    # Sélection AVANT renommage : games contient déjà une colonne median_playtime_min
    stats = games.loc[games["reviews2021_nb_reviews"].notna(),
                      ["app_id"] + [c for c in games if c.startswith("reviews2021_")]].rename(columns={
        "reviews2021_nb_reviews": "nb_reviews", "reviews2021_pct_recommended": "pct_recommended",
        "reviews2021_median_playtime_at_review_min": "median_playtime_min",
        "reviews2021_nb_languages": "nb_languages"})
    stats["median_playtime_min"] = stats["median_playtime_min"].round().astype("Int64")
    cols = ["app_id", "nb_reviews", "pct_recommended", "median_playtime_min", "nb_languages"]
    upsert(cur, "game_review_stats_2021", cols, records(stats, cols), "app_id")
    log.info("game_review_stats_2021 : %d jeux", len(stats))


def import_reviews(cur, reviews: pd.DataFrame) -> None:
    languages = reference_ids(cur, "language", "language_id",
                              set(reviews["language"].dropna()), name_col="code")
    authors = reference_ids(cur, "author", "author_id", set(reviews["author_hash"]),
                            name_col="author_hash")
    reviews = reviews.assign(
        author_id=reviews["author_hash"].map(authors),
        language_id=reviews["language"].map(languages).astype("Int64"),
    )
    cols = ["review_id", "app_id", "author_id", "language_id", "review_text", "recommended",
            "votes_helpful", "author_playtime_min", "source", "created_at", "collected_at"]
    upsert(cur, "review", cols, records(reviews, cols), "review_id")
    log.info("review : %d avis, %d auteurs pseudonymisés, %d langues",
             len(reviews), reviews["author_id"].nunique(), len(languages))


def import_sales(cur, sales: pd.DataFrame) -> None:
    platforms = reference_ids(cur, "platform", "platform_id", set(sales["platform"]))
    publishers = reference_ids(cur, "publisher", "publisher_id", set(sales["publisher"].dropna()))
    sales = sales.assign(
        platform_id=sales["platform"].map(platforms),
        publisher_id=sales["publisher"].map(publishers).astype("Int64"),
        vgsales_genre=sales["genre"],
    )
    cols = ["app_id", "platform_id", "publisher_id", "vgsales_name", "release_year",
            "vgsales_genre", "sales_na_units", "sales_eu_units", "sales_jp_units",
            "sales_other_units", "sales_global_units", "match_method"]
    upsert(cur, "sale", cols, records(sales, cols),
           "app_id, platform_id, vgsales_name, release_year")
    log.info("sale : %d lignes de ventes", len(sales))


def main() -> int:
    setup_logging("import_db")
    start = time.monotonic()
    try:
        games = pd.read_parquet(CLEAN_DIR / "games.parquet")
        reviews = pd.read_parquet(CLEAN_DIR / "reviews.parquet")
        sales = pd.read_parquet(CLEAN_DIR / "sales.parquet")
    except FileNotFoundError as exc:
        log.error("Jeu de données absent (lancer d'abord python -m cleaning.aggregate) : %s", exc)
        return 1

    try:
        with connect() as conn, conn.cursor() as cur:  # commit si succès, rollback sinon
            import_games(cur, games)
            import_reviews(cur, reviews)
            import_sales(cur, sales)
    except psycopg2.Error:
        log.exception("Import annulé (rollback), la base n'a pas été modifiée")
        return 1

    # Les UPSERT et le remplacement des associations laissent des lignes mortes :
    # VACUUM récupère l'espace, ANALYZE met à jour les statistiques du planificateur.
    # (VACUUM est interdit dans une transaction, d'où le mode autocommit)
    conn = connect()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("VACUUM ANALYZE")
    conn.close()

    log.info("Import terminé en %.1f s", time.monotonic() - start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
