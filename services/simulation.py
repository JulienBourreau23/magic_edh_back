"""
services/simulation.py — simulation de parties en solitaire (goldfish).

Entièrement déterministe : on tire des mains au hasard et on compte. Aucune IA
n'intervient ici, et c'est volontaire — la vitesse et la régularité d'un deck
sont des grandeurs mesurables, pas une question d'appréciation. Une même graine
redonne exactement les mêmes résultats, ce qui rend l'affichage stable d'un
rechargement à l'autre et les tests reproductibles.

Modèle et simplifications assumées :
  - on joue en premier (pas de pioche au tour 1), c'est le cas défavorable ;
  - mulligan londonien, on garde une main de 2 à 5 terrains, 2 mulligans max ;
  - un terrain posé par tour, puis les rochers de mana lancés du moins cher au
    plus cher tant que le mana suffit ;
  - pas d'interaction adverse, pas de pioche conditionnelle, pas de terrains
    qui arrivent engagés : on mesure la courbe de départ, pas une partie réelle.
"""
import random
import re
from dataclasses import dataclass

from services.card_categories import LAND, RAMP
from services.mana import can_pay, parse_mana_cost

DEFAULT_ITERATIONS = 1000
HORIZON_TURNS = 10
MAX_MULLIGANS = 2
KEEPABLE_LANDS = range(2, 6)

_ADD_MANA_RE = re.compile(r"add ((?:\{[^}]+\}\s*)+)", re.I)
_SYMBOL_RE = re.compile(r"\{[^}]+\}")


@dataclass(frozen=True)
class SimCard:
    """Projection minimale d'une carte, préparée une fois avant les tirages."""
    name: str
    is_land: bool
    is_ramp: bool
    cmc: int
    generic: int
    pips: tuple[frozenset[str], ...]
    produces: frozenset[str]
    produces_amount: int


def mana_amount(oracle_text: str | None) -> int:
    """Combien de mana la source ajoute (Sol Ring -> 2). 1 par défaut."""
    amounts = [len(_SYMBOL_RE.findall(match)) for match in _ADD_MANA_RE.findall(oracle_text or "")]
    return max(amounts, default=1)


def to_sim_card(card: dict) -> SimCard:
    categories = card.get("categories") or []
    produced = frozenset(card.get("produced_mana") or [])
    generic, pips = parse_mana_cost(card.get("mana_cost"))
    return SimCard(
        name=card["name"],
        is_land=LAND in categories,
        is_ramp=RAMP in categories and bool(produced),
        cmc=int(card.get("cmc") or 0),
        generic=generic,
        pips=tuple(pips),
        produces=produced,
        produces_amount=mana_amount(card.get("oracle_text")) if produced else 0,
    )


def build_library(cards: list[dict]) -> tuple[list[SimCard], SimCard | None]:
    """Développe le deck en une liste de cartes (hors commandant)."""
    library: list[SimCard] = []
    commander: SimCard | None = None
    for card in cards:
        sim_card = to_sim_card(card)
        if card.get("is_commander"):
            commander = commander or sim_card
            continue
        library.extend([sim_card] * card.get("quantity", 1))
    return library, commander


def sources_in_play(permanents: list[SimCard]) -> list[frozenset[str]]:
    """Une entrée par mana disponible : un Sol Ring compte pour deux {C}."""
    sources: list[frozenset[str]] = []
    for permanent in permanents:
        colors = permanent.produces or frozenset("C")
        sources.extend([colors] * max(permanent.produces_amount, 1))
    return sources


def _keep(hand: list[SimCard]) -> bool:
    return sum(card.is_land for card in hand) in KEEPABLE_LANDS


def _bottom(hand: list[SimCard], count: int) -> tuple[list[SimCard], list[SimCard]]:
    """
    Mulligan londonien : renvoie (main gardée, cartes remises au-dessous). Ce
    sont les plus chères qui descendent, ou les terrains en trop. Les cartes
    rendues repassent vraiment sous la bibliothèque — les jeter ferait un deck
    plus petit à chaque mulligan.
    """
    if count <= 0:
        return hand, []
    lands = [card for card in hand if card.is_land]
    ordered = sorted(hand, key=lambda card: (card.is_land and len(lands) <= 4, -card.cmc))
    return ordered[count:], ordered[:count]


def draw_opening_hand(rng: random.Random, library: list[SimCard]) -> tuple[list[SimCard], list[SimCard], int]:
    """Applique le mulligan londonien, renvoie (main, reste de la bibliothèque, mulligans)."""
    for mulligans in range(MAX_MULLIGANS + 1):
        shuffled = library[:]
        rng.shuffle(shuffled)
        hand, rest = shuffled[:7], shuffled[7:]
        if _keep(hand) or mulligans == MAX_MULLIGANS:
            kept, bottomed = _bottom(hand, mulligans)
            return kept, rest + bottomed, mulligans
    raise AssertionError("boucle de mulligan sans issue")  # pragma: no cover


