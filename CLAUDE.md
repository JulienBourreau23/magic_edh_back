# Magic EDH — vue d'ensemble du projet

Assistant de deck-building et d'équilibrage EDH (Commander) : import de decklist,
fiche deck, estimation de bracket, simulation de sorties, comparaison de decks et
suggestions d'amélioration. Deux sous-projets **indépendants** (pas de monorepo,
pas de package.json/pyproject racine), reliés uniquement par HTTP — même
organisation que `sw-coaching` :

```
magic_edh/
├── magic_edh_backend/backend/              → API FastAPI (Python) + Postgres
└── magic_edh_frontend/magic_edh_frontend/  → App Next.js (TypeScript)
```

## Principe directeur : l'IA en dernier recours

**Tout ce qui est calculable est calculé.** Aucun modèle de langage n'intervient
aujourd'hui dans le projet : la vitesse d'un deck, sa régularité, sa manabase,
son bracket et ses manques sont des grandeurs mesurables. Elles sont obtenues
par tirage aléatoire (simulation Monte-Carlo), couplage biparti (castabilité) et
comptage (rôles, sources de couleur), avec une graine fixe pour rester
reproductible.

Une IA n'a de sens ici que pour ce qui n'est pas calculable : commenter une
partie en langage naturel, ou arbitrer des interactions de règles. Si on
l'ajoute (LXC IA, même hôte qu'Ollama pour `sw-coaching`), elle doit
**commenter des faits déjà calculés**, jamais produire les chiffres elle-même.

## Connexion back ↔ front

- **Base URL** : `NEXT_PUBLIC_API_URL` (`lib/api.ts`), définie dans `.env.local`.
  En dev local : `http://localhost:8000`.
- **Auth JWT** sur tous les routeurs sauf `/health` et `/auth/login` — voir le
  chapitre « Authentification ». Le jeton vit dans le `localStorage`, ce qui
  force les pages qui chargent des données à être des composants client.
- **CORS** : whitelist dans `backend/config.py` (`CORS_ORIGINS`).
- **Images de cartes** : le back sert `/card-images` (monté sur `CARD_IMAGES_DIR`,
  `/srv/mtg-cards` en prod — comme `/icons` → `/srv/monsters` pour sw-coaching).
  Téléchargées à la demande, 6 en parallèle, en écriture atomique. Le front
  retombe sur l'URL Scryfall tant qu'une image n'est pas rapatriée.

## Formats : duel ≠ multi

Un deck porte un `format` (`commander` ou `duel`) qui **change la banlist
appliquée** : Sol Ring et Ancient Tomb sont légaux en Commander multijoueur et
bannis en Duel Commander. D'où deux colonnes distinctes (`legal_commander`,
`legal_duel`) et non un booléen unique.

## Arborescence — backend (`magic_edh_backend/backend/`)

```
backend/
├── main.py                   # FastAPI, CORS, mount /card-images, routers
├── config.py                 # env vars (PG_*, CARD_IMAGES_DIR, CORS_ORIGINS, Scryfall)
├── auth.py                   # JWT ; identifiants pris dans l'environnement
├── db/
│   ├── core.py               # pool Postgres
│   ├── cards.py              # résolution de noms, recherche, cartes candidates
│   ├── decks.py              # decks, deck_cards, import_issues, CRUD
│   ├── collection.py         # ce qu'on possède, par oracle_id
│   ├── wishlist.py           # ce qu'on envisage d'acheter — même clé, exprès
│   ├── commanders.py         # commandants possédés + recommandations EDHREC
│   ├── themes.py             # archétypes EDHREC d'un commandant et leurs cartes
│   ├── archetypes.py         # archétypes du format, et ce qu'ils coûteraient
│   ├── rules.py              # banlists, Game Changers
│   ├── duel_meta.py          # tops de tournoi de duel : taux, profils, viviers
│   └── combos.py             # combos à deux cartes présents dans un deck
├── routers/
│   ├── decks.py              # import, CRUD, simulation, suggestions
│   ├── cards.py              # recherche
│   ├── collection.py         # saisie et quantités
│   ├── wishlist.py           # liste de recherche + passage en collection
│   ├── must_have.py          # cartes à avoir, par type
│   ├── deck_ideas.py         # quel deck monter
│   ├── deck_plans.py         # plan de 4 decks à monter
│   ├── competitive.py        # construction d'un deck compétitif
│   ├── archetypes.py         # catalogue des archétypes et leurs articles
│   ├── rules.py              # banlists, brackets, Game Changers
│   ├── balance.py            # équilibrage d'un groupe de decks
│   ├── matchup.py            # comparaison de deux decks
│   ├── auth.py               # /auth/login, /auth/me
│   └── admin.py              # déclenche les syncs EDHREC et combos (Kestra)
├── services/
│   ├── mana.py               # coût de mana + castabilité (couplage biparti)
│   ├── card_categories.py    # classification (ramp, draw, removal, stax...)
│   ├── decklist_parser.py    # parsing texte brut + résolution + persistance
│   ├── collection_import.py  # saisie en masse de la collection
│   ├── wishlist_import.py    # saisie en masse de la liste de recherche
│   ├── deck_analysis.py      # courbe, prix, légalité, manabase, bracket
│   ├── simulation.py         # Monte-Carlo goldfish + main de départ
│   ├── duel.py               # duel simulé coup par coup
│   ├── suggestions.py        # diagnostics -> cartes à ajouter / retirer
│   ├── matchup.py            # comparaison sur axes mesurés
│   ├── allocation.py         # répartit la collection entre les decks
│   ├── balance.py            # plan d'équilibrage d'un groupe
│   ├── deck_plans.py         # comparaison par commandant + 4 decks équilibrés
│   ├── deck_ideas.py         # commandants classés par couverture du noyau
│   ├── competitive.py        # deck compétitif bâti sur la collection
│   ├── must_have.py          # cartes à avoir, par type
│   ├── combos.py             # combos présents dans un deck
│   ├── edhrec.py             # récupération EDHREC (module isolé exprès)
│   ├── mtgtop8.py            # tops des tournois de Duel Commander (module isolé)
│   ├── archetype_notes.py    # le principe de chaque archétype, écrit à la main
│   ├── bracket_rules.py      # le texte des brackets + la démonstration par le moteur
│   ├── spellbook.py          # import du catalogue Commander Spellbook
│   ├── magic_ville_pdf.py    # découpage d'une planche de proxys
│   └── card_images.py        # téléchargement à la demande
├── scripts/
│   ├── migration_0*.sql      # schéma et colonnes successives
│   ├── rebuild_cheapest_view.sql  # définition canonique de la vue matérialisée
│   ├── sync_scryfall.py      # bulk data Scryfall -> cards (+ REFRESH)
│   ├── sync_french_names.py  # alias français (bulk all_cards, ~400 Mo)
│   ├── sync_edhrec.py        # recommandations et archétypes par commandant
│   ├── sync_archetypes.py    # catalogue des archétypes du format
│   ├── sync_combos.py        # catalogue Commander Spellbook
│   ├── sync_mtgtop8.py       # méta du Duel Commander (incrémental)
│   ├── backfill_categories.py # rejoue la classification sans retélécharger
│   ├── decklist_from_pdf.py  # planche magic-ville -> decklist
│   └── hash_password.py      # hash bcrypt pour AUTH_PASSWORD_HASH
├── kestra/                   # les flows d'ordonnancement
├── deploy/                   # unit systemd, INSTALL.md, kestra-sync.sh
└── tests/                    # `python -m pytest`
```

### Modèle de données

- `cards` : impressions Scryfall (anglais, non-digital, hors jetons), avec
  `legal_commander` / `legal_duel`, `price_eur` (**prix non-foil uniquement** ;
  le prix foil vit dans `price_eur_foil` et n'est jamais utilisé comme repli —
  une carte sans prix normal est « prix inconnu », donc jamais proposée à
  l'achat), `game_changer` (liste officielle
  du Commander Format Panel, synchronisée par Scryfall), `produced_mana`
  (sources de couleur exactes), `edhrec_rank` (popularité) et `categories`
  (rôles calculés par `card_categories.classify()` au moment du sync).
