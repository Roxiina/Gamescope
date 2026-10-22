"""Connexion à PostgreSQL avec le rôle gamescope_api (moindre privilège)."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from api.config import get_settings

settings = get_settings()

engine = create_engine(
    URL.create(
        "postgresql+psycopg2",
        username=settings.db_user,
        password=settings.db_password.get_secret_value(),
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
    ),
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,  # détecte les connexions coupées (redémarrage de la base)
    connect_args={"options": f"-c statement_timeout={settings.db_statement_timeout_ms}"},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Dépendance FastAPI : une session par requête, toujours refermée."""
    with SessionLocal() as session:
        yield session
