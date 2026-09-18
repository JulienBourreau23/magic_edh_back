"""
services/deck_plans.py — « monte-moi quatre decks ».

Compare les decks montables derrière chaque commandant possédé, puis retient
le groupe de quatre qui satisfait les deux contraintes demandées, dans cet
ordre :

1. **Équilibré.** Les quatre decks sont construits sur les mêmes repères — les
   quotas de rôle de `deck_analysis.ROLE_TARGETS` — et ramenés au même bracket,
   celui du plus faible du groupe (retirer des Game Changers ne coûte rien,
   en ajouter coûte de l'argent : c'est déjà la règle de `services/balance.py`).
2. **Le moins cher possible.** Un exemplaire physique ne peut être que dans un
   deck à la fois (règle de `services/allocation.py`) : monter quatre decks qui
   réclament les mêmes cartes oblige à racheter les doublons. Le coût d'un
   groupe dépend donc du groupe entier, pas de chaque deck pris isolément —
   c'est tout l'intérêt de comparer les combinaisons plutôt que d'aligner les
   quatre commandants les mieux couverts.

Aucune IA : le contenu des decks vient des cartes qu'EDHREC voit réellement
jouées avec chaque commandant, le reste est du comptage et du tri.

Ce que ce plan ne fait pas : choisir entre deux cartes de même rôle sur autre
chose que leur popularité et leur prix. Il ne connaît ni les synergies fines ni
les combos — c'est un plan d'achat équilibré, pas une liste optimisée.
"""
from itertools import combinations

from services import card_categories as categories
from services import deck_analysis
from services.mana import color_requirements
from services.suggestions import ROLE_LABELS

DECKS_TO_BUILD = 4

# Un deck Commander, c'est 99 cartes plus le commandant. On vise 63 non-terrains
# et 36 terrains : les terrains de base sont gratuits et illimités, les compter
# dans le noyau payant fausserait le budget.
CORE_SIZE = 63
LAND_SLOTS = 36

# Garde-fou combinatoire : au-delà, on ne compare que les commandants les moins
# chers à monter en solo. C(12,4) = 495 groupes, c'est instantané ; C(30,4) en
# ferait 27 000 pour un gain nul (les 18 derniers ne sortiraient jamais).
MAX_COMMANDERS_COMPARED = 12

# Les achats sont comparés par bande de popularité de 5 points : à l'intérieur
# d'une bande, deux cartes sont considérées aussi jouées l'une que l'autre et
# c'est le prix qui tranche. Sans bande, le tri par prix ferait descendre des
# cartes marginales devant les incontournables du commandant.
INCLUSION_BAND = 20

BASIC_LAND_BY_COLOR = {"W": "Plaine", "U": "Île", "B": "Marais", "R": "Montagne", "G": "Forêt"}
COLORLESS_BASIC_LAND = "Étendue"


def _game_changer_allowance(target_bracket: int) -> int:
    """Même barème que `suggestions.cuts_for_bracket` : 0 pour viser 1-2, 3 pour 3."""
    if target_bracket <= 2:
        return 0
    if target_bracket == 3:
        return 3
    return CORE_SIZE


def _summarize(card: dict, owned: bool, role: str | None = None) -> dict:
    return {
        "oracle_id": str(card["oracle_id"]),
        "scryfall_id": card["scryfall_id"],
        "name": card["name"],
        "name_fr": card["name_fr"],
        "price_eur": float(card["price_eur"]) if card["price_eur"] is not None else None,
        "image_uri": card["image_uri"],
        "image_downloaded": card["image_downloaded"],
        "inclusion_rate": float(card["inclusion_rate"]) if card["inclusion_rate"] else None,
        "game_changer": card["game_changer"],
        "owned": owned,
        "role": role,
    }


def _sort_key(entry: tuple[bool, dict], owned_only: bool = False) -> tuple:
    """
    Ordre de pioche dans le pool : ce qu'on possède d'abord (gratuit), puis les
    cartes les plus jouées, et à popularité comparable la moins chère.

    Sans achat, le prix ne départage plus rien — tout est déjà payé. C'est
    alors le rang EDHREC qui tranche : à défaut de savoir ce qui va bien avec ce
    commandant précis, le plus joué du format est le moins mauvais repli, et les
    cartes sans rang passent en dernier (une absence de mesure n'est pas une
    bonne note).
    """
    free, card = entry
    band = -int((card["inclusion_rate"] or 0) * INCLUSION_BAND)
    if owned_only:
        return (0 if free else 1, band, card.get("edhrec_rank") or 10**9, card["name"])
    price = float(card["price_eur"]) if card["price_eur"] is not None else 0.0
    return (0 if free else 1, band, price, card["name"])


