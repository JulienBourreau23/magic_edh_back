"""
Les trois filtres durs de la construction compétitive, appliqués en SQL :
banlist du format, identité de couleur, exclusion des terrains de base.

« Le deck DOIT impérativement respecter la banlist » — ces tests sont là pour
que ça reste vrai après n'importe quelle retouche de la requête. Ils ont besoin
de Postgres et se sautent proprement sans lui.
"""
import pytest

import db.themes as themes_db
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
    not _base_joignable(),
    reason="Postgres injoignable — ces filtres sont écrits en SQL.",
)


def _un_commandant() -> tuple[str, str, list[str]]:
    """Un commandant qui a des thèmes synchronisés, sinon rien à vérifier."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.commander_oracle_id, t.slug, c.color_identity
                FROM commander_themes t
                JOIN cards_cheapest c ON c.oracle_id = t.commander_oracle_id
                ORDER BY t.deck_count DESC LIMIT 1
                """
            )
            row = cur.fetchone()
    if row is None:
        pytest.skip("Aucun thème en base : lance `python scripts/sync_edhrec.py`.")
    return str(row["commander_oracle_id"]), row["slug"], row["color_identity"]


@pytest.mark.parametrize("format", ["commander", "duel"])
def test_le_vivier_ne_contient_que_des_cartes_legales(format):
    oracle_id, theme, identity = _un_commandant()
    pool = themes_db.build_pool(oracle_id, theme, format, identity)

    assert pool, "vivier vide : la requête ne prouve rien"
    colonne = themes_db.LEGALITY_COLUMNS[format]
    illegales = [card["name"] for card in pool if not card[colonne]]
    assert illegales == []


def test_le_vivier_respecte_l_identite_de_couleur():
    oracle_id, theme, identity = _un_commandant()
    pool = themes_db.build_pool(oracle_id, theme, "commander", identity)

    hors_identite = [card["name"] for card in pool
                     if not set(card["color_identity"]) <= set(identity)]
    assert hors_identite == []


def test_le_vivier_exclut_les_terrains_de_base_et_le_commandant():
    oracle_id, theme, identity = _un_commandant()
    pool = themes_db.build_pool(oracle_id, theme, "commander", identity)

    assert [c["name"] for c in pool if (c["type_line"] or "").startswith("Basic Land")] == []
    assert str(oracle_id) not in {str(card["oracle_id"]) for card in pool}


def test_le_duel_est_plus_restrictif_que_le_multi():
    # Duel Commander bannit ce que le multi autorise (Sol Ring, Ancient Tomb) ;
    # l'inverse n'existe pas. Le vivier duel est donc un sous-ensemble.
    oracle_id, theme, identity = _un_commandant()
    multi = {str(c["oracle_id"]) for c in themes_db.build_pool(oracle_id, theme, "commander", identity)}
    duel = {str(c["oracle_id"]) for c in themes_db.build_pool(oracle_id, theme, "duel", identity)}
    assert duel <= multi
