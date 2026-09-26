"""
services/mana.py — coût de mana et castabilité.

Noyau partagé par l'analyse de manabase et la simulation. C'est le seul endroit
du projet où une approximation se paierait cash (un deck déclaré jouable alors
qu'il ne l'est pas), donc la vérification de castabilité fait un vrai couplage
biparti pips -> sources plutôt qu'un comptage par couleur : trois pips {G} face
à trois duales G/U doivent passer, mais un {G}{G} face à une seule source verte
doit échouer, ce qu'un simple comptage par couleur ne distingue pas.
"""
import re
from functools import lru_cache
from math import comb

COLORS = frozenset("WUBRG")

# Le terrain de base de chaque couleur, en français comme le reste de l'affichage.
BASIC_LAND_BY_COLOR = {"W": "Plaine", "U": "Île", "B": "Marais", "R": "Montagne", "G": "Forêt"}

# Fiabilité visée par `sources_needed`. La valeur n'est pas la fiabilité réelle
# visée (90 %) mais celle qui, dans CE modèle, retombe sur les repères publiés :
# comme il ne simule ni mulligan ni pioche, il est plus pessimiste qu'une vraie
# simulation à confiance égale. Calibrée pour donner ~18 sources pour un
# symbole au tour 2 et ~29 pour un double au tour 3, là où les tables usuelles
# donnent 19-20 et 27-30. Toucher à cette constante impose de refaire la
# comparaison — sinon les cibles dérivent en silence.
SOURCE_CONFIDENCE = 0.80
_TOKEN_RE = re.compile(r"\{([^}]+)\}")


def parse_mana_cost(mana_cost: str | None) -> tuple[int, list[frozenset[str]]]:
    """
    Renvoie (mana générique, liste de pips colorés). Chaque pip est l'ensemble
    des couleurs qui peuvent le payer ({G} -> {"G"}, hybride {G/U} -> {"G","U"}).

    Simplifications assumées : {X} compte pour 0, et les hybrides génériques
    ({2/W}) sont traités comme un pip coloré — c'est le cas défavorable, donc
    on ne surestime jamais la castabilité.
    """
    generic = 0
    pips: list[frozenset[str]] = []

    for token in _TOKEN_RE.findall(mana_cost or ""):
        token = token.upper()
        if token.isdigit():
            generic += int(token)
            continue
        if token == "X":
            continue

        colors = {part for part in token.split("/") if part in COLORS}
        if colors:
            pips.append(frozenset(colors))
        else:
            generic += 1  # {C}, {S}... : approximés en générique

    return generic, pips


def can_pay(generic: int, pips: list[frozenset[str]], sources: list[frozenset[str]]) -> bool:
    """
    `sources` = une entrée par mana disponible (un Sol Ring en jeu compte pour
    deux entrées {"C"}). Couplage biparti par chemins augmentants : chaque pip
    coloré doit recevoir sa propre source, le reste paie le générique.
    """
    if len(sources) < generic + len(pips):
        return False

    assigned_to: list[int | None] = [None] * len(sources)

    def assign(pip_index: int, visited: list[bool]) -> bool:
        for source_index, source in enumerate(sources):
            if visited[source_index] or not (pips[pip_index] & source):
                continue
            visited[source_index] = True
            holder = assigned_to[source_index]
            if holder is None or assign(holder, visited):
                assigned_to[source_index] = pip_index
                return True
        return False

    return all(assign(index, [False] * len(sources)) for index in range(len(pips)))


def color_requirements(cards: list[dict]) -> dict[str, int]:
    """Nombre de pips par couleur sur l'ensemble des cartes (pondéré par quantité)."""
    requirements = dict.fromkeys(COLORS, 0)
    for card in cards:
        _, pips = parse_mana_cost(card.get("mana_cost"))
        for pip in pips:
            for color in pip:
                requirements[color] += card.get("quantity", 1)
    return {color: count for color, count in requirements.items() if count}