- `cards_cheapest` (**vue matérialisée**) : une ligne par `oracle_id`,
  l'impression la moins chère. Matérialisée parce qu'en vue simple le filtre sur
  `name` ne peut pas descendre sous le `DISTINCT ON` : chaque résolution triait
  ~41k lignes (~140 ms, soit ~12 s pour importer un deck ; c'est 0,06 s
  aujourd'hui).
- `decks` / `deck_cards` / `deck_import_issues` : un deck, ses cartes (quantité,
  drapeau commandant) et les lignes de decklist non résolues — corrigeables
  depuis l'interface.

### Deux pièges d'exploitation

1. **Toute modification de `cards` doit finir par
   `REFRESH MATERIALIZED VIEW cards_cheapest`** (fait par `sync_scryfall.py`),
   sinon la résolution de noms travaille sur un instantané périmé.
2. **Tout `ALTER TABLE cards ADD COLUMN` impose de rejouer
   `scripts/rebuild_cheapest_view.sql`** : une vue matérialisée fige sa liste de
   colonnes à la création, et `REFRESH` ne l'élargit pas — la nouvelle colonne
   resterait invisible. Et si la colonne vient de Scryfall, il faut **en plus**
   relancer `sync_scryfall.py` : elle naît à sa valeur par défaut partout, et
   seule une synchronisation complète la renseigne (cas de
   `banned_as_commander_duel`, migration 015 ; `banned_commander`,
  `banned_duel` et `set_type`, migration 021).

### Collection et minimisation des achats

La table `collection` est indexée par `oracle_id` (on possède « un Sol Ring »,
l'édition est sans effet sur la construction). **Les terrains de base n'y
figurent jamais** : quantité supposée illimitée, ils ne génèrent aucun achat.

Elle s'alimente par deux chemins, qui partagent l'agrégation
(`decklist_parser.collection_entries`) : la page `/collection`, et l'import de
decklist quand on coche **« ce deck est déjà monté »** (`add_to_collection`).
Le second est *opt-in* : un deck seulement envisagé ne prouve pas qu'on possède
ses cartes, alors qu'un deck monté contient physiquement ses exemplaires — sans
quoi on conseillerait d'acheter ce qui est déjà dans la boîte. Les quantités
s'additionnent (`ON CONFLICT ... quantity + EXCLUDED.quantity`), ce qui est la
bonne sémantique ici : deux decks montés avec un Sol Ring chacun donnent deux
exemplaires, donc zéro achat. **Corollaire : réimporter deux fois le même deck
double sa contribution**, il n'y a pas de garde d'idempotence.

La règle structurante est physique : **un exemplaire ne peut être que dans un
deck à la fois**. `services/allocation.py` répartit donc la collection entre les
decks sélectionnés, et comme le format est singleton, le nombre d'achats d'une
carte vaut exactement `max(0, decks qui la veulent − exemplaires possédés)` —
pas d'optimisation combinatoire cachée, le résultat se vérifie à la main.

Quand plusieurs decks réclament la même carte, **l'ordre de sélection décide** :
le premier servi la prend, les suivants doivent l'acheter. C'est explicite et
modifiable par l'utilisateur plutôt qu'arbitré en douce.

`services/balance.py` en tire un plan pour un groupe de decks (4 maximum) :

- Bracket visé par défaut = **le plus faible du groupe**, parce que retirer des
  cartes ne coûte rien alors qu'en ajouter coûte de l'argent.
- Les cartes conseillées sont d'abord prises dans la collection (gratuit) et
  réservées au fur et à mesure, puis achetées sous le plafond de prix.
- Le classement des achats suit « le moins d'achat possible » : tri par prix
  croissant, le rang EDHREC servant de **filtre de qualité en amont**
  (`MAX_EDHREC_RANK`) pour que « le moins cher » reste « le moins cher parmi les
  cartes réellement jouées ».

La liste d'achats consolidée s'exporte en PDF côté navigateur
(`lib/shopping-pdf.ts`, jsPDF — même approche que sw-coaching). Les deux pages
qui produisent des achats (`/balance` et `/deck-plans`) renvoient **la même
forme** `ShoppingItem`, c'est ce qui permet un seul exportateur.

### Liste de recherche (`/wishlist`)

Ce qu'on **envisage** d'acheter, par opposition à la collection qui est ce
qu'on possède. Les deux tables ont volontairement **la même clé** (`oracle_id`)
et les mêmes colonnes d'affichage, et ce n'est pas de la symétrie décorative :
c'est ce qui permet à l'achat de faire basculer une ligne d'une table à l'autre
**sans rien convertir**.

`POST /wishlist/{oracle_id}/acquire` est ce qui justifie la table. Sans ce
geste, il faudrait retirer la carte d'un côté et la ressaisir de l'autre, et la
collection finirait fausse — or c'est elle qui pilote `/balance`,
`/deck-plans`, `/competitive` et `/must-have`. Trois précautions en découlent :

- **Les deux écritures sont dans la même transaction**, avec un `SELECT ...
  FOR UPDATE` sur la ligne. Une coupure entre les deux perdrait la carte des
  deux côtés ou la compterait deux fois, et l'erreur se paierait en argent.
- **L'acquisition peut être partielle** : deux exemplaires cherchés, un seul
  trouvé en boutique. Le reste attend dans la liste.
- **La quantité tombée à zéro supprime la ligne** plutôt que de laisser un
  zéro, pour que `list_all` n'ait pas à filtrer ce qui n'existe plus.

Les quantités **s'additionnent** à l'ajout, comme dans la collection et pour la
même raison : vouloir une carte pour deux decks, c'est en vouloir deux. La note
du dernier ajout l'emporte — c'est la plus récente, donc celle qui explique
pourquoi la carte est encore là.

Deux détails qui évitent de mal lire l'écran :

- **Le tri est par prix décroissant.** Une liste de recherche sert à prévoir un
  budget : ce sont les cartes chères qui décident, pas les cartes à 0,20 €.
- **`unknown_price` est compté à part** dans les statistiques. Une carte sans
  prix non-foil connu n'entre pas dans le total, et le dire empêche de lire ce
  total comme complet — c'est la même règle que partout : prix inconnu n'est
  pas prix nul.

**Les visuels sont rapatriés ici** (`ensure_images`), contrairement à
`/must-have` : la liste de recherche reste courte par nature, quelques dizaines
de cartes, alors que les cartes à avoir en comptent près de quatre cents.

Les terrains de base n'y entrent jamais, comme dans la collection : supposés
disponibles sans limite, ils ne se cherchent pas. La saisie en masse partage le
parseur des decklists (`decklist_parser`) — même format d'entrée, seule la
destination change.

### Le bouton « + recherche », et pourquoi il se tait parfois

Tous les écrans qui **conseillent** une carte permettent de l'envoyer dans la
liste de recherche : suggestions, équilibrage, cartes à avoir, idée de deck,
deck compétitif, et les deux listes d'achats. Un seul composant
(`components/WishlistButton.tsx`), pour une raison qui n'est pas cosmétique :
**les quantités de la liste de recherche s'additionnent**. Un bouton toujours
actif transforme donc un second clic — ou un simple retour sur la page — en
second exemplaire demandé, sans rien dire. Une carte déjà cherchée affiche
« déjà cherchée » et ne fait rien.

Le compte vient du serveur (`wanted_quantity`), exposé aux trois endroits qui
produisent des conseils :

- `db/cards.find_candidates` — **le point d'entrée unique** de `/suggestions`
  et `/balance`, comme pour les refus : une jointure, deux écrans ;
- `db/themes.build_pool` — le vivier du deck compétitif ;
- `db/wishlist.annotate_wanted` — les listes d'achats déjà assemblées
  (`/balance`, `/deck-plans`), qui n'ont pas de requête unique où poser une
  jointure.

`annotate_wanted` est appelé **par les routers**, jamais par les services qui
calculent ces listes. Deux raisons, et elles se paieraient toutes les deux :
ces calculs sont testés sans base, et `/deck-plans` évalue des dizaines de
groupes dont un seul est retenu — une requête par groupe serait payée pour
rien.

Après un ajout réussi, le bouton bascule **localement** : recharger une page de
conseils pour un booléen coûterait des dizaines de requêtes SQL, et sur
`/must-have` cela relancerait seize requêtes à chaque clic.

### Monter quatre decks d'un coup (`/deck-plans`)

`services/deck_plans.py` répond à « fais-moi quatre decks équilibrés dont les
manques coûtent le moins cher ». Il ne part pas des decks importés mais des
**commandants possédés**, garnis des cartes qu'EDHREC voit jouées avec eux.

Le point qui n'est pas intuitif : **le coût d'un groupe n'est pas la somme des
coûts individuels.** Un exemplaire ne pouvant être que dans un deck à la fois,
quatre decks qui réclament les mêmes cartes obligent à racheter les doublons.
C'est pourquoi on évalue des *combinaisons* (C(n,4), plafonnées par
`MAX_COMMANDERS_COMPARED`) au lieu d'aligner les quatre commandants les mieux
couverts — un commandant à 18 € tout seul peut coûter 129 € dans un groupe.

Trois règles portent la construction :

- **Les quotas de rôle d'abord** (`deck_analysis.ROLE_TARGETS`), le remplissage
  jusqu'à 63 non-terrains ensuite : l'équilibre ne se rattrape pas après coup.
  Le classement du pool est « ce que je possède d'abord, puis le plus joué, et à
  popularité comparable le moins cher » (bandes de 5 points d'inclusion).
- **Le plus contraint sert en premier** : dans un groupe, le commandant qui a le
  moins de cartes possédées choisit avant les autres. L'inverse ferait prendre
  par un deck abondant des exemplaires dont un autre a un besoin exclusif.
- **Les 36 terrains ne coûtent rien** : terrains non-basiques déjà possédés,
  puis terrains de base répartis au prorata des symboles de mana du noyau
  (commandant compris). Aucune manabase n'est achetée.

Le tableau de comparaison, lui, montre chaque commandant **monté seul**,
collection entière disponible : c'est le seul point de vue où ils sont
comparables entre eux. Ne pas additionner ses colonnes de coût pour prévoir un
groupe, elles ne s'additionnent pas.

#### Choisir les quatre commandants un par un

La page se lit de deux façons, et la réponse du back le dit (`after_selection`) :

- **sans sélection**, le tableau montre chaque commandant *monté seul*,
  collection entière disponible — le seul point de vue où ils sont comparables
  entre eux ;
- **dès le premier choisi**, il montre ce que chaque commandant restant
  pourrait encore monter **avec ce que les decks déjà choisis n'ont pas pris**
  (`_next_candidates`). C'est là que la sélection devient honnête : un
  commandant parfait sur la collection entière peut s'effondrer une fois qu'un
  premier deck a pris les mêmes cartes, et un autre remonter parce que ses
  cartes n'intéressaient personne. Les évaluer sur une collection intacte
  reviendrait à proposer quatre fois le même deck.

Le remplacement n'a rien de spécial à coder : une carte prise n'est plus
disponible, donc le constructeur retient la suivante du **même rôle** dans le
vivier restant. Quand il n'y en a plus, le créneau reste vide et le compte
« noyau 51/63 » le dit. « Trop de manques » n'est pas un seuil inventé : c'est
l'écart aux repères de rôle du projet (`role_gap`), et la ligne reste cliquable
— c'est un avertissement, pas une interdiction.

**L'ordre des clics décide du service** (`preserve_order`), contrairement au
choix automatique qui sert « le plus contraint d'abord ». Sans ça, ajouter un
troisième deck rebattrait le contenu des deux premiers, et l'écran cesserait de
raconter ce qu'on vient de faire.

#### Les decks déjà enregistrés ne sont pas réservés par défaut

La règle « un exemplaire ne peut être que dans un deck à la fois » vaut
**entre les quatre decks du plan** — vérifié sur la collection réelle : 392
créneaux, aucune carte employée au-delà du stock.

Face aux decks *déjà enregistrés*, c'est un choix, pas une évidence
(`reserve_existing_decks`, **faux par défaut**) : monter quatre decks
équilibrés pour jouer entre amis, c'est justement rebattre les cartes de ceux
qu'on a déjà. L'interrupteur « mes decks gardent leurs cartes » sert le cas
inverse — monter quatre decks *de plus* — et s'appuie sur
`decks_db.committed_quantities()` + `deck_plans.free_copies()` (soustraction
bornée à zéro : un deck importé sans la case « déjà monté » n'a pas alimenté la
collection, ses cartes peuvent donc être engagées sans être possédées).

Deux points à garder en tête :

- **Rien en base ne dit qu'un deck est *physiquement* monté** : la case « ce
  deck est déjà monté » de l'import alimente la collection mais n'est pas
  conservée. Réserver suppose donc que tous les decks enregistrés le sont. Une
  colonne `assembled` sur `decks` serait la vraie réponse si le besoin se
  précise.
- **Réserver ne coûtait rien en qualité** sur la collection réelle : 480
  exemplaires immobilisés sur 2 111, et le plan sortait toujours quatre decks
  complets. Seul le quatrième commandant changeait. Le défaut se justifie donc
  par l'intention, pas par le résultat.

#### Le mode « sans achat »

`owned_only` répond à une autre question : « qu'est-ce que je peux monter ce
soir, sans rien acheter ». Aucune carte absente de la collection n'entre dans
les decks, et la liste d'achats disparaît de l'écran plutôt que d'afficher zéro.

Trois conséquences qui ne se devinent pas :

- **Le vivier s'élargit à toute la collection** (`with_owned_cards`), identité
  de couleur respectée. Les recommandations EDHREC ne connaissent que ce que
  les autres jouent derrière ce commandant : s'y limiter aurait proposé des
  decks de vingt cartes alors que la collection en contient des centaines de
  jouables. Les cartes conseillées gardent leur `inclusion_rate` et passent
  devant ; le reste de la collection suit, classé par rang EDHREC. Cet
  élargissement est **réservé à ce mode** — avec achats, la page répond « le
  deck qu'EDHREC monte derrière ce commandant », et y verser toute la
  collection changerait la question.
- **Le prix ne départage plus rien**, tout est déjà payé : `_sort_key` bascule
  sur le rang EDHREC, et le plafond de prix disparaît de l'écran.
- **Un noyau peut rester incomplet.** C'est un fait sur la collection, pas un
  échec : l'interface écrit « 27/63, 36 créneaux vides » au lieu de faire
  croire à un deck complet. C'est aussi pourquoi `_group_score` compte
  désormais le **remplissage** juste après l'écart aux rôles : quatre decks
  complets valent mieux qu'un groupe mieux étalé en bracket mais troué.

Un plafond de prix à zéro n'aurait pas suffi à exprimer « sans achat » :
quelques cartes valent 0,00 € sans être pour autant dans la boîte.

#### Enregistrer les decks, puis les améliorer dans le temps

`POST /deck-plans/create` transforme les decks proposés en vrais decks. C'est le
chaînon qui manquait : tout ce qui améliore un deck ensuite — `/balance`, les
suggestions, les refus de conseil — a besoin d'un deck qui existe. La page
renvoie donc vers `/balance?decks=…`, déjà pointé sur les quatre decks créés :
c'est **là** que se décident les achats, au fil du temps et sous plafond de
prix.

Trois précautions :

- **Le groupe est recalculé côté serveur** à partir des seuls `oracle_id` des
  commandants. La decklist n'est pas envoyée par le navigateur : la collection
  a pu bouger entre l'affichage et le clic, et une liste reçue du client serait
  une seconde vérité à vérifier.
- **Un commandant qui a déjà un deck est ignoré, pas dupliqué**, et la réponse
  le dit (`skipped`).
- **Rien n'est ajouté à la collection.** Ces cartes y sont déjà — c'est la
  condition même du mode sans achat — et les compter deux fois ferait
  disparaître des achats pourtant nécessaires.

#### Le piège de performance : une requête par deck construit

Cette page construit **des milliers de decks** : 131 commandants montés seuls,
puis quatre decks par groupe évalué (C(12,4) = 495), soit 2 111 constructions.
Chacune cherchait ses combos par une requête SQL — 2 111 allers-retours vers une
base qui vit sur une autre machine en production.

`combos.matcher_for(vivier)` charge le catalogue **une fois** et croise ensuite
en mémoire, à résultat et ordre identiques. Mesuré à l'échelle de la
collection : 5,4 s → 2,0 s sur base locale, et surtout 2 111 allers-retours
réseau en moins. C'est exactement le genre de somme qui fait dépasser le
**plafond de 100 s de Cloudflare**, lequel coupe la réponse sans rien laisser :
le navigateur n'affiche alors qu'un « NetworkError », sans code HTTP ni message.

La durée est tracée dans `journalctl -u mtg-back` (`deck-plans : N commandants
en X s`) : c'est la seule façon de voir venir ce plafond, puisque la réponse
coupée n'en dit rien.

### Diagnostic de manabase : une cible par couleur, pas un plancher commun

Une couleur est jugée sous-alimentée par rapport à **sa propre demande**
(`mana.sources_needed`, loi hypergéométrique sur les cartes vues au tour visé),
et non contre un nombre fixe. Le plancher absolu qui existait avant
(`MIN_SOURCES_PER_COLOR = 10`) trouvait normales 16 sources bleues pour 51
symboles bleus **et** 19 sources rouges pour 11 symboles : il ne pouvait rien
dire d'un deck mal réparti, seulement d'un deck pauvre.

`SOURCE_CONFIDENCE = 0.80` n'est pas la fiabilité visée (90 %) mais la valeur
qui, dans ce modèle, retombe sur les tables de manabase publiées : le modèle ne
simule ni mulligan ni pioche, il est donc plus pessimiste qu'une vraie
simulation à confiance égale. Un test fige la comparaison — **changer cette
constante sans la refaire ferait dériver toutes les cibles en silence.**

Le piège, lui, est dans le conseil : **les cibles par couleur ne se comparent
pas entre elles.** Prises séparément, elles réclament ensemble plus de sources
que le deck n'a de terrains, et la couleur à la cible la plus haute n'est pas
celle qui bloque le plus de cartes — un Jeskai à 51 symboles bleus simples et
20 blancs souvent doubles donne une cible blanche supérieure à la bleue. La
répartition des terrains de base est donc choisie en minimisant
`expected_stuck_cards` (nombre de cartes qui restent en main faute des bonnes
couleurs), parce qu'elle compte des cartes. Deux conséquences :

- Une couleur peut rester signalée sous-alimentée alors que le conseil ne la
  renforce pas : cela veut dire que des basiques n'y suffiront pas. Ce n'est
  pas une contradiction, et l'interface l'écrit.
- Chaque demande est pondérée par la probabilité que la carte soit **en main**
  au tour visé. Sans ça le commandant compte pour une carte sur 99, alors qu'il
  est disponible à chaque tour : un splash porté par le seul commandant se
  faisait affamer (trois Montagnes conseillées sur un deck qui en veut huit).

Le conseil ne change jamais le **nombre** de terrains : c'est un échange de
basiques, gratuit, jamais un achat.

**Les rochers de mana sont des sources de couleur**, au même titre qu'un
terrain — un Cachet d'Azorius sert le blanc comme une Plaine — mais pas au même
moment : il faut d'abord les lancer, donc ils ne comptent qu'à partir du tour
suivant leur coût (`_sources_by_turn`). Un Anneau solaire, lui, ne produit que
de l'incolore : il ne compte pour aucune couleur, et c'est correct.

**Ce que l'estimation rapide ne peut pas voir.** Elle raisonne couleur par
couleur, donc une duale W/U compte pour une source blanche *et* une source
bleue — alors qu'elle n'en produit qu'une des deux à la fois. Sur un deck dont
88 % des sources blanches sont des duales W/U (cas réel : le Kykar), le blanc
paraît servi et ne l'est plus dès qu'il faut {W}{W} avec du bleu à côté. Seul
`can_pay` le voit, parce qu'il fait le couplage biparti.

D'où le garde-fou : `manabase(deep=True)` mesure le deck par simulation
(`simulation.color_stuck_rate`, ~100 ms), puis **resimule la répartition
conseillée** et ne la propose que si la mesure la confirme. Les deux variantes
partagent la graine, si bien que leur écart est bien plus précis que chacune
des mesures prise seule. Les pages qui conseillent (`/decks/[id]`,
`/suggestions`) activent `deep` ; `matchup` et `balance`, qui n'affichent que la
répartition des couleurs ou le nombre de terrains, s'en passent.

Validation : sur le Kykar d'origine, la répartition conseillée par le calcul
instantané tombe 4ᵉ sur les 153 possibles classées par simulation Monte-Carlo,
et la mesure confirme le gain (16,8 % → 12,9 % de sorts bloqués). Les deux
méthodes sont d'accord, et c'est la simulation qui tranche quand elles ne le
sont pas.

### Ce que la simulation mesure (et ce qu'elle ne mesure pas)

`services/simulation.py` joue N parties en solitaire : mulligan londonien, un
terrain par tour, rochers de mana lancés dès que possible, et relève le tour où
le commandant devient castable (couleurs comprises). Elle ne modélise **pas**
l'adversaire, la pioche conditionnelle ni les terrains engagés : c'est une
mesure de vitesse et de régularité de départ, pas une partie.

Limite connue : la décision de mulligan ne regarde que le nombre de terrains, si
bien que deux decks ayant le même nombre de terrains obtiennent exactement le
même taux de mains gardées. C'est correct mais peu discriminant.

## Arborescence — frontend (`magic_edh_frontend/magic_edh_frontend/`)

Next.js 16 (App Router, Turbopack), React 19, Tailwind 4, shadcn (base `radix`,
preset `nova`, comme sw-coaching).

```
app/
├── decks/page.tsx                   # liste
├── decks/import/page.tsx            # collage de decklist + choix du format
├── decks/[id]/page.tsx              # fiche : bracket, manabase, rôles, cartes
├── decks/[id]/simulation/page.tsx   # métriques + main de départ en images
├── decks/[id]/suggestions/page.tsx  # ajouts/retraits sous plafond de prix
├── collection/page.tsx              # saisie en masse + à l'unité, quantités
├── wishlist/page.tsx                # liste de recherche + « c'est acheté »
├── page.tsx                         # vue d'ensemble : couverture de la collection
├── must-have/page.tsx               # cartes les plus jouées par type, sous plafond
├── deck-ideas/page.tsx              # quel deck monter avec ce qu'on possède
├── deck-ideas/[id]/page.tsx         # decklist proposée + remplacement par la collection
├── deck-plans/page.tsx              # comparaison par commandant + 4 decks à monter + PDF
├── competitive/page.tsx             # deck compétitif bâti sur la collection
├── archetypes/page.tsx              # catalogue des archétypes du format
├── archetypes/[slug]/page.tsx       # l'article d'un archétype
├── regles/page.tsx                  # banlists, brackets, Game Changers
├── balance/page.tsx                 # équilibrage de 4 decks + liste d'achats PDF
├── matchup/page.tsx                 # comparaison de deux decks
├── performance/page.tsx             # qui gagne, et avec quel archétype
├── build/page.tsx                   # atelier : construire carte par carte
├── archives/page.tsx                # decks rangés, remise en service
├── terrains-budget/page.tsx         # manabase budget par cycle
└── login/page.tsx                   # seule page utilisable sans jeton
components/
    CardTile, CardBinder, CardSearch, CollectionFilters, CompetitiveDeck,
    DeckToolbar, DeckExport, ImportIssuesPanel, ManabaseAdvice, TopNav,
    ThemeProvider/Toggle, WishlistButton
    graphiques : ManaCurveChart, ColorDonut, AxisRings, InitiativeSplit, DuelOutcome
lib/api.ts                  # tous les appels au back + types
lib/auth.ts                 # jeton en localStorage (d'où les composants client)
lib/collection-filters.ts   # filtres de la page collection
lib/mtg-labels.ts           # libellés français des mots-clés Scryfall
lib/shopping-pdf.ts         # export PDF de la liste d'achats
lib/deck-pdf.ts             # export PDF d'une fiche : liste, visuels, tournoi
lib/decklist.ts             # découpage d'une decklist en sections de types
```

> Next.js 16 a des ruptures avec les versions antérieures (`params` est une
> Promise ; la règle de lint `react-hooks/set-state-in-effect` interdit un
> `setState` synchrone dans un effet — passer par `.then()`). Voir
> `node_modules/next/dist/docs/` avant d'utiliser une API App Router familière.
> La même famille de règles refuse aussi de réassigner une variable pendant le
> rendu : pas d'accumulateur muté dans un `.map()`.

## La navigation, rangée par question posée

Dix-sept liens alignés à plat tenaient sur **trois rangées** où rien ne se
distinguait : « Terrains budget » voisinait « Qui gagne » sans qu'on sache
lequel parlait de la collection et lequel d'un deck. `TopNav` les range en cinq
menus (`radix-ui` `DropdownMenu`), sur une seule rangée :

**Collection** (ce que je possède) · **Decks** (ce que je joue) · **Que monter**
(ce que je pourrais monter) · **Mesurer** (ce que ça vaut) · **Le format** (ce
qui s'impose à moi).

Deux détails qui ne sont pas cosmétiques :

- **chaque entrée porte une phrase courte.** La moitié de ces pages ont un nom
  qui ne dit pas ce qu'elles font — « Équilibrer », « Qui gagne », « Cartes à
  avoir » — et l'infobulle d'un lien ne se lit jamais ;
- **le lien courant est le plus long qui corresponde**, pas le premier trouvé.
  `/decks/import` commence par `/decks` : sans cette règle, importer une
  decklist surlignerait « Mes decks ». Une fiche de deck (`/decks/42`) retombe
  bien sur « Mes decks », et `/archetypes/tokens` sur « Archétypes ».

## Thème et graphiques

Le thème est piloté par `next-themes` en **mode classe** (`globals.css` déclare
`@custom-variant dark (&:is(.dark *))`). Conséquence pratique : forcer la classe
`dark` à la main dans le layout ne sert à rien, le provider la réécrit au
montage. Pour tester le sombre, émuler la préférence système
(`--blink-settings=preferredColorScheme=0` en Chrome headless).

Les palettes de graphiques sont **validées, pas choisies à l'œil** — via le
validateur de la compétence dataviz, contre les surfaces réelles (`--card` :
`#fdfcf8` en clair, `#1b1d22` en sombre). **Changer une surface impose de
revalider.** Deux jeux distincts, jamais mélangés :

- `--mana-w/u/b/r/g` : les couleurs de Magic, sémantiques donc non
  réattribuables. En sombre le bleu tire volontairement vers le cyan : le bleu
  franc et le violet étaient indiscernables (ΔE 9,8, sous le plancher). Il reste
  un écart rouge/vert faible sous protanopie, inhérent à la roue des couleurs :
  **toute forme qui les emploie doit porter la lettre de couleur**, jamais la
  teinte seule.
- `--series-a` / `--series-b` : les deux decks comparés. Réservées à ça.
- `--chart-seq` : teinte **séquentielle à une seule série**, pour une magnitude
  comparée entre catégories (la vue d'ensemble). `#a56300` en clair, `#c38323`
  en sombre — validés séparément contre `--card` dans chaque mode, et non
  éclaircis l'un depuis l'autre. L'accent `--primary` avait été essayé
  d'abord : il **échoue au plancher de chroma**, c'est-à-dire qu'en graphique
  il lit gris. Ne pas y revenir sans revalider.

Règle de fond pour les comparaisons : les axes ont des unités différentes (un
tour, un taux, un compte). Chaque ligne est normalisée **sur sa propre paire**
avec la valeur brute écrite à côté ; jamais d'échelle commune ni de radar.

Le **bracket n'est pas un axe du score** : compter « bracket plus haut = axe
gagné » offrirait un point gratuit au deck le plus puissant sur une page dont
le sujet est l'équilibrage, alors que cette puissance est déjà mesurée par les
autres axes. Il reste affiché par deck, et le verdict signale un écart de deux
niveaux ou plus.

Deux chiffres distincts cohabitent sur la page de comparaison, ne pas les
confondre ni fusionner leurs libellés :

- **Initiative** (`services/matchup.initiative`) : part des parties où un deck
  pose son commandant en premier. Mesure de vitesse pure, aucun combat.
- **Taux de victoire en duel simulé** (`services/duel.py`) : parties jouées
  coup par coup — terrains, mana et couleurs exacts, créatures avec leur vraie
  force/endurance, removal, board wipes, attaques, blocages, points de vie
  (40 en multi, 30 en Duel Commander), chaque deck commençant la moitié des
  parties.

La **zone de commandement est modélisée** : un commandant détruit y retourne et
se relance avec la taxe de 2 par relance. Ce n'était pas une simplification mais
une erreur de règle — le perdre définitivement sur un board wipe punissait deux
fois le même deck.

**Le combat est joué avec ses règles, pas en additionnant des forces.** Vol et
portée décident qui peut bloquer quoi, la menace exige deux bloqueurs,
l'initiative décide qui meurt avant d'avoir frappé, le contact mortel tue d'un
point, le piétinement laisse passer l'excédent, l'indestructible survit aux
dégâts comme aux board wipes. Les mots-clés viennent de `cards.keywords`
(Scryfall) : ils sont **constatés, pas devinés** depuis le texte oracle — d'où
l'ajout de cette colonne à `SIMULATION_CARD_COLUMNS`, sans laquelle le
simulateur joue des créatures nues et tout ce travail ne sert à rien.

La vigilance mérite une mention à part : **attaquer engage**. Avant, aucune
créature ne se tapait en attaquant, donc tout le monde jouait comme s'il avait
la vigilance et attaquer ne coûtait rien — le modèle surestimait l'agression de
façon structurelle.

Trois autres mécaniques comblent le biais dans sa direction connue :

- **Les dégâts de commandant** (21 d'un même commandant) sont une seconde
  horloge, et elle avantage les commandants gros et évasifs.
- **Les contresorts** sont gardés en réserve et partent sur une vraie menace
  (seuil de coût converti) : les dépenser sur un rocher de mana les rendrait à
  la fois omniprésents et inutiles.
- **Les combos gagnants à deux cartes** terminent la partie quand les deux
  pièces sont disponibles et le mana total payable. C'est **exactement le
  critère affiché sur la fiche de deck** — mêmes `wins_outright` et
  `total_mana_value` — donc le duel et le bracket racontent la même histoire.

**Ce qui reste hors de portée** : les capacités activées et déclenchées en
général. « Quand cette créature meurt, chaque joueur sacrifie un terrain » est
du texte libre, et l'exécuter demanderait un moteur de règles complet — pas une
heuristique de plus. Même chose pour les jetons, les moteurs de pioche
récurrents et la politique.

**Le biais résiduel garde une direction**, plus faible qu'avant : le modèle est
plus à l'aise avec les decks qui gagnent par le combat ou par un combo
identifié qu'avec ceux qui accumulent de petits avantages tour après tour.
L'encadré de l'interface n'est pas décoratif — sans lui, un 60/40 se lit comme
un pronostic.

Mesuré sur quatre decks réels, l'écart entre l'ancien modèle et celui-ci va
**jusqu'à 27 points de taux de victoire** sur un même affrontement. Autrement
dit : tout chiffre de duel relevé avant ce changement est à jeter.

## EDHREC et orchestration

`commander_recommendations` et `commander_brackets` contiennent les cartes
qu'EDHREC voit jouées avec chaque commandant, et à quel bracket il est monté.
Elles alimentent la page « Quel deck monter » (`/deck-ideas`), qui classe les
commandants possédés par part du noyau déjà couverte — le mieux couvert est le
moins cher à monter. Le noyau est réellement **non-terrain** : les terrains
non-basiques conseillés (duales, fetchlands) en sont exclus comme les basiques,
sans quoi les cartes les plus chères de la liste occuperaient des places du
noyau et fausseraient couverture comme budget.

**La source n'est pas une API officielle** : ce sont les endpoints JSON publics
que le site EDHREC consomme lui-même (`json.edhrec.com/pages/commanders/<slug>.json`).
Ils peuvent changer sans préavis, d'où des tables entièrement reconstructibles
et un module isolé (`services/edhrec.py`). Deux règles à respecter :

- **Ne jamais toucher `/deckpreview/`** : leur `robots.txt` l'interdit
  explicitement (decks individuels d'utilisateurs). Les pages commandants et
  *average-decks*, elles, sont sitemapées donc voulues.
- **Pause entre chaque requête** : c'est un site communautaire gratuit, et on
  ne récupère que les commandants réellement possédés (quelques dizaines).

Les cartes y sont identifiées par leur `scryfall_id`, pas par leur nom : la
jointure vers notre base est donc exacte, pas approximative.

**Le libellé exact des sections compte, et il a déjà piégé le projet.** EDHREC
écrit « Utility Artifacts » ; `WANTED_SECTIONS` demandait « Artifacts », qui ne
correspond à **aucune** section. La liste entière était donc jetée en silence —
sur les pages commandants comme sur les pages archétypes — et les viviers de
`/deck-ideas`, `/deck-plans` et `/competitive` n'ont jamais vu Skullclamp, les
bottes, ni les moteurs à artefacts ; seuls les rochers de mana passaient, par
« Mana Artifacts ». Rien n'échouait : le vivier était seulement plus pauvre
qu'il n'aurait dû. **La correction ne prend effet qu'après un
`python scripts/sync_edhrec.py`**, comme toute correction de ce script. Un test
fige le libellé.

« Lands » reste volontairement hors de `WANTED_SECTIONS` : le noyau du projet
est non-terrain partout, et faire entrer cinquante terrains par commandant
changerait le contenu de trois pages sans que personne ne l'ait demandé.

La même synchronisation est accessible de deux façons, avec **une seule
implémentation** dans `services/edhrec.py` :

- `python scripts/sync_edhrec.py` (ligne de commande, lancement manuel)
- `POST /admin/sync-edhrec` (authentifié), appelé par le flow Kestra
  `kestra/sync-edhrec.yml`

Kestra vit dans son propre LXC : l'appel HTTP lui évite de dupliquer le dépôt,
un venv et les identifiants Postgres. **L'ordonnanceur reste interchangeable** —
rien dans le code ne dépend de Kestra, et les scripts CLI font le même travail.

### Les six synchronisations, et pourquoi deux mécanismes

Les flows vivent dans `kestra/` (namespace `mtg-edh`, instance `lxc-kestra`,
192.168.1.119). **Il n'y a pas de timer systemd** : un seul ordonnanceur, sinon
le même travail finirait par être lancé deux fois.

| Flow | Syncs | Déclenchement | Planification |
|---|---|---|---|
| `sync-scryfall.yml` | `cards`, puis `card_names_fr` | SSH | 1er du mois, 2 h |
| `sync-edhrec.yml` | recommandations et archétypes par commandant | SSH | lundi 4 h |
| `sync-archetypes.yml` | catalogue des archétypes du format | SSH | 2 du mois, 3 h |
| `sync-combos.yml` | catalogue Spellbook | HTTP | lundi 5 h |
| `sync-mtgtop8.yml` | tops des tournois de Duel Commander | SSH | mardi 4 h |

**Le choix HTTP / SSH suit la durée, pas la préférence**, et ce n'est pas un
choix figé : EDHREC est passé de HTTP à SSH le jour où la collection a franchi
la centaine de commandants. Un endpoint synchrone ne renvoie rien avant la fin,
donc Kestra compte toute la durée comme de l'inactivité et coupe à
`readIdleTimeout`. Au-delà de quelques minutes, le HTTP n'est plus tenable.

**Le coût d'EDHREC croît avec la collection** : une requête par commandant
**et par archétype**, pause d'une seconde entre chaque. À 36 commandants, une
minute ; à 131, seize. Le seuil sera franchi de nouveau — et à terme c'est la
stratégie qu'il faudra revoir, pas le transport : le flow refetche chaque
semaine des centaines de pages qui n'ont pas bougé.

**Kestra n'a pas de shell sur le back.** Sa clé publique est posée dans
`authorized_keys` avec `command="…/deploy/kestra-sync.sh"`, qui force ce script
quelle que soit la commande demandée ; celle-ci n'arrive que dans
`$SSH_ORIGINAL_COMMAND` et sert d'aiguillage. Seuls `scryfall`, `french-names`,
`edhrec`, `archetypes`, `mtgtop8` et `rank-commanders` sont acceptés, tout le
reste sort en code 2. Ajouter une
synchronisation par SSH, c'est donc **ajouter un `case` dans ce script**, pas
seulement une tâche dans le flow.

Deux contraintes d'infrastructure à ne pas redécouvrir :

- **Le SSH du back est sur le port 52398**, pas 22, et l'hôte comme le port
  vivent dans le KV Store du namespace — le dépôt part sur GitHub.
- **L'UI de Kestra doit être ouverte par le LAN** (`http://192.168.1.119:8080`)
  pour suivre une longue exécution. Par le domaine public, Cloudflare coupe le
  flux de logs à 100 s et le front annonce l'instance injoignable alors qu'elle
  travaille. C'est le même plafond qui interdit d'appeler `/admin/sync-edhrec`
  par le domaine.

## Authentification

Application **personnelle** : un seul compte, **pas d'inscription et pas de
table utilisateurs**. Les identifiants viennent de l'environnement
(`AUTH_USERNAME`, `AUTH_PASSWORD_HASH` bcrypt, `JWT_SECRET`), générés par
`python scripts/hash_password.py` — le mot de passe en clair n'existe nulle
part. Sans `AUTH_PASSWORD_HASH` ou `JWT_SECRET`, la connexion échoue en 500
explicite plutôt que d'ouvrir l'accès.

Tous les routers sont protégés par `Depends(require_auth)` sauf `/health`
(sonde) et `/auth/login`. `/card-images` reste public : ce sont des visuels
Scryfall déjà publics à la source, et les servir ne fait pas grossir le disque —
ce qui était la motivation de l'authentification.

**Conséquence côté front : les pages qui chargent des données doivent être des
composants client.** Le jeton vit dans le `localStorage` du navigateur, donc un
composant serveur se ferait renvoyer un 401. `/decks` et `/decks/[id]` ont été
convertis pour cette raison — ne pas les repasser en rendu serveur.

Corollaire qui se paie cher : **`router.refresh()` ne recharge rien ici.** Il
re-rend les composants serveur et préserve l'état client, donc l'effet qui a
fait le `fetch` ne se rejoue pas et l'écran garde les anciennes données. Après
une mutation, la page passe son propre rechargement aux composants enfants
(`DeckToolbar`, `ImportIssuesPanel` : prop `onChanged` / `onResolved`).

## Noms français

Julien joue en français : **les decklists collées peuvent être en français, et
les noms s'affichent en français** partout où la traduction existe (fiches,
recherche, suggestions, liste d'achats PDF). Les **visuels de cartes restent
anglais** : ce sont les impressions stockées.

`card_names_fr` est une simple table d'alias `(oracle_id, printed_name)`
alimentée par `scripts/sync_french_names.py`. Elle vient du bulk data
`all_cards` (~400 Mo, le seul avec les autres langues) contre `default_cards`
(~78 Mo) pour le reste — d'où un script séparé, à relancer après chaque set.
Importer les cartes françaises entières dupliquerait prix, légalité et rôles
pour rien : seul le nom change, l'`oracle_id` est commun.

La résolution essaie l'anglais d'abord (canonique, et un nom français pourrait
coïncider avec le nom anglais d'une autre carte), puis le français, puis le flou
sur les deux langues à la fois, enfin la **face avant** d'une carte à deux noms
dans les deux langues. **Couverture : ~90 %** — les vieux sets, Secret Lairs et
certains produits Commander n'ont jamais été traduits, l'absence d'alias est
normale et il faut alors le nom anglais.

### Les cartes à deux noms (partagées, recto-verso, aventures)

Scryfall ne met `printed_name` au premier niveau que pour les cartes à **une**
face : une partagée, une recto-verso, une aventure ou une flip le range dans
`card_faces`. Le sync ne lisait que le premier niveau, si bien qu'**une carte à
deux noms sur 878 avait un nom français**, contre 90 % des cartes simples.
C'est l'erreur silencieuse type : rien ne remonte, ces cartes ont juste l'air de
ne pas être traduites. Conséquences concrètes : « Feu // Glace » s'affichait en
anglais partout, fiches et PDF compris, et une decklist française la laissait
non résolue.

`printed_name_for()` recolle donc les faces avec ` // `, **exactement la
convention du champ `name` anglais** : c'est ce qui permet de comparer alias et
nom de la même façon dans les deux langues. Une seule face traduite ne donne
rien — un nom à moitié français ne correspondrait ni à la carte imprimée ni à
ce qu'un joueur écrit, et l'absence d'alias retombe proprement sur l'anglais.
La colonne ne se remplit qu'à la resynchronisation
(`python scripts/sync_french_names.py`), comme toute correction de ce script.
Mesuré après coup : 697 cartes à deux noms sur 878 ont un nom français, le
reste n'a jamais été traduit.

**La résolution accepte la face avant seule** : une decklist écrit « Bloodline
Keeper », jamais « Bloodline Keeper // Lord of Lineage », et magic-ville
n'imprime que le recto sur la vignette. Deux garde-fous, tous deux vérifiés par
un test :

- ce passage vient **en dernier**, donc un nom qui désigne une vraie carte
  gagne toujours — Smelt, Armed et Bind existent à la fois seuls et en face
  avant d'une carte partagée ;
- il ne regarde **que la face avant**. Résoudre « Lord of Lineage » ou une
  moitié aventure ferait passer une planche de proxys magic-ville à 101 cartes
  en silence, alors qu'aujourd'hui ces vignettes sont signalées — c'est le
  comportement décrit au chapitre magic-ville, et il ne change pas.

À l'impression, un nom à deux faces déborde souvent de sa colonne.
`fitCardName` (`lib/deck-pdf.ts`) **retire le verso avant de tronquer** :
« Jace, prodige de Vryn » identifie la carte, « Jace, prodige de Vryn // Jace,
télép… » n'apprend rien de plus.

Côté affichage, `displayName(card)` (front) et `deck_analysis.display_name()`
(back) appliquent la même règle : français si disponible, anglais sinon. **Le
repli anglais n'est pas un cas d'erreur**, c'est la norme pour ces 12 % — toute
jointure sur `card_names_fr` doit rester externe, sinon ces cartes
disparaîtraient purement et simplement des fiches.

## Vocabulaire à l'écran

Le projet parle à un joueur francophone, pas à un deckbuilder anglophone. Le
terme anglais `pips` reste un nom de champ côté API mais **ne doit jamais
apparaître à l'écran** : on affiche « symboles de mana », avec l'explication
({"{1}{B}{B}"} demande deux symboles noirs). Même vigilance pour tout autre
jargon importé.

## Conventions

- Le plafond de prix (50 € par défaut) ne concerne **que les cartes à acheter**.
  Rien ne reproche au deck de contenir des cartes chères déjà possédées.
- Les decks sont indépendants : pas de collection partagée entre eux.
- Les seuils de construction (`ROLE_TARGETS`, nombre de terrains) sont des
  repères communément admis, pas des vérités — ils servent à signaler un écart
  franc. Quand un conseil paraît faux, c'est le seuil qu'il faut discuter.
- **Les tests visent les erreurs silencieuses**, pas la couverture : parsing et
  résolution de noms, calcul de mana, classification, reproductibilité de la
  simulation, planchers de bracket, listes d'achats, et le passage
  transactionnel de la liste de recherche à la collection. Le critère est
  toujours le même — une erreur qui ne lève aucune alerte et se paie en argent
  ou en conseil faux mérite un test ; une fonction évidente, non.
- Les tests qui écrivent en base **se sautent proprement** quand Postgres est
  injoignable (`pytestmark = skipif`), pour que la suite reste lançable
  n'importe où.

## Les règles du format (`/regles`)

Ce qu'on subit plutôt que ce qu'on choisit : les deux banlists, le système de
brackets, la liste officielle des Game Changers. Trois listes, **aucune table
et aucun flow Kestra propres à cette page** — ce sont des colonnes de `cards`,
donc le flow mensuel `sync-scryfall` les rafraîchit déjà. En ajouter un
referait le même travail deux fois, ce que le projet refuse par principe (un
seul ordonnanceur par travail). C'est le même raisonnement que `/must-have`,
qui vit d'`edhrec_rank`.

### « Bannie » n'est pas « pas légale », et l'écart est d'un facteur quarante

`legal_commander` est un booléen : il confond une carte **interdite** et une
carte qui n'a jamais été jouable en tournoi. Mesuré : **2 327 cartes** sont
`NOT legal_commander` — Un-sets, cartes playtest, 30th Anniversary, jetons de
Conspiracy — quand la banlist du multijoueur en compte cinquante-huit. La
requête évidente aurait donc rendu quarante fois trop de lignes, et surtout les
mauvaises.

Scryfall publie la valeur exacte (`legalities.commander` vaut `banned` et non
`not_legal`), et le sync la jetait — **exactement l'information perdue que
`restricted` avant la migration 015**. D'où `banned_commander` et `banned_duel`
(migration 021).

### Les deux familles de bannis qu'il faut séparer

Même avec la bonne colonne, Scryfall annonce 83 cartes en multijoueur et 250 en
duel là où un joueur en attend une cinquantaine. Le reste est banni **parce que
ce ne sont pas des cartes de partie**, et cela se reconnaît de deux façons :

- par le **type** : Conspiracies (25, jouées depuis l'extérieur du deck en
  draft) et Stickers d'Unfinity (48) ;
- par l'**édition** : Unfinity, éditions anniversaire, decks de championnat du
  monde — `funny` et `memorabilia`, 79 cartes rien que pour Unfinity en duel.
  D'où la colonne `set_type`.

**Le critère d'édition se juge sur toutes les impressions, jamais sur celle que
`cards_cheapest` retient**, et c'est la subtilité qui décide de tout :
l'impression la moins chère de Black Lotus est un proxy « 30th Anniversary »
(memorabilia). Juger sur elle retirerait de la banlist Black Lotus, les cinq
Moxen, Ancestral Recall et Chaos Orb — les cartes les plus célèbres du jeu. Une
carte n'est donc écartée que si **aucune** de ses impressions n'appartient à
une vraie édition. Un test le fige.

Ces cartes sont **montrées à part, pas masquées** : les cacher ferait mentir le
total, les mélanger rendrait la liste illisible. Résultat affiché : 58 bannies
en multijoueur (+25 hors tournoi), 99 en duel (+151).

Deux rappels que la page porte à l'écran, parce qu'ils se paient en partie :

- **les deux banlists ne se déduisent pas l'une de l'autre.** Le duel est plus
  strict dans l'ensemble, mais **dix-neuf cartes** sont bannies en multijoueur
  et légales en duel — Dockside Extortionist, Griselbrand, Leovold. Chaque
  carte porte donc les deux drapeaux, et l'écran marque celles dont le statut
  change ;
- **« interdite comme commandant » n'est pas « bannie »** : les 27 cartes
  `restricted` du duel restent jouables dans les 99. Section séparée, et vide
  côté multijoueur puisque le format n'a pas d'équivalent.

### Les brackets : la règle d'un côté, ce que le site en constate de l'autre

Le texte du Commander Format Panel est recopié à la main
(`services/bracket_rules.py`) — c'est du texte, aucune source ne le publie en
machine, même situation que les notes d'archétypes.

Mais **le lien entre la règle et le code n'est pas recopié : il est exécuté.**
Chaque critère porte un deck minimal de démonstration qu'on passe au vrai
`deck_analysis.bracket_estimate`, et c'est sa réponse qui s'affiche — « un deck
avec 4 Game Changers → Bracket 4-5 ». Écrire ce seuil dans une phrase l'aurait
laissé dériver le jour où il change ; ici la page suit le code, et un test
fige la correspondance.

La page nomme aussi **ce qui n'est pas mesuré** : le stax (pas un critère
officiel), la densité de tuteurs (le texte en parle sans fixer de seuil), le
« plan de fin de partie » et l'enchaînement des tours supplémentaires (une
liste de cartes ne le dit pas). Les taire ferait passer ces choix pour des
oublis.

**Pas d'`ensure_images`** : plus de quatre cents visuels au premier affichage,
même arbitrage que `/must-have`. Le tri se fait sur le **nom affiché** et non
sur le nom anglais renvoyé par le serveur, sans quoi une liste écrite en
français serait classée dans un ordre qui n'en est pas un.

## Combos à deux cartes et bracket

Le bracket a quatre critères qu'on sait constater :

- le nombre de **Game Changers** (colonne `game_changer`, liste officielle) ;
- la présence d'un **combo infini à deux cartes qui gagne la partie**,
  officiellement interdit aux brackets 1-2 ;
- la **destruction de terrains de masse**, interdite aux brackets 1, 2 **et 3**
  — c'est le critère le plus punitif du système : un seul Armageddon fait d'un
  deck sans aucun Game Changer un bracket 4 ;
- les **tours supplémentaires**, que le bracket 1 interdit purement et
  simplement.

Le combo ne se lit pas dans le texte d'une carte — il naît de l'interaction
entre deux cartes — donc il se constate contre un catalogue plutôt qu'il ne se
devine : `combos` (table reconstructible) est importée de **Commander
Spellbook** par `services/spellbook.py`, avec la même organisation qu'EDHREC
(CLI `scripts/sync_combos.py`, `POST /admin/sync-combos`, flow Kestra). Leur
API limite le débit : le sync encaisse les 429 et n'écrit qu'à la fin, pour ne
jamais laisser un catalogue à moitié importé.

Deux points qui ne sont pas intuitifs :

- **Tous les combos ne pèsent pas.** Seuls ceux qui gagnent la partie sur place
  comptent pour le plancher (`wins_outright`, calculé au sync depuis les effets
  déclarés) : mana infini, pioche infinie ou ETB infinis demandent une
  troisième carte, ils sont affichés mais ne changent pas le bracket. Une
  exception assumée : le catalogue sous-déclare les combos à jetons avec la
  célérité (Kiki-Jiki + Conscrits zélés ne déclare aucune ligne de dégâts), or
  une infinité d'attaquants finit la partie sur place.
- **Ce qui reste au joueur.** Au-dessus du bracket 3, le texte officiel demande
  qu'un combo à deux cartes soit un plan de *fin de partie*, sans définir le
  terme. On renvoie donc le mana total (les deux cartes + l'exécution) à
  comparer au ramp du deck, sans trancher à sa place.

**Le stax n'est pas un critère officiel**, malgré la tentation : Winter Orb
gêne autant qu'un Armageddon, mais le système ne le nomme nulle part. Le faire
peser inventerait une règle et ferait dériver tous les brackets. Il reste
affiché en signal brut, avec la densité de tuteurs — dont le texte officiel
parle sans fixer de seuil, donc sans qu'on puisse en tirer un plancher.

Deux finesses de la classification (`card_categories.MASS_LAND_DENIAL`), toutes
deux issues de cartes réelles qui piégeaient la règle naïve :

- **« Détruire tous les terrains » se distingue de « épargner les terrains ».**
  Elspeth Tirel détruit « all other permanents *except for* lands », Scourglass
  « all permanents except for artifacts and lands », Street Sweeper les auras
  *attachées à* un terrain. Les clauses qui épargnent sont donc **retirées du
  texte avant** la recherche, et non traitées en exclusion après coup : sans
  quoi Keldon Firebombers (« sacrifie tous ses terrains *sauf trois* ») tomberait
  avec elles alors qu'il détruit bel et bien.
- **Un terrain chacun n'est pas une destruction de masse.** Tremble prive d'une
  pose, pas d'une manabase — d'où l'exigence du pluriel, avec une exception
  pour le singulier répété (Thoughts of Ruin : un terrain par carte en main).

Les tours supplémentaires, eux, ne ferment **que** le bracket 1 : les brackets
2 et 3 n'interdisent que de les *enchaîner*, ce qu'une liste de cartes ne
permet pas de constater. On plafonne donc au bracket 2 sans prétendre
distinguer un Time Warp isolé d'un moteur de tours, et l'interface le dit.

## Importer un deck depuis un PDF magic-ville

`scripts/decklist_from_pdf.py` convertit une planche de proxys en decklist. Le
site n'exporte pas de liste : le découpage se fait aux **coordonnées**, pas sur
le texte brut, que `pdftotext` livre en mélangeant les colonnes.

La règle qui porte tout : sur une rangée, **les vrais titres partagent la même
ligne de base**, celle où le plus de colonnes commencent un nom. Ce qui déborde
d'une vignette voisine se pose deux points à côté et tombe donc de lui-même —
c'est plus fiable que de reconnaître le texte parasite à sa forme.

Le module (`services/magic_ville_pdf.py`) sait recoller un titre sur trois
lignes, un nom coupé en deux fragments, une césure (« brise- miroir ») et les
ligatures typographiques — mais pas `æ`, qui est une lettre, présente dans de
vrais noms de cartes.

**Ce qu'il ne peut pas faire, par construction** : reconnaître une face arrière.
Magic-ville imprime le verso d'un recto-verso et la moitié aventure d'une carte
comme des proxys à part entière, géométriquement identiques à une vraie carte.
Elles se trahissent autrement — pas de nom français, donc « non résolu », et un
total qui dépasse 100. Le script les signale, il ne les corrige pas : lire le
rapport avant de coller la liste. Sur les cinq planches de référence, deux
passent sans retouche, les trois autres demandent entre une et cinq
corrections, toutes nommées dans le rapport.

## Construire un deck compétitif (`/competitive`)

Cinq étapes : **le format d'abord**, puis l'archétype *si on le connaît déjà*
(facultatif), un commandant de la collection, l'archétype à nouveau si on ne
l'a pas choisi, le deck.

L'ordre n'est pas cosmétique : **la liste des commandants dépend du format, dans
les deux sens**. Edgar Markov est légal en multi et banni en duel ; Rofellos,
Iona, Leovold, Erayo et Griselbrand sont bannis en multi et légaux en duel.
Demander le format en deuxième laissait choisir un commandant injouable, et
l'interdiction n'apparaissait qu'à la construction, après l'archétype.

**« Banni comme commandant » n'est pas « banni ».** Le duel interdit 27 cartes
au seul titre de commandant — Geist of Saint Traft, Yuriko, Edgar Markov — qui
restent parfaitement jouables dans les 99. Scryfall publie cette nuance sous la
valeur `restricted` du format duel ; `cards.banned_as_commander_duel` la
retient, et `legal_duel` reste vrai pour ces cartes. Le multijoueur n'a pas
d'équivalent (`restricted:commander` ne renvoie aucune carte), d'où une clause
vide de ce côté plutôt qu'une colonne toujours fausse.

Le piège est que le sync testait `legalities.duel == "legal"` : `restricted`
tombait donc à `false` et ces 27 cartes étaient traitées comme bannies tout
court. L'information arrivait à chaque synchronisation et était jetée.
**Éligibilité et légalité sont désormais deux questions distinctes**, vérifiées
aux deux endroits — la liste des commandants et la construction — pour qu'une
URL fabriquée à la main ne contourne pas le filtre.
C'est la seule page qui ignore les decks existants et regarde **toute la
collection** — en compétition, un seul deck part avec le joueur, la règle « un
exemplaire dans un seul deck » ne s'applique donc pas.

Ce qui rend la construction mesurable plutôt qu'inventée : EDHREC classe les
decks d'un commandant par archétype (Atraxa : infect, superfriends,
proliferate...) et publie pour chacun le profil des decks réels — camembert par
type et histogramme de courbe de mana. Ce sont eux les cibles, thème par thème,
et le classement des cartes est le taux d'inclusion mesuré sur ces decks-là
(`commander_themes`, `theme_recommendations`, migration 012).

**Trois filtres durs, appliqués en SQL avant tout le reste** : la banlist du
format, l'identité de couleur, les terrains de base. `legal_duel` est toujours
**pas** un sur-ensemble de `legal_commander` : le Duel Commander a sa propre
banlist, majoritairement plus stricte, mais **dix-neuf cartes sont bannies en
multijoueur et légales en duel** — Sylvan Primordial, Primeval Titan, Sundering
Titan, et cinq créatures légendaires dont Griselbrand et Leovold. Chaque écran
choisit donc la colonne de son format et n'en déduit jamais l'autre. La
légalité du commandant est vérifiée avant de construire 99 cartes autour de
lui.

**Les commandants de duel seulement sont bien vus.** `owned_commanders(format)`
choisit la colonne de légalité du format, et le sync EDHREC prend les
commandants légaux dans **l'un ou l'autre** format : Rofellos, Iona, Leovold,
Erayo et Griselbrand apparaissent en duel et ont leurs recommandations.

Deux choix qui ne sont pas des détails :

- **Le deck est bâti avec la collection seule.** Les cartes non possédées
  n'entrent jamais dans la liste : un deck qu'on ne peut pas jouer ce soir n'est
  pas un deck. Les achats sous plafond sont proposés à côté, chacun **face à la
  carte qu'il évincerait** — une carte distincte par achat, sinon trois achats
  qui remplacent la même carte feraient croire à trois gains.
- **« Le plus compétitif possible » n'est pas une grandeur.** Ce qui est
  calculable, c'est « le plus proche possible des decks qui jouent cette
  stratégie, avec ce que tu as ». L'écart restant est affiché : courbe obtenue
  contre courbe visée, quotas par type tenus ou non.

Le remplissage relâche ses contraintes dans un ordre fixe — d'abord la courbe,
puis les quotas de type — parce qu'un deck de 99 cartes vaut mieux qu'un deck
de 84 parfaitement galbé.

### Partir d'une stratégie plutôt que d'un commandant

On arrive sur cette page de deux façons : avec un commandant en tête, ou avec
une envie de stratégie (« je veux monter du superfriends »). D'où une étape 2
**facultative et explicitement sautable** — elle ne se charge même pas tant
qu'on ne la demande pas, ce qui évite de payer sa requête à chaque visite.

Les deux chemins lisent **la même mesure**, `themes_db.theme_scores` : une
ligne par couple (commandant, archétype), avec le poids de consensus des 63
meilleures cartes possédées. Seule change la colonne qu'on lit — le meilleur de
chaque commandant, ou celui de l'archétype demandé. C'est ce qui garantit
qu'aucun des deux classements ne peut dériver de l'autre ; les trier chacun de
son côté aurait fini par donner deux vérités.

Trois règles, et la deuxième est celle qui se paierait en silence :

- **La liste des archétypes est bornée aux commandants possédés.** Elle dit
  « ce que je peux monter », pas « ce qui existe en Commander » : proposer un
  archétype qu'aucun commandant de la collection ne joue mènerait droit à un
  écran vide. L'agrégat « toutes stratégies » en est exclu — ce n'est pas une
  stratégie, et le prendre comme filtre reviendrait à ne rien filtrer.
- **Demander un archétype bascule le classement dessus**, et écarte les
  commandants qui ne le jouent pas. Garder l'ancien tri — chacun sur *son*
  meilleur — aurait affiché un ordre qui ne répond pas à la question posée sans
  que rien ne le signale : sur la collection, le commandant qui domine le
  classement général n'est presque jamais le meilleur d'un archétype donné.
  C'est l'erreur silencieuse que fige `tests/test_competitive_archetypes.py`,
  lequel n'a pas besoin de base — le croisement est fait en Python, à partir de
  deux lectures que le routeur ne fait qu'une fois.
- **Le meilleur archétype du commandant reste affiché** quand il diffère de
  celui qu'on a demandé (« monte mieux Infect »). C'est une information, pas une
  correction : la stratégie choisie reste celle qui construit.

Une fois le commandant choisi, le deck est construit **directement** avec
l'archétype de l'étape 2 — le redemander n'apprendrait rien. La liste des
archétypes du commandant reste affichée dessous pour en changer, et elle montre
alors ce que ce commandant-là sait faire d'autre.

## Le méta du Duel Commander (MTGTop8)

**EDHREC ne distingue pas les formats**, et c'était un défaut silencieux du duel :
le deck compétitif, les cartes à avoir et les suggestions d'un deck de duel
étaient tirés de listes **multijoueur**, simplement filtrées par la banlist du
duel. Rien n'échouait — les conseils répondaient juste à un autre format :
ramp lente, effets symétriques et pioche de groupe surévalués, interaction bon
marché et tempo sous-évalués. Sol Ring en tête des « cartes à avoir » d'un
format qui le bannit, écarté trop tard pour que l'ordre du reste ait un sens.

MTGTop8 publie les tops des tournois de Duel Commander (format **`EDH`** chez
eux ; leur `cEDH` est le multi compétitif). Mesuré en septembre 2026 : ~1 000
tournois sur six mois, ~4,5 decks par tournoi, soit **~4 500 listes**.
`services/mtgtop8.py` les relève, `db/duel_meta.py` les sert.

**Le duel seulement.** Le multijoueur ne lit jamais ces tables ; en duel, tout
retombe sur EDHREC tant que le méta n'est pas synchronisé (ou la migration pas
jouée : `available()` le détecte), et l'écran le dit.

### Ce n'est pas une API

Ce sont les pages HTML du site, lues aux motifs qui les structurent, et
l'export texte d'un deck (`mtgo?d=`). Pas de `robots.txt` (404) : rien
d'interdit, rien de prévu non plus. Mêmes règles qu'EDHREC — pause d'une
seconde, module isolé, tables reconstructibles — et des **parseurs purs testés
sur des extraits réels** (`tests/test_mtgtop8.py`), pour qu'un changement de
mise en page casse un test plutôt que de vider le méta au fil des purges. Une
première page de liste illisible lève une erreur franche pour la même raison.

Trois pièges constatés en écrivant le parseur :

- **La liste ne se pagine qu'avec un « méta »** (`LIST_META_ID = 209`, « Last 6
  Months ») : sans lui, le site s'arrête à la troisième page, soit trois
  semaines. La synchro aurait tourné sans erreur sur un méta amputé de 90 %.
- **Chaque page de liste répète le tableau des « grands événements »** avant
  la liste paginée. Le lire ferait croire que chaque page commence au 20
  septembre, et l'arrêt sur la fin de la fenêtre ne se produirait jamais.
- **Le commandant est rangé sous « Sideboard »** dans l'export, seul (deux
  lignes pour des partenaires). C'est ce qui permet de l'identifier sans rien
  deviner. Les cartes partagées y sont écrites « Fire/Ice », converties en
  « Fire // Ice » pour la résolution.

### Incrémental, contrairement à EDHREC

Un tournoi publié ne change plus : seuls les événements **inconnus** sont
demandés, et un événement n'est enregistré qu'avec ses decks, dans une seule
transaction — sans quoi un échec entre les deux le perdrait pour toujours. La
liste est relue jusqu'au bout de la fenêtre à chaque fois (une cinquantaine de
pages) plutôt que de s'arrêter au premier connu : une exécution plafonnée
laisse des trous plus anciens, qu'il faut retrouver la fois suivante.

**Le coût est d'environ 7 s par tournoi** (une page, un export par deck, une
seconde de pause avant chacun) — mesuré, pas estimé. Une semaine ordinaire
tient en sept ou huit minutes, relecture de la liste comprise ; le rattrapage
initial, un millier de tournois, en demande **environ deux heures**, d'où le
plafond de 300 événements par
exécution (`DEFAULT_MAX_EVENTS`) : le flow hebdomadaire rattrape en quatre
semaines, ou un `--max-events 0` lancé à la main le fait d'un coup.

