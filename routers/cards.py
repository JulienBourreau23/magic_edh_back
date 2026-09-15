from fastapi import APIRouter, Query

import db.cards as cards_db

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("/search")
def search_cards(q: str = Query(min_length=2)):
    return cards_db.search(q)
