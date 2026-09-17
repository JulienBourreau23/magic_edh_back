"""
services/spellbook.py — import des combos à **deux cartes** depuis Commander
Spellbook.

Le bracket officiel du Commander Format Panel interdit les combos infinis à
deux cartes aux brackets 1-2 ; c'est un critère qu'on ne peut pas déduire du
texte d'une carte (il naît de l'interaction entre deux cartes, pas d'une
formule dans l'oracle). On importe donc un catalogue plutôt que de le deviner :
`bracket_estimate` n'a plus qu'à regarder si les deux pièces sont dans le deck.

Source : l'API publique de Commander Spellbook (`backend.commanderspellbook.com`),
la même que leur site consomme. Elle est documentée (schéma OpenAPI) et sert
explicitement à ça, mais reste une dépendance externe : la table est
entièrement reconstructible, et ce module est le seul point de contact.

Deux règles de politesse, comme pour EDHREC : une pause entre chaque page, et
`ordering=id` pour que la pagination soit stable au lieu de rejouer des pages.

Ne sont retenues que les paires de **deux cartes réelles distinctes** : les
variantes qui font intervenir un gabarit (« une créature avec la célérité »)
ne sont pas vérifiables mécaniquement contre une decklist.
"""
import re
import time

import httpx
from psycopg2.extras import execute_values

from config import SCRYFALL_HEADERS
from db.core import get_conn

SPELLBOOK_API = "https://backend.commanderspellbook.com/variants/"
PAGE_SIZE = 100
DEFAULT_DELAY_SECONDS = 1.5
# Spellbook limite le débit. Une synchro complète fait une quarantaine de
# pages : on encaisse le 429 au lieu de perdre le lot entier, et on respecte
# le `Retry-After` quand il est fourni.
MAX_RETRIES = 4

# Un combo « qui gagne la partie » au sens du Commander Format Panel : celui
# qui tue, pas celui qui prépare. Les libellés de Spellbook sont normalisés, on
# peut donc les lire à la règle plutôt qu'un par un.
#
#   « ... loses the game »   : y compris « at the beginning of their next
#                              upkeep ». Le « lose » singulier de « You are
#                              unable to lose the game » ne correspond pas.
#   « Win the game ... »     : avec ou sans délai.
#   dégâts / perte de vie / meule, infinis ou presque, **dirigés vers des
#   joueurs** : le mana infini, la pioche infinie ou les ETB infinis ne gagnent
#   rien tout seuls, et les dégâts « to creatures » sont un board wipe.
_WINNING_RE = re.compile(
    r"loses the game"
    r"|^Win the game"
    r"|^(Infinite|Near-infinite) (combat )?(damage|lifeloss|mill)\b",
)
# Exclusions, dans l'ordre de lecture du dessus : un wipe n'est pas une victoire,
# se meuler soi-même non plus.
_NOT_WINNING_RE = re.compile(r"creatures|self-mill")

# Cas que le catalogue sous-déclare : Kiki-Jiki + Conscrits zélés produit
# « Infinite creature tokens with haste » et rien d'autre — pas de ligne de
# dégâts, parce qu'il faut encore attaquer. Un nombre illimité d'attaquants
# avec la célérité finit pourtant la partie sur place, ce que vise exactement
# le critère officiel. Trois garde-fous : des créatures (pas des artefacts),
# non engagées (un jeton qui arrive engagé n'attaque pas), et des corps réels
# (pas des marqueurs +1/+1 sur un jeton déjà là).
_HASTE_WIN_RE = re.compile(
    r"^(Infinite|Near-infinite)(?!.*\btapped\b)(?!.*counters).*\bcreature.*\bwith haste$")


def wins_outright(produces: list[str]) -> bool:
    """Ce combo gagne-t-il la partie à lui seul ?"""
    return any(
        (_WINNING_RE.search(feature) and not _NOT_WINNING_RE.search(feature))
        or _HASTE_WIN_RE.search(feature)
        for feature in produces
    )


def two_card_pair(variant: dict) -> tuple[str, str, str, str] | None:
    """
    (oracle_a, nom_a, oracle_b, nom_b) triés par oracle_id, ou None si la
    variante n'est pas une vraie paire de deux cartes distinctes : gabarit
    requis, deux exemplaires de la même carte (impossible en singleton), ou
    identifiant oracle manquant.
    """
    if variant.get("requires"):
        return None

    uses = variant.get("uses") or []
    if len(uses) != 2 or any((use.get("quantity") or 1) != 1 for use in uses):
        return None

    cards = [(use["card"].get("oracleId"), use["card"].get("name")) for use in uses]
    if any(not oracle_id for oracle_id, _ in cards) or cards[0][0] == cards[1][0]:
        return None

    (oracle_a, name_a), (oracle_b, name_b) = sorted(cards)
    return oracle_a, name_a, oracle_b, name_b


