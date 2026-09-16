"""
Découpage d'une planche de proxys magic-ville. Chaque cas reproduit, aux
coordonnées près, une vignette qui a réellement fait dérailler une conversion :
le PDF n'a pas de decklist, donc une erreur ici produit une liste plausible et
fausse — le genre d'erreur qu'on ne voit qu'en jouant.
"""
from services.magic_ville_pdf import card_names, cells

# Une planche fait 3 colonnes x 3 rangées ; seules les coordonnées comptent.
COLONNES = (9.25, 175.82, 342.40)
BASE = 3.0
INTERLIGNE = 17.0
RANGEES = (BASE, BASE + 238.0, BASE + 475.0)


def _ligne(x: float, y: float, texte: str, largeur: float = 100.0, hauteur: float = 16.34) -> str:
    mots = "".join(f'<word xMin="{x}" yMin="{y}" xMax="{x + largeur}" yMax="{y + hauteur}">{mot}</word>'
                   for mot in texte.split(" "))
    return (f'<line xMin="{x}" yMin="{y}" xMax="{x + largeur}" yMax="{y + hauteur}">'
            f'{mots}</line>')


def _planche(*lignes: str) -> str:
    return '<page width="596" height="842">' + "".join(lignes) + "</page>"


def test_une_case_par_vignette():
    xhtml = _planche(*(_ligne(x, y, f"Carte {i}")
                       for i, (y, x) in enumerate((y, x) for y in RANGEES for x in COLONNES)))
    assert card_names(xhtml) == [f"Carte {i}" for i in range(9)]


def test_nom_d_aventure_ignore():
    # « Chapardage » est écrit dans le corps du titre, mais au milieu de la
    # vignette : c'est la seconde moitié d'une carte-aventure, pas une carte.
    xhtml = _planche(
        _ligne(COLONNES[0], BASE, "Emprunteur intrépide"),
        _ligne(COLONNES[0], BASE + 120, "Chapardage"),
    )
    assert card_names(xhtml) == ["Emprunteur intrépide"]


def test_texte_deborde_d_une_vignette_voisine_ignore():
    # Le piège le plus vicieux : du texte débordé se pose deux points au-dessus
    # des vrais titres. Il ne partage pas la ligne de base de la rangée.
    xhtml = _planche(
        _ligne(10.75, BASE - 2.6, "créature plus cafouillesort"),
        _ligne(COLONNES[0], BASE, "Farfadette cafouillesort"),
        _ligne(COLONNES[2], BASE, "Jace, le sculpteur"),
    )
    assert card_names(xhtml) == ["Farfadette cafouillesort", "Jace, le sculpteur"]


def test_titre_sur_trois_lignes():
    xhtml = _planche(
        _ligne(COLONNES[1], BASE, "Tamiyo,"),
        _ligne(COLONNES[1], BASE + INTERLIGNE, "chercheuse sur le"),
        _ligne(COLONNES[1], BASE + 2 * INTERLIGNE, "terrain"),
    )
    assert card_names(xhtml) == ["Tamiyo, chercheuse sur le terrain"]


def test_ligne_de_type_rejetee():
    # Elle tombe dans la fenêtre verticale de la rangée suivante, et la forme
    # « un type, puis deux points » la distingue d'un nom comme Terrain fertile.
    xhtml = _planche(
        _ligne(COLONNES[0], BASE, "Danitha Capashen, parangon"),
        _ligne(COLONNES[0], BASE + 2 * INTERLIGNE, "Créature légendaire : humain et chevalier"),
    )
    assert card_names(xhtml) == ["Danitha Capashen, parangon"]


def test_nom_qui_ressemble_a_un_type_conserve():
    xhtml = _planche(_ligne(COLONNES[0], BASE, "Terrain fertile"))
    assert card_names(xhtml) == ["Terrain fertile"]


def test_nom_coupe_en_deux_sur_la_meme_ligne():
    # « Précepteur » et « diabolique » sont deux blocs séparés par 3 points.
    xhtml = _planche(
        _ligne(COLONNES[1], BASE, "Précepteur", largeur=62.93),
        _ligne(COLONNES[1] + 66.05, BASE, "diabolique", largeur=61.23),
    )
    assert card_names(xhtml) == ["Précepteur diabolique"]


def test_deux_colonnes_ne_se_recollent_pas():
    # Même ligne de base, mais l'écart est celui de deux colonnes : deux cartes.
    xhtml = _planche(
        _ligne(COLONNES[0], BASE, "Mystique elfe", largeur=77.0),
        _ligne(COLONNES[1], BASE, "Voix du renouveau", largeur=108.0),
    )
    assert card_names(xhtml) == ["Mystique elfe", "Voix du renouveau"]


def test_cesure_recollee():
    xhtml = _planche(
        _ligne(COLONNES[2], BASE, "Kiki-Jiki, brise-"),
        _ligne(COLONNES[2], BASE + INTERLIGNE, "miroir"),
    )
    assert card_names(xhtml) == ["Kiki-Jiki, brise-miroir"]


def test_ligature_typographique_decomposee():
    # pdftotext rend « ﬁ » en un seul caractère ; la base écrit « fi ».
    assert card_names(_planche(_ligne(COLONNES[0], BASE, "Village fortiﬁé"))) == ["Village fortifié"]


def test_ae_n_est_pas_une_ligature():
    # « æ » est une lettre : certaines cartes l'ont vraiment dans leur nom.
    assert card_names(_planche(_ligne(COLONNES[0], BASE, "Nuée de færies"))) == ["Nuée de færies"]


def test_case_vide_signalee():
    # Une case vide ailleurs qu'en fin de planche veut dire qu'un titre a été
    # perdu : c'est le seul signal disponible quand deux vignettes se marchent
    # dessus, et le script s'en sert pour alerter.
    grille = cells(_planche(
        _ligne(COLONNES[0], BASE, "Pincecrâne"),
        _ligne(COLONNES[2], BASE, "Porte des Destinées"),
    ))
    milieu = next(c for c in grille if c.row == 0 and c.column == 1)
    assert milieu.name is None
    assert sum(1 for c in grille if c.name) == 2
