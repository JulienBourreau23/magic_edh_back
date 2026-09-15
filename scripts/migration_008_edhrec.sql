-- Recommandations EDHREC par commandant.
--
-- Source : les endpoints JSON publics de json.edhrec.com. Ce n'est PAS une API
-- officielle documentée : elle peut changer sans préavis, d'où un script de
-- récupération isolé et une table qu'on peut vider/reconstruire sans risque.
-- Leur robots.txt interdit /deckpreview/ (decks individuels d'utilisateurs) :
-- on ne récupère que les pages commandants, qui sont explicitement sitemapées.
CREATE TABLE IF NOT EXISTS commander_recommendations (
    commander_oracle_id UUID NOT NULL,
    card_oracle_id      UUID NOT NULL,
    section             TEXT NOT NULL,
    -- Score de synergie EDHREC : sur-représentation de la carte dans les decks
    -- de ce commandant par rapport à sa présence générale.
    synergy             NUMERIC,
    -- Part des decks de ce commandant qui jouent la carte (0 à 1).
    inclusion_rate      NUMERIC,
    PRIMARY KEY (commander_oracle_id, card_oracle_id, section)
);

CREATE INDEX IF NOT EXISTS commander_reco_commander_idx
    ON commander_recommendations (commander_oracle_id);

-- Répartition des decks par bracket, telle qu'observée sur EDHREC : dit à quel
-- niveau les joueurs montent réellement ce commandant.
CREATE TABLE IF NOT EXISTS commander_brackets (
    commander_oracle_id UUID PRIMARY KEY,
    counts              JSONB NOT NULL,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
