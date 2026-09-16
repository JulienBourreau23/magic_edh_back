"""
services/deck_analysis.py — analyse statique d'un deck : courbe, prix, légalité,
manabase et estimation de bracket. Tout est calculé, rien n'est estimé par une IA.
"""
from services import card_categories as categories, simulation
from services.mana import (BASIC_LAND_BY_COLOR, COLORS, color_requirements,
                           miss_probability, parse_mana_cost, sources_needed)

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
# Part des cartes d'une couleur que la manabase doit soutenir à l'heure. Le
# reste — le quart le plus exigeant — attendra un tour de plus, ce qu'un joueur
# fait de toute façon. Sans ce garde-fou, une seule carte à trois symboles au
# tour 7 fixerait à elle seule une cible que le deck ne peut pas atteindre.
COVERED_SHARE = 0.75
# En deçà de ce manque, l'écart à la cible n'est pas signalé : les cibles sont
# des repères, pas des mesures, et crier pour une source d'écart les
# décrédibiliserait.
TOLERATED_SHORTFALL = 2
# Combien de cartes mal servies on nomme. Au-delà, la liste cesse d'être un
# diagnostic : le compte total dit déjà l'ampleur.
STRAINED_CARDS_SHOWN = 6
# Graine des simulations de contrôle. Fixe, comme partout dans le projet : deux
# consultations de la même fiche doivent donner le même conseil. Les deux
# variantes comparées partagent la graine, si bien que leur **écart** est bien
# plus précis que chacune des deux mesures prise seule.
MANABASE_SEED = 0
# Gain mesuré en deçà duquel on ne conseille rien. Remanier quatre terrains pour
# un dixième de point n'est pas un conseil, c'est du bruit de simulation : le
# joueur défait sa manabase sans rien y gagner.
MIN_MEASURED_GAIN = 0.005


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


def availability(card: dict, turn: int) -> float:
    """
    Probabilité que la carte soit en main au tour visé.

    Sans elle, le calcul traite les 99 cartes comme si toutes étaient en main,
    ce qui écrase le commandant : il est dans la zone de commandement à chaque
    tour, là où une carte du deck n'est vue qu'une fois sur sept au tour 3. Un
    Jeskai dont seul le commandant demande du rouge se retrouvait alors conseillé
    à trois Montagnes — le modèle ne voyait qu'une carte rouge sur 99, alors que
    c'est la carte qu'on lance le plus souvent.
    """
    if card.get("is_commander"):
        return 1.0
    return min(1.0, (6 + turn) / (COMMANDER_DECK_SIZE - 1))


def _demands_by_color(nonland: list[dict], identity: set[str]) -> dict:
    """
    {couleur: [{pips, turn, quantity, needed, card}]} — tout ce que la manabase
    doit soutenir, en une passe.

    Le tour visé est `max(cmc, symboles)` : on ne lance pas un {W}{W}{W} avant
    le tour 3, quel que soit son coût converti. Un pip hybride compte pour ses
    deux couleurs, cas défavorable cohérent avec `parse_mana_cost` — cela
    surestime la demande d'un deck bâti sur des hybrides.
    """
    table = {color: [] for color in identity}
    for card in nonland:
        _, pips = parse_mana_cost(card.get("mana_cost"))
        for color, demands in table.items():
            count = sum(1 for pip in pips if color in pip)
            if not count:
                continue
            turn = max(int(card.get("cmc") or 0), count)
            demands.append({"pips": count, "turn": turn,
                            "quantity": card.get("quantity", 1),
                            "available": availability(card, turn),
                            "needed": sources_needed(count, turn), "card": card})
    return table


def _color_target(demands: list[dict]) -> int:
    """Sources conseillées : de quoi soutenir `COVERED_SHARE` des cartes de la couleur."""
    if not demands:
        return 0
    total = sum(demand["quantity"] for demand in demands)
    covered = 0
    for demand in sorted(demands, key=lambda demand: demand["needed"]):
        covered += demand["quantity"]
        if covered >= total * COVERED_SHARE:
            return demand["needed"]
    return max(demand["needed"] for demand in demands)  # pragma: no cover


