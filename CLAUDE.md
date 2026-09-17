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
│   ├── themes.py             # archétypes EDHREC et leurs cartes
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
│   ├── spellbook.py          # import du catalogue Commander Spellbook
│   ├── magic_ville_pdf.py    # découpage d'une planche de proxys
│   └── card_images.py        # téléchargement à la demande
├── scripts/
│   ├── migration_0*.sql      # schéma et colonnes successives
│   ├── rebuild_cheapest_view.sql  # définition canonique de la vue matérialisée
│   ├── sync_scryfall.py      # bulk data Scryfall -> cards (+ REFRESH)
│   ├── sync_french_names.py  # alias français (bulk all_cards, ~400 Mo)
│   ├── sync_edhrec.py        # recommandations et archétypes
│   ├── sync_combos.py        # catalogue Commander Spellbook
│   ├── backfill_categories.py # rejoue la classification sans retélécharger
│   ├── decklist_from_pdf.py  # planche magic-ville -> decklist
│   └── hash_password.py      # hash bcrypt pour AUTH_PASSWORD_HASH
├── kestra/                   # les trois flows d'ordonnancement
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
   resterait invisible.

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
├── must-have/page.tsx               # cartes les plus jouées par type, sous plafond
├── deck-ideas/page.tsx              # quel deck monter avec ce qu'on possède
├── deck-plans/page.tsx              # comparaison par commandant + 4 decks à monter + PDF
├── competitive/page.tsx             # deck compétitif bâti sur la collection
├── balance/page.tsx                 # équilibrage de 4 decks + liste d'achats PDF
├── matchup/page.tsx                 # comparaison de deux decks
└── login/page.tsx                   # seule page utilisable sans jeton
components/
    CardTile, CardBinder, CardSearch, CollectionFilters, CompetitiveDeck,
    DeckToolbar, ImportIssuesPanel, ManabaseAdvice, TopNav, ThemeProvider/Toggle
    graphiques : ManaCurveChart, ColorDonut, AxisRings, InitiativeSplit, DuelOutcome
lib/api.ts                  # tous les appels au back + types
lib/auth.ts                 # jeton en localStorage (d'où les composants client)
lib/collection-filters.ts   # filtres de la page collection
lib/mtg-labels.ts           # libellés français des mots-clés Scryfall
lib/shopping-pdf.ts         # export PDF de la liste d'achats
```

> Next.js 16 a des ruptures avec les versions antérieures (`params` est une
> Promise ; la règle de lint `react-hooks/set-state-in-effect` interdit un
> `setState` synchrone dans un effet — passer par `.then()`). Voir
> `node_modules/next/dist/docs/` avant d'utiliser une API App Router familière.
> La même famille de règles refuse aussi de réassigner une variable pendant le
> rendu : pas d'accumulateur muté dans un `.map()`.

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

Le duel simulé ignore vol/piétinement, capacités activées et déclenchées,
jetons, moteurs de pioche, combos, contresorts et dégâts de commandant. **Le
biais qui en résulte a une direction connue** : il avantage les decks dont la
puissance est dans les corps de créature et sous-estime ceux qui gagnent par
moteurs, combos ou contrôle. L'encadré « ce que la simulation modélise » dans
l'interface n'est pas décoratif — sans lui, un 60/40 se lit comme un pronostic.

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

La même synchronisation est accessible de deux façons, avec **une seule
implémentation** dans `services/edhrec.py` :

- `python scripts/sync_edhrec.py` (ligne de commande, lancement manuel)
- `POST /admin/sync-edhrec` (authentifié), appelé par le flow Kestra
  `kestra/sync-edhrec.yml`

Kestra vit dans son propre LXC : l'appel HTTP lui évite de dupliquer le dépôt,
un venv et les identifiants Postgres. **L'ordonnanceur reste interchangeable** —
rien dans le code ne dépend de Kestra, et les scripts CLI font le même travail.

### Les quatre synchronisations, et pourquoi deux mécanismes

Les flows vivent dans `kestra/` (namespace `mtg-edh`, instance `lxc-kestra`,
192.168.1.119). **Il n'y a pas de timer systemd** : un seul ordonnanceur, sinon
le même travail finirait par être lancé deux fois.

| Flow | Syncs | Déclenchement | Planification |
|---|---|---|---|
| `sync-scryfall.yml` | `cards`, puis `card_names_fr` | SSH | 1er du mois, 2 h |
| `sync-edhrec.yml` | recommandations et archétypes | HTTP | lundi 4 h |
| `sync-combos.yml` | catalogue Spellbook | HTTP | lundi 5 h |

**Le choix HTTP / SSH suit la durée, pas la préférence.** EDHREC et Spellbook
tiennent en une à deux minutes : l'appel HTTP synchrone rend un vrai code de
retour à l'ordonnanceur, c'est le plus simple. Scryfall et les noms français
durent plusieurs minutes et téléchargent 470 Mo à eux deux ; un endpoint HTTP
bloquant aussi longtemps serait fragile pour le même service rendu, alors que
les scripts CLI existent déjà.

**Kestra n'a pas de shell sur le back.** Sa clé publique est posée dans
`authorized_keys` avec `command="…/deploy/kestra-sync.sh"`, qui force ce script
quelle que soit la commande demandée ; celle-ci n'arrive que dans
`$SSH_ORIGINAL_COMMAND` et sert d'aiguillage. Seuls `scryfall` et
`french-names` sont acceptés, tout le reste sort en code 2. Ajouter une
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
sur les deux langues à la fois. **Couverture : ~88 %** — les vieux sets, Secret
Lairs et certains produits Commander n'ont jamais été traduits, l'absence
d'alias est normale et il faut alors le nom anglais.

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

Quatre étapes : un commandant de la collection, le format, l'archétype, le deck.
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
plus restrictif que `legal_commander`, jamais l'inverse — un test le fige, et
la légalité du commandant est vérifiée avant de construire 99 cartes autour de
lui.

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
liste se met à jour toute seule au rythme mensuel du flow `sync-scryfall`. Il
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


## Reste à faire

**Déployé et planifié.** DB (`lxc-pg18`, 192.168.1.104), back (`lxc-mtg-back`,
192.168.1.143) et front (`lxc-mtg-front`, 192.168.1.144), exposés en
`mtg-edh-api.julien-cloud.eu` et `mtg-edh.julien-cloud.eu`. Les quatre
synchronisations sont ordonnancées par Kestra (`lxc-kestra`, 192.168.1.119).

Rien n'est en chantier. Deux pistes ouvertes, aucune engagée :

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
