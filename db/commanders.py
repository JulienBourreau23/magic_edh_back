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

# Être jouable dans les 99 ne suffit pas à être commandant. Le duel bannit
# 27 cartes **comme commandant seulement** (Geist of Saint Traft, Yuriko,
# Minsc & Boo) : Scryfall les publie en `restricted`, et la colonne
# `banned_as_commander_duel` les retient. Le multijoueur n'a pas d'équivalent —
# `restricted:commander` ne renvoie aucune carte — d'où une clause vide de ce
# côté plutôt qu'une colonne toujours fausse.
COMMANDER_ELIGIBILITY = {
    "commander": "TRUE",
    "duel": "NOT c.banned_as_commander_duel",
}

# Colonnes d'une carte recommandée. `owned_quantity` est ce qui rend la suite
# calculable : c'est lui qui dit si la carte coûte quelque chose.
# Mêmes colonnes que les recommandations, moins celles qui viennent d'EDHREC :
# un remplaçant pris dans la collection n'a ni taux d'inclusion ni section.
RECOMMENDATION_COLUMNS_OWNED = """
    c.oracle_id, c.scryfall_id, c.name, fr.printed_name AS name_fr,
    c.type_line, c.mana_cost, c.cmc, c.color_identity, c.price_eur,
    c.image_uri, c.image_downloaded, c.categories, c.game_changer,
    c.edhrec_rank, col.quantity AS owned_quantity,
    COALESCE(w.quantity, 0) AS wanted_quantity
"""

RECOMMENDATION_COLUMNS = """
    c.oracle_id, c.scryfall_id, c.name, fr.printed_name AS name_fr,
    c.type_line, c.mana_cost, c.cmc, c.color_identity, c.price_eur,
    c.image_uri, c.image_downloaded, c.categories, c.game_changer,
    r.section, r.synergy, r.inclusion_rate,
    COALESCE(col.quantity, 0) AS owned_quantity,
    -- Ce qui est déjà cherché : le bouton « + recherche » doit se désactiver
    -- plutôt que d'ajouter un second exemplaire en silence, les quantités
    -- s'additionnant en base.
    COALESCE(w.quantity, 0) AS wanted_quantity
"""


def owned_commanders(format: str = "commander") -> list[dict]:
    """
    Les commandants possédés et **légaux dans le format demandé**.

    Deux interdictions distinctes, que `legal_duel` seul confondait : une carte
    peut être bannie tout court, ou bannie **comme commandant** en restant
    jouable dans les 99. Scryfall publie la seconde sous la valeur `restricted`
    du format duel ; `banned_as_commander_duel` la retient.
    """
    legality = LEGALITY_COLUMNS[format]
    eligibility = COMMANDER_ELIGIBILITY[format]
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
                WHERE c.{legality} AND {eligibility} AND {IS_COMMANDER_TYPE}
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
                LEFT JOIN wishlist w ON w.oracle_id = c.oracle_id
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
                LEFT JOIN wishlist w ON w.oracle_id = c.oracle_id
                WHERE c.{legality}
                  AND c.color_identity <@ %(identity)s::text[]
                  AND NOT (c.oracle_id = ANY(%(exclude)s::uuid[]))
                  AND NOT (c.categories @> ARRAY['land'])
                ORDER BY c.edhrec_rank NULLS LAST, c.name
                """,
                {"identity": sorted(identity), "exclude": exclude_oracle_ids},
            )
            return cur.fetchall()


def synergies_for_deck(commander_oracle_id: str, oracle_ids: list[str],
                       theme_slug: str | None = None) -> list[dict]:
    """
    Les cartes du deck qu'EDHREC voit **particulièrement** associées à ce
    commandant, la plus synergique d'abord.

    La synergie n'est pas la popularité : c'est l'écart entre « jouée dans les
    decks de ce commandant » et « jouée dans les decks de cette couleur en
    général ». Sol Ring est dans tous les decks et n'a donc aucune synergie
    avec personne ; une carte de niche jouée surtout ici en a beaucoup. C'est
    ce qui distingue « bonne carte » de « carte de ce deck-là ».

    Les valeurs négatives sont conservées : une carte moins jouée ici
    qu'ailleurs est une information, pas une erreur — c'est souvent le signe
    qu'elle n'est pas à sa place.

    `theme_slug` bascule la mesure sur l'archétype plutôt que sur le commandant
    entier. La nuance compte pour un deck construit *pour* une stratégie : une
    carte peut être très synergique avec l'Atraxa infect et sans intérêt pour
    l'Atraxa superfriends. Sans thème, on mesure contre l'ensemble des decks du
    commandant, ce qui est la bonne question pour une liste déjà montée.
    """
    if not oracle_ids:
        return []

    if theme_slug:
        source = """
            FROM theme_recommendations r
            JOIN cards_cheapest c ON c.oracle_id = r.card_oracle_id
            LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
            WHERE r.commander_oracle_id = %(commander)s
              AND r.theme_slug = %(theme)s
              AND r.card_oracle_id = ANY(%(cards)s::uuid[])
        """
    else:
        source = """
            FROM commander_recommendations r
            JOIN cards_cheapest c ON c.oracle_id = r.card_oracle_id
            LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
            WHERE r.commander_oracle_id = %(commander)s
              AND r.card_oracle_id = ANY(%(cards)s::uuid[])
        """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT ON (c.oracle_id)
                       c.oracle_id, c.scryfall_id, c.name, fr.printed_name AS name_fr,
                       c.type_line, c.mana_cost, c.image_uri, c.image_downloaded,
                       r.synergy, r.inclusion_rate, r.section
                {source}
                ORDER BY c.oracle_id, r.synergy DESC NULLS LAST
                """,
                {"commander": commander_oracle_id, "cards": oracle_ids, "theme": theme_slug},
            )
            rows = cur.fetchall()

    # Le `DISTINCT ON` impose de trier par carte : le classement par synergie se
    # refait donc ici, une fois les doublons de section écartés.
    rows.sort(key=lambda row: row["synergy"] if row["synergy"] is not None else -99, reverse=True)
    return rows
