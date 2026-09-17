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
from db.themes import ALL_THEMES_LABEL, ALL_THEMES_SLUG

EDHREC_JSON_BASE = "https://json.edhrec.com/pages/commanders"
DEFAULT_DELAY_SECONDS = 1.0

# Thèmes récupérés par commandant, les plus joués d'abord. Au-delà, ce sont des
# archétypes confidentiels dont les listes ne veulent statistiquement rien dire
# — et chaque thème coûte une requête à un site communautaire gratuit.
MAX_THEMES_PER_COMMANDER = 8
# En dessous, l'échantillon est trop mince pour qu'un taux d'inclusion ait un
# sens : quelques dizaines de decks suffisent à faire dire n'importe quoi.
MIN_THEME_DECKS = 50


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
    # Légal dans **l'un ou l'autre** format : les recommandations EDHREC ne
    # dépendent pas du format, et un commandant jouable en duel seulement
    # (Rofellos, Leovold, Griselbrand) mérite les siennes autant qu'un autre.
    # Filtrer sur `legal_commander` seul les privait de données à jamais.
    sources = ["""
        SELECT DISTINCT c.oracle_id, c.name
        FROM collection col
        JOIN cards c ON c.oracle_id = col.oracle_id
        WHERE (c.legal_commander OR c.legal_duel)
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


def fetch_theme(client: httpx.Client, slug: str, theme_slug: str) -> dict | None:
    """La page d'un thème pour un commandant : mêmes sections, listes filtrées."""
    response = client.get(f"{EDHREC_JSON_BASE}/{slug}/{theme_slug}.json")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def extract_themes(payload: dict) -> list[dict]:
    """
    Les archétypes du commandant, du plus joué au moins joué. `tag_counts` est
    la source : `panels.taglinks` porte la même chose pour l'affichage.
    """
    themes = []
    for tag in payload.get("tag_counts") or []:
        if not tag.get("slug") or (tag.get("count") or 0) < MIN_THEME_DECKS:
            continue
        themes.append({"slug": tag["slug"], "label": tag.get("value") or tag["slug"],
                       "deck_count": tag["count"]})
    return themes[:MAX_THEMES_PER_COMMANDER]


def extract_profile(payload: dict) -> tuple[dict, dict]:
    """
    (cartes par type, courbe de mana) des decks réels du thème.

    C'est une cible **mesurée** et non un repère inventé : le camembert
    d'EDHREC dit combien de terrains et de créatures jouent ceux qui montent
    cette stratégie, et la courbe dit à quels coûts. Les deux servent de
    gabarit au constructeur.
    """
    panels = payload.get("panels") or {}
    type_counts = {
        entry["label"]: entry["value"]
        for entry in (panels.get("piechart") or {}).get("content") or []
        if entry.get("label") is not None
    }
    curve = {str(k): v for k, v in (panels.get("mana_curve") or {}).items()}
    return type_counts, curve


def total_decks(payload: dict) -> int:
    """
    Le nombre de decks recensés pour ce commandant.

    Il n'est écrit nulle part tel quel : chaque carte porte le `potential_decks`
    de sa section, et les sections éditoriales (« New Cards ») en couvrent un
    sous-ensemble. Le maximum est donc le seul total fiable.
    """
    return max(
        (card.get("potential_decks") or 0)
        for section in payload.get("container", {}).get("json_dict", {}).get("cardlists", [])
        for card in section.get("cardviews", [])
    ) if payload.get("container") else 0


def store_themes(commander_oracle_id: str, themes: list[dict]) -> None:
    """Remplace les thèmes du commandant : table entièrement reconstructible."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM commander_themes WHERE commander_oracle_id = %s",
                        (commander_oracle_id,))
            for theme in themes:
                cur.execute(
                    """
                    INSERT INTO commander_themes
                        (commander_oracle_id, slug, label, deck_count, type_counts, mana_curve)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (commander_oracle_id, theme["slug"], theme["label"], theme["deck_count"],
                     json.dumps(theme.get("type_counts") or {}),
                     json.dumps(theme.get("mana_curve") or {})),
                )


