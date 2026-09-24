"""
db/duel_meta.py — ce que jouent les tops des tournois de Duel Commander.

Les tables viennent de MTGTop8 (`services/mtgtop8.py`). Elles alimentent, **en
format duel seulement**, ce qu'EDHREC alimentait faute de mieux : le deck
compétitif, les cartes à avoir et les suggestions. Le multijoueur n'en voit
rien.

Deux « thèmes » en sortent, avec la même forme que ceux d'EDHREC
(`commander_themes`) pour que le constructeur compétitif les vise sans rien
convertir :

- **les listes de tournoi du commandant** (`COMMANDER_SLUG`), quand il en a
  assez (`MIN_COMMANDER_DECKS`) : taux d'inclusion et profil mesurés sur ses
  propres tops. C'est la meilleure réponse possible, et elle n'existe que pour
  les commandants joués en tournoi ;
- **le méta du duel** (`META_SLUG`), toujours disponible : le taux de chaque
  carte parmi les decks qui **pouvaient** la jouer (`duel_card_stats.rate`).
  C'est ce qui reste pour un commandant absent des tops — les cartes qui
  gagnent en duel dans ses couleurs, départagées par ce qu'EDHREC voit jouer
  avec lui. Il ne connaît pas le plan du commandant : c'est sa limite, et
  l'écran la dit.
"""
from psycopg2 import errors

from db.core import get_conn

SOURCE = "mtgtop8"
COMMANDER_SLUG = "_duel_top8"
META_SLUG = "_duel_meta"
SLUGS = (COMMANDER_SLUG, META_SLUG)

# En dessous, un taux d'inclusion par commandant se lit sur trois ou quatre
# listes : une carte fétiche d'un seul joueur y pèserait 25 %.
MIN_COMMANDER_DECKS = 8
# Un taux de méta rapporté à moins de decks éligibles ne mesure rien : une
# carte cinq couleurs vue dans un des deux decks cinq couleurs afficherait
# 50 %. Elle compte alors comme non mesurée.
MIN_ELIGIBLE_DECKS = 20
# Le profil du méta (terrains, types, courbe) se prend sur les decks de la même
# identité quand ils sont assez nombreux, sur tout le format sinon : un
# mono-vert et un Izzet tempo ne se construisent pas pareil, mais trois decks
# ne font pas un profil.
MIN_PROFILE_DECKS = 20
NONLAND_SLOTS = 63

COMMANDER_LABEL = "Ses listes de tournoi (duel)"
META_LABEL = "Méta du duel dans ses couleurs"

_IS_COMMANDER_TYPE = """
    (c.type_line LIKE 'Legendary Creature%%'
     OR c.oracle_text ILIKE '%%can be your commander%%')
"""


