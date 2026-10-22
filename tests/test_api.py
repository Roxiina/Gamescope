"""Tests de l'API REST sur la vraie base (nécessite gamescope-db démarrée).

Trois comptes de test (un par rôle) sont créés au début et supprimés à la fin.
"""
import jwt
import psycopg2
import pytest
from fastapi.testclient import TestClient

from api.config import get_settings
from api.limiter import limiter
from api.main import app
from api.security import hash_password
from database.import_db import connect

PASSWORD = "mot-de-passe-de-test-123"
USERS = {role: f"{role}@test.gamescope" for role in ("reader", "analyst", "admin")}
WITCHER_3 = 292030


@pytest.fixture(scope="module")
def client():
    try:
        conn = connect()
    except psycopg2.OperationalError:
        pytest.skip("base gamescope-db non démarrée")
    with conn, conn.cursor() as cur:
        cur.execute("DELETE FROM api_user WHERE email LIKE '%%@test.gamescope'")
        for role, email in USERS.items():
            cur.execute("INSERT INTO api_user (email, password_hash, role) VALUES (%s, %s, %s)",
                        (email, hash_password(PASSWORD), role))
    yield TestClient(app)
    with conn, conn.cursor() as cur:
        cur.execute("DELETE FROM api_user WHERE email LIKE '%%@test.gamescope'")
    conn.close()


@pytest.fixture(autouse=True)
def reset_rate_limits():
    limiter.reset()


def login(client, email, password=PASSWORD):
    return client.post("/api/v1/auth/token", data={"username": email, "password": password})


@pytest.fixture(scope="module")
def headers(client):
    limiter.reset()
    return {role: {"Authorization": f"Bearer {login(client, email).json()['access_token']}"}
            for role, email in USERS.items()}


# --- Authentification (OWASP API2) ------------------------------------------
def test_health_is_public(client):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}


def test_data_requires_token(client):
    response = client.get("/api/v1/games")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_login_returns_jwt_with_expiry(client):
    body = login(client, USERS["reader"]).json()
    payload = jwt.decode(body["access_token"], options={"verify_signature": False})
    assert body["token_type"] == "bearer" and body["expires_in"] == 1800
    assert payload["role"] == "reader" and "exp" in payload


def test_wrong_password_and_unknown_email_give_same_error(client):
    wrong = login(client, USERS["reader"], "mauvais-mot-de-passe")
    unknown = login(client, "inconnu@test.gamescope")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()  # pas d'énumération des comptes


