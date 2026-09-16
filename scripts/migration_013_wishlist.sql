-- Liste de recherche : les cartes qu'on envisage d'acheter.
--
-- Même clé que la collection (`oracle_id`) et pour la même raison : ce qu'on
-- cherche, c'est « un Sol Ring », pas une édition précise. C'est aussi ce qui
-- permet à l'achat de basculer d'une table à l'autre sans rien convertir.
--
-- Les terrains de base n'y entrent pas davantage : ils sont supposés
-- disponibles sans limite, donc ils ne se cherchent pas.
CREATE TABLE IF NOT EXISTS wishlist (
    oracle_id   UUID PRIMARY KEY,
    -- L'impression retenue au moment de l'ajout : sert à afficher un visuel et
    -- à reprendre un prix. Même type que dans `collection` (UUID, pas texte) :
    -- c'est ce qui permet de joindre `cards` sans transtypage et de basculer
    -- la ligne d'une table à l'autre telle quelle.
    scryfall_id UUID NOT NULL,
    quantity    INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    -- Pourquoi on la cherche : « remplace Birds of Paradise dans Atraxa ».
    -- Rempli automatiquement quand l'ajout vient d'une liste d'achats.
    note        TEXT,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Mêmes droits que le reste : voir migration_010.
DO $$
DECLARE
    owner_role TEXT;
BEGIN
    SELECT tableowner INTO owner_role FROM pg_tables WHERE tablename = 'cards';
    IF owner_role IS NULL THEN
        RETURN;
    END IF;
    EXECUTE format('GRANT ALL PRIVILEGES ON TABLE wishlist TO %I', owner_role);
    BEGIN
        EXECUTE format('ALTER TABLE wishlist OWNER TO %I', owner_role);
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'Propriétaire inchangé (pas membre de %) : les GRANT suffisent.', owner_role;
    END;
END
$$;
