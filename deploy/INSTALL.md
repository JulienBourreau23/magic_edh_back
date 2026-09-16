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
venv/bin/python -m pytest -q          # 83 tests doivent passer
```

## `.env`

Déjà en place sur le conteneur (`chmod 600`), avec la base, le rôle et
`JWT_SECRET` renseignés. **Une seule valeur reste à remplir** :

```bash
venv/bin/python scripts/hash_password.py   # coller le hash dans AUTH_PASSWORD_HASH
```

Le mot de passe en clair n'est stocké nulle part.

## Migrations

Les `scripts/migration_0*.sql` sont à rejouer dans l'ordre sur une base
existante. Les deux dernières :

```bash
psql -h 192.168.1.104 -U julien -d magic_edh -f scripts/migration_010_combos.sql
venv/bin/python scripts/sync_combos.py            # remplit la table `combos`
psql -h 192.168.1.104 -U julien -d magic_edh -f scripts/migration_011_normalize_names.sql
```

`migration_011` crée `normalize_card_name()`, dont dépend la résolution des
noms : **six tests échouent en `skip` tant qu'elle n'est pas jouée**, et les
decklists françaises accentuées repartent au repli flou. Elle ne touche aucune
donnée, elle est rejouable.

**Une migration doit laisser ses tables au rôle applicatif** (celui du `.env`),
pas au compte qui l'a jouée : sinon l'application ne peut ni écrire ni tronquer
la table, et l'erreur n'arrive qu'au premier sync. `migration_010` aligne
elle-même ses droits sur le propriétaire de `cards` ; reprendre ce bloc dans
les migrations suivantes qui créent une table.

## Base de données — faite

Le rôle et la base `magic_edh` existent sur `lxc-pg18` (192.168.1.104,
PostgreSQL 18.6), avec `pg_trgm` pour la recherche floue. Le schéma et les
données ont été transférés depuis la base de développement plutôt que
reconstruits : mêmes comptes à la ligne près.

| Table | Lignes |
|---|---|
| `cards` | 99 539 |
| `cards_cheapest` (matview) | 34 019 |
| `card_names_fr` | 30 090 |
| `commander_recommendations` | 1 627 |
| `collection` | 125 |
| `decks` / `deck_cards` | 3 / 188 |

Aucune ligne à ajouter dans `pg_hba.conf` : une règle
`host all all 192.168.1.0/255.255.255.0 scram-sha-256` couvre déjà tout le LAN,
donc le LXC back est autorisé d'office.

### Rafraîchir les données plus tard

```bash
venv/bin/python scripts/sync_scryfall.py       # ~99 500 cartes
venv/bin/python scripts/sync_french_names.py   # ~30 000 alias, bulk de 393 Mo
venv/bin/python scripts/sync_edhrec.py
venv/bin/python scripts/sync_combos.py         # ~4 000 combos à deux cartes
```

`sync_combos.py` parcourt une quarantaine de pages de l'API Commander
Spellbook, qui limite le débit : le script encaisse les 429 en doublant
l'attente, mais ne lance pas deux synchros coup sur coup. La table n'est
réécrite qu'à la fin — un échec en cours de route laisse l'ancien catalogue
intact.

Après une correction d'une règle de `services/card_categories.py`, les
catégories déjà en base gardent l'ancien verdict : les rejouer sans
retélécharger le bulk data (le script rafraîchit la vue lui-même).

```bash
venv/bin/python scripts/backfill_categories.py --dry-run   # montre le delta
venv/bin/python scripts/backfill_categories.py
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
