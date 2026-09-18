"""
scripts/sync_french_names.py — alimente `card_names_fr` depuis le bulk data
`all_cards` de Scryfall (le seul qui contienne les autres langues).

On ne garde que deux colonnes par carte : l'oracle_id et le nom imprimé en
français. Le fichier fait ~400 Mo compressés, mais il est lu en streaming et
99 % des lignes sont jetées à la volée, donc l'empreinte mémoire reste faible.

Exécution : `python scripts/sync_french_names.py`
À relancer après un nouveau set, comme `sync_scryfall.py`.
"""
import gzip
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from psycopg2.extras import execute_values

from config import SCRYFALL_API_BASE, SCRYFALL_HEADERS
from db.core import get_conn

BATCH_SIZE = 2000

UPSERT_SQL = """
INSERT INTO card_names_fr (oracle_id, printed_name) VALUES %s
ON CONFLICT (oracle_id) DO UPDATE SET printed_name = EXCLUDED.printed_name
"""


def printed_name_for(card: dict) -> str | None:
    """
    Le nom français d'une carte, **faces comprises**.

    Une carte à deux faces (recto-verso, partagée, aventure, flip) n'a pas de
    `printed_name` au premier niveau : Scryfall le range dans chaque face. À ne
    lire que le premier niveau, ces cartes n'avaient jamais de nom français —
    mesuré : 1 carte sur 878, contre 90 % pour les cartes simples. Elles
    s'affichaient donc en anglais partout, et une decklist française les
    laissait non résolues.

    Les faces sont recollées avec ` // `, **exactement la convention du champ
    `name` anglais de Scryfall** : c'est ce qui permet aux deux langues d'être
    comparées de la même façon, alias contre nom.

    Une seule face traduite ne donne rien : un nom à moitié français ne
    correspondrait ni à ce qu'on voit sur la carte, ni à ce qu'un joueur écrit.
    """
    if card.get("printed_name"):
        return card["printed_name"]

    faces = card.get("card_faces") or []
    names = [face.get("printed_name") for face in faces]
    if len(names) >= 2 and all(names):
        return " // ".join(names)
    return None


def main() -> None:
    with httpx.Client(timeout=120, headers=SCRYFALL_HEADERS) as client:
        index = client.get(f"{SCRYFALL_API_BASE}/bulk-data").json()
        entry = next(d for d in index["data"] if d["type"] == "all_cards")
        print(f"Téléchargement de {entry['name']} ({entry['compressed_size'] / 1e6:.0f} Mo compressés)...")

        with tempfile.NamedTemporaryFile(suffix=".jsonl.gz") as tmp:
            with client.stream("GET", entry["jsonl_download_uri"]) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_bytes():
                    tmp.write(chunk)
            tmp.flush()

            print("Extraction des noms français...")
            seen: set[str] = set()
            batch: list[tuple[str, str]] = []
            total = 0

            with get_conn() as conn:
                with conn.cursor() as cur:
                    with gzip.open(tmp.name, "rt", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line or '"lang":"fr"' not in line:
                                continue  # filtre textuel : évite de parser 99 % des lignes

                            card = json.loads(line)
                            oracle_id = card.get("oracle_id")
                            printed = printed_name_for(card)
                            if not oracle_id or not printed or oracle_id in seen:
                                continue

                            seen.add(oracle_id)
                            batch.append((oracle_id, printed))
                            if len(batch) >= BATCH_SIZE:
                                execute_values(cur, UPSERT_SQL, batch, page_size=BATCH_SIZE)
                                total += len(batch)
                                print(f"  {total} noms français...")
                                batch.clear()

                    if batch:
                        execute_values(cur, UPSERT_SQL, batch, page_size=BATCH_SIZE)
                        total += len(batch)

    print(f"Sync terminée : {total} cartes avec un nom français.")


if __name__ == "__main__":
    main()
