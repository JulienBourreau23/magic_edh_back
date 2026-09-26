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
