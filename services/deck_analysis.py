"""
services/deck_analysis.py — analyse statique d'un deck : courbe, prix, légalité,
manabase et estimation de bracket. Tout est calculé, rien n'est estimé par une IA.
"""
from services import card_categories as categories
from services.mana import COLORS, color_requirements

COMMANDER_DECK_SIZE = 100
RECOMMENDED_LANDS = range(35, 39)

# Seuils de diagnostic, volontairement grossiers : ce sont des repères de
# construction communément admis en EDH, pas des vérités. Ils servent à
# signaler un écart franc, pas à noter finement un deck.
ROLE_TARGETS = {
    categories.RAMP: (10, 14),
    categories.DRAW: (8, 12),
    categories.REMOVAL: (8, 12),
    categories.BOARD_WIPE: (2, 4),
}
# En dessous de ce nombre de sources, une couleur significativement demandée
# est considérée comme sous-alimentée.
MIN_SOURCES_PER_COLOR = 10
SIGNIFICANT_PIPS = 8


def display_name(card: dict) -> str:
    """Nom affiché : le français quand il existe, l'anglais sinon (~12 % des cartes)."""
    return card.get("name_fr") or card["name"]


def mana_curve(cards: list[dict]) -> dict[str, int]:
    """Regroupe les cartes non-terrain par CMC (7+ fusionné), pondéré par quantité."""
    curve: dict[str, int] = {}
    for card in cards:
        if categories.is_land(card):
            continue
        cmc = card["cmc"] or 0
        bucket = "7+" if cmc >= 7 else str(int(cmc))
        curve[bucket] = curve.get(bucket, 0) + card["quantity"]
    return curve


def total_price_eur(cards: list[dict]) -> float:
    return round(sum((c["price_eur"] or 0) * c["quantity"] for c in cards), 2)


def commander_identity(cards: list[dict]) -> set[str] | None:
    commanders = [c for c in cards if c["is_commander"]]
    if not commanders:
        return None
    return set().union(*(set(c["color_identity"]) for c in commanders))


def manabase(cards: list[dict]) -> dict:
    """Terrains, sources par couleur et besoins en pips — le socle de tout conseil."""
    land_count = sum(c["quantity"] for c in cards if categories.is_land(c))
    nonland = [c for c in cards if not categories.is_land(c)]

    sources = dict.fromkeys(COLORS, 0)
    for card in cards:
        for color in card.get("produced_mana") or []:
            if color in sources:
                sources[color] += card["quantity"]

    requirements = color_requirements(nonland)
    identity = commander_identity(cards) or set(requirements)

    colors = {
        color: {
            "sources": sources[color],
            "pips": requirements.get(color, 0),
            "under_supplied": (
                sources[color] < MIN_SOURCES_PER_COLOR
                and requirements.get(color, 0) >= SIGNIFICANT_PIPS
            ),
        }
        for color in sorted(identity)
    }

    return {
        "land_count": land_count,
        "recommended_lands": f"{RECOMMENDED_LANDS.start}-{RECOMMENDED_LANDS.stop - 1}",
        "lands_ok": land_count in RECOMMENDED_LANDS,
        "colors": colors,
        # Les cartes sans identité de couleur n'entrent pas dans la répartition
        # par couleur : elles sont comptées à part plutôt que de recevoir une
        # part de camembert grise qui n'aurait pas de sens.
        "colorless_cards": sum(c["quantity"] for c in cards if not c["color_identity"]),
    }


def role_diagnostics(cards: list[dict]) -> list[dict]:
    """Compare les effectifs par rôle aux repères de construction."""
    counts = categories.count_by_category(cards)
    diagnostics = []
    for role, (low, high) in ROLE_TARGETS.items():
        count = counts.get(role, 0)
        if count < low:
            status, gap = "insuffisant", low - count
        elif count > high:
            status, gap = "excédentaire", count - high
        else:
            status, gap = "ok", 0
        diagnostics.append({"role": role, "count": count, "target": f"{low}-{high}",
                            "status": status, "gap": gap})
    return diagnostics


