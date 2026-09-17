"""
services/duel.py — duel simulé entre deux decks, sans IA.

CE QUE CE MODÈLE FAIT : il joue la boucle dominante d'une partie de Magic —
poser des terrains, déployer des créatures, retirer celles d'en face, attaquer,
bloquer, faire tomber les points de vie à zéro. Mana et couleurs sont calculés
exactement (même noyau que le reste du projet) et les corps de créature sont
les vrais.

Le combat est joué avec ses règles, pas en additionnant des forces :
**vol et portée** (qui peut bloquer quoi), **menace** (deux bloqueurs ou
aucun), **initiative et double initiative** (l'ordre des dégâts décide qui
meurt), **contact mortel** (un point suffit), **piétinement** (l'excédent
passe), **lien de vie**, **indestructible**, **défenseur**, **célérité**, et
**vigilance** — qui n'est pas cosmétique : une créature qui attaque se
dégage tard, donc elle ne bloquera pas au tour suivant.

Sont aussi modélisés : les **dégâts de commandant** (21 d'un même commandant
font perdre), la **menace du linceul** qui protège du removal ciblé, les
**contresorts** gardés en réserve, la **pioche** apportée par un sort, et les
**combos gagnants à deux cartes** — quand les deux pièces sont disponibles et
le mana total payable, la partie est gagnée sur place.

CE QU'IL NE FAIT TOUJOURS PAS, et il faut le savoir : les capacités activées
et déclenchées en général. « Quand cette créature meurt, chaque joueur
sacrifie un terrain » est du texte libre, et l'exécuter demanderait un moteur
de règles complet. Même chose pour les jetons, les moteurs de pioche
récurrents, la politique, et bien sûr les erreurs de jeu.

Le biais résiduel garde une direction, mais elle est plus faible qu'avant :
le modèle reste plus à l'aise avec les decks qui gagnent par le combat et par
un combo identifié qu'avec ceux qui gagnent en accumulant de petits avantages
tour après tour. Un taux de victoire sorti d'ici est une mesure de rythme et
de pression, pas un pronostic de table.

La zone de commandement est modélisée : un commandant détruit y retourne et se
relance avec la taxe de 2 par relance. L'ignorer n'était pas une
simplification mais une erreur de règle — elle punissait deux fois les decks
qui subissent un board wipe.
"""
import random
import re
from dataclasses import dataclass, field

from services.card_categories import BOARD_WIPE, COUNTERSPELL, DRAW, LAND, RAMP, REMOVAL
from services.mana import can_pay, parse_mana_cost
from services.simulation import SimCard, draw_opening_hand, mana_amount, sources_in_play

COMMANDER_LIFE = 40
DUEL_COMMANDER_LIFE = 30
MAX_TURNS = 25
# Taxe de commandement : +2 de mana générique par relance déjà effectuée.
COMMANDER_TAX_STEP = 2
# 21 dégâts d'un même commandant font perdre la partie, quels que soient les
# points de vie restants. C'est une seconde horloge, et elle avantage les
# commandants gros et évasifs — exactement ce que le modèle ignorait avant.
COMMANDER_DAMAGE_LETHAL = 21
# En dessous de ce coût, on ne dépense pas un contresort : garder le contresort
# pour la vraie menace est le comportement le plus courant, et le contraire
# rendrait les contresorts absurdement rentables.
COUNTER_MIN_CMC = 3
# Une carte qui pioche ne pioche jamais plus que ça dans ce modèle : au-delà,
# le texte décrit presque toujours une condition qu'on ne sait pas évaluer.
MAX_DRAW_PER_SPELL = 3

_DRAW_RE = re.compile(r"draws? (a|one|two|three|four|five|\d+) cards?", re.I)
_WORD_TO_INT = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _draw_amount(oracle_text: str | None) -> int:
    """
    Combien de cartes ce sort fait piocher. « Draw X cards » renvoie 0 : X
    dépend d'un état qu'on ne sait pas évaluer, et l'estimer haut ferait de
    chaque sort à X un moteur.
    """
    match = _DRAW_RE.search(oracle_text or "")
    if not match:
        return 0
    quantity = match.group(1).lower()
    amount = _WORD_TO_INT.get(quantity)
    if amount is None:
        try:
            amount = int(quantity)
        except ValueError:
            return 0
    return min(amount, MAX_DRAW_PER_SPELL)


