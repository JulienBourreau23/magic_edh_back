"""
db/ignored.py — les cartes refusées pour un deck.

Le refus porte sur une **modification de deck** : « ne me propose plus cette
carte pour celui-ci ». Il est donc rattaché au deck et non global — refuser
Rhystic Study pour l'Atraxa ne dit rien du Kykar, et une ignorance globale
masquerait aussi des cartes sur les écrans qui construisent un deck de zéro,
lesquels ne sont pas concernés.

Une carte refusée n'est jamais retirée du deck : le refus ne parle que du
conseil.
"""
from psycopg2.extras import execute_values

from db.collection import COLLECTION_COLUMNS
from db.core import get_conn


def add(deck_id: int, oracle_id: str, reason: str | None = None) -> None:
    """
    Idempotent : refuser deux fois la même carte n'est pas une erreur, et ne
    doit surtout pas doubler quoi que ce soit — contrairement à la collection
    et à la liste de recherche, où les quantités s'additionnent.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO deck_ignored_cards (deck_id, oracle_id, reason)
                VALUES (%s, %s, %s)
                ON CONFLICT (deck_id, oracle_id) DO UPDATE
                SET reason = COALESCE(EXCLUDED.reason, deck_ignored_cards.reason)
                """,
                (deck_id, oracle_id, reason),
            )


def remove(deck_id: int, oracle_id: str) -> bool:
    """False si la carte n'était pas refusée — l'appelant en fait un 404."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM deck_ignored_cards WHERE deck_id = %s AND oracle_id = %s",
                (deck_id, oracle_id),
            )
            return cur.rowcount > 0


def oracle_ids(deck_id: int) -> list[str]:
    """Les identifiants seuls : c'est ce que consomment les filtres SQL."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT oracle_id FROM deck_ignored_cards WHERE deck_id = %s",
                (deck_id,),
            )
            return [str(row["oracle_id"]) for row in cur.fetchall()]


def by_deck(deck_ids: list[int]) -> dict[int, list[str]]:
    """
    Les refus de plusieurs decks en une requête. L'équilibrage traite jusqu'à
    quatre decks : les interroger un par un ferait quatre allers-retours pour
    rien.
    """
    if not deck_ids:
        return {}
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT deck_id, oracle_id FROM deck_ignored_cards "
                "WHERE deck_id = ANY(%s)",
                (deck_ids,),
            )
            result: dict[int, list[str]] = {deck_id: [] for deck_id in deck_ids}
            for row in cur.fetchall():
                result[row["deck_id"]].append(str(row["oracle_id"]))
            return result


def list_for_deck(deck_id: int) -> list[dict]:
    """
    Les cartes refusées, affichables : la liste doit être **consultable et
    réversible**, sinon on ne saurait plus dans six mois pourquoi une carte ne
    remonte jamais dans les conseils.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT i.reason, i.created_at, {COLLECTION_COLUMNS}
                FROM deck_ignored_cards i
                JOIN cards_cheapest c ON c.oracle_id = i.oracle_id
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                WHERE i.deck_id = %s
                ORDER BY i.created_at DESC
                """,
                (deck_id,),
            )
            return cur.fetchall()
