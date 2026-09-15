"""
La simulation doit être reproductible (même graine = mêmes chiffres), sans quoi
l'affichage sauterait à chaque rechargement et les comparaisons de decks
seraient du bruit.
"""
import random

from services.simulation import build_library, draw_opening_hand, simulate

FOREST = {"name": "Forest", "quantity": 40, "cmc": 0, "mana_cost": "", "categories": ["land"],
          "produced_mana": ["G"], "oracle_text": "({T}: Add {G}.)", "is_commander": False}
BEAR = {"name": "Grizzly Bears", "quantity": 59, "cmc": 2, "mana_cost": "{1}{G}", "categories": [],
        "produced_mana": [], "oracle_text": "", "is_commander": False}
COMMANDER = {"name": "Commandant test", "quantity": 1, "cmc": 3, "mana_cost": "{1}{G}{G}",
             "categories": [], "produced_mana": [], "oracle_text": "", "is_commander": True}

DECK = [FOREST, BEAR, COMMANDER]


def test_meme_graine_memes_resultats():
    assert simulate(DECK, iterations=200, seed=42) == simulate(DECK, iterations=200, seed=42)


def test_graines_differentes_resultats_differents():
    assert simulate(DECK, iterations=200, seed=1) != simulate(DECK, iterations=200, seed=2)


def test_commandant_mono_couleur_est_lance_presque_toujours():
    metrics = simulate(DECK, iterations=300, seed=7)
    # 40 forêts pour un commandant à {1}{G}{G} : il doit sortir quasi à coup sûr
    # et sans blocage de couleur, puisqu'il n'y a qu'une couleur dans le deck.
    assert metrics["commander_cast_rate"] > 0.95
    assert metrics["color_screw_rate"] == 0.0
    assert 3 <= metrics["avg_commander_turn"] <= 5


def test_mana_croit_avec_les_tours():
    metrics = simulate(DECK, iterations=200, seed=3)
    mana = [metrics["avg_mana_by_turn"][turn] for turn in range(1, 9)]
    assert mana == sorted(mana)


def test_deck_trop_petit():
    assert "error" in simulate([COMMANDER], iterations=10)


def test_le_mulligan_ne_perd_aucune_carte():
    # Mulligan londonien : les cartes rendues repassent SOUS la bibliothèque.
    # Les jeter rétrécirait le deck à chaque mulligan, donc fausserait la
    # probabilité de piocher quoi que ce soit ensuite.
    library, _ = build_library(DECK)
    rng = random.Random(3)
    mulligans_vus = set()

    for _ in range(60):
        hand, rest, mulligans = draw_opening_hand(rng, library)
        mulligans_vus.add(mulligans)
        assert len(hand) + len(rest) == len(library)
        assert len(hand) == 7 - mulligans

    assert mulligans_vus != {0}, "aucun mulligan tiré : le test ne prouve rien"
