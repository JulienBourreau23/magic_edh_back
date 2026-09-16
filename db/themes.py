"""
db/themes.py — archétypes EDHREC et vivier de cartes pour la construction
compétitive.

Le vivier est bâti en trois cercles, du plus pertinent au plus général :

1. les cartes jouées **dans ce thème** avec ce commandant (taux d'inclusion
   mesuré sur ces decks-là) ;
2. celles jouées avec le commandant toutes stratégies confondues ;
3. le reste de la collection, à identité et légalité compatibles.

Sans le troisième cercle, une collection qui ne recoupe pas EDHREC donnerait un
deck incomplet ; sans les deux premiers, on ne saurait pas ce qui est bon.
"""
from db.core import get_conn

# Le nom de colonne est interpolé dans le SQL : il vient de cette table, jamais
# d'une valeur reçue du client.
LEGALITY_COLUMNS = {"commander": "legal_commander", "duel": "legal_duel"}


def themes_for(commander_oracle_id: str) -> list[dict]:
    """Les archétypes du commandant, du plus joué au moins joué."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT slug, label, deck_count, type_counts, mana_curve
                FROM commander_themes
                WHERE commander_oracle_id = %s
                ORDER BY deck_count DESC
                """,
                (commander_oracle_id,),
            )
            return cur.fetchall()


def theme_coverage(commander_oracle_id: str, format: str) -> dict[str, dict]:
    """
    Par thème : combien de ses cartes légales sont déjà dans la collection.

    C'est le chiffre qui rend les archétypes comparables entre eux — « celui
    que je peux monter » plutôt que « celui qui est le plus joué ».
    """
    legality = LEGALITY_COLUMNS[format]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT t.theme_slug,
                       count(*) AS cards,
                       count(col.oracle_id) AS owned
                FROM theme_recommendations t
                JOIN cards_cheapest c ON c.oracle_id = t.card_oracle_id
                LEFT JOIN collection col ON col.oracle_id = t.card_oracle_id
                WHERE t.commander_oracle_id = %s
                  AND c.{legality}
                GROUP BY t.theme_slug
                """,
                (commander_oracle_id,),
            )
            return {row["theme_slug"]: dict(row) for row in cur.fetchall()}


def build_pool(commander_oracle_id: str, theme_slug: str, format: str,
               identity: list[str]) -> list[dict]:
    """
    Les cartes jouables pour ce commandant, ce thème et ce format.

    Trois filtres sont **durs**, jamais négociables : la légalité du format
    (c'est la banlist, Duel Commander bannit ce que le multi autorise),
    l'identité de couleur, et l'exclusion des terrains de base — comptés à part
    parce qu'ils ne coûtent rien et ne se choisissent pas.

    `inclusion_rate` vient du thème quand la carte y figure, du commandant
    sinon, et vaut 0 pour une carte seulement possédée : le tri qui s'appuie
    dessus classe donc naturellement le mesuré avant le supposé.
    """
    legality = LEGALITY_COLUMNS[format]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH candidate AS (
                    SELECT card_oracle_id AS oracle_id, max(inclusion_rate) AS theme_rate
                    FROM theme_recommendations
                    WHERE commander_oracle_id = %(commander)s AND theme_slug = %(theme)s
                    GROUP BY card_oracle_id
                  UNION
                    SELECT card_oracle_id, NULL
                    FROM commander_recommendations
                    WHERE commander_oracle_id = %(commander)s
                  UNION
                    SELECT oracle_id, NULL FROM collection
                ),
                rates AS (
                    SELECT oracle_id, max(theme_rate) AS theme_rate FROM candidate GROUP BY oracle_id
                ),
                commander_rates AS (
                    SELECT card_oracle_id AS oracle_id, max(inclusion_rate) AS commander_rate
                    FROM commander_recommendations
                    WHERE commander_oracle_id = %(commander)s
                    GROUP BY card_oracle_id
                )
                SELECT c.*,
                       COALESCE(rates.theme_rate, 0)::float AS theme_rate,
                       COALESCE(commander_rates.commander_rate, 0)::float AS commander_rate,
                       COALESCE(col.quantity, 0) AS owned_quantity,
                       fr.printed_name AS name_fr
                FROM rates
                JOIN cards_cheapest c ON c.oracle_id = rates.oracle_id
                LEFT JOIN commander_rates ON commander_rates.oracle_id = rates.oracle_id
                LEFT JOIN collection col ON col.oracle_id = rates.oracle_id
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                WHERE c.{legality}
                  AND c.color_identity <@ %(identity)s::text[]
                  AND c.oracle_id <> %(commander_oracle)s::uuid
                  AND c.type_line NOT LIKE 'Basic Land%%'
                """,
                {"commander": commander_oracle_id, "theme": theme_slug,
                 "identity": identity, "commander_oracle": commander_oracle_id},
            )
            return cur.fetchall()
