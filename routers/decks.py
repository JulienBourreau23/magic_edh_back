from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import db.decks as decks_db
import services.card_images as card_images
from services import combos, deck_analysis, simulation, suggestions
from services.decklist_parser import import_decklist

router = APIRouter(prefix="/decks", tags=["decks"])

Format = Literal["commander", "duel"]


class ImportDeckRequest(BaseModel):
    name: str
    decklist: str
    format: Format = "commander"
    # Vrai seulement si le deck est physiquement monté : ses cartes entrent
    # alors dans la collection. Faux par défaut — un deck envisagé ne prouve
    # pas qu'on possède quoi que ce soit.
    add_to_collection: bool = False


class UpdateDeckRequest(BaseModel):
    name: str | None = None
    format: Format | None = None
    commander_scryfall_id: str | None = None


class AddCardRequest(BaseModel):
    scryfall_id: str
    quantity: int = Field(default=1, ge=1, le=100)
    is_commander: bool = False
    # Ligne d'import que cet ajout vient corriger, le cas échéant.
    resolves_raw_line: str | None = None


def _load_deck(deck_id: int) -> dict:
    deck = decks_db.get_deck(deck_id)
    if not deck:
        raise HTTPException(404, "Deck introuvable")
    return deck


@router.post("")
def import_deck(payload: ImportDeckRequest):
    if not payload.decklist.strip():
        raise HTTPException(400, "La decklist est vide")
    return import_decklist(payload.name, payload.decklist, payload.format,
                           add_to_collection=payload.add_to_collection)


@router.get("")
def list_decks():
    return decks_db.list_decks()


@router.get("/{deck_id}")
def get_deck(deck_id: int):
    deck = _load_deck(deck_id)
    cards = decks_db.get_deck_cards(deck_id)
    card_images.ensure_images(cards)

    return {
        "deck": deck,
        "cards": cards,
        "import_issues": decks_db.get_import_issues(deck_id),
        "mana_curve": deck_analysis.mana_curve(cards),
        "total_price_eur": deck_analysis.total_price_eur(cards),
        "legality_warnings": deck_analysis.legality_warnings(cards, deck["format"]),
        "bracket": deck_analysis.bracket_estimate(cards, combos.find_in_deck(cards)),
        "manabase": deck_analysis.manabase(cards),
        "role_diagnostics": deck_analysis.role_diagnostics(cards),
    }


@router.patch("/{deck_id}")
def update_deck(deck_id: int, payload: UpdateDeckRequest):
    if not decks_db.update_deck(deck_id, payload.name, payload.format, payload.commander_scryfall_id):
        raise HTTPException(404, "Deck introuvable")
    return decks_db.get_deck(deck_id)


@router.delete("/{deck_id}", status_code=204)
def delete_deck(deck_id: int):
    if not decks_db.delete_deck(deck_id):
        raise HTTPException(404, "Deck introuvable")


@router.post("/{deck_id}/cards", status_code=201)
def add_card(deck_id: int, payload: AddCardRequest):
    _load_deck(deck_id)
    decks_db.add_deck_cards(deck_id, [(payload.scryfall_id, payload.quantity, payload.is_commander)])
    if payload.is_commander:
        decks_db.update_deck(deck_id, commander_scryfall_id=payload.scryfall_id)
    if payload.resolves_raw_line:
        decks_db.resolve_import_issue(deck_id, payload.resolves_raw_line)
    return {"status": "ok"}


@router.delete("/{deck_id}/cards/{scryfall_id}", status_code=204)
def remove_card(deck_id: int, scryfall_id: str):
    if not decks_db.remove_deck_card(deck_id, scryfall_id):
        raise HTTPException(404, "Carte absente du deck")


@router.get("/{deck_id}/simulation")
def simulate_deck(deck_id: int,
                  iterations: int = Query(default=simulation.DEFAULT_ITERATIONS, ge=100, le=5000),
                  seed: int = 0):
    _load_deck(deck_id)
    cards = decks_db.get_deck_cards_for_simulation(deck_id)
    hand = simulation.sample_opening(cards, seed=seed)
    card_images.ensure_images(hand.get("hand", []) + hand.get("draws", []))
    return {
        "metrics": simulation.simulate(cards, iterations=iterations, seed=seed),
        "sample_opening": hand,
    }


@router.get("/{deck_id}/suggestions")
def deck_suggestions(deck_id: int,
                     max_price: float = Query(default=suggestions.DEFAULT_MAX_PRICE_EUR, gt=0),
                     target_bracket: int | None = Query(default=None, ge=1, le=5)):
    deck = _load_deck(deck_id)
    cards = decks_db.get_deck_cards(deck_id)
    result = suggestions.suggest(cards, deck["format"], max_price, target_bracket)
    for group in result.get("to_add", []):
        card_images.ensure_images(group["candidates"])
    return result
