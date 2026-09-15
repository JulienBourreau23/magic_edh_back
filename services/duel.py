"""
services/duel.py — duel simulé entre deux decks, sans IA.

CE QUE CE MODÈLE FAIT : il joue la boucle dominante d'une partie de Magic —
poser des terrains, déployer des créatures, retirer celles d'en face, attaquer,
bloquer, faire tomber les points de vie à zéro. Mana et couleurs sont calculés
exactement (même noyau que le reste du projet), les corps de créature sont les
vrais, les sorts de removal et les board wipes sont comptés.

CE QU'IL NE FAIT PAS, et c'est important : ni vol/piétinement/menace, ni
capacités activées ou déclenchées, ni jetons, ni moteurs de pioche, ni combos,
ni contresorts joués au bon moment, ni dégâts de commandant, ni politique.

La zone de commandement, elle, est modélisée : un commandant détruit y retourne
et se relance avec la taxe de 2 par relance. L'ignorer n'était pas une
simplification mais une erreur de règle — elle punissait deux fois les decks
qui subissent un board wipe.

Le biais qui en découle n'est pas du bruit, il a une direction connue : **ce
modèle favorise les decks dont la puissance est dans les corps de créature et
défavorise ceux dont la puissance est dans les moteurs, les combos ou le
contrôle**. Un taux de victoire sorti d'ici est une indication de rythme et de
pression, pas un pronostic de table.
"""
import random
from dataclasses import dataclass, field

from services.card_categories import BOARD_WIPE, LAND, RAMP, REMOVAL
from services.mana import can_pay, parse_mana_cost
from services.simulation import SimCard, draw_opening_hand, mana_amount, sources_in_play

COMMANDER_LIFE = 40
DUEL_COMMANDER_LIFE = 30
MAX_TURNS = 25
# Taxe de commandement : +2 de mana générique par relance déjà effectuée.
COMMANDER_TAX_STEP = 2


@dataclass(frozen=True)
class DuelCard(SimCard):
    """Une carte de simulation augmentée de son corps et de son rôle."""
    power: int = 0
    toughness: int = 0
    is_creature: bool = False
    is_removal: bool = False
    is_wipe: bool = False


def _stat(value: str | None) -> int:
    """Force/endurance : les valeurs variables (*, 1+*) sont comptées 0."""
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def to_duel_card(card: dict) -> DuelCard:
    categories = card.get("categories") or []
    produced = frozenset(card.get("produced_mana") or [])
    generic, pips = parse_mana_cost(card.get("mana_cost"))
    type_line = card.get("type_line") or ""
    return DuelCard(
        name=card["name"],
        is_land=LAND in categories,
        is_ramp=RAMP in categories and bool(produced),
        cmc=int(card.get("cmc") or 0),
        generic=generic,
        pips=tuple(pips),
        produces=produced,
        produces_amount=mana_amount(card.get("oracle_text")) if produced else 0,
        power=_stat(card.get("power")),
        toughness=_stat(card.get("toughness")),
        is_creature="Creature" in type_line,
        is_removal=REMOVAL in categories,
        is_wipe=BOARD_WIPE in categories,
    )


@dataclass
class Permanent:
    card: DuelCard
    summoning_sick: bool = True
    is_commander: bool = False


