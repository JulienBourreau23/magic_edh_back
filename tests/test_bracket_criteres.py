"""
Les deux critères de bracket qui manquaient : destruction de terrains de masse
et tours supplémentaires.

Ces règles décident d'un plancher, donc une erreur y est silencieuse — un deck
annoncé bracket 1-2 alors qu'il est bracket 4 ne lève aucune alerte, il ment
simplement. Les textes oracle ci-dessous sont recopiés tels quels depuis la
base, y compris les formulations qui piègent la règle.
"""
from services import card_categories as cat
from services.card_categories import classify
from services.deck_analysis import bracket_estimate


def _classe(type_line: str, texte: str) -> list[str]:
    return classify(type_line, texte, None)


# --- ce qui détruit vraiment les terrains de tout le monde ----------------

def test_destruction_de_masse_reconnue():
    assert cat.MASS_LAND_DENIAL in _classe("Sorcery", "Destroy all lands.")
    # Le sacrifice imposé à tous vaut la destruction.
    assert cat.MASS_LAND_DENIAL in _classe(
        "Sorcery",
        "Each player sacrifices four lands of their choice. "
        "Wildfire deals 4 damage to each creature.")
    # « sauf trois » reste de la destruction de masse : l'exclusion porte sur
    # une quantité, pas sur le fait de viser les terrains.
    assert cat.MASS_LAND_DENIAL in _classe(
        "Creature — Human Soldier",
        "When this creature enters, each player sacrifices all lands they "
        "control except for three.")
    # Le singulier compte quand il se répète (Thoughts of Ruin).
    assert cat.MASS_LAND_DENIAL in _classe(
        "Sorcery",
        "Each player sacrifices a land of their choice for each card in your hand.")


def test_les_terrains_epargnes_ne_sont_pas_detruits():
    # Elspeth Tirel : « except for lands » — les terrains sont justement ce qui
    # survit. La règle naïve « destroy all … lands » se fait piéger ici.
    assert cat.MASS_LAND_DENIAL not in _classe(
        "Legendary Planeswalker — Elspeth",
        "+2: You gain 1 life for each creature you control. "
        "−2: Create three 1/1 white Soldier creature tokens. "
        "−5: Destroy all other permanents except for lands and tokens.")
    assert cat.MASS_LAND_DENIAL not in _classe(
        "Artifact",
        "{T}, Sacrifice this artifact: Destroy all permanents except for "
        "artifacts and lands. Activate only during your upkeep.")
    # Street Sweeper détruit des auras, le terrain n'est que leur support.
    assert cat.MASS_LAND_DENIAL not in _classe(
        "Artifact Creature — Construct",
        "Whenever this creature attacks, destroy all Auras attached to target land.")


def test_un_seul_terrain_chacun_nest_pas_une_destruction_de_masse():
    # Tremble prive d'une pose, pas d'une manabase.
    assert cat.MASS_LAND_DENIAL not in _classe(
        "Sorcery", "Each player sacrifices a land of their choice.")


def test_le_stax_nest_pas_de_la_destruction_de_terrains():
    # Winter Orb empêche de dégager, il ne détruit rien : c'est du stax, qui
    # n'est pas un critère officiel de bracket.
    categories = _classe(
        "Artifact",
        "As long as this artifact is untapped, players can't untap more than "
        "one land during their untap steps.")
    assert cat.STAX in categories
    assert cat.MASS_LAND_DENIAL not in categories


# --- effet sur le bracket -------------------------------------------------

def _carte(**overrides) -> dict:
    carte = {"name": "Carte", "name_fr": None,
             "scryfall_id": "00000000-0000-0000-0000-000000000001",
             "quantity": 1, "is_commander": False,
             "game_changer": False, "categories": [], "cmc": 2}
    carte.update(overrides)
    return carte


def test_un_seul_armageddon_ferme_les_brackets_1_a_3():
    # Zéro Game Changer, zéro combo : l'ancien calcul annonçait « bracket 1-2 ».
    estimation = bracket_estimate([
        _carte(),
        _carte(name="Armageddon", categories=[cat.MASS_LAND_DENIAL]),
    ])
    assert (estimation["min"], estimation["max"]) == (4, 5)
    assert [c["name"] for c in estimation["mass_land_denial"]] == ["Armageddon"]


def test_la_destruction_de_masse_prime_sur_le_compte_de_game_changers():
    # Un seul Game Changer plafonnerait au bracket 3 ; la destruction de masse
    # est plus punitive, c'est elle qui décide.
    estimation = bracket_estimate([
        _carte(game_changer=True),
        _carte(name="Jokulhaups", categories=[cat.MASS_LAND_DENIAL]),
    ])
    assert (estimation["min"], estimation["max"]) == (4, 5)


def test_un_tour_supplementaire_ferme_le_bracket_1_sans_plus():
    # Le bracket 1 interdit les tours supplémentaires ; les brackets 2 et 3 ne
    # refusent que de les enchaîner, ce qu'une liste de cartes ne dit pas.
    estimation = bracket_estimate([
        _carte(name="Time Warp", categories=[cat.EXTRA_TURN]),
    ])
    assert (estimation["min"], estimation["max"]) == (2, 2)
    assert [c["name"] for c in estimation["extra_turns"]] == ["Time Warp"]


def test_le_stax_seul_ne_change_pas_le_bracket():
    # Winter Orb gêne autant qu'un Armageddon, mais le système officiel ne
    # nomme le stax nulle part : l'inventer ferait dériver tous les brackets.
    estimation = bracket_estimate([
        _carte(name="Winter Orb", categories=[cat.STAX]),
    ])
    assert (estimation["min"], estimation["max"]) == (1, 2)
    assert estimation["qualitative_signals"]["stax"] == 1


def test_un_deck_sans_signal_reste_au_plancher():
    estimation = bracket_estimate([_carte()])
    assert (estimation["min"], estimation["max"]) == (1, 2)
    assert estimation["floor_reasons"] == []


def test_les_raisons_du_plancher_sont_explicitees():
    estimation = bracket_estimate([
        _carte(game_changer=True),
        _carte(name="Armageddon", categories=[cat.MASS_LAND_DENIAL]),
    ])
    raisons = " ".join(estimation["floor_reasons"])
    assert "destruction de terrains de masse" in raisons
    assert "Game Changer" in raisons
