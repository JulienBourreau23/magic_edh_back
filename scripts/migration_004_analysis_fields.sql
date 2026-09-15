-- Champs Scryfall nécessaires à l'analyse déterministe (aucune IA) :
--   legal_duel     : le Duel Commander a sa propre banlist (Sol Ring y est banni)
--   produced_mana  : couleurs réellement produites -> comptage de sources exact
--   edhrec_rank    : popularité (plus petit = plus joué) -> classement des suggestions
ALTER TABLE cards ADD COLUMN IF NOT EXISTS legal_duel    BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE cards ADD COLUMN IF NOT EXISTS produced_mana TEXT[]  NOT NULL DEFAULT '{}';
ALTER TABLE cards ADD COLUMN IF NOT EXISTS edhrec_rank   INTEGER;

-- Sert au filtrage des cartes candidates dans les suggestions.
CREATE INDEX IF NOT EXISTS cards_edhrec_rank_idx ON cards (edhrec_rank) WHERE edhrec_rank IS NOT NULL;
