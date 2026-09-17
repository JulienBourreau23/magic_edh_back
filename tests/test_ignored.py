"""
Cartes refusées pour un deck.

Une erreur ici est doublement silencieuse : soit une carte refusée revient
sans qu'on comprenne pourquoi, soit — bien pire — une carte disparaît des
conseils sans que rien ne l'explique. Le second cas ne lève aucune alerte et
ne se remarque qu'au bout de plusieurs semaines.

Tests contre la vraie base, comme pour les autres listes d'achats : c'est elle
qui décide du contenu des conseils.
"""
import pytest
from fastapi.testclient import TestClient

import db.decks as decks_db
import db.ignored as ignored_db
from auth import require_auth
from db.core import get_conn
from main import app


def _base_joignable() -> bool:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM deck_ignored_cards LIMIT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _base_joignable(),
    reason="Postgres injoignable ou migration_014 non jouée.",
)


@pytest.fixture
def client():
    app.dependency_overrides[require_auth] = lambda: "test"
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def deck_id() -> int:
    decks = decks_db.list_decks()
    if not decks:
        pytest.skip("aucun deck en base")
    return decks[0]["id"]


def _proposed(client, deck_id, **params) -> list[dict]:
    body = client.get(f"/decks/{deck_id}/suggestions", params=params).json()
    return [card for group in body.get("to_add", []) for card in group["candidates"]]


def test_une_carte_refusee_ne_revient_plus_dans_les_ajouts(client, deck_id):
    proposées = _proposed(client, deck_id)
    if not proposées:
        pytest.skip("ce deck ne reçoit aucune proposition d'ajout")
    cible = proposées[0]
    oracle_id = str(cible["oracle_id"])

    try:
        assert client.post(f"/decks/{deck_id}/ignored",
                           json={"oracle_id": oracle_id}).status_code == 200
        après = _proposed(client, deck_id)
        assert oracle_id not in {str(c["oracle_id"]) for c in après}
    finally:
        client.delete(f"/decks/{deck_id}/ignored/{oracle_id}")

    # Le refus doit être réversible, sinon la carte est perdue pour de bon.
    revenues = {str(c["oracle_id"]) for c in _proposed(client, deck_id)}
    assert oracle_id in revenues


def test_le_refus_sort_aussi_des_retraits(client, deck_id):
    # Viser le bracket 1 force des retraits : les Game Changers du deck.
    body = client.get(f"/decks/{deck_id}/suggestions",
                      params={"target_bracket": 1}).json()
    cuts = body.get("to_cut", [])
    if not cuts:
        pytest.skip("ce deck n'a rien à retirer pour viser le bracket 1")
    oracle_id = str(cuts[0]["card"]["oracle_id"])

    try:
        client.post(f"/decks/{deck_id}/ignored",
                    json={"oracle_id": oracle_id, "reason": "je la garde"})
        après = client.get(f"/decks/{deck_id}/suggestions",
                           params={"target_bracket": 1}).json()
        restants = {str(c["card"]["oracle_id"]) for c in après["to_cut"]}
        assert oracle_id not in restants
    finally:
        client.delete(f"/decks/{deck_id}/ignored/{oracle_id}")


def test_le_refus_est_idempotent(client, deck_id):
    # Contrairement à la collection et à la liste de recherche, où les
    # quantités s'additionnent : refuser deux fois ne doit rien doubler.
    oracle_id = "00000000-0000-0000-0000-0000000000ff"
    try:
        client.post(f"/decks/{deck_id}/ignored", json={"oracle_id": oracle_id})
        client.post(f"/decks/{deck_id}/ignored", json={"oracle_id": oracle_id})
        assert ignored_db.oracle_ids(deck_id).count(oracle_id) == 1
    finally:
        ignored_db.remove(deck_id, oracle_id)


def test_un_refus_ne_vaut_que_pour_son_deck(client):
    decks = decks_db.list_decks()
    if len(decks) < 2:
        pytest.skip("il faut deux decks pour vérifier l'isolation")
    premier, second = decks[0]["id"], decks[1]["id"]
    oracle_id = "00000000-0000-0000-0000-0000000000fe"

    try:
        ignored_db.add(premier, oracle_id)
        assert oracle_id in ignored_db.oracle_ids(premier)
        assert oracle_id not in ignored_db.oracle_ids(second)
    finally:
        ignored_db.remove(premier, oracle_id)


def test_annuler_un_refus_inexistant_est_un_404(client, deck_id):
    réponse = client.delete(
        f"/decks/{deck_id}/ignored/00000000-0000-0000-0000-0000000000fd")
    assert réponse.status_code == 404


def test_la_liste_des_refus_accompagne_les_conseils(client, deck_id):
    """
    Une liste de refus invisible serait un piège : dans six mois, plus moyen de
    savoir pourquoi une carte ne remonte jamais.
    """
    oracle_id = str(decks_db.get_deck_cards(deck_id)[0]["oracle_id"])
    try:
        client.post(f"/decks/{deck_id}/ignored",
                    json={"oracle_id": oracle_id, "reason": "essai"})
        body = client.get(f"/decks/{deck_id}/suggestions").json()
        assert body["ignored_count"] >= 1
        refusées = {str(c["oracle_id"]) for c in body["ignored"]}
        assert oracle_id in refusées
        # La carte est affichable : nom et visuel, pas seulement un identifiant.
        citée = next(c for c in body["ignored"] if str(c["oracle_id"]) == oracle_id)
        assert citée["name"]
        assert citée["reason"] == "essai"
    finally:
        client.delete(f"/decks/{deck_id}/ignored/{oracle_id}")


def test_le_refus_vaut_aussi_pour_l_equilibrage(client):
    """
    Les deux écrans qui modifient un deck partagent `find_candidates` : si le
    filtre n'était posé que sur les suggestions, l'équilibrage reproposerait
    aussitôt la carte refusée, sans que rien ne signale la contradiction.
    """
    decks = decks_db.list_decks()[:2]
    if not decks:
        pytest.skip("aucun deck en base")
    ids = ",".join(str(d["id"]) for d in decks)

    body = client.get("/balance", params={"decks": ids, "max_price": 50}).json()
    proposées = [(plan["deck_id"], card)
                 for plan in body.get("plans", [])
                 for group in plan["adds"]
                 for card in group["candidates"]]
    if not proposées:
        pytest.skip("aucune proposition d'ajout sur ces decks")

    deck_id, cible = proposées[0]
    oracle_id = str(cible["oracle_id"])
    try:
        ignored_db.add(deck_id, oracle_id, "test")
        après = client.get("/balance", params={"decks": ids, "max_price": 50}).json()
        encore = {
            str(card["oracle_id"])
            for plan in après["plans"] if plan["deck_id"] == deck_id
            for group in plan["adds"] for card in group["candidates"]
        }
        assert oracle_id not in encore
    finally:
        ignored_db.remove(deck_id, oracle_id)
