"""
scripts/sync_mtgtop8.py — enveloppe en ligne de commande autour de
`services.mtgtop8.sync`.

Récupère les tops des tournois de Duel Commander publiés sur MTGTop8 depuis la
dernière exécution, purge ce qui sort de la fenêtre et recalcule le méta
(`duel_card_stats`). Incrémental : un événement déjà en base n'est jamais
redemandé.

Usage :
    python scripts/sync_mtgtop8.py                  # jusqu'à 300 événements
    python scripts/sync_mtgtop8.py --max-events 0   # tout ce qui manque (~2 h au premier passage)
    python scripts/sync_mtgtop8.py --stats-only     # recalcule le méta sans rien télécharger
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.mtgtop8 import (DEFAULT_DELAY_SECONDS, DEFAULT_MAX_EVENTS, WINDOW_DAYS,
                              refresh_stats, sync)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS,
                        help="pause entre deux requêtes, en secondes")
    parser.add_argument("--max-events", type=int, default=DEFAULT_MAX_EVENTS,
                        help="plafond d'événements par exécution (0 : aucun)")
    parser.add_argument("--window-days", type=int, default=WINDOW_DAYS,
                        help="profondeur de la fenêtre glissante, en jours")
    parser.add_argument("--stats-only", action="store_true",
                        help="recalculer duel_card_stats sans rien télécharger")
    args = parser.parse_args()

    if args.stats_only:
        print(f"{refresh_stats()} carte(s) mesurée(s).")
        return

    if args.delay < 0.5:
        parser.error("--delay sous 0,5 s : MTGTop8 est un site gratuit, on ne le martèle pas.")

    resume = sync(delay=args.delay, window_days=args.window_days, max_events=args.max_events)
    print(f"{resume['events_listed']} événement(s) nouveau(x) listé(s), "
          f"{resume['events_saved']} enregistré(s), {resume['decks_saved']} deck(s), "
          f"{resume['unresolved_cards']} ligne(s) de carte non résolue(s).")
    if resume["events_remaining"]:
        print(f"  RESTE : {resume['events_remaining']} événement(s) au-delà du plafond — "
              "relancer pour continuer.")
    print(f"  {resume['purged']} événement(s) sorti(s) de la fenêtre, "
          f"{resume['cards_measured']} carte(s) mesurée(s).")
    for entree in resume["decks_skipped"]:
        print(f"  ÉCARTÉ : deck {entree['deck_id']} — commandant non reconnu "
              f"({', '.join(entree['commanders']) or 'aucun'})")
    for entree in resume["events_failed"]:
        print(f"  ÉCHEC  : événement {entree['event_id']} — {entree['reason']}")

    # Code de sortie non nul si rien n'a pu être enregistré alors qu'il y avait
    # du travail : Kestra doit voir l'échec, pas un succès vide.
    if resume["events_listed"] and not resume["events_saved"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
