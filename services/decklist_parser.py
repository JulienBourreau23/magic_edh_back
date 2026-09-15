"""
services/decklist_parser.py — parsing d'une decklist en texte brut (exports
Moxfield / Archidekt / EDHREC, avec ou sans quantités, avec ou sans section
"Commander") puis résolution des noms contre la base et persistance du deck.
"""
import re
from dataclasses import dataclass

import db.cards as cards_db
import db.collection as collection_db
import db.decks as decks_db

SECTION_HEADERS = {
    "commander": "commander",
    "commanders": "commander",
    "deck": "deck",
    "decklist": "deck",
    "mainboard": "deck",
    "maindeck": "deck",
    "sideboard": "sideboard",
    "maybeboard": "sideboard",
    "considering": "sideboard",
    # En-têtes par type de carte (Archidekt, exports "with categories").
    "creature": "deck", "creatures": "deck",
    "instant": "deck", "instants": "deck",
    "sorcery": "deck", "sorceries": "deck",
    "artifact": "deck", "artifacts": "deck",
    "enchantment": "deck", "enchantments": "deck",
    "planeswalker": "deck", "planeswalkers": "deck",
    "battle": "deck", "battles": "deck",
    "land": "deck", "lands": "deck",
    "nonland": "deck", "nonlands": "deck",
}

QTY_LINE_RE = re.compile(r"^(?:SB:\s*)?(\d+)\s*[xX]?\s+(.+)$")
# En-tête de section "Creatures (24)" / "Lands (36)" : pas de quantité en tête,
# mais un compteur entre parenthèses en fin de ligne.
HEADER_COUNT_RE = re.compile(r"^([A-Za-z][A-Za-z '/-]*?)\s*\(\d+\)\s*:?$")

# Suffixes à retirer du nom, appliqués en boucle pour gérer leurs combinaisons
# ("Sol Ring (C21) 205 *F*" par exemple).
NAME_SUFFIX_RES = [
    re.compile(r"\s*\*[^*]*\*\s*$"),                                   # *F*, *Foil*
    re.compile(r"\s*\[[^\]]*\]\s*$"),                                  # [Ramp{top}]
    re.compile(r"\s*\([A-Za-z0-9]{2,6}\)\s*[A-Za-z0-9\-★]*\s*$"),  # (C21) 205
    re.compile(r"\s*<[^>]*>\s*$"),                                     # <cat>
]

# Similarité minimale (pg_trgm) pour accepter une résolution floue automatiquement.
FUZZY_MATCH_THRESHOLD = 0.5


@dataclass
class ParsedLine:
    raw_line: str
    quantity: int
    name: str
    is_commander: bool


def _clean_name(raw: str) -> str:
    name = raw.strip()
    changed = True
    while changed:
        changed = False
        for pattern in NAME_SUFFIX_RES:
            stripped = pattern.sub("", name).strip()
            if stripped != name and stripped:
                name, changed = stripped, True
    return name


def _section_of(line: str) -> str | None:
    """Renvoie la section si la ligne est un en-tête, sinon None."""
    bare = line.rstrip(":").strip()
    section = SECTION_HEADERS.get(bare.lower())
    if section:
        return section
    match = HEADER_COUNT_RE.match(line)
    if match:
        return SECTION_HEADERS.get(match.group(1).lower(), "deck")
    return None


def parse_decklist(raw_text: str) -> tuple[list[ParsedLine], list[tuple[str, str]]]:
    """
    Renvoie (lignes parsées, lignes illisibles). Une ligne sans quantité est
    comptée pour 1 exemplaire (beaucoup d'exports/copier-coller n'en mettent
    pas) ; une ligne qu'on n'arrive pas à interpréter est remontée plutôt que
    jetée en silence.
    """
    lines: list[ParsedLine] = []
    unparsed: list[tuple[str, str]] = []
    section = "deck"

    for raw in raw_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue

        header = _section_of(line)
        if header:
            section = header
            continue

        if section == "sideboard":
            continue  # V1 : on ignore le sideboard/maybeboard

        match = QTY_LINE_RE.match(line)
        quantity, rest = (int(match.group(1)), match.group(2)) if match else (1, line)

        name = _clean_name(rest)
        if not name:
            unparsed.append((raw, "ligne illisible"))
            continue

        lines.append(ParsedLine(raw, quantity, name, section == "commander"))

    return lines, unparsed


