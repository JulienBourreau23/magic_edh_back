"""db/combos.py — lecture du catalogue de combos (table `combos`)."""
from db.core import get_conn


def find_pairs(oracle_ids: list[str]) -> list[dict]:
    """
    Les combos dont les **deux** cartes figurent dans la liste fournie.

    La paire est stockée triée (`oracle_id_a < oracle_id_b`), donc un seul test
    par colonne suffit — pas besoin d'essayer les deux sens.
    """
    if len(oracle_ids) < 2:
        return []

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT variant_id, oracle_id_a, oracle_id_b, card_a, card_b, produces,
                       wins_outright, mana_needed, mana_value_needed, bracket_tag, popularity,
                       description, prerequisites
                FROM combos
                WHERE oracle_id_a = ANY(%(ids)s::uuid[])
                  AND oracle_id_b = ANY(%(ids)s::uuid[])
                ORDER BY wins_outright DESC, popularity DESC NULLS LAST
                """,
                {"ids": oracle_ids},
            )
            return cur.fetchall()
