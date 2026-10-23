"""API REST GameScope : mise à disposition du jeu de données (C5).

Lancement :
    uvicorn api.main:app --port 8000
Documentation interactive : http://localhost:8000/docs (OpenAPI : /openapi.json)
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from api.config import get_settings
from api.database import engine
from api.limiter import limiter
from api.routers import auth, catalog, games, users

log = logging.getLogger("api")
settings = get_settings()

DESCRIPTION = """
Données réelles sur **1 982 jeux Steam** : fiches, tags joueurs, avis pseudonymisés,
ventes par plateforme. Collectées depuis 6 sources (API Steam et SteamSpy, scraping,
fichier vgsales, base partenaire, data lake Spark).

## Authentification

1. `POST /api/v1/auth/token` avec votre e-mail (`username`) et votre mot de passe
2. Utiliser le jeton reçu dans l'en-tête `Authorization: Bearer <jeton>`
   (bouton **Authorize** ci-dessus). Le jeton est valable 30 minutes.

## Rôles

| Rôle | Accès |
|---|---|
| `reader` | jeux, ventes, référentiels |
| `analyst` | + avis des joueurs, statistiques |
| `admin` | + gestion des comptes |

## Limites

120 requêtes par minute et par adresse IP (5 pour la connexion), 100 résultats
maximum par page.
"""

app = FastAPI(
    title="GameScope API",
    version="1.0.0",
    description=DESCRIPTION,
    contact={"name": "Projet GameScope", "url": "https://github.com/Roxiina/Gamescope"},
    openapi_tags=[
        {"name": "Authentification", "description": "Obtention d'un jeton JWT"},
        {"name": "Jeux", "description": "Catalogue, fiches, ventes et avis"},
        {"name": "Référentiels", "description": "Valeurs possibles des filtres"},
        {"name": "Statistiques", "description": "Indicateurs agrégés (rôle analyst)"},
        {"name": "Comptes (admin)", "description": "Gestion des utilisateurs (rôle admin)"},
        {"name": "Supervision", "description": "État du service"},
    ],
)

# --- Limitation de débit (OWASP API4) -----------------------------------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# --- CORS : aucune origine web autorisée par défaut (OWASP API8) ---------------
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["Authorization", "Content-Type"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """En-têtes de sécurité HTTP (OWASP API8 : mauvaise configuration de sécurité)."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store"  # les réponses authentifiées ne sont pas mises en cache
    if not request.url.path.startswith(("/docs", "/redoc")):  # Swagger UI charge des scripts externes
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    """Aucune trace technique renvoyée au client : elle est journalisée côté serveur."""
    log.exception("Erreur non gérée sur %s %s", request.method, request.url.path)
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={"detail": "Erreur interne du serveur"})


API_PREFIX = "/api/v1"  # version dans l'URL : évolutions sans casser les clients (OWASP API9)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(games.router, prefix=API_PREFIX)
app.include_router(catalog.router, prefix=API_PREFIX)
app.include_router(catalog.stats_router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)


@app.get("/health", tags=["Supervision"], summary="État du service")
@limiter.exempt
def health():
    """Vérifie que l'API répond et que la base est joignable (sans authentification)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception:
        log.exception("Base de données injoignable")
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unreachable"})
