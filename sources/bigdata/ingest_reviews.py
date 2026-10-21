"""Chargement du dataset Kaggle "Steam Reviews 2021" (8 Go CSV) dans le data lake.

Usage :
    python -m sources.bigdata.ingest_reviews

Le CSV est lu EN FLUX par blocs (pyarrow) : la mémoire utilisée reste faible
quelle que soit la taille du fichier. Le data lake produit est ensuite
interrogé par Spark (voir extraction/bigdata_reviews.py).

- Schéma explicite : pas de passe d'inférence de types sur 8 Go
- newlines_in_values : certains avis contiennent des retours à la ligne
- RGPD : le steamid est pseudonymisé (SHA-256 salé) AVANT écriture, le data
  lake ne contient donc jamais l'identifiant réel
- Parquet compressé (snappy), partitionné par année de publication : les
  requêtes filtrées sur l'année ne lisent que les dossiers concernés
"""
import hashlib
import logging
import shutil

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as csv
import pyarrow.dataset as ds

from extraction import config

log = logging.getLogger("ingest_reviews")

SOURCE = config.EXTERNAL_DIR / "steam_reviews.csv"
LAKE = config.DATA_DIR / "bigdata" / "steam_reviews"

COLUMN_TYPES = {
    "app_id": pa.int64(), "app_name": pa.string(), "review_id": pa.int64(),
    "language": pa.string(), "review": pa.string(),
    "timestamp_created": pa.int64(), "timestamp_updated": pa.int64(),
    "recommended": pa.bool_(), "votes_helpful": pa.int64(), "votes_funny": pa.int64(),
    "weighted_vote_score": pa.float64(), "comment_count": pa.int64(),
    "steam_purchase": pa.bool_(), "received_for_free": pa.bool_(),
    "written_during_early_access": pa.bool_(),
    "author.steamid": pa.string(), "author.num_games_owned": pa.int64(),
    "author.num_reviews": pa.int64(), "author.playtime_forever": pa.float64(),
    "author.playtime_last_two_weeks": pa.float64(),
    "author.playtime_at_review": pa.float64(),
}


def pseudonymize_column(steamids: pa.ChunkedArray | pa.Array) -> pa.Array:
    salt = config.PSEUDO_SALT.encode()
    return pa.array(
        [hashlib.sha256(salt + s.encode()).hexdigest() if s else None
         for s in steamids.to_pylist()],
        pa.string(),
    )


def transform(batch: pa.RecordBatch) -> pa.Table:
    table = pa.Table.from_batches([batch])
    author_hash = pseudonymize_column(table["author.steamid"])
    table = table.drop_columns(["author.steamid"])  # minimisation RGPD
    table = table.rename_columns([c.replace("author.", "author_") for c in table.column_names])
    year = pc.year(pc.cast(pc.multiply(table["timestamp_created"], 1000), pa.timestamp("ms")))
    return table.append_column("author_hash", author_hash).append_column("year", year)


def batches():
    reader = csv.open_csv(
        SOURCE,
        read_options=csv.ReadOptions(block_size=64 << 20),
        parse_options=csv.ParseOptions(newlines_in_values=True),
        convert_options=csv.ConvertOptions(column_types=COLUMN_TYPES,
                                           include_columns=list(COLUMN_TYPES)),
    )
    total = 0
    for batch in reader:
        table = transform(batch)
        total += table.num_rows
        log.info("%d avis traités", total)
        yield from table.to_batches()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
    if not config.PSEUDO_SALT:
        raise SystemExit("PSEUDO_SALT manquant : ingestion refusée (RGPD)")
    if LAKE.exists():
        shutil.rmtree(LAKE)  # rechargement complet, idempotent

    gen = batches()
    first = next(gen)
    schema = first.schema

    def all_batches():
        yield first
        yield from gen

    ds.write_dataset(
        all_batches(), LAKE, schema=schema, format="parquet",
        partitioning=["year"], partitioning_flavor="hive",
        file_options=ds.ParquetFileFormat().make_write_options(compression="snappy"),
        max_rows_per_file=2_000_000, max_rows_per_group=250_000,
    )
    log.info("Data lake écrit dans %s", LAKE)


if __name__ == "__main__":
    main()