La **fenêtre est glissante** (180 jours, `WINDOW_DAYS`) : les cartes bannies
ou passées de mode sortent d'elles-mêmes, sans liste à tenir.

### La mesure : un dénominateur par carte

`duel_card_stats` (recalculée à chaque synchro, en Python — `compute_card_stats`
se teste sans base) porte deux taux, et les confondre fausserait tout :

- **`rate`** : decks qui jouent la carte / decks **qui pouvaient la jouer**
  (identité du deck ⊇ identité de la carte). Un Contresort joué par tous les
  decks bleus vaut 100 %, pas 40 % : rapporté à tous les decks, il passerait
  pour une carte de niche, et les incolores seraient avantagées d'office.
  Sous 20 decks éligibles (`MIN_ELIGIBLE_DECKS`), le taux compte comme non
  mesuré — une carte cinq couleurs vue dans un des deux decks cinq couleurs
  afficherait 50 %.
- **`share`** : part de **tous** les decks. C'est la popularité brute, celle
  qui classe les cartes à avoir, toutes couleurs confondues.

**Une table et non une vue matérialisée**, exprès : elle dépendrait de
`cards_cheapest`, que `rebuild_cheapest_view.sql` supprime (`DROP MATERIALIZED
VIEW`) — elle disparaîtrait en silence au prochain ajout de colonne sur `cards`.

