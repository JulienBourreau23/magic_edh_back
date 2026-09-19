"""db/videos.py — ce que des vidéos conseillent, par carte et par cycle de terrains."""
from psycopg2.extras import execute_values

from db.core import get_conn


def replace_video(video: dict, mentions: list[dict]) -> int:
    """
    Enregistre une vidéo et ses mentions, en remplaçant les précédentes.

    Réimporter la même vidéo doit donner le même état, pas des mentions
    empilées : c'est un constat refait, pas un ajout. D'où le remplacement
    plutôt qu'un `quantity + 1` — contrairement à la collection, où réimporter
    veut dire « j'en ai un de plus ».
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO videos (video_id, title, channel, url, language,
                                    auto_generated, duration_seconds, fetched_at)
                VALUES (%(video_id)s, %(title)s, %(channel)s, %(url)s, %(language)s,
                        %(auto_generated)s, %(duration_seconds)s, now())
                ON CONFLICT (video_id) DO UPDATE SET
                    title = EXCLUDED.title, channel = EXCLUDED.channel,
                    url = EXCLUDED.url, language = EXCLUDED.language,
                    auto_generated = EXCLUDED.auto_generated,
                    duration_seconds = EXCLUDED.duration_seconds,
                    fetched_at = now()
                """,
                video,
            )
            cur.execute("DELETE FROM video_mentions WHERE video_id = %s", (video["video_id"],))
            if mentions:
                execute_values(
                    cur,
                    "INSERT INTO video_mentions (video_id, kind, key, mentions, first_seconds)"
                    " VALUES %s",
                    [(video["video_id"], m["kind"], m["key"], m["mentions"], m["first_seconds"])
                     for m in mentions],
                )
            return len(mentions)


def list_videos() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT v.*,
                       count(*) FILTER (WHERE m.kind = 'card') AS cards,
                       count(*) FILTER (WHERE m.kind = 'cycle') AS cycles
                FROM videos v
                LEFT JOIN video_mentions m ON m.video_id = v.video_id
                GROUP BY v.video_id
                ORDER BY v.fetched_at DESC
                """
            )
            return cur.fetchall()


def mentions_by_key(kind: str) -> dict[str, list[dict]]:
    """{clé: vidéos qui en parlent}. Sert à marquer « conseillé en vidéo »."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.key, m.mentions, m.first_seconds,
                       v.video_id, v.title, v.channel, v.url
                FROM video_mentions m
                JOIN videos v ON v.video_id = m.video_id
                WHERE m.kind = %s
                ORDER BY m.mentions DESC
                """,
                (kind,),
            )
            par_cle: dict[str, list[dict]] = {}
            for row in cur.fetchall():
                par_cle.setdefault(row["key"], []).append(row)
            return par_cle


def delete_video(video_id: str) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM videos WHERE video_id = %s", (video_id,))
            return cur.rowcount > 0
