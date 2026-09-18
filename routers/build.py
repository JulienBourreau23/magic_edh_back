from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import db.cards as cards_db
import db.commanders as commanders_db
import db.decks as decks_db
import services.card_images as card_images
from services import build as build_service
from services import combos, matchup

router = APIRouter(prefix="/build", tags=["build"])

FORMATS = "^(commander|duel)$"


class DraftCard(BaseModel):
    scryfall_id: str
    quantity: int = Field(default=1, ge=1, le=99)


class DraftRequest(BaseModel):
    format: str = Field(default="commander", pattern=FORMATS)
    commander_scryfall_id: str | None = None
    cards: list[DraftCard] = Field(default_factory=list, max_length=200)


class LandRequest(DraftRequest):
    commander_oracle_id: str
    slots: int = Field(default=build_service.DEFAULT_LAND_SLOTS, ge=0, le=60)


class SaveRequest(DraftRequest):
    name: str = Field(min_length=1, max_length=120)


class CompareRequest(DraftRequest):
    deck_id: int
    name: str = "Brouillon"


@router.get("/commanders")
def list_commanders(format: str = Query(default="commander", pattern=FORMATS)):
    """
    Les commandants de la collection, légaux dans ce format : le classeur qu'on
    ouvre pour commencer. Le format passe **avant** le choix parce qu'il change
    la liste dans les deux sens — Edgar Markov est légal en multi et banni en
    duel, Rofellos l'inverse.
    """
    commanders = commanders_db.owned_commanders(format)
    card_images.ensure_images(commanders)
    return {"commanders": commanders}


@router.get("/pool")
def pool(commander: str, format: str = Query(default="commander", pattern=FORMATS)):
    """Tout ce que la collection permet de mettre dans ce deck, terrains compris."""
    carte = cards_db.get_cheapest_by_oracle_id(commander)
    if not carte:
        raise HTTPException(404, "Commandant introuvable")
    cards = cards_db.buildable_pool(carte["color_identity"], format, commander)
    for card in cards:
        card["inclusion_rate"] = float(card["inclusion_rate"]) if card["inclusion_rate"] else None
    return {"commander": carte, "cards": cards}


@router.post("/lands")
def lands(payload: LandRequest):
    """L'assistance aux terrains : non-basiques possédés, puis basiques au prorata."""
    carte = cards_db.get_cheapest_by_oracle_id(payload.commander_oracle_id)
    if not carte:
        raise HTTPException(404, "Commandant introuvable")
    chosen = build_service.draft_cards([card.model_dump() for card in payload.cards],
                                       payload.commander_scryfall_id)
    plan = build_service.land_assistance(carte, chosen, payload.slots, payload.format)

    # Les terrains de base ne sont pas dans la collection (quantité illimitée) :
    # le conseil les nomme, on rend ici l'impression qui va avec, sans quoi le
    # navigateur ne pourrait pas les poser dans le brouillon.
    resolved = cards_db.resolve_names(list(plan["basics"]))
    # `name` est déjà le nom français (c'est par lui que le conseil les nomme) :
    # on le garde en alias, la résolution ne renvoyant que les colonnes de
    # `cards_cheapest`, donc l'anglais.
    plan["basics_cards"] = [
        {**resolved[name.lower()], "name_fr": name, "quantity": quantity}
        for name, quantity in plan["basics"].items() if name.lower() in resolved
    ]
    return plan


@router.post("/evaluate")
def evaluate(payload: DraftRequest):
    """L'évaluation du brouillon, identique à celle de la fiche de deck."""
    cards = build_service.draft_cards([card.model_dump() for card in payload.cards],
                                      payload.commander_scryfall_id)
    if not cards:
        raise HTTPException(400, "Le brouillon est vide")
    return build_service.evaluate(cards, payload.format)


@router.post("/compare")
def compare(payload: CompareRequest):
    """
    Confronte le brouillon à un deck déjà construit, avec la même mesure que la
    page de comparaison — duel simulé compris.
    """
    deck = decks_db.get_deck(payload.deck_id)
    if not deck:
        raise HTTPException(404, "Deck introuvable")
    cards_a = build_service.draft_cards([card.model_dump() for card in payload.cards],
                                        payload.commander_scryfall_id)
    if not cards_a:
        raise HTTPException(400, "Le brouillon est vide")
    cards_b = decks_db.get_deck_cards_for_simulation(payload.deck_id)
    # `id` à None : le brouillon n'existe pas en base, et c'est justement le
    # sujet — la comparaison doit marcher avant la sauvegarde.
    return matchup.compare(
        {"id": None, "name": payload.name, "format": payload.format}, cards_a, deck, cards_b,
        combos_a=combos.find_in_deck(cards_a), combos_b=combos.find_in_deck(cards_b),
    )


@router.post("/save", status_code=201)
def save(payload: SaveRequest):
    """
    Enregistre le brouillon. **C'est le seul moment où quelque chose est écrit**
    — sans ce clic, le deck n'existe que dans le navigateur.
    """
    if not payload.cards:
        raise HTTPException(400, "Le brouillon est vide")
    deck_id = build_service.save(payload.name, payload.format,
                                 payload.commander_scryfall_id,
                                 [card.model_dump() for card in payload.cards])
    return {"deck_id": deck_id, "name": payload.name}