def available() -> bool:
    """
    Le méta est-il là ? Faux tant que la synchronisation n'a pas tourné — et
    aussi tant que la migration 022 n'a pas été jouée : le code peut être
    déployé avant elle sans casser le duel, qui retombe alors sur EDHREC.
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT EXISTS (SELECT 1 FROM duel_card_stats) AS ok")
                return bool(cur.fetchone()["ok"])
    except errors.UndefinedTable:
        return False


def summary() -> dict:
    """Ce sur quoi reposent les chiffres : combien de decks, sur quelle période."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(DISTINCT e.event_id) AS events, count(d.deck_id) AS decks,
                       min(e.event_date) AS since, max(e.event_date) AS until
                FROM duel_events e
                LEFT JOIN duel_decks d ON d.event_id = e.event_id
                """
            )
            row = cur.fetchone()
    return {"events": row["events"], "decks": row["decks"],
            "since": row["since"].isoformat() if row["since"] else None,
            "until": row["until"].isoformat() if row["until"] else None}


def average_profile(profiles: list[dict]) -> tuple[dict[str, int], dict[str, int]]:
    """
    La moyenne arrondie de profils `{"type_counts", "mana_curve"}`.

    Un type absent d'un deck compte pour zéro dans ce deck : sans ça, trois
    planeswalkers dans un seul deck sur vingt feraient une cible de trois.
    """
    if not profiles:
        return {}, {}
    count = len(profiles)
    types: dict[str, float] = {}
    curve: dict[str, float] = {}
    for profile in profiles:
        for key, value in (profile.get("type_counts") or {}).items():
            types[key] = types.get(key, 0) + value
        for key, value in (profile.get("mana_curve") or {}).items():
            curve[key] = curve.get(key, 0) + value
    return ({key: round(value / count) for key, value in types.items() if round(value / count)},
            {key: round(value / count) for key, value in curve.items()})


def _profiles(where: str, params: dict) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT type_counts, mana_curve FROM duel_decks d WHERE {where}", params)
            return cur.fetchall()


def themes_for(commander_oracle_id: str, identity: list[str]) -> list[dict]:
    """
    Les thèmes de duel d'un commandant, sous la forme de `commander_themes` —
    plus `source`, que l'écran affiche : ces chiffres ne se lisent pas comme
    ceux d'EDHREC.
    """
    if not available():
        return []

    themes = []
    own = _profiles("d.commander_oracle_ids @> ARRAY[%(c)s]::uuid[]", {"c": commander_oracle_id})
    if len(own) >= MIN_COMMANDER_DECKS:
        type_counts, curve = average_profile(own)
        themes.append({"slug": COMMANDER_SLUG, "label": COMMANDER_LABEL,
                       "deck_count": len(own), "type_counts": type_counts,
                       "mana_curve": curve, "source": SOURCE})

    same_identity = _profiles("d.color_identity @> %(i)s::text[] AND d.color_identity <@ %(i)s::text[]",
                              {"i": sorted(identity)})
    profiles = same_identity if len(same_identity) >= MIN_PROFILE_DECKS else _profiles("TRUE", {})
    type_counts, curve = average_profile(profiles)
    themes.append({"slug": META_SLUG, "label": META_LABEL,
                   "deck_count": summary()["decks"], "type_counts": type_counts,
                   "mana_curve": curve, "source": SOURCE,
                   # Dit à l'écran d'où vient la cible de courbe et de types.
                   "profile_decks": len(profiles),
                   "profile_scope": "identity" if profiles is same_identity else "format"})
    return themes


# Les taux d'inclusion d'un commandant sur ses propres listes, bornés à son
# identité : une liste de partenaires (Kraum + Yoshimaru) joue des cartes
# blanches que Kraum seul ne peut pas jouer.
_OWN_RATES = """
    commander_decks AS (
        SELECT deck_id FROM duel_decks
        WHERE commander_oracle_ids @> ARRAY[%(commander)s]::uuid[]
    ),
    own_rates AS (
        SELECT dc.oracle_id,
               count(*)::float / (SELECT count(*) FROM commander_decks) AS rate
        FROM duel_deck_cards dc
        WHERE dc.deck_id IN (SELECT deck_id FROM commander_decks)
        GROUP BY dc.oracle_id
    ),
    meta_rates AS (
        SELECT oracle_id, rate FROM duel_card_stats
        WHERE eligible_decks >= %(min_eligible)s
    )
"""


def build_pool(commander_oracle_id: str, theme_slug: str, identity: list[str]) -> list[dict]:
    """
    Le vivier du deck compétitif en duel, avec les mêmes colonnes que
    `themes_db.build_pool` : `theme_rate` classe, `commander_rate` départage.

    - listes du commandant : `theme_rate` = inclusion dans ses tops,
      `commander_rate` = taux dans le méta ;
    - méta : `theme_rate` = taux dans le méta, `commander_rate` = inclusion
      EDHREC derrière ce commandant. C'est ce qui ramène son plan de jeu à
      égalité de méta — sans jamais le faire passer devant ce qui gagne en duel.

    Mêmes filtres durs qu'ailleurs : banlist du duel, identité, basiques.
    """
    if theme_slug == COMMANDER_SLUG:
        theme_rate, commander_rate = "own_rates.rate", "meta_rates.rate"
    else:
        theme_rate, commander_rate = "meta_rates.rate", "edhrec.rate"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH {_OWN_RATES},
                edhrec AS (
                    SELECT card_oracle_id AS oracle_id, max(inclusion_rate) AS rate
                    FROM commander_recommendations
                    WHERE commander_oracle_id = %(commander)s
                    GROUP BY card_oracle_id
                ),
                candidate AS (
                    SELECT oracle_id FROM meta_rates
                  UNION SELECT oracle_id FROM own_rates
                  UNION SELECT oracle_id FROM edhrec
                  UNION SELECT oracle_id FROM collection
                )
                SELECT c.*,
                       COALESCE({theme_rate}, 0)::float AS theme_rate,
                       COALESCE({commander_rate}, 0)::float AS commander_rate,
                       COALESCE(col.quantity, 0) AS owned_quantity,
                       COALESCE(w.quantity, 0) AS wanted_quantity,
                       fr.printed_name AS name_fr
                FROM candidate
                JOIN cards_cheapest c ON c.oracle_id = candidate.oracle_id
                LEFT JOIN own_rates ON own_rates.oracle_id = c.oracle_id
                LEFT JOIN meta_rates ON meta_rates.oracle_id = c.oracle_id
                LEFT JOIN edhrec ON edhrec.oracle_id = c.oracle_id
                LEFT JOIN collection col ON col.oracle_id = c.oracle_id
                LEFT JOIN wishlist w ON w.oracle_id = c.oracle_id
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                WHERE c.legal_duel
                  AND c.color_identity <@ %(identity)s::text[]
                  AND c.oracle_id <> %(commander)s::uuid
                  AND c.type_line NOT LIKE 'Basic Land%%'
                """,
                {"commander": commander_oracle_id, "identity": sorted(identity),
                 "min_eligible": MIN_ELIGIBLE_DECKS},
            )
            return cur.fetchall()