def test_forged_and_expired_tokens_are_rejected(client):
    forged = jwt.encode({"sub": "1", "role": "admin", "exp": 9999999999}, "x" * 32, "HS256")
    expired = jwt.encode({"sub": "1", "exp": 1}, get_settings().jwt_secret_key.get_secret_value(), "HS256")
    unsigned = jwt.encode({"sub": "1", "exp": 9999999999}, None, "none")
    for token in (forged, expired, unsigned, "pas-un-jeton"):
        assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_login_brute_force_is_rate_limited(client):
    codes = [login(client, USERS["reader"], "essai").status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


# --- Autorisations par rôle (OWASP API1, API5) --------------------------------
@pytest.mark.parametrize("role, url, expected", [
    ("reader", f"/api/v1/games/{WITCHER_3}", 200),
    ("reader", f"/api/v1/games/{WITCHER_3}/reviews", 403),
    ("reader", "/api/v1/stats/genres", 403),
    ("reader", "/api/v1/users", 403),
    ("analyst", f"/api/v1/games/{WITCHER_3}/reviews", 200),
    ("analyst", "/api/v1/stats/genres", 200),
    ("analyst", "/api/v1/users", 403),
    ("admin", "/api/v1/users", 200),
])
def test_role_permissions(client, headers, role, url, expected):
    assert client.get(url, headers=headers[role]).status_code == expected


def test_me_returns_only_own_account(client, headers):
    body = client.get("/api/v1/auth/me", headers=headers["analyst"]).json()
    assert body["email"] == USERS["analyst"] and "password_hash" not in body


def test_admin_cannot_delete_own_account(client, headers):
    me = client.get("/api/v1/auth/me", headers=headers["admin"]).json()
    assert client.delete(f"/api/v1/users/{me['user_id']}", headers=headers["admin"]).status_code == 400


def test_admin_creates_and_deletes_account(client, headers):
    created = client.post("/api/v1/users", headers=headers["admin"],
                          json={"email": "nouveau@test.gamescope", "password": PASSWORD, "role": "reader"})
    assert created.status_code == 201 and "password_hash" not in created.json()
    duplicate = client.post("/api/v1/users", headers=headers["admin"],
                            json={"email": "NOUVEAU@test.gamescope", "password": PASSWORD})
    assert duplicate.status_code == 409
    assert client.delete(f"/api/v1/users/{created.json()['user_id']}", headers=headers["admin"]).status_code == 204


def test_user_creation_rejects_weak_password_and_extra_fields(client, headers):
    weak = {"email": "faible@test.gamescope", "password": "court"}
    extra = {"email": "extra@test.gamescope", "password": PASSWORD, "user_id": 1}
    assert client.post("/api/v1/users", headers=headers["admin"], json=weak).status_code == 422
    assert client.post("/api/v1/users", headers=headers["admin"], json=extra).status_code == 422


# --- Données et exposition (OWASP API3, API4) ---------------------------------
def test_game_detail(client, headers):
    game = client.get(f"/api/v1/games/{WITCHER_3}", headers=headers["reader"]).json()
    assert game["name"].startswith("The Witcher 3")
    assert "RPG" in game["genres"] and game["tags"][0] == "Open World"
    assert game["stats_2021"]["nb_reviews"] > 0


def test_unknown_game_is_404(client, headers):
    assert client.get("/api/v1/games/1", headers=headers["reader"]).status_code == 404


def test_filters_and_sort(client, headers):
    body = client.get("/api/v1/games", headers=headers["reader"], params={
        "genre": "rpg", "min_metacritic": 90, "sort": "-metacritic_score", "size": 100}).json()
    scores = [g["metacritic_score"] for g in body["items"]]
    assert body["total"] == len(scores) > 0
    assert all(s >= 90 for s in scores) and scores == sorted(scores, reverse=True)


def test_pagination_is_bounded(client, headers):
    assert client.get("/api/v1/games?size=1000", headers=headers["reader"]).status_code == 422
    page2 = client.get("/api/v1/games?size=5&page=2", headers=headers["reader"]).json()
    assert len(page2["items"]) == 5 and page2["page"] == 2 and page2["pages"] == -(-page2["total"] // 5)


def test_reviews_never_expose_author(client, headers):
    reviews = client.get(f"/api/v1/games/{WITCHER_3}/reviews?language=en", headers=headers["analyst"]).json()
    assert reviews["total"] > 0
    assert all(set(r) & {"author_id", "author_hash"} == set() for r in reviews["items"])
    assert all(r["language"] == "en" for r in reviews["items"])


# --- Injections et configuration (OWASP API8) -------------------------------
@pytest.mark.parametrize("params", [
    {"sort": "name; DROP TABLE game"},
    {"min_metacritic": "1 OR 1=1"},
])
def test_injection_attempts_are_rejected(client, headers, params):
    assert client.get("/api/v1/games", headers=headers["reader"], params=params).status_code == 422


def test_like_wildcards_are_literal(client, headers):
    # "%" seul correspondrait à tout si les jokers n'étaient pas échappés
    body = client.get("/api/v1/games", headers=headers["reader"], params={"q": "%%"}).json()
    assert body["total"] == 0


def test_security_headers(client):
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]


def test_openapi_documents_all_routes_and_security(client):
    spec = client.get("/openapi.json").json()
    assert spec["openapi"].startswith("3.")
    assert "OAuth2PasswordBearer" in spec["components"]["securitySchemes"]
    assert {"/api/v1/games", "/api/v1/games/{app_id}/reviews", "/api/v1/users"} <= set(spec["paths"])
