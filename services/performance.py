"""
services/performance.py — quel commandant gagne, et avec quel archétype.

**Aucune source ne publie de taux de victoire en Commander casual.** EDHREC
compte des decks, pas des parties. La seule victoire mesurable ici est donc
celle que le projet sait déjà simuler (`services/duel.py`), et c'est la même
mesure que la page de comparaison de deux decks : parties jouées coup par coup,
avec le biais connu et documenté de ce modèle.

La méthode est un **gantelet** plutôt qu'un tournoi toutes rondes : chaque
commandant monte son meilleur deck avec la collection, puis affronte le même
panel — les decks réellement enregistrés. Deux raisons, et la seconde décide :

- un tournoi toutes rondes sur 131 commandants, c'est 8 515 affrontements, une
  heure et demie de calcul, à refaire après chaque achat ;
- « qui bat ce qu'on joue déjà » est une question plus utile, pour une soirée
  entre amis, que « qui bat la moyenne des commandants possédés ».

**Un score ne se compare qu'à panel égal** : le panel est donc écrit dans
chaque ligne, avec la date.
"""
import db.cards as cards_db
import db.collection as collection_db
import db.commanders as commanders_db
import db.decks as decks_db
import db.performance as performance_db
import db.themes as themes_db
from services import combos as combos_service
from services import competitive, deck_plans, duel

# Parties par affrontement. À 3 ms la partie, cent parties contre six decks du
# panel font moins de deux secondes par commandant — et l'écart-type d'un taux
# mesuré sur six cents parties est de l'ordre de deux points, assez fin pour un
# classement.
GAMES_PER_MATCH = 100

# Les archétypes ne sont mesurés que pour les meilleurs commandants : 562
# archétypes coûteraient un quart d'heure, et personne ne lit le 87e.
THEMES_FOR_TOP = 20

# Graine fixe : deux exécutions sur les mêmes données donnent le même
# classement, sinon un écart de deux points ne voudrait rien dire.
SEED = 0

BASIC_LANDS = ("Plaine", "Île", "Marais", "Montagne", "Forêt", "Étendue")

# Un deck trop court n'est pas un adversaire : il perd contre tout le monde et
# gonfle tous les taux de la même façon, ce qui ne classe plus rien. Le seuil
# laisse passer un deck incomplet mais jouable, pas un brouillon de neuf cartes.
MIN_PANEL_DECK_CARDS = 60


def _panel_decks() -> list[dict]:
    """Les decks enregistrés, prêts à jouer. C'est eux que le classement affronte."""
    panel = []
    for deck in decks_db.list_decks():
        cards = decks_db.get_deck_cards_for_simulation(deck["id"])
        if sum(card["quantity"] for card in cards) < MIN_PANEL_DECK_CARDS:
            continue
        commandant = next((card for card in cards if card["is_commander"]), None)
        panel.append({
            "name": deck["name"],
            "format": deck["format"],
            "cards": cards,
            # Pour ne pas faire jouer un commandant contre lui-même : un miroir
            # ne dit rien de qui mérite d'être monté, et seuls les commandants
            # qui ont déjà un deck en affronteraient un.
            "commander_oracle_id": str(commandant["oracle_id"]) if commandant else None,
        })
    return panel


def _deck_rows(scryfall_counts: dict[str, int], commander_scryfall_id: str,
               rows: dict[str, dict]) -> list[dict]:
    """Assemble un deck jouable : cartes du catalogue, quantités, commandant."""
    deck = []
    for scryfall_id, quantity in scryfall_counts.items():
        row = rows.get(str(scryfall_id))
        if row is None:
            continue
        deck.append({**row, "quantity": quantity,
                     "is_commander": str(scryfall_id) == str(commander_scryfall_id)})
    return deck


def _basic_land_ids() -> dict[str, str]:
    resolved = cards_db.resolve_names(list(BASIC_LANDS))
    return {name: resolved[name.lower()]["scryfall_id"]
            for name in BASIC_LANDS if name.lower() in resolved}


def _counts_from_plan(plan: dict, basics: dict[str, str]) -> dict[str, int]:
    """Un plan (`deck_plans`) ou un deck compétitif, ramené à {scryfall_id: quantité}."""
    counts: dict[str, int] = {plan["commander"]["scryfall_id"]: 1}
    for card in plan["core"]:
        counts[card["scryfall_id"]] = counts.get(card["scryfall_id"], 0) + 1
    for land in plan["lands"]["owned_nonbasic"]:
        counts[land["scryfall_id"]] = counts.get(land["scryfall_id"], 0) + 1
    for name, quantity in plan["lands"]["basics"].items():
        if name in basics:
            counts[basics[name]] = counts.get(basics[name], 0) + quantity
    return counts


