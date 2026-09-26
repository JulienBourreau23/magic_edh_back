"""
db/upcoming.py — les cartes d'une ou plusieurs extensions, face à la collection.

Une ligne par carte **et par extension** : une carte rééditée dans les precons
et dans le set principal figure dans les deux, parce que c'est dans les deux
produits qu'on la trouve.
"""
from db.core import get_conn


def cards_of_sets(set_codes: list[str]) -> list[dict]:
    if not set_codes:
        return []
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM (
                    SELECT DISTINCT ON (c.set_code, c.oracle_id)
                           c.set_code, c.collector_number, c.oracle_id,
                           c.scryfall_id, c.name, fr.printed_name AS name_fr,
                           c.type_line, c.mana_cost, c.cmc, c.rarity,
                           c.color_identity,
                           -- Une réédition n'a pas encore de prix sur sa nouvelle
                           -- impression, mais s'achète déjà : on retient la
                           -- moins chère du marché, comme partout pour l'achat.
                           COALESCE(cc.price_eur, c.price_eur) AS price_eur,
                           c.image_uri,
                           c.image_downloaded,
                           COALESCE(col.quantity, 0) AS owned_quantity,
                           COALESCE(w.quantity, 0) AS wanted_quantity
                    FROM cards c
                    LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                    LEFT JOIN cards_cheapest cc ON cc.oracle_id = c.oracle_id
                    LEFT JOIN collection col ON col.oracle_id = c.oracle_id
                    LEFT JOIN wishlist w ON w.oracle_id = c.oracle_id
                    WHERE c.set_code = ANY(%s)
                      AND c.type_line NOT LIKE 'Basic Land%%'
                    -- Variantes (showcase, sans bordure) : la version courante,
                    -- celle au plus petit numéro de collection.
                    ORDER BY c.set_code, c.oracle_id,
                             length(c.collector_number), c.collector_number
                ) per_set
                ORDER BY set_code, length(collector_number), collector_number
                """,
                (set_codes,),
            )
            return cur.fetchall()


def prints_per_set(set_codes: list[str]) -> dict[str, int]:
    """Impressions en base, variantes comprises : l'unité de `card_count` chez Scryfall."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT set_code, count(*) AS n FROM cards WHERE set_code = ANY(%s) GROUP BY set_code",
                (set_codes,),
            )
            return {row["set_code"]: row["n"] for row in cur.fetchall()}
