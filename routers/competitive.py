"""
routers/competitive.py — construction d'un deck compétitif, par étapes.

Une étape par appel, dans l'ordre où l'interface les pose : le format,
l'archétype (facultatif), le commandant, l'archétype à nouveau si on ne l'a pas
choisi, puis le deck. Chaque étape ne dépend que des précédentes, ce qui permet
de revenir en arrière sans rien reconstruire.

L'archétype peut donc se choisir **avant ou après** le commandant, et c'est
délibéré : on arrive sur cette page soit avec un commandant en tête, soit avec
une stratégie. Dans les deux cas la mesure est la même (`themes_db.theme_scores`),
seule change la colonne qu'on lit.
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


@router.get("/archetypes")
def list_archetypes(format: str = Query(default="commander", pattern="^(commander|duel)$")):
    """
    Étape 2, **facultative** : partir d'une stratégie plutôt que d'un commandant.

    On peut la sauter — c'est le chemin d'origine, et rien n'oblige à savoir ce
    qu'on veut jouer avant d'avoir vu ce qu'on peut monter. Elle sert au cas
    inverse : « je veux monter du superfriends, qui ai-je pour ça ».

    La liste ne contient que des archétypes montables avec la collection : ce
    sont ceux des commandants possédés, les seuls dont on sache ce qu'ils
    coûteraient.
    """
    commanders = commanders_db.owned_commanders(format)
    return {"archetypes": competitive.archetypes(commanders, themes_db.theme_scores(format))}


@router.get("/commanders")
def list_commanders(format: str = Query(default="commander", pattern="^(commander|duel)$"),
                    theme: str | None = Query(default=None)):
    """
    Étape 3 : les commandants de la collection, **classés par ce qu'on peut en
    tirer tout de suite**, avec l'archétype qui donne ce résultat.

    Le critère n'est pas « combien de cartes de la liste j'ai » : une pièce
    maîtresse jouée dans 80 % des decks ne vaut pas une carte de niche jouée
    dans 5 %. On somme donc les taux d'inclusion des 63 meilleures cartes
    possédées — le deck qu'on jouerait — et c'est ce total qui classe.

    Ce n'est pas un classement de puissance : un commandant très fort mais dont
    on ne possède aucune pièce n'aidera pas ce soir. Le nombre de decks
    recensés est montré à côté pour que le choix reste éclairé.

    `theme` restreint la liste aux commandants qui jouent cet archétype **et
    bascule le classement dessus**. Les deux vont ensemble : classer sur le
    meilleur archétype de chacun après avoir demandé une stratégie précise
    donnerait un ordre qui ne répond pas à la question, sans rien dire.
    """
    commanders = commanders_db.owned_commanders(format)
    scores = themes_db.theme_scores(format)
    enriched = competitive.rank_commanders(commanders, scores, theme)
    card_images.ensure_images(enriched)
    return {"commanders": enriched, "theme": theme}


@router.get("/themes")
def list_themes(commander: UUID, format: str = Query(default="commander")):
    """
    Étape 4 : les archétypes du commandant, classés par ce qu'en couvre la
    collection — « celui que je peux monter » avant « celui qui est le plus
    joué ».

    Reste appelée même quand l'archétype a été choisi à l'étape 2 : la liste
    dit alors ce que *cet* commandant sait faire d'autre, et permet d'en
    changer sans repartir de zéro.
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
    """Étape 5 : le deck, bâti sur la collection, achats proposés à côté."""
    _check_format(format)
    result = competitive.build(_commander(commander), theme, format, max_price)
    if "error" in result:
        raise HTTPException(400, result["error"])

    card_images.ensure_images(result["cards"])
    card_images.ensure_images(result["lands"]["nonbasic"])
    card_images.ensure_images([item["buy"] for item in result["upgrades"]])
    return result
