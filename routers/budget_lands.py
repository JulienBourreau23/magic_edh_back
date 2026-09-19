from fastapi import APIRouter, HTTPException, Query

import db.cards as cards_db
import db.decks as decks_db
import db.lands as lands_db
import db.videos as videos_db
from services import land_cycles

router = APIRouter(prefix="/budget-lands", tags=["budget-lands"])

COLORS = set("WUBRG")


@router.get("")
def budget_lands(
    identity: str | None = Query(default=None, description="couleurs, ex. « BG »"),
    commander: str | None = Query(default=None, description="oracle_id d'un commandant"),
    deck: int | None = Query(default=None, description="id d'un deck, pour prendre son identité"),
    max_price: float = Query(default=2.0, gt=0),
    format: str = Query(default="commander", pattern="^(commander|duel)$"),
):
    """
    Les terrains non-basiques qui règlent une manabase, groupés par **cycle**.

    Une vidéo « terrains budget » ne conseille pas des cartes une par une : elle
    conseille des familles. Chaque cycle ne compte qu'une carte par paire de
    couleurs, donc la question « qu'est-ce qu'il me manque » a une réponse
    courte et exacte.

    Le plafond ne concerne que les achats : un terrain possédé reste affiché
    quel que soit son prix, comme partout dans le projet.
    """
    couleurs = _identity(identity, commander, deck)
    if len(couleurs) < 2:
        raise HTTPException(400, "Il faut au moins deux couleurs : un terrain dual n'a de sens "
                                 "que pour une paire.")

    lands = lands_db.dual_lands(sorted(couleurs), format)
    conseils = videos_db.mentions_by_key("cycle")

    groupes: list[dict] = []
    hors_cycle: list[dict] = []
    par_cycle: dict[str, list[dict]] = {}
    for land in lands:
        cle = land_cycles.classify(land)
        if cle:
            par_cycle.setdefault(cle, []).append(land)
        else:
            # Terrains utilitaires, arc-en-ciel, fetchlands : utiles, mais ils
            # ne forment pas une famille qu'on puisse conseiller d'un bloc.
            hors_cycle.append(land)

    for cycle in land_cycles.CYCLES:
        cartes = par_cycle.get(cycle["key"], [])
        if not cartes:
            continue
        abordables = [c for c in cartes
                      if c["owned_quantity"] or (c["price_eur"] is not None
                                                 and float(c["price_eur"]) <= max_price)]
        groupes.append({
            **{k: v for k, v in cycle.items() if k != "pattern" and k != "regex"},
            "cards": abordables,
            "owned": sum(1 for c in abordables if c["owned_quantity"]),
            "missing_cost_eur": round(sum(float(c["price_eur"] or 0) for c in abordables
                                          if not c["owned_quantity"]), 2),
            # Les vidéos qui recommandent ce cycle, avec le moment où elles en
            # parlent : le conseil éditorial se pose sur une donnée calculée.
            "videos": conseils.get(cycle["key"], []),
        })

    return {
        "identity": sorted(couleurs),
        "max_price_eur": max_price,
        "format": format,
        "cycles": groupes,
        "other_count": len(hors_cycle),
        "totals": {
            "cards": sum(len(g["cards"]) for g in groupes),
            "owned": sum(g["owned"] for g in groupes),
            "missing_cost_eur": round(sum(g["missing_cost_eur"] for g in groupes), 2),
        },
    }


def _identity(identity: str | None, commander: str | None, deck: int | None) -> set[str]:
    if identity:
        couleurs = {lettre.upper() for lettre in identity if lettre.upper() in COLORS}
        if not couleurs:
            raise HTTPException(400, "Identité de couleur illisible (attendu : WUBRG)")
        return couleurs
    if commander:
        carte = cards_db.get_cheapest_by_oracle_id(commander)
        if not carte:
            raise HTTPException(404, "Commandant introuvable")
        return set(carte["color_identity"])
    if deck:
        cartes = decks_db.get_deck_cards(deck)
        chef = next((c for c in cartes if c["is_commander"]), None)
        if not chef:
            raise HTTPException(404, "Deck sans commandant : impossible d'en déduire l'identité")
        return set(chef["color_identity"])
    raise HTTPException(400, "Donne une identité, un commandant ou un deck")
