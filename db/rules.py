"""
db/rules.py — banlists et Game Changers, lus dans `cards`.

**Aucune table à entretenir ici, et aucune synchronisation propre.** Ces trois
listes sont des colonnes de `cards`, renseignées par `sync_scryfall.py` : elles
suivent donc le flow mensuel `sync-scryfall` sans qu'on ait à s'en occuper.
C'est le même raisonnement que pour `/must-have`, qui vit d'`edhrec_rank`.

Le piège que cette page a révélé : **`NOT legal_commander` n'est pas une
banlist.** Ce booléen confond « bannie » et « n'a jamais été jouable en
tournoi », si bien qu'il désigne 2 327 cartes — Un-sets, cartes playtest,
30th Anniversary — quand la banlist du multijoueur en compte 83. D'où les
colonnes `banned_commander` / `banned_duel` (migration 021), qui reprennent la
valeur exacte publiée par Scryfall.
"""
from db.core import get_conn

BANNED_COLUMNS = {"commander": "banned_commander", "duel": "banned_duel"}

# Beaucoup de cartes sont bannies **parce qu'elles n'ont rien à faire dans une
# partie**, pas parce qu'elles seraient trop fortes. Scryfall les marque
# `banned` comme les autres, si bien qu'une banlist brute mêle « Black Lotus »
# et « Ancestral Hot Dog Minotaur » : 83 cartes en multijoueur et **250** en
# duel, là où un joueur en attend une cinquantaine.
#
# Deux familles, et elles ne se reconnaissent pas de la même façon :
#
# - par leur **type** : les Conspiracies (25, jouées depuis l'extérieur du deck
#   en draft) et les Stickers d'Unfinity (48) ;
# - par leur **édition** : Unfinity, les éditions anniversaire, les decks de
#   championnat du monde — du `funny` et du `memorabilia`, 79 cartes rien que
#   pour Unfinity en duel.
#
# Le critère d'édition se juge sur **toutes les impressions** et non sur celle
# que la vue retient. C'est la subtilité qui décide de tout : l'impression la
# moins chère de Black Lotus est un proxy « 30th Anniversary », et juger sur
# elle retirerait de la banlist Black Lotus, les cinq Moxen, Ancestral Recall
# et Chaos Orb. Une carte n'est écartée que si **aucune** de ses impressions
# n'appartient à une vraie édition.
#
# Elles sont séparées plutôt que masquées : les cacher ferait mentir le total,
# les mélanger rendrait la liste illisible.
NON_PLAYABLE_TYPES = ("Conspiracy", "Stickers")
NON_TOURNAMENT_SET_TYPES = ("funny", "memorabilia")

# Vrai quand la carte n'existe que hors tournoi, impressions comprises.
HORS_TOURNOI = """
    (%(types)s
     OR NOT EXISTS (SELECT 1 FROM cards impression
                    WHERE impression.oracle_id = c.oracle_id
                      AND (impression.set_type IS NULL
                           OR impression.set_type <> ALL(%(sets)s::text[]))))
"""

CARD_COLUMNS = """
    c.oracle_id, c.scryfall_id, c.name, fr.printed_name AS name_fr,
    c.type_line, c.mana_cost, c.cmc, c.color_identity, c.price_eur,
    c.image_uri, c.image_downloaded, c.categories, c.game_changer,
    c.edhrec_rank, c.legal_commander, c.legal_duel,
    c.banned_commander, c.banned_duel, c.banned_as_commander_duel,
    COALESCE(col.quantity, 0) AS owned_quantity
"""


def _select(where: str, params: dict | None = None) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {CARD_COLUMNS}
                FROM cards_cheapest c
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                LEFT JOIN collection col ON col.oracle_id = c.oracle_id
                WHERE {where}
                ORDER BY c.name
                """,
                params or {},
            )
            return cur.fetchall()


def banlist(format: str) -> dict[str, list[dict]]:
    """
    Les cartes bannies dans ce format, par ordre alphabétique.

    L'ordre est alphabétique et non par prix ou popularité : une banlist se
    consulte pour y chercher une carte précise, pas pour la parcourir.

    Chaque carte porte **les deux drapeaux**, pas seulement celui du format
    demandé. C'est ce qui permet à l'écran de séparer « bannie des deux côtés »,
    « bannie en multi seulement » et « bannie en duel seulement » sans une
    requête de plus — et surtout sans qu'un troisième comptage puisse diverger
    des deux listes qu'il prétend croiser. `legal_duel` n'est pas un
    sous-ensemble de `legal_commander` : le duel est plus strict dans
    l'ensemble, mais il autorise dix-neuf cartes que le multijoueur bannit.

    Renvoie deux listes : la banlist proprement dite, et les cartes bannies
    pour leur **type** (voir `NON_PLAYABLE_TYPES`).
    """
    colonne = BANNED_COLUMNS[format]
    types = " OR ".join(f"c.type_line LIKE '{t}%%'" for t in NON_PLAYABLE_TYPES)
    hors_tournoi = HORS_TOURNOI.replace("%(types)s", types)
    params = {"sets": list(NON_TOURNAMENT_SET_TYPES)}
    return {
        "cards": _select(f"c.{colonne} AND NOT {hors_tournoi}", params),
        "outside_tournament": _select(f"c.{colonne} AND {hors_tournoi}", params),
    }


def banned_as_commander(format: str) -> list[dict]:
    """
    Les cartes interdites **comme commandant seulement**, jouables dans les 99.

    Propre au Duel Commander : Scryfall publie cette nuance sous la valeur
    `restricted` du format duel. Le multijoueur n'a pas d'équivalent, d'où une
    liste vide de ce côté plutôt qu'une colonne toujours fausse.
    """
    if format != "duel":
        return []
    return _select("c.banned_as_commander_duel")


def game_changers() -> list[dict]:
    """La liste officielle du Commander Format Panel, telle que Scryfall la
    publie (`is:gamechanger`). C'est le premier critère de bracket."""
    return _select("c.game_changer")


def has_data() -> bool:
    """Les colonnes naissent à `false` : sans resynchronisation complète, les
    deux banlists seraient vides sans que rien ne le signale."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT EXISTS (SELECT 1 FROM cards WHERE banned_commander)")
            return cur.fetchone()["exists"]
