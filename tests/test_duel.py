"""
Le duel simulé produit un taux de victoire : c'est le chiffre le plus facile à
croire sur parole, donc celui qui doit être le plus contraint par des tests.
"""
from services.duel import (
    COMMANDER_LIFE,
    COMMANDER_TAX_STEP,
    Permanent,
    Player,
    simulate_duels,
    to_duel_card,
)


def card(name, **overrides):
    base = {
        "name": name, "quantity": 1, "cmc": 0, "mana_cost": "", "categories": [],
        "produced_mana": [], "oracle_text": "", "is_commander": False,
        "type_line": "", "power": None, "toughness": None,
    }
    return {**base, **overrides}


FOREST = card("Forest", quantity=40, categories=["land"], produced_mana=["G"],
              oracle_text="({T}: Add {G}.)", type_line="Basic Land — Forest")
COMMANDER = card("Chef test", cmc=2, mana_cost="{1}{G}", is_commander=True,
                 type_line="Legendary Creature — Elf", power="2", toughness="2")


def deck(creature_power: str, creature_toughness: str = "2", count: int = 59):
    """Un deck mono-vert : 40 forêts, un commandant, N créatures identiques."""
    return [
        FOREST,
        COMMANDER,
        card("Bête", quantity=count, cmc=2, mana_cost="{1}{G}",
             type_line="Creature — Beast", power=creature_power, toughness=creature_toughness),
    ]


def test_meme_graine_memes_resultats():
    strong, weak = deck("4"), deck("1")
    assert simulate_duels(strong, weak, iterations=60, seed=7) == \
           simulate_duels(strong, weak, iterations=60, seed=7)


def test_les_taux_de_victoire_somment_avec_les_parties_non_conclues():
    result = simulate_duels(deck("3"), deck("2"), iterations=60, seed=1)
    total = result["win_rate_a"] + result["win_rate_b"] + result["unfinished_rate"]
    assert abs(total - 1.0) < 0.02


def test_le_deck_aux_plus_grosses_creatures_gagne_plus_souvent():
    # 4/2 contre 1/2 : à manabase identique, seul le corps change.
    result = simulate_duels(deck("4"), deck("1"), iterations=120, seed=3)
    assert result["win_rate_a"] > result["win_rate_b"]


def test_deux_decks_identiques_sont_a_egalite():
    # L'avantage du premier joueur est neutralisé (moitié des parties chacun),
    # donc deux decks identiques ne doivent pas diverger franchement.
    result = simulate_duels(deck("3"), deck("3"), iterations=200, seed=11)
    assert abs(result["win_rate_a"] - result["win_rate_b"]) < 0.15


def test_points_de_vie_de_depart_respectes():
    result = simulate_duels(deck("3"), deck("3"), iterations=20, seed=5, starting_life=30)
    assert result["starting_life"] == 30
    assert simulate_duels(deck("3"), deck("3"), iterations=20, seed=5)["starting_life"] == COMMANDER_LIFE


def test_deck_vide():
    assert simulate_duels([], [], iterations=10)["unfinished_rate"] == 1.0


def _joueur_avec_commandant_en_jeu(forets: int = 2) -> Player:
    commandant = to_duel_card(COMMANDER)
    player = Player(name="a", library=[], commander=commandant, life=COMMANDER_LIFE)
    player.mana_sources = [to_duel_card(FOREST)] * forets
    player.creatures = [Permanent(commandant, is_commander=True)]
    player.commander_cast = True
    return player


def test_le_commandant_detruit_retourne_en_zone_de_commandement():
    # Un board wipe ne supprime pas un commandant de la partie : il repart en
    # zone de commandement et se relance. L'inverse punissait deux fois le deck.
    player = _joueur_avec_commandant_en_jeu()

    player.destroy(list(player.creatures))

    assert player.creatures == []
    assert player.commander_cast is False
    assert player.commander_tax == COMMANDER_TAX_STEP


def test_la_taxe_de_commandement_rend_la_relance_plus_chere():
    player = _joueur_avec_commandant_en_jeu()
    player.destroy(list(player.creatures))

    # {1}{G} relancé après une destruction coûte {3}{G} : deux forêts ne
    # suffisent plus.
    assert player.can_cast_commander() is False
    player.mana_sources += [to_duel_card(FOREST)] * 2
    assert player.can_cast_commander() is True


def test_une_creature_ordinaire_detruite_ne_taxe_rien():
    player = _joueur_avec_commandant_en_jeu()
    bete = to_duel_card(card("Bête", type_line="Creature — Beast", power="2", toughness="2"))
    player.creatures.append(Permanent(bete))

    player.destroy([player.creatures[-1]])

    assert player.commander_tax == 0
    assert len(player.creatures) == 1
