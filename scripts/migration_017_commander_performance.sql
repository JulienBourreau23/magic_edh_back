-- Performance mesurée d'un commandant, et de chacun de ses archétypes, contre
-- un panel de decks. Table entièrement reconstructible : elle ne contient que
-- le résultat d'un calcul (scripts/rank_commanders.py), jamais une saisie.
--
-- `theme_slug = ''` est la ligne « sans archétype » : le meilleur deck qu'on
-- puisse monter pour ce commandant avec la collection, toutes stratégies
-- confondues. Les autres lignes sont ses archétypes EDHREC.
CREATE TABLE IF NOT EXISTS commander_performance (
    commander_oracle_id UUID        NOT NULL,
    theme_slug          TEXT        NOT NULL DEFAULT '',
    theme_label         TEXT,
    -- Part des parties gagnées, tous adversaires du panel confondus. Les
    -- parties non conclues au bout de 25 tours comptent dans le dénominateur :
    -- ne pas savoir finir est un résultat, pas une absence de résultat.
    win_rate            REAL        NOT NULL,
    games               INTEGER     NOT NULL,
    unfinished_rate     REAL        NOT NULL,
    avg_turns           REAL,
    -- État du deck mesuré : un noyau incomplet explique un mauvais score sans
    -- rien dire du commandant.
    core_size           INTEGER     NOT NULL,
    role_gap            INTEGER     NOT NULL,
    bracket             INTEGER,
    -- Le panel affronté, en clair : un score ne se compare qu'à panel égal.
    panel               TEXT        NOT NULL,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (commander_oracle_id, theme_slug)
);

CREATE INDEX IF NOT EXISTS commander_performance_win_rate_idx
    ON commander_performance (win_rate DESC);
