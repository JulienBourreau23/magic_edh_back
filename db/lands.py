"""db/lands.py — les terrains non-basiques utilisables dans une identité de couleur."""
from db.core import get_conn

LEGALITY_COLUMNS = {"commander": "legal_commander", "duel": "legal_duel"}


# Un sort dont le verso est un terrain : « Sorcery // Land ». Le recto n'est pas
# un terrain, sinon on ramasserait les recto-verso de terrains ordinaires.
MDFC_LAND = """
    c.type_line LIKE '%% // %%'
    AND split_part(c.type_line, ' // ', 2) LIKE '%%Land%%'
    AND split_part(c.type_line, ' // ', 1) NOT LIKE '%%Land%%'
"""

CARD_COLUMNS = """
    c.oracle_id, c.scryfall_id, c.name, fr.printed_name AS name_fr,
    c.type_line, c.oracle_text, c.price_eur, c.image_uri,
    c.image_downloaded, c.produced_mana, c.color_identity,
    c.edhrec_rank, COALESCE(col.quantity, 0) AS owned_quantity,
    COALESCE(w.quantity, 0) AS wanted_quantity,
    (SELECT count(DISTINCT dc.deck_id) FROM deck_cards dc
      JOIN cards dcc ON dcc.scryfall_id = dc.scryfall_id
      JOIN decks d ON d.id = dc.deck_id AND d.archived_at IS NULL
     WHERE dcc.oracle_id = c.oracle_id) AS decks
"""

CARD_JOINS = """
    FROM cards_cheapest c
    LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
    LEFT JOIN collection col ON col.oracle_id = c.oracle_id
    LEFT JOIN wishlist w ON w.oracle_id = c.oracle_id
"""


def modal_lands(identity: list[str], format: str = "commander") -> list[dict]:
    """
    Les sorts qui ont un terrain au verso.

    Ils n'entrent pas dans `dual_lands` : ils ne produisent en général qu'une
    seule couleur, alors que le critère y est d'en produire deux. Ils méritent
    pourtant leur place dans « les terrains à avoir » — ce sont des cartes qui
    ne coûtent pas une place dans le deck, et la moitié de la liste vaut moins
    de cinquante centimes.

    Une seule couleur de l'identité suffit donc ici, et l'incolore passe aussi.
    """
    legality = LEGALITY_COLUMNS[format]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {CARD_COLUMNS}
                {CARD_JOINS}
                WHERE c.{legality}
                  AND {MDFC_LAND}
                  AND c.color_identity <@ %(identity)s::text[]
                ORDER BY c.price_eur NULLS LAST, c.name
                """,
                {"identity": sorted(identity)},
            )
            return cur.fetchall()


def dual_lands(identity: list[str], format: str = "commander") -> list[dict]:
    """
    Les terrains non-basiques qui produisent **au moins deux couleurs de cette
    identité** : ceux qui règlent vraiment une manabase, par opposition à un
    terrain utilitaire ou à un basique.

    Le filtre d'identité est celui du format : un terrain qui produit une
    couleur hors identité est illégal dans le deck, pas seulement inutile.

    Le prix n'est **pas** filtré ici : c'est l'appelant qui décide de son
    plafond, et une carte possédée reste affichée quel que soit son prix — le
    plafond ne concerne que les achats, comme partout dans le projet.
    """
    legality = LEGALITY_COLUMNS[format]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT c.oracle_id, c.scryfall_id, c.name, fr.printed_name AS name_fr,
                       c.type_line, c.oracle_text, c.price_eur, c.image_uri,
                       c.image_downloaded, c.produced_mana, c.color_identity,
                       c.edhrec_rank, COALESCE(col.quantity, 0) AS owned_quantity,
                       COALESCE(w.quantity, 0) AS wanted_quantity,
                       (SELECT count(DISTINCT dc.deck_id) FROM deck_cards dc
                         JOIN cards dcc ON dcc.scryfall_id = dc.scryfall_id
                         JOIN decks d ON d.id = dc.deck_id AND d.archived_at IS NULL
                        WHERE dcc.oracle_id = c.oracle_id) AS decks
                FROM cards_cheapest c
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                LEFT JOIN collection col ON col.oracle_id = c.oracle_id
                LEFT JOIN wishlist w ON w.oracle_id = c.oracle_id
                WHERE c.{legality}
                  AND c.type_line LIKE '%%Land%%'
                  AND c.type_line NOT LIKE 'Basic%%'
                  AND c.color_identity <@ %(identity)s::text[]
                  AND cardinality(ARRAY(
                        SELECT unnest(c.produced_mana) INTERSECT SELECT unnest(%(identity)s::text[])
                      )) >= 2
                ORDER BY c.price_eur NULLS LAST, c.name
                """,
                {"identity": sorted(identity)},
            )
            return cur.fetchall()
