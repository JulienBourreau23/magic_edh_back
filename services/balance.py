"""
services/balance.py — équilibrer plusieurs decks entre eux au coût le plus bas.

Deux principes, dans cet ordre :

1. **Baisser coûte zéro, monter coûte de l'argent.** Aligner un groupe de decks
   sur le plus faible d'entre eux ne demande que des retraits. C'est pour ça
   que le bracket visé par défaut est le minimum observé, et pas la moyenne.
2. **Une carte déjà possédée et non réservée est gratuite.** Les propositions
   piochent d'abord là-dedans ; l'achat n'arrive qu'en dernier recours, sous le
   plafond de prix.

Les exemplaires possédés sont réservés au fur et à mesure : une carte proposée
au premier deck n'est plus proposée gratuitement au suivant.
"""
import db.cards as cards_db
import db.ignored as ignored_db
from services import card_categories as categories
from services import deck_analysis, suggestions
from services.allocation import allocate

MAX_DECKS = 4
CANDIDATES_PER_ROLE = 4


def _exhausted(available: dict[str, int]) -> list[str]:
    """Cartes possédées dont plus aucun exemplaire n'est libre."""
    return sorted(oracle_id for oracle_id, left in available.items() if left <= 0)


def _adds_for_deck(cards: list[dict], format: str, max_price: float,
                   available: dict[str, int], target_bracket: int,
                   ignored: list[str] | None = None) -> list[dict]:
    """
    Comble les manques de rôle, gratuitement si possible. `available` = les
    exemplaires encore libres par `oracle_id`, décrémenté au fur et à mesure :
    une carte proposée ici n'est plus disponible pour le deck suivant, mais un
    deuxième exemplaire possédé le reste.
    """
    identity = deck_analysis.commander_identity(cards)
    if identity is None:
        return []

    # Les cartes refusées pour ce deck sortent comme si elles y étaient déjà :
    # le filtre existait, il suffit de l'élargir.
    exclude = [card["oracle_id"] for card in cards] + list(ignored or [])
    groups = []

    deficits = [d for d in deck_analysis.role_diagnostics(cards) if d["status"] == "insuffisant"]
    manabase = deck_analysis.manabase(cards)
    if manabase["land_count"] < deck_analysis.RECOMMENDED_LANDS.start:
        deficits.append({
            "role": categories.LAND,
            "gap": deck_analysis.RECOMMENDED_LANDS.start - manabase["land_count"],
            "count": manabase["land_count"],
            "target": manabase["recommended_lands"],
        })

    for deficit in deficits:
        candidates = cards_db.find_candidates(
            identity, deficit["role"], exclude, max_price, format,
            limit=CANDIDATES_PER_ROLE,
            exclude_game_changers=target_bracket <= 3,
            exhausted_oracle_ids=_exhausted(available),
        )
        if not candidates:
            continue

        retained = candidates[: deficit["gap"]] or candidates[:1]
        for candidate in retained:
            # Réserver tout de suite : le deck suivant ne doit pas croire que
            # cet exemplaire est encore disponible.
            if candidate["free_to_use"]:
                oracle_id = str(candidate["oracle_id"])
                available[oracle_id] = available.get(oracle_id, 0) - 1

        groups.append({
            "role": deficit["role"],
            "label": suggestions.ROLE_LABELS.get(deficit["role"], deficit["role"]),
            "missing": deficit["gap"],
            "reason": f"{deficit['count']} pour un repère de {deficit['target']}",
            "candidates": retained,
        })

    return groups


