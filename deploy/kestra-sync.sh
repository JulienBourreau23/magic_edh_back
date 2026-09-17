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
  *)
    echo "Commande refusée : '${SSH_ORIGINAL_COMMAND:-<vide>}'." >&2
    echo "Valeurs acceptées : scryfall, french-names, edhrec." >&2
    exit 2
    ;;
esac
