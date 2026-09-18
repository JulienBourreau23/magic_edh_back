"""
Noms français des cartes à deux faces.

Scryfall ne met `printed_name` au premier niveau que pour les cartes à une
seule face : une partagée, une recto-verso, une aventure ou une flip le range
dans `card_faces`. Le sync ne lisait que le premier niveau, donc **une carte à
deux noms sur 878 avait un nom français** (contre 90 % des cartes simples) :
elles s'affichaient en anglais partout et une decklist française les laissait
non résolues.

C'est l'erreur silencieuse type — rien ne remonte, la carte a juste l'air de ne
pas être traduite — d'où ce test, qui ne demande ni base ni réseau.
"""
from scripts.sync_french_names import printed_name_for


def test_carte_a_une_face():
    assert printed_name_for({"printed_name": "Anneau solaire"}) == "Anneau solaire"


def test_carte_a_deux_faces_recollee_comme_scryfall_ecrit_name():
    # ` // ` est exactement la convention du champ `name` anglais : c'est ce qui
    # permet de comparer alias et nom de la même façon dans les deux langues.
    card = {
        "name": "Fire // Ice",
        "card_faces": [{"printed_name": "Feu"}, {"printed_name": "Glace"}],
    }
    assert printed_name_for(card) == "Feu // Glace"


def test_une_seule_face_traduite_ne_donne_rien():
    # Un nom à moitié français ne correspondrait ni à la carte imprimée ni à ce
    # qu'un joueur écrit : mieux vaut l'absence d'alias, qui retombe sur
    # l'anglais.
    card = {"name": "A // B", "card_faces": [{"printed_name": "Feu"}, {}]}
    assert printed_name_for(card) is None


def test_carte_sans_traduction():
    assert printed_name_for({"name": "Sol Ring"}) is None