def free_copies(owned: dict[str, int], committed: dict[str, int]) -> dict[str, int]:
    """
    Les exemplaires réellement disponibles : ce qu'on possède moins ce que les
    decks déjà enregistrés immobilisent.

    La soustraction est **bornée à zéro** : la collection peut ignorer les
    cartes d'un deck importé sans la case « déjà monté », et un compte négatif
    n'aurait aucun sens — il rendrait la carte impossible à employer au lieu de
    la rendre simplement rare.
    """
    return {
        oracle_id: max(0, quantity - committed.get(oracle_id, 0))
        for oracle_id, quantity in owned.items()
    }


def with_owned_cards(pools: dict[str, list[dict]], commanders: list[dict],
                     owned_cards: list[dict]) -> dict[str, list[dict]]:
    """
    Élargit chaque vivier à **toute la collection jouable** derrière ce
    commandant (identité de couleur respectée), en plus des cartes qu'EDHREC y
    voit jouées.

    Sans ça, le mode « sans achat » ne pourrait piocher que dans l'intersection
    entre la collection et les listes EDHREC — quelques dizaines de cartes — et
    proposerait des decks de vingt cartes alors que la collection en contient
    des centaines de jouables. Les recommandations gardent leur `inclusion_rate`
    et passent donc devant ; le reste de la collection vient ensuite, classé par
    popularité.

    Réservé à ce mode, volontairement : avec achats, la page répond « le deck
    qu'EDHREC monte derrière ce commandant », et y verser toute la collection
    changerait la question.
    """
    elargis = {}
    for commander in commanders:
        oracle_id = str(commander["oracle_id"])
        identity = set(commander["color_identity"] or [])
        pool = pools.get(oracle_id, [])
        known = {str(card["oracle_id"]) for card in pool}
        known.add(oracle_id)
        extra = [
            {**card, "inclusion_rate": None}
            for card in owned_cards
            if str(card["oracle_id"]) not in known
            and set(card["color_identity"] or []) <= identity
        ]
        elargis[oracle_id] = [*pool, *extra]
    return elargis


def _main_role(card: dict) -> str | None:
    """Le rôle sur lequel la carte est retenue, pour expliquer l'achat."""
    for role in deck_analysis.ROLE_TARGETS:
        if role in (card.get("categories") or []):
            return role
    return None


def build_deck(commander: dict, pool: list[dict], available: dict[str, int],
               max_price: float, target_bracket: int | None,
               find_combos=None, owned_only: bool = False) -> dict:
    """
    Construit un deck pour ce commandant en consommant `available` (les
    exemplaires encore libres dans la collection, modifié sur place).

    Deux passes, dans cet ordre : les quotas de rôle d'abord — c'est ce qui rend
    le deck équilibré et ça ne peut pas être rattrapé après coup — puis le
    remplissage jusqu'à 63 non-terrains.

    `owned_only` répond à « que puis-je monter ce soir sans rien acheter » :
    aucune carte absente de la collection n'entre dans la liste. Le noyau peut
    alors faire moins de 63 cartes — c'est un fait sur la collection, pas un
    échec, et `core_size` le dit. Un plafond de prix à zéro n'aurait pas suffi :
    quelques cartes valent 0,00 € sans être pour autant dans la boîte.
    """
    allowance = _game_changer_allowance(target_bracket) if target_bracket else CORE_SIZE

    candidates: list[tuple[bool, dict]] = []
    for card in pool:
        if categories.is_land(card):
            continue
        free = available.get(str(card["oracle_id"]), 0) > 0
        if not free and owned_only:
            continue
        # Sans prix connu, impossible de garantir le plafond : on ne l'achète pas.
        if not free and (card["price_eur"] is None or float(card["price_eur"]) > max_price):
            continue
        candidates.append((free, card))
    candidates.sort(key=lambda entry: _sort_key(entry, owned_only))

    chosen: list[dict] = []
    taken: set[str] = set()
    game_changers = 0

    def take(entry: tuple[bool, dict], role: str | None) -> None:
        nonlocal game_changers
        free, card = entry
        oracle_id = str(card["oracle_id"])
        if free:
            available[oracle_id] -= 1
        if card["game_changer"]:
            game_changers += 1
        taken.add(oracle_id)
        chosen.append({**_summarize(card, free, role), "_card": card})

    def can_take(entry: tuple[bool, dict]) -> bool:
        _, card = entry
        if str(card["oracle_id"]) in taken:
            return False
        return not (card["game_changer"] and game_changers >= allowance)

    for role, (low, _high) in deck_analysis.ROLE_TARGETS.items():
        filled = 0
        for entry in candidates:
            if filled >= low or len(chosen) >= CORE_SIZE:
                break
            if role in (entry[1].get("categories") or []) and can_take(entry):
                take(entry, role)
                filled += 1

    for entry in candidates:
        if len(chosen) >= CORE_SIZE:
            break
        if can_take(entry):
            take(entry, _main_role(entry[1]))

    core_cards = [item.pop("_card") for item in chosen]
    return _describe(commander, chosen, core_cards, pool, available, find_combos)


