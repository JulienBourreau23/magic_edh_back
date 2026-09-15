"""
services/allocation.py — répartition de la collection entre plusieurs decks.

Un exemplaire physique ne peut être que dans un deck à la fois. Quand plusieurs
decks réclament la même carte, les premiers servis sont ceux de la liste
transmise : la priorité est donc **l'ordre de sélection des decks**, ce qui la
rend explicite et modifiable, plutôt qu'un arbitrage implicite illisible.

Les terrains de base échappent à la règle : quantité supposée illimitée, jamais
d'achat.

Le format étant singleton, chaque deck ne réclame qu'un exemplaire d'une carte
donnée : le nombre d'achats d'une carte vaut donc exactement
`max(0, nombre de decks qui la veulent - exemplaires possédés)`. Il n'y a pas
d'optimisation combinatoire cachée là-dedans, et c'est tant mieux : le résultat
est vérifiable à la main.
"""
from services.collection_import import is_basic_land

CARD_FIELDS = ("scryfall_id", "oracle_id", "name", "name_fr", "price_eur",
               "image_uri", "image_downloaded")


def _card_summary(card: dict) -> dict:
    return {field: card[field] for field in CARD_FIELDS}


def allocate(deck_entries: list[tuple[dict, list[dict]]], owned: dict[str, int]) -> dict:
    """
    `deck_entries` = [(deck, cartes)] dans l'ordre de priorité décroissant.
    Renvoie la couverture par deck et la liste d'achats consolidée.
    """
    remaining = dict(owned)
    purchases: dict[str, dict] = {}
    per_deck = []

    for deck, cards in deck_entries:
        covered, to_buy = [], []
        for card in cards:
            if is_basic_land(card):
                continue

            oracle_id = str(card["oracle_id"])
            if remaining.get(oracle_id, 0) > 0:
                remaining[oracle_id] -= 1
                covered.append(_card_summary(card))
                continue

            to_buy.append(_card_summary(card))
            purchase = purchases.setdefault(
                oracle_id,
                {**_card_summary(card), "quantity": 0, "decks": []},
            )
            purchase["quantity"] += 1
            purchase["decks"].append(deck["name"])

        per_deck.append({
            "deck_id": deck["id"],
            "name": deck["name"],
            "owned_count": len(covered),
            "to_buy_count": len(to_buy),
            "to_buy_cost_eur": round(sum(c["price_eur"] or 0 for c in to_buy), 2),
            "to_buy": to_buy,
        })

    shopping_list = sorted(
        (
            {**purchase, "total_eur": round((purchase["price_eur"] or 0) * purchase["quantity"], 2)}
            for purchase in purchases.values()
        ),
        key=lambda item: item["total_eur"],
        reverse=True,
    )

    return {
        "decks": per_deck,
        "shopping_list": shopping_list,
        "total_cost_eur": round(sum(item["total_eur"] for item in shopping_list), 2),
        # Exemplaires encore libres après répartition, par oracle_id. Un
        # décompte et non un ensemble de cartes « réservées » : posséder deux
        # exemplaires et en placer un doit laisser le second disponible.
        "remaining_copies": remaining,
    }