def _at_least(successes: int, population: int, draws: int, wanted: int) -> float:
    """P(voir au moins `wanted` exemplaires) en tirant `draws` cartes sans remise."""
    if wanted <= 0:
        return 1.0
    if successes < wanted or draws < wanted:
        return 0.0
    total = comb(population, draws)
    return sum(comb(successes, hit) * comb(population - successes, draws - hit)
               for hit in range(wanted, min(successes, draws) + 1)) / total


@lru_cache(maxsize=None)
def miss_probability(pips: int, turn: int, sources: int, deck_size: int = 99) -> float:
    """
    Probabilité de NE PAS avoir `pips` sources d'une couleur au tour `turn`
    avec `sources` exemplaires dans un deck de `deck_size` cartes.

    C'est `sources_needed` vue par l'autre bout : au lieu de demander combien
    il en faut pour une carte, elle dit ce que coûte l'état actuel. Sommée sur
    le deck, elle donne le nombre de cartes que les couleurs laissent en main —
    la grandeur qu'on cherche vraiment à faire baisser.
    """
    seen = min(deck_size, 6 + turn)
    return 1.0 - _at_least(sources, deck_size, seen, pips)


def sources_needed(pips: int, turn: int,
                   deck_size: int = 99, confidence: float = SOURCE_CONFIDENCE) -> int:
    """
    Combien de sources d'une couleur il faut pour lancer à l'heure, dans
    `confidence` des parties, un sort qui demande `pips` symboles de cette
    couleur au tour `turn`.

    Le modèle est celui des tables de manabase communément utilisées : on
    compte les cartes **vues** au tour visé — sept en main plus une pioche par
    tour — et on cherche le plus petit nombre de sources tel que la loi
    hypergéométrique donne au moins `pips` d'entre elles.

    Il ignore volontairement deux choses, dans deux directions opposées : on ne
    peut poser qu'un terrain par tour (le modèle est donc optimiste sur les
    tours précoces), mais un mulligan et les effets de pioche font voir plus de
    cartes (il est pessimiste sur les tours tardifs). C'est un repère de
    construction, pas une mesure — la mesure, c'est la simulation.
    """
    seen = min(deck_size, 6 + turn)  # 7 cartes en main au tour 1, +1 par tour
    for sources in range(pips, deck_size + 1):
        if _at_least(sources, deck_size, seen, pips) >= confidence:
            return sources
    return deck_size


LAND_TYPES = frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest"})


def _land_types(card: dict) -> set[str]:
    type_line = card.get("type_line") or ""
    return set(type_line.split("—", 1)[1].split()) & LAND_TYPES if "—" in type_line else set()


def resolve_fetchlands(cards: list[dict]) -> list[dict]:
    """
    Donne à chaque fetchland les couleurs des terrains qu'il peut aller
    chercher **dans ce deck**.

    Scryfall ne déclare aucun mana produit pour un fetchland : il comptait donc
    comme un terrain muet partout — manabase, simulation, duel — et un deck qui
    en joue six paraissait plus lent et plus mal réparti qu'il ne l'est. La
    couleur dépend des cibles présentes : Polluted Delta vaut du blanc dans un
    deck qui joue Hallowed Fountain (type Île), et rien du tout dans un deck
    sans Île ni Marais.

    Seuls les terrains qui ne produisent aucune couleur par eux-mêmes sont
    résolus : Flagstones of Trokair produit déjà du blanc et ne cherche une
    Plaine qu'une fois détruit. Idempotent : résoudre deux fois ne change rien.
    """
    lands = [card for card in cards if "Land" in (card.get("type_line") or "")]
    resolved = []
    for card in cards:
        fetches = set(card.get("fetches") or [])
        produced = set(card.get("produced_mana") or [])
        if not fetches or produced & COLORS:
            resolved.append(card)
            continue
        colors = set(produced)
        for target in lands:
            if target is card or target.get("fetches"):
                continue
            by_type = _land_types(target) & fetches
            is_basic = (target.get("type_line") or "").startswith("Basic Land")
            if by_type or ("Basic" in fetches and is_basic):
                colors |= set(target.get("produced_mana") or [])
        resolved.append({**card, "produced_mana": sorted(colors, key="WUBRGC".index)})
    return resolved
