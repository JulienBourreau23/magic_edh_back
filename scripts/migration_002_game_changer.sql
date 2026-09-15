-- Scryfall expose maintenant un flag officiel "game_changer" (synchronisé avec
-- la liste du Commander Format Panel utilisée par le système de brackets).
ALTER TABLE cards ADD COLUMN IF NOT EXISTS game_changer BOOLEAN NOT NULL DEFAULT false;

-- Recrée la vue pour qu'elle inclue la nouvelle colonne (CREATE VIEW capture
-- la liste de colonnes de `SELECT *` au moment de la création).
CREATE OR REPLACE VIEW cards_cheapest AS
SELECT DISTINCT ON (oracle_id) *
FROM cards
ORDER BY oracle_id, (price_eur IS NULL), price_eur ASC, updated_at DESC;
