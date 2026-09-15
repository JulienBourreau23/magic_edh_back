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


def test_recherche_par_type_de_terrain_est_du_ramp():
    # Nature's Lore et Wood Elves ne prononcent jamais le mot "land" : ils
    # cherchent "a Forest card". Comptés en tuteurs et pas en ramp, ils
    # faussaient le bracket et faisaient conseiller du ramp déjà présent.
    lore = classify("Sorcery", "Search your library for a Forest card, put that card onto "
                               "the battlefield, then shuffle.", None)
    assert "ramp" in lore
    assert "tutor" not in lore

    elves = classify("Creature — Elf Scout",
                     "When this creature enters, search your library for a Forest card, "
                     "put that card onto the battlefield, then shuffle.", None)
    assert "ramp" in elves
    assert "tutor" not in elves


def test_fetchland_n_est_ni_tuteur_ni_ramp():
    # Wooded Foothills : il remplace la pose de terrain du tour au lieu de s'y
    # ajouter, et chercher un terrain n'est pas tutoriser.
    categories = classify("Land",
                          "{T}, Pay 1 life, Sacrifice this land: Search your library for a "
                          "Mountain or Forest card, put it onto the battlefield, then shuffle.",
                          None)
    assert categories == ["land"]


def test_tuteur_a_creature_reste_un_tuteur():
    # Worldly Tutor : la contre-épreuve du cas ci-dessus, pour que la règle
    # "terrain" ne mange pas les vrais tuteurs.
    categories = classify("Instant",
                          "Search your library for a creature card, reveal it, then shuffle "
                          "and put that card on top.", None)
    assert "tutor" in categories
    assert "ramp" not in categories


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
