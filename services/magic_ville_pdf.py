"""
services/magic_ville_pdf.py — lecture d'une planche de proxys magic-ville.

Le site exporte un deck en pages A4 de 3x3 vignettes : nom en gros, ligne de
type, texte, force/endurance. Il n'y a pas de liste, donc la decklist se
reconstruit à partir de la **position** des mots — `pdftotext` livre le texte
brut dans un ordre qui mélange les colonnes.

Le corps du titre (plus de 15 points) isole les noms, mais il sert aussi à
autre chose. Cinq pièges, tous rencontrés sur des decks réels :

1. **Le nom d'une aventure** (« Chapardage » sous Emprunteur intrépide) est
   écrit dans le corps du titre, au milieu de la vignette : seul ce qui
   commence sur la ligne de base d'une case est un nom de carte.
2. **Le texte d'une vignette voisine qui déborde** atterrit à quelques points
   du haut de la case suivante. Il ne partage pas la ligne de base de la
   rangée — c'est ce qui le trahit, mieux que sa forme.
3. **Un nom sur deux ou trois lignes** descend d'exactement 17 points par
   ligne, et **un nom coupé en deux fragments** sur la même ligne de base
   (« Précepteur » + « diabolique ») se recolle par l'écart horizontal.
4. **Les ligatures typographiques** : `pdftotext` rend « ﬁ » et « ﬂ » en un
   seul caractère, que `NFKC` redécompose ; et une césure laisse un blanc
   après le trait d'union (« Kiki-Jiki, brise- miroir »). En revanche `æ` est
   une lettre, pas une ligature : certaines cartes l'ont vraiment dans leur nom.
5. **Les faces arrière** (recto-verso, aventures) sont imprimées comme des
   proxys à part entière, géométriquement indiscernables d'une vraie carte.
   Celles-là, seule la résolution contre la base les démasque. Ce module ne
   peut que compter les cases : c'est l'appelant qui signale l'anomalie.
"""
import re
import unicodedata
from dataclasses import dataclass
from html import unescape

# Les trois colonnes d'une planche, en points PostScript. Le haut de la
# première rangée varie d'une page à l'autre (9 sur la première, 3 ensuite) :
# il est mesuré, les deux autres rangées s'en déduisent.
COLUMN_X = (9.25, 176.0, 342.5)
ROW_OFFSETS = (0.0, 238.0, 475.0)
COLUMN_TOLERANCE = 5.0
ROW_TOLERANCE = 36.0
TITLE_MIN_HEIGHT = 15.0
# Interligne d'un titre, mesuré identique sur les cinq planches.
LINE_SPACING = 17.0
BASELINE_TOLERANCE = 2.0
# Au-delà, deux fragments sur la même ligne de base appartiennent à deux textes
# différents et non à un nom coupé en deux.
FRAGMENT_GAP = 6.0

_TYPES = ("Créature|Créature-artefact|Terrain|Artefact|Enchantement|Éphémère"
          "|Rituel|Planeswalker|Bataille|Enchantement-artefact")
_IS_TYPE_LINE = re.compile(rf"^({_TYPES})\b.*\s:\s|^({_TYPES})s?$")

_LINE_RE = re.compile(
    r'<line xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</line>',
    re.S,
)
_WORD_RE = re.compile(r">([^<]*)</word>")
# Césure : « brise- miroir » est un seul mot coupé par la mise en page.
_HYPHEN_BREAK_RE = re.compile(r"-\s+")


@dataclass(frozen=True)
class Cell:
    """Une vignette de la planche. `name` vaut None si la case est vide."""
    page: int
    row: int
    column: int
    name: str | None


@dataclass(frozen=True)
class _Fragment:
    x_min: float
    x_max: float
    y: float
    text: str


