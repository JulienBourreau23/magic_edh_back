"""
services/card_categories.py — classification déterministe d'une carte à partir
de son type, de son texte oracle et du mana qu'elle produit.

Source de vérité unique : la classification est calculée une fois au sync et
stockée dans `cards.categories`, ce qui la rend filtrable en SQL (suggestions)
sans dupliquer les règles côté requête.

Ce sont des heuristiques textuelles, donc imparfaites par nature (un "destroy
target" dans une capacité déclenchée compte comme du removal). Elles sont
volontairement lisibles et testables plutôt que subtiles : quand un cas est
faux, on ajoute un test et on corrige la règle ici, à un seul endroit.
"""
import re

LAND = "land"
RAMP = "ramp"
DRAW = "draw"
REMOVAL = "removal"
BOARD_WIPE = "board_wipe"
COUNTERSPELL = "counterspell"
TUTOR = "tutor"
PROTECTION = "protection"
RECURSION = "recursion"
EXTRA_TURN = "extra_turn"
STAX = "stax"

# Catégories qui décrivent un rôle dans la construction du deck : ce sont
# celles dont on mesure la quantité pour diagnostiquer un deck.
ROLE_CATEGORIES = [RAMP, DRAW, REMOVAL, BOARD_WIPE, COUNTERSPELL, PROTECTION, RECURSION, TUTOR]

_RULES: list[tuple[str, re.Pattern]] = [
    (DRAW, re.compile(r"\bdraws? (a card|\w+ cards)", re.I)),
    (REMOVAL, re.compile(
        r"(destroy|exile) target (creature|permanent|artifact|enchantment|planeswalker|nonland)"
        r"|deals? \d+ damage to target (creature|permanent|planeswalker)"
        r"|target creature gets -\d+/-\d+", re.I)),
    (BOARD_WIPE, re.compile(
        r"(destroy|exile) (all|each) (creature|permanent|nonland)"
        r"|each player sacrifices", re.I)),
    (COUNTERSPELL, re.compile(r"counter target", re.I)),
    (TUTOR, re.compile(r"search your library for (a|up to \w+|two|three)", re.I)),
    (PROTECTION, re.compile(
        r"\b(hexproof|indestructible|protection from|phases? out)\b"
        r"|sacrifice .* regenerate", re.I)),
    (RECURSION, re.compile(r"return .* from (your|a) graveyard", re.I)),
    (EXTRA_TURN, re.compile(r"takes? an extra turn", re.I)),
    (STAX, re.compile(
        r"(players?|opponents?|creatures?) can't"
        r"|spells? (your opponents cast )?costs? \{\d+\} more"
        r"|don't untap", re.I)),
]

_LAND_RAMP_RE = re.compile(r"search your library for .*\bland", re.I)


def classify(type_line: str | None, oracle_text: str | None, produced_mana: list[str] | None) -> list[str]:
    """Renvoie les catégories d'une carte, dans un ordre stable."""
    type_line = type_line or ""
    text = oracle_text or ""
    categories: set[str] = set()

    is_land = "Land" in type_line
    if is_land:
        categories.add(LAND)

    # Accélération de mana : tout ce qui produit du mana sans être un terrain
    # (rochers, dorks), plus les sorts qui vont chercher un terrain.
    if (produced_mana and not is_land) or _LAND_RAMP_RE.search(text):
        categories.add(RAMP)

    for category, pattern in _RULES:
        if pattern.search(text):
            categories.add(category)

    # Un tuteur à terrain est déjà compté comme ramp : le compter aussi comme
    # tuteur gonflerait artificiellement le signal "tuteur" du bracket.
    if TUTOR in categories and RAMP in categories and _LAND_RAMP_RE.search(text):
        categories.discard(TUTOR)

    return sorted(categories)


def is_land(card: dict) -> bool:
    """
    Seule définition de « c'est un terrain » côté service : la classification
    faite au sync, pas une relecture du `type_line`. Trois modules en avaient
    leur propre copie.
    """
    return LAND in (card.get("categories") or [])


def count_by_category(cards: list[dict]) -> dict[str, int]:
    """
    Compte les cartes par rôle, pondéré par quantité, **commandant compris** :
    une carte toujours disponible en zone de commandement compte au moins
    autant qu'une carte du deck pour juger d'un manque de pioche ou de ramp.
    Les appelants qui ne veulent pas du commandant le filtrent eux-mêmes
    (cf. `suggestions._cuts_for_surplus`, qui ne propose jamais de le couper).
    """
    counts = dict.fromkeys(ROLE_CATEGORIES, 0)
    for card in cards:
        for category in card.get("categories") or []:
            if category in counts:
                counts[category] += card.get("quantity", 1)
    return counts
