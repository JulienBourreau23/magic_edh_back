"""
services/deck_ideas.py — « quel deck puis-je monter avec ce que j'ai ? »

Croise les commandants de la collection avec les cartes qu'EDHREC voit
réellement jouées avec eux, puis classe par **part déjà couverte** : le
commandant le mieux couvert est celui qui coûte le moins cher à monter.

Le noyau visé est volontairement le non-terrain (voir NONLAND_CORE) : les
terrains complètent le deck sans rien coûter dès lors qu'on accepte des
terrains de base, les compter fausserait à la fois la couverture et le budget.
L'exclusion porte sur **tous** les terrains, pas seulement les basiques.
"""
import db.commanders as commanders_db
from services.suggestions import DEFAULT_MAX_PRICE_EUR

# Un deck Commander, c'est 99 cartes dont ~36 terrains. On vise donc un noyau
# de 63 non-terrains ; le reste se complète en terrains, majoritairement de base.
NONLAND_CORE = 63


def _summarize(card: dict) -> dict:
    return {
        "scryfall_id": card["scryfall_id"],
        "oracle_id": card["oracle_id"],
        "name": card["name"],
        "name_fr": card["name_fr"],
        "price_eur": card["price_eur"],
        "image_uri": card["image_uri"],
        "image_downloaded": card["image_downloaded"],
        "inclusion_rate": float(card["inclusion_rate"]) if card["inclusion_rate"] else None,
        "game_changer": card["game_changer"],
    }


def deck_ideas(max_price: float = DEFAULT_MAX_PRICE_EUR) -> dict:
    if not commanders_db.has_data():
        return {
            "error": "Aucune donnée EDHREC en base : lance "
                     "`python scripts/sync_edhrec.py` pour les récupérer.",
            "ideas": [],
        }

    ideas = []
    for commander in commanders_db.owned_commanders():
        core = commanders_db.recommendations(str(commander["oracle_id"]), NONLAND_CORE,
                                             exclude_lands=True)
        if not core:
            continue

        owned = [card for card in core if card["owned_quantity"] > 0]
        missing = [card for card in core if card["owned_quantity"] == 0]
        affordable = [c for c in missing if c["price_eur"] is not None and c["price_eur"] <= max_price]
        too_expensive = [c for c in missing if c["price_eur"] is None or c["price_eur"] > max_price]

        ideas.append({
            "commander": {
                "oracle_id": commander["oracle_id"],
                "scryfall_id": commander["scryfall_id"],
                "name": commander["name"],
                "name_fr": commander["name_fr"],
                "color_identity": commander["color_identity"],
                "image_uri": commander["image_uri"],
                "image_downloaded": commander["image_downloaded"],
            },
            # Répartition des brackets observée sur EDHREC : à quel niveau les
            # joueurs montent réellement ce commandant.
            "bracket_counts": commander["bracket_counts"],
            "core_size": len(core),
            "owned_count": len(owned),
            "coverage": round(len(owned) / len(core), 3),
            "to_buy_count": len(affordable),
            "to_buy_cost_eur": round(sum(c["price_eur"] for c in affordable), 2),
            "over_budget_count": len(too_expensive),
            "to_buy": [_summarize(c) for c in affordable],
            "owned": [_summarize(c) for c in owned],
        })

    # Le mieux couvert d'abord : c'est le deck le moins cher à monter.
    ideas.sort(key=lambda idea: idea["coverage"], reverse=True)
    return {"max_price_eur": max_price, "nonland_core": NONLAND_CORE, "ideas": ideas}
