"""db/performance.py — le classement mesuré des commandants et de leurs archétypes."""
from psycopg2.extras import execute_values

from db.core import get_conn

COLUMNS = ("commander_oracle_id", "theme_slug", "theme_label", "win_rate", "games",
           "unfinished_rate", "avg_turns", "core_size", "role_gap", "bracket", "panel")


def replace_all(rows: list[dict]) -> int:
    """
    Remplace le classement d'un bloc.

    Écriture en une transaction, après coup : un classement à moitié calculé
    n'aurait aucun sens, et il vaut mieux lire l'ancien que lire un mélange des
    deux — c'est la même règle que le catalogue de combos.
    """
    if not rows:
        return 0
    values = [tuple(row[column] for column in COLUMNS) for row in rows]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM commander_performance")
            execute_values(
                cur,
                f"INSERT INTO commander_performance ({', '.join(COLUMNS)}) VALUES %s",
                values,
            )
    return len(values)


def ranking(limit: int = 10) -> dict:
    """
    Les meilleurs commandants, chacun avec **tous** ses archétypes mesurés.

    Les archétypes voyagent avec le commandant plutôt que dans une seconde
    requête : la question « et les autres archétypes de l'Atraxa ? » est
    précisément celle à laquelle la page doit répondre sans nouveau clic.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.*, c.name, fr.printed_name AS name_fr, c.scryfall_id,
                       c.image_uri, c.image_downloaded, c.color_identity,
                       (SELECT d.id FROM decks d
                         JOIN cards dc ON dc.scryfall_id = d.commander_scryfall_id
                         WHERE dc.oracle_id = p.commander_oracle_id
                         ORDER BY d.id LIMIT 1) AS existing_deck_id
                FROM commander_performance p
                JOIN cards_cheapest c ON c.oracle_id = p.commander_oracle_id
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                WHERE p.theme_slug = ''
                ORDER BY p.win_rate DESC, c.name
                LIMIT %s
                """,
                (limit,),
            )
            commanders = cur.fetchall()
            if not commanders:
                return {"commanders": [], "panel": None, "computed_at": None,
                        "games": None}

            cur.execute(
                """
                SELECT * FROM commander_performance
                WHERE theme_slug <> '' AND commander_oracle_id = ANY(%s::uuid[])
                ORDER BY win_rate DESC
                """,
                ([str(row["commander_oracle_id"]) for row in commanders],),
            )
            themes: dict[str, list[dict]] = {}
            for row in cur.fetchall():
                themes.setdefault(str(row["commander_oracle_id"]), []).append(row)

    return {
        "commanders": [
            {**row, "commander_oracle_id": str(row["commander_oracle_id"]),
             "themes": themes.get(str(row["commander_oracle_id"]), [])}
            for row in commanders
        ],
        "panel": commanders[0]["panel"],
        "computed_at": commanders[0]["computed_at"],
        # Parties jouées par commandant, panel entier confondu : c'est le
        # dénominateur du taux affiché, pas le nombre par affrontement.
        "games": commanders[0]["games"],
    }
