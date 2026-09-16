"""
services/competitive.py — construction d'un deck compétitif.

Le principe du projet s'applique ici sans changement : **rien n'est estimé**.
La cible n'est pas inventée, elle est mesurée sur les decks réels du thème
(EDHREC : combien de terrains, de créatures, à quels coûts), et le classement
des cartes est le taux d'inclusion — ce que jouent réellement ceux qui montent
cette stratégie, pas ce qui est cher ou spectaculaire.

Trois contraintes sont dures, jamais arbitrées :

- **la banlist du format**, appliquée en SQL (`legal_duel` ou `legal_commander`)
  avant même que la carte entre dans le vivier : Duel Commander bannit ce que
  le multi autorise, et l'inverse n'existe pas ;
- **l'identité de couleur** du commandant ;
- **le singleton** : un exemplaire par carte, terrains de base exceptés.

Deux choses le sont moins, et c'est assumé :

- « le plus compétitif possible » n'est pas une grandeur. Ce qui est calculable,
  c'est « le plus proche possible des decks qui jouent cette stratégie, avec ce
  que tu as » — c'est ce qu'on optimise, et l'écart restant est affiché ;
- le deck est bâti **avec la collection seule**. Les achats sont proposés à
  côté, chacun face à la carte qu'il remplacerait : un deck qu'on ne peut pas
  jouer ce soir n'est pas un deck.
"""
import db.themes as themes_db
from services import mana

# Repères de repli quand EDHREC n'a pas de profil pour le thème (thème récent,
# petit échantillon) : les mêmes que le reste du projet.
FALLBACK_LAND_COUNT = 36
DECK_SIZE = 100
# Au-delà, tous les coûts se valent pour une courbe : on regroupe.
MAX_CURVE_BUCKET = 7

# Les types du camembert EDHREC, dans l'ordre où on remplit. Les créatures
# d'abord : ce sont elles qui portent le plan de jeu, et elles se choisissent
# moins interchangeablement qu'un rocher de mana.
TYPE_ORDER = ["Creature", "Instant", "Sorcery", "Artifact", "Enchantment",
              "Planeswalker", "Battle"]


def _bucket(cmc) -> int:
    return min(int(cmc or 0), MAX_CURVE_BUCKET)


def _type_of(card: dict) -> str | None:
    """Le type qui sert de quota. Une carte multi-type compte pour le premier
    trouvé dans `TYPE_ORDER`, comme le camembert d'EDHREC qui ne compte jamais
    une carte deux fois."""
    type_line = card.get("type_line") or ""
    if "Land" in type_line:
        return "Land"
    for card_type in TYPE_ORDER:
        if card_type in type_line:
            return card_type
    return None


def _rank(card: dict) -> tuple:
    """
    Classement de compétitivité : le taux d'inclusion du thème d'abord, celui
    du commandant ensuite, puis la popularité générale. Le prix ne départage
    qu'à égalité — il ne doit jamais faire préférer une carte moins jouée.
    """
    return (
        -card["theme_rate"],
        -card["commander_rate"],
        card.get("edhrec_rank") or 10**9,
        card.get("price_eur") or 0,
    )


def choose_nonlands(pool: list[dict], type_targets: dict[str, int],
                    curve_target: dict[int, int], slots: int) -> list[dict]:
    """
    Remplit les emplacements non-terrain en respectant deux gabarits à la fois :
    le nombre de cartes par type et la courbe de mana.

    L'algorithme est volontairement lisible plutôt qu'optimal : on descend le
    vivier par ordre de compétitivité et on prend une carte si **son type et
    son coût** ont encore de la place. Un second passage relâche la courbe,
    puis un troisième les types — parce qu'un deck de 99 cartes vaut mieux
    qu'un deck de 84 parfaitement galbé.
    """
    chosen: list[dict] = []
    taken_types: dict[str, int] = {}
    taken_curve: dict[int, int] = {}
    ordered = sorted(pool, key=_rank)

    def fits(card: dict, *, check_curve: bool, check_type: bool) -> bool:
        card_type = _type_of(card)
        if check_type:
            target = type_targets.get(card_type or "", 0)
            if taken_types.get(card_type or "", 0) >= target:
                return False
        if check_curve and curve_target:
            bucket = _bucket(card.get("cmc"))
            if taken_curve.get(bucket, 0) >= curve_target.get(bucket, 0):
                return False
        return True

    for check_curve, check_type in ((True, True), (False, True), (False, False)):
        for card in ordered:
            if len(chosen) >= slots:
                break
            if card in chosen or _type_of(card) == "Land":
                continue
            if not fits(card, check_curve=check_curve, check_type=check_type):
                continue
            chosen.append(card)
            taken_types[_type_of(card) or ""] = taken_types.get(_type_of(card) or "", 0) + 1
            taken_curve[_bucket(card.get("cmc"))] = taken_curve.get(_bucket(card.get("cmc")), 0) + 1

    return chosen


