#!/usr/bin/env bash
# Déploiement du back Magic EDH sur lxc-mtg-back.
set -euo pipefail

cd "$(dirname "$0")"

git pull
venv/bin/pip install -q -r requirements.txt

# Les tests couvrent parsing, mana, classification et reproductibilité de la
# simulation : les endroits où une erreur est silencieuse. On ne redémarre pas
# un service qui les casse.
venv/bin/python -m pytest -q

sudo systemctl restart magic-edh-back
echo "✓ Back déployé"
