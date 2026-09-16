"""
Liste de recherche → collection.

Le geste « c'est acheté » écrit dans deux tables. S'il se passait mal, la carte
serait perdue des deux côtés ou comptée deux fois — et comme la collection
pilote toutes les listes d'achats, l'erreur se paierait en argent. Ces tests
ont besoin de Postgres et se sautent proprement sans lui.
"""
import pytest

import db.collection as collection_db
import db.wishlist as wishlist_db
from db.core import get_conn


def _base_joignable() -> bool:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _base_joignable(), reason="Postgres injoignable — ces écritures sont transactionnelles."
)


@pytest.fixture
def carte():
    """Une carte réelle, remise dans son état d'origine après le test."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT oracle_id, scryfall_id FROM cards_cheapest "
                        "WHERE NOT type_line LIKE 'Basic Land%' ORDER BY name LIMIT 1")
            row = cur.fetchone()
    oracle_id = str(row["oracle_id"])
    avant = collection_db.quantities().get(oracle_id, 0)

    yield oracle_id, str(row["scryfall_id"])

    wishlist_db.set_quantity(oracle_id, 0)
    collection_db.set_quantity(oracle_id, avant)


def test_acheter_deplace_la_carte(carte):
    oracle_id, scryfall_id = carte
    avant = collection_db.quantities().get(oracle_id, 0)
    wishlist_db.add([(oracle_id, scryfall_id, 1, None)])

    assert wishlist_db.acquire(oracle_id) == {"moved": 1, "remaining": 0}
    assert collection_db.quantities().get(oracle_id, 0) == avant + 1
    assert [row for row in wishlist_db.list_all() if str(row["oracle_id"]) == oracle_id] == []


def test_acheter_une_partie_laisse_le_reste(carte):
    # Deux exemplaires cherchés, un seul trouvé en boutique.
    oracle_id, scryfall_id = carte
    avant = collection_db.quantities().get(oracle_id, 0)
    wishlist_db.add([(oracle_id, scryfall_id, 3, None)])

    assert wishlist_db.acquire(oracle_id, 1) == {"moved": 1, "remaining": 2}
    assert collection_db.quantities().get(oracle_id, 0) == avant + 1
    restant = next(row for row in wishlist_db.list_all() if str(row["oracle_id"]) == oracle_id)
    assert restant["quantity"] == 2


def test_acheter_plus_que_cherche_ne_multiplie_pas(carte):
    # Demander 10 alors qu'on en cherchait 2 ne doit pas en créer 10.
    oracle_id, scryfall_id = carte
    avant = collection_db.quantities().get(oracle_id, 0)
    wishlist_db.add([(oracle_id, scryfall_id, 2, None)])

    assert wishlist_db.acquire(oracle_id, 10) == {"moved": 2, "remaining": 0}
    assert collection_db.quantities().get(oracle_id, 0) == avant + 2


def test_acheter_une_carte_absente_ne_touche_a_rien(carte):
    oracle_id, _ = carte
    avant = collection_db.quantities().get(oracle_id, 0)

    assert wishlist_db.acquire(oracle_id) is None
    assert collection_db.quantities().get(oracle_id, 0) == avant


def test_les_quantites_s_additionnent(carte):
    # Vouloir une carte pour deux decks, c'est en vouloir deux.
    oracle_id, scryfall_id = carte
    wishlist_db.add([(oracle_id, scryfall_id, 1, "deck A")])
    wishlist_db.add([(oracle_id, scryfall_id, 1, "deck B")])

    ligne = next(row for row in wishlist_db.list_all() if str(row["oracle_id"]) == oracle_id)
    assert ligne["quantity"] == 2
    # La note la plus récente l'emporte : c'est elle qui explique la présence.
    assert ligne["note"] == "deck B"
