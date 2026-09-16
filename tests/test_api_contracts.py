"""
Contrats HTTP des endpoints d'écriture.

Ces tests existent à cause d'une panne réelle : le client envoyait un corps
JSON **doublement sérialisé**, l'API répondait 422, et rien ne l'avait vu —
les tests appelaient les fonctions de routeur directement, en sautant la
validation Pydantic, c'est-à-dire précisément la couche qui refusait.

On passe donc par une vraie requête HTTP. L'authentification est neutralisée
par `dependency_overrides` : ce qu'on vérifie ici est la forme du corps, pas
le jeton.
"""
import pytest
from fastapi.testclient import TestClient

from auth import require_auth
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
    not _base_joignable(), reason="Postgres injoignable — ces endpoints écrivent en base."
)


@pytest.fixture
def client():
    app.dependency_overrides[require_auth] = lambda: "test"
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def carte():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT oracle_id, scryfall_id FROM cards_cheapest "
                        "WHERE NOT type_line LIKE 'Basic Land%' ORDER BY name LIMIT 1")
            row = cur.fetchone()
    return str(row["oracle_id"]), str(row["scryfall_id"])


def test_ajout_a_la_liste_de_recherche(client, carte):
    oracle_id, scryfall_id = carte
    try:
        reponse = client.post("/wishlist", json={"scryfall_id": scryfall_id, "quantity": 1})
        assert reponse.status_code == 200, reponse.text
        noms = [row["oracle_id"] for row in client.get("/wishlist").json()["cards"]]
        assert oracle_id in noms
    finally:
        client.delete(f"/wishlist/{oracle_id}")


def test_un_corps_deja_serialise_est_refuse(client, carte):
    # La faute exacte qui a produit le 422 : `JSON.stringify` côté client, sur
    # un corps que la couche HTTP sérialise déjà. Le test la fige comme une
    # erreur du client, pas du serveur.
    _, scryfall_id = carte
    reponse = client.post("/wishlist", json='{"scryfall_id": "%s", "quantity": 1}' % scryfall_id)
    assert reponse.status_code == 422


def test_quantite_hors_bornes_refusee(client, carte):
    _, scryfall_id = carte
    assert client.post("/wishlist", json={"scryfall_id": scryfall_id,
                                         "quantity": 0}).status_code == 422


def test_carte_inconnue(client):
    reponse = client.post("/wishlist",
                          json={"scryfall_id": "00000000-0000-0000-0000-000000000000"})
    assert reponse.status_code == 404


def test_la_fiche_deck_expose_le_diagnostic_de_manabase(client):
    """
    Le conseil de manabase traverse HTTP entier : il contient des flottants
    arrondis et une clé qui vaut parfois None, deux formes qu'une sérialisation
    peut abîmer sans que le calcul soit en cause.
    """
    decks = client.get("/decks").json()
    if not decks:
        pytest.skip("aucun deck en base")

    manabase = client.get(f"/decks/{decks[0]['id']}").json()["manabase"]

    assert isinstance(manabase["stuck_cards"], (int, float))
    assert manabase["strained_total"] >= len(manabase["strained_cards"])
    for color in manabase["colors"].values():
        assert color["target"] >= 0
        assert color["shortfall"] == max(0, color["target"] - color["sources"])

    advice = manabase["basic_lands"]
    if advice is not None:
        # Un échange, jamais un achat : le total de basiques est conservé.
        assert sum(advice["suggested"].values()) == sum(advice["current"].values())
        assert advice["stuck_after"] <= advice["stuck_before"]
