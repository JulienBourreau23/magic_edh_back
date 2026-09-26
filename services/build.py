"""
services/build.py — l'atelier de construction, carte par carte.

Construire à la main, c'est le geste du classeur : on pose un commandant, on
regarde ce qui peut aller avec, on ajoute, on retire. Le site n'a donc rien à
décider ici — il propose, il compte, et il évalue. Trois services :

- le **vivier** : ce que la collection permet de mettre dans ce deck
  (`cards_db.buildable_pool`, filtré par identité de couleur et légalité) ;
- l'**assistance aux terrains**, qui réutilise exactement le calcul de la page
  « Monter 4 decks » (non-basiques possédés d'abord, puis basiques au prorata
  des symboles de mana réellement demandés) ;
- l'**évaluation**, qui est celle de la fiche de deck, à l'identique : un
  brouillon doit se lire avec les mêmes chiffres que le deck qu'il deviendra,
  sinon sauvegarder changerait le diagnostic.

**Rien n'est écrit en base tant que l'utilisateur ne le demande pas.** Le
brouillon vit dans le navigateur ; ces fonctions ne font que le mesurer.
"""
import db.cards as cards_db
import db.commanders as commanders_db
import db.decks as decks_db
from services import combos as combos_service
from services import deck_analysis, deck_plans, upcoming

# 36 terrains pour 99 cartes : le repère du format, celui que la page « Monter
# 4 decks » applique déjà. L'atelier laisse le régler, c'est un repère et non
# une règle.
DEFAULT_LAND_SLOTS = deck_plans.LAND_SLOTS


def draft_cards(entries: list[dict], commander_scryfall_id: str | None) -> list[dict]:
    """
    Les cartes d'un brouillon, prêtes à être analysées comme un vrai deck.

    Le brouillon n'arrive qu'en identifiants : le catalogue est relu ici, ce
    qui garantit que l'évaluation porte sur les mêmes colonnes que la fiche —
    texte oracle et corps de créature compris, dont dépendent bracket et duel.
    """
    quantities = {str(entry["scryfall_id"]): int(entry.get("quantity", 1)) for entry in entries}
    rows = decks_db.simulation_cards_by_id(list(quantities))
    cards = []
    for scryfall_id, quantity in quantities.items():
        row = rows.get(scryfall_id)
        if row is None:
            continue
        cards.append({**row, "quantity": quantity,
                      "is_commander": scryfall_id == str(commander_scryfall_id)})
    return cards


def evaluate(cards: list[dict], format: str) -> dict:
    """L'évaluation d'un brouillon : **exactement** celle de la fiche de deck."""
    return {
        "counts": {
            "total": sum(card["quantity"] for card in cards),
            "lands": sum(card["quantity"] for card in cards
                         if "Land" in (card["type_line"] or "")),
            "distinct": len(cards),
        },
        "mana_curve": deck_analysis.mana_curve(cards),
        "total_price_eur": deck_analysis.total_price_eur(cards),
        "legality_warnings": deck_analysis.legality_warnings(
            cards, format, upcoming.release_dates_for(cards, format), upcoming.today_paris(),
        ),
        "bracket": deck_analysis.bracket_estimate(cards, combos_service.find_in_deck(cards)),
        "manabase": deck_analysis.manabase(cards, deep=True),
        "role_diagnostics": deck_analysis.role_diagnostics(cards),
        "synergies": _synergies(cards),
    }


def _synergies(cards: list[dict]) -> list[dict]:
    commander = next((card for card in cards if card.get("is_commander")), None)
    if commander is None:
        return []
    return commanders_db.synergies_for_deck(
        str(commander["oracle_id"]),
        [str(card["oracle_id"]) for card in cards if not card.get("is_commander")],
    )


def land_assistance(commander: dict, chosen: list[dict], slots: int = DEFAULT_LAND_SLOTS,
                    format: str = "commander") -> dict:
    """
    Ce qu'il faut poser comme terrains, à coût nul.

    Même calcul que « Monter 4 decks » : les terrains **non-basiques possédés**
    d'abord — ils sont gratuits et meilleurs qu'un basique — puis les basiques
    au prorata des symboles de mana que le deck demande vraiment, commandant
    compris (c'est lui qu'il faut pouvoir lancer).

    Les cartes déjà choisies sont exclues du conseil : proposer un terrain déjà
    posé ferait passer le deck à 101 cartes sans que rien ne le signale.
    """
    deja = {str(card["oracle_id"]) for card in chosen}
    pool = [card for card in cards_db.buildable_pool(commander["color_identity"], format,
                                                     str(commander["oracle_id"]))
            if str(card["oracle_id"]) not in deja]
    available = {str(card["oracle_id"]): card["owned_quantity"] for card in pool}
    nonlands = [card for card in chosen if "Land" not in (card["type_line"] or "")]
    return deck_plans.land_plan(commander, pool, available, nonlands, slots)


def save(name: str, format: str, commander_scryfall_id: str | None,
         entries: list[dict]) -> int:
    """
    Enregistre le brouillon comme un vrai deck, et **seulement sur demande** :
    tant que ce bouton n'est pas cliqué, rien n'existe côté serveur.

    Rien n'est ajouté à la collection : les cartes posées viennent d'elle, les
    compter deux fois ferait disparaître des achats pourtant nécessaires.
    """
    deck_id = decks_db.create_deck(name, format)
    rows = [(str(entry["scryfall_id"]), int(entry.get("quantity", 1)),
             str(entry["scryfall_id"]) == str(commander_scryfall_id))
            for entry in entries]
    decks_db.add_deck_cards(deck_id, rows)
    if commander_scryfall_id:
        decks_db.set_commanders(deck_id, commander_scryfall_id)
    return deck_id
