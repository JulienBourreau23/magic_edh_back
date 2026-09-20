"""db/cards.py — lecture de la table `cards` / vue matérialisée `cards_cheapest`."""
from db.core import get_conn

# Le nom de colonne est interpolé dans le SQL : il doit venir de cette table de
# correspondance, jamais d'une valeur reçue du client.
LEGALITY_COLUMNS = {"commander": "legal_commander", "duel": "legal_duel"}

# Plancher de qualité pour les cartes conseillées : au-delà de ce rang EDHREC,
# une carte n'est quasiment jouée par personne. Il sert de filtre AVANT le tri
# par prix, sans quoi « le moins cher » ferait remonter des cartes à 5 centimes
# que personne ne joue.
MAX_EDHREC_RANK = 2000


def resolve_names(names: list[str]) -> dict[str, dict]:
    """
    Résout une liste de noms en allers-retours SQL successifs, du plus strict
    au plus tolérant : noms anglais exacts, puis noms français exacts, puis les
    deux en comparaison **insensible aux accents et aux ligatures**, enfin la
    **face avant** d'une carte à deux noms dans les deux langues. Renvoie
    {nom de la requête en minuscules: carte}. Les noms non trouvés sont
    simplement absents — à l'appelant de tenter le flou.

    Chaque passage ne travaille que sur le reliquat du précédent : l'ordre est
    donc une priorité, pas une simple suite. C'est ce qui rend le passage par
    face avant sans danger (voir son commentaire).

    L'anglais est prioritaire : c'est le nom canonique, et un nom français peut
    théoriquement coïncider avec le nom anglais d'une autre carte.

    Le passage normalisé existe parce que les noms français de Scryfall ne sont
    pas homogènes : « Ile » sans accent pour l'île de base, « Nécropède » avec,
    « Nuée de fÆries » avec ligature quand « Annonciatrice faerie » n'en a pas.
    Sans lui, l'orthographe qui marche change d'une carte à l'autre. Il ne
    tourne que sur le reliquat des deux premiers passages — en général quelques
    lignes — donc son balayage de `cards_cheapest` se paie une fois par import,
    pas une fois par carte.
    """
    if not names:
        return {}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (lower(c.name)) lower(c.name) AS match_key, c.*
                FROM unnest(%s::text[]) AS q(name)
                JOIN cards_cheapest c ON lower(c.name) = lower(q.name)
                """,
                (names,),
            )
            resolved = {row["match_key"]: row for row in cur.fetchall()}

            remaining = [name for name in names if name.lower() not in resolved]
            if not remaining:
                return resolved

            cur.execute(
                """
                SELECT DISTINCT ON (lower(fr.printed_name)) lower(fr.printed_name) AS match_key, c.*
                FROM unnest(%s::text[]) AS q(name)
                JOIN card_names_fr fr ON lower(fr.printed_name) = lower(q.name)
                JOIN cards_cheapest c ON c.oracle_id = fr.oracle_id
                """,
                (remaining,),
            )
            for row in cur.fetchall():
                resolved.setdefault(row["match_key"], row)

            remaining = [name for name in names if name.lower() not in resolved]
            if not remaining:
                return resolved

            # Troisième passage : accents et ligatures neutralisés des deux
            # côtés. La clé renvoyée est le nom **demandé**, pas celui trouvé :
            # c'est par lui que l'appelant retrouve sa ligne de decklist.
            # `ORDER BY` pour que deux cartes qui ne diffèrent que par un accent
            # — cas théorique — donnent toujours la même réponse.
            cur.execute(
                """
                SELECT DISTINCT ON (lower(q.name)) lower(q.name) AS match_key, c.*
                FROM unnest(%s::text[]) AS q(name)
                JOIN cards_cheapest c
                  ON normalize_card_name(c.name) = normalize_card_name(q.name)
                ORDER BY lower(q.name), c.name
                """,
                (remaining,),
            )
            for row in cur.fetchall():
                resolved.setdefault(row["match_key"], row)

            remaining = [name for name in names if name.lower() not in resolved]
            if not remaining:
                return resolved

            cur.execute(
                """
                SELECT DISTINCT ON (lower(q.name)) lower(q.name) AS match_key, c.*
                FROM unnest(%s::text[]) AS q(name)
                JOIN card_names_fr fr
                  ON normalize_card_name(fr.printed_name) = normalize_card_name(q.name)
                JOIN cards_cheapest c ON c.oracle_id = fr.oracle_id
                ORDER BY lower(q.name), c.name
                """,
                (remaining,),
            )
            for row in cur.fetchall():
                resolved.setdefault(row["match_key"], row)

            remaining = [name for name in names if name.lower() not in resolved]
            if not remaining:
                return resolved

            # Dernier passage : la **face avant** d'une carte à deux noms, dans
            # les deux langues. Une decklist écrit « Bloodline Keeper », pas
            # « Bloodline Keeper // Lord of Lineage », et magic-ville n'imprime
            # que le recto sur la vignette.
            #
            # Deux garde-fous :
            #   - il vient en **dernier**, donc un nom qui désigne une vraie
            #     carte gagne toujours. C'est ce qui sauve Smelt, Armed et Bind,
            #     qui existent à la fois seuls et en face avant d'une partagée ;
            #   - il ne regarde **que** la face avant. La face arrière (« Lord of
            #     Lineage ») et la moitié aventure ne sont pas des cartes : les
            #     résoudre ferait passer une planche de proxys magic-ville à 101
            #     cartes en silence, alors qu'aujourd'hui elles sont signalées.
            cur.execute(
                """
                SELECT DISTINCT ON (lower(q.name)) lower(q.name) AS match_key, c.*
                FROM unnest(%s::text[]) AS q(name)
                JOIN cards_cheapest c
                  ON c.name LIKE '%% // %%'
                 AND normalize_card_name(split_part(c.name, ' // ', 1))
                     = normalize_card_name(q.name)
                ORDER BY lower(q.name), c.name
                """,
                (remaining,),
            )
            for row in cur.fetchall():
                resolved.setdefault(row["match_key"], row)

            remaining = [name for name in names if name.lower() not in resolved]
            if not remaining:
                return resolved

            cur.execute(
                """
                SELECT DISTINCT ON (lower(q.name)) lower(q.name) AS match_key, c.*
                FROM unnest(%s::text[]) AS q(name)
                JOIN card_names_fr fr
                  ON fr.printed_name LIKE '%% // %%'
                 AND normalize_card_name(split_part(fr.printed_name, ' // ', 1))
                     = normalize_card_name(q.name)
                JOIN cards_cheapest c ON c.oracle_id = fr.oracle_id
                ORDER BY lower(q.name), c.name
                """,
                (remaining,),
            )
            for row in cur.fetchall():
                resolved.setdefault(row["match_key"], row)

    return resolved


def basic_land_printings(basics: dict[str, int]) -> list[dict]:
    """
    Les impressions des terrains de base d'un conseil de manabase.

    Les basiques ne sont pas dans la collection — quantité supposée illimitée —
    donc les calculs ne les rendent que par leur **nom** et leur compte. Or un
    nom ne se pose pas dans un brouillon et ne s'évalue pas : l'atelier comme
    l'export de fiche ont besoin d'une impression pour relire la carte dans le
    catalogue.

    Un nom non résolu est simplement absent, comme partout avec
    `resolve_names` : une manabase amputée se voit au compte de terrains, alors
    qu'une ligne inventée passerait inaperçue.

    `name_fr` est réaffirmé depuis la clé parce que c'est par lui que le
    conseil nomme le terrain ; la résolution, elle, ne rend que les colonnes de
    `cards_cheapest`, donc l'anglais.
    """
    resolved = resolve_names(list(basics))
    return [{**resolved[name.lower()], "name_fr": name, "quantity": quantity}
            for name, quantity in basics.items() if name.lower() in resolved]


def get_cheapest_by_oracle_id(oracle_id: str) -> dict | None:
    """L'impression la moins chère d'une carte, nom français compris. Sert aux
    écrans qui raisonnent par carte et non par impression (commandant choisi,
    construction compétitive)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.*, fr.printed_name AS name_fr
                FROM cards_cheapest c
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                WHERE c.oracle_id = %s
                """,
                (oracle_id,),
            )
            return cur.fetchone()


def get_by_scryfall_id(scryfall_id: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM cards WHERE scryfall_id = %s", (scryfall_id,))
            return cur.fetchone()


# Recherche floue sur les deux langues : la carte est la même, seul le nom
# diffère, donc on prend le meilleur score des deux et on dédoublonne par carte.
# `matched_fr` dit au client quel nom français a déclenché la correspondance,
# pour qu'il puisse l'afficher en repère.
_FUZZY_SQL = """
WITH matches AS (
    SELECT c.*, similarity(c.name, %(q)s) AS score, NULL::text AS matched_fr
    FROM cards_cheapest c
    WHERE c.name %% %(q)s {english_extra}
    UNION ALL
    SELECT c.*, similarity(fr.printed_name, %(q)s) AS score, fr.printed_name AS matched_fr
    FROM card_names_fr fr
    JOIN cards_cheapest c ON c.oracle_id = fr.oracle_id
    WHERE fr.printed_name %% %(q)s {french_extra}
),
best AS (
    SELECT DISTINCT ON (oracle_id) * FROM matches ORDER BY oracle_id, score DESC
)
SELECT * FROM best ORDER BY score DESC LIMIT %(limit)s
"""


def find_by_similar_name(name: str, limit: int = 5) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                _FUZZY_SQL.format(english_extra="", french_extra=""),
                {"q": name, "limit": limit},
            )
            return cur.fetchall()


def search(query: str, limit: int = 20) -> list[dict]:
    """Recherche interactive : on accepte aussi la sous-chaîne, dans les deux langues."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                _FUZZY_SQL.format(
                    english_extra="OR c.name ILIKE %(pattern)s",
                    french_extra="OR fr.printed_name ILIKE %(pattern)s",
                ),
                {"q": query, "pattern": f"%{query}%", "limit": limit},
            )
            return cur.fetchall()