**Les terrains de base ne sont pas dans `duel_deck_cards`** (ils ne se
choisissent pas) mais **comptent dans le profil** de chaque deck
(`type_counts`, `mana_curve`, calculés à l'import avec les règles de
`competitive.type_of`). Sans eux, un deck à 38 terrains en afficherait 14, et
le constructeur viserait une manabase absurde. Un test le fige.

### Ce que ça change à l'écran

**`/competitive` en duel** gagne deux références, **en tête** de la liste des
thèmes, avec la même forme que les thèmes EDHREC (le constructeur n'a rien à
convertir) :

- **« Ses listes de tournoi »** (`_duel_top8`), quand le commandant a au moins
  8 tops (`MIN_COMMANDER_DECKS`) : taux et profil mesurés sur ses propres
  listes, bornés à son identité — une liste Kraum + Yoshimaru joue du blanc
  que Kraum seul ne peut pas jouer. C'est la meilleure cible possible.
- **« Méta du duel dans ses couleurs »** (`_duel_meta`), toujours là : ce qui
  gagne en face à face dans ses couleurs, départagé par l'inclusion EDHREC
  derrière ce commandant. **Il ne connaît pas le plan du commandant**, et
  l'écran le dit. Son profil vient des decks de la même identité, ou du
  format entier sous 20 decks (`profile_scope`).

