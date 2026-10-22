"""Correspondance ORM (SQLAlchemy 2.0) des tables utilisées par l'API.

Le schéma est créé par database/init/01_schema.sql : ces classes ne font que
le décrire, l'API ne crée ni ne modifie aucune table.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Column, ForeignKey, Integer, SmallInteger, Table, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def link_table(name: str, column: str, target: str, id_type=Integer) -> Table:
    return Table(name, Base.metadata,
                 Column("app_id", Integer, ForeignKey("game.app_id"), primary_key=True),
                 Column(column, id_type, ForeignKey(f"{target}.{column}"), primary_key=True))


game_developer = link_table("game_developer", "developer_id", "developer")
game_publisher = link_table("game_publisher", "publisher_id", "publisher")
game_genre = link_table("game_genre", "genre_id", "genre", SmallInteger)
game_category = link_table("game_category", "category_id", "category", SmallInteger)
game_os = link_table("game_os", "os_id", "operating_system", SmallInteger)


class Developer(Base):
    __tablename__ = "developer"
    developer_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]


class Publisher(Base):
    __tablename__ = "publisher"
    publisher_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]


class Genre(Base):
    __tablename__ = "genre"
    genre_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str]


class Category(Base):
    __tablename__ = "category"
    category_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str]


class Tag(Base):
    __tablename__ = "tag"
    tag_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str]


class OperatingSystem(Base):
    __tablename__ = "operating_system"
    os_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str]


class GameTag(Base):
    """Association porteuse d'un attribut (rang du tag) : classe dédiée."""
    __tablename__ = "game_tag"
    app_id: Mapped[int] = mapped_column(ForeignKey("game.app_id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tag.tag_id"), primary_key=True)
    tag_rank: Mapped[int]
    tag: Mapped[Tag] = relationship(lazy="joined")


class GameReviewStats2021(Base):
    __tablename__ = "game_review_stats_2021"
    app_id: Mapped[int] = mapped_column(ForeignKey("game.app_id"), primary_key=True)
    nb_reviews: Mapped[int]
    pct_recommended: Mapped[Decimal | None]
    median_playtime_min: Mapped[int | None]
    nb_languages: Mapped[int | None]


class Game(Base):
    __tablename__ = "game"
    app_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    release_date: Mapped[date]
    price_eur: Mapped[Decimal | None]
    price_initial_eur: Mapped[Decimal | None]
    discount_pct: Mapped[int | None]
    is_free: Mapped[bool]
    required_age: Mapped[int | None]
    owners_min: Mapped[int | None]
    owners_max: Mapped[int | None]
    metacritic_score: Mapped[int | None]
    positive_reviews: Mapped[int | None]
    negative_reviews: Mapped[int | None]
    pct_positive: Mapped[Decimal | None]
    recent_review_pct: Mapped[int | None]
    recent_review_count: Mapped[int | None]
    recent_review_desc: Mapped[str | None]
    avg_playtime_min: Mapped[int | None]
    median_playtime_min: Mapped[int | None]
    peak_ccu: Mapped[int | None]
    dlc_count: Mapped[int | None]
    achievements: Mapped[int | None]
    recommendations: Mapped[int | None]
    languages_count: Mapped[int | None]
    updated_at: Mapped[datetime]

    developers: Mapped[list[Developer]] = relationship(secondary=game_developer)
    publishers: Mapped[list[Publisher]] = relationship(secondary=game_publisher)
    genres: Mapped[list[Genre]] = relationship(secondary=game_genre)
    categories: Mapped[list[Category]] = relationship(secondary=game_category)
    operating_systems: Mapped[list[OperatingSystem]] = relationship(secondary=game_os)
    tag_links: Mapped[list[GameTag]] = relationship(order_by=GameTag.tag_rank)
    stats_2021: Mapped[GameReviewStats2021 | None] = relationship()


class Language(Base):
    __tablename__ = "language"
    language_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str]


class Review(Base):
    __tablename__ = "review"
    review_id: Mapped[int] = mapped_column(primary_key=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("game.app_id"))
    author_id: Mapped[int]  # jamais exposé par l'API (minimisation RGPD)
    language_id: Mapped[int | None] = mapped_column(ForeignKey("language.language_id"))
    review_text: Mapped[str]
    recommended: Mapped[bool]
    votes_helpful: Mapped[int | None]
    author_playtime_min: Mapped[int | None]
    source: Mapped[str]
    created_at: Mapped[datetime]
    collected_at: Mapped[datetime]
    language: Mapped[Language | None] = relationship(lazy="joined")


class Platform(Base):
    __tablename__ = "platform"
    platform_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str]


class Sale(Base):
    __tablename__ = "sale"
    sale_id: Mapped[int] = mapped_column(primary_key=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("game.app_id"))
    platform_id: Mapped[int] = mapped_column(ForeignKey("platform.platform_id"))
    publisher_id: Mapped[int | None] = mapped_column(ForeignKey("publisher.publisher_id"))
    vgsales_name: Mapped[str]
    release_year: Mapped[int | None]
    vgsales_genre: Mapped[str | None]
    sales_na_units: Mapped[int]
    sales_eu_units: Mapped[int]
    sales_jp_units: Mapped[int]
    sales_other_units: Mapped[int]
    sales_global_units: Mapped[int]
    match_method: Mapped[str]
    platform: Mapped[Platform] = relationship(lazy="joined")
    publisher: Mapped[Publisher | None] = relationship(lazy="joined")


class ApiUser(Base):
    __tablename__ = "api_user"
    user_id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str]
    password_hash: Mapped[str]
    role: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_login_at: Mapped[datetime | None]