def curve_of(cards: list[dict]) -> dict[int, int]:
    curve: dict[int, int] = {}
    for card in cards:
        curve[_bucket(card.get("cmc"))] = curve.get(_bucket(card.get("cmc")), 0) + 1
    return curve


BASIC_LAND_BY_COLOR = {"W": "Plaine", "U": "Île", "B": "Marais", "R": "Montagne", "G": "Forêt"}
COLORLESS_BASIC_LAND = "Étendue"


def land_package(pool: list[dict], slots: int, identity: list[str],
                 nonland_cards: list[dict], commander: dict) -> dict:
    """
    La manabase : les terrains non-basiques possédés les plus joués d'abord,
    puis des terrains de base au prorata des symboles de mana réellement
    demandés.

    Rien n'est acheté ici, comme dans `/deck-plans` et pour la même raison :
    une manabase achetée coûte vite plus cher que le reste du deck, et des
    terrains de base font le travail. Les duales manquantes ressortent dans les
    achats, où elles sont comparables au reste.
    """
    owned_lands = [card for card in sorted(pool, key=_rank)
                   if _type_of(card) == "Land" and card["owned_quantity"] > 0][:slots]

    remaining = max(0, slots - len(owned_lands))
    colors = [color for color in identity if color in BASIC_LAND_BY_COLOR]
    if not colors or not remaining:
        return {"nonbasic": owned_lands,
                "basics": {COLORLESS_BASIC_LAND: remaining} if remaining else {},
                "total": len(owned_lands) + remaining}

    pips = mana.color_requirements(
        [{**card, "quantity": 1} for card in nonland_cards] + [{**commander, "quantity": 1}]
    )
    # Plancher de deux : une couleur peu demandée doit garder des sources, sinon
    # la seule carte qui l'exige devient injouable.
    weights = {color: pips.get(color, 0) + 2 for color in colors}
    total_weight = sum(weights.values())
    exact = {color: remaining * weight / total_weight for color, weight in weights.items()}
    basics = {color: int(value) for color, value in exact.items()}
    for color in sorted(exact, key=lambda c: exact[c] - int(exact[c]),
                        reverse=True)[:remaining - sum(basics.values())]:
        basics[color] += 1

    return {
        "nonbasic": owned_lands,
        "basics": {BASIC_LAND_BY_COLOR[color]: count
                   for color, count in sorted(basics.items()) if count},
        "total": len(owned_lands) + sum(basics.values()),
    }


def upgrades(pool: list[dict], chosen: list[dict], max_price: float,
             limit: int = 15) -> list[dict]:
    """
    Les achats qui valent le coup, chacun **face à la carte qu'il remplace**.

    Une carte non possédée n'a d'intérêt que si elle est plus jouée que la
    moins bonne carte retenue **du même type** : sinon l'acheter ne rapproche
    pas le deck des listes de référence, elle le déplace latéralement. Le
    remplacement est donc désigné, pas laissé à deviner.
    """
    # Les cartes retenues, du maillon le plus faible au plus fort, par type.
    # Chaque achat évince **une** carte distincte : proposer trois achats qui
    # remplacent tous la même carte ferait croire à trois gains alors qu'il n'y
    # en a qu'un.
    by_type: dict[str, list[dict]] = {}
    for card in sorted(chosen, key=_rank, reverse=True):
        by_type.setdefault(_type_of(card) or "", []).append(card)

    candidates = [
        card for card in pool
        if card["owned_quantity"] == 0
        and card not in chosen
        and _type_of(card) != "Land"
        and card.get("price_eur") is not None
        and card["price_eur"] <= max_price
    ]

    proposals = []
    for card in sorted(candidates, key=_rank):
        card_type = _type_of(card) or ""
        remaining = by_type.get(card_type)
        if not remaining:
            continue
        replaced = remaining[0]
        if _rank(card) >= _rank(replaced):
            continue
        remaining.pop(0)
        proposals.append({"buy": card, "replace": replaced,
                          "price_eur": float(card["price_eur"])})
        if len(proposals) >= limit:
            break
    return proposals


