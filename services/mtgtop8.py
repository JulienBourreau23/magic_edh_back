"""
services/mtgtop8.py — les tops des tournois de Duel Commander, relevés sur
MTGTop8.

**Pourquoi une seconde source.** EDHREC ne distingue pas les formats : ses
listes sont celles du multijoueur. Conseiller un deck de duel avec elles, c'est
lui donner ce qui marche à quatre joueurs et 40 points de vie — ramp lente,
effets symétriques, pioche de groupe — au détriment de ce qui gagne en face à
face : l'interaction bon marché et le tempo. MTGTop8 publie les tops des
tournois de Duel Commander (format `EDH` chez eux ; le cEDH multi est un autre
format, `cEDH`), avec la liste complète de chaque deck.

**Ce n'est pas une API.** Ce sont les pages HTML du site, lues aux motifs qui
les structurent, et l'export texte d'un deck (`mtgo?d=`). Il n'y a pas de
`robots.txt` (le site répond 404) : rien n'est interdit, rien n'est prévu non
plus. D'où les mêmes règles qu'avec EDHREC — une pause entre chaque requête, un
module isolé, des tables entièrement reconstructibles — et des parseurs purs,
testés sur des extraits réels, pour qu'un changement de mise en page casse un
test plutôt que de vider le méta en silence.

**La synchronisation est incrémentale**, contrairement à celle d'EDHREC qui
refetche chaque semaine des centaines de pages qui n'ont pas bougé : un
tournoi publié ne change plus, donc on ne demande que ceux qu'on n'a pas
encore. Le coût d'une semaine est d'une cinquantaine d'événements.

La fenêtre est glissante (`WINDOW_DAYS`) : les cartes bannies ou passées de
mode sortent d'elles-mêmes du méta, sans liste à tenir.
"""
import html
import re
import time
from datetime import date, datetime, timedelta

import httpx
from psycopg2.extras import Json

import db.cards as cards_db
from db.core import get_conn
from services import competitive

BASE_URL = "https://www.mtgtop8.com"
FORMAT_CODE = "EDH"
# La liste des événements ne se pagine qu'avec un « méta » choisi : sans lui,
# le site s'arrête à la troisième page (une soixantaine d'événements, trois
# semaines). 209 est « Last 6 Months » ; la liste d'événements qu'il pagine
# est la même pour tous les métas, seule la profondeur change.
LIST_META_ID = 209
DEFAULT_DELAY_SECONDS = 1.0
# Six mois : assez pour qu'un commandant joué ait plusieurs listes, assez
# court pour que le méta reflète la banlist en vigueur. Mesuré en septembre
# 2026 : ~5 événements par jour, ~4,5 decks par événement, soit ~4 000 decks.
WINDOW_DAYS = 180
# Plafond d'événements par exécution. La première synchronisation en compte
# près d'un millier (~2 h, à ~7 s par tournoi) : on la découpe plutôt que de
# tenir une connexion SSH ouverte aussi longtemps. Chaque exécution reprend
# où la précédente s'est arrêtée, puisque seuls les événements inconnus sont
# demandés. `0` lève le plafond.
DEFAULT_MAX_EVENTS = 300
# Page de liste au-delà de laquelle on s'arrête quoi qu'il arrive : garde-fou
# contre une mise en page qui ne laisserait plus lire les dates.
MAX_LIST_PAGES = 120

# Un navigateur ordinaire : le site sert des pages différentes (ou rien) à
# certains agents. Les requêtes restent identifiables par leur rythme.
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) MagicEDH/0.1",
           "Accept": "*/*"}


# --- Parseurs purs ------------------------------------------------------------
#
# Aucun ne touche le réseau ni la base : ils prennent le texte d'une page et
# rendent des structures. C'est ce qui les rend testables sur des extraits
# réels (`tests/test_mtgtop8.py`).

