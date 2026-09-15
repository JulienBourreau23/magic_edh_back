from fastapi import APIRouter, Query

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