def legality_warnings(cards: list[dict], format: str = "commander") -> list[dict]:
    """
    Règles dures du format : taille, singleton, banlist, identité de couleur.
    L'identité de couleur est la contrainte structurante en EDH — une carte
    hors identité est injouable, pas simplement déconseillée. Le Duel Commander
    a sa propre banlist (Sol Ring y est banni), d'où le paramètre `format`.
    """
    warnings: list[dict] = []
    legality_field = "legal_duel" if format == "duel" else "legal_commander"
    identity = commander_identity(cards)

    total_cards = sum(c["quantity"] for c in cards)
    if total_cards != COMMANDER_DECK_SIZE:
        warnings.append({
            "card": "—",
            "issue": f"{total_cards} cartes au lieu de {COMMANDER_DECK_SIZE} ({total_cards - COMMANDER_DECK_SIZE:+d})",
        })

    if identity is None:
        warnings.append({
            "card": "—",
            "issue": "commandant non déterminé : l'identité de couleur n'a pas pu être vérifiée",
        })

    for card in cards:
        if not card[legality_field]:
            label = "Duel Commander" if format == "duel" else "Commander"
            warnings.append({"card": display_name(card), "issue": f"non légale en {label} (bannie ou hors format)"})

        is_basic_land = card["type_line"] and card["type_line"].startswith("Basic Land")
        if card["quantity"] > 1 and not (is_basic_land or card.get("allows_multiple")) and not card["is_commander"]:
            warnings.append({"card": display_name(card), "issue": f"{card['quantity']} exemplaires (singleton attendu)"})

        if identity is not None and not card["is_commander"]:
            off_identity = set(card["color_identity"]) - identity
            if off_identity:
                warnings.append({
                    "card": display_name(card),
                    "issue": f"hors de l'identité de couleur du commandant ({'/'.join(sorted(off_identity))})",
                })

    return warnings


def bracket_estimate(cards: list[dict], combos: list[dict] | None = None) -> dict:
    """
    Bracket officiel du Commander Format Panel, à partir des deux critères
    qu'on sait constater.

    1. **Game Changers** : 0 = brackets 1-2, 1 à 3 = bracket 3, 4+ = brackets
       4-5. Le commandant compte s'il est lui-même sur la liste.
    2. **Combos infinis à deux cartes qui gagnent la partie** : officiellement
       interdits aux brackets 1-2. Un tel combo ne se lit pas dans le texte
       d'une carte — il naît de l'interaction — donc il se constate contre un
       catalogue (`services/combos.py`), et le déclarer relève ici du plancher.

    Ce que ce calcul ne tranche **pas** : au-dessus du bracket 3, le texte
    officiel demande qu'un combo à deux cartes reste un plan de fin de partie,
    sans définir « fin de partie ». Le mana total du combo est renvoyé avec,
    à lire avec le ramp du deck ; c'est au joueur de trancher.

    Les autres critères officiels (tours supplémentaires, stax, destruction de
    terrains) ne sont pas quantifiables de façon fiable depuis les données de
    carte : on les remonte en signaux bruts, sans les laisser modifier le
    bracket, pour que l'écart entre le calcul et la réalité reste visible
    plutôt que masqué derrière un chiffre.
    """
    game_changers = [
        {"name": c["name"], "name_fr": c.get("name_fr"),
         "scryfall_id": c["scryfall_id"], "is_commander": c["is_commander"]}
        for c in cards if c.get("game_changer")
    ]
    count = len(game_changers)
    combos = combos or []
    winning_combos = [combo for combo in combos if combo["wins_outright"]]

    if count == 0 and not winning_combos:
        bracket = {"min": 1, "max": 2, "label": "Bracket 1-2 (exhibition / core)"}
    elif count <= 3:
        bracket = {"min": 3, "max": 3, "label": "Bracket 3 (upgraded)"}
    else:
        bracket = {"min": 4, "max": 5, "label": "Bracket 4-5 (optimized / cEDH)"}

    role_counts = categories.count_by_category(cards)
    qualitative = {
        "tutors": role_counts.get(categories.TUTOR, 0),
        "extra_turns": sum(c["quantity"] for c in cards
                           if categories.EXTRA_TURN in (c.get("categories") or [])),
        "stax": sum(c["quantity"] for c in cards
                    if categories.STAX in (c.get("categories") or [])),
    }

    return {
        "game_changers": game_changers,
        "game_changer_count": count,
        **bracket,
        "two_card_combos": combos,
        "winning_combo_count": len(winning_combos),
        "qualitative_signals": qualitative,
        "note": (
            "Plancher calculé sur les Game Changers et sur les combos à deux "
            "cartes qui gagnent la partie (interdits aux brackets 1-2). Le "
            "système officiel demande en plus qu'un tel combo reste un plan de "
            "fin de partie : compare son mana total au ramp du deck. Les "
            "signaux ci-contre (tuteurs, tours supplémentaires, stax) comptent "
            "aussi mais ne sont pas automatisables : à toi de trancher."
        ),
    }