def buildable_pool(identity: list[str], format: str, commander_oracle_id: str) -> list[dict]:
    """
    Tout ce que la collection permet de mettre dans ce deck : cartes possédées,
    légales dans le format, dont l'identité de couleur tient dans celle du
    commandant. **Terrains compris** — on construit aussi la manabase ici.

    Les artefacts et cartes incolores passent sans clause particulière : leur
    identité est vide, donc incluse dans n'importe laquelle.

    `inclusion_rate` dit ce qu'EDHREC voit joué derrière ce commandant. Il sert
    à classer le vivier par pertinence plutôt que par ordre alphabétique ; il
    est nul pour les cartes qu'EDHREC ne connaît pas avec lui, ce qui n'est pas
    un défaut : c'est la moitié d'une collection.

    Le vivier part **entier** au navigateur : quelques centaines de lignes
    tiennent dans une réponse, et un aller-retour par filtre rendrait la
    construction poussive.
    """
    legality_column = LEGALITY_COLUMNS[format]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT c.scryfall_id, c.oracle_id, c.name, fr.printed_name AS name_fr,
                       c.mana_cost, c.cmc, c.type_line, c.color_identity, c.price_eur,
                       c.image_uri, c.image_downloaded, c.categories, c.game_changer,
                       c.edhrec_rank, c.keywords, col.quantity AS owned_quantity,
                       COALESCE(w.quantity, 0) AS wanted_quantity,
                       r.inclusion_rate
                FROM collection col
                JOIN cards_cheapest c ON c.oracle_id = col.oracle_id
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                LEFT JOIN wishlist w ON w.oracle_id = c.oracle_id
                LEFT JOIN (
                    SELECT card_oracle_id, max(inclusion_rate) AS inclusion_rate
                    FROM commander_recommendations
                    WHERE commander_oracle_id = %(commander)s::uuid
                    GROUP BY card_oracle_id
                ) r ON r.card_oracle_id = c.oracle_id
                WHERE c.{legality_column}
                  AND c.color_identity <@ %(identity)s::text[]
                  AND c.oracle_id <> %(commander)s::uuid
                ORDER BY r.inclusion_rate DESC NULLS LAST, c.edhrec_rank NULLS LAST, c.name
                """,
                {"identity": sorted(identity), "commander": commander_oracle_id},
            )
            return cur.fetchall()


def find_candidates(color_identity: set[str], category: str, exclude_oracle_ids: list[str],
                    max_price: float, format: str = "commander", limit: int = 8,
                    exclude_game_changers: bool = False,
                    exhausted_oracle_ids: list[str] | None = None) -> list[dict]:
    """
    Cartes candidates pour combler un manque : dans l'identité de couleur,
    légales dans le format, absentes du deck.

    Deux règles de coût, dans cet ordre :
      - une carte déjà en collection dont il reste au moins un exemplaire libre
        est gratuite : elle passe devant, et le plafond de prix ne s'y applique
        pas (posséder une carte à 200 € ne coûte rien de plus). C'est
        `exhausted_oracle_ids` qui dit lesquelles n'ont plus d'exemplaire
        disponible — un ensemble de « déjà réservé » ne suffirait pas, il
        déclarerait payante une carte possédée en double dont un seul
        exemplaire est pris ;
      - sinon c'est un achat : plafond de prix appliqué, et prix connu exigé
        puisqu'on ne peut pas garantir le plafond sans prix.

    Le classement suit la consigne « le moins d'achat possible » : gratuit
    d'abord, puis le moins cher. Le rang EDHREC ne sert pas de tri principal
    mais de filtre de qualité en amont (`MAX_EDHREC_RANK`), pour que « le moins
    cher » reste « le moins cher parmi les cartes réellement jouées ».
    """
    legality_column = LEGALITY_COLUMNS[format]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT c.scryfall_id, c.oracle_id, c.name, c.mana_cost, c.cmc, c.type_line,
                       c.color_identity, c.price_eur, c.image_uri, c.image_downloaded,
                       c.edhrec_rank, c.categories, c.game_changer,
                       fr.printed_name AS name_fr,
                       COALESCE(col.quantity, 0) AS owned_quantity,
                       -- Déjà dans la liste de recherche : le bouton doit le
                       -- dire au lieu d'en demander un second exemplaire, les
                       -- quantités s'y additionnant.
                       COALESCE(w.quantity, 0) AS wanted_quantity,
                       (col.quantity IS NOT NULL
                        AND NOT (c.oracle_id = ANY(%(exhausted)s::uuid[]))) AS free_to_use
                FROM cards_cheapest c
                LEFT JOIN collection col ON col.oracle_id = c.oracle_id
                LEFT JOIN wishlist w ON w.oracle_id = c.oracle_id
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                WHERE c.{legality_column}
                  AND c.color_identity <@ %(identity)s::text[]
                  AND c.categories @> ARRAY[%(category)s]
                  AND NOT (c.oracle_id = ANY(%(exclude)s::uuid[]))
                  AND c.edhrec_rank IS NOT NULL AND c.edhrec_rank <= %(max_rank)s
                  AND (NOT %(exclude_gc)s OR NOT c.game_changer)
                  AND (col.quantity IS NOT NULL
                       OR (c.price_eur IS NOT NULL AND c.price_eur <= %(max_price)s))
                ORDER BY free_to_use DESC,
                         CASE WHEN col.quantity IS NOT NULL THEN 0 ELSE c.price_eur END ASC,
                         c.edhrec_rank
                LIMIT %(limit)s
                """,
                {
                    "identity": sorted(color_identity),
                    "category": category,
                    "max_price": max_price,
                    "exclude": exclude_oracle_ids,
                    "exhausted": exhausted_oracle_ids or [],
                    "exclude_gc": exclude_game_changers,
                    "max_rank": MAX_EDHREC_RANK,
                    "limit": limit,
                },
            )
            return cur.fetchall()


def _set_image_flag(scryfall_ids: list[str], downloaded: bool) -> None:
    if not scryfall_ids:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE cards SET image_downloaded = %s WHERE scryfall_id = ANY(%s::uuid[])",
                (downloaded, scryfall_ids),
            )


def mark_images_downloaded(scryfall_ids: list[str]) -> None:
    _set_image_flag(scryfall_ids, True)


def mark_images_missing(scryfall_ids: list[str]) -> None:
    """Image absente du disque : le front doit retomber sur l'URL Scryfall."""
    _set_image_flag(scryfall_ids, False)