@dataclass
class GameResult:
    mulligans: int
    opening_lands: int
    commander_turn: int | None
    mana_by_turn: list[int]
    mana_when_commander_missed: int


def play_one(rng: random.Random, library: list[SimCard], commander: SimCard | None) -> GameResult:
    hand, deck, mulligans = draw_opening_hand(rng, library)
    opening_lands = sum(card.is_land for card in hand)

    battlefield: list[SimCard] = []
    commander_turn: int | None = None
    mana_by_turn: list[int] = []
    mana_when_missed = 0

    for turn in range(1, HORIZON_TURNS + 1):
        if turn > 1 and deck:
            hand.append(deck.pop(0))

        land = next((card for card in hand if card.is_land), None)
        if land:
            hand.remove(land)
            battlefield.append(land)

        # Rochers de mana, du moins cher au plus cher tant qu'on peut payer.
        for rock in sorted((c for c in hand if c.is_ramp), key=lambda c: c.cmc):
            sources = sources_in_play(battlefield)
            if can_pay(rock.generic, list(rock.pips), sources):
                hand.remove(rock)
                battlefield.append(rock)

        sources = sources_in_play(battlefield)
        mana_by_turn.append(len(sources))

        if commander and commander_turn is None:
            if can_pay(commander.generic, list(commander.pips), sources):
                commander_turn = turn
            elif len(sources) >= commander.cmc:
                # Assez de mana mais pas les bonnes couleurs : c'est un
                # problème de manabase, pas de vitesse.
                mana_when_missed = max(mana_when_missed, len(sources))

    return GameResult(mulligans, opening_lands, commander_turn, mana_by_turn, mana_when_missed)


def play_games(cards: list[dict], iterations: int, seed: int) -> list[GameResult]:
    """Parties individuelles, exposées pour les comparaisons tête-à-tête."""
    library, commander = build_library(cards)
    if len(library) < 7:
        return []
    rng = random.Random(seed)
    return [play_one(rng, library, commander) for _ in range(iterations)]


def simulate(cards: list[dict], iterations: int = DEFAULT_ITERATIONS, seed: int = 0) -> dict:
    """Agrège `iterations` parties en solitaire et renvoie les métriques du deck."""
    library, commander = build_library(cards)
    if len(library) < 7:
        return {"error": "deck trop petit pour être simulé"}

    rng = random.Random(seed)
    results = [play_one(rng, library, commander) for _ in range(iterations)]

    commander_turns = [r.commander_turn for r in results if r.commander_turn]
    cast_by_turn = {
        turn: round(sum(1 for t in commander_turns if t <= turn) / iterations, 3)
        for turn in range(1, 9)
    }

    return {
        "iterations": iterations,
        "commander": commander.name if commander else None,
        "keep_seven_rate": round(sum(1 for r in results if r.mulligans == 0) / iterations, 3),
        "avg_mulligans": round(sum(r.mulligans for r in results) / iterations, 2),
        "avg_opening_lands": round(sum(r.opening_lands for r in results) / iterations, 2),
        "avg_commander_turn": round(sum(commander_turns) / len(commander_turns), 2) if commander_turns else None,
        "commander_cast_rate": round(len(commander_turns) / iterations, 3),
        "commander_cast_by_turn": cast_by_turn,
        "avg_mana_by_turn": {
            turn: round(sum(r.mana_by_turn[turn - 1] for r in results) / iterations, 2)
            for turn in range(1, 9)
        },
        "color_screw_rate": round(sum(1 for r in results if r.mana_when_commander_missed) / iterations, 3),
    }


def sample_opening(cards: list[dict], seed: int = 0, draws: int = 5) -> dict:
    """
    Une main de départ concrète + les pioches suivantes, pour l'affichage avec
    les images. Sert à visualiser ce que la simulation mesure en masse.
    """
    by_name = {card["name"]: card for card in cards}
    library, _ = build_library(cards)
    if len(library) < 7:
        return {"error": "deck trop petit pour être simulé"}

    rng = random.Random(seed)
    hand, deck, mulligans = draw_opening_hand(rng, library)

    def describe(sim_cards: list[SimCard]) -> list[dict]:
        return [by_name[card.name] for card in sim_cards if card.name in by_name]

    return {
        "mulligans": mulligans,
        "kept": _keep(hand),
        "lands_in_hand": sum(card.is_land for card in hand),
        "hand": describe(hand),
        "draws": describe(deck[:draws]),
    }
