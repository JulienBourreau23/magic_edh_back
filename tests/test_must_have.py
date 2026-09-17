"""
La liste « cartes à avoir » est une liste d'achats : une erreur y coûte de
l'argent ou fait rater une carte, sans jamais lever d'alerte.

Les règles vérifiées ici sont celles qui se trompent en silence — le plafond
qui déborde, une carte sans prix proposée à l'achat, un terrain de base dans
une liste de courses, ou la banlist du duel qui laisserait passer un Sol Ring.
Elles portent sur les données réelles plutôt que sur un jeu de test : c'est la
base qui décide du contenu, et une règle juste sur des cartes inventées ne
prouverait rien.
"""
import pytest

from db.core import get_conn
from services.must_have import DEFAULT_MAX_PRICE_EUR, must_have


def _base_joignable() -> bool:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _base_joignable(), reason="Postgres injoignable — cette liste se calcule en base."
)


@pytest.fixture(scope="module")
def liste() -> dict:
    return must_have()


def _toutes_les_cartes(resultat: dict) -> list[dict]:
    return [card for group in resultat["groups"] for card in group["cards"]]


def test_aucun_achat_ne_depasse_le_plafond(liste):
    for card in _toutes_les_cartes(liste):
        if card["owned"] == 0:
            assert card["price_eur"] is not None, f"{card['name']} : prix inconnu, donc non achetable"
            assert float(card["price_eur"]) <= DEFAULT_MAX_PRICE_EUR, card["name"]


def test_une_carte_possedee_reste_quel_que_soit_son_prix(liste):
    # Le plafond ne concerne que les achats : rien ne reproche à la collection
    # de contenir des cartes chères. Sans cette règle, une carte possédée à
    # 80 € disparaîtrait de la liste alors qu'elle est déjà acquise.
    assert [c for c in _toutes_les_cartes(liste) if c["owned"] > 0], \
        "la collection devrait recouper le haut du classement"

    # Un plafond d'un centime ne laisse rien d'achetable : tout ce qui reste
    # est donc là parce qu'il est possédé, et non malgré son prix. C'est la
    # seule formulation qui prouve la règle sans dépendre du contenu réel de
    # la collection.
    ruine = _toutes_les_cartes(must_have(max_price=0.01))
    assert ruine, "les cartes possédées devraient survivre à n'importe quel plafond"
    chers = [c for c in ruine if c["price_eur"] is None or float(c["price_eur"]) > 0.01]
    assert chers, "le jeu de données ne prouve rien si tout coûte moins d'un centime"
    assert all(c["owned"] > 0 for c in chers)


def test_aucun_terrain_de_base(liste):
    terrains = next(g for g in liste["groups"] if g["key"] == "land")
    for card in terrains["cards"]:
        assert "Basic Land" not in card["type_line"], card["name"]


def test_le_plafond_plus_bas_reduit_la_liste_et_augmente_le_compte_ecarte():
    large = must_have(max_price=50)
    etroit = must_have(max_price=1)

    achats_larges = sum(g["to_buy_count"] for g in large["groups"])
    achats_etroits = sum(g["to_buy_count"] for g in etroit["groups"])
    assert achats_etroits < achats_larges

    # Ce qui sort de la liste doit être compté, sinon elle se ferait passer
    # pour un classement complet.
    assert sum(g["over_budget"] for g in etroit["groups"]) > \
        sum(g["over_budget"] for g in large["groups"])


def test_le_duel_est_plus_restrictif_que_le_multi():
    # `legal_duel` est toujours plus restrictif que `legal_commander`, jamais
    # l'inverse. Sol Ring est le cas d'école : premier des artefacts en
    # multijoueur, banni en duel.
    multi = {c["oracle_id"] for c in _toutes_les_cartes(must_have(format="commander"))}
    duel = {c["oracle_id"] for c in _toutes_les_cartes(must_have(format="duel"))}

    noms_duel = {c["name"] for c in _toutes_les_cartes(must_have(format="duel"))}
    assert "Sol Ring" not in noms_duel
    assert "Sol Ring" in {c["name"] for c in _toutes_les_cartes(must_have(format="commander"))}
    # Le duel ne fait pas qu'enlever : les places libérées sont reprises par
    # des cartes moins jouées, donc les deux ensembles ne s'emboîtent pas.
    assert duel - multi, "le duel devrait remonter des cartes que le multi ne montre pas"


