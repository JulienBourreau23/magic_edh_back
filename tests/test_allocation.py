"""
La répartition de la collection décide de ce qu'il faut racheter. L'erreur qui
coûte de l'argent en silence, c'est de confondre « cette carte est déjà placée »
et « je n'en ai plus d'exemplaire libre ».
"""
from services.allocation import allocate

DECK_A = {"id": 1, "name": "Deck A"}
DECK_B = {"id": 2, "name": "Deck B"}


def card(name: str, price: float = 5.0, type_line: str = "Artifact") -> dict:
    return {
        "scryfall_id": f"scryfall-{name}", "oracle_id": f"oracle-{name}", "name": name,
        "name_fr": None, "price_eur": price, "image_uri": None, "image_downloaded": False,
        "type_line": type_line,
    }


def test_un_seul_exemplaire_pour_deux_decks_impose_un_achat():
    partagee = card("Partagée", price=7.0)
    result = allocate([(DECK_A, [partagee]), (DECK_B, [partagee])], {"oracle-Partagée": 1})

    assert result["decks"][0]["to_buy_count"] == 0
    assert result["decks"][1]["to_buy_count"] == 1
    assert result["total_cost_eur"] == 7.0
    assert result["remaining_copies"]["oracle-Partagée"] == 0


def test_deux_exemplaires_servent_deux_decks_sans_achat():
    partagee = card("Partagée", price=7.0)
    result = allocate([(DECK_A, [partagee]), (DECK_B, [partagee])], {"oracle-Partagée": 2})

    assert result["shopping_list"] == []
    assert result["total_cost_eur"] == 0
    # Les deux exemplaires sont placés : il n'en reste aucun de libre.
    assert result["remaining_copies"]["oracle-Partagée"] == 0


def test_un_exemplaire_en_trop_reste_disponible():
    # Le point du correctif : possédée en double, placée une fois, la carte doit
    # rester gratuite pour la suite — un simple ensemble de « cartes réservées »
    # la déclarerait payante.
    result = allocate([(DECK_A, [card("Sol Ring")])], {"oracle-Sol Ring": 2})

    assert result["remaining_copies"]["oracle-Sol Ring"] == 1


def test_les_terrains_de_base_ne_generent_jamais_d_achat():
    result = allocate([(DECK_A, [card("Marais", type_line="Basic Land — Swamp")])], {})

    assert result["shopping_list"] == []
    assert result["decks"][0]["to_buy_count"] == 0
