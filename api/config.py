"""Configuration de l'API, lue depuis les variables d'environnement (.env).

L'API refuse de démarrer si un secret obligatoire manque ou est trop faible.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # Accès base : rôle dédié gamescope_api (lecture des données, gestion des comptes)
    db_host: str = Field("localhost", validation_alias="GAMESCOPE_DB_HOST")
    db_port: int = Field(5436, validation_alias="GAMESCOPE_DB_PORT")
    db_name: str = "gamescope"
    db_user: str = "gamescope_api"
    db_password: SecretStr = Field(validation_alias="GAMESCOPE_API_PASSWORD")
    # Une requête SQL plus longue est interrompue (protection contre l'épuisement des ressources)
    db_statement_timeout_ms: int = 5000

    # Jetons JWT : clé d'au moins 32 caractères (256 bits pour HS256)
    jwt_secret_key: SecretStr = Field(validation_alias="JWT_SECRET_KEY", min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(30, validation_alias="JWT_EXPIRE_MINUTES")

    # Limitation de débit par adresse IP
    rate_limit_default: str = Field("120/minute", validation_alias="RATE_LIMIT_DEFAULT")
    rate_limit_login: str = Field("5/minute", validation_alias="RATE_LIMIT_LOGIN")

    # Origines web autorisées (CORS), séparées par des virgules. Vide = aucune.
    cors_origins: str = Field("", validation_alias="CORS_ORIGINS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
