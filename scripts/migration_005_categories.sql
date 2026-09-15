-- Rôles de la carte (ramp, draw, removal...) calculés par
-- services/card_categories.classify() au moment du sync. Stockés plutôt que
-- recalculés : ça rend le filtrage des cartes candidates possible en SQL pour
-- les suggestions, sans dupliquer les règles de classification côté requête.
ALTER TABLE cards ADD COLUMN IF NOT EXISTS categories TEXT[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS cards_categories_idx ON cards USING gin (categories);
