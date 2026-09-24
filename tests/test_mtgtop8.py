"""
Méta du Duel Commander (MTGTop8).

Les pages sont lues aux motifs qui les structurent : si la mise en page
change, ces tests doivent casser — l'alternative serait un méta qui se vide en
silence au fil des purges. Les extraits sont recopiés de pages réelles
(septembre 2026), réduits à ce que les parseurs lisent.

Le reste vise la mesure elle-même : le dénominateur des taux, le profil des
listes, et le choix de la référence quand EDHREC et le duel coexistent.
"""
from datetime import date

from db.duel_meta import COMMANDER_SLUG, META_SLUG, SOURCE, average_profile
from services import competitive
from services.mtgtop8 import (compute_card_stats, deck_profile, normalize_card_name,
                              parse_event, parse_event_list, parse_export, placement_of)

# Une page de liste : le tableau des « grands événements » d'abord, repris sur
# chaque page, puis la liste paginée.
EVENT_LIST_PAGE = """
<table>
  <tr class=hover_tr>
    <td width=70% class=S14><a href=event?e=91140&f=EDH>ZAP Realmbreaker 7</a> @ <a class=und href=event?e=91140&f=EDH>Palaiseau (France)</a></td>
    <td width=13% align=center><img src=/graph/star.png></td>
    <td align=right width=12% class=S12>20/09/26</td>
  </tr>
</table>
<div class=w_title align=center>Events 181 to 200<div class=c_tl></div></div>
<table border=0 class=Stable width=98% align=center>
  <tr class=hover_tr>
    <td width=5% align=center><img src=/graph/online/paper.png height=17 title="Paper"></td>
    <td width=70% class=S14><a href=event?e=89591&f=EDH>Duel for Cradle by MU</a> @ <a class=und href=event?e=89591&f=EDH>157 H.V. Dela Costa (Makati City, Philippines)</a></td>
    <td width=13% align=center><img src=/graph/star.png><img src=/graph/star.png><img src=/graph/star.png></td>
    <td align=right width=12% class=S12>16/08/26</td>
  </tr>
  <tr class=hover_tr>
    <td width=5% align=center><img src=/graph/online/paper.png height=17 title="Paper"></td>
    <td width=70% class=S14><a href=event?e=89641&f=EDH>C4ST Summer 2026</a> @ <a class=und href=event?e=89641&f=EDH>Gigean (France)</a></td>
    <td width=13% align=center><img src=/graph/star.png></td>
    <td align=right width=12% class=S12>15/08/26</td>
  </tr>
</table>
"""

EVENT_PAGE = """
<div class=event_title>FNM Duel BCN @ inGenio (Barcelona)</div>
<div class=event_title>#1 Cooking Spanish Omelette  - <a class=player_big href=search?player=Wasekone>Wasekone</a></div>
<div class=meta_arch style="padding:2px;">Duel Commander <img src=/graph/star.png></div>
	<div style="margin-bottom:5px;">21 players - 18/09/26</div>
			<div class=chosen_tr style="padding:3px 0px 3px 0px;" align=left>
			  <div style="display:flex;align-items:center;">
			    <div style="width:42px;" align=center class=S14>1</div>
			    <div style="width:80px;height:40px;background:black;"><a href=?e=91132&d=892150&f=EDH><img src=/metas_thumbs/994.jpg></a></div>
			    <div style="flex:1;">
			      <div class=S14 style="width:100%;padding-left:4px;margin-bottom:4px;"><a href=?e=91132&d=892150&f=EDH>Cooking Spanish Omelette </a> </div>
			    </div>
			  </div>
			</div>
			<div class=hover_tr style="padding:3px 0px 3px 0px;" align=left>
			  <div style="display:flex;align-items:center;">
			    <div style="width:42px;" align=center class=S14>3-4</div>
			    <div style="width:80px;height:40px;background:black;"><a href=?e=91132&d=892152&f=EDH><img src=/metas_thumbs/2674.jpg></a></div>
			    <div style="flex:1;">
			      <div class=S14 style="width:100%;padding-left:4px;margin-bottom:4px;"><a href=?e=91132&d=892152&f=EDH>Terra 2.0</a> </div>
			    </div>
			  </div>
			</div>
"""

