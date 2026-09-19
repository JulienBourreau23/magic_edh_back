"""
Banlists, Game Changers, et le système de brackets tel qu'il est affiché.

L'erreur visée ici se paie en partie, pas en argent : une banlist fausse
laisse construire un deck illégal, ou fait retirer une carte qui ne l'est pas.
Trois pièges, tous rencontrés en écrivant la page :

- confondre « bannie » et « n'a jamais été jouable en tournoi » : le booléen
  `legal_commander` désigne 2 327 cartes, la banlist en compte cinquante-huit ;
- juger l'édition d'une carte sur l'impression que la vue retient : la moins
  chère de Black Lotus est un proxy anniversaire, ce qui le ferait disparaître
  de la banlist ;
- laisser le texte des brackets diverger du moteur qui les calcule.
"""
import pytest

import db.rules as rules_db
from db.core import get_conn
from services import bracket_rules


def _base_joignable() -> bool:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


base = pytest.mark.skipif(not _base_joignable(),
                          reason="Postgres injoignable — ces listes sont en SQL.")


def _donnees() -> None:
    if not rules_db.has_data():
        pytest.skip("Colonnes de banlist vides : lance `python scripts/sync_scryfall.py`.")


# --- Les banlists -----------------------------------------------------------

@base
@pytest.mark.parametrize("format", ["commander", "duel"])
def test_une_banlist_n_est_pas_l_ensemble_des_cartes_illegales(format):
    _donnees()
    bannies = rules_db.banlist(format)["cards"]
    colonne = {"commander": "legal_commander", "duel": "legal_duel"}[format]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(DISTINCT oracle_id) AS n FROM cards WHERE NOT {colonne}")
            illegales = cur.fetchone()["n"]

    # Le rapport est de l'ordre de 1 à 40 : tout le reste, ce sont des cartes
    # qui n'ont jamais existé en tournoi, pas des cartes interdites.
    assert 0 < len(bannies) < illegales / 10


@base
def test_black_lotus_reste_dans_la_banlist():
    """
    Son impression la moins chère est un proxy « 30th Anniversary », donc une
    édition hors tournoi. Juger sur elle — c'est-à-dire sur `cards_cheapest` —
    retirerait de la banlist la carte la plus célèbre du jeu, avec les cinq
    Moxen, Ancestral Recall et Chaos Orb.
    """
    _donnees()
    noms = {c["name"] for c in rules_db.banlist("commander")["cards"]}
    assert {"Black Lotus", "Ancestral Recall", "Mox Sapphire", "Chaos Orb"} <= noms


@base
def test_les_cartes_hors_tournoi_sont_a_part_et_pas_perdues():
    _donnees()
    duel = rules_db.banlist("duel")
    hors = {c["name"] for c in duel["outside_tournament"]}
    reelles = {c["name"] for c in duel["cards"]}

    assert hors and reelles
    assert not (hors & reelles), "une carte ne peut pas être dans les deux listes"
    # Les Stickers d'Unfinity sont le cas d'école : bannis, mais personne ne
    # les cherche dans une banlist.
    assert any("Stickers" in (c["type_line"] or "") for c in duel["outside_tournament"])


@base
def test_les_deux_formats_ne_se_deduisent_pas_l_un_de_l_autre():
    """
    `legal_duel` n'est **pas** un sous-ensemble de `legal_commander`. Le duel
    est plus strict dans l'ensemble, mais il autorise des cartes que le
    multijoueur bannit — Dockside Extortionist, Griselbrand, Leovold. Déduire
    une banlist de l'autre ferait un écran faux dans les deux sens.
    """
    _donnees()
    multi = {c["name"] for c in rules_db.banlist("commander")["cards"]}
    duel = {c["name"] for c in rules_db.banlist("duel")["cards"]}

    assert multi - duel, "aucune carte bannie en multi et légale en duel : suspect"
    assert duel - multi
    assert multi & duel


@base
def test_banni_comme_commandant_n_est_pas_banni():
    """Le duel interdit 27 cartes au seul titre de commandant : elles restent
    jouables dans les 99, donc hors de la banlist."""
    _donnees()
    commandant_seul = rules_db.banned_as_commander("duel")
    bannies = {c["name"] for c in rules_db.banlist("duel")["cards"]}

    assert commandant_seul
    assert not ({c["name"] for c in commandant_seul} & bannies)
    assert all(c["legal_duel"] for c in commandant_seul)
    # Le multijoueur n'a pas d'équivalent : une liste vide, pas une colonne
    # toujours fausse.
    assert rules_db.banned_as_commander("commander") == []


@base
def test_les_game_changers_sont_la_liste_officielle():
    _donnees()
    gc = rules_db.game_changers()
    assert all(c["game_changer"] for c in gc)
    # Liste courte et fermée : si elle explose, c'est que la colonne a changé
    # de sens au dernier sync.
    assert 20 < len(gc) < 200


# --- Les brackets -----------------------------------------------------------

def test_la_page_des_brackets_suit_le_moteur_et_non_un_texte():
    """
    Les verdicts affichés sont produits en exécutant `bracket_estimate` sur un
    deck minimal par critère. Recopier « 4 Game Changers font un bracket 4 »
    dans une phrase l'aurait laissé dériver le jour où le seuil bouge.
    """
    decrit = bracket_rules.describe()
    verdicts = {c["key"]: c["demonstration"] for c in decrit["criteria"]}

    assert verdicts["game_changers"]["min"] == 3
    assert verdicts["game_changers_4"]["min"] == 4
    # Le critère le plus punitif du système : un seul Armageddon, aucun Game
    # Changer, et le deck est déjà bracket 4.
    assert verdicts["mass_land_denial"]["min"] == 4
    # Les tours supplémentaires ne ferment que le bracket 1.
    assert verdicts["extra_turns"]["min"] == 2 and verdicts["extra_turns"]["max"] == 2
    assert verdicts["combos"]["min"] == 3
    assert "1-2" in decrit["baseline"]["verdict"]


def test_ce_qui_n_est_pas_mesure_est_nomme():
    """Le stax et les tuteurs ne pèsent pas, et la page doit le dire : une
    absence silencieuse passerait pour un oubli plutôt que pour un choix."""
    labels = " ".join(item["label"].lower() for item in bracket_rules.describe()["not_measured"])
    assert "stax" in labels and "tuteurs" in labels