@dataclass(frozen=True)
class DuelCard(SimCard):
    """Une carte de simulation augmentée de son corps, son rôle et ses mots-clés."""
    oracle_id: str = ""
    power: int = 0
    toughness: int = 0
    is_creature: bool = False
    is_removal: bool = False
    is_wipe: bool = False
    is_counterspell: bool = False
    draws: int = 0
    # Mots-clés de combat, lus dans `cards.keywords` (Scryfall), donc constatés
    # et non devinés depuis le texte.
    flying: bool = False
    reach: bool = False
    trample: bool = False
    deathtouch: bool = False
    first_strike: bool = False
    double_strike: bool = False
    vigilance: bool = False
    lifelink: bool = False
    menace: bool = False
    indestructible: bool = False
    hexproof: bool = False
    haste: bool = False
    defender: bool = False

    @property
    def strikes_first(self) -> bool:
        return self.first_strike or self.double_strike


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
    keywords = {k.lower() for k in (card.get("keywords") or [])}
    text = card.get("oracle_text")

    return DuelCard(
        name=card["name"],
        is_land=LAND in categories,
        is_ramp=RAMP in categories and bool(produced),
        cmc=int(card.get("cmc") or 0),
        generic=generic,
        pips=tuple(pips),
        produces=produced,
        produces_amount=mana_amount(text) if produced else 0,
        oracle_id=str(card.get("oracle_id") or ""),
        power=_stat(card.get("power")),
        toughness=_stat(card.get("toughness")),
        is_creature="Creature" in type_line,
        is_removal=REMOVAL in categories,
        is_wipe=BOARD_WIPE in categories,
        is_counterspell=COUNTERSPELL in categories,
        draws=_draw_amount(text) if DRAW in categories else 0,
        flying="flying" in keywords,
        reach="reach" in keywords,
        trample="trample" in keywords,
        deathtouch="deathtouch" in keywords,
        first_strike="first strike" in keywords,
        double_strike="double strike" in keywords,
        vigilance="vigilance" in keywords,
        lifelink="lifelink" in keywords,
        menace="menace" in keywords,
        indestructible="indestructible" in keywords,
        hexproof="hexproof" in keywords,
        haste="haste" in keywords,
        defender="defender" in keywords,
    )


@dataclass
class Permanent:
    card: DuelCard
    summoning_sick: bool = True
    is_commander: bool = False
    # Une créature qui a attaqué reste engagée jusqu'à son prochain
    # dégagement : sans ça, tout le monde jouait comme s'il avait la vigilance,
    # et attaquer ne coûtait rien.
    tapped: bool = False

    @property
    def can_attack(self) -> bool:
        return (not self.tapped and not self.card.defender and self.card.power > 0
                and (not self.summoning_sick or self.card.haste))

    @property
    def can_block(self) -> bool:
        return not self.tapped


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
    # Dégâts reçus du commandant adverse : seconde condition de défaite.
    commander_damage: int = 0
    # Contresort gardé en réserve pour le tour adverse, et le mana qu'il
    # immobilise.
    counter_ready: DuelCard | None = None
    # Paires (identifiants des deux cartes, mana total) d'un combo qui gagne
    # la partie sur place.
    winning_combos: list[tuple[frozenset[str], int]] = field(default_factory=list)

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

    def destroy(self, permanents: list[Permanent], by_damage: bool = False) -> None:
        """
        Retire des créatures du champ de bataille. Le commandant n'est pas
        détruit : il retourne en zone de commandement, relançable une taxe plus
        cher. C'est la règle, et elle change le résultat d'un board wipe.

        `by_damage` distingue les dégâts du reste : indestructible survit aux
        dégâts et aux board wipes qui détruisent, mais le modèle n'ayant que
        ces deux sources de mort, la carte devient tout simplement increvable —
        ce qui est presque vrai.
        """
        for permanent in permanents:
            if permanent.card.indestructible:
                continue
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

    def draw(self, count: int = 1) -> None:
        for _ in range(count):
            if self.library:
                self.hand.append(self.library.pop(0))

    def on_battlefield_or_hand(self) -> set[str]:
        """
        Les cartes qu'on peut mettre en jeu maintenant ou qui y sont déjà. Sert
        à constater qu'un combo est en place : une pièce en main compte, sinon
        seuls les combos déjà posés seraient vus, c'est-à-dire presque jamais.
        """
        ids = {card.oracle_id for card in self.hand}
        ids |= {p.card.oracle_id for p in self.creatures}
        ids |= {card.oracle_id for card in self.mana_sources}
        if self.commander is not None:
            ids.add(self.commander.oracle_id)
        return ids - {""}

    def combo_ready(self) -> bool:
        """
        Un combo gagnant est exécutable quand ses deux pièces sont disponibles
        **et** que le mana total (lancer les deux cartes puis exécuter) est
        payable ce tour-ci. C'est exactement le chiffre que la fiche de deck
        affiche déjà à côté du combo : le même critère décide ici.
        """
        if not self.winning_combos:
            return False
        available = self.on_battlefield_or_hand()
        mana = len(self.sources)
        return any(pieces <= available and cost <= mana
                   for pieces, cost in self.winning_combos)