def balance(deck_entries: list[tuple[dict, list[dict]]], owned: dict[str, int],
            max_price: float = suggestions.DEFAULT_MAX_PRICE_EUR,
            target_bracket: int | None = None,
            combos_by_deck: dict[int, list[dict]] | None = None) -> dict:
    """
    `combos_by_deck` vient de l'appelant plutôt que d'une lecture ici : le
    bracket doit être le même que sur la fiche du deck, sinon le bracket visé
    par défaut — le plus faible du groupe — se calcule sur des chiffres que
    l'utilisateur ne voit nulle part ailleurs.
    """
    if not deck_entries:
        return {"error": "aucun deck sélectionné"}
    if len(deck_entries) > MAX_DECKS:
        return {"error": f"{MAX_DECKS} decks au maximum"}

    allocation = allocate(deck_entries, owned)
    # Les exemplaires restants pilotent la gratuité des propositions ; ils ne
    # regardent pas le client, d'où le retrait de la réponse.
    available = allocation.pop("remaining_copies")

    combos_by_deck = combos_by_deck or {}
    # Une seule requête pour les quatre decks : les interroger un par un ferait
    # quatre allers-retours pour rien.
    ignored_by_deck = ignored_db.by_deck([deck["id"] for deck, _ in deck_entries])
    brackets = {
        deck["id"]: deck_analysis.bracket_estimate(cards, combos_by_deck.get(deck["id"]))
        for deck, cards in deck_entries
    }
    minimums = [bracket["min"] for bracket in brackets.values()]
    target = target_bracket or min(minimums)

    plans = []
    for deck, cards in deck_entries:
        bracket = brackets[deck["id"]]
        ignored = ignored_by_deck.get(deck["id"], [])
        cuts = (suggestions.cuts_for_bracket(cards, target, combos_by_deck.get(deck["id"]))
                if bracket["min"] > target else [])
        cuts = [cut for cut in cuts if str(cut["card"]["oracle_id"]) not in set(ignored)]
        adds = _adds_for_deck(cards, deck["format"], max_price, available, target, ignored)

        purchases = [
            candidate
            for group in adds
            for candidate in group["candidates"]
            if not candidate["free_to_use"]
        ]
        plans.append({
            "deck_id": deck["id"],
            "name": deck["name"],
            "bracket": bracket,
            "cuts": cuts,
            "adds": adds,
            "free_picks": sum(1 for g in adds for c in g["candidates"] if c["free_to_use"]),
            "purchases_cost_eur": round(sum(c["price_eur"] or 0 for c in purchases), 2),
        })

    shopping_list = _merge_shopping_list(allocation, plans)
    return {
        "target_bracket": target,
        "spread": {"min": min(minimums), "max": max(minimums), "gap": max(minimums) - min(minimums)},
        "allocation": allocation,
        "plans": plans,
        "shopping_list": shopping_list,
        "total_cost_eur": round(sum(item["total_eur"] for item in shopping_list), 2),
        "max_price_eur": max_price,
    }


def _merge_shopping_list(allocation: dict, plans: list[dict]) -> list[dict]:
    """
    Fusionne deux sources d'achats : les cartes déjà dans les decks mais absentes
    de la collection, et les cartes conseillées qu'il faut acheter.
    """
    merged: dict[str, dict] = {}

    for item in allocation["shopping_list"]:
        merged[str(item["oracle_id"])] = {**item, "motif": "déjà dans la liste du deck"}

    for plan in plans:
        for group in plan["adds"]:
            for candidate in group["candidates"]:
                if candidate["free_to_use"]:
                    continue
                oracle_id = str(candidate["oracle_id"])
                entry = merged.setdefault(oracle_id, {
                    "scryfall_id": candidate["scryfall_id"],
                    "oracle_id": candidate["oracle_id"],
                    "name": candidate["name"],
                    "name_fr": candidate.get("name_fr"),
                    "price_eur": candidate["price_eur"],
                    "image_uri": candidate["image_uri"],
                    "image_downloaded": candidate["image_downloaded"],
                    "quantity": 0,
                    "decks": [],
                    "motif": f"ajout conseillé ({group['label']})",
                })
                entry["quantity"] += 1
                entry["decks"].append(plan["name"])

    for entry in merged.values():
        entry["total_eur"] = round((entry["price_eur"] or 0) * entry["quantity"], 2)

    return sorted(merged.values(), key=lambda item: item["total_eur"], reverse=True)
