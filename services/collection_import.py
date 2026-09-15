"""
services/collection_import.py — saisie en masse de la collection.

Réutilise le parseur de decklist : le format d'entrée est le même (« 2 Sol Ring »),
seule la destination change. Les terrains de base sont ignorés — ils sont
considérés comme disponibles sans limite et ne génèrent jamais d'achat.
"""
import db.collection as collection_db
from services.decklist_parser import (
    collection_entries,
    is_basic_land,  # noqa: F401 — ré-exporté, routers/collection.py l'importe d'ici
    parse_decklist,
    resolve_lines,
)


def import_collection(raw_text: str) -> dict:
    parsed_lines, issues = parse_decklist(raw_text)
    resolved, resolution_issues = resolve_lines(parsed_lines)
    issues += resolution_issues

    entries, skipped_basics = collection_entries(parsed_lines, resolved)
    collection_db.add(entries)

    return {
        "added_distinct": len(entries),
        "added_total": sum(quantity for _, _, quantity in entries),
        "skipped_basic_lands": skipped_basics,
        "issues": [{"raw_line": line, "reason": reason} for line, reason in issues],
    }
