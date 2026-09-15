"""
services/edhrec.py — récupération des recommandations EDHREC par commandant.

Source : les endpoints JSON publics de json.edhrec.com. Ce n'est **pas une API
officielle documentée** : elle peut changer sans préavis, d'où un module isolé
et des tables reconstructibles. Le robots.txt d'EDHREC interdit /deckpreview/
(decks individuels d'utilisateurs), qu'on ne touche donc pas ; les pages
commandants sont explicitement sitemapées.

EDHREC est un site communautaire gratuit : une pause entre chaque requête, et
on ne récupère que les commandants réellement possédés.

Ce module est appelé aussi bien par `scripts/sync_edhrec.py` (ligne de commande)
que par l'endpoint d'administration (déclenché par Kestra) : une seule
implémentation, l'ordonnanceur reste interchangeable.
"""
import json
import re
import time
import unicodedata

import httpx

from config import SCRYFALL_HEADERS
from db.core import get_conn

EDHREC_JSON_BASE = "https://json.edhrec.com/pages/commanders"
DEFAULT_DELAY_SECONDS = 1.0

# Sections retenues : celles qui portent une information exploitable pour
# construire un deck. Les rubriques éditoriales ("New Cards") sont ignorées.
WANTED_SECTIONS = {
    "High Synergy Cards", "Top Cards", "Game Changers",
    "Creatures", "Instants", "Sorceries", "Artifacts",
    "Enchantments", "Planeswalkers", "Utility Lands", "Mana Artifacts",
}


def slugify(name: str) -> str:
    """
    « Krenko, Mob Boss » -> « krenko-mob-boss ». Les cartes double-face sont
    référencées par leur face avant seule.
    """
    name = name.split(" // ")[0]
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^\w\s-]", "", name.lower())
    return re.sub(r"[\s_]+", "-", name).strip("-")


def commanders_to_fetch(include_decks: bool) -> list[tuple[str, str]]:
    """[(oracle_id, nom)] — les légendaires possédés, et optionnellement ceux
    déjà utilisés comme commandant dans un deck."""
    sources = ["""
        SELECT DISTINCT c.oracle_id, c.name
        FROM collection col
        JOIN cards c ON c.oracle_id = col.oracle_id
        WHERE c.legal_commander
          AND (c.type_line LIKE 'Legendary Creature%%'
               OR c.oracle_text ILIKE '%%can be your commander%%')
    """]
    if include_decks:
        sources.append("""
            SELECT DISTINCT c.oracle_id, c.name
            FROM deck_cards dc
            JOIN cards c ON c.scryfall_id = dc.scryfall_id
            WHERE dc.is_commander
        """)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(" UNION ".join(sources) + " ORDER BY 2")
            return [(str(row["oracle_id"]), row["name"]) for row in cur.fetchall()]


def fetch_commander(client: httpx.Client, slug: str) -> dict | None:
    response = client.get(f"{EDHREC_JSON_BASE}/{slug}.json")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def extract_recommendations(payload: dict) -> list[tuple[str, str, float | None, float | None]]:
    """[(scryfall_id, section, synergy, taux d'inclusion)] depuis le JSON EDHREC."""
    rows = []
    for section in payload.get("container", {}).get("json_dict", {}).get("cardlists", []):
        header = section.get("header", "")
        if header not in WANTED_SECTIONS:
            continue
        for card in section.get("cardviews", []):
            scryfall_id = card.get("id")
            if not scryfall_id:
                continue
            decks, potential = card.get("num_decks"), card.get("potential_decks")
            inclusion = decks / potential if decks and potential else None
            rows.append((scryfall_id, header, card.get("synergy"), inclusion))
    return rows


def store(commander_oracle_id: str, recommendations: list, bracket_counts: dict | None) -> int:
    """
    Les cartes sont référencées par `scryfall_id` chez EDHREC : on le convertit
    en `oracle_id` via notre propre base. Une carte inconnue (impression qu'on
    ne synchronise pas) est simplement ignorée plutôt que de faire échouer le lot.

    Renvoie le nombre de **cartes** retenues, pas de lignes insérées : une carte
    peut figurer dans plusieurs sections (« Top Cards » et « Creatures »), et la
    clé primaire les garde toutes. Compter les lignes gonflerait le résumé lu
    par l'ordonnanceur d'un facteur qui n'a aucun sens métier.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM commander_recommendations WHERE commander_oracle_id = %s",
                (commander_oracle_id,),
            )
            stored = 0
            if recommendations:
                # `unnest` de colonnes parallèles plutôt qu'un VALUES construit :
                # une seule requête, et la constante `commander` se place
                # naturellement dans le SELECT.
                cur.execute(
                    """
                    INSERT INTO commander_recommendations
                        (commander_oracle_id, card_oracle_id, section, synergy, inclusion_rate)
                    SELECT %(commander)s, c.oracle_id, v.section, v.synergy, v.inclusion
                    FROM unnest(%(ids)s::uuid[], %(sections)s::text[],
                                %(synergies)s::numeric[], %(inclusions)s::numeric[])
                         AS v(scryfall_id, section, synergy, inclusion)
                    JOIN cards c ON c.scryfall_id = v.scryfall_id
                    ON CONFLICT DO NOTHING
                    """,
                    {
                        "commander": commander_oracle_id,
                        "ids": [r[0] for r in recommendations],
                        "sections": [r[1] for r in recommendations],
                        "synergies": [r[2] for r in recommendations],
                        "inclusions": [r[3] for r in recommendations],
                    },
                )
                cur.execute(
                    "SELECT count(DISTINCT card_oracle_id) AS cards "
                    "FROM commander_recommendations WHERE commander_oracle_id = %s",
                    (commander_oracle_id,),
                )
                stored = cur.fetchone()["cards"]

            if bracket_counts:
                cur.execute(
                    """
                    INSERT INTO commander_brackets (commander_oracle_id, counts)
                    VALUES (%s, %s)
                    ON CONFLICT (commander_oracle_id)
                    DO UPDATE SET counts = EXCLUDED.counts, fetched_at = now()
                    """,
                    (commander_oracle_id, json.dumps(bracket_counts)),
                )
    return stored




def sync(include_decks: bool = False, delay: float = DEFAULT_DELAY_SECONDS) -> dict:
    """Renvoie un résumé exploitable par un ordonnanceur (Kestra lit le JSON)."""
    commanders = commanders_to_fetch(include_decks)
    resultats, introuvables, echecs = [], [], []

    with httpx.Client(timeout=30, headers=SCRYFALL_HEADERS, follow_redirects=True) as client:
        for index, (oracle_id, name) in enumerate(commanders):
            slug = slugify(name)
            try:
                payload = fetch_commander(client, slug)
            except httpx.HTTPError as error:
                echecs.append({"commander": name, "reason": str(error)})
                continue

            if payload is None:
                introuvables.append({"commander": name, "slug": slug})
                continue

            stored = store(oracle_id, extract_recommendations(payload), payload.get("bracket_counts"))
            resultats.append({"commander": name, "recommendations": stored})

            if index < len(commanders) - 1:
                time.sleep(delay)

    return {
        "commanders_found": len(commanders),
        "synced": len(resultats),
        "recommendations_total": sum(r["recommendations"] for r in resultats),
        "not_found": introuvables,
        "failed": echecs,
        "details": resultats,
    }