@dataclass
class Player:
    name: str
    library: list[DuelCard]
    commander: DuelCard | None
    life: int
    hand: list[DuelCard] = field(default_factory=list)
    mana_sources: list[DuelCard] = field(default_factory=list)
    creatures: list[Permanent] = field(default_factory=list)
    commander_cast: bool = False
    commander_tax: int = 0

    @property
    def sources(self) -> list[frozenset[str]]:
        return sources_in_play(self.mana_sources)

    @property
    def commander_cost(self) -> int:
        """Coût converti du commandant, taxe de commandement comprise."""
        return (self.commander.cmc if self.commander else 0) + self.commander_tax

    def can_cast_commander(self, used: int = 0) -> bool:
        if self.commander is None:
            return False
        available = self.sources
        return len(available) - used >= self.commander_cost and can_pay(
            self.commander.generic + self.commander_tax, list(self.commander.pips), available
        )

    def destroy(self, permanents: list[Permanent]) -> None:
        """
        Retire des créatures du champ de bataille. Le commandant n'est pas
        détruit : il retourne en zone de commandement, relançable une taxe plus
        cher. C'est la règle, et elle change le résultat d'un board wipe.
        """
        for permanent in permanents:
            if permanent in self.creatures:
                self.creatures.remove(permanent)
            if permanent.is_commander:
                self.commander_cast = False
                self.commander_tax += COMMANDER_TAX_STEP

    def can_cast(self, card: DuelCard, used: int = 0) -> bool:
        """
        Le mana dépensé dans le tour est suivi en quantité, mais les couleurs
        sont vérifiées sort par sort sur l'ensemble des sources. Léger
        optimisme quand on enchaîne plusieurs sorts très colorés dans le même
        tour ; l'alternative (retirer arbitrairement des sources déjà
        « utilisées ») fausserait davantage en supprimant justement celles qui
        produisent la bonne couleur.
        """
        available = self.sources
        return len(available) - used >= card.cmc and can_pay(
            card.generic, list(card.pips), available
        )


def build_player(name: str, cards: list[dict], rng: random.Random, life: int) -> Player:
    library: list[DuelCard] = []
    commander: DuelCard | None = None
    for card in cards:
        duel_card = to_duel_card(card)
        if card.get("is_commander"):
            commander = commander or duel_card
            continue
        library.extend([duel_card] * card.get("quantity", 1))

    hand, rest, _ = draw_opening_hand(rng, library)
    return Player(name=name, library=rest, commander=commander, life=life, hand=hand)


def _take_turn(player: Player, opponent: Player, turn: int, first_player: bool) -> None:
    if not (turn == 1 and first_player) and player.library:
        player.hand.append(player.library.pop(0))

    for permanent in player.creatures:
        permanent.summoning_sick = False

    land = next((card for card in player.hand if card.is_land), None)
    if land:
        player.hand.remove(land)
        player.mana_sources.append(land)

    _cast_phase(player, opponent)
    _combat_phase(player, opponent)


def _cast_phase(player: Player, opponent: Player) -> None:
    """
    Ordre de priorité volontairement simple et lisible : accélération, puis
    réponse au plateau adverse, puis développement du sien.
    """
    spent = 0

    for rock in sorted((c for c in player.hand if c.is_ramp and not c.is_land), key=lambda c: c.cmc):
        if player.can_cast(rock, spent):
            player.hand.remove(rock)
            player.mana_sources.append(rock)
            spent += rock.cmc

    if len(opponent.creatures) >= 3:
        wipe = next((c for c in player.hand if c.is_wipe and player.can_cast(c, spent)), None)
        if wipe:
            player.hand.remove(wipe)
            spent += wipe.cmc
            opponent.destroy(list(opponent.creatures))
            player.destroy(list(player.creatures))

    if opponent.creatures:
        removal = next((c for c in player.hand if c.is_removal and not c.is_creature
                        and player.can_cast(c, spent)), None)
        if removal:
            player.hand.remove(removal)
            spent += removal.cmc
            biggest = max(opponent.creatures, key=lambda p: p.card.power)
            opponent.destroy([biggest])

    # Le commandant d'abord : c'est le plan de jeu du deck.
    if player.commander and not player.commander_cast and player.can_cast_commander(spent):
        spent += player.commander_cost
        player.commander_cast = True
        if player.commander.is_creature:
            player.creatures.append(Permanent(player.commander, is_commander=True))

    for creature in sorted((c for c in player.hand if c.is_creature), key=lambda c: -c.power):
        if player.can_cast(creature, spent):
            player.hand.remove(creature)
            spent += creature.cmc
            player.creatures.append(Permanent(creature))