def resolve_lines(parsed_lines: list[ParsedLine]) -> tuple[dict[str, dict], list[tuple[str, str]]]:
    """Résout les noms (exact en une requête, puis flou au cas par cas)."""
    exact = cards_db.resolve_names([line.name for line in parsed_lines])
    resolved: dict[str, dict] = {}
    issues: list[tuple[str, str]] = []

    for line in parsed_lines:
        if line.name in resolved:
            continue
        card = exact.get(line.name.lower())
        if card:
            resolved[line.name] = card
            continue

        candidates = cards_db.find_by_similar_name(line.name, limit=1)
        if candidates and candidates[0]["score"] >= FUZZY_MATCH_THRESHOLD:
            resolved[line.name] = candidates[0]
        elif candidates:
            issues.append((line.raw_line, f"ambiguous (proche de: {candidates[0]['name']})"))
        else:
            issues.append((line.raw_line, "not_found"))

    return resolved, issues


def is_basic_land(card: dict) -> bool:
    return bool(card.get("type_line")) and card["type_line"].startswith("Basic Land")


def collection_entries(parsed_lines: list, resolved: dict) -> tuple[list[tuple[str, str, int]], int]:
    """
    Agrège des lignes résolues pour la collection, indexée par `oracle_id` :
    posséder « un Sol Ring » ne dépend pas de l'édition. Renvoie
    (entrées, terrains de base ignorés) — ces derniers sont supposés
    disponibles sans limite et ne génèrent jamais d'achat.
    """
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
    return [(oid, sid, qty) for oid, (sid, qty) in aggregated.items()], skipped_basics


def import_decklist(deck_name: str, raw_text: str, format: str = "commander",
                    add_to_collection: bool = False) -> dict:
    parsed_lines, issues = parse_decklist(raw_text)
    resolved, resolution_issues = resolve_lines(parsed_lines)
    issues += resolution_issues

    # Agrégation par carte : une même carte peut apparaître sur plusieurs
    # lignes, et Postgres refuse de traiter deux fois la même clé de conflit
    # dans un seul INSERT.
    aggregated: dict[str, list] = {}
    commanders: list[str] = []
    for line in parsed_lines:
        card = resolved.get(line.name)
        if not card:
            continue
        entry = aggregated.setdefault(card["scryfall_id"], [0, False])
        entry[0] += line.quantity
        entry[1] = entry[1] or line.is_commander
        if line.is_commander and card["scryfall_id"] not in commanders:
            commanders.append(card["scryfall_id"])

    deck_id = decks_db.create_deck(deck_name, format)
    decks_db.add_deck_cards(
        deck_id, [(sid, qty, is_cmd) for sid, (qty, is_cmd) in aggregated.items()]
    )
    decks_db.add_import_issues(deck_id, issues)

    if commanders:
        decks_db.set_commanders(deck_id, commanders[0], commanders[1] if len(commanders) > 1 else None)

    # Un deck déjà monté contient physiquement ses exemplaires : les inscrire
    # dans la collection évite qu'on conseille d'acheter ce qui est déjà dans
    # la boîte. Opt-in, parce qu'un deck seulement envisagé ne prouve rien.
    collection_summary = None
    if add_to_collection:
        entries, skipped_basics = collection_entries(parsed_lines, resolved)
        collection_db.add(entries)
        collection_summary = {
            "added_distinct": len(entries),
            "added_total": sum(quantity for _, _, quantity in entries),
            "skipped_basic_lands": skipped_basics,
        }

    return {
        "deck_id": deck_id,
        "commander_resolved": bool(commanders),
        "import_issues": decks_db.get_import_issues(deck_id),
        "collection": collection_summary,
    }