# « LAST 20 EVENTS » sur la première page, « Events 41 to 60 » sur les suivantes.
_EVENTS_TITLE_RE = re.compile(r"LAST \d+ EVENTS|Events \d+ to \d+")
# Une ligne du tableau des événements : le lien, puis la date en fin de ligne.
# Le `[^<]*` du nom interdit de déborder sur la ligne suivante.
_EVENT_ROW_RE = re.compile(
    r"<a href=event\?e=(\d+)&f=EDH>([^<]*)</a>.*?class=S12>(\d\d/\d\d/\d\d)</td>",
    re.S,
)
_PLAYERS_RE = re.compile(r"(\d+) players\s*-\s*(\d\d/\d\d/\d\d)")
_EVENT_DATE_RE = re.compile(r">\s*(\d\d/\d\d/\d\d)\s*<")
_EVENT_TITLE_RE = re.compile(r"<div class=event_title>([^<]*)</div>")
# Un deck du top : la place, puis le lien vers le deck, puis son nom.
_DECK_ROW_RE = re.compile(
    r"<div style=\"width:42px;\" align=center class=S14>([^<]*)</div>\s*"
    r"<div[^>]*><a href=\?e=\d+&d=(\d+)&f=EDH>.*?"
    r"<a href=\?e=\d+&d=\d+&f=EDH>([^<]*)</a>",
    re.S,
)
_EXPORT_LINE_RE = re.compile(r"^(\d+)\s+(.+)$")


def parse_date(text: str) -> date:
    """« 18/09/26 » → 2026-09-18. MTGTop8 écrit l'année sur deux chiffres."""
    return datetime.strptime(text, "%d/%m/%y").date()


def parse_event_list(page: str) -> list[dict]:
    """
    Les événements d'une page de liste, du plus récent au plus ancien.

    La page porte **deux** tableaux : les « derniers grands événements », repris
    à l'identique sur chaque page, puis la liste paginée (« LAST 20 EVENTS » sur
    la première, « Events 41 to 60 » ensuite).
    Seule la seconde est lue — la première ferait croire que chaque page
    commence au 20 septembre, et l'arrêt sur la date ne se produirait jamais.
    """
    title = _EVENTS_TITLE_RE.search(page)
    if not title:
        return []
    return [
        {"event_id": int(event_id), "name": html.unescape(name).strip(),
         "event_date": parse_date(day)}
        for event_id, name, day in _EVENT_ROW_RE.findall(page[title.end():])
    ]


def placement_of(rank_label: str) -> int | None:
    """« 1 » → 1, « 3-4 » → 3, « 5-8 » → 5 : la meilleure place possible."""
    match = re.match(r"\s*(\d+)", rank_label or "")
    return int(match.group(1)) if match else None


def parse_event(page: str) -> dict:
    """
    Le nom, la date, le nombre de joueurs et les decks classés d'un événement.

    Le nombre de joueurs n'est pas toujours publié : il vaut alors `None`, pas
    zéro. Les places « 3-4 » et « 5-8 » sont gardées telles quelles — MTGTop8
    ne départage pas toujours les demi-finalistes, et inventer un ordre serait
    faux.
    """
    players = _PLAYERS_RE.search(page)
    if players:
        event_date = parse_date(players.group(2))
    else:
        found = _EVENT_DATE_RE.search(page[page.find("meta_arch"):]) if "meta_arch" in page else None
        event_date = parse_date(found.group(1)) if found else None

    title = _EVENT_TITLE_RE.search(page)
    decks, seen = [], set()
    for rank_label, deck_id, deck_name in _DECK_ROW_RE.findall(page):
        if deck_id in seen:
            continue
        seen.add(deck_id)
        decks.append({"deck_id": int(deck_id), "rank_label": rank_label.strip(),
                      "placement": placement_of(rank_label),
                      "deck_name": html.unescape(deck_name).strip()})

    return {
        "name": html.unescape(title.group(1)).strip() if title else None,
        "event_date": event_date,
        "players": int(players.group(1)) if players else None,
        "decks": decks,
    }


def normalize_card_name(name: str) -> str:
    """
    L'export écrit une carte partagée « Fire/Ice » là où Scryfall écrit
    « Fire // Ice ». Sans cette conversion, la carte resterait non résolue —
    et le passage « face avant » de la résolution ne la rattraperait pas,
    puisque « Fire/Ice » n'est le recto de rien.
    """
    name = name.strip()
    if "/" in name and " // " not in name:
        name = re.sub(r"\s*/+\s*", " // ", name)
    return name