def _with_basics(cards: list[dict], by_color: dict) -> list[dict]:
    """Le même deck avec d'autres quantités de terrains de base."""
    variant = []
    for card in cards:
        if categories.is_basic_land(card):
            colors = [c for c in (card.get("produced_mana") or []) if c in by_color]
            if colors:
                card = {**card, "quantity": by_color[colors[0]]}
                if card["quantity"] == 0:
                    continue
        variant.append(card)
    return variant


def manabase(cards: list[dict], deep: bool = False) -> dict:
    """
    Terrains, sources par couleur et besoins en pips — le socle de tout conseil.

    `deep` ajoute deux simulations de contrôle (~200 ms) : elles mesurent ce que
    l'estimation analytique ne sait pas voir, à savoir qu'une duale W/U ne paie
    qu'un symbole à la fois. Les pages qui conseillent les activent ; celles qui
    ne montrent que la répartition des couleurs s'en passent.

    Une couleur est jugée sous-alimentée par rapport à **sa propre demande**, et
    non contre un plancher commun : un plancher absolu laissait passer 16
    sources bleues pour 51 symboles bleus tout en trouvant normales 19 sources
    rouges pour 11 symboles. La cible vient de `mana.sources_needed`, donc d'un
    calcul, et les cartes que la manabase ne soutient pas sont nommées.
    """
    land_count = sum(c["quantity"] for c in cards if categories.is_land(c))
    nonland = [c for c in cards if not categories.is_land(c)]

    sources = dict.fromkeys(COLORS, 0)
    for card in cards:
        for color in card.get("produced_mana") or []:
            if color in sources:
                sources[color] += card["quantity"]

    requirements = color_requirements(nonland)
    identity = commander_identity(cards) or set(requirements)

    by_color = _demands_by_color(nonland, identity)
    ready = _sources_by_turn(cards, identity)
    colors, strained = {}, []
    for color in sorted(identity):
        demands = by_color[color]
        target = _color_target(demands)
        shortfall = max(0, target - sources[color])
        colors[color] = {
            "sources": sources[color],
            "pips": requirements.get(color, 0),
            "target": target,
            "shortfall": shortfall,
            "under_supplied": shortfall > TOLERATED_SHORTFALL,
        }
        if shortfall > TOLERATED_SHORTFALL:
            strained += [
                {"name": display_name(demand["card"]),
                 "mana_cost": demand["card"].get("mana_cost"),
                 "color": color, "needed": demand["needed"], "sources": sources[color]}
                for demand in demands if demand["needed"] > sources[color]
            ]

    # Les plus mal servies d'abord : ce sont elles qui restent en main.
    strained.sort(key=lambda entry: entry["sources"] - entry["needed"])

    advice = basic_land_advice(cards, colors, by_color, ready)
    measured = None
    if deep:
        measured = round(simulation.color_stuck_rate(cards, seed=MANABASE_SEED), 3)
        if advice:
            by_basic = {color: advice["suggested"].get(BASIC_LAND_BY_COLOR[color], 0)
                        for color in colors if color in BASIC_LAND_BY_COLOR}
            after = simulation.color_stuck_rate(_with_basics(cards, by_basic),
                                                seed=MANABASE_SEED)
            advice["measured_before"] = measured
            advice["measured_after"] = round(after, 3)
            # Le glouton raisonne couleur par couleur ; la simulation voit les
            # sources partagées. Quand elles se contredisent, c'est la
            # simulation qui tranche — et on ne conseille rien.
            advice["confirmed"] = measured - after >= MIN_MEASURED_GAIN

    return {
        "land_count": land_count,
        "recommended_lands": f"{RECOMMENDED_LANDS.start}-{RECOMMENDED_LANDS.stop - 1}",
        "lands_ok": land_count in RECOMMENDED_LANDS,
        "colors": colors,
        "strained_cards": strained[:STRAINED_CARDS_SHOWN],
        "strained_total": len(strained),
        "basic_lands": advice,
        "stuck_cards": round(expected_stuck_cards(by_color, ready), 1),
        "measured_stuck_rate": measured,
        # Les cartes sans identité de couleur n'entrent pas dans la répartition
        # par couleur : elles sont comptées à part plutôt que de recevoir une
        # part de camembert grise qui n'aurait pas de sens.
        "colorless_cards": sum(c["quantity"] for c in cards if not c["color_identity"]),
    }


