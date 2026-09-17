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

`wanted` accompagne `owned` pour la même raison : la page laisse ajouter une
carte à la collection ou à la liste de recherche d'un clic, et les quantités
**s'additionnent** dans les deux tables. Sans savoir ce qui y est déjà, un
second clic demanderait un second exemplaire sans rien dire.

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
           COALESCE(col.quantity, 0) AS owned,
           COALESCE(w.quantity, 0) AS wanted
    FROM cards_cheapest c
    LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
    LEFT JOIN collection col ON col.oracle_id = c.oracle_id
    LEFT JOIN wishlist w ON w.oracle_id = c.oracle_id
    WHERE c.edhrec_rank IS NOT NULL
      AND {legality}
      AND c.type_line ILIKE %(match)s
      AND {no_basics}
"""


def _legality_column(format: str) -> str:
    """
    Le Duel Commander a sa propre banlist. Elle est majoritairement plus
    stricte — un Sol Ring domine le top des artefacts en multijoueur et n'a
    rien à faire dans une liste d'achats pour du duel — mais ce n'est **pas**
    un sur-ensemble : quelques cartes bannies en multijoueur y sont légales.
    D'où une colonne par format, jamais déduite de l'autre.
    """
    return "c.legal_duel" if format == "duel" else "c.legal_commander"


def must_have(
    format: str = "commander",
    max_price: float | None = DEFAULT_MAX_PRICE_EUR,
) -> dict:
    """
    Les cartes les plus jouées de chaque type.

    `max_price=None` retire le plafond : on obtient alors le classement **réel**,
    sans filtre d'achat. C'est ce que demande le récapitulatif de collection, où
    la question n'est pas « qu'est-ce que je peux acheter » mais « combien du
    top est-ce que je possède ». Les deux lectures partagent la même requête,
    pour qu'elles ne puissent pas diverger.
    """
    legality = _legality_column(format)

    if max_price is None:
        condition = ""
    else:
        # Ce qu'on affiche : possédé quel qu'en soit le prix, ou achetable.
        condition = """
      AND (col.quantity > 0
           OR (c.price_eur IS NOT NULL AND c.price_eur <= %(max_price)s))"""

    achetable = _SELECT.format(legality=legality, no_basics=_EXCLUDE_BASICS) + condition + """
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
                    "max_price": max_price if max_price is not None else 0,
                    "top": type_def["top"],
                }
                cur.execute(achetable, params)
                cards = cur.fetchall()

                if max_price is None:
                    over_budget = 0        # sans plafond, rien n'est écarté
                else:
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


# Tranches de popularité EDHREC. Le rang est un classement, pas une note : la
# distance entre le 1er et le 100e n'a rien à voir avec celle entre le 4000e et
# le 4100e. D'où des tranches à bornes croissantes, et des libellés qui disent
# ce que le rang signifie plutôt que le rang lui-même.
RANK_BANDS: list[tuple[str, int | None, int | None]] = [
    ("Incontournables (top 100)", None, 100),
    ("Très jouées (101 – 500)", 101, 500),
    ("Courantes (501 – 1500)", 501, 1500),
    ("Occasionnelles (1501 – 5000)", 1501, 5000),
    ("Rarement jouées (au-delà)", 5001, None),
]


def rank_distribution() -> list[dict]:
    """
    Combien de cartes possédées dans chaque tranche de popularité.

    Les terrains de base sont hors collection par construction, donc absents
    d'office. Les cartes sans rang EDHREC ne sont pas comptées : un rang absent
    n'est pas un mauvais rang, c'est une absence de mesure — les ranger avec
    les moins jouées inventerait une information.
    """
    cas = "\n".join(
        f"WHEN {_band_condition(low, high)} THEN {index}"
        for index, (_, low, high) in enumerate(RANK_BANDS)
    )
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT bande, COUNT(*) AS cartes, COALESCE(SUM(quantity), 0) AS exemplaires
                FROM (
                    SELECT col.quantity,
                           CASE {cas} END AS bande
                    FROM collection col
                    JOIN cards_cheapest c ON c.oracle_id = col.oracle_id
                    WHERE c.edhrec_rank IS NOT NULL
                ) t
                WHERE bande IS NOT NULL
                GROUP BY bande
            """)
            counts = {row["bande"]: row for row in cur.fetchall()}

    return [
        {
            "label": label,
            "cards": counts.get(index, {}).get("cartes", 0),
            "copies": int(counts.get(index, {}).get("exemplaires", 0)),
        }
        for index, (label, _, _) in enumerate(RANK_BANDS)
    ]


def _band_condition(low: int | None, high: int | None) -> str:
    if low is None:
        return f"c.edhrec_rank <= {high}"
    if high is None:
        return f"c.edhrec_rank >= {low}"
    return f"c.edhrec_rank BETWEEN {low} AND {high}"


def coverage(format: str = "commander") -> dict:
    """
    Récapitulatif de collection : quelle part du classement réel est possédée,
    type par type.

    **Sans plafond de prix, volontairement.** La question n'est pas « qu'est-ce
    que je peux acheter » — ça, c'est `/must-have` — mais « où en est ma
    collection face à ce qui se joue ». Filtrer par prix répondrait à l'autre
    question et gonflerait artificiellement la couverture, puisque les cartes
    chères qu'on ne possède pas disparaîtraient du dénominateur.
    """
    import db.collection as collection_db

    lists = must_have(format=format, max_price=None)
    groups = []
    for group in lists["groups"]:
        owned = [card for card in group["cards"] if card["owned"] > 0]
        groups.append({
            "key": group["key"],
            "label": group["label"],
            # Le dénominateur est la taille **réelle** de la liste, pas la
            # cible : les Batailles sont moins de cinquante en tout, et
            # afficher « 0 / 50 » laisserait croire à un manque inexistant.
            "listed": len(group["cards"]),
            "target": group["top"],
            "owned": len(owned),
            "cards": group["cards"],
        })

    return {
        "format": format,
        "stats": collection_db.stats(),
        "groups": groups,
        "rank_distribution": rank_distribution(),
    }
