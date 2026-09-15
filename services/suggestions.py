"""
services/suggestions.py — propositions de changements, sans IA.

Le raisonnement est explicite et vérifiable : on mesure un écart aux repères de
construction (trop peu de ramp, pas assez de terrains, bracket trop haut pour
la table visée), puis on propose des cartes qui comblent cet écart en
respectant trois contraintes dures — identité de couleur, légalité du format,
plafond de prix. Le classement se fait au rang EDHREC (popularité), qui est un
proxy honnête de « carte qui fait le travail » sans rien inventer.

Le plafond de prix ne s'applique qu'aux cartes à ACHETER : rien ici ne
reproche au deck de contenir des cartes chères déjà possédées.
"""
import db.cards as cards_db
from services import card_categories as categories
from services import deck_analysis

DEFAULT_MAX_PRICE_EUR = 50.0
CANDIDATES_PER_ROLE = 6

ROLE_LABELS = {
    categories.RAMP: "accélération de mana",
    categories.DRAW: "pioche",
    categories.REMOVAL: "removal ciblé",
    categories.BOARD_WIPE: "board wipe",
    categories.LAND: "terrains",
}


def _deck_oracle_ids(cards: list[dict]) -> list[str]:
    return [card["oracle_id"] for card in cards]


def cuts_for_bracket(cards: list[dict], target_bracket: int) -> list[dict]:
    """
    Pour redescendre de bracket, le levier officiel est le nombre de Game
    Changers : 0 pour viser les brackets 1-2, 3 maximum pour le bracket 3.
    """
    game_changers = [c for c in cards if c.get("game_changer")]
    allowed = 0 if target_bracket <= 2 else (3 if target_bracket == 3 else len(game_changers))
    surplus = len(game_changers) - allowed
    if surplus <= 0:
        return []

    # On coupe en priorité les moins jouées : à impact de bracket égal, ce sont
    # celles dont l'absence se sentira le moins dans le deck.
    ordered = sorted(game_changers, key=lambda c: c.get("edhrec_rank") or 10**9, reverse=True)
    return [
        {
            "card": {k: card[k] for k in ("scryfall_id", "name", "name_fr", "price_eur", "image_uri", "image_downloaded")},
            "reason": f"Game Changer : en retirer {surplus} pour viser le bracket {target_bracket}",
        }
        for card in ordered[:surplus]
    ]


def _cuts_for_surplus(cards: list[dict], diagnostics: list[dict]) -> list[dict]:
    """Rôles en excédent : propose les cartes les moins jouées de ce rôle."""
    cuts = []
    for diagnostic in diagnostics:
        if diagnostic["status"] != "excédentaire":
            continue
        role = diagnostic["role"]
        in_role = [c for c in cards
                   if role in (c.get("categories") or []) and not c["is_commander"]]
        ordered = sorted(in_role, key=lambda c: c.get("edhrec_rank") or 10**9, reverse=True)
        for card in ordered[:diagnostic["gap"]]:
            cuts.append({
                "card": {k: card[k] for k in ("scryfall_id", "name", "name_fr", "price_eur", "image_uri", "image_downloaded")},
                "reason": f"{ROLE_LABELS.get(role, role)} en excédent ({diagnostic['count']} pour {diagnostic['target']})",
            })
    return cuts


def suggest(cards: list[dict], format: str = "commander",
            max_price: float = DEFAULT_MAX_PRICE_EUR,
            target_bracket: int | None = None) -> dict:
    identity = deck_analysis.commander_identity(cards)
    if identity is None:
        return {
            "error": "commandant non déterminé : sans identité de couleur, "
                     "aucune suggestion fiable n'est possible",
        }

    diagnostics = deck_analysis.role_diagnostics(cards)
    mana = deck_analysis.manabase(cards)
    exclude = _deck_oracle_ids(cards)
    # Si on cherche à contenir le bracket, inutile de proposer des cartes qui
    # le feraient remonter aussitôt.
    exclude_game_changers = target_bracket is not None and target_bracket <= 3

    to_add = []
    for diagnostic in diagnostics:
        if diagnostic["status"] != "insuffisant":
            continue
        candidates = cards_db.find_candidates(
            identity, diagnostic["role"], exclude, max_price, format,
            limit=CANDIDATES_PER_ROLE, exclude_game_changers=exclude_game_changers,
        )
        if candidates:
            to_add.append({
                "role": diagnostic["role"],
                "label": ROLE_LABELS.get(diagnostic["role"], diagnostic["role"]),
                "missing": diagnostic["gap"],
                "reason": f"{diagnostic['count']} cartes pour un repère de {diagnostic['target']}",
                "candidates": candidates,
            })

    if not mana["lands_ok"] and mana["land_count"] < deck_analysis.RECOMMENDED_LANDS.start:
        missing = deck_analysis.RECOMMENDED_LANDS.start - mana["land_count"]
        candidates = cards_db.find_candidates(
            identity, categories.LAND, exclude, max_price, format,
            limit=CANDIDATES_PER_ROLE, exclude_game_changers=exclude_game_changers,
        )
        if candidates:
            to_add.insert(0, {
                "role": categories.LAND,
                "label": ROLE_LABELS[categories.LAND],
                "missing": missing,
                "reason": f"{mana['land_count']} terrains pour un repère de {mana['recommended_lands']}",
                "candidates": candidates,
            })

    to_cut = _cuts_for_surplus(cards, diagnostics)
    if target_bracket is not None:
        to_cut = cuts_for_bracket(cards, target_bracket) + to_cut

    return {
        "format": format,
        "max_price_eur": max_price,
        "target_bracket": target_bracket,
        "diagnostics": diagnostics,
        "manabase": mana,
        "to_add": to_add,
        "to_cut": to_cut,
    }