def _sources_by_turn(cards: list[dict], identity: set[str]) -> dict:
    """
    Par couleur, le tour à partir duquel chaque source peut produire du mana.

    Un rocher de mana **est** une source de couleur — un Cachet d'Azorius sert
    le blanc comme une Plaine — mais pas au même moment : il faut d'abord le
    lancer. Le compter disponible dès le tour 1, comme un terrain, surestimait
    la stabilité de tout deck à rochers.
    """
    table = {color: [] for color in identity}
    for card in cards:
        produced = [color for color in (card.get("produced_mana") or []) if color in table]
        if not produced:
            continue
        ready = 1 if categories.is_land(card) else int(card.get("cmc") or 0) + 1
        for color in produced:
            table[color].extend([ready] * card["quantity"])
    return table


def _available(ready_turns: list[int], turn: int) -> int:
    return sum(1 for ready in ready_turns if ready <= turn)


def expected_stuck_cards(demands: dict, sources_ready: dict) -> float:
    """
    Nombre de cartes que les couleurs laissent bloquées **en main**, en
    espérance, si le deck jouait chaque sort à son tour.

    C'est la seule fonction objectif qui compare des couleurs entre elles sans
    les traiter séparément. Une cible par couleur ne le peut pas : elle ignore
    **combien** de cartes en dépendent. Dans un Jeskai à 51 symboles bleus et
    20 blancs, viser une cible blanche haute (les doubles blancs sont exigeants)
    et une cible bleue basse (les sorts bleus sont surtout simples) conseille de
    nourrir le blanc — alors que chaque source retirée au bleu coûte deux fois
    plus de cartes bloquées. Compter les cartes tranche, les ratios non.
    """
    return sum(demand["quantity"] * demand["available"]
               * miss_probability(demand["pips"], demand["turn"],
                                  _available(sources_ready.get(color, []), demand["turn"]))
               for color, color_demands in demands.items()
               for demand in color_demands)


def basic_land_advice(cards: list[dict], colors: dict, demands: dict,
                      ready: dict) -> dict | None:
    """
    Répartition conseillée des terrains de base, ou None s'il n'y a rien à dire.

    Les basiques sont le seul levier gratuit d'une manabase : les échanger ne
    coûte ni argent ni emplacement, et le nombre de terrains ne bouge pas — ce
    n'est jamais un conseil d'achat. On les replace un par un, chacun allant à
    la couleur qui fait le plus baisser `expected_stuck_cards`. Le glouton n'est
    pas garanti optimal, mais chaque étape est vérifiable à la main et le gain
    annoncé est celui de la répartition proposée, pas d'un optimum théorique.
    """
    current = {}
    for card in cards:
        if not categories.is_basic_land(card):
            continue
        for color in card.get("produced_mana") or []:
            if color in BASIC_LAND_BY_COLOR:
                current[color] = current.get(color, 0) + card["quantity"]

    pool = sum(current.values())
    candidates = [color for color in colors if color in BASIC_LAND_BY_COLOR]
    if not pool or not candidates:
        return None

    before = expected_stuck_cards(demands, ready)
    # On repart des sources hors basiques : elles, on ne peut pas les déplacer.
    # Un basique est disponible dès le tour 1, d'où les `1` qu'on rajoute.
    held = {color: [turn for turn in ready.get(color, [])] for color in ready}
    for color in candidates:
        for _ in range(current.get(color, 0)):
            held[color].remove(1)

    suggested = dict.fromkeys(candidates, 0)
    for _ in range(pool):
        color = min(candidates,
                    key=lambda c: (expected_stuck_cards(demands, {**held, c: held[c] + [1]}), c))
        suggested[color] += 1
        held[color].append(1)
    after = expected_stuck_cards(demands, held)

    if suggested == {color: current.get(color, 0) for color in candidates}:
        return None

    return {
        "total": pool,
        "current": {BASIC_LAND_BY_COLOR[color]: count
                    for color, count in sorted(current.items()) if count},
        "suggested": {BASIC_LAND_BY_COLOR[color]: count
                      for color, count in sorted(suggested.items()) if count},
        "moves": sorted(
            ({"land": BASIC_LAND_BY_COLOR[color],
              "from": current.get(color, 0),
              "to": suggested[color],
              "delta": suggested[color] - current.get(color, 0)}
             for color in candidates if suggested[color] != current.get(color, 0)),
            key=lambda move: move["delta"],
        ),
        "stuck_before": round(before, 1),
        "stuck_after": round(after, 1),
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
