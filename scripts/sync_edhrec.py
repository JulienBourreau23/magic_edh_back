"""
scripts/sync_edhrec.py — enveloppe en ligne de commande autour de
`services.edhrec.sync`.

La logique vit dans le service : ce fichier ne fait que parser les arguments et
afficher le résumé, pour que le même code serve au CLI, à un timer systemd et à
Kestra.

Usage :
    python scripts/sync_edhrec.py             # commandants de la collection
    python scripts/sync_edhrec.py --all       # + ceux déjà utilisés dans tes decks
    python scripts/sync_edhrec.py --delay 2   # pause entre requêtes, en secondes
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.edhrec import DEFAULT_DELAY_SECONDS, sync


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true",
                        help="inclure aussi les commandants de tes decks, pas seulement la collection")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS,
                        help="pause entre deux requêtes, en secondes")
    args = parser.parse_args()

    resume = sync(include_decks=args.all, delay=args.delay)
    print(f"{resume['commanders_found']} commandant(s) trouve(s), "
          f"{resume['synced']} synchronise(s), "
          f"{resume['recommendations_total']} recommandations.")

    for entree in resume["details"]:
        print(f"  {entree['commander']} — {entree['recommendations']} recommandations")
    for entree in resume["not_found"]:
        print(f"  ABSENT : {entree['commander']} (slug « {entree['slug']} »)")
    for entree in resume["failed"]:
        print(f"  ECHEC  : {entree['commander']} — {entree['reason']}")


if __name__ == "__main__":
    main()
