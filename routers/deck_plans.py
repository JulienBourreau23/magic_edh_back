from fastapi import APIRouter, HTTPException, Query

import db.collection as collection_db
import db.commanders as commanders_db
import services.card_images as card_images
from services import deck_plans as deck_plans_service
from services.suggestions import DEFAULT_MAX_PRICE_EUR

router = APIRouter(prefix="/deck-plans", tags=["deck-plans"])


@router.get("")
def build_deck_plans(
    max_price: float = Query(default=DEFAULT_MAX_PRICE_EUR, gt=0),
    target_bracket: int | None = Query(default=None, ge=1, le=5),
    commanders: str | None = Query(
        default=None,
        description="oracle_id séparés par des virgules pour imposer la sélection ; "
                    "sans ça, le meilleur groupe est choisi automatiquement",
    ),
):
    """
    Compare les decks montables derrière chaque commandant possédé et renvoie le
    meilleur groupe de quatre : équilibré d'abord, le moins cher ensuite.
    """
    chosen = [value.strip() for value in commanders.split(",") if value.strip()] if commanders else None
    if chosen:
        if len(chosen) > deck_plans_service.DECKS_TO_BUILD:
            raise HTTPException(400, f"{deck_plans_service.DECKS_TO_BUILD} decks au maximum")
        if len(set(chosen)) != len(chosen):
            raise HTTPException(400, "Un même commandant est sélectionné plusieurs fois")

    owned = commanders_db.owned_commanders()
    pools = commanders_db.recommendation_pool([str(c["oracle_id"]) for c in owned])
    result = deck_plans_service.plan_decks(
        owned, pools, collection_db.quantities(), max_price, target_bracket, chosen
    )

    selection = result.get("selection")
    if selection:
        card_images.ensure_images(selection["shopping_list"])
        card_images.ensure_images([plan["commander"] for plan in selection["plans"]])
    return result
