"""Remplit la base du partenaire avec le dataset Kaggle "Steam Games" (games.csv).

Usage (après `docker compose up -d partner-db`) :
    python -m sources.partner_db.seed_partner_db

Contrainte technique du fichier : l'en-tête contient "DiscountDLC count"
(deux colonnes fusionnées), soit 39 noms pour 40 valeurs par ligne. L'en-tête
est corrigé à la lecture.
"""
import logging
import os

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from extraction import config

log = logging.getLogger("seed_partner")
SOURCE = config.EXTERNAL_DIR / "games.csv"

RENAME = {
    "AppID": "app_id", "Name": "name", "Release date": "release_date",
    "Estimated owners": "estimated_owners", "Peak CCU": "peak_ccu",
    "Required age": "required_age", "Price": "price_usd", "Discount": "discount_pct",
    "DLC count": "dlc_count", "Windows": "windows", "Mac": "mac", "Linux": "linux",
    "Metacritic score": "metacritic_score", "User score": "user_score",
    "Positive": "positive", "Negative": "negative", "Achievements": "achievements",
    "Recommendations": "recommendations", "Average playtime forever": "avg_playtime_min",
    "Median playtime forever": "median_playtime_min",
}
# (colonne CSV, table référentiel, colonne id, table d'association, garder le rang)
LINKS = [
    ("Developers", "developers", "developer_id", "game_developers", False),
    ("Publishers", "publishers", "publisher_id", "game_publishers", False),
    ("Genres", "genres", "genre_id", "game_genres", False),
    ("Tags", "tags", "tag_id", "game_tags", True),
    ("Categories", "categories", "category_id", "game_categories", False),
]


def admin_params() -> dict:
    """Compte propriétaire de la base (création et remplissage)."""
    return {
        "host": os.environ["PARTNER_DB_HOST"], "port": os.environ["PARTNER_DB_PORT"],
        "dbname": "steam_partner", "user": os.environ["PARTNER_DB_USER"],
        "password": os.environ["PARTNER_DB_PASSWORD"],
    }


def read_games() -> pd.DataFrame:
    header = SOURCE.open(encoding="utf-8").readline().strip().split(",")
    i = header.index("DiscountDLC count")
    header[i:i + 1] = ["Discount", "DLC count"]
    df = pd.read_csv(SOURCE, names=header, header=0, index_col=False,
                     usecols=list(RENAME) + [c for c, *_ in LINKS])
    df = df.drop_duplicates("AppID")
    df["Release date"] = pd.to_datetime(df["Release date"], format="mixed", errors="coerce").dt.date
    return df


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
    df = read_games()
    log.info("%d jeux lus depuis %s", len(df), SOURCE.name)

    with psycopg2.connect(**admin_params()) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE games, developers, publishers, genres, tags, categories CASCADE")
        games = df[list(RENAME)].rename(columns=RENAME)
        games = games.astype(object).where(games.notna(), None)
        execute_values(cur, f"INSERT INTO games ({', '.join(games.columns)}) VALUES %s",
                       games.itertuples(index=False, name=None), page_size=5000)

        for col, table, id_col, link_table, ranked in LINKS:
            pairs = [(app_id, name.strip(), rank)
                     for app_id, value in zip(df["AppID"], df[col]) if isinstance(value, str)
                     for rank, name in enumerate(dict.fromkeys(value.split(",")), 1) if name.strip()]
            names = sorted({name for _, name, _ in pairs})
            execute_values(cur, f"INSERT INTO {table} (name) VALUES %s", [(n,) for n in names])
            cur.execute(f"SELECT name, {id_col} FROM {table}")
            ids = dict(cur.fetchall())
            rows = {(a, ids[n]): r for a, n, r in pairs}  # dédoublonnage (app, id)
            if ranked:
                values = [(a, i, r) for (a, i), r in rows.items()]
                sql = f"INSERT INTO {link_table} (app_id, {id_col}, tag_rank) VALUES %s"
            else:
                values = list(rows)
                sql = f"INSERT INTO {link_table} (app_id, {id_col}) VALUES %s"
            execute_values(cur, sql, values, page_size=10000)
            log.info("%s : %d valeurs, %d liens", table, len(names), len(values))

        # Rôle en lecture seule utilisé par GameScope pour l'extraction
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'gamescope_reader'")
        verb = "ALTER" if cur.fetchone() else "CREATE"
        cur.execute(f"{verb} ROLE gamescope_reader LOGIN PASSWORD %s",
                    (os.environ["PARTNER_READER_PASSWORD"],))
        cur.execute("""
            GRANT CONNECT ON DATABASE steam_partner TO gamescope_reader;
            GRANT USAGE ON SCHEMA public TO gamescope_reader;
            GRANT SELECT ON ALL TABLES IN SCHEMA public TO gamescope_reader;
        """)
    log.info("Base partenaire prête")


if __name__ == "__main__":
    main()
