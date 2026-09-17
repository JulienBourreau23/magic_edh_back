"""db/commanders.py — commandants possédés et recommandations EDHREC."""
from db.core import get_conn
from services.card_categories import is_land

# Un commandant : créature légendaire, ou carte disant explicitement qu'elle
# peut l'être (arrière-plans, quelques planeswalkers).
#
# **La légalité dépend du format et ne se déduit pas d'un seul sens.** Geist of
# Saint Traft est légal en multi et banni en duel ; Rofellos, Iona, Leovold,
# Erayo et Griselbrand sont bannis en multi et légaux en duel. Filtrer sur
# `legal_commander` en dur, ce que faisait cette clause, écartait donc les
# seconds d'office et laissait passer le premier jusqu'à l'écran de
# construction.
IS_COMMANDER_TYPE = """
    (c.type_line LIKE 'Legendary Creature%%'
     OR c.oracle_text ILIKE '%%can be your commander%%')
"""

LEGALITY_COLUMNS = {"commander": "legal_commander", "duel": "legal_duel"}

# Colonnes d'une carte recommandée. `owned_quantity` est ce qui rend la suite
# calculable : c'est lui qui dit si la carte coûte quelque chose.
# Mêmes colonnes que les recommandations, moins celles qui viennent d'EDHREC :
# un remplaçant pris dans la collection n'a ni taux d'inclusion ni section.
RECOMMENDATION_COLUMNS_OWNED = """
    c.oracle_id, c.scryfall_id, c.name, fr.printed_name AS name_fr,
    c.type_line, c.mana_cost, c.cmc, c.color_identity, c.price_eur,
    c.image_uri, c.image_downloaded, c.categories, c.game_changer,
    c.edhrec_rank, col.quantity AS owned_quantity
"""

RECOMMENDATION_COLUMNS = """
    c.oracle_id, c.scryfall_id, c.name, fr.printed_name AS name_fr,
    c.type_line, c.mana_cost, c.cmc, c.color_identity, c.price_eur,
    c.image_uri, c.image_downloaded, c.categories, c.game_changer,
    r.section, r.synergy, r.inclusion_rate,
    COALESCE(col.quantity, 0) AS owned_quantity
"""


def owned_commanders(format: str = "commander") -> list[dict]:
    """
    Les commandants possédés et **légaux dans le format demandé**.

    Scryfall ne distingue pas « banni comme commandant » de « banni tout
    court » : un commandant interdit à ce seul titre en Duel Commander y est
    marqué banni intégralement. On est donc plus strict que la réalité — une
    carte jouable dans les 99 se voit refusée — mais jamais plus laxiste, et
    aucune liste illégale n'est proposée.
    """
    legality = LEGALITY_COLUMNS[format]
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
                WHERE c.{legality} AND {IS_COMMANDER_TYPE}
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


def owned_pool(identity: list[str], exclude_oracle_ids: list[str],
               format: str = "commander") -> list[dict]:
    """
    Les cartes **possédées** utilisables avec ce commandant, hors celles déjà
    retenues. Sert à remplacer un achat conseillé par quelque chose qu'on a
    déjà, pour essayer l'archétype avant de dépenser.

    Aucun filtre de prix : ces cartes sont acquises, leur prix ne concerne
    personne. Les terrains sont écartés parce que le noyau visé est non-terrain
    — remplacer un rocher de mana par une forêt ne remplirait pas le créneau.

    Classées par rang EDHREC croissant : à défaut de savoir ce qui va bien avec
    ce commandant précis, le plus joué du format est le moins mauvais repli.
    Les cartes sans rang passent en dernier — une absence de mesure n'est pas
    une bonne note.
    """
    legality = LEGALITY_COLUMNS[format]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {RECOMMENDATION_COLUMNS_OWNED}
                FROM collection col
                JOIN cards_cheapest c ON c.oracle_id = col.oracle_id
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                WHERE c.{legality}
                  AND c.color_identity <@ %(identity)s::text[]
                  AND NOT (c.oracle_id = ANY(%(exclude)s::uuid[]))
                  AND NOT (c.categories @> ARRAY['land'])
                ORDER BY c.edhrec_rank NULLS LAST, c.name
                """,
                {"identity": sorted(identity), "exclude": exclude_oracle_ids},
            )
            return cur.fetchall()