Les archétypes EDHREC restent proposés dessous, badgés « EDHREC · multi » : ce
sont les seuls à nommer des **stratégies** (l'étape 2 en dépend). Mais
**`competitive._best` fait passer les références de duel devant**, et ce n'est
pas une préférence : les deux échelles ne se comparent pas. Un taux EDHREC se
mesure sur les decks d'un seul commandant, celui du méta sur tous les decks
d'une couleur — mécaniquement plus bas. Comparer les poids ferait toujours
gagner EDHREC, donc toujours conseiller en duel ce qui se joue en multi. Pour
la même raison, l'indice « monte mieux X » ne compare que deux thèmes de même
source. Un test fige la règle.

Les **synergies** d'un deck bâti sur une référence de duel restent celles
d'EDHREC, tous decks du commandant confondus : c'est la seule source qui les
mesure, et l'encadré ne prétend plus qu'elles portent sur l'archétype.

**`/must-have` en duel** est classé par `share` (« 52 % des tops ») au lieu
d'`edhrec_rank`. Même réponse, mêmes huit types : seule la mesure qui ordonne
change. Sur le premier échantillon : Solitude, Swords to Plowshares, Lightning
Bolt, Mental Misstep, Skullclamp — là où EDHREC mettait Sol Ring en tête.

**Les suggestions et l'équilibrage d'un deck de duel** passent par
`find_candidates`, le point d'entrée unique : le plancher de qualité
« rang EDHREC ≤ 2000 » y devient « vue dans au moins 5 tops **et** 2 % des
decks éligibles » (`MIN_DUEL_DECKS`, `MIN_DUEL_RATE`). Deux conditions parce
qu'aucune ne suffit : un compte absolu devient laxiste quand le méta grossit,
un taux seul se laisse berner par un petit dénominateur.

**Ce qui ne change pas** : `/deck-ideas`, `/deck-plans` et `/build` restent sur
EDHREC. Ils montent des decks pour jouer entre amis, sans choix de format de
tournoi ; les brancher sur le duel serait une autre question.

## Le catalogue des archétypes (`/archetypes`)

**La seule page du projet qui parle de ce qu'on ne possède pas.** Toutes les
autres partent de la collection : quel deck monter avec elle, comment
l'équilibrer, que lui acheter. Celle-ci part du format — « qu'est-ce que le
superfriends, qui le pilote, et qu'est-ce que ça me coûterait » — parce qu'une
page de découverte bornée à la collection ne ferait rien découvrir.

La source est la **deuxième famille d'endpoints EDHREC** : `/pages/tags/themes.json`
recense les archétypes, `/pages/tags/<slug>.json` donne pour chacun ses
commandants et ses cartes. Elle est sitemapée (`/sitemaps/tags.xml`) donc
voulue, au même titre que les pages commandants. Trois tables reconstructibles
(migration 020) : `archetypes`, `archetype_cards`, `archetype_commanders`.

**Deux entrées peuvent viser la même carte.** EDHREC référence ses
commandants par impression (`scryfall_id`) : deux d'entre elles peuvent
retomber sur le même `oracle_id`. Un `ON CONFLICT DO UPDATE` touchait alors
deux fois la même ligne dans une seule commande, Postgres refusait
(`CardinalityViolation`) et **toute la synchronisation s'arrêtait** — pas
seulement l'archétype fautif. Constaté au vingtième archétype du catalogue
réel, donc invisible sur un essai à cinq. Le `DISTINCT ON` garde l'impression
la plus jouée ; un test le fige.

**Le slug est dans l'`url`, jamais dans le champ `slug`** — celui-ci porte la
carte qui illustre la vignette (« skullclamp » pour Tokens). Se tromper de
champ demande une page qui n'existe pas, et le bucket S3 d'EDHREC répond alors
**403 et non 404**, faute de droit de listage : l'erreur ne se lit même pas
comme une page absente. Un test fige la règle.

**Plancher à 500 decks** (`MIN_ARCHETYPE_DECKS`) : 183 archétypes retenus sur
les 270 recensés — mesuré : **4 min 37 s**, 56 964 cartes, 4 324 commandants,
ce qui range d'office cette synchronisation du côté SSH. La queue, ce sont « planechase » ou « dandan » à cinq decks,
dont le taux d'inclusion serait calculé sur une poignée de listes. Le plancher
est plus haut que celui des thèmes par commandant (50) parce que l'assiette
n'est pas la même — le format entier contre les decks d'un seul commandant.

### Ce qui est écrit à la main, et pourquoi c'est assumé

**EDHREC ne publie aucune description.** Le champ existe dans leur JSON, il est
vide — sur les pages archétypes comme sur les pages commandants. « Ce que fait
un deck aristocrats » n'est ni un compte ni un taux : rien dans le projet ne
peut le calculer, et le faire produire par un modèle de langage reviendrait à
inventer ce qu'on refuse d'inventer partout ailleurs (c'est l'argument du stax
dans le bracket).

D'où `services/archetype_notes.py` : quarante archétypes décrits à la main, en
trois champs — le principe, comment ça gagne, ce qui lui tombe dessus. La règle
de lecture est affichée sur la page : **les textes sont d'un joueur, les
chiffres sont mesurés**, et aucun nombre n'entre dans ces notes. Les écrire
deux fois les ferait diverger de ce qui les calcule.

Les autres archétypes affichent leurs chiffres sans note plutôt que de faire
semblant d'avoir un avis. `aliases` sert la recherche, exactement comme dans
`land_cycles` : EDHREC range le superfriends sous « Planeswalkers », et un
joueur francophone tape « jetons » ou « défausse ».

### « Est-ce que je peux le monter » n'a pas de réponse au niveau de l'archétype

Le coût est une propriété **du commandant**, pas de la stratégie : le même
archétype derrière un commandant qu'on possède et derrière un autre à 40 €
qu'on n'a pas ne sont pas la même dépense. La page chiffre donc chacun des
seize premiers commandants, et trois règles portent ce calcul :

- **L'identité de couleur borne le noyau.** Les 63 meilleures cartes d'un
  archétype sont réparties sur les cinq couleurs : sans le `<@`, on annoncerait
  un prix pour un deck impossible à jouer. Conséquence visible à l'écran : un
  commandant mono-couleur affiche « noyau 9/51 » — c'est l'archétype qui n'a pas
  assez de cartes dans ces couleurs, **pas la collection qui manque**, et
  l'interface le dit.
- **Le commandant n'occupe pas un des 63 créneaux** (il est dans la zone de
  commandement) mais son propre prix est affiché à côté quand il n'est pas
  possédé — c'est souvent le plus gros achat de la liste.
