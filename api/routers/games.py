"""Catalogue des jeux : recherche filtrée et paginée, fiche détaillée, ventes, avis."""
import math
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from api.database import get_db
from api.models import Game, GameTag, Genre, Language, Review, Sale, Tag
from api.schemas import GameDetail, GameSort, GameSummary, Page, ReviewOut, Role, SaleOut
from api.security import require_role

router = APIRouter(prefix="/games", tags=["Jeux"])

SORTS = {
    GameSort.name: Game.name.asc(),
    GameSort.release_date: Game.release_date.asc(),
    GameSort.release_date_desc: Game.release_date.desc(),
    GameSort.metacritic_desc: Game.metacritic_score.desc().nulls_last(),
    GameSort.pct_positive_desc: Game.pct_positive.desc().nulls_last(),
    GameSort.owners_desc: Game.owners_max.desc().nulls_last(),
}
NOT_FOUND = {404: {"description": "Jeu inexistant"}}
LIST_FIELDS = {"developers", "publishers", "genres", "categories", "operating_systems", "tags"}


def escape_like(text: str) -> str:
    """Les caractères % et _ saisis sont cherchés littéralement, pas comme jokers."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def paginate(db: Session, query, page: int, size: int) -> tuple[list, int]:
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    items = db.scalars(query.offset((page - 1) * size).limit(size)).unique().all()
    return items, total


def get_game_or_404(db: Session, app_id: int) -> Game:
    game = db.get(Game, app_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Aucun jeu avec l'app_id {app_id}")
    return game


@router.get("", response_model=Page[GameSummary], summary="Rechercher des jeux",
            dependencies=[Depends(require_role(Role.reader))])
def list_games(
    db: Session = Depends(get_db),
    q: str | None = Query(None, min_length=2, max_length=100, description="Recherche dans le nom"),
    genre: str | None = Query(None, max_length=50, examples=["RPG"]),
    tag: str | None = Query(None, max_length=50, examples=["Open World"]),
    min_metacritic: int | None = Query(None, ge=1, le=100),
    released_after: date | None = None,
    released_before: date | None = None,
    is_free: bool | None = None,
    sort: GameSort = GameSort.name,
    page: int = Query(1, ge=1, le=10_000),
    size: int = Query(20, ge=1, le=100, description="100 résultats maximum par page"),
):
    query = select(Game)
    if q:
        query = query.where(Game.name.ilike(f"%{escape_like(q)}%", escape="\\"))
    if genre:
        query = query.where(Game.genres.any(func.lower(Genre.name) == genre.lower()))
    if tag:
        query = query.where(Game.tag_links.any(GameTag.tag.has(func.lower(Tag.name) == tag.lower())))
    if min_metacritic is not None:
        query = query.where(Game.metacritic_score >= min_metacritic)
    if released_after:
        query = query.where(Game.release_date >= released_after)
    if released_before:
        query = query.where(Game.release_date <= released_before)
    if is_free is not None:
        query = query.where(Game.is_free.is_(is_free))
    query = query.order_by(SORTS[sort], Game.app_id)  # app_id : ordre stable entre les pages

    items, total = paginate(db, query, page, size)
    return Page(items=items, total=total, page=page, size=size, pages=math.ceil(total / size))


@router.get("/{app_id}", response_model=GameDetail, summary="Fiche détaillée d'un jeu",
            responses=NOT_FOUND, dependencies=[Depends(require_role(Role.reader))])
def get_game(app_id: int, db: Session = Depends(get_db)):
    game = db.scalar(select(Game).where(Game.app_id == app_id).options(
        selectinload(Game.developers), selectinload(Game.publishers),
        selectinload(Game.genres), selectinload(Game.categories),
        selectinload(Game.operating_systems), selectinload(Game.tag_links),
        selectinload(Game.stats_2021)))
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Aucun jeu avec l'app_id {app_id}")
    # Les relations n,n sont aplaties en listes de noms ; les tags gardent leur rang
    detail = {field: getattr(game, field) for field in GameDetail.model_fields if field not in LIST_FIELDS}
    detail.update({field: [item.name for item in getattr(game, field)] for field in LIST_FIELDS - {"tags"}})
    detail["tags"] = [link.tag.name for link in game.tag_links]
    return GameDetail.model_validate(detail, from_attributes=True)


@router.get("/{app_id}/sales", response_model=list[SaleOut], summary="Ventes par plateforme",
            responses=NOT_FOUND, dependencies=[Depends(require_role(Role.reader))])
def get_sales(app_id: int, db: Session = Depends(get_db)):
    get_game_or_404(db, app_id)
    sales = db.scalars(select(Sale).where(Sale.app_id == app_id)
                       .order_by(Sale.sales_global_units.desc())).all()
    return [SaleOut(platform=s.platform.name, publisher=s.publisher.name if s.publisher else None,
                    **{f: getattr(s, f) for f in SaleOut.model_fields if f not in ("platform", "publisher")})
            for s in sales]


@router.get("/{app_id}/reviews", response_model=Page[ReviewOut], summary="Avis des joueurs",
            responses={**NOT_FOUND, 403: {"description": "Rôle analyst requis"}},
            dependencies=[Depends(require_role(Role.analyst))])
def get_reviews(
    app_id: int,
    db: Session = Depends(get_db),
    language: str | None = Query(None, max_length=10, examples=["en"], description="Code BCP 47"),
    recommended: bool | None = None,
    page: int = Query(1, ge=1, le=10_000),
    size: int = Query(20, ge=1, le=100),
):
    """Avis pseudonymisés : aucun identifiant d'auteur n'est renvoyé. Réservé au rôle analyst."""
    get_game_or_404(db, app_id)
    query = select(Review).where(Review.app_id == app_id)
    if language:
        query = query.where(Review.language.has(Language.code == language))
    if recommended is not None:
        query = query.where(Review.recommended.is_(recommended))
    query = query.order_by(Review.votes_helpful.desc().nulls_last(), Review.review_id)
    items, total = paginate(db, query, page, size)
    return Page(
        items=[ReviewOut(language=r.language.code if r.language else None,
                         **{f: getattr(r, f) for f in ReviewOut.model_fields if f != "language"})
               for r in items],
        total=total, page=page, size=size, pages=math.ceil(total / size))