# Un événement MTGO : pas de nombre de joueurs, la date seule.
EVENT_PAGE_WITHOUT_PLAYERS = """
<div class=event_title>MTGO League</div>
<div class=meta_arch style="padding:2px;">Duel Commander <img src=/graph/star.png></div>
	<div style="margin-bottom:5px;">18/08/26</div>
"""

EXPORT = "1 Anger\r\n1 Fire/Ice\r\n12 Island\r\n1 Urza's Saga\r\nSideboard\r\n" \
         "1 Kraum, Ludevic's Opus\r\n1 Yoshimaru, Ever Faithful\r\n"


def test_liste_ignore_le_tableau_des_grands_evenements():
    """Lu en premier, il ferait croire que chaque page commence au 20
    septembre : l'arrêt sur la fin de la fenêtre ne se produirait jamais."""
    events = parse_event_list(EVENT_LIST_PAGE)
    assert [e["event_id"] for e in events] == [89591, 89641]
    assert events[0]["event_date"] == date(2026, 8, 16)
    assert events[1]["name"] == "C4ST Summer 2026"


def test_premiere_page_titree_autrement():
    page = EVENT_LIST_PAGE.replace("Events 181 to 200", "LAST 20 EVENTS")
    assert len(parse_event_list(page)) == 2


def test_page_illisible_ne_rend_rien():
    """C'est ce vide que `list_new_events` transforme en erreur franche."""
    assert parse_event_list("<html>maintenance</html>") == []


def test_evenement():
    event = parse_event(EVENT_PAGE)
    assert event["name"] == "FNM Duel BCN @ inGenio (Barcelona)"
    assert event["players"] == 21
    assert event["event_date"] == date(2026, 9, 18)
    assert [(d["deck_id"], d["rank_label"], d["placement"]) for d in event["decks"]] == [
        (892150, "1", 1), (892152, "3-4", 3)]
    assert event["decks"][1]["deck_name"] == "Terra 2.0"


def test_evenement_sans_nombre_de_joueurs():
    """Absent n'est pas zéro."""
    event = parse_event(EVENT_PAGE_WITHOUT_PLAYERS)
    assert event["players"] is None
    assert event["event_date"] == date(2026, 8, 18)


def test_place_partagee():
    assert placement_of("5-8") == 5
    assert placement_of("") is None


def test_export_le_commandant_est_en_sideboard():
    """Deux lignes pour des partenaires ; rien d'autre n'y figure."""
    export = parse_export(EXPORT)
    assert export["commanders"] == ["Kraum, Ludevic's Opus", "Yoshimaru, Ever Faithful"]
    assert (12, "Island") in export["cards"]
    assert all("Kraum" not in name for _q, name in export["cards"])


def test_carte_partagee_au_format_scryfall():
    """« Fire/Ice » ne se résoudrait pas : ce n'est le recto de rien."""
    assert normalize_card_name("Fire/Ice") == "Fire // Ice"
    assert normalize_card_name("Fire // Ice") == "Fire // Ice"
    assert normalize_card_name("Urza's Saga") == "Urza's Saga"


def test_taux_rapporte_aux_decks_qui_pouvaient_jouer_la_carte():
    """
    Le dénominateur fait la mesure. Un Contresort joué par les deux decks
    bleus sur quatre vaut 100 % de ceux qui pouvaient le jouer, pas 50 % :
    le juger contre des decks rouges le ferait passer pour une carte de niche,
    et avantagerait mécaniquement les incolores.
    """
    decks = {1: ["U"], 2: ["U", "R"], 3: ["R"], 4: ["R", "G"]}
    cards = [(1, "counterspell"), (2, "counterspell"), (1, "sol"), (3, "sol")]
    identities = {"counterspell": ["U"], "sol": []}
    stats = {row["oracle_id"]: row for row in compute_card_stats(decks, cards, identities)}

    assert stats["counterspell"]["eligible_decks"] == 2
    assert stats["counterspell"]["rate"] == 1.0
    assert stats["counterspell"]["share"] == 0.5
    assert stats["sol"]["eligible_decks"] == 4
    assert stats["sol"]["rate"] == 0.5


def test_taux_jamais_au_dessus_de_un():
    """Une identité mal résolue ne doit pas produire un taux absurde."""
    stats = compute_card_stats({1: ["R"]}, [(1, "counterspell")], {"counterspell": ["U"]})
    assert stats[0]["rate"] == 1.0


