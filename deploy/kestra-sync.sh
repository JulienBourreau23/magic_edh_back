#!/usr/bin/env bash
# Point d'entrée unique des synchronisations lancées par Kestra en SSH.
#
# Pourquoi ce script existe plutôt qu'un appel direct : la clé publique de
# Kestra est posée dans `authorized_keys` avec `command="…/kestra-sync.sh"`,
# qui **force** l'exécution de ce fichier quelle que soit la commande demandée.
# Kestra n'obtient donc pas un shell sur le back, seulement le droit de lancer
# l'une des synchronisations listées ici. La commande réellement demandée
# arrive dans $SSH_ORIGINAL_COMMAND et sert uniquement d'aiguillage.
#
# Les syncs **longues** passent par là plutôt que par un endpoint HTTP : elles
# durent plusieurs minutes, et Kestra couperait un endpoint synchrone resté
# muet tout ce temps. Les scripts CLI existent déjà de toute façon. Seule la
# synchro des combos, qui tient en deux minutes, reste en HTTP.
set -euo pipefail

REPO=/opt/mtg-back/magic_edh_back

# `/tmp` est un tmpfs : les ~400 Mo du bulk data y seraient écrits en RAM, sur
# les 2 Go du conteneur. `/var/tmp` est sur le disque.
export TMPDIR=/var/tmp

cd "$REPO"

case "${SSH_ORIGINAL_COMMAND:-}" in
  scryfall)
    # Rafraîchit `cards` (~99 500 impressions) et termine par le REFRESH de la
    # vue matérialisée `cards_cheapest` — le script s'en charge lui-même.
    exec venv/bin/python scripts/sync_scryfall.py
    ;;
  edhrec)
    # Passée en SSH le jour où elle a dépassé dix minutes : une requête par
    # commandant **et par archétype**, pause d'une seconde entre chaque. À 36
    # commandants elle tenait en une minute et l'appel HTTP suffisait ; à 131
    # elle en demande seize, et Kestra coupait un endpoint synchrone resté muet
    # tout ce temps. Le coût croît avec la collection : ce seuil sera franchi
    # de nouveau, pas revenu en arrière.
    exec venv/bin/python scripts/sync_edhrec.py
    ;;
  french-names)
    # Alimente `card_names_fr` depuis le bulk `all_cards` (~400 Mo, lu en
    # streaming). À rejouer après chaque sortie de set, comme Scryfall.
    exec venv/bin/python scripts/sync_french_names.py
    ;;
  archetypes)
    # Le catalogue des archétypes du format (pages `/tags/` d'EDHREC) : une
    # requête pour l'index, puis une par archétype au-dessus du plancher — 183
    # sur les 270 recensés, soit 4 min 37 s mesurées avec la pause d'une
    # seconde. Même raison que pour `edhrec` : trop long pour un endpoint
    # HTTP, et il n'en existe d'ailleurs aucun pour cette synchronisation.
    exec venv/bin/python scripts/sync_archetypes.py
    ;;
  mtgtop8)
    # Les tops des tournois de Duel Commander (MTGTop8), qui remplacent EDHREC
    # pour conseiller un deck de duel. Incrémental : seuls les événements
    # inconnus sont demandés, une cinquantaine par semaine. Le premier passage
    # en compte un millier ; il est plafonné à 300 par exécution et se termine
    # donc en quatre semaines, ou d'un `--max-events 0` lancé à la main.
    exec venv/bin/python scripts/sync_mtgtop8.py
    ;;
  rank-commanders)
    # Classe les commandants possédés par victoire mesurée : des milliers de
    # parties simulées, plusieurs minutes. Ce n'est pas une synchronisation —
    # rien n'est récupéré à l'extérieur — mais c'est le même besoin : un calcul
    # trop long pour une requête HTTP, à rejouer quand la collection bouge.
    exec venv/bin/python scripts/rank_commanders.py
    ;;
  *)
    echo "Commande refusée : '${SSH_ORIGINAL_COMMAND:-<vide>}'." >&2
    echo "Valeurs acceptées : scryfall, french-names, edhrec, archetypes, mtgtop8, rank-commanders." >&2
    exit 2
    ;;
esac