def parse_export(text: str) -> dict:
    """
    L'export texte d'un deck : `{"cards": [(quantité, nom)], "commanders": [nom]}`.

    **Le commandant est rangé sous « Sideboard »**, et c'est la seule chose
    qu'on y trouve : deux lignes pour des partenaires, une sinon. C'est ce qui
    permet de l'identifier sans rien deviner — le prendre dans la liste
    principale serait impossible, rien ne l'y distingue.
    """
    cards, commanders = [], []
    in_sideboard = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith("sideboard"):
            in_sideboard = True
            continue
        match = _EXPORT_LINE_RE.match(line)
        if not match:
            continue
        quantity, name = int(match.group(1)), normalize_card_name(match.group(2))
        if in_sideboard:
            commanders.append(name)
        else:
            cards.append((quantity, name))
    return {"cards": cards, "commanders": commanders}


def compute_card_stats(deck_identities: dict[int, list[str]],
                       deck_cards: list[tuple[int, str]],
                       card_identities: dict[str, list[str]]) -> list[dict]:
    """
    Par carte : combien de decks la jouent, combien **pouvaient** la jouer, et
    les deux taux qui en découlent.

    Le dénominateur est ce qui fait la mesure. Une carte bleue jouée dans 30 %
    de **tous** les decks peut l'être dans 80 % des decks qui ont le bleu :
    rapporter à l'ensemble ferait passer une carte incontournable de sa couleur
    pour une carte de niche, et avantagerait mécaniquement les cartes
    incolores. `rate` rapporte donc aux decks dont l'identité contient celle de
    la carte ; `share` rapporte à tous, et sert à ce qui se compare toutes
    couleurs confondues (« les cartes à avoir »).

    Les decks sont regroupés par identité avant le comptage : il n'y en a que
    trente-deux, ce qui évite de croiser chaque carte avec chaque deck.
    """
    total = len(deck_identities)
    if not total:
        return []

    by_identity: dict[frozenset, int] = {}
    for identity in deck_identities.values():
        key = frozenset(identity)
        by_identity[key] = by_identity.get(key, 0) + 1

    played: dict[str, int] = {}
    for deck_id, oracle_id in deck_cards:
        if deck_id in deck_identities:
            played[oracle_id] = played.get(oracle_id, 0) + 1

    stats = []
    for oracle_id, decks in played.items():
        card_identity = frozenset(card_identities.get(oracle_id) or [])
        eligible = sum(count for identity, count in by_identity.items()
                       if card_identity <= identity)
        # Un deck ne joue pas une carte hors de son identité ; si c'est arrivé,
        # c'est une identité mal résolue, et le taux ne doit pas dépasser 1.
        eligible = max(eligible, decks)
        stats.append({"oracle_id": oracle_id, "decks": decks,
                      "eligible_decks": eligible, "rate": decks / eligible,
                      "share": decks / total})
    return stats


# --- Réseau --------------------------------------------------------------------


def _get(client: httpx.Client, path: str) -> str:
    response = client.get(f"{BASE_URL}/{path}")
    response.raise_for_status()
    # Le site sert du latin-1 (en-tête `charset=ISO-8859-1`). cp1252 en est un
    # sur-ensemble qui décode aussi les guillemets typographiques.
    return response.content.decode("cp1252", errors="replace")


def list_new_events(client: httpx.Client, known: set[int], since: date,
                    delay: float) -> list[dict]:
    """
    Les événements inconnus depuis `since`, du plus récent au plus ancien.

    On parcourt la liste page par page jusqu'à dépasser la fenêtre. On ne
    s'arrête **pas** au premier événement connu : une exécution plafonnée
    laisse des trous plus anciens, qu'il faut retrouver la fois suivante.
    Relire la liste coûte une cinquantaine de pages, c'est le prix de la
    reprise.
    """
    found: list[dict] = []
    for page_number in range(1, MAX_LIST_PAGES + 1):
        events = parse_event_list(_get(
            client, f"format?f={FORMAT_CODE}&meta={LIST_META_ID}&cp={page_number}"))
        if not events:
            # Une première page vide n'est pas « rien de neuf » : c'est la mise
            # en page qui a changé. Le taire viderait le méta en silence au fil
            # des purges.
            if page_number == 1:
                raise RuntimeError("MTGTop8 : aucun événement lisible sur la première page "
                                   "— la mise en page a changé, voir parse_event_list.")
            break
        for event in events:
            if event["event_date"] >= since and event["event_id"] not in known:
                found.append(event)
        if events[-1]["event_date"] < since:
            break
        time.sleep(delay)

    unique = {event["event_id"]: event for event in found}
    return sorted(unique.values(), key=lambda e: (e["event_date"], e["event_id"]), reverse=True)


