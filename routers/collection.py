from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import db.cards as cards_db
import db.collection as collection_db

from services.collection_import import import_collection, is_basic_land

router = APIRouter(prefix="/collection", tags=["collection"])


class ImportCollectionRequest(BaseModel):
    cards: str


class AddCardRequest(BaseModel):
    scryfall_id: str
    quantity: int = Field(default=1, ge=1, le=999)


class SetQuantityRequest(BaseModel):
    quantity: int = Field(ge=0, le=999)


@router.get("")
def list_collection(search: str | None = Query(default=None)):
    # Pas de `ensure_images` ici : une collection complète, c'est des milliers
    # de cartes, donc des milliers de téléchargements déclenchés par un simple
    # affichage de tableau. Les images sont rapatriées quand une carte entre
    # dans un deck ou une liste d'achat.
    return {"cards": collection_db.list_all(search), "stats": collection_db.stats()}


@router.post("/import")
def import_bulk(payload: ImportCollectionRequest):
    if not payload.cards.strip():
        raise HTTPException(400, "La liste est vide")
    return import_collection(payload.cards)


@router.post("")
def add_card(payload: AddCardRequest):
    card = cards_db.get_by_scryfall_id(payload.scryfall_id)
    if not card:
        raise HTTPException(404, "Carte introuvable")
    if is_basic_land(card):
        raise HTTPException(
            400,
            "Les terrains de base ne sont pas suivis : ils sont considérés "
            "comme disponibles sans limite.",
        )
    collection_db.add([(str(card["oracle_id"]), card["scryfall_id"], payload.quantity)])
    return {"status": "ok"}


# `oracle_id` est typé UUID : une valeur mal formée devient un 422 de FastAPI
# au lieu d'une erreur Postgres remontée en 500.
@router.patch("/{oracle_id}")
def set_quantity(oracle_id: UUID, payload: SetQuantityRequest):
    if not collection_db.set_quantity(str(oracle_id), payload.quantity):
        raise HTTPException(404, "Carte absente de la collection")
    return {"status": "ok"}


@router.delete("/{oracle_id}", status_code=204)
def remove_card(oracle_id: UUID):
    if not collection_db.set_quantity(str(oracle_id), 0):
        raise HTTPException(404, "Carte absente de la collection")