def build_player(name: str, cards: list[dict], rng: random.Random, life: int,
                 winning_combos: list[tuple[frozenset[str], int]] | None = None) -> Player:
    library: list[DuelCard] = []
    commander: DuelCard | None = None
    for card in cards:
        duel_card = to_duel_card(card)
        if card.get("is_commander"):
            commander = commander or duel_card
            continue
        library.extend([duel_card] * card.get("quantity", 1))

    hand, rest, _ = draw_opening_hand(rng, library)
    return Player(name=name, library=rest, commander=commander, life=life, hand=hand,
                  winning_combos=list(winning_combos or []))


def _untap(player: Player) -> None:
    for permanent in player.creatures:
        permanent.summoning_sick = False
        permanent.tapped = False


def _take_turn(player: Player, opponent: Player, turn: int, first_player: bool) -> None:
    _untap(player)
    # Le contresort gardé pour le tour adverse a servi ou non : il ne mobilise
    # plus rien pendant son propre tour.
    player.counter_ready = None

    if not (turn == 1 and first_player) and player.library:
        player.draw()

    land = next((card for card in player.hand if card.is_land), None)
    if land:
        player.hand.remove(land)
        player.mana_sources.append(land)

    _cast_phase(player, opponent)
    _combat_phase(player, opponent)


def _countered(defender: Player, card: DuelCard) -> bool:
    """
    Le contresort gardé en réserve part sur la première menace qui en vaut la
    peine. Le seuil évite de dépenser un contresort sur un rocher de mana, ce
    qui rendrait les contresorts à la fois omniprésents et inutiles.
    """
    if defender.counter_ready is None or card.cmc < COUNTER_MIN_CMC:
        return False
    defender.counter_ready = None
    return True


def _cast_phase(player: Player, opponent: Player) -> None:
    """
    Ordre de priorité volontairement simple et lisible : accélération, puis
    réponse au plateau adverse, puis développement du sien. Le contresort
    adverse s'interpose sur les sorts qui comptent.
    """
    spent = 0

    for rock in sorted((c for c in player.hand if c.is_ramp and not c.is_land), key=lambda c: c.cmc):
        if player.can_cast(rock, spent):
            player.hand.remove(rock)
            player.mana_sources.append(rock)
            spent += rock.cmc

    # Piocher avant de décider du reste : une carte de plus peut changer le
    # tour, et c'est précisément ce que le modèle ne voyait pas.
    for spell in sorted((c for c in player.hand if c.draws and not c.is_creature),
                        key=lambda c: c.cmc):
        if player.can_cast(spell, spent):
            player.hand.remove(spell)
            spent += spell.cmc
            if not _countered(opponent, spell):
                player.draw(spell.draws)

    if len(opponent.creatures) >= 3:
        wipe = next((c for c in player.hand if c.is_wipe and player.can_cast(c, spent)), None)
        if wipe:
            player.hand.remove(wipe)
            spent += wipe.cmc
            if not _countered(opponent, wipe):
                opponent.destroy(list(opponent.creatures))
                player.destroy(list(player.creatures))

    if opponent.creatures:
        removal = next((c for c in player.hand if c.is_removal and not c.is_creature
                        and player.can_cast(c, spent)), None)
        # Le linceul protège du removal ciblé : la menace visée est la plus
        # grosse **que l'on peut viser**.
        targets = [p for p in opponent.creatures if not p.card.hexproof]
        if removal and targets:
            player.hand.remove(removal)
            spent += removal.cmc
            if not _countered(opponent, removal):
                opponent.destroy([max(targets, key=lambda p: p.card.power)])

    # Le commandant d'abord : c'est le plan de jeu du deck.
    if player.commander and not player.commander_cast and player.can_cast_commander(spent):
        spent += player.commander_cost
        if not _countered(opponent, player.commander):
            player.commander_cast = True
            if player.commander.is_creature:
                player.creatures.append(Permanent(player.commander, is_commander=True))

    for creature in sorted((c for c in player.hand if c.is_creature), key=lambda c: -c.power):
        if player.can_cast(creature, spent):
            player.hand.remove(creature)
            spent += creature.cmc
            if _countered(opponent, creature):
                continue
            player.creatures.append(Permanent(creature))
            if creature.draws:
                player.draw(creature.draws)

    # Ce qui reste de mana garde un contresort prêt pour le tour adverse.
    counter = next((c for c in player.hand if c.is_counterspell
                    and player.can_cast(c, spent)), None)
    if counter is not None:
        player.hand.remove(counter)
        player.counter_ready = counter


