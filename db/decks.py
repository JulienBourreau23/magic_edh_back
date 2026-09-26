"""db/decks.py — decks, deck_cards, deck_import_issues."""
from datetime import datetime, timezone

from psycopg2.extras import execute_values

from db.core import get_conn

# Colonnes renvoyées pour la fiche deck. On exclut volontairement `oracle_text`
# et `card_faces` : inutiles à l'affichage et ~2x le poids de la réponse. Le
# seul besoin métier tiré du texte (cartes autorisant les exemplaires
# multiples) est calculé côté SQL en booléen.
DECK_CARD_COLUMNS = """
    c.scryfall_id, c.oracle_id, c.name, c.mana_cost, c.cmc, c.type_line,
    c.color_identity, c.rarity, c.price_eur, c.image_uri, c.image_downloaded,
    c.legal_commander, c.legal_duel, c.game_changer, c.categories,
    c.produced_mana, c.edhrec_rank, fr.printed_name AS name_fr,
    c.set_code, c.banned_commander, c.banned_duel,
    (c.oracle_text ILIKE '%%deck can have any number of cards named%%') AS allows_multiple
"""

# Le nom français vient d'une table d'alias séparée (~88 % de couverture) :
# jointure externe, jamais interne, sinon les cartes jamais traduites
# disparaîtraient purement et simplement des fiches.
FRENCH_NAME_JOIN = "LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id"

# La simulation a besoin du texte oracle (quantité de mana produite par une
# source : "Add {C}{C}") et des corps de créature pour le combat. Ces colonnes
# ne sont jamais renvoyées au client.
SIMULATION_CARD_COLUMNS = (
    DECK_CARD_COLUMNS
    # `keywords` alimente le combat du duel simulé : vol, piétinement,
    # initiative, contact mortel... Sans cette colonne, le simulateur joue des
    # créatures nues et le travail sur les règles de combat ne sert à rien.
    + ", c.oracle_text, c.power, c.toughness, c.keywords"
)


def create_deck(name: str, format: str = "commander") -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO decks (name, format) VALUES (%s, %s) RETURNING id",
                (name, format),
            )
            return cur.fetchone()["id"]


def set_commanders(deck_id: int, scryfall_id: str, partner_scryfall_id: str | None = None) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE decks SET commander_scryfall_id = %s, partner_scryfall_id = %s WHERE id = %s",
                (scryfall_id, partner_scryfall_id, deck_id),
            )


def add_deck_cards(deck_id: int, rows: list[tuple[str, int, bool]]) -> None:
    """rows = [(scryfall_id, quantity, is_commander)], insérées en une requête."""
    if not rows:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO deck_cards (deck_id, scryfall_id, quantity, is_commander)
                VALUES %s
                ON CONFLICT (deck_id, scryfall_id)
                DO UPDATE SET quantity = deck_cards.quantity + EXCLUDED.quantity,
                              is_commander = deck_cards.is_commander OR EXCLUDED.is_commander
                """,
                [(deck_id, sid, qty, is_cmd) for sid, qty, is_cmd in rows],
            )


def add_import_issues(deck_id: int, issues: list[tuple[str, str]]) -> None:
    """issues = [(raw_line, reason)], insérées en une requête."""
    if not issues:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                "INSERT INTO deck_import_issues (deck_id, raw_line, reason) VALUES %s",
                [(deck_id, line, reason) for line, reason in issues],
            )


def list_decks(archived: bool = False) -> list[dict]:
    """
    Les decks actifs, ou les archivés.

    Un deck archivé n'est pas supprimé : il sort seulement des écrans qui
    parlent de ce qu'on joue. Il reste donc **hors** du panel de performance,
    de l'équilibrage et de la comparaison, sans quoi archiver ne changerait
    rien à ce que le site raconte.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT d.id, d.name, d.format, d.created_at, d.archived_at,
                       c.name AS commander_name, fr.printed_name AS commander_name_fr,
                       c.image_uri AS commander_image_uri,
                       (SELECT COALESCE(SUM(dc.quantity), 0) FROM deck_cards dc WHERE dc.deck_id = d.id) AS card_count
                FROM decks d
                LEFT JOIN cards c ON c.scryfall_id = d.commander_scryfall_id
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                WHERE d.archived_at IS {'NOT NULL' if archived else 'NULL'}
                ORDER BY {'d.archived_at DESC' if archived else 'd.created_at DESC'}
                """
            )
            return cur.fetchall()


def set_archived(deck_id: int, archived: bool) -> bool:
    """Range un deck, ou le remet en service. Aucune carte n'est touchée."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE decks SET archived_at = %s WHERE id = %s",
                (datetime.now(timezone.utc) if archived else None, deck_id),
            )
            return cur.rowcount > 0


def get_deck(deck_id: int) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM decks WHERE id = %s", (deck_id,))
            return cur.fetchone()