def theme_coverage(commander_oracle_id: str, identity: list[str]) -> dict[str, dict]:
    """
    Par thème de duel : combien de cartes mesurées, et combien possédées —
    le même chiffre que `themes_db.theme_coverage` pour les thèmes EDHREC.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH {_OWN_RATES}
                SELECT slug, count(*) AS cards, count(col.oracle_id) AS owned
                FROM (SELECT %(own_slug)s AS slug, oracle_id FROM own_rates
                      UNION ALL
                      SELECT %(meta_slug)s, oracle_id FROM meta_rates) t
                JOIN cards_cheapest c ON c.oracle_id = t.oracle_id
                LEFT JOIN collection col ON col.oracle_id = t.oracle_id
                WHERE c.legal_duel
                  AND c.color_identity <@ %(identity)s::text[]
                  AND c.oracle_id <> %(commander)s::uuid
                  AND c.type_line NOT LIKE 'Basic Land%%'
                GROUP BY slug
                """,
                {"commander": commander_oracle_id, "identity": sorted(identity),
                 "min_eligible": MIN_ELIGIBLE_DECKS,
                 "own_slug": COMMANDER_SLUG, "meta_slug": META_SLUG},
            )
            return {row["slug"]: dict(row) for row in cur.fetchall()}


def theme_scores() -> list[dict]:
    """
    Les thèmes de duel des commandants possédés, sous la forme de
    `themes_db.theme_scores` : la somme des taux des 63 meilleures cartes
    possédées (`reachable`), rapportée à celle des 63 meilleures tout court.

    Le méta ne dépend que de l'**identité**, pas du commandant : il est donc
    calculé une fois par identité (trente-deux au plus) puis distribué, plutôt
    qu'une fois par commandant — cent trente commandants croisés avec six mille
    cartes feraient trier près d'un million de lignes à chaque affichage.
    """
    if not available():
        return []

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH cmd AS (
                    SELECT DISTINCT c.oracle_id, c.color_identity
                    FROM collection col
                    JOIN cards_cheapest c ON c.oracle_id = col.oracle_id
                    WHERE c.legal_duel AND NOT c.banned_as_commander_duel
                      AND {_IS_COMMANDER_TYPE}
                ),
                identities AS (SELECT DISTINCT color_identity FROM cmd),
                meta AS (
                    SELECT s.oracle_id, s.rate, c.color_identity,
                           col.oracle_id IS NOT NULL AS owned
                    FROM duel_card_stats s
                    JOIN cards_cheapest c ON c.oracle_id = s.oracle_id
                    LEFT JOIN collection col ON col.oracle_id = s.oracle_id
                    WHERE c.legal_duel AND c.type_line NOT LIKE 'Basic Land%%'
                      AND s.eligible_decks >= %(min_eligible)s
                ),
                meta_ranked AS (
                    SELECT i.color_identity, m.rate, m.owned,
                           row_number() OVER (PARTITION BY i.color_identity
                                              ORDER BY m.rate DESC) AS rang,
                           row_number() OVER (PARTITION BY i.color_identity, m.owned
                                              ORDER BY m.rate DESC) AS rang_owned
                    FROM identities i
                    JOIN meta m ON m.color_identity <@ i.color_identity
                ),
                meta_scores AS (
                    SELECT color_identity,
                           sum(rate) FILTER (WHERE rang <= %(slots)s) AS ideal,
                           sum(rate) FILTER (WHERE owned AND rang_owned <= %(slots)s) AS reachable,
                           count(*) FILTER (WHERE owned AND rang_owned <= %(slots)s) AS owned_cards
                    FROM meta_ranked GROUP BY color_identity
                ),
                cmd_decks AS (
                    SELECT cmd.oracle_id AS commander, cmd.color_identity, d.deck_id
                    FROM cmd JOIN duel_decks d ON d.commander_oracle_ids @> ARRAY[cmd.oracle_id]
                ),
                cmd_counts AS (
                    SELECT commander, count(*) AS n FROM cmd_decks
                    GROUP BY commander HAVING count(*) >= %(min_decks)s
                ),
                own AS (
                    SELECT cd.commander, dc.oracle_id,
                           count(*)::float / max(n.n) AS rate,
                           bool_or(col.oracle_id IS NOT NULL) AS owned
                    FROM cmd_decks cd
                    JOIN cmd_counts n ON n.commander = cd.commander
                    JOIN duel_deck_cards dc ON dc.deck_id = cd.deck_id
                    JOIN cards_cheapest c ON c.oracle_id = dc.oracle_id
                    LEFT JOIN collection col ON col.oracle_id = dc.oracle_id
                    WHERE c.legal_duel AND c.color_identity <@ cd.color_identity
                    GROUP BY cd.commander, dc.oracle_id
                ),
                own_ranked AS (
                    SELECT commander, rate, owned,
                           row_number() OVER (PARTITION BY commander ORDER BY rate DESC) AS rang,
                           row_number() OVER (PARTITION BY commander, owned
                                              ORDER BY rate DESC) AS rang_owned
                    FROM own
                ),
                own_scores AS (
                    SELECT commander,
                           sum(rate) FILTER (WHERE rang <= %(slots)s) AS ideal,
                           sum(rate) FILTER (WHERE owned AND rang_owned <= %(slots)s) AS reachable,
                           count(*) FILTER (WHERE owned AND rang_owned <= %(slots)s) AS owned_cards
                    FROM own_ranked GROUP BY commander
                )
                SELECT cmd.oracle_id AS commander_oracle_id, %(meta_slug)s AS theme_slug,
                       %(meta_label)s AS label,
                       (SELECT count(*) FROM duel_decks) AS deck_count,
                       COALESCE(ms.owned_cards, 0) AS owned_cards,
                       COALESCE(ms.reachable, 0) / NULLIF(ms.ideal, 0) AS score,
                       COALESCE(ms.reachable, 0) AS reachable
                FROM cmd JOIN meta_scores ms ON ms.color_identity = cmd.color_identity
              UNION ALL
                SELECT os.commander, %(own_slug)s, %(own_label)s, n.n,
                       COALESCE(os.owned_cards, 0),
                       COALESCE(os.reachable, 0) / NULLIF(os.ideal, 0),
                       COALESCE(os.reachable, 0)
                FROM own_scores os JOIN cmd_counts n ON n.commander = os.commander
                """,
                {"min_eligible": MIN_ELIGIBLE_DECKS, "min_decks": MIN_COMMANDER_DECKS,
                 "slots": NONLAND_SLOTS, "meta_slug": META_SLUG, "meta_label": META_LABEL,
                 "own_slug": COMMANDER_SLUG, "own_label": COMMANDER_LABEL},
            )
            return [{**row, "source": SOURCE} for row in cur.fetchall()]


def top_cards(type_match: str, limit: int, max_price: float | None) -> tuple[list[dict], int]:
    """
    Les cartes les plus jouées en tops de duel pour un type, et combien du
    classement sans plafond ont été écartées pour leur prix.

    Classées par **part de tous les decks** (`share`), pas par taux rapporté à
    l'identité : une liste de cartes à avoir se lit toutes couleurs
    confondues, et le taux par identité y ferait monter une carte cinq
    couleurs jouée par les deux seuls decks qui le pouvaient.
    """
    condition = "" if max_price is None else """
      AND (col.quantity > 0 OR (c.price_eur IS NOT NULL AND c.price_eur <= %(max_price)s))"""
    params = {"match": f"%{type_match}%", "top": limit,
              "max_price": max_price if max_price is not None else 0}
    base = """
        FROM duel_card_stats s
        JOIN cards_cheapest c ON c.oracle_id = s.oracle_id
        LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
        LEFT JOIN collection col ON col.oracle_id = c.oracle_id
        LEFT JOIN wishlist w ON w.oracle_id = c.oracle_id
        WHERE c.legal_duel
          AND c.type_line ILIKE %(match)s
          AND c.type_line NOT ILIKE 'Basic Land%%'
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.oracle_id, c.scryfall_id, c.name, fr.printed_name AS name_fr,
                       c.type_line, c.mana_cost, c.cmc, c.price_eur, c.edhrec_rank,
                       c.image_uri, c.image_downloaded, c.color_identity,
                       COALESCE(col.quantity, 0) AS owned,
                       COALESCE(w.quantity, 0) AS wanted,
                       s.share AS duel_share, s.decks AS duel_decks
                """ + base + condition + """
                ORDER BY s.share DESC, c.edhrec_rank NULLS LAST
                LIMIT %(top)s
                """,
                params,
            )
            cards = cur.fetchall()
            if max_price is None:
                return cards, 0
            cur.execute(
                """
                SELECT count(*) AS n FROM (
                    SELECT COALESCE(col.quantity, 0) AS owned, c.price_eur
                """ + base + """
                    ORDER BY s.share DESC, c.edhrec_rank NULLS LAST
                    LIMIT %(top)s
                ) t
                WHERE t.owned = 0 AND (t.price_eur IS NULL OR t.price_eur > %(max_price)s)
                """,
                params,
            )
            return cards, cur.fetchone()["n"]
