# Installation du back sur `lxc-mtg-back` (192.168.1.143)

Debian 13 trixie, Python 3.13.5, 2 vCPU / 2 Go / 17 Go.

## Étapes root (une seule fois)

```bash
sudo apt install -y git python3-venv postgresql-client poppler-utils

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
venv/bin/python -m pytest -q          # 213 tests doivent passer
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
existante. Celles qui ont suivi le transfert initial :

```bash
psql -h 192.168.1.104 -U julien -d magic_edh -f scripts/migration_010_combos.sql
venv/bin/python scripts/sync_combos.py            # remplit la table `combos`
psql -h 192.168.1.104 -U julien -d magic_edh -f scripts/migration_011_normalize_names.sql
psql -h 192.168.1.104 -U julien -d magic_edh -f scripts/migration_012_themes.sql
psql -h 192.168.1.104 -U julien -d magic_edh -f scripts/migration_013_wishlist.sql
psql -h 192.168.1.104 -U julien -d magic_edh -f scripts/migration_014_ignored_cards.sql
psql -h 192.168.1.104 -U julien -d magic_edh -f scripts/migration_015_banned_as_commander.sql
psql -h 192.168.1.104 -U julien -d magic_edh -f scripts/rebuild_cheapest_view.sql   # obligatoire après le ADD COLUMN
venv/bin/python scripts/sync_scryfall.py          # seule façon de peupler la nouvelle colonne
psql -h 192.168.1.104 -U julien -d magic_edh -f scripts/migration_016_combo_description.sql
venv/bin/python scripts/sync_combos.py            # idem : les étapes des combos
```

Le méta du Duel Commander (MTGTop8, migration 022) — quatre tables neuves,
rien à reconstruire côté `cards` :

```bash
psql -h 192.168.1.104 -U julien -d magic_edh -f scripts/migration_022_duel_meta.sql
# Premier passage : ~1 000 tournois à ~7 s chacun, soit environ deux heures.
# Dans un tmux, ou laisser le flow hebdomadaire rattraper par tranches de 300.
venv/bin/python scripts/sync_mtgtop8.py --max-events 0
```

Tant que la table est vide, le duel retombe sur EDHREC et l'écran le signale :
déployer le code avant la migration ne casse rien. Puis importer
`kestra/sync-mtgtop8.yml` dans le namespace `mtg-edh` : le `case mtgtop8` de
`kestra-sync.sh` est déjà là.

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

Comptes **au moment du transfert** (15 septembre 2026) ; ils bougent à chaque
passage des flows de synchronisation.

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

## Ordonnancement par Kestra

Les synchronisations ne tournent **pas** par timer systemd : elles sont
planifiées par l'instance Kestra de `lxc-kestra` (192.168.1.119:8080,
Kestra 1.3.31 OSS), namespace `mtg-edh`. Les trois flows sont versionnés dans
`kestra/` et se déposent par **Flows → Import** (le collage dans l'éditeur
réindente ce qu'on lui donne et casse le YAML).

| Flow | Ce qu'il synchronise | Comment | Quand |
|---|---|---|---|
| `sync-scryfall.yml` | `cards` puis `card_names_fr` | SSH | 1er du mois, 2 h |
| `sync-edhrec.yml` | recommandations, archétypes | SSH | lundi 4 h |
| `sync-combos.yml` | catalogue Spellbook | HTTP | lundi 5 h |

### KV Store du namespace `mtg-edh`

Aucun identifiant ne vit dans les flows. Sept clés à créer dans
**Namespaces → `mtg-edh` → KV Store** — le namespace n'apparaît qu'une fois un
premier flow déposé, donc importer d'abord, remplir ensuite.

| Key | Valeur | Type |
|---|---|---|
| `magic_edh_api_url` | `http://192.168.1.143:8000` | STRING |
| `magic_edh_user` | identifiant applicatif | STRING |
| `magic_edh_password` | mot de passe applicatif | STRING |
| `mtg_back_ssh_host` | `192.168.1.143` | STRING |
| `mtg_back_ssh_port` | `52398` | NUMBER |
| `mtg_back_ssh_user` | `julien` | STRING |
| `mtg_back_ssh_key` | clé privée ed25519, les 8 lignes | STRING |

`kv()` est résolu **à l'exécution, pas à la sauvegarde** : une clé manquante ou
mal nommée ne se voit qu'au lancement, et Kestra s'arrête à la première — il
faut donc les créer toutes avant de relancer. Les valeurs sont stockées en
clair dans la base `kestra` ; pour le mot de passe applicatif, `secret()` et une
variable `SECRET_MAGIC_EDH_PASSWORD` en base64 dans le `docker-compose.yml` de
Kestra seraient plus propres.

**L'URL de l'API est celle du LAN, jamais le domaine public** :
`/admin/sync-edhrec` et `/admin/sync-combos` sont synchrones et dépassent les
100 s que Cloudflare tolère. Même raison pour suivre une longue exécution
depuis `http://192.168.1.119:8080` plutôt que par le domaine — sinon le flux de
logs est coupé et l'UI annonce l'instance injoignable alors qu'elle travaille.

### Accès SSH de Kestra (`deploy/kestra-sync.sh`)

Les syncs longues passent par SSH parce qu'un endpoint synchrone resté muet
plusieurs minutes se fait couper par Kestra. Seule celle des combos, qui tient
en deux minutes, reste en HTTP. Kestra n'obtient pas
de shell pour autant :

```bash
# Sur le poste d'administration, une paire dédiée (sans passphrase : Kestra
# s'authentifie sans interaction).
ssh-keygen -t ed25519 -N "" -C "kestra@lxc-kestra -> lxc-mtg-back" \
    -f ~/.ssh/kestra_mtg_back

# Sur lxc-mtg-back, la clé publique contrainte à un seul programme.
# `command=` force ce script quelle que soit la commande demandée ; celle-ci
# n'arrive que dans $SSH_ORIGINAL_COMMAND et sert d'aiguillage.
cat >> ~/.ssh/authorized_keys <<KEY
command="/opt/mtg-back/magic_edh_back/deploy/kestra-sync.sh",no-agent-forwarding,no-port-forwarding,no-user-rc,no-X11-forwarding ssh-ed25519 AAAA... kestra@lxc-kestra
KEY
chmod 600 ~/.ssh/authorized_keys
chmod +x /opt/mtg-back/magic_edh_back/deploy/kestra-sync.sh
```

Vérification — avec cette seule clé, tout doit être refusé sauf les deux
aiguillages. Attention à `IdentitiesOnly` : `-i` **s'ajoute** aux clés du
`~/.ssh/config` au lieu de les remplacer, et le test réussirait avec la clé
personnelle sans rien prouver.

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/kestra_mtg_back \
    -p 52398 -o ProxyJump=julienserveur-vpn julien@192.168.1.143 'whoami'
# → Commande refusée : 'whoami'.  (code 2)
```

**Ajouter une synchronisation par SSH, c'est ajouter un `case` dans
`kestra-sync.sh`**, pas seulement une tâche dans le flow. Le script y pose
aussi `TMPDIR=/var/tmp` : `/tmp` est un tmpfs, et les ~400 Mo du bulk data
`all_cards` y seraient écrits dans les 2 Go de RAM du conteneur.
