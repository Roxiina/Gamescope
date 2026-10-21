"""Source 4 - Base de données PostgreSQL du partenaire (catalogue Steam).

Connexion avec un rôle en LECTURE SEULE (gamescope_reader) : l'extraction ne
peut pas modifier la base source. La requête est versionnée dans
sql/partner/01_extraction.sql et documentée dans sql/README.md.
"""
import logging
import os

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from extraction import config

log = logging.getLogger("extraction.db_partner")

QUERY_FILE = config.ROOT_DIR / "sql" / "partner" / "01_extraction.sql"
OUTPUT = config.RAW_DIR / "partner_games.parquet"


def build_engine():
    url = URL.create(
        "postgresql+psycopg2",
        username="gamescope_reader",
        password=os.environ["PARTNER_READER_PASSWORD"],
        host=os.getenv("PARTNER_DB_HOST", "localhost"),
        port=int(os.getenv("PARTNER_DB_PORT", 5435)),
        database="steam_partner",
    )
    return create_engine(url, pool_pre_ping=True)


def extract(appids: list[int]) -> pd.DataFrame:
    engine = build_engine()
    query = text(QUERY_FILE.read_text(encoding="utf-8"))
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"appids": appids})
    engine.dispose()

    df.to_parquet(OUTPUT, index=False)
    log.info("Base partenaire : %d/%d jeux trouvés, sauvegardés dans %s",
             len(df), len(appids), OUTPUT.name)
    return df