# --- Base ------------------------------------------------------------------------


def _known_events() -> set[int]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT event_id FROM duel_events")
            return {row["event_id"] for row in cur.fetchall()}


def _save_event(event: dict, decks: list[dict]) -> None:
    """
    Un événement et ses decks, **dans une seule transaction** : un événement
    enregistré est un événement qu'on ne redemandera plus. L'écrire avant ses
    decks, puis échouer entre les deux, les perdrait pour toujours.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO duel_events (event_id, name, event_date, players)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (event["event_id"], event["name"], event["event_date"], event["players"]),
            )
            for deck in decks:
                cur.execute(
                    """
                    INSERT INTO duel_decks (deck_id, event_id, rank_label, placement,
                                            deck_name, commander_oracle_ids,
                                            color_identity, type_counts, mana_curve,
                                            unresolved)
                    VALUES (%s, %s, %s, %s, %s, %s::uuid[], %s, %s, %s, %s)
                    ON CONFLICT (deck_id) DO NOTHING
                    """,
                    (deck["deck_id"], event["event_id"], deck["rank_label"],
                     deck["placement"], deck["deck_name"], deck["commanders"],
                     deck["color_identity"], Json(deck["type_counts"]),
                     Json(deck["mana_curve"]), deck["unresolved"]),
                )
                cur.executemany(
                    "INSERT INTO duel_deck_cards (deck_id, oracle_id) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING",
                    [(deck["deck_id"], oracle_id) for oracle_id in deck["cards"]],
                )


def deck_profile(cards: list[tuple[int, dict]]) -> tuple[dict[str, int], dict[str, int]]:
    """
    (cartes par type, courbe des non-terrains) d'une liste `[(quantité, carte)]`.

    Même forme que les profils EDHREC de `commander_themes`, et même règle de
    classement (`competitive.type_of`) : une carte multi-type ne compte qu'une
    fois, les terrains d'abord. Les **terrains de base comptent** dans
    « Land » — ce sont eux qui font le nombre de terrains d'une liste.
    """
    type_counts: dict[str, int] = {}
    curve: dict[str, int] = {}
    for quantity, card in cards:
        card_type = competitive.type_of(card)
        if card_type is None:
            continue
        type_counts[card_type] = type_counts.get(card_type, 0) + quantity
        if card_type != "Land":
            bucket = str(competitive.curve_bucket(card.get("cmc")))
            curve[bucket] = curve.get(bucket, 0) + quantity
    return type_counts, curve


def _resolve_deck(export: dict, resolved: dict[str, dict]) -> dict | None:
    """
    Les identifiants et le profil d'un deck exporté. `None` si un commandant
    n'est pas reconnu : sans lui, ni l'identité du deck ni le commandant auquel
    rattacher la liste ne sont connus, et un deck à identité fausse fausserait
    tous les dénominateurs.
    """
    commanders = [resolved.get(name.lower()) for name in export["commanders"]]
    if not commanders or any(card is None for card in commanders):
        return None

    commander_ids = {str(card["oracle_id"]) for card in commanders}
    identity = sorted({color for card in commanders for color in card["color_identity"] or []})
    cards, found, unresolved = set(), [], 0
    for quantity, name in export["cards"]:
        card = resolved.get(name.lower())
        if card is None:
            unresolved += 1
            continue
        oracle_id = str(card["oracle_id"])
        if oracle_id in commander_ids:
            continue
        found.append((quantity, card))
        # Les basiques comptent dans le profil, pas dans les cartes jouées :
        # ils ne se choisissent pas et ne s'achètent pas.
        if not (card["type_line"] or "").startswith("Basic Land"):
            cards.add(oracle_id)

    type_counts, mana_curve = deck_profile(found)
    return {"commanders": sorted(commander_ids), "color_identity": identity,
            "cards": sorted(cards), "unresolved": unresolved,
            "type_counts": type_counts, "mana_curve": mana_curve}


def refresh_stats() -> int:
    """
    Recalcule `duel_card_stats` depuis les decks de la fenêtre. Renvoie le
    nombre de cartes mesurées.

    Le calcul est fait en Python (`compute_card_stats`) et non en SQL : c'est
    la formule qui porte toute la mesure, et elle se teste ainsi sans base.
    Quelques centaines de milliers de lignes se lisent en une seconde.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT deck_id, color_identity FROM duel_decks")
            deck_identities = {row["deck_id"]: row["color_identity"] or [] for row in cur.fetchall()}
            cur.execute("SELECT deck_id, oracle_id::text AS oracle_id FROM duel_deck_cards")
            deck_cards = [(row["deck_id"], row["oracle_id"]) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT c.oracle_id::text AS oracle_id, c.color_identity
                FROM cards_cheapest c
                WHERE c.oracle_id IN (SELECT DISTINCT oracle_id FROM duel_deck_cards)
                """
            )
            card_identities = {row["oracle_id"]: row["color_identity"] or [] for row in cur.fetchall()}

            stats = compute_card_stats(deck_identities, deck_cards, card_identities)
            # Dans la même transaction que la lecture : la page ne voit jamais
            # une table à moitié remplie.
            cur.execute("DELETE FROM duel_card_stats")
            cur.executemany(
                """
                INSERT INTO duel_card_stats (oracle_id, decks, eligible_decks, rate, share)
                VALUES (%(oracle_id)s, %(decks)s, %(eligible_decks)s, %(rate)s, %(share)s)
                """,
                stats,
            )
    return len(stats)


def _purge(before: date) -> int:
    """Les événements sortis de la fenêtre, decks et cartes en cascade."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM duel_events WHERE event_date < %s", (before,))
            return cur.rowcount


