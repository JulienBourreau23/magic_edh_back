-- Thèmes de deck par commandant, et cartes jouées dans chaque thème.
--
-- EDHREC classe les decks d'un commandant par archétype (Atraxa : infect,
-- superfriends, proliferate, combo...). C'est la donnée qui manquait pour
-- construire un deck *orienté* plutôt qu'un agrégat de tout ce qui se joue
-- avec ce commandant, toutes stratégies confondues.
--
-- Deux tables reconstructibles, alimentées par `services/edhrec.py`.
CREATE TABLE IF NOT EXISTS commander_themes (
    commander_oracle_id UUID NOT NULL,
    slug                TEXT NOT NULL,
    label               TEXT NOT NULL,
    -- Nombre de decks recensés : sert à trier, et à écarter les thèmes
    -- confidentiels dont les listes ne veulent rien dire statistiquement.
    deck_count          INTEGER NOT NULL DEFAULT 0,
    -- Le profil des decks réels du thème, tel qu'EDHREC l'agrège : combien de
    -- terrains, de créatures, d'éphémères... et la courbe de mana. C'est une
    -- cible **mesurée** au lieu d'un repère inventé — sur ce thème précis, pas
    -- sur le Commander en général.
    type_counts         JSONB NOT NULL DEFAULT '{}'::jsonb,
    mana_curve          JSONB NOT NULL DEFAULT '{}'::jsonb,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (commander_oracle_id, slug)
);

CREATE TABLE IF NOT EXISTS theme_recommendations (
    commander_oracle_id UUID NOT NULL,
    theme_slug          TEXT NOT NULL,
    card_oracle_id      UUID NOT NULL,
    section             TEXT NOT NULL,
    synergy             NUMERIC,
    -- Part des decks de ce commandant DANS CE THÈME qui jouent la carte.
    -- C'est le classement de compétitivité : ce que jouent les gens qui
    -- gagnent avec cette stratégie, pas ce qui est cher ou joli.
    inclusion_rate      NUMERIC,
    PRIMARY KEY (commander_oracle_id, theme_slug, card_oracle_id, section)
);

CREATE INDEX IF NOT EXISTS theme_reco_lookup_idx
    ON theme_recommendations (commander_oracle_id, theme_slug);

-- Mêmes droits que le reste : voir migration_010.
DO $$
DECLARE
    owner_role TEXT;
BEGIN
    SELECT tableowner INTO owner_role FROM pg_tables WHERE tablename = 'cards';
    IF owner_role IS NULL THEN
        RETURN;
    END IF;
    EXECUTE format('GRANT ALL PRIVILEGES ON TABLE commander_themes TO %I', owner_role);
    EXECUTE format('GRANT ALL PRIVILEGES ON TABLE theme_recommendations TO %I', owner_role);
    BEGIN
        EXECUTE format('ALTER TABLE commander_themes OWNER TO %I', owner_role);
        EXECUTE format('ALTER TABLE theme_recommendations OWNER TO %I', owner_role);
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'Propriétaire inchangé (pas membre de %) : les GRANT suffisent.', owner_role;
    END;
END
$$;
