"""
scripts/rank_commanders.py — classe les commandants possédés par victoire mesurée.

Chaque commandant monte son meilleur deck avec la collection, puis affronte le
même panel : les decks enregistrés. Les archétypes des meilleurs sont mesurés
de la même façon.

Exécution : `python scripts/rank_commanders.py`

**En ligne de commande seulement.** Le calcul dure plusieurs minutes : un
endpoint HTTP synchrone se ferait couper à 100 s par Cloudflare, comme la
synchronisation EDHREC avant lui.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import performance


def main() -> None:
    started = time.time()

    def progress(index, total, nom, win_rate) -> None:
        avancement = f"{index}/{total}" if index else "  archétype"
        print(f"  {avancement:>9}  {nom[:44]:46} {win_rate:.0%}")

    result = performance.rank(progress=progress)
    if result.get("error"):
        print(result["error"])
        raise SystemExit(1)

    print(f"\nClassement écrit : {result['commanders']} commandants, "
          f"{result['themes']} archétypes, {result['games_per_match']} parties par "
          f"affrontement, en {time.time() - started:.0f} s.")
    print(f"Panel : {result['panel']}")


if __name__ == "__main__":
    main()
