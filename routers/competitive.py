"""
routers/competitive.py — construction d'un deck compétitif, par étapes.

Une étape par appel, dans l'ordre où l'interface les pose : le commandant, le
format, l'archétype, puis le deck. Chaque étape ne dépend que des précédentes,
ce qui permet de revenir en arrière sans rien reconstruire.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

import db.cards as cards_db
import db.commanders as commanders_db
import db.themes as themes_db
import services.card_images as card_images
from services import competitive
from services.suggestions import DEFAULT_MAX_PRICE_EUR

router = APIRouter(prefix="/competitive", tags=["competitive"])

FORMATS = tuple(themes_db.LEGALITY_COLUMNS)


def _check_format(format: str) -> str:
    if format not in FORMATS:
        raise HTTPException(400, f"Format inconnu : {', '.join(FORMATS)}")
    return format


def _commander(oracle_id: UUID) -> dict:
    card = cards_db.get_cheapest_by_oracle_id(str(oracle_id))
    if not card:
        raise HTTPException(404, "Commandant introuvable")
    return card


@router.get("/commanders")
def list_commanders():
    """Étape 1 : les commandants présents dans la collection."""
    commanders = commanders_db.owned_commanders()
    card_images.ensure_images(commanders)
    return {"commanders": commanders}


@router.get("/themes")
def list_themes(commander: UUID, format: str = Query(default="commander")):
    """
    Étape 3 : les archétypes du commandant, classés par ce qu'en couvre la
    collection — « celui que je peux monter » avant « celui qui est le plus
    joué ».
    """
    _check_format(format)
    oracle_id = str(commander)
    themes = themes_db.themes_for(oracle_id)
    if not themes:
        return {"themes": [], "error": "Aucun archétype connu pour ce commandant : lance "
                                       "`python scripts/sync_edhrec.py`."}

    coverage = themes_db.theme_coverage(oracle_id, format)
    enriched = []
    for theme in themes:
        stats = coverage.get(theme["slug"], {})
        cards, owned = stats.get("cards", 0), stats.get("owned", 0)
        enriched.append({
            **theme,
            "cards_legal": cards,
            "cards_owned": owned,
            # Part du vivier de l'archétype déjà en collection : le seul
            # chiffre qui dise ce que coûterait de le monter.
            "coverage": round(owned / cards, 3) if cards else 0.0,
        })
    enriched.sort(key=lambda theme: (-theme["coverage"], -theme["deck_count"]))
    return {"themes": enriched}


@router.get("/build")
def build(commander: UUID, theme: str, format: str = Query(default="commander"),
          max_price: float = Query(default=DEFAULT_MAX_PRICE_EUR, gt=0)):
    """Étape 4 : le deck, bâti sur la collection, achats proposés à côté."""
    _check_format(format)
    result = competitive.build(_commander(commander), theme, format, max_price)
    if "error" in result:
        raise HTTPException(400, result["error"])

    card_images.ensure_images(result["cards"])
    card_images.ensure_images(result["lands"]["nonbasic"])
    card_images.ensure_images([item["buy"] for item in result["upgrades"]])
    return result
