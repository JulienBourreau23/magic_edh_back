-- « Banni comme commandant » en Duel Commander.
--
-- Le duel distingue deux interdictions que `legal_duel` confondait :
--   * bannie tout court      → Scryfall : legalities.duel = "banned"   (~250 cartes)
--   * bannie comme COMMANDANT → Scryfall : legalities.duel = "restricted" (27 cartes)
--
-- Les 27 secondes sont parfaitement jouables dans les 99 : Geist of Saint
-- Traft, Yuriko, Minsc & Boo. Le sync les traitait comme bannies parce qu'il
-- testait `duel == "legal"`, ce qui écartait `restricted` — l'information
-- arrivait à chaque synchronisation et était jetée.
--
-- Pas d'équivalent en multijoueur : `restricted:commander` ne renvoie aucune
-- carte sur Scryfall, le Commander n'a plus de liste « banni comme commandant ».
-- Une colonne symétrique serait donc toujours fausse, et n'est pas créée.
ALTER TABLE cards
    ADD COLUMN IF NOT EXISTS banned_as_commander_duel BOOLEAN NOT NULL DEFAULT false;

-- **Rejouer `rebuild_cheapest_view.sql` après cette migration.** Une vue
-- matérialisée fige sa liste de colonnes à la création et `REFRESH` ne
-- l'élargit pas : sans reconstruction, la colonne resterait invisible depuis
-- `cards_cheapest`, d'où tout le reste du projet la lit.
--
-- Puis relancer `sync_scryfall.py` : la colonne naît à `false` partout, et
-- seule une synchronisation complète peut la renseigner depuis Scryfall.
