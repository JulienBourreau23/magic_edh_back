"""
Le catalogue des archétypes : lecture du JSON d'EDHREC, et chiffrage du coût.

Trois erreurs silencieuses sont visées ici, toutes rencontrées pour de vrai :

- prendre le mauvais champ pour le slug d'un archétype — EDHREC y range la
  carte qui illustre la vignette, pas l'archétype ;
- laisser tomber une section entière parce que son libellé a changé, ce qui
  appauvrit tous les viviers du projet sans qu'aucune alerte ne se lève ;
- chiffrer un montage sans filtrer sur l'identité de couleur, ce qui annonce un
  deck impossible pour un prix qui ne veut rien dire.
"""
import pytest

import db.archetypes as archetypes_db
from db.core import get_conn
import services.edhrec as edhrec
from services.edhrec import (MIN_ARCHETYPE_DECKS, WANTED_SECTIONS,
                             extract_recommendations, extract_tag_commanders,
                             extract_tag_index)


def _cardlists(sections: list[dict]) -> dict:
    return {"container": {"json_dict": {"cardlists": sections}}}


# Extrait réel du catalogue : le champ `slug` porte « skullclamp », la carte qui
# illustre la vignette du Tokens. C'est l'`url` qui nomme l'archétype.
CATALOGUE = _cardlists([{
    "header": "Tags By Popularity Sort",
    "cardviews": [
        {"name": "Tokens", "slug": "skullclamp", "url": "/tags/tokens",
         "num_decks": 203123},
        {"name": "+1/+1 Counters", "slug": "hardened-scales",
         "url": "/tags/plus-1-plus-1-counters", "num_decks": 165450},
        {"name": "Dandan", "slug": "dandan", "url": "/tags/dandan", "num_decks": 5},
    ],
}])


def test_le_slug_vient_de_l_url_pas_du_champ_slug():
    # Prendre `slug` aurait demandé `/pages/tags/skullclamp.json`, qui n'existe
    # pas — et le bucket répond 403, pas 404, donc l'erreur ne se lit même pas
    # comme une page absente.
    index = extract_tag_index(CATALOGUE)
    assert [entry["slug"] for entry in index] == ["tokens", "plus-1-plus-1-counters"]
    assert index[0]["label"] == "Tokens"


def test_la_queue_du_classement_est_ecartee():
    # « Dandan » à cinq decks n'est pas un archétype : son taux d'inclusion
    # serait calculé sur cinq listes.
    assert all(entry["deck_count"] >= MIN_ARCHETYPE_DECKS
               for entry in extract_tag_index(CATALOGUE))


def test_seuls_les_commandants_en_tete_sont_retenus():
    # « New Commanders » est une rubrique éditoriale : ce sont les sorties
    # récentes, pas les commandants qui portent l'archétype.
    payload = _cardlists([
        {"header": "New Commanders", "tag": "newcommanders",
         "cardviews": [{"id": "nouveau", "num_decks": 3, "potential_decks": 100}]},
        {"header": "Top Commanders", "tag": "topcommanders",
         "cardviews": [{"id": "krenko", "num_decks": 2582, "potential_decks": 203123}]},
    ])
    assert extract_tag_commanders(payload) == [("krenko", 2582, 203123)]


def test_la_section_des_artefacts_utilitaires_est_lue():
    # EDHREC écrit « Utility Artifacts », jamais « Artifacts ». Le libellé au
    # singulier ne correspondait à rien : la section entière était jetée, sur
    # les pages commandants comme sur les pages archétypes, et le vivier
    # perdait Skullclamp, les bottes et tous les moteurs à artefacts sans que
    # rien ne le signale.
    payload = _cardlists([{
        "header": "Utility Artifacts",
        "cardviews": [{"id": "skullclamp", "num_decks": 30, "potential_decks": 100,
                       "synergy": 0.19}],
    }])
    assert extract_recommendations(payload) == [("skullclamp", "Utility Artifacts",
                                                 0.19, 0.3)]
    assert "Artifacts" not in WANTED_SECTIONS


def test_les_terrains_restent_hors_du_vivier():
    # Le noyau du projet est non-terrain partout : la manabase se calcule, elle
    # ne s'achète pas. Faire entrer cinquante terrains par commandant changerait
    # le contenu de trois autres pages.
    payload = _cardlists([{"header": "Lands",
                           "cardviews": [{"id": "command-tower", "num_decks": 9,
                                          "potential_decks": 10}]}])
    assert extract_recommendations(payload) == []


