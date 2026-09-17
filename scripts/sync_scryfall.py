"""
scripts/sync_scryfall.py — télécharge le bulk data "default_cards" de Scryfall
(une ligne par impression) et upsert dans la table `cards`.

Exécution manuelle : `python scripts/sync_scryfall.py`
Un refresh périodique (systemd timer) sera mis en place au déploiement.
"""
import gzip
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from psycopg2.extras import execute_values

from config import SCRYFALL_API_BASE, SCRYFALL_HEADERS
from db.core import get_conn
from services.card_categories import classify

BATCH_SIZE = 2000

# Layouts qui ne sont pas des cartes jouables en deck (jetons, emblemes, etc.)
SKIP_LAYOUTS = {
    "token", "double_faced_token", "emblem", "scheme", "vanguard",
    "planar", "art_series", "reversible_card",
}

UPSERT_SQL = """
INSERT INTO cards (
    scryfall_id, oracle_id, name, lang, mana_cost, cmc, type_line, oracle_text,
    colors, color_identity, keywords, power, toughness, loyalty,
    set_code, collector_number, rarity, legal_commander, price_eur,
    card_faces, image_uri, game_changer, legal_duel, produced_mana, edhrec_rank,
    categories, price_eur_foil, banned_as_commander_duel
) VALUES %s
ON CONFLICT (scryfall_id) DO UPDATE SET
    oracle_id = EXCLUDED.oracle_id,
    name = EXCLUDED.name,
    mana_cost = EXCLUDED.mana_cost,
    cmc = EXCLUDED.cmc,
    type_line = EXCLUDED.type_line,
    oracle_text = EXCLUDED.oracle_text,
    colors = EXCLUDED.colors,
    color_identity = EXCLUDED.color_identity,
    keywords = EXCLUDED.keywords,
    power = EXCLUDED.power,
    toughness = EXCLUDED.toughness,
    loyalty = EXCLUDED.loyalty,
    rarity = EXCLUDED.rarity,
    legal_commander = EXCLUDED.legal_commander,
    price_eur = EXCLUDED.price_eur,
    price_eur_foil = EXCLUDED.price_eur_foil,
    card_faces = EXCLUDED.card_faces,
    image_uri = EXCLUDED.image_uri,
    game_changer = EXCLUDED.game_changer,
    legal_duel = EXCLUDED.legal_duel,
    banned_as_commander_duel = EXCLUDED.banned_as_commander_duel,
    produced_mana = EXCLUDED.produced_mana,
    edhrec_rank = EXCLUDED.edhrec_rank,
    categories = EXCLUDED.categories,
    updated_at = now()
"""


def _image_uri(card: dict) -> str | None:
    uris = card.get("image_uris")
    if uris:
        return uris.get("normal")
    faces = card.get("card_faces") or []
    if faces and faces[0].get("image_uris"):
        return faces[0]["image_uris"].get("normal")
    return None


def _price(value) -> float | None:
    return float(value) if value else None


def _row(card: dict) -> tuple:
    # `price_eur` est le prix NON-FOIL, uniquement. Reprendre le prix foil comme
    # repli faisait passer un prix de collectionneur pour un prix d'achat, dans
    # `cards_cheapest` comme dans les listes d'achats. Sans prix normal, la
    # carte est « prix inconnu » : elle n'est pas proposée à l'achat, faute de
    # pouvoir garantir le plafond de prix.
    prices = card.get("prices") or {}
    return (
        card["id"],
        card["oracle_id"],
        card["name"],
        card.get("lang", "en"),
        card.get("mana_cost"),
        card.get("cmc"),
        card.get("type_line"),
        card.get("oracle_text"),
        card.get("colors") or [],
        card.get("color_identity") or [],
        card.get("keywords") or [],
        card.get("power"),
        card.get("toughness"),
        card.get("loyalty"),
        card["set"],
        card["collector_number"],
        card.get("rarity"),
        (card.get("legalities") or {}).get("commander") == "legal",
        _price(prices.get("eur")),
        json.dumps(card["card_faces"]) if card.get("card_faces") else None,
        _image_uri(card),
        bool(card.get("game_changer")),
        # `restricted` en duel veut dire « banni comme commandant », pas
        # « banni » : la carte reste jouable dans les 99. Tester l'égalité à
        # "legal" écartait ces 27 cartes du format entier.
        _duel_legality(card) in ("legal", "restricted"),
        card.get("produced_mana") or [],
        card.get("edhrec_rank"),
        classify(card.get("type_line"), card.get("oracle_text"), card.get("produced_mana")),
        _price(prices.get("eur_foil")),
        _duel_legality(card) == "restricted",
    )


def _duel_legality(card: dict) -> str | None:
    return (card.get("legalities") or {}).get("duel")


def _wanted(card: dict) -> bool:
    return (
        card.get("lang") == "en"
        and not card.get("digital")
        and card.get("layout") not in SKIP_LAYOUTS
        and bool(card.get("oracle_id"))
    )


def main() -> None:
    with httpx.Client(timeout=60, headers=SCRYFALL_HEADERS) as client:
        bulk_index = client.get(f"{SCRYFALL_API_BASE}/bulk-data").json()
        entry = next(d for d in bulk_index["data"] if d["type"] == "default_cards")
        print(f"Téléchargement de {entry['name']} ({entry['compressed_size'] / 1e6:.0f} Mo compressés)...")

        with tempfile.NamedTemporaryFile(suffix=".jsonl.gz") as tmp:
            with client.stream("GET", entry["jsonl_download_uri"]) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_bytes():
                    tmp.write(chunk)
            tmp.flush()

            print("Upsert en base...")
            total = 0
            batch: list[tuple] = []
            with get_conn() as conn:
                with conn.cursor() as cur:
                    with gzip.open(tmp.name, "rt", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            card = json.loads(line)
                            if not _wanted(card):
                                continue
                            batch.append(_row(card))
                            if len(batch) >= BATCH_SIZE:
                                execute_values(cur, UPSERT_SQL, batch, page_size=BATCH_SIZE)
                                total += len(batch)
                                print(f"  {total} impressions synchronisées...")
                                batch.clear()
                    if batch:
                        execute_values(cur, UPSERT_SQL, batch, page_size=BATCH_SIZE)
                        total += len(batch)

                    # `cards_cheapest` est matérialisée : sans refresh, les
                    # résolutions de noms travaillent sur l'ancien instantané.
                    print("Refresh de la vue matérialisée cards_cheapest...")
                    cur.execute("REFRESH MATERIALIZED VIEW cards_cheapest")

    print(f"Sync terminée : {total} impressions.")


if __name__ == "__main__":
    main()