def _describe(commander: dict, chosen: list[dict], core_cards: list[dict],
              pool: list[dict], available: dict[str, int], find_combos=None) -> dict:
    to_buy = [item for item in chosen if not item["owned"]]
    role_counts = categories.count_by_category(core_cards)
    role_gap = sum(
        max(0, low - role_counts.get(role, 0))
        for role, (low, _high) in deck_analysis.ROLE_TARGETS.items()
    )

    # `bracket_estimate` attend des cartes de deck : on lui donne le noyau plus
    # le commandant, qui compte s'il est lui-même Game Changer.
    bracket_input = [{**card, "quantity": 1, "is_commander": False} for card in core_cards]
    bracket_input.append({**commander, "quantity": 1, "is_commander": True,
                          "categories": commander.get("categories") or []})
    inclusions = [item["inclusion_rate"] for item in chosen if item["inclusion_rate"]]

    return {
        "commander": {
            "oracle_id": str(commander["oracle_id"]),
            "scryfall_id": commander["scryfall_id"],
            "name": commander["name"],
            "name_fr": commander["name_fr"],
            "color_identity": commander["color_identity"],
            "image_uri": commander["image_uri"],
            "image_downloaded": commander["image_downloaded"],
            "existing_deck_id": commander.get("existing_deck_id"),
        },
        "core": chosen,
        "core_size": len(chosen),
        "pool_size": len(pool),
        "owned_count": len(chosen) - len(to_buy),
        "to_buy": to_buy,
        "to_buy_count": len(to_buy),
        "cost_eur": round(sum(item["price_eur"] or 0 for item in to_buy), 2),
        "role_counts": {role: role_counts.get(role, 0) for role in deck_analysis.ROLE_TARGETS},
        "role_targets": {role: f"{low}-{high}" for role, (low, high) in deck_analysis.ROLE_TARGETS.items()},
        "role_gap": role_gap,
        # Les combos sont cherchés par une fonction injectée : le deck est
        # construit ici, l'appelant ne peut donc pas les pré-calculer comme le
        # fait `/balance`. Sans elle, le module reste testable sans base.
        "bracket": deck_analysis.bracket_estimate(
            bracket_input, find_combos(bracket_input) if find_combos else None),
        "avg_inclusion": round(sum(inclusions) / len(inclusions), 3) if inclusions else 0.0,
        "lands": _land_plan(commander, pool, available, core_cards),
    }


def _land_plan(commander: dict, pool: list[dict], available: dict[str, int],
               core_cards: list[dict]) -> dict:
    """
    Les 36 terrains, à coût nul : les terrains non-basiques déjà possédés (et
    encore libres) d'abord, le reste en terrains de base répartis selon les
    symboles de mana réellement demandés par le noyau.

    Rien n'est acheté ici, volontairement : une manabase achetée coûte vite plus
    cher que le reste du deck, et des terrains de base font le travail.
    """
    owned_lands = []
    for card in pool:
        if len(owned_lands) >= LAND_SLOTS:
            break
        oracle_id = str(card["oracle_id"])
        if categories.is_land(card) and available.get(oracle_id, 0) > 0:
            available[oracle_id] -= 1
            owned_lands.append(_summarize(card, owned=True, role=categories.LAND))

    slots = max(0, LAND_SLOTS - len(owned_lands))
    identity = [color for color in commander["color_identity"] if color in BASIC_LAND_BY_COLOR]
    if not identity or not slots:
        return {"owned_nonbasic": owned_lands,
                "basics": {COLORLESS_BASIC_LAND: slots} if slots else {},
                "total": len(owned_lands) + slots}

    # Répartition au prorata des symboles de mana demandés, commandant compris
    # (c'est lui qu'il faut pouvoir lancer en premier). Le plancher de deux
    # points de pondération évite qu'une couleur peu demandée se retrouve sans
    # la moindre source.
    pips = color_requirements(core_cards + [commander])
    weights = {color: pips.get(color, 0) + 2 for color in identity}
    total_weight = sum(weights.values())

    exact = {color: slots * weight / total_weight for color, weight in weights.items()}
    basics = {color: int(value) for color, value in exact.items()}
    remainder = slots - sum(basics.values())
    for color in sorted(exact, key=lambda c: exact[c] - int(exact[c]), reverse=True)[:remainder]:
        basics[color] += 1

    return {
        "owned_nonbasic": owned_lands,
        "basics": {BASIC_LAND_BY_COLOR[color]: count
                   for color, count in sorted(basics.items()) if count},
        "total": len(owned_lands) + sum(basics.values()),
    }


