-- Définition canonique de `cards_cheapest` (une ligne par oracle_id :
-- l'impression la moins chère). À REJOUER après tout ALTER TABLE cards
-- ADD COLUMN : une vue matérialisée fige sa liste de colonnes à la création,
-- et REFRESH ne la met pas à jour — la nouvelle colonne resterait invisible.
DROP MATERIALIZED VIEW IF EXISTS cards_cheapest;

CREATE MATERIALIZED VIEW cards_cheapest AS
SELECT DISTINCT ON (oracle_id) *
FROM cards
ORDER BY oracle_id, (price_eur IS NULL), price_eur ASC, updated_at DESC;

CREATE UNIQUE INDEX cards_cheapest_scryfall_id_idx ON cards_cheapest (scryfall_id);
CREATE INDEX cards_cheapest_name_lower_idx ON cards_cheapest (lower(name));
CREATE INDEX cards_cheapest_name_trgm_idx ON cards_cheapest USING gin (name gin_trgm_ops);
CREATE INDEX cards_cheapest_oracle_id_idx ON cards_cheapest (oracle_id);
CREATE INDEX cards_cheapest_categories_idx ON cards_cheapest USING gin (categories);
CREATE INDEX cards_cheapest_edhrec_rank_idx ON cards_cheapest (edhrec_rank) WHERE edhrec_rank IS NOT NULL;
