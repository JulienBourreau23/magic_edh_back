"""
Remplacer un achat conseillé par une carte qu'on possède déjà.

L'intention : essayer un archétype avec ce qu'on a avant de dépenser. Les
erreurs possibles sont toutes silencieuses — un remplaçant qu'on ne possède
pas, hors identité de couleur, ou déjà dans la liste, produirait une decklist
injouable sans qu'aucune alerte ne se déclenche.
"""
import pytest

import db.commanders as commanders_db
from db.core import get_conn
from services.card_categories import is_land
from services.deck_ideas import deck_idea_detail


def _base_joignable() -> bool:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _base_joignable(), reason="Postgres injoignable — ce vivier se calcule en base."
)


@pytest.fixture(scope="module")
def detail() -> dict:
    commandants = commanders_db.owned_commanders()
    if not commandants:
        pytest.skip("aucun commandant possédé")
    for commander in commandants:
        result = deck_idea_detail(str(commander["oracle_id"]))
        if result and result["substitutes"]:
            return result
    pytest.skip("aucun commandant avec des remplaçants possédés")


def test_un_commandant_non_possede_n_a_pas_de_detail():
    assert deck_idea_detail("00000000-0000-0000-0000-000000000000") is None


def test_tous_les_remplacants_sont_possedes(detail):
    # C'est toute la raison d'être du vivier : proposer un achat ici viderait
    # la fonctionnalité de son sens.
    for card in detail["substitutes"]:
        assert card["owned_quantity"] > 0, card["name"]


def test_aucun_remplacant_n_est_deja_dans_la_liste(detail):
    déjà = {str(card["oracle_id"]) for card in detail["core"]}
    déjà.add(str(detail["commander"]["oracle_id"]))
    for card in detail["substitutes"]:
        assert str(card["oracle_id"]) not in déjà, card["name"]


def test_les_remplacants_respectent_l_identite_de_couleur(detail):
    identité = set(detail["commander"]["color_identity"])
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT oracle_id, name, color_identity FROM cards_cheapest "
                "WHERE oracle_id = ANY(%s::uuid[])",
                ([str(c["oracle_id"]) for c in detail["substitutes"]],),
            )
            for row in cur.fetchall():
                assert set(row["color_identity"]) <= identité, row["name"]


def test_aucun_terrain_parmi_les_remplacants(detail):
    # Le noyau visé est non-terrain : remplacer un rocher de mana par une forêt
    # ne remplirait pas le créneau, elle en créerait un autre.
    for card in detail["substitutes"]:
        assert not is_land(card), card["name"]


def test_le_noyau_dit_ce_qui_est_possede(detail):
    assert len(detail["core"]) <= detail["nonland_core"]
    # Le drapeau doit correspondre à la quantité, sinon l'écran proposerait de
    # remplacer une carte qu'on a déjà.
    for card in detail["core"]:
        assert card["owned"] == (card["owned_quantity"] > 0), card["name"]


def test_les_remplacants_portent_leur_role(detail):
    """
    Le rôle sert à remplacer comme par comme : échanger un removal contre un
    rocher de mana dépannerait le budget en déséquilibrant le deck.
    """
    assert any(card["categories"] for card in detail["substitutes"]), \
        "aucun remplaçant classé : le rôle ne pourrait jamais être respecté"


def test_la_synergie_distingue_la_carte_du_deck_de_la_bonne_carte(detail):
    """
    La synergie EDHREC est l'écart entre « jouée avec ce commandant » et
    « jouée dans cette couleur en général ». Sol Ring est partout, donc
    synergique avec personne ; une carte de niche jouée surtout ici l'est
    beaucoup. Confondre les deux ferait remonter les mêmes dix cartes sur
    tous les decks.
    """
    import db.commanders as commanders_db

    commandant = str(detail["commander"]["oracle_id"])
    cartes = [str(c["oracle_id"]) for c in detail["core"]]
    rangées = commanders_db.synergies_for_deck(commandant, cartes)
    if not rangées:
        pytest.skip("ce commandant n'a pas de données EDHREC")

    # Classement décroissant : c'est ce que l'affichage suppose.
    valeurs = [float(r["synergy"]) for r in rangées if r["synergy"] is not None]
    assert valeurs == sorted(valeurs, reverse=True)

    # Une carte ubiquitaire ne doit pas trôner en tête. Sol Ring est le témoin.
    par_nom = {r["name"]: float(r["synergy"] or 0) for r in rangées}
    if "Sol Ring" in par_nom and len(valeurs) > 3:
        assert par_nom["Sol Ring"] < max(valeurs), \
            "Sol Ring en tête des synergies : c'est la popularité qui est mesurée, pas la synergie"


def test_aucune_synergie_sans_donnees_edhrec():
    # Un commandant inconnu du catalogue ne doit pas faire échouer la fiche :
    # la liste est vide, et l'interface masque la section.
    import db.commanders as commanders_db

    assert commanders_db.synergies_for_deck(
        "00000000-0000-0000-0000-000000000000", ["00000000-0000-0000-0000-000000000001"]
    ) == []
