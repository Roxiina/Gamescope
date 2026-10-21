"""Source 5 - Système big data : Spark Thrift Server (protocole HiveServer2).

Le data lake Parquet (21 M avis, 8 Go en CSV) est trop volumineux pour pandas :
les agrégations sont exécutées par Spark, seul le résultat est rapatrié.
Connexion programmatique avec PyHive, comme pour un cluster Hive/Impala.
"""
import logging
import os

import pandas as pd
from pyhive import hive

from extraction import config

log = logging.getLogger("extraction.bigdata")
logging.getLogger("pyhive").setLevel(logging.WARNING)  # PyHive journalise chaque requête

SQL_DIR = config.ROOT_DIR / "sql" / "bigdata"
LAKE_PATH = "/data/bigdata/steam_reviews"  # chemin vu depuis le conteneur Spark
QUERIES = {
    "01_reviews_stats.sql": config.RAW_DIR / "bigdata_reviews_stats.parquet",
    "02_reviews_sample.sql": config.RAW_DIR / "bigdata_reviews_sample.parquet",
}


def extract() -> None:
    conn = hive.connect(
        host=os.getenv("SPARK_HOST", "localhost"),
        port=int(os.getenv("SPARK_PORT", 10000)),
        auth="NOSASL",
    )
    try:
        cursor = conn.cursor()
        # Vue sur le data lake : Spark découvre seul les partitions year=...
        cursor.execute(
            f"CREATE OR REPLACE TEMPORARY VIEW steam_reviews "
            f"USING parquet OPTIONS (path '{LAKE_PATH}')"
        )
        for sql_file, output in QUERIES.items():
            query = (SQL_DIR / sql_file).read_text(encoding="utf-8")
            log.info("Spark SQL : exécution de %s", sql_file)
            cursor.execute(query)
            columns = [c[0] for c in cursor.description]
            df = pd.DataFrame(cursor.fetchall(), columns=columns)
            df.to_parquet(output, index=False)
            log.info("Spark SQL : %d lignes sauvegardées dans %s", len(df), output.name)
    finally:
        conn.close()
