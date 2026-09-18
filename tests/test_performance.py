"""
Classement des commandants par victoire mesurée.

Le chiffre affiché est un **taux de victoire**, c'est-à-dire ce qu'un joueur
lira comme une promesse. Les erreurs qui comptent ici sont celles qui le
faussent sans rien casser : un adversaire qui n'en est pas un, un miroir qui
gonfle un score, une moyenne qui oublie des parties.
"""
from services import duel, performance


def _panel_deck(nom, commander_oracle_id, cartes=80):
    return {"name": nom, "format": "commander", "commander_oracle_id": commander_oracle_id,
            "cards": [{"oracle_id": f"{nom}-{i}", "quantity": 1} for i in range(cartes)]}


def test_le_miroir_est_ecarte(monkeypatch):
    # Un commandant ne s'affronte pas lui-même : le miroir ne dit rien de qui
    # mérite d'être monté, et seuls les commandants qui ont déjà un deck en
    # joueraient un — le classement cesserait d'être comparable.
    rencontres = []

    def faux_duel(cards_a, cards_b, **kwargs):
        rencontres.append(cards_b[0]["oracle_id"].split("-")[0])
        return {"iterations": 100, "win_rate_a": 0.5, "win_rate_b": 0.5,
                "unfinished_rate": 0.0, "avg_turns": 10.0}

    monkeypatch.setattr(duel, "simulate_duels", faux_duel)
    panel = [_panel_deck("moi", "oracle-A"), _panel_deck("autre", "oracle-B")]

    mesure = performance._run_gauntlet([{"oracle_id": "x"}], panel, lambda cards: [],
                                       commander_oracle_id="oracle-A")

    assert rencontres == ["autre"]
    assert mesure["games"] == 100


def test_le_taux_agrege_toutes_les_parties(monkeypatch):
    # Un taux global sur l'ensemble des parties, et non la moyenne de deux
    # taux : sans ça, un adversaire écarté (miroir) pèserait autant qu'un
    # adversaire joué.
    resultats = iter([0.8, 0.2])

    def faux_duel(cards_a, cards_b, **kwargs):
        return {"iterations": 100, "win_rate_a": next(resultats), "win_rate_b": 0.0,
                "unfinished_rate": 0.1, "avg_turns": 12.0}

    monkeypatch.setattr(duel, "simulate_duels", faux_duel)
    panel = [_panel_deck("a", "oracle-X"), _panel_deck("b", "oracle-Y")]

    mesure = performance._run_gauntlet([{"oracle_id": "x"}], panel, lambda cards: [])

    assert mesure["games"] == 200
    assert mesure["win_rate"] == 0.5
    assert mesure["unfinished_rate"] == 0.1


def test_un_deck_trop_court_n_est_pas_un_adversaire(monkeypatch):
    # Un brouillon de neuf cartes perd contre tout le monde et gonfle tous les
    # taux de la même façon : il ne classe plus rien. Cas réel, un deck de test
    # traînait dans la base.
    import db.decks as decks_db

    decks = [{"id": 1, "name": "vrai", "format": "commander"},
             {"id": 2, "name": "brouillon", "format": "commander"}]
    cartes = {
        1: [{"oracle_id": f"o{i}", "quantity": 1, "is_commander": i == 0} for i in range(80)],
        2: [{"oracle_id": "o0", "quantity": 9, "is_commander": True}],
    }
    monkeypatch.setattr(decks_db, "list_decks", lambda: decks)
    monkeypatch.setattr(decks_db, "get_deck_cards_for_simulation", lambda deck_id: cartes[deck_id])

    panel = performance._panel_decks()

    assert [deck["name"] for deck in panel] == ["vrai"]
