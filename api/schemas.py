"""Schémas Pydantic : validation des entrées et forme exacte des réponses.

Les modèles de réponse sont des LISTES BLANCHES : seul un champ déclaré ici peut
sortir de l'API (OWASP API3, exposition excessive de données). Ainsi
`password_hash` et `author_id` ne sont jamais renvoyés.
"""
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(description="Nombre total de résultats pour ces filtres")
    page: int
    size: int
    pages: int


# --- Authentification et comptes ---------------------------------------------
class Role(str, Enum):
    reader = "reader"      # catalogue des jeux et ventes
    analyst = "analyst"    # + avis et statistiques
    admin = "admin"        # + gestion des comptes


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Durée de validité en secondes")


class UserOut(ORMModel):
    user_id: int
    email: str
    role: Role
    created_at: datetime
    last_login_at: datetime | None


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")  # aucun champ inattendu (affectation de masse)
    email: EmailStr
    password: str = Field(min_length=12, description="12 caractères minimum")
    role: Role = Role.reader

    @field_validator("password")
    @classmethod
    def bcrypt_limit(cls, value: str) -> str:
        if len(value.encode()) > 72:
            raise ValueError("72 octets maximum (limite de bcrypt)")
        return value


# --- Jeux --------------------------------------------------------------------
class GameSort(str, Enum):
    """Tris autorisés : liste fermée, jamais de nom de colonne venant du client."""
    name = "name"
    release_date = "release_date"
    release_date_desc = "-release_date"
    metacritic_desc = "-metacritic_score"
    pct_positive_desc = "-pct_positive"
    owners_desc = "-owners_max"


class GameSummary(ORMModel):
    app_id: int
    name: str
    release_date: date
    price_eur: Decimal | None
    is_free: bool
    metacritic_score: int | None
    pct_positive: Decimal | None
    owners_min: int | None
    owners_max: int | None


class Stats2021Out(ORMModel):
    nb_reviews: int
    pct_recommended: Decimal | None
    median_playtime_min: int | None
    nb_languages: int | None


class GameDetail(GameSummary):
    price_initial_eur: Decimal | None
    discount_pct: int | None
    required_age: int | None
    positive_reviews: int | None
    negative_reviews: int | None
    recent_review_pct: int | None
    recent_review_count: int | None
    recent_review_desc: str | None
    avg_playtime_min: int | None
    median_playtime_min: int | None
    peak_ccu: int | None
    dlc_count: int | None
    achievements: int | None
    recommendations: int | None
    languages_count: int | None
    developers: list[str]
    publishers: list[str]
    genres: list[str]
    categories: list[str]
    tags: list[str] = Field(description="Tags joueurs, du plus voté au moins voté")
    operating_systems: list[str]
    stats_2021: Stats2021Out | None
    updated_at: datetime


class SaleOut(ORMModel):
    platform: str
    publisher: str | None
    vgsales_name: str
    release_year: int | None
    sales_na_units: int
    sales_eu_units: int
    sales_jp_units: int
    sales_other_units: int
    sales_global_units: int


class ReviewOut(ORMModel):
    """Avis SANS identifiant d'auteur, même pseudonymisé (minimisation RGPD)."""
    review_id: int
    language: str | None
    review_text: str
    recommended: bool
    votes_helpful: int | None
    author_playtime_min: int | None
    created_at: datetime
    source: str


# --- Référentiels et statistiques -------------------------------------------
class NamedCount(BaseModel):
    name: str
    nb_games: int


class GenreStats(BaseModel):
    genre: str
    nb_games: int
    avg_metacritic: Decimal | None
    avg_pct_positive: Decimal | None
    avg_price_eur: Decimal | None
    pct_free: Decimal


class PlatformSales(BaseModel):
    platform: str
    nb_games: int
    total_units: int