def _legal_blockers(attacking: Permanent, blockers: list[Permanent]) -> list[Permanent]:
    """Qui a le droit de bloquer cet attaquant."""
    if attacking.card.flying:
        return [b for b in blockers if b.card.flying or b.card.reach]
    return list(blockers)


def _lethal(source: DuelCard, target: DuelCard, damage: int) -> bool:
    """Un point suffit avec le contact mortel ; l'indestructible ne meurt pas."""
    if target.indestructible or damage <= 0:
        return False
    return source.deathtouch or damage >= target.toughness


def _resolve_block(attacking: Permanent, blocker: Permanent,
                   attacker: Player, defender: Player) -> int:
    """
    Résout un combat bloqué et renvoie les dégâts qui passent au joueur
    (piétinement uniquement).

    L'initiative n'est pas un détail : elle décide qui meurt avant d'avoir
    frappé. La double initiative frappe aux deux étapes, donc inflige sa force
    deux fois.
    """
    a_card, b_card = attacking.card, blocker.card
    a_damage = a_card.power * (2 if a_card.double_strike else 1)

    a_first = a_card.strikes_first and not b_card.strikes_first
    b_first = b_card.strikes_first and not a_card.strikes_first

    blocker_dies = _lethal(a_card, b_card, a_card.power)
    attacker_dies = _lethal(b_card, a_card, b_card.power)

    if a_first and blocker_dies:
        attacker_dies = False       # le bloqueur meurt avant de frapper
    if b_first and attacker_dies:
        blocker_dies = False

    if blocker_dies:
        defender.destroy([blocker], by_damage=True)
    if attacker_dies:
        attacker.destroy([attacking], by_damage=True)

    if a_card.lifelink:
        attacker.life += a_damage

    if a_card.trample and blocker_dies:
        return max(0, a_damage - b_card.toughness)
    return 0


def _combat_phase(attacker: Player, defender: Player) -> None:
    attackers = sorted((p for p in attacker.creatures if p.can_attack),
                       key=lambda p: -p.card.power)
    if not attackers:
        return

    available_blockers = [p for p in defender.creatures if p.can_block]
    incoming = sum(p.card.power for p in attackers)
    lethal = incoming >= defender.life

    for attacking in attackers:
        # Attaquer engage, sauf vigilance : la créature ne bloquera pas au tour
        # suivant. C'est le vrai coût d'une attaque, et il manquait.
        if not attacking.card.vigilance:
            attacking.tapped = True

        legal = _legal_blockers(attacking, available_blockers)
        # La menace demande deux bloqueurs : avec un seul disponible, elle
        # passe. Le modèle ne bloquant qu'à une créature, on traite le cas en
        # exigeant qu'il en reste assez, puis on en consomme deux.
        needed = 2 if attacking.card.menace else 1
        blocker = (_choose_blocker(attacking, legal, lethal)
                   if len(legal) >= needed else None)

        if blocker is None:
            damage = attacking.card.power * (2 if attacking.card.double_strike else 1)
            _damage_player(attacker, defender, attacking, damage)
            continue

        available_blockers.remove(blocker)
        if needed == 2:
            # Le second bloqueur est immobilisé sans être résolu : il ne peut
            # plus arrêter un autre attaquant, ce qui est l'essentiel de la
            # menace.
            second = next((b for b in _legal_blockers(attacking, available_blockers)), None)
            if second is not None:
                available_blockers.remove(second)

        trampled = _resolve_block(attacking, blocker, attacker, defender)
        if trampled:
            _damage_player(attacker, defender, attacking, trampled)


