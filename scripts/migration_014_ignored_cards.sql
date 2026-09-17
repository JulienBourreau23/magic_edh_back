-- Cartes refusées pour un deck : « ne me propose plus celle-là ici ».
--
-- Rattachée au deck et non globale, parce que le refus porte sur une
-- *modification de deck* : refuser Rhystic Study pour l'Atraxa ne dit rien du
-- Kykar. Les écrans qui construisent un deck de zéro (/deck-plans,
-- /competitive, /deck-ideas) n'ont pas de deck sur lequel s'accrocher et ne
-- sont donc pas concernés.
--
-- Même clé que la collection et la liste de recherche (`oracle_id`) : ce qu'on
-- refuse, c'est « un Sol Ring », pas une édition.
CREATE TABLE IF NOT EXISTS deck_ignored_cards (
    deck_id    INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    oracle_id  UUID NOT NULL,
    -- Pourquoi elle a été refusée, si on a pris la peine de le dire. La liste
    -- est consultable et réversible : sans raison ni date, on ne saurait plus
    -- dans six mois pourquoi une carte ne remonte jamais.
    reason     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (deck_id, oracle_id)
);

-- Le filtre part toujours d'un deck : c'est l'ordre de la clé primaire, donc
-- aucun index supplémentaire n'est utile.

-- Mêmes droits que le reste : voir migration_010.
DO $$
DECLARE
    owner_role TEXT;
BEGIN
    SELECT tableowner INTO owner_role FROM pg_tables WHERE tablename = 'cards';
    IF owner_role IS NULL THEN
        RETURN;
    END IF;
    EXECUTE format('GRANT ALL PRIVILEGES ON TABLE deck_ignored_cards TO %I', owner_role);
    BEGIN
        EXECUTE format('ALTER TABLE deck_ignored_cards OWNER TO %I', owner_role);
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'Propriétaire inchangé (pas membre de %) : les GRANT suffisent.', owner_role;
    END;
END
$$;
