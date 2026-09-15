"""
services/collection_import.py — saisie en masse de la collection.

Réutilise le parseur de decklist : le format d'entrée est le même (« 2 Sol Ring »),
seule la destination change. Les terrains de base sont ignorés — ils sont
considérés comme disponibles sans limite et ne génèrent jamais d'achat.
"""
import db.collection as collection_db
from services.decklist_parser import parse_decklist, resolve_lines


def is_basic_land(card: dict) -> bool:
    return bool(card.get("type_line")) and card["type_line"].startswith("Basic Land")


def import_collection(raw_text: str) -> dict:
    parsed_lines, issues = parse_decklist(raw_text)
    resolved, resolution_issues = resolve_lines(parsed_lines)
    issues += resolution_issues

    aggregated: dict[str, tuple[str, int]] = {}
    skipped_basics = 0
    for line in parsed_lines:
        card = resolved.get(line.name)
        if not card:
            continue
        if is_basic_land(card):
            skipped_basics += line.quantity
            continue
        oracle_id = str(card["oracle_id"])
        scryfall_id, quantity = aggregated.get(oracle_id, (card["scryfall_id"], 0))
        aggregated[oracle_id] = (scryfall_id, quantity + line.quantity)

    collection_db.add([(oracle_id, sid, qty) for oracle_id, (sid, qty) in aggregated.items()])

    return {
        "added_distinct": len(aggregated),
        "added_total": sum(quantity for _, quantity in aggregated.values()),
        "skipped_basic_lands": skipped_basics,
        "issues": [{"raw_line": line, "reason": reason} for line, reason in issues],
    }
