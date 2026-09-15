-- Collection physique. La clé est l'`oracle_id` et non l'impression : on
-- possède « un Sol Ring », l'édition n'a aucune incidence sur la construction
-- d'un deck. `scryfall_id` ne sert que de référence d'affichage (image, prix).
--
-- Les terrains de base n'y figurent pas : ils sont considérés comme disponibles
-- en quantité illimitée et ne génèrent jamais d'achat.
CREATE TABLE IF NOT EXISTS collection (
    oracle_id    UUID PRIMARY KEY,
    scryfall_id  UUID NOT NULL REFERENCES cards(scryfall_id),
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
