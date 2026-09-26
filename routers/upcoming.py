import httpx
from fastapi import APIRouter, HTTPException

import db.upcoming as upcoming_db
from services import upcoming as upcoming_service

router = APIRouter(prefix="/upcoming", tags=["upcoming"])


@router.get("")
def next_set():
    """
    La prochaine extension et ses cartes, face à la collection.

    Pas d'`ensure_images` : plusieurs centaines de visuels, même arbitrage que
    `/must-have` — le front retombe sur l'URL Scryfall en chargement paresseux.
    """
    try:
        sets = upcoming_service.fetch_sets()
    except httpx.HTTPError as error:
        raise HTTPException(502, f"Scryfall injoignable : {error}") from error

    release = upcoming_service.next_release(sets, upcoming_service.today_paris())
    if release is None:
        return {"release": None, "cards": []}

    codes = [s["code"] for s in release["sets"]]
    cards = upcoming_db.cards_of_sets(codes)
    prints = upcoming_db.prints_per_set(codes)
    for s in release["sets"]:
        # Même unité que `card_count` (impressions, variantes comprises) : un
        # écart signale des spoilers arrivés après le dernier sync Scryfall,
        # qu'on verrait sinon comme une extension simplement plus petite.
        s["prints_in_base"] = prints.get(s["code"], 0)
    return {"release": release, "cards": cards}
