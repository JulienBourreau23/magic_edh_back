-- Archiver un deck : le sortir de la liste courante sans le supprimer.
--
-- Une date plutôt qu'un booléen : « quand l'ai-je rangé » est une information
-- qu'on veut lire sur la page d'archives, et `NULL` dit « actif » sans avoir à
-- maintenir deux colonnes cohérentes.
ALTER TABLE decks ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

-- La liste courante filtre là-dessus à chaque chargement.
CREATE INDEX IF NOT EXISTS decks_archived_at_idx ON decks (archived_at);
