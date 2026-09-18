"""
db/wishlist.py — les cartes qu'on envisage d'acheter.

Symétrique de `db/collection.py` : même clé (`oracle_id`), mêmes colonnes
d'affichage. C'est ce qui permet à l'achat de faire basculer une ligne d'une
table à l'autre sans rien convertir.
"""
from psycopg2.extras import execute_values

from db.collection import COLLECTION_COLUMNS
from db.core import get_conn


def add(entries: list[tuple[str, str, int, str | None]]) -> None:
    """
    entries = [(oracle_id, scryfall_id, quantity, note)].

    Les quantités s'additionnent, comme dans la collection : vouloir une carte
    pour deux decks différents, c'est en vouloir deux. La note du dernier ajout
    l'emporte — c'est la plus récente, donc celle qui explique pourquoi la
    carte est encore là.
    """
    if not entries:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO wishlist (oracle_id, scryfall_id, quantity, note) VALUES %s
                ON CONFLICT (oracle_id) DO UPDATE
                SET quantity = wishlist.quantity + EXCLUDED.quantity,
                    note = COALESCE(EXCLUDED.note, wishlist.note),
                    updated_at = now()
                """,
                entries,
            )


def set_quantity(oracle_id: str, quantity: int) -> bool:
    """Quantité absolue ; 0 ou moins retire la carte. False si elle n'y était pas."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            if quantity <= 0:
                cur.execute("DELETE FROM wishlist WHERE oracle_id = %s", (oracle_id,))
            else:
                cur.execute(
                    "UPDATE wishlist SET quantity = %s, updated_at = now() WHERE oracle_id = %s",
                    (quantity, oracle_id),
                )
            return cur.rowcount > 0


def list_all() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT w.quantity, w.note, w.added_at, {COLLECTION_COLUMNS},
                       COALESCE(col.quantity, 0) AS owned_quantity
                FROM wishlist w
                JOIN cards c ON c.scryfall_id = w.scryfall_id
                LEFT JOIN card_names_fr fr ON fr.oracle_id = c.oracle_id
                LEFT JOIN collection col ON col.oracle_id = w.oracle_id
                ORDER BY c.price_eur DESC NULLS LAST, c.name
                """
            )
            return cur.fetchall()


def wanted_by_oracle_id(oracle_ids: list[str]) -> dict[str, int]:
    """
    {oracle_id: exemplaires déjà cherchés}, pour les seuls identifiants demandés.

    Sert aux listes d'achats, qui sont assemblées en Python à partir de
    plusieurs sources : elles n'ont pas de requête unique où accrocher une
    jointure, et les quantités de la liste de recherche **s'additionnent** — un
    second clic demanderait un second exemplaire sans rien dire.
    """
    if not oracle_ids:
        return {}
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT oracle_id, quantity FROM wishlist WHERE oracle_id = ANY(%s::uuid[])",
                (list({str(oracle_id) for oracle_id in oracle_ids}),),
            )
            return {str(row["oracle_id"]): row["quantity"] for row in cur.fetchall()}


def annotate_wanted(items: list[dict]) -> list[dict]:
    """
    Marque des lignes d'achat (`ShoppingItem`) des exemplaires **déjà** dans la
    liste de recherche, en une seule requête.

    Appelé par les routers et non par les services qui calculent ces listes :
    ces calculs sont testés sans base, et `/deck-plans` évalue des dizaines de
    groupes dont un seul est retenu — une requête par groupe serait payée pour
    rien.
    """
    wanted = wanted_by_oracle_id([item["oracle_id"] for item in items])
    for item in items:
        item["wanted_quantity"] = wanted.get(str(item["oracle_id"]), 0)
    return items


def acquire(oracle_id: str, quantity: int | None = None) -> dict | None:
    """
    L'achat est fait : la carte passe de la liste de recherche à la collection.

    Les deux écritures sont dans **la même transaction**. Sans ça, une coupure
    entre les deux perdrait la carte des deux côtés, ou la laisserait dans les
    deux — et la collection pilote les listes d'achats, donc l'erreur se
    paierait en argent.

    `quantity` permet d'acquérir une partie seulement (deux exemplaires
    cherchés, un seul trouvé en boutique) : le reste attend.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT oracle_id, scryfall_id, quantity FROM wishlist "
                "WHERE oracle_id = %s FOR UPDATE",
                (oracle_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            moved = row["quantity"] if quantity is None else min(quantity, row["quantity"])
            if moved <= 0:
                return None

            cur.execute(
                """
                INSERT INTO collection (oracle_id, scryfall_id, quantity) VALUES (%s, %s, %s)
                ON CONFLICT (oracle_id) DO UPDATE
                SET quantity = collection.quantity + EXCLUDED.quantity, updated_at = now()
                """,
                (str(row["oracle_id"]), row["scryfall_id"], moved),
            )

            remaining = row["quantity"] - moved
            if remaining > 0:
                cur.execute(
                    "UPDATE wishlist SET quantity = %s, updated_at = now() WHERE oracle_id = %s",
                    (remaining, oracle_id),
                )
            else:
                cur.execute("DELETE FROM wishlist WHERE oracle_id = %s", (oracle_id,))

            return {"moved": moved, "remaining": remaining}


def stats() -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS distinct_cards,
                       COALESCE(SUM(w.quantity), 0) AS total_cards,
                       COALESCE(SUM(w.quantity * c.price_eur), 0) AS total_price_eur,
                       COUNT(*) FILTER (WHERE c.price_eur IS NULL) AS unknown_price
                FROM wishlist w
                JOIN cards c ON c.scryfall_id = w.scryfall_id
                """
            )
            row = cur.fetchone()
            return {
                "distinct_cards": row["distinct_cards"],
                "total_cards": row["total_cards"],
                "total_price_eur": float(row["total_price_eur"]),
                # Une carte sans prix non-foil connu n'est pas comptée dans le
                # total : le dire évite de lire un budget comme complet.
                "unknown_price": row["unknown_price"],
            }
