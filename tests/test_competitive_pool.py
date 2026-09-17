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


def test_chaque_vivier_respecte_la_banlist_de_son_format():
    """
    Ce test affirmait que le vivier duel est un **sous-ensemble** du vivier
    multi, au motif que « le Duel Commander bannit ce que le multi autorise, et
    jamais l'inverse ». C'est faux, et la base le prouve : dix-neuf cartes sont
    bannies en Commander multijoueur et légales en duel — Sylvan Primordial,
    Primeval Titan, Sundering Titan, et cinq créatures légendaires dont
    Griselbrand et Leovold.

    L'hypothèse avait tenu par chance : le commandant tiré n'était pas vert,
    donc aucune de ces cartes n'entrait dans son vivier.

    Le vrai invariant n'est pas un emboîtement mais une appartenance : chaque
    vivier ne contient que des cartes légales dans **son** format.
    """
    oracle_id, theme, identity = _un_commandant()

    for format, colonne in (("commander", "legal_commander"), ("duel", "legal_duel")):
        pool = themes_db.build_pool(oracle_id, theme, format, identity)
        assert pool, f"vivier vide en {format}"
        illégales = [c["name"] for c in pool if not c[colonne]]
        assert illégales == [], f"{format} : {illégales[:5]}"


def test_la_liste_des_commandants_depend_du_format():
    """
    La légalité d'un commandant n'est pas la même dans les deux formats, et
    dans les deux sens : Edgar Markov est légal en multi et banni en duel,
    Rofellos et Griselbrand l'inverse. Une liste unique laissait donc passer
    des commandants injouables jusqu'à l'écran de construction, et en cachait
    d'autres à jamais.
    """
    import db.commanders as commanders_db
    from db.core import get_conn

    multi = {str(c["oracle_id"]) for c in commanders_db.owned_commanders("commander")}
    duel = {str(c["oracle_id"]) for c in commanders_db.owned_commanders("duel")}

    with get_conn() as conn:
        with conn.cursor() as cur:
            for format, colonne, ids in (("commander", "legal_commander", multi),
                                         ("duel", "legal_duel", duel)):
                if not ids:
                    continue
                cur.execute(
                    f"SELECT name FROM cards_cheapest "
                    f"WHERE oracle_id = ANY(%s::uuid[]) AND NOT {colonne}",
                    (sorted(ids),),
                )
                illégaux = [r["name"] for r in cur.fetchall()]
                assert illégaux == [], f"{format} : {illégaux}"


def test_banni_comme_commandant_n_est_pas_banni_tout_court():
    """
    Le duel distingue deux interdictions que `legal_duel` seul confondait :
    bannie tout court, et bannie **comme commandant** en restant jouable dans
    les 99. Scryfall publie la seconde sous `restricted` ; le sync la traitait
    comme un bannissement, ce qui privait le format de 27 cartes.

    Geist of Saint Traft est le cas d'école : interdit comme commandant en Duel
    Commander, parfaitement jouable dans les 99.
    """
    from db.core import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, legal_duel, banned_as_commander_duel FROM cards_cheapest "
                "WHERE banned_as_commander_duel"
            )
            interdits = cur.fetchall()

    if not interdits:
        pytest.skip("migration_015 non jouée ou sync Scryfall non relancé")

    # Une carte bannie comme commandant reste légale dans le deck : si les deux
    # drapeaux disaient la même chose, la colonne ne servirait à rien.
    for carte in interdits:
        assert carte["legal_duel"], carte["name"]

    assert "Geist of Saint Traft" in {c["name"] for c in interdits}


def test_un_commandant_banni_a_ce_titre_sort_de_la_liste_duel():
    import db.commanders as commanders_db
    from db.core import get_conn

    duel = {str(c["oracle_id"]) for c in commanders_db.owned_commanders("duel")}
    if not duel:
        pytest.skip("aucun commandant possédé")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name FROM cards_cheapest "
                "WHERE oracle_id = ANY(%s::uuid[]) AND banned_as_commander_duel",
                (sorted(duel),),
            )
            fautifs = [r["name"] for r in cur.fetchall()]
    assert fautifs == [], fautifs