def _fragments(page_xml: str) -> list[_Fragment]:
    """Les morceaux de texte écrits dans le corps du titre, lignes de type exclues."""
    found = []
    for match in _LINE_RE.finditer(page_xml):
        x_min, y_min, x_max, y_max = (float(value) for value in match.groups()[:4])
        if y_max - y_min < TITLE_MIN_HEIGHT:
            continue
        text = unicodedata.normalize("NFKC", unescape(" ".join(_WORD_RE.findall(match.group(5))))).strip()
        if text and not _IS_TYPE_LINE.match(text):
            found.append(_Fragment(x_min, x_max, y_min, text))
    return found


def _column_of(x: float) -> int | None:
    for index, column_x in enumerate(COLUMN_X):
        if abs(x - column_x) < COLUMN_TOLERANCE:
            return index
    return None


def _baseline(fragments: list[_Fragment]) -> float | None:
    """
    La ligne de base d'une rangée : celle où **le plus de colonnes** commencent
    un titre. Prendre le plus haut ne marcherait pas — du texte débordé d'une
    vignette voisine se place volontiers deux points au-dessus des vrais noms.
    """
    columns_by_y: dict[float, set[int]] = {}
    for fragment in fragments:
        column = _column_of(fragment.x_min)
        if column is not None:
            columns_by_y.setdefault(round(fragment.y, 1), set()).add(column)
    if not columns_by_y:
        return None
    return max(columns_by_y, key=lambda y: (len(columns_by_y[y]), -y))


def _on_title_line(y: float, baseline: float) -> bool:
    """Un titre tient sur trois lignes au plus, espacées de `LINE_SPACING`."""
    return any(abs(y - (baseline + LINE_SPACING * n)) <= BASELINE_TOLERANCE for n in (0, 1, 2))


def _assemble(fragments: list[_Fragment], column: int) -> str | None:
    """Recolle les morceaux d'une case : les lignes du titre, puis leurs suites."""
    lines = []
    for start in sorted((f for f in fragments if _column_of(f.x_min) == column),
                        key=lambda f: f.y):
        text, right_edge = start.text, start.x_max
        # Un nom coupé en deux sur la même ligne de base (« Précepteur » +
        # « diabolique ») : on absorbe ce qui suit immédiatement à droite.
        for other in sorted((f for f in fragments if abs(f.y - start.y) <= BASELINE_TOLERANCE),
                            key=lambda f: f.x_min):
            if 0 <= other.x_min - right_edge < FRAGMENT_GAP:
                text += " " + other.text
                right_edge = other.x_max
        lines.append(text)
    if not lines:
        return None
    return _HYPHEN_BREAK_RE.sub("-", " ".join(lines)).strip()


def cells(bbox_xhtml: str) -> list[Cell]:
    """Les neuf cases de chaque page, vides comprises — dans l'ordre de lecture."""
    found = []
    for page_index, page_xml in enumerate(bbox_xhtml.split("<page ")[1:], start=1):
        fragments = _fragments(page_xml)
        if not fragments:
            continue
        first_row_top = min(f.y for f in fragments)

        for row, offset in enumerate(ROW_OFFSETS):
            top = first_row_top + offset
            in_row = [f for f in fragments if top - 2 <= f.y <= top + ROW_TOLERANCE]
            baseline = _baseline(in_row)
            if baseline is None:
                found.extend(Cell(page_index, row, column, None) for column in range(3))
                continue

            on_title = [f for f in in_row if _on_title_line(f.y, baseline)]
            for column in range(3):
                found.append(Cell(page_index, row, column, _assemble(on_title, column)))
    return found


def card_names(bbox_xhtml: str) -> list[str]:
    """
    Les noms de cartes d'une planche, dans l'ordre des vignettes.

    Prend la sortie de `pdftotext -bbox-layout`. Un exemplaire par vignette :
    les doublons sont voulus (terrains de base), c'est à l'appelant d'agréger.
    """
    return [cell.name for cell in cells(bbox_xhtml) if cell.name]