CARD_FIELDS = ("oracle_id", "scryfall_id", "name", "name_fr", "mana_cost", "cmc",
               "type_line", "price_eur", "image_uri", "image_downloaded",
               "categories", "color_identity", "game_changer", "edhrec_rank")


def _summarize(card: dict) -> dict:
    summary = {field: card.get(field) for field in CARD_FIELDS}
    summary["oracle_id"] = str(card["oracle_id"])
    summary["owned"] = card["owned_quantity"] > 0
    summary["theme_rate"] = round(card["theme_rate"], 3)
    summary["commander_rate"] = round(card["commander_rate"], 3)
    return summary


def _targets(theme: dict) -> tuple[dict[str, int], dict[int, int], int]:
    """
    (cartes par type, courbe, nombre de terrains) depuis le profil EDHREC du
    thème. Sans profil — thème récent, échantillon trop mince — on retombe sur
    les repères du projet plutôt que de refuser de construire.
    """
    type_counts = {key: int(value) for key, value in (theme.get("type_counts") or {}).items()}
    lands = type_counts.pop("Land", 0) or FALLBACK_LAND_COUNT
    curve = {int(bucket): int(count) for bucket, count in (theme.get("mana_curve") or {}).items()}
    return type_counts, curve, lands


def build(commander: dict, theme_slug: str, format: str, max_price: float) -> dict:
    """
    Construit le deck et renvoie de quoi le vérifier : les cartes retenues, la
    courbe obtenue face à la courbe visée, ce qui manque, et les achats.
    """
    commander_oracle_id = str(commander["oracle_id"])

    # La banlist s'applique d'abord au commandant : inutile de construire 99
    # cartes autour d'une carte qu'on ne peut pas poser. Sol Ring et Ancient
    # Tomb sont légaux en multi et bannis en Duel — un commandant peut l'être
    # aussi.
    legality_field = themes_db.LEGALITY_COLUMNS[format]
    if not commander.get(legality_field):
        return {"error": f"{commander['name']} n'est pas légal dans ce format."}

    themes = {theme["slug"]: theme for theme in themes_db.themes_for(commander_oracle_id)}
    theme = themes.get(theme_slug)
    if theme is None:
        return {"error": f"Thème « {theme_slug} » inconnu pour ce commandant : "
                         "relance la synchronisation EDHREC."}

    type_targets, curve_target, land_slots = _targets(theme)
    pool = themes_db.build_pool(commander_oracle_id, theme_slug, format,
                                commander["color_identity"])

    # 99 cartes plus le commandant. Les terrains ont leur propre gabarit : ce
    # qui reste va aux sorts.
    nonland_slots = DECK_SIZE - 1 - land_slots
    # **Le deck est bâti avec la collection seule.** Les cartes non possédées
    # restent dans le vivier pour alimenter les achats, mais n'entrent jamais
    # dans la liste : un deck qu'on ne peut pas jouer ce soir n'est pas un deck,
    # et c'est exactement ce que demande « en prenant en compte la collection ».
    owned_pool = [card for card in pool if card["owned_quantity"] > 0]
    chosen = choose_nonlands(owned_pool, type_targets, curve_target, nonland_slots)
    lands = land_package(pool, land_slots, commander["color_identity"], chosen, commander)

    achieved = curve_of(chosen)
    owned_count = sum(1 for card in chosen if card["owned_quantity"] > 0)

    return {
        "commander": _summarize({**commander, "owned_quantity": 1,
                                 "theme_rate": 1.0, "commander_rate": 1.0}),
        "theme": {"slug": theme["slug"], "label": theme["label"],
                  "deck_count": theme["deck_count"]},
        "format": format,
        "cards": [_summarize(card) for card in sorted(chosen, key=_rank)],
        "lands": {
            "nonbasic": [_summarize(card) for card in lands["nonbasic"]],
            "basics": lands["basics"],
            "total": lands["total"],
        },
        "counts": {
            "total": 1 + len(chosen) + lands["total"],
            "nonland": len(chosen),
            "nonland_target": nonland_slots,
            "lands": lands["total"],
            "owned": owned_count,
            "missing": len(chosen) - owned_count,
        },
        "curve": {"target": curve_target, "achieved": achieved},
        "type_targets": type_targets,
        "type_achieved": {card_type: sum(1 for card in chosen if _type_of(card) == card_type)
                          for card_type in type_targets},
        "upgrades": [
            {"buy": _summarize(item["buy"]), "replace": _summarize(item["replace"]),
             "price_eur": item["price_eur"]}
            for item in upgrades(pool, chosen, max_price)
        ],
        "pool_size": len(pool),
    }