def _counts_from_build(build: dict, basics: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {build["commander"]["scryfall_id"]: 1}
    for card in build["cards"]:
        counts[card["scryfall_id"]] = counts.get(card["scryfall_id"], 0) + 1
    for land in build["lands"]["nonbasic"]:
        counts[land["scryfall_id"]] = counts.get(land["scryfall_id"], 0) + 1
    for name, quantity in build["lands"]["basics"].items():
        if name in basics:
            counts[basics[name]] = counts.get(basics[name], 0) + quantity
    return counts


def _run_gauntlet(cards: list[dict], panel: list[dict], find_combos,
                  commander_oracle_id: str | None = None) -> dict:
    """
    Le deck contre tout le panel. Les parties s'additionnent : un taux global
    sur six cents parties vaut mieux que six taux de cent qu'il faudrait
    moyenner à la main.

    Les parties **non conclues** au bout de 25 tours comptent au dénominateur :
    ne pas savoir finir est un résultat, pas une absence de résultat.
    """
    combos_deck = find_combos(cards)
    wins = games = unfinished = 0
    turns = 0.0
    for adversaire in panel:
        if commander_oracle_id and adversaire["commander_oracle_id"] == commander_oracle_id:
            continue
        life = duel.DUEL_COMMANDER_LIFE if adversaire["format"] == "duel" else duel.COMMANDER_LIFE
        result = duel.simulate_duels(
            cards, adversaire["cards"], iterations=GAMES_PER_MATCH, seed=SEED,
            starting_life=life, combos_a=combos_deck,
            combos_b=find_combos(adversaire["cards"]),
        )
        wins += round(result["win_rate_a"] * result["iterations"])
        unfinished += round(result["unfinished_rate"] * result["iterations"])
        turns += result["avg_turns"] * result["iterations"]
        games += result["iterations"]

    return {
        "win_rate": round(wins / games, 3) if games else 0.0,
        "games": games,
        "unfinished_rate": round(unfinished / games, 3) if games else 0.0,
        "avg_turns": round(turns / games, 1) if games else 0.0,
    }


def rank(progress=None) -> dict:
    """
    Classe les commandants possédés, puis les archétypes des meilleurs, et
    écrit le tout en base. Renvoie de quoi rendre compte en ligne de commande.
    """
    panel = _panel_decks()
    if not panel:
        return {"error": "Aucun deck enregistré : le panel de référence est vide. "
                         "Importe au moins un deck, c'est lui qui sert d'adversaire."}

    commanders = commanders_db.owned_commanders()
    pools = commanders_db.recommendation_pool([str(c["oracle_id"]) for c in commanders])
    pools = deck_plans.with_owned_cards(pools, commanders, commanders_db.owned_cards())
    owned = collection_db.quantities()

    universe = {str(card["oracle_id"]) for pool in pools.values() for card in pool}
    universe.update(str(c["oracle_id"]) for c in commanders)
    for adversaire in panel:
        universe.update(str(card["oracle_id"]) for card in adversaire["cards"])
    find_combos = combos_service.matcher_for(universe)

    basics = _basic_land_ids()
    panel_label = ", ".join(deck["name"] for deck in panel)

    lignes = []
    for index, commander in enumerate(commanders, start=1):
        oracle_id = str(commander["oracle_id"])
        plan = deck_plans.build_deck(commander, pools[oracle_id], dict(owned), 0, None,
                                     owned_only=True)
        if plan["core_size"] == 0:
            continue

        counts = _counts_from_plan(plan, basics)
        rows = decks_db.simulation_cards_by_id(list(counts))
        cards = _deck_rows(counts, commander["scryfall_id"], rows)
        mesure = _run_gauntlet(cards, panel, find_combos, oracle_id)
        if mesure["games"] == 0:
            continue
        lignes.append({
            "commander_oracle_id": oracle_id, "theme_slug": "", "theme_label": None,
            "core_size": plan["core_size"], "role_gap": plan["role_gap"],
            "bracket": plan["bracket"]["min"], "panel": panel_label, **mesure,
        })
        if progress:
            progress(index, len(commanders), commander["name"], mesure["win_rate"])

    meilleurs = sorted(lignes, key=lambda ligne: -ligne["win_rate"])[:THEMES_FOR_TOP]
    for ligne in meilleurs:
        commander = next(c for c in commanders
                         if str(c["oracle_id"]) == ligne["commander_oracle_id"])
        carte = cards_db.get_cheapest_by_oracle_id(ligne["commander_oracle_id"])
        for theme in themes_db.themes_for(ligne["commander_oracle_id"]):
            if theme["slug"] == "_all":
                continue
            # Le deck compétitif est déjà « le plus proche des decks réels de cet
            # archétype, avec ce que j'ai » : exactement ce qu'on veut mesurer.
            build = competitive.build(carte, theme["slug"], "commander", max_price=0.01)
            if build.get("error") or not build["cards"]:
                continue
            counts = _counts_from_build(build, basics)
            rows = decks_db.simulation_cards_by_id(list(counts))
            cards = _deck_rows(counts, commander["scryfall_id"], rows)
            mesure = _run_gauntlet(cards, panel, find_combos, ligne["commander_oracle_id"])
            lignes.append({
                "commander_oracle_id": ligne["commander_oracle_id"],
                "theme_slug": theme["slug"], "theme_label": theme["label"],
                "core_size": build["counts"]["nonland"], "role_gap": 0,
                "bracket": None, "panel": panel_label, **mesure,
            })
            if progress:
                progress(None, None, f"{commander['name']} — {theme['label']}",
                         mesure["win_rate"])

    performance_db.replace_all(lignes)
    return {"commanders": sum(1 for l in lignes if not l["theme_slug"]),
            "themes": sum(1 for l in lignes if l["theme_slug"]),
            "panel": panel_label, "games_per_match": GAMES_PER_MATCH}
