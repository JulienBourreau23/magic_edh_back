"""
services/combos.py — les combos à deux cartes présents dans un deck.

Le catalogue vient de Commander Spellbook (`services/spellbook.py`) ; ici on ne
fait que croiser : un combo est « présent » quand ses deux cartes sont dans la
liste. C'est un constat, pas une estimation — d'où l'identifiant Spellbook
renvoyé avec, pour aller vérifier le combo à la main.
"""
from typing import Callable, Iterable

import db.combos as combos_db
from services.deck_analysis import display_name

SPELLBOOK_COMBO_URL = "https://commanderspellbook.com/combo/{variant_id}/"


def _describe(row: dict, by_oracle: dict[str, dict]) -> dict:
    first, second = by_oracle[str(row["oracle_id_a"])], by_oracle[str(row["oracle_id_b"])]
    return {
        "variant_id": row["variant_id"],
        "url": SPELLBOOK_COMBO_URL.format(variant_id=row["variant_id"]),
        # Les noms viennent des cartes du deck, pas du catalogue : c'est la même
        # règle d'affichage que partout (français si connu, anglais sinon).
        "cards": [display_name(first), display_name(second)],
        # Pour que l'appelant retrouve les cartes du deck sans repasser par les
        # noms affichés — c'est la règle du projet : on joint par identifiant.
        "oracle_ids": [str(row["oracle_id_a"]), str(row["oracle_id_b"])],
        "produces": row["produces"],
        "wins_outright": row["wins_outright"],
        "mana_needed": row["mana_needed"],
        # Mana total pour lancer les deux cartes **et** exécuter le combo : c'est
        # le chiffre qui dit si le combo est un plan de fin de partie (toléré au
        # bracket 3) ou un plan de départ. À lire avec le ramp du deck, pas seul.
        "total_mana_value": int((first["cmc"] or 0) + (second["cmc"] or 0)
                                + (row["mana_value_needed"] or 0)),
        "bracket_tag": row["bracket_tag"],
        "popularity": row["popularity"],
        # Comment on l'exécute, et ce qu'il suppose en place. « Infinite
        # damage » ne dit pas quelle carte lancer en premier : sans les
        # étapes, la fiche annonce un combo que le joueur ne sait pas jouer.
        "description": row.get("description"),
        "prerequisites": row.get("prerequisites"),
    }


def find_in_deck(cards: list[dict]) -> list[dict]:
    """Les combos à deux cartes du deck, les gagnants d'abord."""
    by_oracle = {str(card["oracle_id"]): card for card in cards if card.get("oracle_id")}
    return [_describe(row, by_oracle) for row in combos_db.find_pairs(sorted(by_oracle))]


def matcher_for(oracle_ids: Iterable[str]) -> Callable[[list[dict]], list[dict]]:
    """
    Un `find_in_deck` qui **ne touche plus la base** : le catalogue utile est
    chargé une fois, le croisement se fait ensuite en mémoire.

    `/deck-plans` construit des milliers de decks (131 commandants montés seuls,
    puis quatre decks par groupe évalué) et tous puisent dans le même vivier.
    Une requête par deck, c'est 2 111 allers-retours pour un catalogue qui ne
    bouge pas entre deux : la base est sur une autre machine en production, et
    c'est exactement le genre de somme qui fait dépasser le plafond de 100 s de
    Cloudflare — la page renvoie alors une erreur réseau, sans rien dire de plus.

    Le résultat est **identique** à celui de `find_in_deck`, ordre compris : les
    lignes gardent l'ordre du catalogue (gagnants d'abord), on ne fait que les
    filtrer.
    """
    universe = sorted({str(oracle_id) for oracle_id in oracle_ids})
    pairs = combos_db.find_pairs(universe)

    # Index par carte : un deck de 64 cartes ne regarde que les combos qui le
    # concernent, au lieu de parcourir tout le catalogue à chaque fois.
    by_card: dict[str, list[dict]] = {}
    rank = {}
    for position, row in enumerate(pairs):
        by_card.setdefault(str(row["oracle_id_a"]), []).append(row)
        rank[row["variant_id"]] = position

    def find(cards: list[dict]) -> list[dict]:
        by_oracle = {str(card["oracle_id"]): card for card in cards if card.get("oracle_id")}
        found = [row for oracle_id in by_oracle
                 for row in by_card.get(oracle_id, ())
                 if str(row["oracle_id_b"]) in by_oracle]
        # `pairs` est déjà trié (gagnants d'abord) : on rétablit cet ordre, que
        # le parcours par carte a perdu.
        found.sort(key=lambda row: rank[row["variant_id"]])
        return [_describe(row, by_oracle) for row in found]

    return find
