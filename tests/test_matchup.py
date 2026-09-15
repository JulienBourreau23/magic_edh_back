"""
La comparaison de decks est la sortie la plus facile à croire sur parole : un
score « 4-2 » se lit comme un verdict. On vérifie donc ce que ce score compte,
et surtout ce qu'il ne compte pas.
"""
from services import matchup

DECK_A = {"id": 1, "name": "Deck A", "format": "commander"}
DECK_B = {"id": 2, "name": "Deck B", "format": "commander"}


def card(name: str, **overrides) -> dict:
    base = {
        "name": name, "name_fr": None, "scryfall_id": f"scryfall-{name}",
        "oracle_id": f"oracle-{name}", "quantity": 1, "cmc": 0, "mana_cost": "",
        "categories": [], "produced_mana": [], "oracle_text": "", "is_commander": False,
        "type_line": "", "power": None, "toughness": None, "color_identity": ["G"],
        "game_changer": False, "price_eur": 1.0, "edhrec_rank": 1000,
    }
    return {**base, **overrides}


FOREST = card("Forest", quantity=40, categories=["land"], produced_mana=["G"],
              oracle_text="({T}: Add {G}.)", type_line="Basic Land — Forest")
COMMANDER = card("Chef test", cmc=2, mana_cost="{1}{G}", is_commander=True,
                 type_line="Legendary Creature — Elf", power="2", toughness="2")


def deck(power: str, game_changers: int = 0) -> list[dict]:
    cards = [FOREST, COMMANDER,
             card("Bête", quantity=59 - game_changers, cmc=2, mana_cost="{1}{G}",
                  type_line="Creature — Beast", power=power, toughness="2")]
    if game_changers:
        cards.append(card("Carte décisive", quantity=game_changers, cmc=2, mana_cost="{1}{G}",
                          type_line="Creature — Beast", power=power, toughness="2",
                          game_changer=True))
    return cards


def test_le_bracket_n_est_pas_un_axe_du_score():
    # Sur une page d'équilibrage, « bracket plus haut = axe gagné » donnerait un
    # point gratuit au deck le plus puissant, alors que sa puissance est déjà
    # mesurée par les autres axes. Le bracket reste affiché, pas compté.
    result = matchup.compare(DECK_A, deck("3"), DECK_B, deck("3", game_changers=5),
                             iterations=100)

    assert all("racket" not in axis["label"] for axis in result["axes"])
    assert result["wins"]["a"] + result["wins"]["b"] <= len(result["axes"])
    # Le bracket reste renvoyé par deck, lui.
    assert result["a"]["bracket"]["min"] < result["b"]["bracket"]["min"]


def test_les_axes_designent_un_gagnant_dans_le_bon_sens():
    result = matchup.compare(DECK_A, deck("3"), DECK_B, deck("3"), iterations=100)

    for axis in result["axes"]:
        if axis["winner"] is None or axis["a"] is None or axis["b"] is None:
            continue
        gagnant = axis["a"] if axis["winner"] == "a" else axis["b"]
        perdant = axis["b"] if axis["winner"] == "a" else axis["a"]
        assert (gagnant < perdant) if axis["lower_is_better"] else (gagnant > perdant)
