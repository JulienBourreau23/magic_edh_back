"""
Le parsing de decklist est la porte d'entrée de toute l'appli : une regex trop
stricte fait disparaître des cartes en silence. Ces cas viennent de formats
d'export réels (Moxfield, Archidekt, copier-coller EDHREC).
"""
from services.decklist_parser import parse_decklist


def names(raw_text: str) -> list[str]:
    lines, _ = parse_decklist(raw_text)
    return [line.name for line in lines]


def test_ligne_sans_quantite_compte_pour_un():
    lines, unparsed = parse_decklist("Commander\nKrenko, Mob Boss\n\nDeck\nSol Ring")
    assert [(line.name, line.quantity) for line in lines] == [
        ("Krenko, Mob Boss", 1),
        ("Sol Ring", 1),
    ]
    assert unparsed == []


def test_suffixes_set_collector_et_foil():
    assert names("1 Sol Ring (C21) 205 *F*") == ["Sol Ring"]
    assert names("1x Arid Mesa (ZEN) 211") == ["Arid Mesa"]
    assert names("1 Sol Ring [Ramp{top}]") == ["Sol Ring"]


def test_entetes_de_type_ne_sont_pas_des_cartes():
    assert names("Creatures (2)\n1 Llanowar Elves\nLands\n1 Forest") == [
        "Llanowar Elves",
        "Forest",
    ]


def test_section_commander_et_partenaires():
    lines, _ = parse_decklist(
        "Commander\n1 Thrasios, Triton Hero\n1 Tymna the Weaver\n\nDeck\n1 Sol Ring"
    )
    assert [line.is_commander for line in lines] == [True, True, False]


def test_sideboard_ignore_et_commentaires():
    assert names("// commentaire\n1 Sol Ring\nSideboard\n1 Lightning Bolt") == ["Sol Ring"]


def test_nom_avec_parentheses_preserve():
    # Nom de carte contenant réellement des parenthèses : ne doit pas être tronqué.
    assert names("1 Erase (Not the Urza's Legacy One)") == ["Erase (Not the Urza's Legacy One)"]
