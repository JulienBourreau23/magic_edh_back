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
    """
    Étape 1 : les commandants de la collection, **classés par ce qu'on peut en
    tirer tout de suite**, avec l'archétype qui donne ce résultat.

    Le critère n'est pas « combien de cartes de la liste j'ai » : une pièce
    maîtresse jouée dans 80 % des decks ne vaut pas une carte de niche jouée
    dans 5 %. On somme donc les taux d'inclusion des 63 meilleures cartes
    possédées — le deck qu'on jouerait — et c'est ce total qui classe.

    Ce n'est pas un classement de puissance : un commandant très fort mais dont
    on ne possède aucune pièce n'aidera pas ce soir. Le nombre de decks
    recensés est montré à côté pour que le choix reste éclairé.

    La couverture est calculée sur la banlist multijoueur, la plus large : le
    format n'est choisi qu'à l'étape suivante, et la banlist Duel retire les
    mêmes quelques dizaines de cartes à tout le monde — elle ne change pas
    l'ordre.
    """
    commanders = commanders_db.owned_commanders()
    best = themes_db.best_theme_by_commander("commander")

    enriched = []
    for commander in commanders:
        theme = best.get(str(commander["oracle_id"]))
        enriched.append({
            **commander,
            "best_theme": {
                "slug": theme["theme_slug"],
                "label": theme["label"],
                # Poids de consensus des 63 meilleures cartes possédées : c'est
                # lui qui classe, d'où son affichage — un tri sur un nombre
                # invisible est un tri qu'on ne peut pas contester.
                "consensus": round(float(theme["reachable"] or 0), 1),
                "cards_usable": theme["owned_cards"],
                # Part de l'optimum de cet archétype-là. À lire ensemble : 99 %
                # d'une référence molle vaut moins que 93 % d'une référence forte.
                "score": round(float(theme["score"] or 0), 3),
                "deck_count": theme["deck_count"],
            } if theme else None,
        })

    # Sans archétype connu (synchronisation EDHREC jamais lancée), le
    # commandant passe en fin de liste plutôt que de disparaître.
    enriched.sort(key=lambda entry: (
        -(entry["best_theme"]["consensus"] if entry["best_theme"] else -1),
        entry["name"],
    ))
    card_images.ensure_images(enriched)
    return {"commanders": enriched}


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
