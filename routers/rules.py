"""
routers/rules.py — les règles qu'on subit : banlists, brackets, Game Changers.

Une seule requête HTTP pour toute la page : quatre listes de quelques dizaines
à quelques centaines de lignes, lues dans `cards` par des index partiels. Les
découper en trois appels ferait trois allers-retours pour un écran qu'on
consulte d'un bloc.

**Aucune synchronisation propre à cette page.** Les trois listes sont des
colonnes de `cards` renseignées par `sync_scryfall.py`, donc rafraîchies par le
flow mensuel `sync-scryfall`. Un flow Kestra de plus referait exactement le
même travail — et le projet tient à n'avoir qu'un seul ordonnanceur pour un
travail donné.
"""
from fastapi import APIRouter

import db.rules as rules_db
from services import bracket_rules

router = APIRouter(prefix="/rules", tags=["rules"])

DONNEES_ABSENTES = (
    "Banlists vides : les colonnes `banned_commander` / `banned_duel` naissent "
    "à faux et seule une synchronisation complète les renseigne — "
    "`python scripts/sync_scryfall.py`."
)


@router.get("")
def get_rules():
    """
    Les deux banlists, les cartes interdites comme commandant, les Game
    Changers et le système de brackets.

    **Pas d'`ensure_images`** : plus de quatre cents visuels au premier
    affichage feraient attendre une vingtaine de secondes, pour une page qu'on
    lit surtout en liste. Même arbitrage que `/must-have` — Scryfall sert les
    images, et le navigateur ne charge que ce qui est à l'écran.
    """
    return {
        "banlists": {
            "commander": rules_db.banlist("commander"),
            "duel": rules_db.banlist("duel"),
        },
        # Jouables dans les 99, interdites au seul titre de commandant. Propre
        # au duel : le multijoueur n'a pas d'équivalent.
        "banned_as_commander": {
            "commander": rules_db.banned_as_commander("commander"),
            "duel": rules_db.banned_as_commander("duel"),
        },
        "game_changers": rules_db.game_changers(),
        "brackets": bracket_rules.describe(),
        "error": None if rules_db.has_data() else DONNEES_ABSENTES,
    }
