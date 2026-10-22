# API REST GameScope (C5)

Met à disposition le jeu de données GameScope (1 982 jeux, 85 791 avis, 719 lignes
de ventes) pour les autres composants du projet : analyses, futur modèle d'IA
(blocs E2/E3) et application (E4).

- **Documentation interactive (Swagger UI)** : http://localhost:8000/docs
- **Documentation alternative (ReDoc)** : http://localhost:8000/redoc
- **Spécification OpenAPI 3.1** : http://localhost:8000/openapi.json, versionnée dans
  [`docs/openapi.json`](../docs/openapi.json)

## 1. Spécifications techniques

| Élément | Choix | Justification |
|---|---|---|
| Langage | Python 3.12 | même langage que la collecte et le nettoyage |
| Framework | **FastAPI** 0.121 | génération automatique de la doc **OpenAPI**, validation des entrées par Pydantic, performances (ASGI) |
| Serveur | Uvicorn (2 workers) | serveur ASGI de référence pour FastAPI |
| Accès aux données | SQLAlchemy 2.0 (ORM) + psycopg2 | requêtes **paramétrées** (aucune injection SQL possible), modèles typés |
| Validation | Pydantic 2 | contrôle des types, bornes et formats de chaque paramètre ; réponses filtrées par liste blanche |
| Authentification | OAuth2 *password flow* + **JWT** (PyJWT, HS256) | standard, sans état côté serveur, supporté nativement par Swagger UI |
| Mots de passe | bcrypt (coût 12) | hachage lent et salé, résistant aux attaques par dictionnaire |
| Limitation de débit | slowapi | protection contre le brute force et l'épuisement des ressources |
| Conteneurisation | Docker (`api/Dockerfile`) | installation reproductible, utilisateur non-root |
| Supervision | `/health` + Uptime Kuma | disponibilité de l'API et de la base, alertes |
| Tests | pytest + TestClient | 28 tests sur la vraie base |

### Architecture

```
Client (équipe data, app, modèle IA)
        │  HTTPS + Authorization: Bearer <JWT>
        ▼
┌──────────────────── API FastAPI (conteneur gamescope_api, port 8000) ────────────────────┐
│ Middlewares : limitation de débit → en-têtes de sécurité → CORS (désactivé par défaut)   │
│ Routeurs    : /auth   /games   /genres /tags /platforms   /stats   /users                │
│ Dépendances : get_current_user (JWT) → require_role(reader | analyst | admin)             │
│ Validation  : schémas Pydantic (entrées) ; response_model (sorties, liste blanche)       │
└──────────────────────────────────────────┬────────────────────────────────────────────────┘
                                           │ SQLAlchemy, rôle PostgreSQL gamescope_api,
                                           │ statement_timeout = 5 s
                                           ▼
                              PostgreSQL gamescope (conteneur gamescope_db)
```

```
api/
├── main.py         application, middlewares, gestion des erreurs, /health
├── config.py       configuration (.env), validée au démarrage
├── database.py     connexion PostgreSQL (rôle gamescope_api)
├── models.py       correspondance ORM des tables
├── schemas.py      schémas Pydantic (entrées et sorties)
├── security.py     bcrypt, JWT, contrôle des rôles
├── limiter.py      limitation de débit
├── create_user.py  création d'un compte en ligne de commande
└── routers/        auth.py, games.py, catalog.py, users.py
```

## 2. Installation et lancement

