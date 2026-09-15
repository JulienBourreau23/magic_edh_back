"""
services/matchup.py — comparaison de deux decks.

Le verdict est construit à partir de grandeurs mesurées (simulation + comptages),
pas d'une appréciation : chaque axe a un gagnant objectif, et le commentaire
n'est que la mise en phrase du décompte. Aucune IA n'est nécessaire ici.
"""
from services import card_categories as categories
from services import deck_analysis, duel, simulation

INTERACTION_CATEGORIES = [categories.REMOVAL, categories.COUNTERSPELL, categories.BOARD_WIPE]


def _profile(deck: dict, cards: list[dict], iterations: int, seed: int) -> dict:
    metrics = simulation.simulate(cards, iterations=iterations, seed=seed)
    role_counts = categories.count_by_category(cards)
    return {
        "deck_id": deck["id"],
        "name": deck["name"],
        "bracket": deck_analysis.bracket_estimate(cards),
        "manabase": deck_analysis.manabase(cards),
        "role_counts": role_counts,
        "interaction_count": sum(role_counts.get(c, 0) for c in INTERACTION_CATEGORIES),
        "simulation": metrics,
    }


def initiative(cards_a: list[dict], cards_b: list[dict], iterations: int, seed: int) -> dict:
    """
    Part des parties simulées où chaque deck est opérationnel le premier
    (commandant en jeu le plus tôt), à main de départ tirée indépendamment.

    **Ce n'est pas un taux de victoire.** Une probabilité de victoire honnête
    supposerait de modéliser combat, blocages, removal ciblé et ordre de
    priorité — autrement dit un moteur de règles — et surtout de la calibrer
    contre de vraies parties, dont nous n'avons aucune. Le chiffre ci-dessous
    mesure uniquement qui démarre le plus vite : c'est l'indicateur
    d'équilibrage demandé, sans le déguiser en pronostic.
    """
    games_a = simulation.play_games(cards_a, iterations, seed)
    games_b = simulation.play_games(cards_b, iterations, seed)
    if not games_a or not games_b:
        return {"a": None, "b": None, "tie": None, "iterations": 0}

    never = 10**6
    wins_a = wins_b = ties = 0
    for game_a, game_b in zip(games_a, games_b):
        turn_a = game_a.commander_turn or never
        turn_b = game_b.commander_turn or never
        if turn_a < turn_b:
            wins_a += 1
        elif turn_b < turn_a:
            wins_b += 1
        else:
            ties += 1

    total = len(games_a)
    return {
        "a": round(wins_a / total, 3),
        "b": round(wins_b / total, 3),
        "tie": round(ties / total, 3),
        "iterations": total,
    }


def _axis(label: str, a_value, b_value, lower_is_better: bool, hint: str) -> dict:
    """
    `lower_is_better` est renvoyé au client : sans lui, l'affichage ne peut pas
    savoir dans quel sens remplir une jauge (un tour de commandant plus bas est
    meilleur, un taux de mains gardées plus haut aussi).
    """
    winner = None
    if a_value is not None and b_value is not None and a_value != b_value:
        a_wins = a_value < b_value if lower_is_better else a_value > b_value
        winner = "a" if a_wins else "b"
    return {"label": label, "a": a_value, "b": b_value, "winner": winner,
            "lower_is_better": lower_is_better, "hint": hint}


def compare(deck_a: dict, cards_a: list[dict], deck_b: dict, cards_b: list[dict],
            iterations: int = simulation.DEFAULT_ITERATIONS, seed: int = 0) -> dict:
    profile_a = _profile(deck_a, cards_a, iterations, seed)
    profile_b = _profile(deck_b, cards_b, iterations, seed)
    sim_a, sim_b = profile_a["simulation"], profile_b["simulation"]

    axes = [
        _axis("Vitesse — tour moyen du commandant", sim_a["avg_commander_turn"], sim_b["avg_commander_turn"],
              lower_is_better=True, hint="Plus tôt le commandant arrive, plus tôt le deck fait ce qu'il sait faire."),
        _axis("Régularité — mains gardées à 7", sim_a["keep_seven_rate"], sim_b["keep_seven_rate"],
              lower_is_better=False, hint="Taux de mains de départ jouables sans mulligan."),
        _axis("Mana disponible au tour 4", sim_a["avg_mana_by_turn"][4], sim_b["avg_mana_by_turn"][4],
              lower_is_better=False, hint="Mesure l'accélération réelle (terrains + rochers)."),
        _axis("Stabilité des couleurs", sim_a["color_screw_rate"], sim_b["color_screw_rate"],
              lower_is_better=True, hint="Parties où le mana suffisait mais pas les couleurs."),
        _axis("Interaction (removal, contres, wipes)", profile_a["interaction_count"], profile_b["interaction_count"],
              lower_is_better=False, hint="Capacité à répondre au plan adverse."),
    ]
    # Le bracket n'est volontairement PAS un axe : sur une page d'équilibrage,
    # compter « bracket plus haut = axe gagné » donnerait un point gratuit au
    # deck le plus puissant, alors que sa puissance est déjà mesurée par les
    # axes ci-dessus. Il reste affiché par deck, et le verdict signale un écart
    # de deux niveaux ou plus.

    wins = {"a": sum(1 for axis in axes if axis["winner"] == "a"),
            "b": sum(1 for axis in axes if axis["winner"] == "b")}
    starting_life = duel.DUEL_COMMANDER_LIFE if deck_a.get("format") == "duel" else duel.COMMANDER_LIFE
    return {"a": profile_a, "b": profile_b, "axes": axes, "wins": wins,
            "initiative": initiative(cards_a, cards_b, iterations, seed),
            "duel": duel.simulate_duels(cards_a, cards_b, seed=seed, starting_life=starting_life),
            "verdict": _verdict(profile_a, profile_b, axes, wins)}


def _verdict(profile_a: dict, profile_b: dict, axes: list[dict], wins: dict) -> str:
    leader, trailer = (profile_a, profile_b) if wins["a"] >= wins["b"] else (profile_b, profile_a)
    leader_key = "a" if leader is profile_a else "b"

    if wins["a"] == wins["b"]:
        opening = f"« {profile_a['name'] } » et « {profile_b['name']} » sont au coude à coude ({wins['a']}-{wins['b']})."
    else:
        opening = (f"« {leader['name']} » prend l'avantage sur {max(wins.values())} axes sur {len(axes)} "
                   f"face à « {trailer['name']} ».")

    forces = [axis["label"] for axis in axes if axis["winner"] == leader_key]
    detail = f" Ses points forts : {', '.join(forces).lower()}." if forces else ""

    ecart = abs(leader["bracket"]["min"] - trailer["bracket"]["min"])
    bracket_note = (
        f" Attention, l'écart de bracket est de {ecart} niveau(x) : "
        "en duel comme en multi, ces decks ne joueront pas la même partie."
        if ecart >= 2 else ""
    )
    return opening + detail + bracket_note
