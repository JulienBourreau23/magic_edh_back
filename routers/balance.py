from fastapi import APIRouter, HTTPException, Query

import db.collection as collection_db
import db.decks as decks_db
import services.card_images as card_images
from services import balance as balance_service
from services import suggestions

router = APIRouter(prefix="/balance", tags=["balance"])


@router.get("")
def balance_decks(
    decks: str = Query(description=f"ids séparés par des virgules, {balance_service.MAX_DECKS} maximum"),
    max_price: float = Query(default=suggestions.DEFAULT_MAX_PRICE_EUR, gt=0),
    target_bracket: int | None = Query(default=None, ge=1, le=5),
):
    """
    Équilibrage d'un groupe de decks contre la collection. L'ordre des ids fixe
    la priorité d'attribution des exemplaires possédés.
    """
    try:
        deck_ids = [int(value) for value in decks.split(",") if value.strip()]
    except ValueError:
        raise HTTPException(400, "Liste d'ids invalide")

    if not deck_ids:
        raise HTTPException(400, "Sélectionne au moins un deck")
    if len(deck_ids) > balance_service.MAX_DECKS:
        raise HTTPException(400, f"{balance_service.MAX_DECKS} decks au maximum")
    if len(set(deck_ids)) != len(deck_ids):
        raise HTTPException(400, "Un même deck est sélectionné plusieurs fois")

    entries = []
    for deck_id in deck_ids:
        deck = decks_db.get_deck(deck_id)
        if not deck:
            raise HTTPException(404, f"Deck {deck_id} introuvable")
        entries.append((deck, decks_db.get_deck_cards(deck_id)))

    result = balance_service.balance(entries, collection_db.quantities(), max_price, target_bracket)
    card_images.ensure_images(result.get("shopping_list", []))
    return result