def committed_quantities(exclude_deck_ids: list[int] | None = None) -> dict[str, int]:
    """
    {oracle_id: exemplaires immobilisés dans les decks enregistrés}.

    Un exemplaire rangé dans un deck monté n'est pas disponible pour en monter
    un autre : c'est la même règle physique que celle appliquée *entre* les
    quatre decks d'un plan, mais elle s'arrêtait à la porte des decks existants.
    Le plan pouvait donc proposer un Sol Ring déjà dans une boîte.

    Les terrains de base sont exclus, comme partout : ils ne s'épuisent pas.

    **Limite assumée** : rien en base ne dit qu'un deck est *physiquement*
    monté. Un deck seulement envisagé immobilise donc ses cartes lui aussi —
    d'où l'interrupteur côté page, plutôt qu'une réservation imposée en
    silence.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.oracle_id, SUM(dc.quantity)::int AS quantity
                FROM deck_cards dc
                JOIN cards c ON c.scryfall_id = dc.scryfall_id
                WHERE c.type_line NOT LIKE 'Basic Land%%'
                  AND NOT (dc.deck_id = ANY(%(exclude)s::int[]))
                GROUP BY c.oracle_id
                """,
                {"exclude": exclude_deck_ids or []},
            )
            return {str(row["oracle_id"]): row["quantity"] for row in cur.fetchall()}


def get_deck_cards(deck_id: int) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT dc.quantity, dc.is_commander, {DECK_CARD_COLUMNS}
                FROM deck_cards dc
                JOIN cards c ON c.scryfall_id = dc.scryfall_id
                {FRENCH_NAME_JOIN}
                WHERE dc.deck_id = %s
                ORDER BY dc.is_commander DESC, c.cmc NULLS FIRST, c.name
                """,
                (deck_id,),
            )
            return cur.fetchall()


def get_deck_cards_for_simulation(deck_id: int) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT dc.quantity, dc.is_commander, {SIMULATION_CARD_COLUMNS}
                FROM deck_cards dc
                JOIN cards c ON c.scryfall_id = dc.scryfall_id
                {FRENCH_NAME_JOIN}
                WHERE dc.deck_id = %s
                """,
                (deck_id,),
            )
            return cur.fetchall()


def simulation_cards_by_id(scryfall_ids: list[str]) -> dict[str, dict]:
    """
    {scryfall_id: carte prête pour le duel simulé}, en une requête.

    Le duel a besoin du texte oracle, des corps de créature et des mots-clés —
    colonnes que les écrans de construction ne renvoient jamais. Un deck
    fabriqué ailleurs (plan, deck compétitif) arrive donc ici sous forme
    d'identifiants, et repart jouable.
    """
    if not scryfall_ids:
        return {}
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {SIMULATION_CARD_COLUMNS}
                FROM cards c
                {FRENCH_NAME_JOIN}
                WHERE c.scryfall_id = ANY(%s::uuid[])
                """,
                (list({str(value) for value in scryfall_ids}),),
            )
            return {str(row["scryfall_id"]): row for row in cur.fetchall()}


def update_deck(deck_id: int, name: str | None = None, format: str | None = None,
                commander_scryfall_id: str | None = None) -> bool:
    """Met à jour les champs fournis. Renvoie False si le deck n'existe pas."""
    updates = {"name": name, "format": format, "commander_scryfall_id": commander_scryfall_id}
    updates = {column: value for column, value in updates.items() if value is not None}
    if not updates:
        return get_deck(deck_id) is not None

    assignments = ", ".join(f"{column} = %({column})s" for column in updates)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE decks SET {assignments} WHERE id = %(deck_id)s",
                {**updates, "deck_id": deck_id},
            )
            if cur.rowcount == 0:
                return False

    # Le commandant fixé à la main doit aussi porter le drapeau côté cartes :
    # c'est lui qui pilote l'identité de couleur et le comptage Game Changers.
    # S'il ne fait pas encore partie du deck (commandant non détecté à
    # l'import), on l'y ajoute plutôt que de laisser un drapeau sans carte.
    if "commander_scryfall_id" in updates:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO deck_cards (deck_id, scryfall_id, quantity, is_commander)
                    VALUES (%(deck_id)s, %(commander)s, 1, true)
                    ON CONFLICT (deck_id, scryfall_id) DO NOTHING
                    """,
                    {"commander": commander_scryfall_id, "deck_id": deck_id},
                )
                cur.execute(
                    """
                    UPDATE deck_cards
                    SET is_commander = (scryfall_id = %(commander)s)
                    WHERE deck_id = %(deck_id)s
                    """,
                    {"commander": commander_scryfall_id, "deck_id": deck_id},
                )
    return True


def delete_deck(deck_id: int) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM decks WHERE id = %s", (deck_id,))
            return cur.rowcount > 0


def remove_deck_card(deck_id: int, scryfall_id: str) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM deck_cards WHERE deck_id = %s AND scryfall_id = %s",
                (deck_id, scryfall_id),
            )
            return cur.rowcount > 0


def resolve_import_issue(deck_id: int, raw_line: str) -> None:
    """Une ligne corrigée à la main n'a plus à être signalée."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM deck_import_issues WHERE deck_id = %s AND raw_line = %s",
                (deck_id, raw_line),
            )


def get_import_issues(deck_id: int) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT raw_line, reason FROM deck_import_issues WHERE deck_id = %s ORDER BY id",
                (deck_id,),
            )
            return cur.fetchall()