# --- Le chiffrage, qui a besoin de la base ----------------------------------

def _base_joignable() -> bool:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


base = pytest.mark.skipif(not _base_joignable(),
                          reason="Postgres injoignable — ce chiffrage est en SQL.")


def _un_archetype_avec_un_commandant_etroit() -> tuple[str, dict]:
    """Un archétype où un commandant a une identité trop étroite pour remplir
    le noyau : c'est là que le filtre d'identité se voit."""
    if not archetypes_db.has_data():
        pytest.skip("Catalogue vide : lance `python scripts/sync_archetypes.py`.")
    for archetype in archetypes_db.list_all():
        for commander in archetypes_db.commanders_for(archetype["slug"]):
            if commander["core_size"] < archetypes_db.CORE_SLOTS:
                return archetype["slug"], commander
    pytest.skip("Aucun commandant étroit dans le catalogue synchronisé.")


@base
def test_l_identite_de_couleur_borne_le_noyau():
    # Sans le `<@`, tous les commandants d'un archétype atteindraient 63 cartes
    # — y compris un mono-rouge à qui on aurait compté des cartes bleues. Le
    # prix annoncé serait celui d'un deck impossible à jouer.
    slug, etroit = _un_archetype_avec_un_commandant_etroit()
    large = max(archetypes_db.commanders_for(slug),
                key=lambda row: len(row["color_identity"]))

    assert len(etroit["color_identity"]) < len(large["color_identity"])
    assert etroit["core_size"] < large["core_size"]


@base
def test_le_noyau_vaut_les_cartes_jouables_moins_le_commandant():
    """
    Compté indépendamment : les cartes de l'archétype que ce commandant peut
    légalement jouer, lui-même exclu. Un commandant très joué figure aussi
    dans les cartes de son archétype, et s'y compter lui-même lui offrirait un
    créneau gratuit — il occupe la zone de commandement, pas un des 63.
    """
    slug, etroit = _un_archetype_avec_un_commandant_etroit()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(DISTINCT ac.card_oracle_id) AS jouables
                FROM archetype_cards ac
                JOIN cards_cheapest c ON c.oracle_id = ac.card_oracle_id
                WHERE ac.archetype_slug = %(slug)s
                  AND c.legal_commander
                  AND c.type_line NOT LIKE 'Basic Land%%'
                  AND c.color_identity <@ %(identity)s::text[]
                  AND c.oracle_id <> %(commander)s::uuid
                """,
                {"slug": slug, "identity": etroit["color_identity"],
                 "commander": str(etroit["oracle_id"])},
            )
            jouables = cur.fetchone()["jouables"]

    assert etroit["core_size"] == jouables


@base
def test_deux_impressions_du_meme_commandant_ne_cassent_pas_la_synchro():
    """
    EDHREC référence ses commandants par `scryfall_id`, donc par impression :
    deux entrées peuvent viser la même carte. `ON CONFLICT DO UPDATE` touchait
    alors deux fois la même ligne dans une seule commande, Postgres refusait
    (`CardinalityViolation`) et **toute la synchronisation s'arrêtait** — pas
    seulement l'archétype fautif. Constaté sur le catalogue réel, au vingtième
    archétype.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT oracle_id::text, array_agg(scryfall_id::text) AS impressions
                FROM cards GROUP BY oracle_id HAVING count(*) > 1 LIMIT 1
                """
            )
            row = cur.fetchone()
    if row is None:
        pytest.skip("Aucune carte à plusieurs impressions en base.")

    premiere, seconde = row["impressions"][:2]
    slug = "_test-doublons"
    try:
        _, commandants = edhrec.store_archetype(
            slug, "Test", 1000, [],
            [(str(premiere), 300, 1000), (str(seconde), 120, 1000)],
        )
        assert commandants == 1

        garde = [c for c in archetypes_db.commanders_for(slug)
                 if str(c["oracle_id"]) == str(row["oracle_id"])]
        # L'impression la plus jouée l'emporte : c'est son compte qui nous
        # intéresse, pas celui d'une réimpression confidentielle.
        assert garde and garde[0]["num_decks"] == 300
    finally:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM archetypes WHERE slug = %s", (slug,))
