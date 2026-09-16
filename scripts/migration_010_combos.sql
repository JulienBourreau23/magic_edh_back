-- Combos à deux cartes, importés de Commander Spellbook.
--
-- Pourquoi une table plutôt qu'une règle : un combo naît de l'interaction
-- entre deux cartes, il n'est pas lisible dans le texte de l'une d'elles. Le
-- critère officiel « pas de combo infini à deux cartes aux brackets 1-2 » est
-- donc le seul du Commander Format Panel qu'on ne peut ni calculer ni deviner
-- — il se constate, contre un catalogue.
--
-- Source : l'API publique de Commander Spellbook. Table entièrement
-- reconstructible (`python scripts/sync_combos.py`), aucune donnée propre.
CREATE TABLE IF NOT EXISTS combos (
    -- Identifiant de la variante chez Spellbook : stable, et il permet de
    -- retrouver la page du combo pour vérifier à la main.
    variant_id        TEXT PRIMARY KEY,
    -- La paire est triée (a < b) : une seule ligne par combo, et la recherche
    -- « les deux cartes sont dans le deck » n'a pas à tester les deux sens.
    oracle_id_a       UUID NOT NULL,
    oracle_id_b       UUID NOT NULL,
    -- Noms anglais, pour l'affichage de secours et la lecture en SQL. Le nom
    -- français, s'il existe, est joint à l'affichage comme partout ailleurs.
    card_a            TEXT NOT NULL,
    card_b            TEXT NOT NULL,
    -- Effets produits ("Infinite damage", "Win the game"...).
    produces          TEXT[] NOT NULL DEFAULT '{}',
    -- Ce combo gagne-t-il la partie à lui seul ? Calculé au sync à partir de
    -- `produces` : c'est lui qui pèse sur le bracket, pas le mana infini.
    wins_outright     BOOLEAN NOT NULL DEFAULT FALSE,
    -- Mana nécessaire pour exécuter le combo une fois les deux cartes posées.
    mana_needed       TEXT,
    mana_value_needed INTEGER,
    -- Étiquette de bracket telle que Spellbook la publie (R/S/P/O/C/E/B).
    -- Conservée brute, comme signal : leur échelle n'est pas la nôtre.
    bracket_tag       TEXT,
    -- Nombre de decks recensés jouant ce combo : sert à trier.
    popularity        INTEGER,
    fetched_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT combos_pair_ordered CHECK (oracle_id_a < oracle_id_b)
);

CREATE INDEX IF NOT EXISTS combos_oracle_a_idx ON combos (oracle_id_a);
CREATE INDEX IF NOT EXISTS combos_oracle_b_idx ON combos (oracle_id_b);

-- Aligne les droits sur le rôle qui possède `cards`, c'est-à-dire le rôle
-- applicatif, quel que soit le compte qui joue cette migration. Sans ça, une
-- migration passée avec un compte personnel crée une table que l'application
-- ne peut ni tronquer ni remplir : le sync échoue en « permission denied »
-- après avoir téléchargé les 40 pages.
--
-- Les GRANT d'abord, parce qu'ils suffisent et qu'ils passent toujours ;
-- le changement de propriétaire ensuite, parce qu'il est plus propre mais
-- exige d'être membre du rôle cible — ce qui n'est pas garanti. Son échec
-- n'est donc pas une erreur. Idempotent dans tous les cas.
DO $$
DECLARE
    owner_role TEXT;
BEGIN
    SELECT tableowner INTO owner_role FROM pg_tables WHERE tablename = 'cards';
    IF owner_role IS NULL THEN
        RAISE NOTICE 'Table `cards` absente : droits non alignés, migration 001 d''abord.';
        RETURN;
    END IF;

    EXECUTE format('GRANT ALL PRIVILEGES ON TABLE combos TO %I', owner_role);

    BEGIN
        EXECUTE format('ALTER TABLE combos OWNER TO %I', owner_role);
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'Propriétaire inchangé (pas membre de %) : les GRANT suffisent.', owner_role;
    END;
END
$$;