def to_row(variant: dict) -> tuple | None:
    pair = two_card_pair(variant)
    if pair is None:
        return None

    oracle_a, name_a, oracle_b, name_b = pair
    produces = [p["feature"]["name"] for p in variant.get("produces") or []]
    return (
        variant["id"], oracle_a, oracle_b, name_a, name_b, produces,
        wins_outright(produces), variant.get("manaNeeded"),
        variant.get("manaValueNeeded"), variant.get("bracketTag"),
        variant.get("popularity"),
        _clean(variant.get("description")),
        _prerequisites(variant),
    )


def _clean(value: str | None) -> str | None:
    """Une chaîne vide n'est pas une information : elle vaut NULL."""
    text = (value or "").strip()
    return text or None


def _prerequisites(variant: dict) -> str | None:
    """
    Ce qu'il faut avoir en place avant de lancer le combo. Spellbook sépare les
    conditions banales (« avoir du mana ») des notables (« un autre elfe sur le
    champ de bataille ») : on les concatène, l'affichage n'a pas à trancher
    entre les deux.
    """
    morceaux = [_clean(variant.get("easyPrerequisites")),
                _clean(variant.get("notablePrerequisites"))]
    joint = "\n".join(m for m in morceaux if m)
    return joint or None


def _get_with_backoff(client: httpx.Client, url: str, params: dict | None, delay: float):
    """
    Un GET qui encaisse le 429. L'attente double à chaque essai, sauf si le
    serveur dit lui-même combien de temps patienter. Au dernier essai, l'erreur
    remonte : mieux vaut un sync en échec qu'un catalogue à moitié importé —
    et comme l'écriture n'a lieu qu'à la fin, la table garde l'ancien contenu.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        response = client.get(url, params=params)
        if response.status_code != 429 or attempt == MAX_RETRIES:
            response.raise_for_status()
            return response
        retry_after = response.headers.get("Retry-After")
        time.sleep(float(retry_after) if retry_after else delay * 2 ** attempt)


def fetch_pages(client: httpx.Client, delay: float):
    """Génère les variantes à deux cartes, page par page."""
    url = SPELLBOOK_API
    params = {"q": "cards=2", "limit": PAGE_SIZE, "ordering": "id"}
    while url:
        response = _get_with_backoff(client, url, params, delay)
        payload = response.json()
        yield payload.get("results") or []

        # `next` porte déjà tous les paramètres : les repasser les dupliquerait.
        url, params = payload.get("next"), None
        if url:
            time.sleep(delay)


def store(rows: list[tuple]) -> tuple[int, int]:
    """
    Remplace le contenu de `combos`, et renvoie (enregistrés, ignorés).

    Un combo dont une des deux cartes est absente de notre base est écarté :
    la table ne sert qu'à reconnaître des cartes qu'on peut réellement avoir en
    main, et `cards` ne couvre que l'anglais non-digital hors jetons. Le filtre
    est fait ici, en Python, plutôt que par une jointure : c'est le seul moyen
    de distinguer « ignoré » de « perdu » dans le résumé.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT oracle_id FROM cards")
            known = {str(row["oracle_id"]) for row in cur.fetchall()}
            keep = [row for row in rows if row[1] in known and row[2] in known]

            cur.execute("TRUNCATE combos")
            if keep:
                execute_values(
                    cur,
                    """
                    INSERT INTO combos (variant_id, oracle_id_a, oracle_id_b, card_a, card_b,
                                        produces, wins_outright, mana_needed,
                                        mana_value_needed, bracket_tag, popularity,
                                        description, prerequisites)
                    VALUES %s
                    ON CONFLICT (variant_id) DO NOTHING
                    """,
                    keep,
                    page_size=500,
                )
            return len(keep), len(rows) - len(keep)


def sync(delay: float = DEFAULT_DELAY_SECONDS, progress=None) -> dict:
    """
    Résumé exploitable par un ordonnanceur, comme `edhrec.sync`.

    `progress` reçoit (pages, variantes lues) après chaque page : une synchro
    qui encaisse des 429 peut durer plusieurs minutes, et sans ça on ne
    distingue pas « ça avance lentement » de « c'est bloqué ».
    """
    rows, seen, pages = [], 0, 0

    with httpx.Client(timeout=60, headers=SCRYFALL_HEADERS, follow_redirects=True) as client:
        for results in fetch_pages(client, delay):
            pages += 1
            seen += len(results)
            rows.extend(row for row in map(to_row, results) if row)
            if progress:
                progress(pages, seen)

    stored, ignored = store(rows)
    return {
        "pages": pages,
        "variants_seen": seen,
        "two_card_pairs": len(rows),
        "stored": stored,
        # Combos dont une des deux cartes n'existe pas dans notre base : normal
        # (cartes Alchemy, produits non synchronisés), pas une erreur.
        "ignored_unknown_cards": ignored,
    }
