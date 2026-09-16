"""
Le catalogue de combos décide d'un plancher de bracket : une règle trop large
ferait monter tous les decks, une règle trop étroite raterait le combo qui
gagne. Chaque cas vient d'une variante réelle de Commander Spellbook.
"""
from services.deck_analysis import bracket_estimate
from services.spellbook import to_row, two_card_pair, wins_outright

ORACLE_A = "9a1412db-45ad-46ea-8f12-a85d203113d8"
ORACLE_B = "1de1b591-a73f-4974-b507-8c63e07a0868"


def _variant(**overrides) -> dict:
    variant = {
        "id": "513-5034", "manaNeeded": "{U}{U}{B}", "manaValueNeeded": 3,
        "bracketTag": "R", "popularity": 12,
        "uses": [
            {"quantity": 1, "card": {"oracleId": ORACLE_A, "name": "Demonic Consultation"}},
            {"quantity": 1, "card": {"oracleId": ORACLE_B, "name": "Thassa's Oracle"}},
        ],
        "produces": [{"feature": {"name": "Win the game"}}],
        "requires": [],
    }
    variant.update(overrides)
    return variant


def test_gagne_la_partie():
    assert wins_outright(["Win the game"])
    assert wins_outright(["Target opponent loses the game at the beginning of their next upkeep"])
    assert wins_outright(["Infinite combat damage"])
    # Kiki-Jiki + Conscrits zélés : Spellbook ne déclare aucune ligne de dégâts,
    # mais une infinité d'attaquants avec la célérité finit la partie sur place.
    assert wins_outright(["Infinite creature tokens with haste", "Infinite creature ETB"])


def test_ne_gagne_pas_la_partie():
    # Des préparatifs, pas une victoire : chacun de ces effets demande une
    # troisième carte pour tuer.
    assert not wins_outright(["Infinite mana", "Infinite card draw"])
    assert not wins_outright(["Infinite self-mill"])
    assert not wins_outright(["Infinite damage to all creatures"])       # board wipe
    assert not wins_outright(["Infinite tapped creature tokens with haste"])  # n'attaquent pas
    assert not wins_outright(["Infinite copies of artifacts you control with haste"])


def test_paire_triee_et_normalisee():
    oracle_a, name_a, oracle_b, name_b = two_card_pair(_variant())
    assert oracle_a < oracle_b            # la table stocke la paire triée
    assert {name_a, name_b} == {"Demonic Consultation", "Thassa's Oracle"}


def test_variantes_non_exploitables_ecartees():
    # Un gabarit ("une créature avec la célérité") ne se vérifie pas contre une
    # decklist : deux cartes nommées, ou rien.
    assert two_card_pair(_variant(requires=[{"template": {"name": "Haste outlet"}}])) is None
    # Deux exemplaires de la même carte : impossible en singleton.
    meme_carte = _variant()
    meme_carte["uses"][1]["card"]["oracleId"] = ORACLE_A
    assert two_card_pair(meme_carte) is None
    # Trois cartes : le filtre de l'API n'est pas une garantie.
    trois = _variant()
    trois["uses"].append({"quantity": 1, "card": {"oracleId": ORACLE_A, "name": "X"}})
    assert two_card_pair(trois) is None


def test_ligne_prete_pour_la_base():
    row = to_row(_variant())
    assert row[0] == "513-5034"
    assert row[5] == ["Win the game"] and row[6] is True
    assert row[9] == "R"


# --- plancher de bracket ---------------------------------------------------

def _carte(**overrides) -> dict:
    carte = {"name": "Carte", "scryfall_id": "00000000-0000-0000-0000-000000000001",
             "quantity": 1, "is_commander": False,
             "game_changer": False, "categories": [], "cmc": 2}
    carte.update(overrides)
    return carte


def _combo(wins: bool) -> dict:
    return {"cards": ["A", "B"], "wins_outright": wins, "produces": [], "total_mana_value": 10}


def test_combo_gagnant_interdit_les_brackets_1_2():
    # Aucun Game Changer, mais un combo qui gagne : le bracket 1-2 est
    # officiellement fermé à ce deck.
    estimation = bracket_estimate([_carte()], [_combo(wins=True)])
    assert (estimation["min"], estimation["max"]) == (3, 3)
    assert estimation["winning_combo_count"] == 1


def test_combo_non_gagnant_ne_change_pas_le_bracket():
    # Mana infini sans débouché : ça reste un deck de bracket 1-2.
    estimation = bracket_estimate([_carte()], [_combo(wins=False)])
    assert (estimation["min"], estimation["max"]) == (1, 2)
    assert estimation["winning_combo_count"] == 0
    assert len(estimation["two_card_combos"]) == 1   # affiché quand même


def test_sans_catalogue_le_calcul_reste_celui_des_game_changers():
    estimation = bracket_estimate([_carte(game_changer=True)])
    assert (estimation["min"], estimation["max"]) == (3, 3)
    assert estimation["two_card_combos"] == []
