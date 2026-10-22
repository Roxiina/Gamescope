"""Référentiels (valeurs possibles des filtres) et statistiques agrégées."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import Game, GameTag, Genre, Platform, Sale, Tag, game_genre
from api.schemas import GenreStats, NamedCount, PlatformSales, Role
from api.security import require_role

router = APIRouter(tags=["Référentiels"], dependencies=[Depends(require_role(Role.reader))])
stats_router = APIRouter(prefix="/stats", tags=["Statistiques"],
                         dependencies=[Depends(require_role(Role.analyst))])


@router.get("/genres", response_model=list[NamedCount], summary="Genres et nombre de jeux")
def list_genres(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Genre.name, func.count().label("nb_games"))
        .join(game_genre, game_genre.c.genre_id == Genre.genre_id)
        .group_by(Genre.name).order_by(func.count().desc()))
    return [NamedCount(name=name, nb_games=n) for name, n in rows]


@router.get("/tags", response_model=list[NamedCount], summary="Tags joueurs les plus utilisés")
def list_tags(db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=500)):
    rows = db.execute(
        select(Tag.name, func.count().label("nb_games"))
        .join(GameTag, GameTag.tag_id == Tag.tag_id)
        .group_by(Tag.name).order_by(func.count().desc()).limit(limit))
    return [NamedCount(name=name, nb_games=n) for name, n in rows]


@router.get("/platforms", response_model=list[NamedCount], summary="Plateformes des ventes")
def list_platforms(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Platform.name, func.count(func.distinct(Sale.app_id)))
        .join(Sale, Sale.platform_id == Platform.platform_id)
        .group_by(Platform.name).order_by(func.count(func.distinct(Sale.app_id)).desc()))
    return [NamedCount(name=name, nb_games=n) for name, n in rows]


@stats_router.get("/genres", response_model=list[GenreStats], summary="Indicateurs par genre")
def genre_stats(db: Session = Depends(get_db)):
    """Note Metacritic moyenne, % d'avis positifs, prix moyen et part de free-to-play par genre."""
    rows = db.execute(
        select(
            Genre.name,
            func.count().label("nb_games"),
            func.round(func.avg(Game.metacritic_score), 1),
            func.round(func.avg(Game.pct_positive), 1),
            func.round(func.avg(Game.price_eur), 2),
            func.round(func.avg(cast(Game.is_free, Integer)) * 100, 1),
        )
        .join(game_genre, game_genre.c.app_id == Game.app_id)
        .join(Genre, Genre.genre_id == game_genre.c.genre_id)
        .group_by(Genre.name).order_by(func.count().desc()))
    return [GenreStats(genre=g, nb_games=n, avg_metacritic=m, avg_pct_positive=p,
                       avg_price_eur=price, pct_free=free) for g, n, m, p, price, free in rows]


@stats_router.get("/sales-by-platform", response_model=list[PlatformSales],
                  summary="Ventes cumulées par plateforme")
def sales_by_platform(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Platform.name, func.count(func.distinct(Sale.app_id)), func.sum(Sale.sales_global_units))
        .join(Sale, Sale.platform_id == Platform.platform_id)
        .group_by(Platform.name).order_by(func.sum(Sale.sales_global_units).desc()))
    return [PlatformSales(platform=p, nb_games=n, total_units=t) for p, n, t in rows]