def sync(delay: float = DEFAULT_DELAY_SECONDS, window_days: int = WINDOW_DAYS,
         max_events: int = DEFAULT_MAX_EVENTS, log=print) -> dict:
    """
    Récupère les événements inconnus de la fenêtre, puis recalcule le méta.

    Un événement qui échoue (réseau, page illisible) n'est **pas** enregistré :
    il sera redemandé à l'exécution suivante. Un deck dont le commandant n'est
    pas reconnu est écarté et compté (`decks_skipped`), sans bloquer les
    autres.
    """
    since = date.today() - timedelta(days=window_days)
    summary = {"events_listed": 0, "events_saved": 0, "events_failed": [],
               "decks_saved": 0, "decks_skipped": [], "unresolved_cards": 0,
               "events_remaining": 0, "purged": 0, "cards_measured": 0}

    with httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
        pending = list_new_events(client, _known_events(), since, delay)
        summary["events_listed"] = len(pending)
        if max_events:
            summary["events_remaining"] = max(0, len(pending) - max_events)
            pending = pending[:max_events]

        for index, listed in enumerate(pending, 1):
            try:
                time.sleep(delay)
                event = parse_event(_get(client, f"event?e={listed['event_id']}&f={FORMAT_CODE}"))
                exports = {}
                for deck in event["decks"]:
                    time.sleep(delay)
                    exports[deck["deck_id"]] = parse_export(_get(client, f"mtgo?d={deck['deck_id']}"))
            except (httpx.HTTPError, ValueError) as error:
                summary["events_failed"].append({"event_id": listed["event_id"],
                                                 "reason": str(error)[:200]})
                continue

            names = sorted({name for export in exports.values()
                            for name in export["commanders"] + [n for _q, n in export["cards"]]})
            resolved = cards_db.resolve_names(names)

            decks = []
            for deck in event["decks"]:
                ids = _resolve_deck(exports[deck["deck_id"]], resolved)
                if ids is None:
                    summary["decks_skipped"].append({
                        "deck_id": deck["deck_id"],
                        "commanders": exports[deck["deck_id"]]["commanders"]})
                    continue
                summary["unresolved_cards"] += ids["unresolved"]
                decks.append({**deck, **ids})

            _save_event({**listed, "name": event["name"] or listed["name"],
                         "event_date": event["event_date"] or listed["event_date"],
                         "players": event["players"]}, decks)
            summary["events_saved"] += 1
            summary["decks_saved"] += len(decks)
            if index % 25 == 0:
                log(f"  {index}/{len(pending)} événements, {summary['decks_saved']} decks")

    summary["purged"] = _purge(since)
    summary["cards_measured"] = refresh_stats()
    return summary
