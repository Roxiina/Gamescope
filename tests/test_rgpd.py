"""Tests de la procédure de tri RGPD sur la vraie base (nécessite gamescope-db démarrée).

Chaque test travaille dans une transaction annulée à la fin : la base n'est
jamais modifiée.
"""
import psycopg2
import pytest

from database import rgpd_cleanup
from database.import_db import connect
from extraction.utils import pseudonymize

PARAMS = {"review_years": 3, "user_years": 2}


@pytest.fixture
def cur():
    try:
        conn = connect()
    except psycopg2.OperationalError:
        pytest.skip("base gamescope-db non démarrée")
    with conn.cursor() as cursor:
        yield cursor
    conn.rollback()
    conn.close()


def add_review(cur, review_id: int, steamid: str, collected_years_ago: int) -> None:
    cur.execute("SELECT app_id FROM game LIMIT 1")
    app_id = cur.fetchone()[0]
    cur.execute("INSERT INTO author (author_hash) VALUES (%s) RETURNING author_id", (pseudonymize(steamid),))
    author_id = cur.fetchone()[0]
    cur.execute("""
        INSERT INTO review (review_id, app_id, author_id, review_text, recommended, source,
                            created_at, collected_at)
        VALUES (%s, %s, %s, 'test', TRUE, 'steam_api', now(),
                now() - make_interval(years => %s))""",
                (review_id, app_id, author_id, collected_years_ago))


def count(cur, sql: str, *args) -> int:
    cur.execute(sql, args)
    return cur.fetchone()[0]


def test_old_reviews_and_orphan_authors_are_purged(cur):
    add_review(cur, -1, "test-ancien", collected_years_ago=4)
    add_review(cur, -2, "test-recent", collected_years_ago=1)
    for _, _, sql in rgpd_cleanup.PURGES:
        cur.execute(sql, PARAMS)
    assert count(cur, "SELECT count(*) FROM review WHERE review_id = -1") == 0
    assert count(cur, "SELECT count(*) FROM review WHERE review_id = -2") == 1
    assert count(cur, "SELECT count(*) FROM author WHERE author_hash = %s", pseudonymize("test-ancien")) == 0


def test_inactive_api_users_are_purged(cur):
    cur.execute("""INSERT INTO api_user (email, password_hash, role, created_at, last_login_at) VALUES
        ('inactif@test.fr', 'x', 'reader', now() - interval '5 years', now() - interval '3 years'),
        ('actif@test.fr',   'x', 'reader', now() - interval '5 years', now() - interval '1 month')""")
    cur.execute(rgpd_cleanup.PURGES[2][2], PARAMS)
    cur.execute("SELECT email FROM api_user WHERE email LIKE '%%@test.fr'")
    assert [r[0] for r in cur.fetchall()] == ["actif@test.fr"]


def test_erasure_request_deletes_all_reviews_of_a_person(cur):
    add_review(cur, -3, "76561190000000001", collected_years_ago=0)
    rgpd_cleanup.erase_person(cur, "76561190000000001", dry_run=True)
    assert count(cur, "SELECT count(*) FROM review WHERE review_id = -3") == 0