- **Le total est doublé d'un compte au-dessus du plafond de prix.** « 320 € »
  ne se décide pas pareil selon qu'il s'agit de soixante cartes à cinq euros ou
  de trois pièces à cent, et c'est exactement la question « gros investissement
  ou non ». Les cartes sans prix sont comptées à part, jamais ajoutées pour
  zéro.

**Le catalogue au niveau de la liste n'affiche aucun taux de couverture**, et
c'est délibéré : « j'ai 40 des 63 meilleures cartes du tokens » mélangerait les
cinq couleurs et ne dirait rien de constructible. Le seul chiffre honnête à ce
niveau est le nombre de commandants de l'archétype **qu'on possède**.

### Le lien vers `/competitive`, et le piège qu'il révèle

L'article renvoie vers `/competitive?archetype=<slug>&format=<format>` : les
deux pages partagent le **même espace de slugs** (EDHREC nomme « infect » ou
« planeswalkers » des deux côtés), donc la stratégie choisie ici arrive
présélectionnée là-bas.

Mais les deux tables ne recensent pas la même chose, et l'écran doit le dire :
`commander_themes` ne contient que les **huit archétypes les plus joués de
chaque commandant possédé** (ce qu'EDHREC publie sur sa fiche, au-dessus de
50 decks), tandis que `archetype_commanders` part du format entier. Un
commandant qu'on possède peut donc figurer parmi les pilotes d'un archétype
sans que cet archétype soit dans son top 8 — auquel cas `/competitive` ne sait
pas le construire. Il l'écrit en clair plutôt que d'afficher une grille non
filtrée comme si de rien n'était.

**Les visuels ne sont rapatriés que pour les commandants et les trois sections
de tête** (une trentaine), pas pour les trois cents cartes du catalogue : même
règle que `/must-have`, au-delà de quelques dizaines d'images un rapatriement
six par six ferait attendre une vingtaine de secondes pour des cartes qu'on ne
regardera pas.

## Cartes à avoir (`/must-have`)

**Ce n'est pas un palmarès, c'est une liste d'achats de long terme.** La
question n'est pas « quelles sont les meilleures cartes du format » mais
« qu'est-ce que je gagnerais à acheter, au fil du temps, sans dépasser mon
plafond ». Cette intention décide de tout le reste :

- **Le filtre de prix change la physionomie du classement, et c'est assumé.**
  Une carte à 400 € n'est pas une information manquante ici : elle ne sera
  jamais achetée. En contrepartie, le nombre de cartes écartées est renvoyé
  (`over_budget`) et affiché, pour que la liste ne se fasse pas passer pour un
  classement complet. Mesuré sur la collection actuelle : à 50 €, six cartes
  seulement sur 366 sont écartées — le haut du classement est massivement fait
  de pièces à moins d'un euro.
- **Les cartes possédées restent, quel que soit leur prix**, grisées. Le
  plafond ne concerne que les achats, comme partout ailleurs.
- **Une carte sans `price_eur` n'est jamais proposée** : prix inconnu n'est pas
  prix nul.

Le classement est `edhrec_rank`, qui arrive avec `sync_scryfall`. **Il n'y a
donc aucune table à entretenir et aucun flow Kestra propre à cette page** : la
liste se met à jour toute seule au rythme mensuel du flow `sync-scryfall`.
**Sauf en duel**, classé sur les tops de tournoi — voir « Le méta du Duel
Commander ». Il
n'en faudrait un que pour changer de source — les pages *top cards* d'EDHREC,
qui classent par taux d'inclusion réel plutôt que par popularité globale.

Deux choix qui se discutent :

- **Une carte figure dans chacun de ses types.** Un « Artifact Creature »
  apparaît chez les artefacts et chez les créatures. Pour un usage d'achat
  c'est le bon comportement : on cherche un rocher de mana dans les artefacts
  sans se demander s'il est aussi une créature, et on ne l'achète qu'une fois.
- **Trente planeswalkers au lieu de cinquante** : ils sont bien moins nombreux,
  et la queue du classement descendrait vite dans ce qui ne se joue pas.

Les terrains de base sont exclus, comme partout : ils ne s'achètent pas. Le
format (`commander` / `duel`) change la banlist appliquée — Sol Ring domine les
artefacts en multijoueur et disparaît en duel, où des cartes moins jouées
prennent sa place. Les deux listes ne s'emboîtent donc pas, un test le fige.

**Deux boutons par carte** — « + collection » et « + recherche » — pour remplir
l'une ou l'autre au fil de la lecture. C'est le chemin naturel quand la
collection a été alimentée par les decks cochés « déjà monté » et non saisie
carte par carte : beaucoup de choses marquées « à acheter » sont en fait déjà
dans les boîtes.

Deux précautions, parce que les quantités **s'additionnent** dans les deux
tables :

- La réponse porte `wanted` à côté de `owned`. Sans afficher ce qui est déjà
  dans la liste de recherche, un second clic demanderait un second exemplaire
  sans rien dire.
- Le bouton est désactivé pendant l'envoi, ce qui neutralise le double-clic.

L'ajout **met la liste à jour localement** plutôt que de la recharger : la page
fait seize requêtes SQL, et on ajoute des cartes à la chaîne. La mise à jour
parcourt tous les groupes, parce qu'une même carte figure dans plusieurs types
(Solemn Simulacrum est dans les artefacts *et* dans les créatures) et que n'en
marquer qu'un laisserait l'autre affirmer le contraire. Les compteurs d'en-tête
sont recalculés à l'affichage pour la même raison — ceux du serveur seraient
périmés dès le premier clic.

La page a **deux affichages**, visuels par défaut et liste au choix, comme la
collection : sur une liste d'achats, beaucoup de cartes sont inconnues et une
illustration les fait reconnaître plus vite qu'un nom, mais comparer des prix
se fait en tableau. Les cartes possédées sont estompées et non retirées — leur
place dans le classement reste une information.

**Pas d'appel à `card_images.ensure_images` sur cet endpoint** pour autant,
contrairement à `/wishlist` : huit types à cinquante cartes font près de quatre
cents visuels, qu'un rapatriement six par six mettrait une vingtaine de
secondes à récupérer au premier chargement. Les images viennent donc de
Scryfall, et `CardTile` les charge en `loading="lazy"` : le navigateur ne prend
que ce qui est à l'écran. C'est ce qui rend le mode visuel gratuit — il
n'aurait pas été tenable en chargement imposé.


## Refuser un conseil (`deck_ignored_cards`)

