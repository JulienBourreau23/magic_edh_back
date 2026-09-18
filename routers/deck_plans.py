import logging
import time

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import db.cards as cards_db
import db.collection as collection_db
import db.decks as decks_db
import db.commanders as commanders_db
import db.wishlist as wishlist_db
import services.card_images as card_images
from services import combos
from services import deck_plans as deck_plans_service
from services.suggestions import DEFAULT_MAX_PRICE_EUR

router = APIRouter(prefix="/deck-plans", tags=["deck-plans"])
# Le logger d'uvicorn, et non celui du module : uvicorn configure ses propres
# gestionnaires, et une ligne émise ailleurs remonte à la racine, qui est en
# WARNING par défaut — elle n'apparaîtrait donc jamais dans journalctl.
logger = logging.getLogger("uvicorn.error")


def _available(reserve_existing_decks: bool) -> dict[str, int]:
    """
    Ce qui est réellement disponible pour monter de nouveaux decks.

    La règle « un exemplaire dans un seul deck à la fois » était appliquée entre
    les quatre decks du plan, mais pas face aux decks déjà enregistrés : sur une
    collection alimentée par des decks montés, le plan reproposait donc des
    cartes physiquement rangées ailleurs.
    """
    owned = collection_db.quantities()
    if not reserve_existing_decks:
        return owned
    return deck_plans_service.free_copies(owned, decks_db.committed_quantities())


class CreateDecksRequest(BaseModel):
    commanders: list[str] = Field(min_length=1, max_length=deck_plans_service.DECKS_TO_BUILD)
    max_price: float = Field(default=DEFAULT_MAX_PRICE_EUR, gt=0)
    target_bracket: int | None = Field(default=None, ge=1, le=5)
    owned_only: bool = False
    reserve_existing_decks: bool = False


@router.get("")
def build_deck_plans(
    max_price: float = Query(default=DEFAULT_MAX_PRICE_EUR, gt=0),
    target_bracket: int | None = Query(default=None, ge=1, le=5),
    commanders: str | None = Query(
        default=None,
        description="oracle_id séparés par des virgules pour imposer la sélection ; "
                    "sans ça, le meilleur groupe est choisi automatiquement",
    ),
    owned_only: bool = Query(
        default=False,
        description="ne retenir que des cartes déjà possédées : quatre decks montables "
                    "ce soir, sans aucun achat",
    ),
    reserve_existing_decks: bool = Query(
        default=False,
        description="les decks déjà enregistrés gardent leurs cartes. Faux par défaut : "
                    "monter quatre decks équilibrés, c'est justement rebattre les cartes "
                    "de ceux qu'on a déjà",
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
    if owned_only:
        # Une requête pour toute la collection, l'identité de couleur se
        # vérifiant ensuite en mémoire — voir `commanders_db.owned_cards`.
        pools = deck_plans_service.with_owned_cards(pools, owned, commanders_db.owned_cards())

    # Le catalogue de combos est chargé **une fois** pour tout le vivier : cette
    # page construit des milliers de decks, et une requête par deck faisait
    # dépasser le plafond de 100 s de Cloudflare — la page renvoyait alors une
    # simple erreur réseau.
    universe = {str(card["oracle_id"]) for pool in pools.values() for card in pool}
    universe.update(str(commander["oracle_id"]) for commander in owned)

    started = time.monotonic()
    result = deck_plans_service.plan_decks(
        owned, pools, _available(reserve_existing_decks), max_price, target_bracket, chosen,
        find_combos=combos.matcher_for(universe), owned_only=owned_only,
    )
    result["reserve_existing_decks"] = reserve_existing_decks
    # Tracé dans journalctl : c'est la seule façon de voir venir un dépassement
    # du plafond de Cloudflare, qui coupe sans rien laisser dans la réponse.
    logger.info("deck-plans : %d commandants en %.1f s", len(owned), time.monotonic() - started)

    selection = result.get("selection")
    if selection:
        wishlist_db.annotate_wanted(selection["shopping_list"])
        card_images.ensure_images(selection["shopping_list"])
        card_images.ensure_images([plan["commander"] for plan in selection["plans"]])
    return result


@router.post("/create", status_code=201)
def create_decks(request: CreateDecksRequest):
    """
    Enregistre les decks proposés comme de vrais decks.

    C'est le chaînon qui manquait : `/deck-plans` ne faisait que proposer, et
    tout ce qui améliore un deck dans le temps (`/balance`, les suggestions, les
    refus de conseil) a besoin d'un deck qui existe. Le groupe est **recalculé
    ici** à partir des mêmes commandants plutôt que reçu du navigateur : la
    collection a pu bouger entre l'affichage et le clic, et une decklist envoyée
    par le client serait une seconde vérité à vérifier.

    Un commandant qui a déjà un deck est **ignoré, pas dupliqué** : la réponse
    le dit. Rien n'est ajouté à la collection — ces cartes y sont déjà.
    """
    owned = commanders_db.owned_commanders()
    pools = commanders_db.recommendation_pool([str(c["oracle_id"]) for c in owned])
    if request.owned_only:
        pools = deck_plans_service.with_owned_cards(pools, owned, commanders_db.owned_cards())

    universe = {str(card["oracle_id"]) for pool in pools.values() for card in pool}
    universe.update(str(commander["oracle_id"]) for commander in owned)

    result = deck_plans_service.plan_decks(
        owned, pools, _available(request.reserve_existing_decks), request.max_price,
        request.target_bracket, request.commanders, find_combos=combos.matcher_for(universe),
        owned_only=request.owned_only,
    )
    if result.get("error"):
        raise HTTPException(400, result["error"])

    selection = result.get("selection")
    if not selection:
        raise HTTPException(400, "Aucun deck à créer pour cette sélection")

    # Les terrains de base ne sont pas dans la collection (quantité illimitée) :
    # leur impression se résout ici, une fois pour les quatre decks.
    basic_names = sorted({name for plan in selection["plans"] for name in plan["lands"]["basics"]})
    resolved = cards_db.resolve_names(basic_names)
    basic_land_ids = {name: resolved[name.lower()]["scryfall_id"]
                      for name in basic_names if name.lower() in resolved}

    created, skipped = [], []
    for plan in selection["plans"]:
        commander = plan["commander"]
        if commander.get("existing_deck_id"):
            skipped.append({"name": commander["name_fr"] or commander["name"],
                            "deck_id": commander["existing_deck_id"]})
            continue
        deck_id = decks_db.create_deck(commander["name_fr"] or commander["name"])
        decks_db.add_deck_cards(deck_id, deck_plans_service.deck_rows(plan, basic_land_ids))
        decks_db.set_commanders(deck_id, commander["scryfall_id"])
        created.append({"deck_id": deck_id, "name": commander["name_fr"] or commander["name"],
                        "card_count": sum(row[1] for row in
                                          deck_plans_service.deck_rows(plan, basic_land_ids))})

    missing_basics = [name for name in basic_names if name not in basic_land_ids]
    return {"created": created, "skipped": skipped, "missing_basics": missing_basics}
