"""
routers/wishlist.py — la liste de recherche : ce qu'on envisage d'acheter.

Le point qui la rend utile est `POST /{oracle_id}/acquire` : l'achat fait, la
carte rejoint la collection en un geste. Sans ça, il faudrait la retirer d'un
côté et la ressaisir de l'autre, et la collection finirait fausse — or c'est
elle qui pilote toutes les listes d'achats.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import db.cards as cards_db
import db.wishlist as wishlist_db
import services.card_images as card_images
from services.collection_import import is_basic_land
from services.wishlist_import import import_wishlist

router = APIRouter(prefix="/wishlist", tags=["wishlist"])


class AddCardRequest(BaseModel):
    scryfall_id: str
    quantity: int = Field(default=1, ge=1, le=999)
    note: str | None = None


class ImportRequest(BaseModel):
    cards: str
    note: str | None = None


class SetQuantityRequest(BaseModel):
    quantity: int = Field(ge=0, le=999)


@router.get("")
def list_wishlist():
    cards = wishlist_db.list_all()
    # Contrairement à la collection, la liste de recherche reste courte : on
    # peut rapatrier les visuels sans risquer des milliers de téléchargements.
    card_images.ensure_images(cards)
    return {"cards": cards, "stats": wishlist_db.stats()}


@router.post("")
def add_card(payload: AddCardRequest):
    card = cards_db.get_by_scryfall_id(payload.scryfall_id)
    if not card:
        raise HTTPException(404, "Carte introuvable")
    if is_basic_land(card):
        raise HTTPException(
            400,
            "Les terrains de base sont considérés comme disponibles sans limite : "
            "ils ne se cherchent pas.",
        )
    wishlist_db.add([(str(card["oracle_id"]), card["scryfall_id"],
                      payload.quantity, payload.note)])
    return {"status": "ok"}


@router.post("/import")
def import_bulk(payload: ImportRequest):
    if not payload.cards.strip():
        raise HTTPException(400, "La liste est vide")
    return import_wishlist(payload.cards, payload.note)


@router.patch("/{oracle_id}")
def set_quantity(oracle_id: UUID, payload: SetQuantityRequest):
    if not wishlist_db.set_quantity(str(oracle_id), payload.quantity):
        raise HTTPException(404, "Carte absente de la liste de recherche")
    return {"status": "ok"}


@router.delete("/{oracle_id}", status_code=204)
def remove_card(oracle_id: UUID):
    if not wishlist_db.set_quantity(str(oracle_id), 0):
        raise HTTPException(404, "Carte absente de la liste de recherche")


@router.post("/{oracle_id}/acquire")
def acquire(oracle_id: UUID,
            quantity: int | None = Query(default=None, ge=1, le=999,
                                         description="acquérir une partie seulement")):
    """
    L'achat est fait : la carte passe en collection. Les deux écritures sont
    dans la même transaction, sinon une coupure entre les deux la perdrait des
    deux côtés — et la collection pilote les achats, donc l'erreur se paierait.
    """
    result = wishlist_db.acquire(str(oracle_id), quantity)
    if result is None:
        raise HTTPException(404, "Carte absente de la liste de recherche")
    return result
