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


# --- casser un combo pour redescendre de bracket -------------------------

from services.suggestions import cuts_for_bracket  # noqa: E402

ORACLE_KIKI, ORACLE_CONSCRITS = "oracle-kiki", "oracle-conscrits"
ORACLE_ANGE, ORACLE_CMD = "oracle-ange", "oracle-commandant"


def _piece(oracle_id: str, nom: str, *, commandant: bool = False, rang: int = 100) -> dict:
    return {"oracle_id": oracle_id, "scryfall_id": f"sid-{oracle_id}", "name": nom,
            "name_fr": None, "price_eur": 1.0, "image_uri": None, "image_downloaded": False,
            "quantity": 1, "is_commander": commandant, "game_changer": False,
            "edhrec_rank": rang, "categories": [], "cmc": 5}


def _combo_entre(a: str, b: str, noms: list[str], wins: bool = True) -> dict:
    return {"cards": noms, "oracle_ids": [a, b], "wins_outright": wins,
            "produces": [], "total_mana_value": 10}


def test_un_seul_retrait_casse_deux_combos():
    # Kiki-Jiki est la moitié de deux combos : le couper une fois suffit, et
    # c'est ce qu'il faut proposer plutôt que deux retraits.
    cartes = [_piece(ORACLE_KIKI, "Kiki-Jiki"), _piece(ORACLE_CONSCRITS, "Conscrits zélés"),
              _piece(ORACLE_ANGE, "Ange de la restauration")]
    combos = [_combo_entre(ORACLE_KIKI, ORACLE_CONSCRITS, ["Kiki-Jiki", "Conscrits zélés"]),
              _combo_entre(ORACLE_KIKI, ORACLE_ANGE, ["Kiki-Jiki", "Ange de la restauration"])]

    cuts = cuts_for_bracket(cartes, 2, combos)
    assert [cut["card"]["name"] for cut in cuts] == ["Kiki-Jiki"]


def test_le_commandant_n_est_jamais_coupe():
    # Il reste disponible en zone de commandement : le couper ne casse rien.
    cartes = [_piece(ORACLE_CMD, "Commandant", commandant=True),
              _piece(ORACLE_ANGE, "Ange de la restauration")]
    combos = [_combo_entre(ORACLE_CMD, ORACLE_ANGE, ["Commandant", "Ange de la restauration"])]

    cuts = cuts_for_bracket(cartes, 2, combos)
    assert [cut["card"]["name"] for cut in cuts] == ["Ange de la restauration"]


def test_combo_incassable_signale_sans_carte():
    # Deux commandants (partenaires) : aucun retrait ne casse le combo, et le
    # dire vaut mieux que de rendre une liste vide qui aurait l'air complète.
    cartes = [_piece(ORACLE_CMD, "Commandant A", commandant=True),
              _piece(ORACLE_ANGE, "Commandant B", commandant=True)]
    combos = [_combo_entre(ORACLE_CMD, ORACLE_ANGE, ["Commandant A", "Commandant B"])]

    cuts = cuts_for_bracket(cartes, 2, combos)
    assert len(cuts) == 1 and cuts[0]["card"] is None
    assert "incassable" in cuts[0]["reason"]


def test_le_bracket_3_tolere_les_combos():
    cartes = [_piece(ORACLE_KIKI, "Kiki-Jiki"), _piece(ORACLE_CONSCRITS, "Conscrits zélés")]
    combos = [_combo_entre(ORACLE_KIKI, ORACLE_CONSCRITS, ["Kiki-Jiki", "Conscrits zélés"])]
    assert cuts_for_bracket(cartes, 3, combos) == []


def test_un_combo_qui_ne_gagne_pas_ne_se_casse_pas():
    # Mana infini sans débouché : il ne ferme aucun bracket.
    cartes = [_piece(ORACLE_KIKI, "Kiki-Jiki"), _piece(ORACLE_CONSCRITS, "Conscrits zélés")]
    combos = [_combo_entre(ORACLE_KIKI, ORACLE_CONSCRITS,
                           ["Kiki-Jiki", "Conscrits zélés"], wins=False)]
    assert cuts_for_bracket(cartes, 2, combos) == []
