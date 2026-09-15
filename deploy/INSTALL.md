# Installation du back sur `lxc-mtg-back` (192.168.1.143)

Debian 13 trixie, Python 3.13.5, 2 vCPU / 2 Go / 17 Go.

## Étapes root (une seule fois)

```bash
sudo apt install -y git python3-venv postgresql-client

# Le dossier créé s'appelait « mgt-back » (faute de frappe pour « mtg »).
sudo mv /opt/mgt-back /opt/mtg-back

# Cache d'images de cartes : régénérable, à exclure des sauvegardes.
sudo mkdir -p /srv/mtg-cards && sudo chown julien:julien /srv/mtg-cards
```

## Installation applicative (utilisateur `julien`)

```bash
git clone https://github.com/JulienBourreau23/magic_edh_back.git /opt/mtg-back/magic_edh_back
cd /opt/mtg-back/magic_edh_back
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python -m pytest -q          # 55 tests doivent passer
```

## `.env`

Recopier `.env.example` et remplir. `JWT_SECRET` et `AUTH_PASSWORD_HASH` se
génèrent avec `venv/bin/python scripts/hash_password.py` — le mot de passe en
clair n'est stocké nulle part.

La base vit sur `lxc-pg18` (192.168.1.104, PostgreSQL 18.6) :

```
PG_HOST=192.168.1.104
PG_DATABASE=magic_edh
CARD_IMAGES_DIR=/srv/mtg-cards
CORS_ORIGINS=https://mtg-edh.julien-cloud.eu
```

## Schéma et données

```bash
for f in scripts/migration_0*.sql; do psql -h 192.168.1.104 -U julien -d magic_edh -f "$f"; done
venv/bin/python scripts/sync_scryfall.py       # ~99 500 cartes
venv/bin/python scripts/sync_french_names.py   # ~30 000 alias, bulk de 393 Mo
venv/bin/python scripts/sync_edhrec.py
```

`sync_french_names.py` écrit ~400 Mo dans un fichier temporaire. `/tmp` étant un
tmpfs (en RAM) sur ce conteneur, exporter `TMPDIR=/var/tmp` avant de le lancer —
l'unit systemd le fait déjà pour le service.

Toute modification de `cards` doit finir par `REFRESH MATERIALIZED VIEW
cards_cheapest`, et tout `ALTER TABLE cards ADD COLUMN` impose de rejouer
`scripts/rebuild_cheapest_view.sql`.

## Service

```bash
sudo cp deploy/mtg-back.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now mtg-back
curl -s localhost:8000/health
```

Déploiements suivants : `./deploy.sh`.
