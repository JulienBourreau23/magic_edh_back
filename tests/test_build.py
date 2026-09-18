"""
Atelier de construction et archivage.

Deux promesses faites à l'écran, et deux façons de les trahir en silence :
« rien n'est enregistré tant que tu ne cliques pas » — un brouillon qui
écrirait quand même remplirait la liste de decks sans prévenir — et
« archiver ne supprime rien » — un archivage qui perdrait les cartes ne se
verrait qu'au moment de désarchiver, trop tard.
"""
import pytest
from fastapi.testclient import TestClient

from auth import require_auth
import db.decks as decks_db
from db.core import get_conn
from main import app


def _base_joignable() -> bool:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _base_joignable(), reason="Postgres injoignable — ces endpoints lisent et écrivent."
)


@pytest.fixture
def client():
    app.dependency_overrides[require_auth] = lambda: "test"
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def brouillon(client):
    """Un commandant possédé et trois cartes de son vivier."""
    commanders = client.get("/build/commanders?format=commander").json()["commanders"]
    if not commanders:
        pytest.skip("aucun commandant dans la collection de cette base")
    chef = commanders[0]
    pool = client.get(f"/build/pool?commander={chef['oracle_id']}").json()["cards"]
    return {
        "format": "commander",
        "commander_scryfall_id": chef["scryfall_id"],
        "cards": [{"scryfall_id": chef["scryfall_id"], "quantity": 1}]
                 + [{"scryfall_id": card["scryfall_id"], "quantity": 1} for card in pool[:3]],
    }


def test_le_vivier_respecte_l_identite_de_couleur(client):
    commanders = client.get("/build/commanders?format=commander").json()["commanders"]
    if not commanders:
        pytest.skip("aucun commandant dans la collection de cette base")
    chef = commanders[0]
    identite = set(chef["color_identity"])

    pool = client.get(f"/build/pool?commander={chef['oracle_id']}").json()["cards"]

    # Une carte hors identité rendrait le deck illégal sans qu'aucun écran ne le
    # dise : c'est la règle que l'atelier doit garantir avant toute autre.
    assert all(set(card["color_identity"]) <= identite for card in pool)
    # Les terrains en font partie : la manabase se construit ici aussi.
    assert any("Land" in (card["type_line"] or "") for card in pool)


def test_evaluer_n_enregistre_rien(client, brouillon):
    avant = len(decks_db.list_decks())

    reponse = client.post("/build/evaluate", json=brouillon)

    assert reponse.status_code == 200, reponse.text
    assert "bracket" in reponse.json()
    assert len(decks_db.list_decks()) == avant


def test_enregistrer_puis_archiver_ne_perd_aucune_carte(client, brouillon):
    deck_id = client.post("/build/save", json={**brouillon, "name": "Deck de test"}).json()["deck_id"]
    try:
        cartes = decks_db.get_deck_cards(deck_id)
        assert len(cartes) == len(brouillon["cards"])
        assert sum(1 for carte in cartes if carte["is_commander"]) == 1

        actifs = {deck["id"] for deck in decks_db.list_decks()}
        assert deck_id in actifs

        client.post(f"/decks/{deck_id}/archive")
        assert deck_id not in {deck["id"] for deck in decks_db.list_decks()}
        assert deck_id in {deck["id"] for deck in decks_db.list_decks(archived=True)}
        # Archiver ne parle que de ce qu'on joue : les cartes sont intactes.
        assert len(decks_db.get_deck_cards(deck_id)) == len(cartes)

        client.post(f"/decks/{deck_id}/archive?archived=false")
        assert deck_id in {deck["id"] for deck in decks_db.list_decks()}
    finally:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM decks WHERE id = %s", (deck_id,))
