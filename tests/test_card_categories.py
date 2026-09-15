"""
La classification pilote le diagnostic du deck et les suggestions : une règle
trop large ferait conseiller n'importe quoi. Chaque cas vient d'une carte réelle.
"""
from services.card_categories import classify


def test_terrain_de_base():
    assert classify("Basic Land — Forest", "({T}: Add {G}.)", ["G"]) == ["land"]


def test_rocher_de_mana_est_du_ramp():
    assert "ramp" in classify("Artifact", "{T}: Add {C}{C}.", ["C"])


def test_tuteur_a_terrain_compte_comme_ramp_pas_comme_tuteur():
    # Cultivate : sinon le signal "tuteur" du bracket serait gonflé par toute
    # la fixation de mana du deck.
    categories = classify("Sorcery", "Search your library for up to two basic land cards...", None)
    assert "ramp" in categories
    assert "tutor" not in categories


def test_tuteur_generique():
    categories = classify("Sorcery", "Search your library for a card, put that card into your hand...", None)
    assert "tutor" in categories


def test_removal_cible():
    assert "removal" in classify("Instant", "Destroy target creature. It can't be regenerated.", None)


def test_board_wipe():
    assert "board_wipe" in classify("Sorcery", "Destroy all creatures. They can't be regenerated.", None)


def test_contresort():
    assert classify("Instant", "Counter target spell.", None) == ["counterspell"]


def test_pioche():
    assert "draw" in classify("Enchantment", "Whenever an opponent casts a spell, you may draw a card.", None)


def test_tour_supplementaire():
    assert "extra_turn" in classify("Sorcery", "Take an extra turn after this one.", None)


def test_carte_sans_role_identifie():
    assert classify("Creature — Bear", "", None) == []
