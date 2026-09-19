"""
db/archetypes.py — les archétypes du format, et ce qu'ils coûteraient.

La question de ces requêtes n'est pas celle de `db/themes.py`. Là-bas on part
d'un commandant possédé et on demande ce qu'on monte derrière lui ; ici on part
d'une stratégie et on demande **qui la pilote**, y compris des commandants
qu'on ne possède pas. Une page de découverte qui ne parlerait que de la
collection ne ferait rien découvrir.

Le noyau retenu pour chiffrer un montage est **non-terrain** et limité à
`CORE_SLOTS` cartes, exactement comme partout ailleurs dans le projet : la
manabase ne s'achète pas (elle se calcule, terrains de base compris), et
compter les terrains dans le noyau ferait passer les cartes les plus chères de
la liste pour des cartes indispensables.
"""
from db.core import get_conn
from services.suggestions import DEFAULT_MAX_PRICE_EUR

LEGALITY_COLUMNS = {"commander": "legal_commander", "duel": "legal_duel"}

# Le même effectif que le reste du projet : 63 non-terrains, 36 terrains, le
# commandant. Deux repères identiques valent mieux que deux repères proches.
CORE_SLOTS = 63

# Les sections d'EDHREC mises en avant dans l'article, dans cet ordre. Le reste
# (Creatures, Instants...) est renvoyé aussi, mais sert de catalogue plutôt que
# de démonstration.
HEADLINE_SECTIONS = ("High Synergy Cards", "Top Cards", "Game Changers")

CARD_COLUMNS = """
    c.oracle_id, c.scryfall_id, c.name, fr.printed_name AS name_fr,
    c.type_line, c.mana_cost, c.cmc, c.color_identity, c.price_eur,
    c.image_uri, c.image_downloaded, c.categories, c.game_changer,
    c.edhrec_rank,
    COALESCE(col.quantity, 0) AS owned_quantity,
    COALESCE(w.quantity, 0) AS wanted_quantity
"""


