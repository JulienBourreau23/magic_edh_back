"""
scripts/sync_combos.py — enveloppe en ligne de commande autour de
`services.spellbook.sync`.

Comme pour EDHREC, la logique vit dans le service : le même code sert au CLI,
à un timer systemd et à l'endpoint d'administration.

Usage :
    python scripts/sync_combos.py
    python scripts/sync_combos.py --delay 2   # pause entre deux pages
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.spellbook import DEFAULT_DELAY_SECONDS, sync


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS,
                        help="pause entre deux pages, en secondes")
    args = parser.parse_args()

    def avancement(pages: int, variantes: int) -> None:
        print(f"  page {pages}, {variantes} variantes lues...", flush=True)

    resume = sync(delay=args.delay, progress=avancement)
    print(f"{resume['pages']} page(s), {resume['variants_seen']} variantes lues, "
          f"{resume['two_card_pairs']} paires de deux cartes.")
    print(f"{resume['stored']} combos enregistrés, "
          f"{resume['ignored_unknown_cards']} ignorés (carte absente de la base).")


if __name__ == "__main__":
    main()
