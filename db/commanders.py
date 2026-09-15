"""db/commanders.py — commandants possédés et recommandations EDHREC."""
from db.core import get_conn
from services.card_categories import is_land

# Un commandant : créature légendaire, ou carte disant explicitement qu'elle
# peut l'être (arrière-plans, quelques planeswalkers).
IS_COMMANDER_CLAUSE = """
    c.legal_commander
    AND (c.type_line LIKE 'Legendary Creature%%'
         OR c.oracle_text ILIKE '%%can be your commander%%')
"""

# Colonnes d'une carte recommandée. `owned_quantity` est ce qui rend la suite
# calculable : c'est lui qui dit si la carte coûte quelque chose.
RECOMMENDATION_COLUMNS = """
    c.oracle_id, c.scryfall_id, c.name, fr.printed_name AS name_fr,
    c.type_line, c.mana_cost, c.cmc, c.color_identity, c.price_eur,
    c.image_uri, c.image_downloaded, c.categories, c.game_changer,
    r.section, r.synergy, r.inclusion_rate,
    COALESCE(col.quantity, 0) AS owned_quantity
"""


def owned_commanders() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT DISTINCT ON (c.oracle_id)
                       c.oracle_id, c.scryfall_id, c.name, fr.printed_name AS name_fr,
                       c.color_identity, c.image_uri, c.image_downloaded,
                       -- Le commandant compte dans le bracket s'il est
                       -- lui-même Game Changer, et son coût dans la manabase.
                       c.mana_cost, c.categories, c.game_changer,
                       b.counts AS bracket_counts,
                       (SELECT d.id FROM decks d
                         JOIN cards dc ON dc.scryfall_id = d.commander_scryfall_id
                         WHERE dc.oracle_id = c.oracle_id
                         ORDER BY d.id LIMIT 1) AS existing_deck_id
                FROM collection col
                JOIN cards_cheapest c ON c.oracle_id = col.oracle_id
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                LEFT JOIN commander_brackets b ON b.commander_oracle_id = c.oracle_id
                WHERE {IS_COMMANDER_CLAUSE}
                ORDER BY c.oracle_id, c.name
            """)
            return cur.fetchall()


def recommendation_pool(commander_oracle_ids: list[str]) -> dict[str, list[dict]]:
    """
    {oracle_id du commandant: cartes conseillées, les plus jouées d'abord}, en
    une seule requête pour tout le lot — la page « Monter 4 decks » compare tous
    les commandants possédés, un aller-retour par commandant serait du gâchis.

    Une carte peut figurer dans plusieurs sections EDHREC (« Top Cards » et
    « Creatures ») : le `DISTINCT ON` la ramène une seule fois. Les terrains de
    base sont exclus — ils complètent le deck sans jamais rien coûter.
    """
    if not commander_oracle_ids:
        return {}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT ON (r.commander_oracle_id, c.oracle_id)
                       r.commander_oracle_id, {RECOMMENDATION_COLUMNS}
                FROM commander_recommendations r
                JOIN cards_cheapest c ON c.oracle_id = r.card_oracle_id
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                LEFT JOIN collection col ON col.oracle_id = c.oracle_id
                WHERE r.commander_oracle_id = ANY(%(commanders)s::uuid[])
                  AND c.type_line NOT LIKE 'Basic Land%%'
                ORDER BY r.commander_oracle_id, c.oracle_id, r.inclusion_rate DESC NULLS LAST
                """,
                {"commanders": commander_oracle_ids},
            )
            rows = cur.fetchall()

    pools: dict[str, list[dict]] = {}
    for row in rows:
        pools.setdefault(str(row["commander_oracle_id"]), []).append(row)
    for cards in pools.values():
        cards.sort(key=lambda card: card["inclusion_rate"] or 0, reverse=True)
    return pools


def recommendations(commander_oracle_id: str, limit: int,
                    exclude_lands: bool = False) -> list[dict]:
    """
    Cartes conseillées pour ce commandant, les plus jouées d'abord.

    `exclude_lands` retire aussi les terrains non-basiques (duales, fetchlands,
    terrains utilitaires) : un noyau annoncé « non-terrain » qui les compte
    fausse à la fois la couverture et le budget, et ce sont justement les
    cartes les plus chères de la liste.
    """
    pool = recommendation_pool([commander_oracle_id]).get(commander_oracle_id, [])
    if exclude_lands:
        pool = [card for card in pool if not is_land(card)]
    return pool[:limit]


def has_data() -> bool:
    """Les recommandations viennent d'un script séparé : elles peuvent manquer."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT EXISTS (SELECT 1 FROM commander_recommendations)")
            return cur.fetchone()["exists"]
