"""
services/video_cards.py — ce qu'une vidéo cite, constaté contre le catalogue.

Une retranscription est du texte ; le catalogue dit quelles suites de mots sont
des noms de cartes. Le croisement est donc un **constat**, pas une
interprétation : aucun modèle de langage n'a son mot à dire ici, il inventerait
parfois une carte là où la comparaison ne trouve rien.

Trois règles, toutes venues d'une mesure sur une vidéo réelle :

- **Deux mots minimum pour une carte.** Avec un seul mot autorisé, on ramassait
  « Concentration », « Dragons », « Embuscade », « Mutilation » — des mots
  français courants qui sont aussi des noms de cartes. Le filtre à deux mots a
  ramené onze cartes dont un seul faux positif, contre dix-huit dont sept.
- **Les cycles de terrains comptent autant que les cartes.** Une vidéo de
  manabase ne recommande pas des cartes une par une, elle recommande des
  familles : « checklands », « tango lands », « filtres d'Odyssey ». C'est le
  chapitrage de la vidéo qui le dit le plus proprement, parce qu'il est écrit.
- **Le chapitrage prime sur l'audio.** Les sous-titres automatiques n'ont ni
  ponctuation ni majuscules et écorchent les noms propres ; une ligne de
  description est du texte écrit par l'auteur.
"""
import re
import unicodedata

import db.cards as cards_db
from db.core import get_conn
from services import land_cycles

# Longueur maximale d'un nom de carte, en mots. Au-delà, on ne ferait que
# balayer du vide : le plus long nom du catalogue tient largement dedans.
MAX_WORDS = 6
MIN_WORDS = 2


def normalize(value: str) -> str:
    """Minuscules, sans accents ni ponctuation — la règle de `normalize_card_name`."""
    sans_accent = "".join(
        char for char in unicodedata.normalize("NFD", value.lower())
        if unicodedata.category(char) != "Mn"
    )
    sans_accent = sans_accent.replace("æ", "ae").replace("œ", "oe")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", sans_accent)).strip()


def _catalogue() -> dict[str, str]:
    """{nom normalisé: oracle_id}, français et anglais mêlés."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.oracle_id, c.name, fr.printed_name AS name_fr
                FROM cards_cheapest c
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                """
            )
            index: dict[str, str] = {}
            for row in cur.fetchall():
                for nom in (row["name"], row["name_fr"]):
                    if nom and len(normalize(nom).split()) >= MIN_WORDS:
                        index.setdefault(normalize(nom), str(row["oracle_id"]))
            return index


def _words_with_time(segments: list[dict]) -> list[tuple[str, float]]:
    mots: list[tuple[str, float]] = []
    for segment in segments:
        debut = float(segment.get("start") or 0)
        for mot in normalize(segment.get("text") or "").split():
            mots.append((mot, debut))
    return mots


def find_cards(segments: list[dict], index: dict[str, str] | None = None) -> list[dict]:
    """Les cartes citées : nom exact d'au moins deux mots, dans l'une des deux langues."""
    index = index if index is not None else _catalogue()
    mots = _words_with_time(segments)
    trouvees: dict[str, dict] = {}

    position = 0
    while position < len(mots):
        saut = 1
        for longueur in range(MAX_WORDS, MIN_WORDS - 1, -1):
            if position + longueur > len(mots):
                continue
            candidat = " ".join(mot for mot, _ in mots[position:position + longueur])
            oracle_id = index.get(candidat)
            if oracle_id:
                entree = trouvees.setdefault(oracle_id, {
                    "kind": "card", "key": oracle_id, "mentions": 0,
                    "first_seconds": int(mots[position][1]),
                })
                entree["mentions"] += 1
                saut = longueur
                break
        position += saut
    return list(trouvees.values())


def find_cycles(segments: list[dict], chapters: list[dict] | None = None) -> list[dict]:
    """
    Les cycles de terrains dont parle la vidéo.

    Le chapitrage d'abord — c'est de l'écrit, et un chapitre nommé « TANGO
    LANDS » désigne le cycle sans ambiguïté — puis l'audio, qui rattrape les
    cycles évoqués sans chapitre dédié.
    """
    trouves: dict[str, dict] = {}

    for chapitre in chapters or []:
        cle = land_cycles.cycle_of_text(chapitre.get("title") or "")
        if cle:
            entree = trouves.setdefault(cle, {
                "kind": "cycle", "key": cle, "mentions": 0,
                "first_seconds": int(chapitre.get("start") or 0),
            })
            entree["mentions"] += 1

    for segment in segments:
        cle = land_cycles.cycle_of_text(segment.get("text") or "")
        if not cle:
            continue
        entree = trouves.setdefault(cle, {
            "kind": "cycle", "key": cle, "mentions": 0,
            "first_seconds": int(float(segment.get("start") or 0)),
        })
        entree["mentions"] += 1

    return list(trouves.values())


def extract(segments: list[dict], chapters: list[dict] | None = None) -> list[dict]:
    """Tout ce que la vidéo cite : cartes et cycles, avec leur premier horodatage."""
    return find_cards(segments) + find_cycles(segments, chapters)


def describe(mentions: list[dict]) -> dict:
    """Le résultat rendu lisible : noms de cartes et libellés de cycles."""
    oracle_ids = [m["key"] for m in mentions if m["kind"] == "card"]
    cartes = {}
    for oracle_id in oracle_ids:
        carte = cards_db.get_cheapest_by_oracle_id(oracle_id)
        if carte:
            cartes[oracle_id] = carte
    return {
        "cards": [
            {**cartes[m["key"]], "mentions": m["mentions"], "first_seconds": m["first_seconds"]}
            for m in mentions if m["kind"] == "card" and m["key"] in cartes
        ],
        "cycles": [
            {**land_cycles.CYCLES_BY_KEY[m["key"]], "mentions": m["mentions"],
             "first_seconds": m["first_seconds"]}
            for m in mentions if m["kind"] == "cycle" and m["key"] in land_cycles.CYCLES_BY_KEY
        ],
    }
