-- Noms français des cartes, pour pouvoir coller une decklist en français.
--
-- Volontairement une simple table d'alias et non des cartes françaises
-- complètes : `printed_name` (le nom imprimé sur la carte française) partage
-- l'`oracle_id` de la version anglaise, qui reste la donnée canonique (prix,
-- légalité, rôles, Game Changers). Importer les cartes françaises en entier
-- dupliquerait tout ça pour rien.
--
-- Toutes les cartes n'ont pas d'impression française (vieux sets, Secret
-- Lairs, certains produits Commander) : l'absence d'alias est normale.
CREATE TABLE IF NOT EXISTS card_names_fr (
    oracle_id     UUID PRIMARY KEY,
    printed_name  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS card_names_fr_lower_idx ON card_names_fr (lower(printed_name));
CREATE INDEX IF NOT EXISTS card_names_fr_trgm_idx ON card_names_fr USING gin (printed_name gin_trgm_ops);