def store_theme_cards(commander_oracle_id: str, theme_slug: str, recommendations: list) -> int:
    """Même conversion `scryfall_id` -> `oracle_id` que pour le commandant."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM theme_recommendations "
                "WHERE commander_oracle_id = %s AND theme_slug = %s",
                (commander_oracle_id, theme_slug),
            )
            if not recommendations:
                return 0
            cur.execute(
                """
                INSERT INTO theme_recommendations
                    (commander_oracle_id, theme_slug, card_oracle_id, section, synergy, inclusion_rate)
                SELECT %(commander)s, %(theme)s, c.oracle_id, v.section, v.synergy, v.inclusion
                FROM unnest(%(ids)s::uuid[], %(sections)s::text[],
                            %(synergies)s::numeric[], %(inclusions)s::numeric[])
                     AS v(scryfall_id, section, synergy, inclusion)
                JOIN cards c ON c.scryfall_id = v.scryfall_id
                ON CONFLICT DO NOTHING
                """,
                {"commander": commander_oracle_id, "theme": theme_slug,
                 "ids": [r[0] for r in recommendations], "sections": [r[1] for r in recommendations],
                 "synergies": [r[2] for r in recommendations],
                 "inclusions": [r[3] for r in recommendations]},
            )
            cur.execute(
                "SELECT count(DISTINCT card_oracle_id) AS cards FROM theme_recommendations "
                "WHERE commander_oracle_id = %s AND theme_slug = %s",
                (commander_oracle_id, theme_slug),
            )
            return cur.fetchone()["cards"]


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




def sync(include_decks: bool = False, delay: float = DEFAULT_DELAY_SECONDS,
         with_themes: bool = True) -> dict:
    """
    Renvoie un résumé exploitable par un ordonnanceur (Kestra lit le JSON).

    `with_themes` récupère en plus, pour chaque commandant, les archétypes les
    plus joués et leurs listes de cartes. C'est ce qui permet de construire un
    deck *orienté* (Atraxa infect) plutôt qu'un agrégat de tout ce qui se joue
    avec le commandant. Une requête par thème : d'où le plafond, la pause
    conservée entre chaque, et la possibilité de couper.
    """
    commanders = commanders_to_fetch(include_decks)
    resultats, introuvables, echecs = [], [], []
    themes_total = 0

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

            themes = []
            if with_themes:
                # L'agrégat d'abord : il ne coûte aucune requête (tout est déjà
                # dans la page du commandant) et garantit qu'aucun commandant
                # possédé ne reste sans porte d'entrée.
                types_all, curve_all = extract_profile(payload)
                themes.append({"slug": ALL_THEMES_SLUG, "label": ALL_THEMES_LABEL,
                               "deck_count": total_decks(payload),
                               "type_counts": types_all, "mana_curve": curve_all})
                for theme in extract_themes(payload):
                    time.sleep(delay)
                    try:
                        theme_payload = fetch_theme(client, slug, theme["slug"])
                    except httpx.HTTPError as error:
                        echecs.append({"commander": f"{name} / {theme['slug']}",
                                       "reason": str(error)})
                        continue
                    if theme_payload is None:
                        continue
                    type_counts, curve = extract_profile(theme_payload)
                    theme = {**theme, "type_counts": type_counts, "mana_curve": curve}
                    themes.append(theme)
                    store_theme_cards(oracle_id, theme["slug"],
                                      extract_recommendations(theme_payload))
                store_themes(oracle_id, themes)
                themes_total += len(themes)

            resultats.append({"commander": name, "recommendations": stored,
                              "themes": [t["slug"] for t in themes]})

            if index < len(commanders) - 1:
                time.sleep(delay)

    return {
        "commanders_found": len(commanders),
        "synced": len(resultats),
        "recommendations_total": sum(r["recommendations"] for r in resultats),
        "themes_total": themes_total,
        "not_found": introuvables,
        "failed": echecs,
        "details": resultats,
    }