Prérequis : base `gamescope-db` démarrée et remplie (voir le [README principal](../README.md#4-base-de-données-c4)).
Le fichier `.env` doit contenir `GAMESCOPE_API_PASSWORD` et `JWT_SECRET_KEY` (32 caractères
minimum). L'API **refuse de démarrer** si ce secret manque ou est trop court.

```bash
# Option 1 : conteneur Docker (recommandé)
docker compose up -d --build --wait api

# Option 2 : en local (développement, rechargement automatique)
uvicorn api.main:app --reload --port 8000
```

Création du premier compte administrateur (mot de passe saisi de façon masquée) :

```bash
python -m api.create_user --email admin@example.com --role admin
```

Les comptes suivants se créent via l'API (`POST /api/v1/users`, rôle admin).

## 3. Authentification et autorisations

### Obtenir un jeton

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
     -d "username=analyste@example.com" -d "password=<mot de passe>"
# {"access_token": "eyJhbGciOi...", "token_type": "bearer", "expires_in": 1800}
```

Le jeton se transmet ensuite dans l'en-tête de chaque requête :

```bash
curl http://localhost:8000/api/v1/games?genre=RPG -H "Authorization: Bearer eyJhbGciOi..."
```

Dans Swagger UI : bouton **Authorize**, puis saisir l'e-mail et le mot de passe.

| Règle | Détail |
|---|---|
| Durée de validité | 30 minutes (`JWT_EXPIRE_MINUTES`), puis nouvelle connexion |
| Contenu du jeton | `sub` (identifiant du compte), `role`, `iat`, `exp`. Aucune donnée personnelle. |
| Signature | HS256 avec `JWT_SECRET_KEY`. Les jetons non signés (`alg: none`) ou signés avec une autre clé sont refusés. |
| Révocation | le compte est relu en base à chaque requête : un compte **supprimé** perd l'accès immédiatement |
| Échec de connexion | message identique pour un e-mail inconnu et un mauvais mot de passe |
| Tentatives | 5 par minute et par adresse IP sur `/auth/token`, puis `429 Too Many Requests` |

### Rôles

Chaque rôle inclut les droits des rôles précédents.

| Rôle | Pour qui | Accès |
|---|---|---|
| `reader` | consultation, future application de jeu | catalogue des jeux, fiches, ventes, référentiels |
| `analyst` | équipe data, modèle IA | + **avis des joueurs** (données pseudonymisées), statistiques |
| `admin` | administrateur | + gestion des comptes |

### Codes de réponse

| Code | Signification |
|---|---|
| `200` / `201` / `204` | succès / créé / supprimé |
| `400` | requête incohérente (ex. supprimer son propre compte) |
| `401` | jeton absent, invalide ou expiré |
| `403` | rôle insuffisant |
| `404` | ressource inexistante |
| `409` | conflit (e-mail déjà utilisé) |
| `422` | paramètre invalide (type, borne, valeur hors liste) |
| `429` | trop de requêtes |
| `500` | erreur interne : message générique, détail journalisé côté serveur uniquement |

## 4. Points de terminaison

Préfixe : `/api/v1` (version dans l'URL).

| Méthode | Route | Rôle | Description |
|---|---|---|---|
| POST | `/auth/token` | public | obtenir un jeton (formulaire `username` = e-mail, `password`) |
| GET | `/auth/me` | connecté | son propre compte |
| GET | `/games` | reader | recherche paginée et filtrée |
| GET | `/games/{app_id}` | reader | fiche complète : genres, tags ordonnés, développeurs, éditeurs, systèmes, stats 2021 |
| GET | `/games/{app_id}/sales` | reader | ventes par plateforme (unités, par région) |
| GET | `/games/{app_id}/reviews` | **analyst** | avis paginés, filtrables par langue et recommandation |
| GET | `/genres` | reader | genres et nombre de jeux |
| GET | `/tags` | reader | tags les plus utilisés (`limit` ≤ 500) |
| GET | `/platforms` | reader | plateformes présentes dans les ventes |
| GET | `/stats/genres` | **analyst** | par genre : note Metacritic, % d'avis positifs, prix moyen, % de free-to-play |
| GET | `/stats/sales-by-platform` | **analyst** | ventes cumulées par plateforme |
| GET | `/users` | **admin** | liste des comptes |
| POST | `/users` | **admin** | créer un compte (`email`, `password` ≥ 12 caractères, `role`) |
| DELETE | `/users/{user_id}` | **admin** | supprimer un compte (sauf le sien) |
| GET | `/health` | public | état de l'API et de la base (supervision) |

### Paramètres de `GET /games`

| Paramètre | Type | Contrainte | Exemple |
|---|---|---|---|
| `q` | texte | 2 à 100 caractères, recherche dans le nom (`%` et `_` cherchés littéralement) | `witcher 3` |
| `genre` | texte | nom exact, insensible à la casse (voir `/genres`) | `RPG` |
| `tag` | texte | nom exact, insensible à la casse (voir `/tags`) | `Open World` |
| `min_metacritic` | entier | 1 à 100 | `85` |
| `released_after`, `released_before` | date | ISO 8601 | `2015-01-01` |
| `is_free` | booléen | | `true` |
| `sort` | liste fermée | `name`, `release_date`, `-release_date`, `-metacritic_score`, `-pct_positive`, `-owners_max` | `-metacritic_score` |
| `page` | entier | ≥ 1 | `2` |
| `size` | entier | 1 à **100** (défaut 20) | `50` |

Réponse paginée (réelle, pour `GET /api/v1/games?q=witcher 3`) :

```json
{
  "items": [
    {
      "app_id": 292030,
      "name": "The Witcher 3: Wild Hunt — Remastered",
      "release_date": "2015-05-18",
      "price_eur": "49.99",
      "is_free": false,
      "metacritic_score": 93,
      "pct_positive": "96.13",
      "owners_min": 20000000,
      "owners_max": 50000000
    }
  ],
  "total": 1,
  "page": 1,
  "size": 20,
  "pages": 1
}
```

## 5. Sécurité : OWASP API Security Top 10 (2023)

| Risque | Mesures dans GameScope | Vérifié par |
|---|---|---|
| **API1** Autorisation au niveau objet (BOLA) | aucune donnée n'appartient à un utilisateur, sauf son compte : `/auth/me` ne renvoie que le compte du porteur du jeton, `/users/{id}` est réservé aux admins | `test_me_returns_only_own_account` |
| **API2** Authentification défaillante | bcrypt ; JWT court (30 min) avec algorithme imposé ; clé ≥ 256 bits vérifiée au démarrage ; 5 tentatives/min ; message d'erreur identique et durée constante (hash factice) contre l'énumération des comptes | `test_forged_and_expired_tokens_are_rejected`, `test_login_brute_force_is_rate_limited`, `test_wrong_password_and_unknown_email_give_same_error` |
| **API3** Autorisation au niveau des propriétés | `response_model` en liste blanche : `password_hash`, `author_id` et `author_hash` ne sortent jamais. En entrée, `extra="forbid"` empêche l'affectation de masse (ex. imposer son `user_id`). | `test_reviews_never_expose_author`, `test_user_creation_rejects_weak_password_and_extra_fields` |
| **API4** Consommation illimitée des ressources | 120 requêtes/min par IP ; pagination obligatoire (100 maximum) ; longueur des textes bornée ; requêtes SQL coupées au-delà de 5 s (`statement_timeout`) ; pool de 10 connexions maximum | `test_pagination_is_bounded` |
| **API5** Autorisation au niveau fonction | dépendance `require_role` sur chaque routeur : avis et statistiques réservés au rôle `analyst`, comptes au rôle `admin` | `test_role_permissions` (8 cas) |
| **API6** Accès sans restriction aux flux sensibles | seul flux sensible : la connexion, limitée à 5 tentatives/min | `test_login_brute_force_is_rate_limited` |
| **API7** Falsification de requête côté serveur (SSRF) | l'API ne télécharge aucune URL fournie par un client | (sans objet) |
| **API8** Mauvaise configuration de sécurité | en-têtes `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, `Strict-Transport-Security`, `Cache-Control: no-store` ; CORS fermé par défaut ; aucune trace d'erreur renvoyée au client ; conteneur non-root ; rôle PostgreSQL à moindre privilège ; tris en liste fermée, requêtes paramétrées | `test_security_headers`, `test_injection_attempts_are_rejected`, `test_like_wildcards_are_literal` |
| **API9** Mauvaise gestion de l'inventaire | API versionnée (`/api/v1`) ; toutes les routes documentées dans OpenAPI ; spécification versionnée dans Git | `test_openapi_documents_all_routes_and_security` |
| **API10** Consommation non sûre d'API tierces | les données issues de Steam sont validées, nettoyées (C3) et contraintes par le schéma SQL avant d'être servies | contraintes `CHECK` du MPD |

**Déploiement en production :** l'API doit être placée derrière un proxy inverse
HTTPS (Nginx, Traefik ou Caddy). L'en-tête `Strict-Transport-Security` oblige
ensuite les navigateurs à toujours utiliser HTTPS.

## 6. Accès aux données

| Accès | Pour qui | Moyen |
|---|---|---|
| **API REST** (recommandé) | consultation, application, modèle IA | HTTP + JWT, voir ci-dessus |
| **Accès direct PostgreSQL**, lecture seule | équipe data (analyses lourdes, entraînement) | rôle `gamescope_analyst`, voir le [README principal](../README.md#accès-à-la-base) |

Côté serveur, l'API se connecte avec le rôle **`gamescope_api`** : lecture de toutes
les données métier, écriture uniquement dans `api_user`, aucun accès à `rgpd_log`. Les
identifiants viennent du `.env` et ne sont jamais écrits dans le code.

## 7. Supervision

| Outil | Rôle |
|---|---|
| `GET /health` | vérifie que l'API répond et que la base est joignable (`503` sinon) |
| `HEALTHCHECK` Docker | redémarrage de l'état « unhealthy » visible dans `docker ps` |
| **Uptime Kuma** (http://localhost:3001) | interroge `/health` toutes les 60 s, historique de disponibilité, alertes (e-mail, Discord…) |
| Journaux | `docker logs gamescope_api` : requêtes et erreurs détaillées |

Configuration d'Uptime Kuma, la première fois :
1. Créer le compte administrateur d'Uptime Kuma.
2. *Add New Monitor* → type **HTTP(s)**, URL `http://api:8000/health`, intervalle 60 s.
3. *Notifications* → ajouter un canal d'alerte (e-mail SMTP, Discord…).

## 8. Tests

```bash
python -m pytest tests/test_api.py -v
```

28 tests sur la vraie base : authentification, rôles, jetons falsifiés, brute force,
injections, pagination, exposition des données, en-têtes de sécurité, OpenAPI. Les
comptes de test sont créés au début et supprimés à la fin.