def list_all(format: str = "commander") -> list[dict]:
    """
    Le catalogue, du plus joué au moins joué.

    **Aucun taux de couverture ici, et c'est délibéré.** Les cartes d'un
    archétype couvrent toutes les couleurs — un seul deck ne pourrait jamais
    les jouer ensemble — donc « j'ai 40 des 63 meilleures cartes du tokens » ne
    dit rien de constructible. Le seul chiffre honnête à ce niveau est le
    nombre de commandants de l'archétype **qu'on possède** : c'est ce qui dit
    si on peut commencer. Le coût réel se calcule commandant par commandant, une
    fois l'identité de couleur connue (`commanders_for`).
    """
    legality = LEGALITY_COLUMNS[format]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT a.slug, a.label, a.deck_count,
                       count(ac.commander_oracle_id) AS commanders,
                       count(col.oracle_id) AS owned_commanders
                FROM archetypes a
                LEFT JOIN archetype_commanders ac ON ac.archetype_slug = a.slug
                LEFT JOIN cards_cheapest c ON c.oracle_id = ac.commander_oracle_id
                                          AND c.{legality}
                LEFT JOIN collection col ON col.oracle_id = c.oracle_id
                GROUP BY a.slug, a.label, a.deck_count
                ORDER BY a.deck_count DESC
                """
            )
            return cur.fetchall()


def get(slug: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT slug, label, deck_count, fetched_at "
                        "FROM archetypes WHERE slug = %s", (slug,))
            return cur.fetchone()


def commanders_for(slug: str, format: str = "commander", limit: int = 16,
                   max_price: float = DEFAULT_MAX_PRICE_EUR) -> list[dict]:
    """
    Les commandants de l'archétype, et **ce qu'il en coûterait de monter le
    deck derrière chacun**.

    C'est la réponse à « est-ce que je peux le monter », et elle n'existe qu'à
    ce niveau : le coût dépend du commandant, pas de l'archétype. Le
    superfriends derrière un commandant qu'on possède déjà et celui derrière un
    commandant à 40 € qu'on n'a pas ne sont pas la même dépense.

    Trois précautions :

    - **l'identité de couleur filtre le noyau** (`<@`). Sans elle, on
      chiffrerait un deck impossible : les 63 meilleures cartes d'un archétype
      sont réparties sur les cinq couleurs ;
    - **le commandant lui-même n'entre pas dans le noyau**, mais son prix est
      renvoyé à côté quand il n'est pas possédé — c'est un achat, et souvent le
      plus gros ;
    - **une carte sans prix n'est pas une carte gratuite.** Elle est comptée à
      part (`unknown_price`) plutôt qu'ajoutée pour zéro, comme partout dans le
      projet.

    Le total est doublé d'un compte au-dessus du plafond de prix
    (`over_cap_*`), parce que « 320 € » ne veut pas dire la même chose selon
    qu'il s'agit de soixante cartes à cinq euros ou de trois pièces à cent.
    C'est cette nuance-là qui répond à « gros investissement ou non », et elle
    disparaîtrait dans un total unique.
    """
    legality = LEGALITY_COLUMNS[format]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH commandants AS (
                    SELECT ac.commander_oracle_id, ac.num_decks, ac.potential_decks,
                           c.color_identity
                    FROM archetype_commanders ac
                    JOIN cards_cheapest c ON c.oracle_id = ac.commander_oracle_id
                    WHERE ac.archetype_slug = %(slug)s AND c.{legality}
                    ORDER BY ac.num_decks DESC
                    LIMIT %(limit)s
                ),
                noyau AS (
                    SELECT ac.card_oracle_id, max(ac.inclusion_rate) AS rate,
                           c.color_identity, c.price_eur,
                           (col.oracle_id IS NOT NULL) AS owned
                    FROM archetype_cards ac
                    JOIN cards_cheapest c ON c.oracle_id = ac.card_oracle_id
                    LEFT JOIN collection col ON col.oracle_id = ac.card_oracle_id
                    WHERE ac.archetype_slug = %(slug)s
                      AND c.{legality}
                      AND c.type_line NOT LIKE 'Basic Land%%'
                    GROUP BY ac.card_oracle_id, c.color_identity, c.price_eur, col.oracle_id
                ),
                classe AS (
                    SELECT commandants.commander_oracle_id, noyau.owned, noyau.price_eur,
                           row_number() OVER (
                               PARTITION BY commandants.commander_oracle_id
                               ORDER BY noyau.rate DESC NULLS LAST) AS rang
                    FROM commandants
                    JOIN noyau ON noyau.color_identity <@ commandants.color_identity
                              AND noyau.card_oracle_id <> commandants.commander_oracle_id
                ),
                couverture AS (
                    SELECT commander_oracle_id,
                           count(*) AS core_size,
                           count(*) FILTER (WHERE owned) AS core_owned,
                           COALESCE(sum(price_eur) FILTER (WHERE NOT owned), 0) AS missing_price,
                           count(*) FILTER (WHERE NOT owned AND price_eur IS NULL)
                               AS unknown_price,
                           count(*) FILTER (WHERE NOT owned AND price_eur > %(cap)s)
                               AS over_cap_cards,
                           COALESCE(sum(price_eur)
                               FILTER (WHERE NOT owned AND price_eur > %(cap)s), 0)
                               AS over_cap_price
                    FROM classe WHERE rang <= %(slots)s
                    GROUP BY commander_oracle_id
                )
                SELECT {CARD_COLUMNS},
                       commandants.num_decks, commandants.potential_decks,
                       COALESCE(couverture.core_size, 0) AS core_size,
                       COALESCE(couverture.core_owned, 0) AS core_owned,
                       COALESCE(couverture.missing_price, 0)::float AS missing_price,
                       COALESCE(couverture.unknown_price, 0) AS unknown_price,
                       COALESCE(couverture.over_cap_cards, 0) AS over_cap_cards,
                       COALESCE(couverture.over_cap_price, 0)::float AS over_cap_price
                FROM commandants
                JOIN cards_cheapest c ON c.oracle_id = commandants.commander_oracle_id
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                LEFT JOIN collection col ON col.oracle_id = c.oracle_id
                LEFT JOIN wishlist w ON w.oracle_id = c.oracle_id
                LEFT JOIN couverture
                       ON couverture.commander_oracle_id = commandants.commander_oracle_id
                ORDER BY commandants.num_decks DESC
                """,
                {"slug": slug, "limit": limit, "slots": CORE_SLOTS, "cap": max_price},
            )
            return cur.fetchall()


def cards_for(slug: str, format: str = "commander") -> list[dict]:
    """
    Les cartes de l'archétype, section par section.

    Une carte peut figurer dans deux sections (« Top Cards » et « Creatures ») :
    elle est renvoyée une fois par section, comme EDHREC l'affiche. Le
    `DISTINCT ON` habituel serait ici une perte d'information — c'est justement
    la section qui dit pourquoi la carte est citée.

    Les terrains de base sont écartés : ils ne s'achètent pas et ne
    caractérisent aucune stratégie.
    """
    legality = LEGALITY_COLUMNS[format]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {CARD_COLUMNS},
                       ac.section, ac.synergy::float, ac.inclusion_rate::float
                FROM archetype_cards ac
                JOIN cards_cheapest c ON c.oracle_id = ac.card_oracle_id
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                LEFT JOIN collection col ON col.oracle_id = c.oracle_id
                LEFT JOIN wishlist w ON w.oracle_id = c.oracle_id
                WHERE ac.archetype_slug = %(slug)s
                  AND c.{legality}
                  AND c.type_line NOT LIKE 'Basic Land%%'
                ORDER BY ac.section, ac.inclusion_rate DESC NULLS LAST
                """,
                {"slug": slug},
            )
            return cur.fetchall()


def has_data() -> bool:
    """Le catalogue vient d'un script séparé : il peut n'avoir jamais tourné."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT EXISTS (SELECT 1 FROM archetypes)")
            return cur.fetchone()["exists"]
