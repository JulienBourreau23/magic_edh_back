-- Schéma initial : cache de cartes Scryfall + decks importés.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS cards (
    scryfall_id       UUID PRIMARY KEY,
    oracle_id         UUID NOT NULL,
    name              TEXT NOT NULL,
    lang              TEXT NOT NULL DEFAULT 'en',
    mana_cost         TEXT,
    cmc               NUMERIC,
    type_line         TEXT,
    oracle_text       TEXT,
    colors            TEXT[] NOT NULL DEFAULT '{}',
    color_identity    TEXT[] NOT NULL DEFAULT '{}',
    keywords          TEXT[] NOT NULL DEFAULT '{}',
    power             TEXT,
    toughness         TEXT,
    loyalty           TEXT,
    set_code          TEXT NOT NULL,
    collector_number  TEXT NOT NULL,
    rarity            TEXT,
    legal_commander   BOOLEAN NOT NULL DEFAULT false,
    price_eur         NUMERIC,
    card_faces        JSONB,
    image_uri         TEXT,
    image_downloaded  BOOLEAN NOT NULL DEFAULT false,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS cards_name_trgm_idx ON cards USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS cards_oracle_id_idx ON cards (oracle_id);
CREATE INDEX IF NOT EXISTS cards_name_lower_idx ON cards (lower(name));

CREATE TABLE IF NOT EXISTS decks (
    id                     SERIAL PRIMARY KEY,
    name                   TEXT NOT NULL,
    commander_scryfall_id  UUID REFERENCES cards(scryfall_id),
    partner_scryfall_id    UUID REFERENCES cards(scryfall_id),
    format                 TEXT NOT NULL DEFAULT 'commander',
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS deck_cards (
    deck_id       INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    scryfall_id   UUID NOT NULL REFERENCES cards(scryfall_id),
    quantity      INTEGER NOT NULL DEFAULT 1,
    is_commander  BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (deck_id, scryfall_id)
);

CREATE TABLE IF NOT EXISTS deck_import_issues (
    id        SERIAL PRIMARY KEY,
    deck_id   INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    raw_line  TEXT NOT NULL,
    reason    TEXT NOT NULL
);

-- Une ligne par carte (oracle_id), la moins chère parmi les impressions
-- anglaises non-digitales connues : c'est cette "vue" qu'on utilise pour
-- résoudre les noms importés et afficher les fiches deck.
CREATE OR REPLACE VIEW cards_cheapest AS
SELECT DISTINCT ON (oracle_id) *
FROM cards
ORDER BY oracle_id, (price_eur IS NULL), price_eur ASC, updated_at DESC;
