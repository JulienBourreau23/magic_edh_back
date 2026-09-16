"""
services/wishlist_import.py — saisie en masse de la liste de recherche.

Même parseur que les decklists et que la collection : le format d'entrée est
identique (« 2 Sol Ring »), seule la destination change. Les terrains de base
sont ignorés — disponibles sans limite, ils ne se cherchent pas.
"""
import db.wishlist as wishlist_db
from services.decklist_parser import collection_entries, parse_decklist, resolve_lines


def import_wishlist(raw_text: str, note: str | None = None) -> dict:
    parsed_lines, issues = parse_decklist(raw_text)
    resolved, resolution_issues = resolve_lines(parsed_lines)
    issues += resolution_issues

    entries, skipped_basics = collection_entries(parsed_lines, resolved)
    wishlist_db.add([(oracle_id, scryfall_id, quantity, note)
                     for oracle_id, scryfall_id, quantity in entries])

    return {
        "added_distinct": len(entries),
        "added_total": sum(quantity for _, _, quantity in entries),
        "skipped_basic_lands": skipped_basics,
        "issues": [{"raw_line": line, "reason": reason} for line, reason in issues],
    }
