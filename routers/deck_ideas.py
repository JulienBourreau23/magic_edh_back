from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

import services.card_images as card_images
from services import deck_ideas as deck_ideas_service
from services.suggestions import DEFAULT_MAX_PRICE_EUR

router = APIRouter(prefix="/deck-ideas", tags=["deck-ideas"])


@router.get("")
def list_deck_ideas(max_price: float = Query(default=DEFAULT_MAX_PRICE_EUR, gt=0)):
    """Quels decks monter avec les commandants possédés, du moins cher au plus cher."""
    result = deck_ideas_service.deck_ideas(max_price)
    card_images.ensure_images([idea["commander"] for idea in result["ideas"]])
    return result


@router.get("/{commander_oracle_id}")
def deck_idea_detail(commander_oracle_id: UUID,
                     max_price: float = Query(default=DEFAULT_MAX_PRICE_EUR, gt=0),
                     format: str = Query(default="commander", pattern="^(commander|duel)$")):
    """
    La decklist proposée pour un commandant, avec le vivier de remplaçants
    déjà possédés — pour essayer l'archétype avant d'acheter.

    `ensure_images` porte sur le noyau seulement : c'est lui qu'on regarde
    carte par carte. Le vivier, lui, peut compter plusieurs centaines de
    lignes dont on n'affichera qu'une poignée, et les rapatrier toutes
    coûterait une attente pour rien.
    """
    detail = deck_ideas_service.deck_idea_detail(str(commander_oracle_id), max_price, format)
    if detail is None:
        raise HTTPException(404, "Ce commandant n'est pas dans la collection")
    card_images.ensure_images(detail["core"])
    return detail
