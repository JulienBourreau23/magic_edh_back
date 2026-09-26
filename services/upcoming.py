"""
services/upcoming.py — la prochaine extension à sortir, et ses cartes.

Scryfall ne sert qu'à dire **quelles extensions sortent et quand** (`/sets`) :
notre base n'a pas de date de sortie. Les cartes, elles, viennent de `cards`,
qui les contient dès le spoiler, et c'est ce qui donne les noms français, la
possession et un bouton « + recherche » qui marche (il exige une carte en base).

Aucune table : le jour de la sortie, la date n'est plus dans le futur et la
page passe d'elle-même à l'extension suivante. Une table à purger serait une
seconde vérité à entretenir.
"""
import threading
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from config import SCRYFALL_API_BASE, SCRYFALL_HEADERS

# Ce qui se joue. Les jetons, promos, objets de collection et produits
# numériques partagent la date de sortie d'une extension sans en être.
PLAYABLE_SET_TYPES = {
    "expansion", "core", "commander", "draft_innovation", "masters", "masterpiece",
}

# La liste des extensions bouge à l'annonce d'un produit, pas d'heure en heure.
CACHE_SECONDS = 6 * 3600

_cache: dict = {"at": 0.0, "sets": None}
_lock = threading.Lock()


def today_paris() -> date:
    """Le jour de sortie se juge à l'heure française, pas à celle du serveur."""
    return datetime.now(ZoneInfo("Europe/Paris")).date()


def next_release(sets: list[dict], today: date) -> dict | None:
    """
    Les extensions jouables de la prochaine date **strictement** future.

    Strictement : le jour même, l'extension est sortie et quitte la page. Le set
    principal et ses precons Commander partagent la même date, d'où une liste.
    """
    upcoming = [
        s for s in sets
        if s.get("set_type") in PLAYABLE_SET_TYPES
        and not s.get("digital")
        and s.get("released_at")
        and date.fromisoformat(s["released_at"]) > today
    ]
    if not upcoming:
        return None
    release = min(date.fromisoformat(s["released_at"]) for s in upcoming)
    chosen = [s for s in upcoming if date.fromisoformat(s["released_at"]) == release]
    # Le set principal d'abord, ses produits dérivés ensuite.
    chosen.sort(key=lambda s: (s.get("parent_set_code") is not None, s["code"]))
    return {
        "released_at": release.isoformat(),
        "sets": [
            {
                "code": s["code"],
                "name": s["name"],
                "set_type": s["set_type"],
                "card_count": s.get("card_count", 0),
                "icon_svg_uri": s.get("icon_svg_uri"),
            }
            for s in chosen
        ],
    }


def fetch_sets() -> list[dict]:
    with _lock:
        if _cache["sets"] is not None and time.monotonic() - _cache["at"] < CACHE_SECONDS:
            return _cache["sets"]
    with httpx.Client(timeout=15, headers=SCRYFALL_HEADERS) as client:
        response = client.get(f"{SCRYFALL_API_BASE}/sets")
        response.raise_for_status()
        sets = response.json()["data"]
    with _lock:
        _cache.update(at=time.monotonic(), sets=sets)
    return sets
