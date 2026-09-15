"""
scripts/backfill_categories.py — rejoue `card_categories.classify()` sur toute
la table `cards`.

Les catégories sont figées au sync : corriger une règle de classification ne
change rien tant que la base garde l'ancien verdict. Ce script rattrape l'écart
sans retélécharger les 78 Mo de bulk data, et rafraîchit `cards_cheapest`, qui
fige sa propre copie des colonnes.

  python scripts/backfill_categories.py --dry-run   # montre le delta, n'écrit rien
  python scripts/backfill_categories.py             # applique et rafraîchit la vue
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from psycopg2.extras import execute_values

from db.core import get_conn
from services.card_categories import classify

BATCH_SIZE = 2000


def main(dry_run: bool) -> None:
    gained: Counter[str] = Counter()
    lost: Counter[str] = Counter()
    changed: list[tuple[str, list[str]]] = []

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT scryfall_id, type_line, oracle_text, produced_mana, categories FROM cards")
            for row in cur.fetchall():
                before = list(row["categories"] or [])
                after = classify(row["type_line"], row["oracle_text"], row["produced_mana"])
                if after == before:
                    continue
                changed.append((str(row["scryfall_id"]), after))
                for category in set(after) - set(before):
                    gained[category] += 1
                for category in set(before) - set(after):
                    lost[category] += 1

            print(f"{len(changed)} impressions reclassées")
            for category, count in sorted(gained.items()):
                print(f"  + {category:12} {count}")
            for category, count in sorted(lost.items()):
                print(f"  - {category:12} {count}")

            if dry_run:
                print("--dry-run : rien n'a été écrit.")
                conn.rollback()
                return

            for start in range(0, len(changed), BATCH_SIZE):
                execute_values(
                    cur,
                    "UPDATE cards SET categories = data.categories "
                    "FROM (VALUES %s) AS data(scryfall_id, categories) "
                    "WHERE cards.scryfall_id = data.scryfall_id::uuid",
                    changed[start:start + BATCH_SIZE],
                )

            # Même piège qu'au sync : la vue matérialisée garde l'ancien
            # instantané tant qu'on ne la rafraîchit pas.
            print("Refresh de la vue matérialisée cards_cheapest...")
            cur.execute("REFRESH MATERIALIZED VIEW cards_cheapest")

    print("Backfill terminé." if not dry_run else "")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv[1:])