« Ne me propose plus cette carte pour ce deck. » Deux endroits l'offrent, et ce
sont exactement ceux qui **modifient un deck existant** : les suggestions
(`/decks/[id]/suggestions`) et l'équilibrage (`/balance`). Les écrans qui
*construisent* un deck de zéro — `/deck-plans`, `/competitive`, `/deck-ideas` —
n'ont pas de deck sur lequel accrocher un refus et ne sont pas concernés.

**Le refus est rattaché au deck, pas global.** Refuser Rhystic Study pour
l'Atraxa ne dit rien du Kykar, et une ignorance globale irait masquer des cartes
sur les écrans ci-dessus, dont ce n'était pas le sujet. Une seconde table
globale reste possible si le besoin apparaît : le filtre est déjà posé.

Trois propriétés qui ne se devinent pas :

- **Le refus ne retire rien du deck** et ne change aucune quantité. Il ne parle
  que du conseil. Une carte refusée reste jouée si elle l'était.
- **Il vaut dans les deux sens** : ni proposée à l'ajout, ni proposée au
  retrait. Le même identifiant ne peut pas signifier les deux à la fois — une
  carte est dans le deck ou elle n'y est pas — donc il n'y a pas d'ambiguïté.
  C'est ce qui permet au bouton « je la garde » d'un retrait conseillé et au
  bouton « ignorer » d'un ajout conseillé de partager la même table.
- **Il est idempotent**, contrairement à la collection et à la liste de
  recherche où les quantités s'additionnent. Refuser deux fois ne double rien.

**Le filtre tient en une ligne parce que le point d'entrée est unique** : les
deux écrans passent par `cards_db.find_candidates`, dont le paramètre
`exclude_oracle_ids` servait déjà à écarter les cartes présentes dans le deck.
Les refus s'y ajoutent. Si un troisième écran de modification apparaît, c'est le
seul endroit à ne pas oublier.

**La liste des refus voyage avec les conseils** (`ignored` dans la réponse des
suggestions) et s'annule d'un bouton. Ce n'est pas du confort : une liste
invisible serait un piège, et dans six mois plus rien n'expliquerait pourquoi
une carte ne remonte jamais. La page d'équilibrage, qui n'affiche pas cette
liste, renvoie explicitement vers les suggestions du deck.

Refuser relance le calcul côté client, là où `/must-have` se contente d'une mise
à jour locale : écarter une carte doit laisser une autre prendre sa place, et
seul le moteur peut la désigner.


### Combos expliqués et synergies (fiche de deck)

La fiche de deck ne se contente plus d'annoncer un combo, elle dit **comment on
le joue** : Spellbook publie les étapes (`description`) et les prérequis, qu'on
jetait. « Infinite damage » ne dit pas quelle carte lancer en premier ni combien
de fois répéter la boucle — sans les étapes, on annonce au joueur un combo qu'il
ne sait pas exécuter. Migration 016, puis `sync_combos.py` : la colonne naît
vide, seule une resynchronisation la remplit.

L'encadré de bracket n'en garde que le **compte**, la liste détaillée vivant
plus bas : le bracket a besoin de savoir *combien* de combos gagnent la partie,
pas de les raconter.

**La synergie n'est pas la popularité, et c'est tout l'intérêt.** EDHREC la
définit comme l'écart entre « jouée avec ce commandant » et « jouée dans cette
couleur en général ». Sol Ring est dans presque tous les decks : sa synergie
avoisine zéro partout. Une carte de niche jouée surtout ici monte à +0,85.
Classer par popularité ferait remonter les mêmes dix cartes sur les six decks ;
classer par synergie désigne ce qui est là **pour ce commandant-là**. Un test le
fige en vérifiant que Sol Ring n'arrive jamais en tête.

Les valeurs **négatives** sont conservées et affichées : une carte moins jouée
ici qu'ailleurs est une information, souvent le signe qu'elle n'est pas à sa
place.

La liste est **vide** quand le commandant n'a pas de données EDHREC — il n'est
pas dans la collection, ou la synchro n'a pas tourné — et l'interface masque
alors la section plutôt que d'afficher un tableau vide.

**Les trois écrans qui produisent une decklist l'affichent** : la fiche de deck,
la decklist proposée (`/deck-ideas/[id]`) et le deck compétitif. Un seul
composant (`CombosAndSynergies`) et une seule requête les servent — les trois
posent la même question et méritent la même mise en garde, et la dupliquer
laisserait les explications diverger.

**Une nuance sépare pourtant le compétitif des deux autres : la synergie y est
mesurée contre l'archétype**, pas contre l'ensemble des decks du commandant
(`theme_recommendations` au lieu de `commander_recommendations`). Ce deck est
bâti *pour* une stratégie, et une carte peut être décisive en infect et inutile
en superfriends. Vérifié sur l'Atraxa : en thème Infect, les meilleures
synergies sont Prologue to Phyresis et Infectious Inquiry, qui ne remonteraient
pas dans un classement tous decks confondus.


### Essayer un archétype sans acheter (`/deck-ideas/[id]`)

Ouvrir une idée de deck donne la liste que les joueurs d'EDHREC montent
réellement avec ce commandant, et **un bouton « remplacer » sur chaque carte à
acheter** : le créneau est repris par une carte déjà possédée. Le deck y perd
en puissance et c'est assumé — un deck moins fort qu'on peut jouer ce soir vaut
mieux qu'un deck parfait qu'on n'a pas.

Quatre règles portent le remplacement :

- **Le remplaçant est du même rôle** quand il en existe un (`categories`).
  Échanger un removal contre un rocher de mana dépannerait le budget en
  déséquilibrant le deck.
- **Un exemplaire n'occupe qu'un créneau.** C'est la même règle physique que
  pour l'allocation entre decks : une carte déjà employée ne ressort pas
  ailleurs dans la liste.
- **Le vivier ignore le prix et écarte les terrains.** Ces cartes sont acquises,
  leur prix ne concerne personne ; et le noyau visé étant non-terrain,
  remplacer un rocher de mana par une forêt ne remplirait pas le créneau, il en
  créerait un autre.
- **Rien n'est écrit en base.** La page est un brouillon : le remplacement vit
  dans le navigateur, il est instantané et réversible. Le vivier complet est
  renvoyé en une fois plutôt qu'interrogé carte par carte — quelques centaines
  de lignes tiennent dans une réponse, un aller-retour par clic rendrait le
  geste poussif.

`ensure_images` ne porte que sur le noyau : le vivier peut compter des
centaines de lignes dont on n'affichera qu'une poignée.


## Vue d'ensemble (`/`)

La page d'arrivée après connexion — la page de connexion elle-même ne peut rien
afficher, elle n'a pas encore de jeton. Elle répond à « où en est ma collection
face à ce qui se joue », par type et par popularité.

**Sans plafond de prix, et c'est tout le point.** `/must-have` répond « qu'est-ce
que je peux acheter », cette page répond « qu'est-ce que je couvre ». Appliquer
un plafond ici gonflerait mécaniquement la couverture : les cartes chères qu'on
ne possède pas sortiraient du **dénominateur**, donc le pourcentage monterait
sans qu'on ait rien acquis. Les deux lectures partagent la même requête
(`must_have(max_price=None)`), pour qu'elles ne puissent pas diverger.

Trois précautions d'affichage :

- **Le dénominateur est la taille réelle de chaque classement**, pas la cible :
  les Batailles sont moins de cinquante en tout, et « 0 / 50 » laisserait croire
  à un manque inexistant.
- **Les cartes manquantes sont estompées, pas masquées.** Un classement dont on
  retire ce qu'on n'a pas ne dit plus rien de ce qu'il reste à couvrir.
- **Une carte à plusieurs types n'est comptée qu'une fois** dans la liste
  parcourue, alors qu'elle figure bien dans chacun de ses classements.

Les **tranches de popularité** sont de largeur croissante parce que le rang
EDHREC est un classement et non une note : l'écart entre le 1er et le 100e n'a
rien à voir avec celui entre le 4000e et le 4100e. Les cartes **sans rang** ne
sont comptées dans aucune tranche — une absence de mesure n'est pas un mauvais
score, et les ranger avec les moins jouées inventerait une information.

Les deux graphiques n'ont **qu'une série** chacun : ce sont des magnitudes, pas
des identités. D'où `--chart-seq` et non une palette catégorielle, qui aurait
donné huit couleurs sans information et enterré la seule chose qui compte,
l'ordre des longueurs. Filtre et pagination sont côté navigateur : la réponse
tient en une requête, la repayer à chaque clic de page serait du gaspillage.


## Construire un deck à la main (`/build`)

Le geste du classeur : le format, un commandant qu'on prend, puis les cartes
qui peuvent aller avec lui. Le site ne décide rien ici — il propose, il compte,
il évalue.

**Rien n'est écrit tant que le bouton « enregistrer » n'est pas cliqué.** Le
brouillon vit dans le `localStorage` du navigateur, ce qui le fait survivre à un
rechargement sans jamais devenir un deck. C'est la promesse centrale de la page,
et un test la fige : évaluer ne crée aucun deck.

Quatre appuis, tous réutilisés plutôt que réécrits :

- **Le vivier** (`cards_db.buildable_pool`) : ce que la collection permet de
  mettre dans *ce* deck — identité de couleur, légalité du format, terrains
  compris, puisqu'on construit aussi la manabase. Les artefacts passent sans
  clause particulière : leur identité est vide, donc incluse partout. Le vivier
  part **entier** au navigateur (quelques centaines de lignes), qui filtre et
  cherche sans aller-retour ; il est classé par taux d'inclusion EDHREC pour ce
  commandant, l'ordre alphabétique ne disant rien de ce qui va avec lui.
- **L'assistance aux terrains** appelle `deck_plans.land_plan`, le calcul de la
  page « Monter 4 decks » : non-basiques possédés d'abord (gratuits et meilleurs
  qu'un basique), puis basiques au prorata des symboles de mana réellement
  demandés, commandant compris. L'endpoint renvoie les basiques **avec leur
  impression** : le conseil ne fait pas que les nommer, le navigateur doit
  pouvoir les poser.
- **L'évaluation** est celle de la fiche de deck, à l'identique — bracket,
  manabase profonde, rôles, courbe, prix, alertes de légalité. Un brouillon doit
  se lire avec les mêmes chiffres que le deck qu'il deviendra, sinon
  enregistrer changerait le diagnostic.
- **La comparaison** passe par `matchup.compare`, la même que `/matchup`, avec
  `id: None` pour le brouillon : confronter avant d'enregistrer est tout
  l'intérêt.

**Changer de commandant vide le brouillon** : l'identité de couleur change, et
garder des cartes devenues illégales serait un piège silencieux.

**L'illustration au survol** (`components/CardHoverPreview.tsx`) répond à
« qu'est-ce que je suis en train de poser » : les deux listes de la page — le
vivier et le deck — ne montrent que des noms, et on construit avec une
collection qu'on ne connaît pas par cœur. Elle est posée sur les deux, parce
qu'on retire une carte par erreur aussi facilement qu'on en ajoute une.

Trois choix qui ne se devinent pas :

- **L'aperçu ne suit pas la souris.** Il se pose là où le curseur est entré
  dans la ligne et n'y bouge plus : suivre le pointeur obligerait à réagir à
  chaque `mousemove`, donc à re-rendre une page de deux cents lignes en
  continu, pour un confort qui n'en est pas un — une image qui glisse sous
  l'œil se lit moins bien qu'une image posée.
- **120 ms avant d'afficher, et avant d'effacer.** Sans ce délai, descendre la
  liste déclencherait deux cents téléchargements d'illustration pour des lignes
  qu'on n'a fait que traverser ; au retrait, il évite le clignotement d'une
  ligne à sa voisine.
- **Le clavier est servi comme la souris** : les lignes sont des boutons, donc
  elles se reçoivent au `Tab`, et l'aperçu se place alors contre le bord droit
  de la ligne — il n'y a pas de curseur d'où partir.

Le rendu passe par un portail vers `document.body` : une liste à
`overflow-y-auto` ne clippe pas un élément `fixed`, mais un ancêtre à
`transform` le ferait, et cela ne se verrait qu'une fois la carte survolée.

### Archiver plutôt que supprimer

`decks.archived_at` (migration 018) — une date et non un booléen : « quand
l'ai-je rangé » se lit sur la page d'archives, et `NULL` dit « actif » sans
seconde colonne à tenir cohérente.

**Archiver ne supprime rien et ne touche pas à la collection.** Le deck sort
seulement des écrans qui parlent de ce qu'on joue : la liste des decks,
l'équilibrage, la comparaison, et le **panel du classement de performance** —
`decks_db.list_decks()` filtre par défaut, donc tous ces écrans suivent sans
rien changer. Sans ce filtre, archiver n'aurait rien changé à ce que le site
raconte.

Le deck qu'on vient de construire s'archive directement depuis l'atelier, une
fois enregistré : ranger un deck d'essai est le cas le plus fréquent.

## Terrains budget, par cycle (`/terrains-budget`)

Une manabase ne s'achète pas carte par carte mais par **cycles** : checklands,
tango, filtres, painlands, horizons… Chaque cycle compte une carte par paire de
couleurs, donc « qu'est-ce qu'il me manque en B/G » a une réponse courte et
exacte — mesuré sur la collection réelle : 21 cartes, 2 possédées, **9,05 €
pour compléter**.

