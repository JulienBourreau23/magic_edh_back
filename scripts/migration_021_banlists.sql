-- Les banlists, qui n'étaient nulle part.
--
-- `legal_commander` et `legal_duel` sont des booléens : ils confondent
-- « bannie » et « n'a jamais été jouable en tournoi ». Sur 99 500 impressions,
-- **2 327 cartes sont `NOT legal_commander`** — Un-sets, cartes playtest,
-- 30th Anniversary, jetons de Conspiracy — alors que la banlist du
-- multijoueur fait **83 cartes** et celle du duel **250**. On ne pouvait donc
-- pas afficher une banlist : la requête évidente aurait rendu quarante fois
-- trop de lignes, et surtout les mauvaises.
--
-- Scryfall publie la nuance (`legalities.commander` vaut `banned` et non
-- `not_legal`), et le sync la jetait — exactement le cas de `restricted` avant
-- la migration 015.
--
-- Deux conséquences obligatoires, ce sont les deux pièges documentés du projet :
--   1. rejouer `scripts/rebuild_cheapest_view.sql` (une vue matérialisée fige
--      sa liste de colonnes à la création) ;
--   2. relancer `python scripts/sync_scryfall.py` — les colonnes naissent à
--      `false` partout, et seule une synchronisation complète les renseigne.
--      Sans elle, la page affiche deux banlists vides sans rien signaler.
ALTER TABLE cards
    ADD COLUMN IF NOT EXISTS banned_commander BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS banned_duel      BOOLEAN NOT NULL DEFAULT FALSE,
    -- Le type d'édition de **cette impression** (`core`, `expansion`,
    -- `funny`, `memorabilia`...). Il sert à écarter de la banlist les cartes
    -- qui n'existent que hors tournoi : Unfinity marque 79 cartes bannies en
    -- duel, elles n'ont rien à faire à côté de Black Lotus.
    --
    -- Il est porté par l'impression et non par l'`oracle_id`, ce qui est
    -- **indispensable** : la plus célèbre des cartes bannies a pour impression
    -- la moins chère un proxy « 30th Anniversary » (memorabilia). Juger sur
    -- elle retirerait Black Lotus, les Moxen, Ancestral Recall et Chaos Orb de
    -- la banlist. On ne peut écarter une carte que si **aucune** de ses
    -- impressions n'est une vraie édition.
    ADD COLUMN IF NOT EXISTS set_type         TEXT;

-- Les deux listes se lisent en entier à chaque affichage (83 et 250 lignes) :
-- un index partiel suffit et reste minuscule.
CREATE INDEX IF NOT EXISTS cards_banned_commander_idx
    ON cards (oracle_id) WHERE banned_commander;
CREATE INDEX IF NOT EXISTS cards_banned_duel_idx
    ON cards (oracle_id) WHERE banned_duel;