def deck_rows(plan: dict, basic_land_ids: dict[str, str]) -> list[tuple[str, int, bool]]:
    """
    Le plan tel qu'il s'écrit en base : `[(scryfall_id, quantité, commandant)]`.

    Le deck enregistré est **exactement celui affiché** — noyau, terrains
    non-basiques possédés, terrains de base — sans quoi les conseils qui
    suivront ne parleraient pas du même deck.

    Rien n'est ajouté à la collection au passage : ces cartes y sont déjà, c'est
    la condition même du mode sans achat. Les ajouter compterait chaque
    exemplaire deux fois et ferait disparaître des achats pourtant nécessaires.
    """
    rows = [(plan["commander"]["scryfall_id"], 1, True)]
    rows += [(card["scryfall_id"], 1, False) for card in plan["core"]]
    rows += [(land["scryfall_id"], 1, False) for land in plan["lands"]["owned_nonbasic"]]
    rows += [
        (basic_land_ids[name], count, False)
        for name, count in plan["lands"]["basics"].items()
        if name in basic_land_ids
    ]
    return rows


def _shopping_list(plans: list[dict]) -> list[dict]:
    """
    Liste d'achats consolidée, au format attendu par l'export PDF existant.
    Une carte réclamée par deux decks compte pour deux exemplaires : le format
    est singleton, un exemplaire ne peut pas être dans les deux.
    """
    merged: dict[str, dict] = {}
    for plan in plans:
        deck_name = plan["commander"]["name_fr"] or plan["commander"]["name"]
        for item in plan["to_buy"]:
            entry = merged.setdefault(item["oracle_id"], {
                "scryfall_id": item["scryfall_id"],
                "oracle_id": item["oracle_id"],
                "name": item["name"],
                "name_fr": item["name_fr"],
                "price_eur": item["price_eur"],
                "image_uri": item["image_uri"],
                "image_downloaded": item["image_downloaded"],
                "quantity": 0,
                "decks": [],
                "motif": _motif(item),
            })
            entry["quantity"] += 1
            entry["decks"].append(deck_name)

    for entry in merged.values():
        entry["total_eur"] = round((entry["price_eur"] or 0) * entry["quantity"], 2)
    return sorted(merged.values(), key=lambda item: item["total_eur"], reverse=True)


def _motif(item: dict) -> str:
    if item["role"]:
        return ROLE_LABELS.get(item["role"], item["role"])
    return "noyau du commandant"


def _build_group(commanders: list[dict], pools: dict[str, list[dict]], owned: dict[str, int],
                 max_price: float, natural: dict[str, int], target_bracket: int | None,
                 find_combos=None, owned_only: bool = False) -> dict:
    """
    Monte les quatre decks d'un groupe sur une collection partagée.

    L'ordre de service est **le plus contraint d'abord** : le commandant qui a
    le moins de cartes possédées dans son pool choisit en premier. Servir
    l'abondant d'abord lui ferait prendre des exemplaires dont l'autre a un
    besoin exclusif, et la facture monterait sans rien apporter.
    """
    target = target_bracket or min(natural[str(c["oracle_id"])] for c in commanders)
    available = dict(owned)

    ordered = sorted(
        commanders,
        key=lambda commander: (
            sum(1 for card in pools[str(commander["oracle_id"])] if card["owned_quantity"] > 0),
            commander["name"],
        ),
    )

    plans = [
        build_deck(commander, pools[str(commander["oracle_id"])], available, max_price,
                   target, find_combos, owned_only)
        for commander in ordered
    ]
    shopping_list = _shopping_list(plans)
    return {
        "target_bracket": target,
        "plans": plans,
        "shopping_list": shopping_list,
        "total_cost_eur": round(sum(item["total_eur"] for item in shopping_list), 2),
        "missing_count": sum(item["quantity"] for item in shopping_list),
        "role_gap": sum(plan["role_gap"] for plan in plans),
        "brackets": sorted({plan["bracket"]["min"] for plan in plans}),
    }


