"""
La prochaine extension : les deux erreurs silencieuses seraient de garder une
extension le jour de sa sortie (la page ne passerait jamais à la suivante) et
de retenir des jetons ou des promos qui partagent sa date.
"""
from datetime import date

from services.upcoming import next_release

SETS = [
    {"code": "old", "name": "Old", "set_type": "expansion", "released_at": "2026-09-01"},
    {"code": "tfra", "name": "Tokens", "set_type": "token", "released_at": "2026-10-02",
     "parent_set_code": "fra"},
    {"code": "pfra", "name": "Promos", "set_type": "promo", "released_at": "2026-10-02",
     "parent_set_code": "fra"},
    {"code": "frc", "name": "Commander", "set_type": "commander", "released_at": "2026-10-02",
     "parent_set_code": "fra"},
    {"code": "fra", "name": "Main", "set_type": "expansion", "released_at": "2026-10-02"},
    {"code": "arena", "name": "Alchemy", "set_type": "alchemy", "released_at": "2026-10-01",
     "digital": True},
    {"code": "trk", "name": "Next", "set_type": "expansion", "released_at": "2026-11-13"},
]


def test_prochaine_sortie_garde_set_et_precons_sans_jetons_ni_promos():
    release = next_release(SETS, date(2026, 9, 26))
    assert release["released_at"] == "2026-10-02"
    assert [s["code"] for s in release["sets"]] == ["fra", "frc"]


def test_le_jour_de_sortie_la_page_passe_a_la_suivante():
    release = next_release(SETS, date(2026, 10, 2))
    assert release["released_at"] == "2026-11-13"
    assert [s["code"] for s in release["sets"]] == ["trk"]


def test_rien_a_venir():
    assert next_release(SETS, date(2027, 1, 1)) is None


# --- L'alerte de légalité d'une carte pas encore sortie --------------------

from services.deck_analysis import legality_warnings  # noqa: E402

RELEASES = {"fra": date(2026, 10, 2), "lea": date(1993, 8, 5)}


def _card(**overrides):
    card = {"name": "X", "name_fr": None, "quantity": 1, "is_commander": False,
            "type_line": "Instant", "color_identity": [], "legal_commander": False,
            "legal_duel": False, "banned_commander": False, "banned_duel": False,
            "set_code": "fra"}
    return {**card, **overrides}


def _issue(card, today, format="commander"):
    warnings = legality_warnings([card], format, RELEASES, today)
    return next(w["issue"] for w in warnings if w["card"] == "X")


def test_une_nouveaute_n_est_pas_annoncee_interdite():
    assert _issue(_card(), date(2026, 9, 26)) == "pas encore sortie : utilisable à partir du 2 octobre 2026"


def test_sortie_recente_non_synchronisee():
    assert "prochain sync Scryfall" in _issue(_card(), date(2026, 10, 10))


def test_une_carte_bannie_reste_bannie_meme_nouvelle():
    assert "bannie" in _issue(_card(banned_commander=True), date(2026, 9, 26))
    # Le drapeau de l'autre format ne compte pas.
    assert "pas encore sortie" in _issue(_card(banned_duel=True), date(2026, 9, 26))


def test_vieille_carte_hors_format_garde_l_ancien_message():
    assert "hors format" in _issue(_card(set_code="lea"), date(2026, 9, 26))


def test_sans_dates_l_ancien_message():
    warnings = legality_warnings([_card()], "commander")
    assert any("hors format" in w["issue"] for w in warnings)
