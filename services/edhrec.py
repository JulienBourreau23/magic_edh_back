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
# construire un deck. Les rubriques éditoriales ("New Cards", "New Commanders")
# sont ignorées.
#
# **« Utility Artifacts », et non « Artifacts ».** C'est le libellé réel
# d'EDHREC, sur les pages commandants comme sur les pages archétypes ; le nom
# au singulier ne correspondait à aucune section et la liste entière était donc
# jetée en silence — les rochers de mana passaient par « Mana Artifacts », mais
# ni Skullclamp, ni les bottes, ni les moteurs à artefacts. Erreur invisible
# type : rien n'échoue, le vivier est seulement plus pauvre qu'il ne devrait.
# **Correction sans effet tant que `sync_edhrec.py` n'a pas été relancé.**
#
# « Lands » reste volontairement dehors : le noyau conseillé par le projet est
# non-terrain (la manabase est gratuite et se calcule ailleurs), et faire
# entrer cinquante terrains par commandant changerait le contenu de
# `/deck-ideas`, `/deck-plans` et `/competitive` sans que personne ne l'ait
# demandé.
WANTED_SECTIONS = {
    "High Synergy Cards", "Top Cards", "Game Changers",
    "Creatures", "Instants", "Sorceries", "Utility Artifacts",
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


# --- Les archétypes du format, indépendamment d'un commandant ----------------
#
# Deuxième famille d'endpoints du même site : `/pages/tags/themes.json` liste
# les archétypes recensés, `/pages/tags/<slug>.json` donne pour chacun ses
# commandants et ses cartes. Elle est sitemapée (`/sitemaps/tags.xml`), donc
# voulue, au même titre que les pages commandants.
#
# **Ce n'est pas la même question que `commander_themes`.** Celle-là part d'un
# commandant possédé et demande ce qu'on monte derrière lui ; celle-ci part
# d'une stratégie et demande qui la pilote — y compris des commandants qu'on ne
# possède pas, ce qui est tout l'intérêt d'une page de découverte.
#
# Ce que ces pages ne contiennent **pas** : une description. Le champ existe et
# il est vide, sur les pages tags comme sur les pages commandants. Le principe
# du style de jeu est donc écrit à la main (`services/archetype_notes.py`) — ce
# n'est pas un oubli de synchronisation, et aucune resynchronisation ne le
# remplira.

EDHREC_TAGS_BASE = "https://json.edhrec.com/pages/tags"

# En dessous, le taux d'inclusion est calculé sur une poignée de decks et ne
# veut rien dire — la queue du classement, ce sont « planechase » ou « dandan »
# à cinq decks. Le plancher est plus haut que `MIN_THEME_DECKS` (50) parce que
# l'assiette n'est pas la même : là on comptait les decks d'un seul commandant,
# ici ceux du format entier. Mesuré sur le catalogue : 270 archétypes recensés,
# 183 au-dessus de ce seuil.
MIN_ARCHETYPE_DECKS = 500


def fetch_tag_index(client: httpx.Client) -> dict | None:
    """Le catalogue des archétypes : une seule requête pour les 270."""
    response = client.get(f"{EDHREC_TAGS_BASE}/themes.json")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def extract_tag_index(payload: dict) -> list[dict]:
    """
    [{slug, label, deck_count}] — les archétypes au-dessus du plancher.

    Le `slug` utile est dans l'`url` (`/tags/tokens`), **pas** dans le champ
    `slug` : celui-ci porte la carte qui illustre la vignette (« skullclamp »
    pour Tokens). Prendre le mauvais aurait donné des 403 en série, et un 403
    est ici un « cette page n'existe pas » — le bucket répond ainsi aux clés
    absentes, faute de droit de listage.
    """
    archetypes = []
    for section in payload.get("container", {}).get("json_dict", {}).get("cardlists", []):
        for entry in section.get("cardviews", []):
            url = entry.get("url") or ""
            if not url.startswith("/tags/"):
                continue
            decks = entry.get("num_decks") or 0
            if decks < MIN_ARCHETYPE_DECKS:
                continue
            archetypes.append({"slug": url.removeprefix("/tags/"),
                               "label": entry.get("name") or url.removeprefix("/tags/"),
                               "deck_count": decks})
    return archetypes


def fetch_tag(client: httpx.Client, slug: str) -> dict | None:
    response = client.get(f"{EDHREC_TAGS_BASE}/{slug}.json")
    if response.status_code in (403, 404):
        # 403 : clé absente du bucket S3, qui ne distingue pas « interdit » de
        # « inexistant » quand le listage n'est pas autorisé. Dans les deux cas
        # il n'y a rien à lire.
        return None
    response.raise_for_status()
    return response.json()


def extract_tag_commanders(payload: dict) -> list[tuple[str, int, int]]:
    """[(scryfall_id, decks de ce commandant dans l'archétype, decks de l'archétype)]."""
    rows = []
    for section in payload.get("container", {}).get("json_dict", {}).get("cardlists", []):
        if section.get("tag") != "topcommanders":
            continue
        for entry in section.get("cardviews", []):
            if entry.get("id"):
                rows.append((entry["id"], entry.get("num_decks") or 0,
                             entry.get("potential_decks") or 0))
    return rows


def store_archetype(slug: str, label: str, deck_count: int, cards: list,
                    commanders: list[tuple[str, int, int]]) -> tuple[int, int]:
    """
    Remplace un archétype et tout ce qui s'y rattache, en une transaction.

    `ON DELETE CASCADE` fait le ménage des deux tables filles : un archétype
    dont EDHREC a retiré des cartes ne doit pas les garder. Les identifiants
    sont convertis de `scryfall_id` en `oracle_id` par jointure sur notre base,
    comme partout ailleurs — une impression inconnue est ignorée plutôt que de
    faire échouer le lot.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM archetypes WHERE slug = %s", (slug,))
            cur.execute(
                "INSERT INTO archetypes (slug, label, deck_count) VALUES (%s, %s, %s)",
                (slug, label, deck_count),
            )
            if cards:
                cur.execute(
                    """
                    INSERT INTO archetype_cards
                        (archetype_slug, card_oracle_id, section, synergy, inclusion_rate)
                    SELECT %(slug)s, c.oracle_id, v.section, v.synergy, v.inclusion
                    FROM unnest(%(ids)s::uuid[], %(sections)s::text[],
                                %(synergies)s::numeric[], %(inclusions)s::numeric[])
                         AS v(scryfall_id, section, synergy, inclusion)
                    JOIN cards c ON c.scryfall_id = v.scryfall_id
                    ON CONFLICT DO NOTHING
                    """,
                    {"slug": slug, "ids": [r[0] for r in cards],
                     "sections": [r[1] for r in cards], "synergies": [r[2] for r in cards],
                     "inclusions": [r[3] for r in cards]},
                )
            if commanders:
                # `DISTINCT ON` et non `ON CONFLICT` : deux entrées d'EDHREC
                # peuvent viser deux **impressions** d'un même commandant, donc
                # le même `oracle_id`. Postgres refuse alors la mise à jour
                # d'une ligne deux fois dans la même commande
                # (`CardinalityViolation`) et toute la synchro s'arrête —
                # constaté sur le catalogue réel. On garde l'impression la plus
                # jouée, qui est celle dont le compte nous intéresse.
                cur.execute(
                    """
                    INSERT INTO archetype_commanders
                        (archetype_slug, commander_oracle_id, num_decks, potential_decks)
                    SELECT DISTINCT ON (c.oracle_id)
                           %(slug)s, c.oracle_id, v.decks, v.potential
                    FROM unnest(%(ids)s::uuid[], %(decks)s::int[], %(potential)s::int[])
                         AS v(scryfall_id, decks, potential)
                    JOIN cards c ON c.scryfall_id = v.scryfall_id
                    ORDER BY c.oracle_id, v.decks DESC
                    """,
                    {"slug": slug, "ids": [r[0] for r in commanders],
                     "decks": [r[1] for r in commanders],
                     "potential": [r[2] for r in commanders]},
                )

            cur.execute("SELECT count(DISTINCT card_oracle_id) AS cards "
                        "FROM archetype_cards WHERE archetype_slug = %s", (slug,))
            stored_cards = cur.fetchone()["cards"]
            cur.execute("SELECT count(*) AS commanders "
                        "FROM archetype_commanders WHERE archetype_slug = %s", (slug,))
            return stored_cards, cur.fetchone()["commanders"]


def sync_archetypes(delay: float = DEFAULT_DELAY_SECONDS,
                    limit: int | None = None) -> dict:
    """
    Le catalogue des archétypes, une requête par archétype.

    Mesuré sur le catalogue entier : 183 archétypes au-dessus du plancher,
    **4 min 37 s**, 56 964 cartes et 4 324 commandants. C'est très au-delà de
    ce qu'un endpoint HTTP peut porter — Kestra compte l'attente comme de l'inactivité, et
    Cloudflare coupe à 100 s : cette synchronisation n'existe donc qu'en ligne
    de commande et par le `case` SSH de `deploy/kestra-sync.sh`, contrairement
    à `sync-combos` qui tient en HTTP.

    Chaque archétype est écrit dès qu'il est lu : une coupure en cours de route
    laisse un catalogue partiel mais cohérent, et la reprise se contente de
    tout réécrire. C'est le choix inverse de `sync_combos`, qui n'écrit qu'à la
    fin — là-bas le catalogue est une seule liste, ici ce sont 183 listes
    indépendantes.
    """
    resultats, echecs = [], []
    with httpx.Client(timeout=30, headers=SCRYFALL_HEADERS, follow_redirects=True) as client:
        index = fetch_tag_index(client)
        if index is None:
            return {"archetypes_found": 0, "synced": 0, "cards_total": 0,
                    "commanders_total": 0, "failed": [{"archetype": "index",
                                                       "reason": "catalogue introuvable"}],
                    "details": []}

        archetypes = extract_tag_index(index)[:limit]
        for position, archetype in enumerate(archetypes):
            time.sleep(delay)
            try:
                payload = fetch_tag(client, archetype["slug"])
            except httpx.HTTPError as error:
                echecs.append({"archetype": archetype["slug"], "reason": str(error)})
                continue
            if payload is None:
                echecs.append({"archetype": archetype["slug"], "reason": "page absente"})
                continue

            cards, commanders = store_archetype(
                archetype["slug"], archetype["label"], archetype["deck_count"],
                extract_recommendations(payload), extract_tag_commanders(payload),
            )
            resultats.append({"archetype": archetype["slug"], "label": archetype["label"],
                              "cards": cards, "commanders": commanders})

    return {
        "archetypes_found": len(archetypes),
        "synced": len(resultats),
        "cards_total": sum(r["cards"] for r in resultats),
        "commanders_total": sum(r["commanders"] for r in resultats),
        "failed": echecs,
        "details": resultats,
    }