def _group_score(group: dict) -> tuple:
    """
    Équilibre d'abord (l'écart aux repères de rôle), puis le **remplissage**,
    puis le prix.

    Le remplissage ne comptait pas tant que les decks faisaient toujours 63
    cartes. Sans achat, ce n'est plus vrai : deux commandants qui se disputent
    la même moitié de collection donnent deux decks courts, et un groupe de
    quatre decks complets vaut mieux qu'un groupe mieux étalé en bracket mais
    troué.
    """
    return (
        group["role_gap"],
        -sum(plan["core_size"] for plan in group["plans"]),
        group["brackets"][-1] - group["brackets"][0],
        group["total_cost_eur"],
        -sum(plan["avg_inclusion"] for plan in group["plans"]),
    )


def plan_decks(commanders: list[dict], pools: dict[str, list[dict]], owned: dict[str, int],
               max_price: float, target_bracket: int | None = None,
               chosen_oracle_ids: list[str] | None = None, find_combos=None,
               owned_only: bool = False) -> dict:
    """
    Renvoie la comparaison de tous les commandants et le meilleur groupe de
    quatre (ou celui imposé par `chosen_oracle_ids`).
    """
    usable = [c for c in commanders if pools.get(str(c["oracle_id"]))]
    if not usable:
        return {"error": "Aucune donnée EDHREC pour les commandants possédés : lance "
                         "`python scripts/sync_edhrec.py`.",
                "commanders": [], "selection": None}

    # Référence de comparaison : chaque deck monté seul, collection entière
    # disponible. C'est le seul point de vue où les commandants sont comparables
    # entre eux — dans un groupe, le coût de l'un dépend des trois autres.
    solo = {}
    natural = {}
    for commander in usable:
        oracle_id = str(commander["oracle_id"])
        plan = build_deck(commander, pools[oracle_id], dict(owned), max_price, None,
                          find_combos, owned_only)
        solo[oracle_id] = plan
        natural[oracle_id] = plan["bracket"]["min"]

    comparison = sorted(solo.values(), key=lambda plan: (plan["role_gap"], plan["cost_eur"]))

    if chosen_oracle_ids:
        by_id = {str(c["oracle_id"]): c for c in usable}
        missing = [oid for oid in chosen_oracle_ids if oid not in by_id]
        if missing:
            return {"error": f"Commandant inconnu ou sans données EDHREC : {', '.join(missing)}",
                    "commanders": [_comparison_row(plan) for plan in comparison],
                    "selection": None}
        group = _build_group([by_id[oid] for oid in chosen_oracle_ids], pools, owned,
                             max_price, natural, target_bracket, find_combos, owned_only)
        return _result(comparison, group, max_price, len(usable), forced=True,
                       owned_only=owned_only)

    # Au-delà du garde-fou, on ne garde que les moins chers à monter seuls : un
    # commandant qui coûte déjà cher tout seul ne devient pas bon marché en
    # groupe, où il partage la collection avec trois autres.
    pool_of_commanders = usable
    if len(usable) > MAX_COMMANDERS_COMPARED:
        cheapest = sorted(comparison, key=lambda plan: plan["cost_eur"])[:MAX_COMMANDERS_COMPARED]
        keep = {plan["commander"]["oracle_id"] for plan in cheapest}
        pool_of_commanders = [c for c in usable if str(c["oracle_id"]) in keep]

    size = min(DECKS_TO_BUILD, len(pool_of_commanders))
    best = min(
        (_build_group(list(group), pools, owned, max_price, natural, target_bracket,
                      find_combos, owned_only)
         for group in combinations(pool_of_commanders, size)),
        key=_group_score,
    )
    return _result(comparison, best, max_price, len(usable), forced=False,
                   owned_only=owned_only)


def _comparison_row(plan: dict) -> dict:
    """
    Le tableau de comparaison n'affiche que des totaux : renvoyer en plus les
    63 cartes de chaque commandant triplerait le poids de la réponse pour rien.
    Le détail carte par carte n'est renvoyé que pour les decks retenus.
    """
    return {key: value for key, value in plan.items() if key not in ("core", "to_buy", "lands")}


def _result(comparison: list[dict], group: dict, max_price: float,
            commanders_compared: int, forced: bool, owned_only: bool = False) -> dict:
    return {
        "core_size": CORE_SIZE,
        "land_slots": LAND_SLOTS,
        "decks_to_build": DECKS_TO_BUILD,
        "max_price_eur": max_price,
        "owned_only": owned_only,
        "commanders_compared": commanders_compared,
        "selection_forced": forced,
        "commanders": [_comparison_row(plan) for plan in comparison],
        "selection": group,
        "incomplete": len(group["plans"]) < DECKS_TO_BUILD,
    }
