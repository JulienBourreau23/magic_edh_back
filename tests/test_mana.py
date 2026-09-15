"""
Le calcul de castabilité décide si un deck est jouable ou non : c'est la partie
où une approximation se verrait dans les conseils donnés à l'utilisateur.
"""
from services.mana import can_pay, color_requirements, parse_mana_cost


def source(*colors: str) -> frozenset[str]:
    return frozenset(colors)


def test_parse_cout_simple():
    assert parse_mana_cost("{2}{G}{U}") == (2, [frozenset("G"), frozenset("U")])


def test_parse_hybride_et_x():
    generic, pips = parse_mana_cost("{X}{G/U}{W}")
    assert generic == 0
    assert pips == [frozenset({"G", "U"}), frozenset("W")]


def test_parse_incolore_compte_comme_generique():
    assert parse_mana_cost("{2}{C}") == (3, [])


def test_duales_couvrent_plusieurs_pips_de_meme_couleur():
    # Trois {G} et trois duales G/U : le couplage doit trouver une solution.
    assert can_pay(0, [frozenset("G")] * 3, [source("G", "U")] * 3)


def test_une_seule_source_ne_paie_pas_deux_pips():
    # {G}{G} avec une seule source verte (+ une source rouge) : impossible.
    assert not can_pay(0, [frozenset("G")] * 2, [source("G"), source("R")])


def test_source_dediee_a_un_pip_ne_paie_pas_le_generique():
    # {1}{W}{U} : trois sources dont une seule blanche et une seule bleue.
    assert can_pay(1, [frozenset("W"), frozenset("U")], [source("W"), source("U"), source("C")])
    assert not can_pay(1, [frozenset("W"), frozenset("U")], [source("W"), source("U")])


def test_couplage_avec_reaffectation():
    # {W}{U} avec une duale W/U et une source mono-blanche : un glouton naïf
    # donnerait la duale au pip {W} puis échouerait sur {U}. Le couplage par
    # chemins augmentants réaffecte la duale au bleu et trouve la solution.
    assert can_pay(0, [frozenset("W"), frozenset("U")], [source("W", "U"), source("W")])

    # En revanche, deux pips bleus pour une seule source bleue reste impossible.
    assert not can_pay(0, [frozenset("U")] * 2, [source("W", "U"), source("W")])


def test_comptage_des_pips_par_couleur():
    cards = [
        {"mana_cost": "{1}{B}{B}", "quantity": 1},
        {"mana_cost": "{R}", "quantity": 2},
        {"mana_cost": None, "quantity": 5},
    ]
    assert color_requirements(cards) == {"B": 2, "R": 2}
