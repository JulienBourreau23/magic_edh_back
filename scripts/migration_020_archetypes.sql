-- Les archétypes du format, tels qu'EDHREC les recense — et non ceux d'un
-- commandant précis.
--
-- `commander_themes` répond déjà à « que monte-t-on derrière Atraxa ». Ces
-- tables-ci répondent à l'inverse : « qu'est-ce que le superfriends, qui le
-- pilote, et qu'est-ce que ça me coûterait ». La source est la même famille
-- d'endpoints (`json.edhrec.com/pages/tags/<slug>.json`, sitemapée donc
-- voulue), mais la question est différente et la clé aussi : un archétype seul,
-- sans commandant. Les joindre aux tables existantes aurait obligé à inventer
-- un commandant fictif pour porter les lignes.
--
-- Les trois tables sont **entièrement reconstructibles** par
-- `python scripts/sync_archetypes.py` : rien ici n'est saisi à la main, et une
-- reconstruction repart de zéro archétype par archétype.

CREATE TABLE IF NOT EXISTS archetypes (
    slug        TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    -- Decks recensés par EDHREC sur cet archétype, tous commandants confondus.
    -- C'est la popularité de la stratégie dans le format, à ne pas confondre
    -- avec le `deck_count` de `commander_themes`, qui compte les decks d'un
    -- seul commandant.
    deck_count  INTEGER NOT NULL DEFAULT 0,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Les cartes de l'archétype. Une carte peut figurer dans plusieurs sections
-- (« Top Cards » et « Creatures »), comme pour les recommandations par
-- commandant : la section fait partie de la clé.
CREATE TABLE IF NOT EXISTS archetype_cards (
    archetype_slug  TEXT NOT NULL REFERENCES archetypes(slug) ON DELETE CASCADE,
    card_oracle_id  UUID NOT NULL,
    section         TEXT NOT NULL,
    -- Écart entre « jouée dans cet archétype » et « jouée dans cette couleur
    -- en général ». Négative pour une carte moins jouée ici qu'ailleurs : c'est
    -- une information, pas une erreur.
    synergy         NUMERIC,
    -- `num_decks / potential_decks` : la part des decks **qui pouvaient la
    -- jouer** (identité de couleur comprise) et qui la jouent. C'est ce qui
    -- rend comparables une carte mono-blanche et une carte incolore.
    inclusion_rate  NUMERIC,
    PRIMARY KEY (archetype_slug, card_oracle_id, section)
);

-- Les commandants qui pilotent l'archétype, possédés ou non — c'est tout
-- l'intérêt de cette page : elle parle aussi de ce qu'on n'a pas.
CREATE TABLE IF NOT EXISTS archetype_commanders (
    archetype_slug      TEXT NOT NULL REFERENCES archetypes(slug) ON DELETE CASCADE,
    commander_oracle_id UUID NOT NULL,
    -- Decks de ce commandant dans cet archétype, et decks de l'archétype en
    -- tout. Le rapport dit quelle part de la stratégie ce commandant porte —
    -- une mesure qui n'a rien à voir avec le taux d'inclusion d'une carte,
    -- d'où une table séparée plutôt qu'une section de `archetype_cards`.
    num_decks           INTEGER NOT NULL DEFAULT 0,
    potential_decks     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (archetype_slug, commander_oracle_id)
);

CREATE INDEX IF NOT EXISTS archetype_cards_card_idx
    ON archetype_cards (card_oracle_id);
CREATE INDEX IF NOT EXISTS archetype_commanders_commander_idx
    ON archetype_commanders (commander_oracle_id);