def _damage_player(attacker: Player, defender: Player,
                   source: Permanent, damage: int) -> None:
    """
    Les dégâts au joueur, avec les deux effets qui s'y accrochent : le lien de
    vie, et le compteur de dégâts de commandant — 21 d'un même commandant font
    perdre indépendamment des points de vie.
    """
    if damage <= 0:
        return
    defender.life -= damage
    if source.is_commander:
        defender.commander_damage += damage
    if source.card.lifelink:
        attacker.life += damage


def _choose_blocker(attacking: Permanent, blockers: list[Permanent],
                    lethal: bool) -> Permanent | None:
    """
    Bloque d'abord ce qu'on tue en survivant, puis ce qu'on tue en échangeant.
    Face à une attaque létale, on bloque avec n'importe quoi — la partie est
    perdue sinon.
    """
    if not blockers:
        return None

    survives_and_kills = [
        b for b in blockers
        if _lethal(b.card, attacking.card, b.card.power)
        and not _lethal(attacking.card, b.card, attacking.card.power)
    ]
    if survives_and_kills:
        return min(survives_and_kills, key=lambda b: b.card.power)

    trades = [b for b in blockers if _lethal(b.card, attacking.card, b.card.power)]
    if trades:
        return min(trades, key=lambda b: b.card.power)

    return blockers[0] if lethal else None


def _defeated(player: Player) -> bool:
    return player.life <= 0 or player.commander_damage >= COMMANDER_DAMAGE_LETHAL


def play_duel(cards_a: list[dict], cards_b: list[dict], rng: random.Random,
              starting_life: int,
              combos_a: list[tuple[frozenset[str], int]] | None = None,
              combos_b: list[tuple[frozenset[str], int]] | None = None
              ) -> tuple[str | None, int]:
    """Renvoie (« a », « b » ou None pour une partie non conclue, nombre de tours)."""
    player_a = build_player("a", cards_a, rng, starting_life, combos_a)
    player_b = build_player("b", cards_b, rng, starting_life, combos_b)
    if not player_a.library or not player_b.library:
        return None, 0

    # Le joueur qui commence ne pioche pas au premier tour : c'est sa
    # compensation, et elle change le résultat, donc on alterne entre parties.
    for turn in range(1, MAX_TURNS + 1):
        _take_turn(player_a, player_b, turn, first_player=True)
        if player_a.combo_ready():
            return "a", turn
        if _defeated(player_b):
            return "a", turn

        _take_turn(player_b, player_a, turn, first_player=False)
        if player_b.combo_ready():
            return "b", turn
        if _defeated(player_a):
            return "b", turn

    return None, MAX_TURNS


def winning_combo_pairs(combos: list[dict] | None) -> list[tuple[frozenset[str], int]]:
    """
    Ne garde que les combos qui **gagnent la partie sur place**, avec leur mana
    total. C'est le même tri que pour le plancher de bracket : un mana infini
    demande une troisième carte, il ne finit pas la partie.
    """
    return [
        (frozenset(combo["oracle_ids"]), int(combo["total_mana_value"]))
        for combo in (combos or [])
        if combo.get("wins_outright") and len(combo.get("oracle_ids", [])) == 2
    ]


def simulate_duels(cards_a: list[dict], cards_b: list[dict], iterations: int = 400,
                   seed: int = 0, starting_life: int = COMMANDER_LIFE,
                   combos_a: list[dict] | None = None,
                   combos_b: list[dict] | None = None) -> dict:
    """
    Moitié des parties avec A qui commence, moitié avec B : l'avantage du
    premier joueur est réel en duel, le neutraliser évite de le confondre avec
    la force du deck.
    """
    rng = random.Random(seed)
    pairs_a = winning_combo_pairs(combos_a)
    pairs_b = winning_combo_pairs(combos_b)
    wins = {"a": 0, "b": 0}
    unfinished = 0
    total_turns = 0

    for index in range(iterations):
        if index % 2 == 0:
            first, second, first_combos, second_combos = cards_a, cards_b, pairs_a, pairs_b
        else:
            first, second, first_combos, second_combos = cards_b, cards_a, pairs_b, pairs_a

        winner, turns = play_duel(first, second, rng, starting_life,
                                  first_combos, second_combos)
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
