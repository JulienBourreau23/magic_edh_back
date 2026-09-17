-- Comment s'exécute un combo, et ce qu'il suppose.
--
-- On stockait ce qu'un combo **produit** (`produces`) mais pas comment on le
-- joue. « Infinite damage » ne dit pas quelle carte lancer en premier ni
-- combien de fois répéter la boucle : sans les étapes, la fiche de deck
-- annonce un combo que le joueur ne sait pas exécuter.
--
-- Commander Spellbook publie les deux champs depuis toujours, on les jetait :
--   description         → les étapes, une par ligne
--   prerequisites       → ce qu'il faut avoir en place (concaténation de
--                         `easyPrerequisites` et `notablePrerequisites`)
--
-- Table entièrement reconstructible : après cette migration, relancer
-- `python scripts/sync_combos.py` pour renseigner les colonnes.
ALTER TABLE combos
    ADD COLUMN IF NOT EXISTS description   TEXT,
    ADD COLUMN IF NOT EXISTS prerequisites TEXT;
