-- Ce que des vidéos conseillent : des cartes, et des **cycles** de terrains.
--
-- Deux tables reconstructibles : elles ne contiennent que le résultat d'un
-- croisement entre une retranscription et le catalogue. **Aucun texte de
-- retranscription n'est stocké** — seulement des identifiants, des comptes et
-- des horodatages. Ce qui se republierait n'a rien à faire en base ; ce qui est
-- utile, c'est « cette vidéo parle de cette carte à 3 min 12 ».
CREATE TABLE IF NOT EXISTS videos (
    video_id    TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    channel     TEXT,
    url         TEXT NOT NULL,
    language    TEXT,
    -- Vrai quand les sous-titres sont générés automatiquement : ils écorchent
    -- les noms propres, donc une extraction incomplète y est normale.
    auto_generated BOOLEAN NOT NULL DEFAULT TRUE,
    duration_seconds INTEGER,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS video_mentions (
    video_id    TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    -- 'card' : une carte nommée. 'cycle' : une famille de terrains (checkland,
    -- tango...), qui est ce dont parlent réellement les vidéos de manabase.
    kind        TEXT NOT NULL CHECK (kind IN ('card', 'cycle')),
    -- oracle_id pour une carte, clé de cycle pour un cycle.
    key         TEXT NOT NULL,
    mentions    INTEGER NOT NULL DEFAULT 1,
    -- Première occurrence, en secondes : de quoi fabriquer un lien qui ouvre la
    -- vidéo au bon moment.
    first_seconds INTEGER,
    PRIMARY KEY (video_id, kind, key)
);

CREATE INDEX IF NOT EXISTS video_mentions_key_idx ON video_mentions (kind, key);
