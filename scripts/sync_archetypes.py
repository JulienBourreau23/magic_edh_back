"""
scripts/sync_archetypes.py — le catalogue des archétypes du format.

Même organisation que `sync_edhrec.py` : la logique vit dans
`services.edhrec`, ce fichier ne fait que parser les arguments et afficher le
résumé.

**Pas d'endpoint HTTP équivalent, contrairement aux autres synchronisations.**
183 archétypes à une seconde de pause font 4 min 37 s (mesuré), et un
endpoint synchrone ne renvoie rien avant la fin : Kestra compterait l'attente
comme de l'inactivité et Cloudflare couperait à 100 s. Le `case`
`archetypes` de `deploy/kestra-sync.sh` appelle donc ce script par SSH.

Usage :
    python scripts/sync_archetypes.py              # tout le catalogue
    python scripts/sync_archetypes.py --limit 5    # les 5 plus joués, pour tester
    python scripts/sync_archetypes.py --delay 2    # pause entre requêtes
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.edhrec import DEFAULT_DELAY_SECONDS, sync_archetypes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS,
                        help="pause entre deux requêtes, en secondes")
    parser.add_argument("--limit", type=int, default=None,
                        help="ne traiter que les N archétypes les plus joués")
    args = parser.parse_args()

    resume = sync_archetypes(delay=args.delay, limit=args.limit)
    print(f"{resume['archetypes_found']} archétype(s) recensé(s), "
          f"{resume['synced']} synchronisé(s), "
          f"{resume['cards_total']} cartes, "
          f"{resume['commanders_total']} commandants.")

    for entree in resume["failed"]:
        print(f"  ECHEC : {entree['archetype']} — {entree['reason']}")


if __name__ == "__main__":
    main()