def _combat_phase(attacker: Player, defender: Player) -> None:
    attackers = sorted(
        (p for p in attacker.creatures if not p.summoning_sick and p.card.power > 0),
        key=lambda p: -p.card.power,
    )
    if not attackers:
        return

    available_blockers = list(defender.creatures)
    incoming = sum(p.card.power for p in attackers)
    lethal = incoming >= defender.life

    damage = 0
    for attacking in attackers:
        blocker = _choose_blocker(attacking, available_blockers, lethal)
        if blocker is None:
            damage += attacking.card.power
            continue

        available_blockers.remove(blocker)
        if attacking.card.power >= blocker.card.toughness:
            defender.destroy([blocker])
        if blocker.card.power >= attacking.card.toughness:
            attacker.destroy([attacking])

    defender.life -= damage


def _choose_blocker(attacking: Permanent, blockers: list[Permanent], lethal: bool) -> Permanent | None:
    """
    Bloque d'abord ce qu'on tue en survivant, puis ce qu'on tue en échangeant.
    Face à une attaque létale, on bloque avec n'importe quoi — la partie est
    perdue sinon.
    """
    survives_and_kills = [
        b for b in blockers
        if b.card.power >= attacking.card.toughness and b.card.toughness > attacking.card.power
    ]
    if survives_and_kills:
        return min(survives_and_kills, key=lambda b: b.card.power)

    trades = [b for b in blockers if b.card.power >= attacking.card.toughness]
    if trades:
        return min(trades, key=lambda b: b.card.power)

    return blockers[0] if lethal and blockers else None


def play_duel(cards_a: list[dict], cards_b: list[dict], rng: random.Random,
              starting_life: int) -> tuple[str | None, int]:
    """Renvoie (« a », « b » ou None pour une partie non conclue, nombre de tours)."""
    player_a = build_player("a", cards_a, rng, starting_life)
    player_b = build_player("b", cards_b, rng, starting_life)
    if not player_a.library or not player_b.library:
        return None, 0

    # Le joueur qui commence ne pioche pas au premier tour : c'est sa
    # compensation, et elle change le résultat, donc on alterne entre parties.
    for turn in range(1, MAX_TURNS + 1):
        _take_turn(player_a, player_b, turn, first_player=True)
        if player_b.life <= 0:
            return "a", turn
        _take_turn(player_b, player_a, turn, first_player=False)
        if player_a.life <= 0:
            return "b", turn

    return None, MAX_TURNS


def simulate_duels(cards_a: list[dict], cards_b: list[dict], iterations: int = 400,
                   seed: int = 0, starting_life: int = COMMANDER_LIFE) -> dict:
    """
    Moitié des parties avec A qui commence, moitié avec B : l'avantage du
    premier joueur est réel en duel, le neutraliser évite de le confondre avec
    la force du deck.
    """
    rng = random.Random(seed)
    wins = {"a": 0, "b": 0}
    unfinished = 0
    total_turns = 0

    for index in range(iterations):
        first, second = (cards_a, cards_b) if index % 2 == 0 else (cards_b, cards_a)
        winner, turns = play_duel(first, second, rng, starting_life)
        total_turns += turns

        if winner is None:
            unfinished += 1
        elif index % 2 == 0:
            wins[winner] += 1
        else:
            wins["b" if winner == "a" else "a"] += 1

    decided = wins["a"] + wins["b"]
    return {
        "iterations": iterations,
        "starting_life": starting_life,
        "win_rate_a": round(wins["a"] / iterations, 3),
        "win_rate_b": round(wins["b"] / iterations, 3),
        "unfinished_rate": round(unfinished / iterations, 3),
        "avg_turns": round(total_turns / iterations, 1) if iterations else 0,
        "decided": decided,
    }
