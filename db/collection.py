"""
db/collection.py — cartes physiquement possédées.

Indexée par `oracle_id` : la contrainte qui compte pour construire un deck est
« combien d'exemplaires j'ai », pas « quelle édition ». Les terrains de base
n'entrent jamais ici (quantité supposée illimitée).
"""
from psycopg2.extras import execute_values

from db.core import get_conn

COLLECTION_COLUMNS = """
    c.scryfall_id, c.oracle_id, c.name, c.mana_cost, c.cmc, c.type_line,
    c.color_identity, c.rarity, c.price_eur, c.image_uri, c.image_downloaded,
    c.legal_commander, c.legal_duel, c.game_changer, c.categories,
    -- `keywords` ne sert qu'ici : la page collection filtre dessus (vol,
    -- infection...). Les autres écrans n'en ont pas besoin, d'où son absence
    -- des colonnes de deck.
    c.keywords,
    c.produced_mana, c.edhrec_rank, fr.printed_name AS name_fr
"""


def add(entries: list[tuple[str, str, int]]) -> None:
    """entries = [(oracle_id, scryfall_id, quantity)] ; les quantités s'ajoutent."""
    if not entries:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO collection (oracle_id, scryfall_id, quantity) VALUES %s
                ON CONFLICT (oracle_id) DO UPDATE
                SET quantity = collection.quantity + EXCLUDED.quantity,
                    updated_at = now()
                """,
                entries,
            )


def set_quantity(oracle_id: str, quantity: int) -> bool:
    """
    Quantité absolue ; 0 ou moins retire la carte de la collection. Renvoie
    False si la carte n'y était pas : sans ça, un `oracle_id` inconnu ne faisait
    rien du tout et l'interface affichait un succès.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            if quantity <= 0:
                cur.execute("DELETE FROM collection WHERE oracle_id = %s", (oracle_id,))
            else:
                cur.execute(
                    "UPDATE collection SET quantity = %s, updated_at = now() WHERE oracle_id = %s",
                    (quantity, oracle_id),
                )
            return cur.rowcount > 0


def list_all(search: str | None = None) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT col.quantity, col.updated_at, {COLLECTION_COLUMNS}
                FROM collection col
                JOIN cards c ON c.scryfall_id = col.scryfall_id
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                WHERE %(search)s IS NULL
                   OR c.name ILIKE %(pattern)s
                   OR fr.printed_name ILIKE %(pattern)s
                ORDER BY c.name
                """,
                {"search": search, "pattern": f"%{search or ''}%"},
            )
            return cur.fetchall()


def quantities() -> dict[str, int]:
    """{oracle_id: quantité possédée} — base de tout calcul de couverture."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT oracle_id, quantity FROM collection")
            return {str(row["oracle_id"]): row["quantity"] for row in cur.fetchall()}


def stats() -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS distinct_cards,
                       COALESCE(SUM(col.quantity), 0) AS total_cards,
                       COALESCE(SUM(col.quantity * c.price_eur), 0) AS total_value_eur
                FROM collection col
                JOIN cards c ON c.scryfall_id = col.scryfall_id
                """
            )
            row = cur.fetchone()
            return {
                "distinct_cards": row["distinct_cards"],
                "total_cards": int(row["total_cards"]),
                "total_value_eur": round(float(row["total_value_eur"]), 2),
            }


def clear() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM collection")
