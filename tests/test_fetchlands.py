"""
Un fetchland n'a pas de mana produit chez Scryfall : il comptait comme un
terrain muet dans la manabase, la simulation et le duel. L'erreur ne levait
rien — un deck à six fetchlands paraissait simplement plus lent.
"""
from services.mana import resolve_fetchlands
from services.simulation import simulate


def land(name, type_line="Land", produced=(), fetches=None, quantity=1):
    return {"name": name, "type_line": type_line, "produced_mana": list(produced),
            "fetches": fetches, "quantity": quantity, "is_commander": False,
            "categories": ["land"], "mana_cost": None, "cmc": 0, "oracle_text": None}


def colors(cards, name):
    return next(c["produced_mana"] for c in resolve_fetchlands(cards) if c["name"] == name)


def test_un_fetchland_prend_les_couleurs_des_cibles_du_deck():
    deck = [land("Polluted Delta", fetches=["Island", "Swamp"]),
            land("Hallowed Fountain", "Land — Plains Island", "WU"),
            land("Swamp", "Basic Land — Swamp", "B"),
            land("Mountain", "Basic Land — Mountain", "R")]
    # Hallowed Fountain est une Île : Delta va aussi chercher du blanc.
    assert colors(deck, "Polluted Delta") == ["W", "U", "B"]


def test_sans_cible_dans_le_deck_il_ne_produit_rien():
    deck = [land("Polluted Delta", fetches=["Island", "Swamp"]),
            land("Mountain", "Basic Land — Mountain", "R")]
    assert colors(deck, "Polluted Delta") == []


def test_basic_land_card_ne_vise_que_les_basiques():
    deck = [land("Evolving Wilds", fetches=["Basic"]),
            land("Plains", "Basic Land — Plains", "W"),
            land("Hallowed Fountain", "Land — Plains Island", "WU")]
    assert colors(deck, "Evolving Wilds") == ["W"]


def test_un_terrain_qui_produit_deja_une_couleur_n_est_pas_touche():
    deck = [land("Flagstones of Trokair", produced="W", fetches=["Plains"]),
            land("Hallowed Fountain", "Land — Plains Island", "WU")]
    assert colors(deck, "Flagstones of Trokair") == ["W"]


def test_la_simulation_compte_les_fetchlands_comme_des_sources():
    commander = {"name": "Cmd", "type_line": "Legendary Creature", "produced_mana": [],
                 "categories": [], "mana_cost": "{2}{U}{U}", "cmc": 4, "quantity": 1,
                 "is_commander": True, "oracle_text": None, "fetches": None}
    filler = {"name": "Filler", "type_line": "Sorcery", "produced_mana": [], "categories": [],
              "mana_cost": "{5}", "cmc": 5, "quantity": 63, "is_commander": False,
              "oracle_text": None, "fetches": None}
    fetch_deck = [commander, filler, land("Island", "Basic Land — Island", "U", quantity=1),
                  *[land(f"Fetch {i}", fetches=["Island"]) for i in range(35)]]
    island_deck = [commander, filler, land("Island", "Basic Land — Island", "U", quantity=36)]
    with_fetches = simulate(fetch_deck, iterations=300, seed=0)["commander_cast_rate"]
    with_islands = simulate(island_deck, iterations=300, seed=0)["commander_cast_rate"]
    assert with_fetches == with_islands
