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

COLORS = frozenset("WUBRG")
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
