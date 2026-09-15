-- `cards_cheapest` était une vue simple : le filtre (lower(name) = ...) ne peut
-- pas descendre sous le DISTINCT ON, donc chaque résolution de nom triait ~41k
-- lignes (~140 ms mesurés, soit ~12 s pour importer un deck de 100 cartes).
-- En vue matérialisée + index, la même résolution devient un index scan.
-- Contrepartie : il faut REFRESH après chaque sync (fait par sync_scryfall.py).
DROP VIEW IF EXISTS cards_cheapest;

CREATE MATERIALIZED VIEW cards_cheapest AS
SELECT DISTINCT ON (oracle_id) *
FROM cards
ORDER BY oracle_id, (price_eur IS NULL), price_eur ASC, updated_at DESC;

CREATE UNIQUE INDEX cards_cheapest_scryfall_id_idx ON cards_cheapest (scryfall_id);
CREATE INDEX cards_cheapest_name_lower_idx ON cards_cheapest (lower(name));
CREATE INDEX cards_cheapest_name_trgm_idx ON cards_cheapest USING gin (name gin_trgm_ops);
CREATE INDEX cards_cheapest_oracle_id_idx ON cards_cheapest (oracle_id);