def test_les_planeswalkers_sont_plafonnes_a_trente(liste):
    pw = next(g for g in liste["groups"] if g["key"] == "planeswalker")
    assert pw["top"] == 30
    assert len(pw["cards"]) <= 30


def test_le_classement_suit_la_popularite(liste):
    for group in liste["groups"]:
        rangs = [c["edhrec_rank"] for c in group["cards"]]
        assert rangs == sorted(rangs), group["label"]


def test_ce_qui_est_deja_cherche_est_signale():
    """
    Sans ce champ, la page laisserait ajouter deux fois la même carte à la
    liste de recherche : les quantités s'additionnent, donc le second clic
    demanderait un second exemplaire sans que rien ne l'indique.
    """
    import db.wishlist as wishlist_db

    cible = next(c for c in _toutes_les_cartes(must_have()) if c["wanted"] == 0)
    oracle_id = str(cible["oracle_id"])

    wishlist_db.add([(oracle_id, cible["scryfall_id"], 1, "test")])
    try:
        apres = {c["oracle_id"]: c["wanted"] for c in _toutes_les_cartes(must_have())}
        assert apres[cible["oracle_id"]] == 1
    finally:
        wishlist_db.set_quantity(oracle_id, 0)

    # Et l'état revient bien à zéro une fois la carte retirée.
    rendu = {c["oracle_id"]: c["wanted"] for c in _toutes_les_cartes(must_have())}
    assert rendu[cible["oracle_id"]] == 0


# --- récapitulatif de collection ------------------------------------------

def test_le_recapitulatif_ignore_le_plafond_de_prix():
    """
    `/must-have` répond « qu'est-ce que je peux acheter », le récapitulatif
    « où en est ma collection face à ce qui se joue ». Filtrer par prix ici
    gonflerait la couverture : les cartes chères non possédées sortiraient du
    dénominateur, donc le pourcentage monterait sans qu'on ait rien acquis.
    """
    from services.must_have import coverage

    récap = coverage()
    sous_plafond = must_have(max_price=1)

    for groupe, filtré in zip(récap["groups"], sous_plafond["groups"]):
        assert groupe["listed"] >= len(filtré["cards"]), groupe["label"]

    # Une carte hors plafond doit bien figurer dans le récapitulatif.
    chères = [c for g in récap["groups"] for c in g["cards"]
              if c["owned"] == 0 and c["price_eur"] is not None and float(c["price_eur"]) > 50]
    assert chères, "le classement réel devrait contenir des cartes au-dessus du plafond"


def test_le_denominateur_est_la_taille_reelle_de_la_liste():
    # Les Batailles sont moins de cinquante en tout : afficher « 0 / 50 »
    # laisserait croire à un manque inexistant.
    from services.must_have import coverage

    for groupe in coverage()["groups"]:
        assert groupe["listed"] == len(groupe["cards"])
        assert groupe["owned"] <= groupe["listed"]


def test_les_tranches_de_popularite_couvrent_la_collection_classee():
    """
    Une carte sans rang EDHREC n'est pas une carte mal classée : c'est une
    absence de mesure. La ranger avec les moins jouées inventerait une
    information, donc elle n'est comptée nulle part.
    """
    from services.must_have import rank_distribution
    from db.core import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS n FROM collection col
                JOIN cards_cheapest c ON c.oracle_id = col.oracle_id
                WHERE c.edhrec_rank IS NOT NULL
            """)
            classées = cur.fetchone()["n"]

    assert sum(b["cards"] for b in rank_distribution()) == classées