**Les cycles sont constatés dans le texte oracle**, jamais saisis à la main :
`services/land_cycles.py` ne contient que des motifs, la liste des cartes est le
résultat d'une requête et suit donc les sorties de sets toute seule. Les motifs
sont écrits une fois et joués des deux côtés — en SQL pour chercher, en Python
pour classer (`_matches` reproduit la sémantique d'`ILIKE`) — parce que dix
balayages du catalogue pour dix cycles seraient payés à chaque affichage.

Les effectifs servent de garde-fou : tango 10, bounce 10, slow 10, check 11,
filter 10. Un cycle qui gonflerait soudain signale un motif devenu trop large
après une sortie de set. Le motif des filterlands a justement dû être resserré
en regex (`{X}, {T}: Add`) : en `ILIKE` il ramassait soixante cartes.

**Le plafond ne concerne que les achats** : un terrain possédé reste affiché
quel que soit son prix, comme partout.

### Ce qu'une vidéo apporte, et ce qu'elle n'apporte pas

L'idée de départ était d'extraire des **noms de cartes** de vidéos « budget ».
Mesuré sur une vidéo francophone de treize minutes :

- **En acceptant un seul mot**, dix-huit trouvailles dont sept fausses —
  « Concentration », « Dragons », « Embuscade », « Mutilation » sont des mots
  français courants *et* des noms de cartes. **Deux mots minimum** : onze
  trouvailles, un seul faux positif. C'est la règle retenue.
- **Le rappel reste faible** et c'est structurel : les sous-titres automatiques
  n'ont ni ponctuation ni majuscules et écorchent les noms propres.

Le vrai gisement était ailleurs : **le chapitrage de la vidéo**, écrit par
l'auteur, nommait dix cycles (« TANGO LANDS », « ODISSEY FILTERS »). Une vidéo
de manabase ne recommande pas des cartes, elle recommande des familles — et une
famille, le catalogue sait l'énumérer exactement. D'où `ALIASES` dans
`land_cycles` : les mots par lesquels une chaîne francophone désigne un cycle.

`videos` et `video_mentions` (migration 019) ne stockent **aucun texte de
retranscription** : des identifiants de cartes, des clés de cycles, des comptes
et le moment de la première mention — de quoi fabriquer un lien qui ouvre la
vidéo au bon endroit. Ce qui se republierait n'a rien à faire en base.

**C'est l'outil local qui parle à YouTube, jamais le serveur.**
`magic_edh_tools/youtube_cards.py` (hors dépôt, hors déploiement) récupère
retranscription et chapitrage, puis appelle `POST /videos/import`, qui croise et
retient. Mettre YouTube dans le chemin d'un écran ajouterait une dépendance
externe fragile — ils bloquent volontiers les adresses de serveurs — pour un
usage qui reste ponctuel.

## Qui gagne, et avec quel archétype (`/performance`)

**Aucune source ne publie de taux de victoire en Commander casual.** EDHREC
compte des decks, pas des parties ; les bases de tournoi ne couvrent que le
cEDH. Prendre le bracket ou la popularité pour une performance inventerait la
mesure — exactement ce que le projet refuse ailleurs pour le stax. La seule
victoire mesurable ici est donc celle que le projet simule déjà
(`services/duel.py`), et la page hérite du **biais documenté** de ce modèle.

**La méthode est un gantelet, pas un tournoi toutes rondes.** Chaque commandant
possédé monte son meilleur deck avec la collection, puis affronte le même
panel : les decks enregistrés. Deux raisons, et la seconde décide :

- un tournoi toutes rondes sur 131 commandants, c'est 8 515 affrontements, une
  heure et demie de calcul, à refaire après chaque achat ;
- « qui bat ce qu'on joue déjà » est une question plus utile, pour une soirée
  entre amis, que « qui bat la moyenne des commandants possédés ».

Quatre règles portent la mesure, toutes venues d'un résultat faux constaté :

- **Un score ne se compare qu'à panel égal.** Le panel est donc écrit dans
  chaque ligne, avec la date, et affiché en tête de page. Ajouter un deck
  enregistré change tous les taux.
- **Un deck de moins de 60 cartes n'est pas un adversaire**
  (`MIN_PANEL_DECK_CARDS`). Un brouillon de neuf cartes traînait en base : il
  perdait contre tout le monde et gonflait tous les taux de la même façon, ce
  qui ne classe plus rien.
- **Pas de miroir** : un commandant n'affronte pas son propre deck. Seuls ceux
  qui en ont déjà un en joueraient, et leur score cesserait d'être comparable
  aux autres (mesuré : 65 % → 75 % sur l'Edgar une fois le miroir écarté).
- **Les parties non conclues au bout de 25 tours comptent au dénominateur.** Ne
  pas savoir finir est un résultat, pas une absence de résultat.

Le taux agrège **toutes** les parties du panel plutôt que la moyenne des taux
par adversaire : sinon un adversaire écarté pèserait autant qu'un adversaire
joué.

**Les archétypes ne sont mesurés que pour les vingt premiers**
(`THEMES_FOR_TOP`) : 562 archétypes coûteraient un quart d'heure et personne ne
lit le 87e. Chacun est monté par `competitive.build`, qui répond déjà à « le
plus proche des decks réels de cet archétype, avec ce que j'ai ». **Tous les
archétypes d'un commandant restent affichés**, pas seulement le meilleur :
savoir que l'infect gagne ne dit rien de ce que valent les autres, et c'est
justement la question qu'on se pose devant un commandant.

**Le calcul vit en ligne de commande** (`scripts/rank_commanders.py`, plusieurs
minutes) et écrit `commander_performance`, table reconstructible. L'endpoint
`GET /performance` ne fait que la lire : le déclencher en HTTP se ferait couper
à 100 s par Cloudflare, comme la synchro EDHREC avant lui. Le `case`
`rank-commanders` de `deploy/kestra-sync.sh` permet de le planifier.

**Un noyau incomplet explique un mauvais score sans rien dire du commandant** :
c'est la collection qui manque de cartes dans son identité de couleur. La page
affiche donc `core_size` à côté du taux.

## Sortir une decklist de l'écran

### Les terrains se lisent en liste, comme le reste des cartes

Les écrans qui **construisent** un deck (`/competitive`, `/deck-plans`) les
énuméraient en une phrase — « Bassin réfléchissant, Fontaine sacrée, 11 Ile,
8 Montagne » — alors que les sorts, eux, étaient en liste. Une manabase se
relit carte par carte comme le reste, et les basiques portent une quantité
qu'une énumération noie. Ils sont donc rendus comme les autres sections :
quantité à gauche, nom à droite. Les terrains de base n'ont pas de visuel en
mode images (ils n'ont pas d'impression choisie, seulement un nom et un
compte) : ils restent en liste sous la planche des non-basiques.

Le découpage par type vit dans `lib/decklist.ts`, partagé par le deck
compétitif et l'export PDF — sans quoi la même carte finirait dans deux
sections différentes selon l'écran. Deux règles de classement s'y trouvent,
toutes deux issues de cartes réelles : **`Land` est testé en premier** (une
Cité de Darksteel est un « Artifact Land », et on la cherche dans ses
terrains), et **`Creature` avant `Artifact`** (un Solemn Simulacrum se joue
comme une créature).

### Trois PDF pour trois usages (`lib/deck-pdf.ts`)

Générés côté navigateur comme la liste d'achats, par un seul composant
(`components/DeckExport.tsx`) branché sur les **quatre écrans qui montrent une
decklist** : la fiche de deck, l'atelier, le deck compétitif et l'idée de deck.
Ce ne sont pas trois habillages du même document : chacun répond à une question
que les deux autres ne posent pas.

- **Fiche du deck** — le deck rangé par sections, deux colonnes, une page pour
  cent cartes, **suivi de ce que le site dit du deck** : courbe de mana,
  bracket et ce qui en fixe le plancher, manabase couleur par couleur avec
  l'échange de basiques conseillé, équilibre des rôles, alertes de légalité,
  combos avec leurs étapes, meilleures synergies. C'est ce qu'on garde avec la
  boîte, et une liste seule ne rappelle pas pourquoi le deck est ce qu'il est.
  Un écran sans analyse à donner exporte la liste seule, sous son ancien nom
  (« liste par type »).
- **Visuels** — cinq cartes par ligne, vingt-cinq par page. À 33 mm de large
  l'illustration reste reconnaissable, ce qui est tout son rôle ici, le nom
  étant en légende. Quatre colonnes donnaient sept pages pour un deck.
  **Une carte en plusieurs exemplaires n'est dessinée qu'une fois**, sa
  quantité en légende : imprimer douze Forêts coûterait douze images sans rien
  apprendre.
- **Feuille de tournoi** — **tout** est listé, quantité et nom seulement, par
  ordre alphabétique et en trois colonnes équilibrées, le commandant marqué
  d'un astérisque. Rien d'autre : c'est ce qu'un arbitre vérifie, le prix et le
  type l'encombreraient. **Elle n'a jamais d'analyse**, même quand l'écran en a
  une — c'est le seul de ces documents qu'on remet à quelqu'un d'autre.

Les visuels gardent le bandeau de tête mais **pas** l'analyse : c'est une
planche, et l'imprimer une seconde fois ne l'expliquerait pas mieux.

#### D'où viennent les chiffres de la fiche

`lib/deck-sheet.ts` ne calcule **rien** : il met en page ce que l'écran affiche
déjà (`deckAnalysis()` adapte indifféremment un `DeckDetail` et un
`BuildEvaluation`, qui sortent du même calcul côté serveur). Un PDF qui
compterait de son côté finirait par contredire la fiche, et c'est le genre
d'écart qu'on ne voit qu'une fois le deck monté.

L'analyse arrive au composant de deux façons, et la distinction se paierait :

- **`analysis`** quand l'écran l'a déjà — la fiche de deck ;
- **`loadAnalysis`**, appelé **au clic**, quand elle se calcule : l'atelier,
  dont le brouillon a pu changer depuis le dernier « Évaluer », et le deck
  compétitif, qui n'est pas enregistré. La payer au chargement de ces pages
  serait payer une évaluation profonde que personne n'a demandée ; la lire dans
  un état déjà affiché la rendrait périmée dès la carte suivante. Une analyse
  qui échoue n'emporte pas la decklist : le PDF sort sans elle et l'écran le
  dit.

Deux conséquences qui ne se devinent pas :

- **Le deck compétitif se fait évaluer comme un brouillon d'atelier**
  (`/build/evaluate`), ce qui a obligé `/competitive/build` à rendre ses
  terrains de base **avec leur impression** (`basics_cards`, comme
  `/build/lands`) : cet endpoint ne connaît que des `scryfall_id`, et des
  basiques réduits à leur nom auraient disparu du brouillon — manabase jugée
  sur douze terrains au lieu de trente-six, sans qu'aucune alerte ne le
  signale. Un test le fige. Ses **synergies et ses combos restent ceux de
  l'écran**, mesurés contre l'archétype et non contre tous les decks du
  commandant.
- **`/deck-ideas/[id]` n'a ni bracket ni manabase** : son noyau est
  non-terrain, rien de tout cela ne s'y calcule. Sa fiche porte les combos, les
  synergies et une phrase qui dit précisément ce qui manque, plutôt que des
  sections vides.

Trois contraintes de mise en page, toutes constatées à l'impression
(`lib/pdf-page.ts`) :

- **jsPDF ne connaît que des coordonnées** : chaque bloc réserve sa hauteur
  avant d'écrire (`PageFlow.need`), sinon un saut de page oublié écrit
  par-dessus le bas de page — invisible tant qu'on ne regarde pas le PDF.
- **Un en-tête de tableau ne part jamais seul** : il est écrit avec la place de
  sa première ligne et réécrit en haut de la page suivante.
- **La police par défaut (Helvetica, WinAnsi) n'a pas de flèche.** « 11 → 13 »
  s'imprimait en deux caractères parasites ; l'échange de basiques s'écrit donc
  « de 11 à 13 ». Même vigilance pour tout caractère hors cp1252.

**Toutes les listes ne valent pas une feuille de tournoi**, d'où le paramètre
`modes` : `/deck-ideas/[id]` n'en propose pas. Cette liste est un brouillon de
63 non-terrains sans manabase, et l'exporter comme une decklist officielle
serait un piège — le PDF porte d'ailleurs une `note` qui dit ce qui manque. Ce
qui part au PDF y est l'**état courant de l'écran**, remplacements compris.

Trois conséquences du fait que ces écrans ne stockent rien
(`generatedDeckCards`) :

- **Chaque carte vaut un exemplaire**, sauf les terrains de base qui arrivent
  en compte (`{"Forêt": 8}`) et non en cartes.
- **Un basique n'a ni identifiant Scryfall ni visuel** : aucune édition n'a été
  choisie pour lui. Il est listé comme les autres et laisse, en mode images, un
  cadre à son nom — ce qui est exact, pas un défaut d'affichage.
- **Le commandant a sa propre section** en tête de la liste par type. C'est
  ainsi qu'une decklist s'écrit, et c'est la seule carte dont le rôle ne se lit
  pas dans son type — accessoirement, `/deck-ideas` ne renvoie pas le
  `type_line` de son commandant, qui serait tombé dans « Autre ».

Le `type_line` des cartes conseillées, lui, **était déjà lu en base et jeté**
par `services/deck_ideas._summarize` : sans lui toute la liste tombait dans
« Autre ». Il est désormais exposé (une ligne, aucune requête de plus).

Deux points d'exploitation :

- **Les visuels passent par `fetch`, donc par CORS.** Scryfall répond `*`, et
  notre `/card-images` hérite des en-têtes de `CORSMiddleware` — mais une
  origine absente de `CORS_ORIGINS` ferait échouer silencieusement chaque
  image. L'export ne casse pas pour autant : une image manquante laisse un
  cadre au nom de la carte, et le manque se voit. Six téléchargements en
  parallèle, comme le rapatriement côté back, et la progression est affichée
  sur le bouton — une centaine d'images prend quelques secondes et pèse
  ~8 Mo.
- **Les noms sont ceux de l'écran** (`displayName`) : français quand la carte
  a été traduite, anglais pour les ~12 % qui ne l'ont jamais été. Un arbitre
  français lit les deux ; forcer l'anglais rendrait la feuille illisible pour
  le joueur qui la remplit.

## Reste à faire

**Déployé et planifié.** DB (`lxc-pg18`, 192.168.1.104), back (`lxc-mtg-back`,
192.168.1.143) et front (`lxc-mtg-front`, 192.168.1.144), exposés en
`mtg-edh-api.julien-cloud.eu` et `mtg-edh.julien-cloud.eu`. Les
synchronisations sont ordonnancées par Kestra (`lxc-kestra`, 192.168.1.119).

Le méta du duel (MTGTop8) est codé et testé, **pas encore déployé** : migration
022, puis un premier `sync_mtgtop8.py --max-events 0` (quelques heures), puis
le flow `sync-mtgtop8.yml` à importer dans Kestra — voir `deploy/INSTALL.md`.

Deux pistes ouvertes, aucune engagée :

- **Narration de partie par Ollama** (LXC IA, même hôte que pour
  `sw-coaching`). Le principe directeur tient : une IA ne commenterait que des
  chiffres déjà calculés, elle n'en produirait aucun. Aucune IA n'est
  nécessaire au fonctionnement du projet aujourd'hui.
- **Changer la source du classement de `/must-have`** pour les pages *top
  cards* d'EDHREC, qui mesurent le taux d'inclusion réel plutôt que la
  popularité globale d'`edhrec_rank`. C'est la seule évolution de cette page
  qui demanderait une table et un flow Kestra propres.

Le duel simulé reste le point le plus perfectible du projet : il ignore vol,
piétinement, capacités activées et déclenchées, jetons, moteurs de pioche,
combos et contresorts. Le biais a une direction connue et l'interface le dit,
mais chaque mécanique ajoutée le réduirait.
