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
    # Stax : priver ou taxer les ressources de l'adversaire. La règle tenait sur
    # « creatures can't », qui attrape surtout « can't be blocked » et « can't
    # block » — de l'évasion et des inconvénients, pas du stax. Chaque
    # alternative ci-dessous nomme donc ce qui est empêché, pas seulement qui.
    (STAX, re.compile(
        # Interdire aux joueurs : lancer, piocher, chercher, gagner de la vie...
        r"(players?|opponents?|each player) can't\b"
        # Forteresse : Propaganda, Ghostly Prison, Sphere of Safety.
        r"|creatures? can't attack"
        # Taxe sur les sorts et capacités.
        r"|costs? \{\d+\} more"
        # Verrou de dégagement statique : Winter Orb, Meekstone, Intruder Alarm.
        # Le « next » écarte les effets ponctuels (Sleep, Icy Blast), qui sont
        # du tempo : le stax dure.
        r"|don't untap during(?!.*\bnext\b)"
        r"|skips? their untap step", re.I)),
]

# Une carte qui va chercher un terrain le nomme de deux façons : par le mot
# « land » (Cultivate : « two basic land cards ») ou par un type de base
# (Nature's Lore : « a Forest card »). Ne connaître que la première faisait de
# la fixation de mana un tuteur, et privait de `ramp` tout ce qui cherche par
# type — les deux erreurs à la fois, sur la même famille de cartes.
_BASIC_LAND_TYPES = "Plains|Island|Swamp|Mountain|Forest"
# « Split second » interdit littéralement aux joueurs de lancer des sorts, mais
# le temps d'une résolution : c'est le rappel d'un mot-clé sur un éphémère
# (Krosan Grip, Angel's Grace), pas un verrou posé sur la table.
_SPLIT_SECOND_RE = re.compile(r"split second", re.I)

_LAND_SEARCH_RE = re.compile(
    rf"search your library for .*\b(lands?|{_BASIC_LAND_TYPES})\b", re.I)


def classify(type_line: str | None, oracle_text: str | None, produced_mana: list[str] | None) -> list[str]:
    """Renvoie les catégories d'une carte, dans un ordre stable."""
    type_line = type_line or ""
    text = oracle_text or ""
    categories: set[str] = set()

    is_land = "Land" in type_line
    if is_land:
        categories.add(LAND)

    # Accélération de mana : tout ce qui produit du mana sans être un terrain
    # (rochers, dorks), plus les sorts qui vont chercher un terrain. Un terrain
    # qui en cherche un autre en se sacrifiant (fetchland, Terminal Moraine)
    # n'accélère rien : il remplace la pose du tour au lieu de s'y ajouter.
    if not is_land and (produced_mana or _LAND_SEARCH_RE.search(text)):
        categories.add(RAMP)

    for category, pattern in _RULES:
        if pattern.search(text):
            categories.add(category)

    if STAX in categories and _SPLIT_SECOND_RE.search(text):
        categories.discard(STAX)

    # Chercher un terrain n'est pas tutoriser : le signal "tuteur" du bracket
    # doit compter les cartes qui vont chercher une réponse ou une pièce de
    # combo, pas la manabase. La condition ne regarde donc plus `ramp` — un
    # fetchland ne l'a pas, et restait compté comme tuteur.
    if TUTOR in categories and _LAND_SEARCH_RE.search(text):
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
