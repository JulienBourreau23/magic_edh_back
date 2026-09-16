"""
scripts/decklist_from_pdf.py — transforme une planche de proxys magic-ville en
decklist collable dans l'application.

    python scripts/decklist_from_pdf.py deck.pdf --commander "Lathril, lame des elfes"

Le découpage de la planche vit dans `services/magic_ville_pdf.py` (testé sans
PDF) ; ce script n'y ajoute que l'appel à `pdftotext`, la résolution contre la
base et le rapport.

**Lire le rapport avant de coller la liste.** Le module sait écarter les noms
d'aventures, les lignes de type et les titres sur trois lignes, mais pas les
faces arrière des cartes recto-verso : magic-ville les imprime comme des proxys
à part entière, indiscernables d'une vraie carte. Elles se trahissent
autrement : elles n'ont presque jamais de nom français, donc elles ressortent
en « non résolu », et le total dépasse 100. C'est ce que le rapport signale.

Prérequis : `pdftotext` (paquet poppler-utils).
"""
import argparse
import collections
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db.cards as cards_db
from services.magic_ville_pdf import cells

DECK_SIZE = 100


def extract(pdf_path: Path) -> list:
    try:
        completed = subprocess.run(
            ["pdftotext", "-bbox-layout", str(pdf_path), "-"],
            capture_output=True, check=True, text=True, encoding="utf-8",
        )
    except FileNotFoundError:
        sys.exit("pdftotext est introuvable — installe le paquet poppler-utils.")
    except subprocess.CalledProcessError as error:
        sys.exit(f"pdftotext a échoué sur {pdf_path} : {error.stderr.strip()}")
    return cells(completed.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--commander", help="nom du commandant, tel qu'imprimé sur la planche")
    parser.add_argument("--output", type=Path, help="fichier de sortie (défaut : sortie standard)")
    args = parser.parse_args()

    grille = extract(args.pdf)
    names = [cell.name for cell in grille if cell.name]
    resolved = cards_db.resolve_names(sorted(set(names)))

    unresolved = [name for name in dict.fromkeys(names) if name.lower() not in resolved]
    counts = collections.Counter(name for name in names if name != args.commander)

    lines = []
    if args.commander:
        lines += ["Commander", f"1 {args.commander}", "", "Deck"]
    for name in sorted(counts):
        lines.append(f"{counts[name]} {name}")

    decklist = "\n".join(lines) + "\n"
    if args.output:
        args.output.write_text(decklist, encoding="utf-8")
        print(f"Decklist écrite dans {args.output}")
    else:
        print(decklist)

    # --- rapport, sur stderr pour ne pas polluer une redirection de la liste ---
    total = sum(counts.values()) + (1 if args.commander else 0)
    report = [f"{len(names)} vignettes lues, {total} exemplaires dans la liste."]

    # Une case vide ailleurs qu'en fin de planche veut dire qu'un titre n'a pas
    # été lu — typiquement deux vignettes dont les textes se chevauchent. C'est
    # plus précis qu'un simple écart sur le total.
    derniere_page = max(cell.page for cell in grille)
    vides = [cell for cell in grille
             if cell.name is None and cell.page != derniere_page]
    if vides:
        report.append("  Case(s) vide(s) — un titre n'a pas été lu : "
                      + ", ".join(f"page {c.page} rangée {c.row + 1} colonne {c.column + 1}"
                                  for c in vides))
    if total != DECK_SIZE:
        report.append(f"  /!\\ {DECK_SIZE} attendus : cherche une face arrière comptée "
                      f"deux fois, ou une vignette manquée.")
    if not args.commander:
        legendaires = sorted({
            resolved[name.lower()]["name"] for name in names
            if name.lower() in resolved
            and "Legendary" in (resolved[name.lower()]["type_line"] or "")
        })
        report.append("  Aucun --commander : candidats légendaires -> " + ", ".join(legendaires))

    doublons = [f"{name} x{count}" for name, count in counts.items()
                if count > 1 and name.lower() in resolved
                and "Basic Land" not in (resolved[name.lower()]["type_line"] or "")]
    if doublons:
        report.append("  Non-terrains en plusieurs exemplaires (singleton : suspect) -> "
                      + ", ".join(doublons))

    if unresolved:
        report.append(f"  {len(unresolved)} nom(s) non résolu(s) — faces arrière probables :")
        for name in unresolved:
            pistes = cards_db.find_by_similar_name(name, 2)
            suggestions = ", ".join(f"{c['name']} [{c.get('matched_fr') or '-'}]" for c in pistes)
            report.append(f"    {name!r} -> {suggestions or 'aucune piste'}")

    print("\n".join(report), file=sys.stderr)


if __name__ == "__main__":
    main()
