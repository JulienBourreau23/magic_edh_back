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

# Archétype de repli, toujours présent : l'agrégat de tous les decks du
# commandant, stratégies confondues. Il existe pour deux raisons. D'abord parce
# qu'un commandant peu joué n'a aucun thème au-dessus du plancher d'échantillon
# (Vendilion Clique : son meilleur archétype tient sur 27 decks) et resterait
# inconstruisible. Ensuite parce qu'à ces effectifs-là, l'agrégat est
# **statistiquement meilleur** qu'un thème : plus de decks, moins de bruit.
# Le préfixe `_` ne peut pas entrer en collision avec un slug EDHREC.
ALL_THEMES_SLUG = "_all"
ALL_THEMES_LABEL = "Toutes stratégies"


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
            # L'agrégat n'a pas de lignes dans `theme_recommendations` : son
            # vivier, ce sont les recommandations du commandant. Sans ce
            # deuxième volet, il s'afficherait à « 0 / 0 carte ».
            cur.execute(
                f"""
                SELECT %(all_slug)s AS theme_slug,
                       count(*) AS cards,
                       count(col.oracle_id) AS owned
                FROM (SELECT DISTINCT card_oracle_id FROM commander_recommendations
                      WHERE commander_oracle_id = %(commander)s) r
                JOIN cards_cheapest c ON c.oracle_id = r.card_oracle_id
                LEFT JOIN collection col ON col.oracle_id = r.card_oracle_id
                WHERE c.{legality}
                """,
                {"commander": commander_oracle_id, "all_slug": ALL_THEMES_SLUG},
            )
            coverage = {row["theme_slug"]: dict(row) for row in cur.fetchall()}

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
            coverage.update({row["theme_slug"]: dict(row) for row in cur.fetchall()})
            return coverage


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
                       COALESCE(w.quantity, 0) AS wanted_quantity,
                       fr.printed_name AS name_fr
                FROM rates
                JOIN cards_cheapest c ON c.oracle_id = rates.oracle_id
                LEFT JOIN commander_rates ON commander_rates.oracle_id = rates.oracle_id
                LEFT JOIN collection col ON col.oracle_id = rates.oracle_id
                LEFT JOIN wishlist w ON w.oracle_id = rates.oracle_id
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


# Le nombre de non-terrains d'un deck Commander, et la somme des histogrammes
# de courbe publiés par EDHREC : c'est sur cet effectif qu'on compare.
NONLAND_SLOTS = 63


def best_theme_by_commander(format: str) -> dict[str, dict]:
    """
    Pour chaque commandant possédé, l'archétype qu'on peut monter le plus près
    de la référence **avec la collection**.

    Le score n'est pas un taux de recouvrement (« combien de cartes de la liste
    j'ai »), qui a deux défauts : il compare des ratios alors que ce qui compte
    est un compte — il faut 63 non-terrains, pas un pourcentage — et il met une
    pièce maîtresse jouée dans 80 % des decks au même rang qu'une carte de
    niche jouée dans 5 %.

    On compare donc **deux decks** : celui qu'on peut bâtir avec la collection
    (les 63 meilleures cartes possédées) et celui de référence (les 63
    meilleures, possédées ou non), chacun mesuré par la somme des taux
    d'inclusion de ses cartes.

    Le classement se fait sur la valeur **absolue** du premier, pas sur le
    rapport des deux. Le rapport est trompeur pour choisir : l'agrégat « toutes
    stratégies » a une référence plus molle qu'un archétype marqué — ses cartes
    sont jouées dans moins de decks chacune — donc on l'approche plus
    facilement. Sur Atraxa, la collection atteint 99 % de l'agrégat et 93 % de
    l'infect, alors que le deck infect porte bien plus de consensus (29,7
    contre 22,2). Le rapport reste renvoyé, pour dire à quel point on est loin
    de l'optimum de cet archétype-là.

    Une seule requête pour tous les commandants : la page en affiche une
    trentaine, et trente allers-retours pour trier une grille seraient absurdes.
    """
    legality = LEGALITY_COLUMNS[format]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH cartes AS (
                    -- Les cartes de chaque archétype, plus celles de l'agrégat,
                    -- avec leur taux d'inclusion et le fait qu'on les possède.
                    SELECT t.commander_oracle_id, t.theme_slug, t.card_oracle_id,
                           max(t.inclusion_rate) AS rate,
                           bool_or(col.oracle_id IS NOT NULL) AS owned
                    FROM theme_recommendations t
                    JOIN cards_cheapest c ON c.oracle_id = t.card_oracle_id
                    LEFT JOIN collection col ON col.oracle_id = t.card_oracle_id
                    WHERE c.{legality} AND c.type_line NOT LIKE 'Basic Land%%'
                    GROUP BY 1, 2, 3
                  UNION ALL
                    SELECT r.commander_oracle_id, %(all_slug)s, r.card_oracle_id,
                           max(r.inclusion_rate),
                           bool_or(col.oracle_id IS NOT NULL)
                    FROM commander_recommendations r
                    JOIN cards_cheapest c ON c.oracle_id = r.card_oracle_id
                    LEFT JOIN collection col ON col.oracle_id = r.card_oracle_id
                    WHERE c.{legality} AND c.type_line NOT LIKE 'Basic Land%%'
                    GROUP BY 1, 2, 3
                ),
                reference AS (
                    SELECT commander_oracle_id, theme_slug, sum(rate) AS ideal
                    FROM (SELECT *, row_number() OVER (
                              PARTITION BY commander_oracle_id, theme_slug
                              ORDER BY rate DESC NULLS LAST) AS rang
                          FROM cartes) c
                    WHERE rang <= %(slots)s
                    GROUP BY 1, 2
                ),
                possede AS (
                    SELECT commander_oracle_id, theme_slug,
                           sum(rate) AS reachable, count(*) AS owned_cards
                    FROM (SELECT *, row_number() OVER (
                              PARTITION BY commander_oracle_id, theme_slug
                              ORDER BY rate DESC NULLS LAST) AS rang
                          FROM cartes WHERE owned) c
                    WHERE rang <= %(slots)s
                    GROUP BY 1, 2
                ),
                classe AS (
                    SELECT reference.commander_oracle_id, reference.theme_slug,
                           th.label, th.deck_count,
                           COALESCE(possede.owned_cards, 0) AS owned_cards,
                           COALESCE(possede.reachable, 0) / NULLIF(reference.ideal, 0) AS score,
                           COALESCE(possede.reachable, 0) AS reachable,
                           row_number() OVER (
                               PARTITION BY reference.commander_oracle_id
                               ORDER BY COALESCE(possede.reachable, 0) DESC NULLS LAST,
                                        th.deck_count DESC NULLS LAST
                           ) AS rang
                    FROM reference
                    LEFT JOIN possede
                           ON possede.commander_oracle_id = reference.commander_oracle_id
                          AND possede.theme_slug = reference.theme_slug
                    JOIN commander_themes th
                      ON th.commander_oracle_id = reference.commander_oracle_id
                     AND th.slug = reference.theme_slug
                )
                SELECT commander_oracle_id, theme_slug, label, deck_count,
                       owned_cards, score, reachable
                FROM classe WHERE rang = 1
                """,
                {"all_slug": ALL_THEMES_SLUG, "slots": NONLAND_SLOTS},
            )
            return {str(row["commander_oracle_id"]): dict(row) for row in cur.fetchall()}
