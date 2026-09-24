-- Le méta du Duel Commander, tel que MTGTop8 le relève en tournoi.
--
-- EDHREC ne distingue pas les formats : ses listes sont celles du
-- multijoueur, et les conseils de duel en héritaient — ramp lente, effets
-- symétriques et pioche de groupe surévalués, interaction bon marché et tempo
-- sous-évalués. MTGTop8 publie les tops des tournois de Duel Commander
-- (format `EDH` chez eux), avec le commandant rangé en « Sideboard » dans
-- l'export texte.
--
-- Les quatre tables sont **reconstructibles** par
-- `python scripts/sync_mtgtop8.py` : rien n'y est saisi à la main.

CREATE TABLE IF NOT EXISTS duel_events (
    event_id    INTEGER PRIMARY KEY,          -- `e=` chez MTGTop8
    name        TEXT NOT NULL,
    event_date  DATE NOT NULL,
    -- NULL quand l'organisateur ne l'a pas publié : ce n'est pas zéro joueur.
    players     INTEGER,
    -- Un événement sans aucune liste exploitable est gardé quand même, à
    -- zéro deck : sans cette ligne, chaque synchronisation le redemanderait.
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS duel_events_date_idx ON duel_events (event_date);

CREATE TABLE IF NOT EXISTS duel_decks (
    deck_id      INTEGER PRIMARY KEY,         -- `d=` chez MTGTop8
    event_id     INTEGER NOT NULL REFERENCES duel_events ON DELETE CASCADE,
    -- Tel qu'affiché (« 1 », « 3-4 », « 5-8 ») : MTGTop8 ne départage pas
    -- toujours les demi-finalistes, et inventer un ordre serait faux.
    rank_label   TEXT,
    placement    SMALLINT,                    -- meilleure place possible
    deck_name    TEXT,
    -- Un ou deux commandants (partenaires, arrière-plans).
    commander_oracle_ids UUID[] NOT NULL,
    -- L'union des identités des commandants : c'est elle qui dit quelles
    -- cartes ce deck **aurait pu** jouer, donc le dénominateur des taux.
    color_identity TEXT[] NOT NULL,
    -- Le profil du deck, calculé à l'import : cartes par type (terrains de
    -- base **compris** dans « Land ») et courbe des non-terrains. Même forme
    -- que les profils EDHREC de `commander_themes`, ce qui permet au
    -- constructeur compétitif de viser l'un ou l'autre sans rien convertir.
    -- Les basiques ne sont pas dans `duel_deck_cards` : sans ce compte, un
    -- deck à 38 terrains en afficherait 14.
    type_counts  JSONB NOT NULL,
    mana_curve   JSONB NOT NULL,
    -- Lignes de l'export qu'on n'a pas su résoudre, pour surveiller la
    -- qualité sans bloquer l'import.
    unresolved   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS duel_decks_commanders_idx
    ON duel_decks USING gin (commander_oracle_ids);

-- Les 99, commandants exclus (ils sont dans `duel_decks`), terrains de base
-- exclus (ils ne se choisissent pas et ne s'achètent pas).
CREATE TABLE IF NOT EXISTS duel_deck_cards (
    deck_id   INTEGER NOT NULL REFERENCES duel_decks ON DELETE CASCADE,
    oracle_id UUID NOT NULL,
    PRIMARY KEY (deck_id, oracle_id)
);
CREATE INDEX IF NOT EXISTS duel_deck_cards_oracle_idx ON duel_deck_cards (oracle_id);

-- Une ligne par carte vue dans au moins un deck, recalculée à la fin de
-- chaque synchronisation.
--
-- **Une table et non une vue matérialisée**, exprès : elle dépendrait de
-- `cards_cheapest` pour l'identité des cartes, et
-- `rebuild_cheapest_view.sql` fait un `DROP MATERIALIZED VIEW` — elle
-- disparaîtrait en silence au prochain ajout de colonne sur `cards`.
CREATE TABLE IF NOT EXISTS duel_card_stats (
    oracle_id      UUID PRIMARY KEY,
    -- Decks qui la jouent.
    decks          INTEGER NOT NULL,
    -- Decks qui **pouvaient** la jouer : ceux dont l'identité contient la
    -- sienne. Sans ce dénominateur, un Contresort serait jugé contre des
    -- decks mono-rouge qui n'ont jamais eu le droit de le jouer.
    eligible_decks INTEGER NOT NULL,
    rate           REAL NOT NULL,             -- decks / eligible_decks
    -- Part de **tous** les decks : c'est la popularité brute, celle qui
    -- classe « les cartes à avoir » toutes couleurs confondues.
    share          REAL NOT NULL
);

DO $$
DECLARE
    owner_role TEXT;
    t TEXT;
BEGIN
    SELECT tableowner INTO owner_role FROM pg_tables WHERE tablename = 'cards';
    IF owner_role IS NULL THEN
        RAISE NOTICE 'Table `cards` absente : droits non alignés, migration 001 d''abord.';
        RETURN;
    END IF;

    FOREACH t IN ARRAY ARRAY['duel_events', 'duel_decks', 'duel_deck_cards', 'duel_card_stats'] LOOP
        EXECUTE format('GRANT ALL PRIVILEGES ON TABLE %I TO %I', t, owner_role);
        BEGIN
            EXECUTE format('ALTER TABLE %I OWNER TO %I', t, owner_role);
        EXCEPTION WHEN insufficient_privilege THEN
            RAISE NOTICE 'Propriétaire de % inchangé (pas membre de %) : les GRANT suffisent.', t, owner_role;
        END;
    END LOOP;
END
$$;
