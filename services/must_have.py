"""
services/must_have.py — « les cartes à avoir », type par type.

Ce n'est **pas un top de référence mais une liste d'achats de long terme** :
la question posée n'est pas « quelles sont les meilleures cartes du format »
mais « qu'est-ce que je gagnerais à acheter, au fil du temps, sans dépasser mon
plafond ». D'où le filtre de prix, qui change effectivement la physionomie du
classement — une carte à 400 € n'est pas une information manquante ici, elle ne
sera jamais achetée.

Trois conséquences de cette intention :

- **Les cartes possédées restent, quel que soit leur prix.** Le plafond ne
  concerne que les achats, comme partout ailleurs dans le projet : rien ne
  reproche à la collection de contenir des cartes chères. Elles occupent leur
  place dans la liste, marquées comme acquises.
- **Le nombre de cartes écartées pour dépassement est renvoyé** (`over_budget`),
  sans les lister. La liste reste utilisable tout en disant qu'elle est filtrée
  — sans ce compte, elle se ferait passer pour un classement complet.
- **Une carte sans prix connu n'est jamais proposée à l'achat**, conformément à
  la règle du projet : `price_eur` nul est « prix inconnu », pas « gratuit ».

Le classement est `edhrec_rank`, c'est-à-dire la popularité mesurée par EDHREC,
qui arrive avec `sync_scryfall`. **Aucune table à entretenir, donc aucun flow
d'ordonnancement propre à cette page** : la liste se met à jour toute seule au
rythme mensuel du flow `sync-scryfall`.
"""
from db.core import get_conn

DEFAULT_MAX_PRICE_EUR = 50.0
DEFAULT_TOP = 50
PLANESWALKER_TOP = 30

# Un `type_line` porte plusieurs types (« Artifact Creature — Construct »), et
# une carte apparaît donc dans chacune de ses catégories. C'est voulu pour un
# usage d'achat : on cherche un rocher de mana dans les artefacts sans se
# demander s'il est aussi une créature, et on ne l'achète qu'une fois de toute
# façon.
TYPES: list[dict] = [
    {"key": "creature", "label": "Créatures", "match": "Creature", "top": DEFAULT_TOP},
    {"key": "instant", "label": "Éphémères", "match": "Instant", "top": DEFAULT_TOP},
    {"key": "sorcery", "label": "Rituels", "match": "Sorcery", "top": DEFAULT_TOP},
    {"key": "artifact", "label": "Artefacts", "match": "Artifact", "top": DEFAULT_TOP},
    {"key": "enchantment", "label": "Enchantements", "match": "Enchantment", "top": DEFAULT_TOP},
    # Les planeswalkers sont bien moins nombreux : trente suffisent à couvrir
    # ceux qu'on voit réellement jouer.
    {"key": "planeswalker", "label": "Planeswalkers", "match": "Planeswalker", "top": PLANESWALKER_TOP},
    {"key": "land", "label": "Terrains", "match": "Land", "top": DEFAULT_TOP},
    {"key": "battle", "label": "Batailles", "match": "Battle", "top": DEFAULT_TOP},
]

# Les terrains de base ne s'achètent pas : quantité supposée illimitée, ils ne
# figurent jamais dans la collection et n'ont rien à faire dans une liste
# d'achats. Même règle que partout ailleurs dans le projet.
_EXCLUDE_BASICS = "c.type_line NOT ILIKE 'Basic Land%%'"

_SELECT = """
    SELECT c.oracle_id, c.scryfall_id, c.name, fr.printed_name AS name_fr,
           c.type_line, c.mana_cost, c.cmc, c.price_eur, c.edhrec_rank,
           c.image_uri, c.image_downloaded, c.color_identity,
           COALESCE(col.quantity, 0) AS owned
    FROM cards_cheapest c
    LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
    LEFT JOIN collection col ON col.oracle_id = c.oracle_id
    WHERE c.edhrec_rank IS NOT NULL
      AND {legality}
      AND c.type_line ILIKE %(match)s
      AND {no_basics}
"""


def _legality_column(format: str) -> str:
    """
    `legal_duel` est toujours plus restrictif que `legal_commander`, jamais
    l'inverse : un Sol Ring domine le top des artefacts en multijoueur et n'a
    rien à faire dans une liste d'achats pour du duel.
    """
    return "c.legal_duel" if format == "duel" else "c.legal_commander"


def must_have(
    format: str = "commander",
    max_price: float = DEFAULT_MAX_PRICE_EUR,
) -> dict:
    """Les cartes les plus jouées de chaque type, achetables sous le plafond."""
    legality = _legality_column(format)

    # Ce qu'on affiche : possédé quel qu'en soit le prix, ou achetable.
    achetable = _SELECT.format(legality=legality, no_basics=_EXCLUDE_BASICS) + """
      AND (col.quantity > 0
           OR (c.price_eur IS NOT NULL AND c.price_eur <= %(max_price)s))
    ORDER BY c.edhrec_rank
    LIMIT %(top)s
    """

    # Ce qu'on aurait affiché sans plafond, pour dire combien manquent. On ne
    # rapatrie que le drapeau, pas les cartes : la liste ne doit pas se
    # remplir de ce qui ne sera pas acheté.
    sans_plafond = """
    SELECT COUNT(*) AS n FROM (
        SELECT COALESCE(col.quantity, 0) AS owned, c.price_eur
        FROM cards_cheapest c
        LEFT JOIN collection col ON col.oracle_id = c.oracle_id
        WHERE c.edhrec_rank IS NOT NULL
          AND {legality}
          AND c.type_line ILIKE %(match)s
          AND {no_basics}
        ORDER BY c.edhrec_rank
        LIMIT %(top)s
    ) t
    WHERE t.owned = 0 AND (t.price_eur IS NULL OR t.price_eur > %(max_price)s)
    """.format(legality=legality, no_basics=_EXCLUDE_BASICS)

    groups = []
    with get_conn() as conn:
        with conn.cursor() as cur:
            for type_def in TYPES:
                params = {
                    "match": f"%{type_def['match']}%",
                    "max_price": max_price,
                    "top": type_def["top"],
                }
                cur.execute(achetable, params)
                cards = cur.fetchall()

                cur.execute(sans_plafond, params)
                over_budget = cur.fetchone()["n"]

                groups.append({
                    "key": type_def["key"],
                    "label": type_def["label"],
                    "top": type_def["top"],
                    "cards": cards,
                    "owned_count": sum(1 for c in cards if c["owned"] > 0),
                    "to_buy_count": sum(1 for c in cards if c["owned"] == 0),
                    "over_budget": over_budget,
                })

    return {
        "format": format,
        "max_price_eur": max_price,
        "groups": groups,
    }
