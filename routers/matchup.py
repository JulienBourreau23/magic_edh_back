from fastapi import APIRouter, HTTPException, Query

import db.decks as decks_db
from services import combos, matchup, simulation

router = APIRouter(prefix="/matchup", tags=["matchup"])


@router.get("")
def compare_decks(a: int = Query(description="id du premier deck"),
                  b: int = Query(description="id du second deck"),
                  iterations: int = Query(default=simulation.DEFAULT_ITERATIONS, ge=100, le=5000),
                  seed: int = 0):
    """Comparaison de deux decks — 100 % calculée, aucune IA impliquée."""
    if a == b:
        raise HTTPException(400, "Choisis deux decks différents")

    decks = {}
    for key, deck_id in (("a", a), ("b", b)):
        deck = decks_db.get_deck(deck_id)
        if not deck:
            raise HTTPException(404, f"Deck {deck_id} introuvable")
        decks[key] = (deck, decks_db.get_deck_cards_for_simulation(deck_id))

    return matchup.compare(
        *decks["a"], *decks["b"], iterations=iterations, seed=seed,
        combos_a=combos.find_in_deck(decks["a"][1]),
        combos_b=combos.find_in_deck(decks["b"][1]),
    )