def test_profil_compte_les_basiques_dans_les_terrains():
    """Sans eux, un deck à 38 terrains en afficherait 14 — et le constructeur
    viserait une manabase absurde."""
    cards = [(24, {"type_line": "Basic Land — Island", "cmc": 0}),
             (1, {"type_line": "Land", "cmc": 0}),
             (1, {"type_line": "Artifact Creature — Golem", "cmc": 4}),
             (1, {"type_line": "Instant", "cmc": 2})]
    types, curve = deck_profile(cards)
    assert types == {"Land": 25, "Creature": 1, "Instant": 1}
    assert curve == {"4": 1, "2": 1}


def test_profil_moyen_compte_les_absences_pour_zero():
    """Trois planeswalkers dans un seul deck sur trois ne font pas une cible
    de trois."""
    types, curve = average_profile([
        {"type_counts": {"Land": 38, "Planeswalker": 3}, "mana_curve": {"2": 20}},
        {"type_counts": {"Land": 36}, "mana_curve": {"2": 16}},
        {"type_counts": {"Land": 37}, "mana_curve": {"2": 18}},
    ])
    assert types == {"Land": 37, "Planeswalker": 1}
    assert curve == {"2": 18}


def _row(commander, slug, reachable, source=None, deck_count=10):
    row = {"commander_oracle_id": commander, "theme_slug": slug, "label": slug,
           "reachable": reachable, "owned_cards": 10, "score": 0.5, "deck_count": deck_count}
    if source:
        row["source"] = source
    return row


def test_le_duel_passe_devant_edhrec_quelle_que_soit_l_echelle():
    """
    Un taux EDHREC se mesure sur les decks d'un seul commandant, celui du méta
    sur tous les decks d'une couleur : le premier est mécaniquement plus haut.
    Les comparer ferait toujours gagner EDHREC — donc toujours conseiller en
    duel ce qui se joue en multijoueur.
    """
    commanders = [{"oracle_id": "a", "name": "A"}]
    scores = [_row("a", "_all", 30.0), _row("a", "infect", 25.0),
              _row("a", META_SLUG, 9.0, SOURCE), _row("a", COMMANDER_SLUG, 12.0, SOURCE)]
    ranked = competitive.rank_commanders(commanders, scores)
    assert ranked[0]["best_theme"]["slug"] == COMMANDER_SLUG
    assert ranked[0]["best_theme"]["source"] == SOURCE


def test_sans_duel_rien_ne_change():
    commanders = [{"oracle_id": "a", "name": "A"}]
    ranked = competitive.rank_commanders(commanders, [_row("a", "_all", 30.0),
                                                      _row("a", "infect", 25.0)])
    assert ranked[0]["best_theme"]["slug"] == "_all"


def test_les_references_de_duel_ne_sont_pas_des_strategies():
    """L'étape « partir d'une stratégie » ne doit proposer que des archétypes."""
    commanders = [{"oracle_id": "a", "name": "A"}]
    scores = [_row("a", "infect", 25.0), _row("a", META_SLUG, 9.0, SOURCE),
              _row("a", COMMANDER_SLUG, 12.0, SOURCE)]
    assert [entry["slug"] for entry in competitive.archetypes(commanders, scores)] == ["infect"]


def _meta_disponible() -> bool:
    try:
        from db import duel_meta
        return duel_meta.available()
    except Exception:
        return False


def test_suggestion_de_duel_prise_dans_les_tops():
    """
    Le plancher de qualité des suggestions de duel est le méta, pas EDHREC :
    une carte qui ne figure pas dans les tops (ou sous les planchers) ne doit
    jamais être proposée, même très bien classée en multijoueur.
    """
    import pytest

    if not _meta_disponible():
        pytest.skip("méta du duel absent : Postgres injoignable ou sync_mtgtop8 jamais lancé")

    import db.cards as cards_db
    from db.core import get_conn

    candidats = cards_db.find_candidates({"W", "U", "B", "R", "G"}, "removal", [], 1000.0,
                                         format="duel", limit=50)
    assert candidats
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT oracle_id::text AS o FROM duel_card_stats "
                "WHERE decks >= %s AND rate >= %s",
                (cards_db.MIN_DUEL_DECKS, cards_db.MIN_DUEL_RATE),
            )
            dans_les_tops = {row["o"] for row in cur.fetchall()}
    assert {str(c["oracle_id"]) for c in candidats} <= dans_les_tops
