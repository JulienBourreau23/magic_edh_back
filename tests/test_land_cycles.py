"""
Cycles de terrains et extraction vidéo.

Deux mesures faites sur une vraie vidéo décident de ces règles, et une
régression y passerait inaperçue : un motif de cycle devenu trop large
range n'importe quel terrain dans une famille, et un nom de carte d'un seul mot
transforme une conversation française en liste d'achats.
"""
from services import land_cycles, video_cards


def terrain(texte: str) -> dict:
    return {"oracle_text": texte, "type_line": "Land"}


def test_les_cycles_se_reconnaissent_a_leur_texte():
    assert land_cycles.classify(
        terrain("({T}: Add {B} or {G}.)\nThis land enters tapped unless you control a Swamp "
                "or a Forest.")) == "check"
    assert land_cycles.classify(
        terrain("This land enters tapped unless you control two or more basic lands.")) == "tango"
    assert land_cycles.classify(
        terrain("This land enters tapped unless you control two or more other lands.")) == "slow"
    assert land_cycles.classify(
        terrain("{T}: Add {C}.\n{T}: Add {B} or {G}. This land deals 1 damage to you.")) == "pain"
    assert land_cycles.classify(
        terrain("{T}: Add {C}.\n{B/G}, {T}: Add {B}{B}, {B}{G}, or {G}{G}.")) == "filter"


def test_un_terrain_ordinaire_n_appartient_a_aucun_cycle():
    # Le garde-fou qui compte : un motif trop large rangerait n'importe quel
    # terrain dans une famille, et la page conseillerait d'acheter du vide.
    assert land_cycles.classify(terrain("{T}: Add {G}.")) is None
    assert land_cycles.classify(terrain("")) is None


def test_le_chapitrage_d_une_video_designe_un_cycle():
    # Les titres viennent d'une vidéo réelle : c'est ainsi qu'une chaîne
    # francophone nomme ces familles.
    assert land_cycles.cycle_of_text("TANGO LANDS") == "tango"
    assert land_cycles.cycle_of_text("CHECKLANDS") == "check"
    assert land_cycles.cycle_of_text("ODISSEY FILTERS") == "filter"
    assert land_cycles.cycle_of_text("INTRODUCTION") is None
    assert land_cycles.cycle_of_text("4 OU 5 COULEURS") is None


def test_un_nom_d_un_seul_mot_n_est_jamais_retenu():
    # Mesuré : en acceptant un seul mot, une vidéo de treize minutes ramenait
    # « Concentration », « Dragons », « Embuscade », « Mutilation » — des mots
    # français courants qui sont aussi des noms de cartes. Sept faux positifs
    # sur dix-huit trouvailles.
    index = {"sol ring": "oracle-sol-ring", "concentration": "oracle-concentration"}
    segments = [{"text": "je mets un Sol Ring et beaucoup de concentration", "start": 0}]

    trouvees = video_cards.find_cards(segments, index)

    assert [m["key"] for m in trouvees] == ["oracle-sol-ring"]


def test_les_accents_et_la_casse_ne_comptent_pas():
    # Les sous-titres automatiques n'ont ni majuscules ni accents fiables.
    index = {"anneau solaire": "oracle-anneau"}
    segments = [{"text": "un ANNEAU SOLAIRE au tour un", "start": 12.5}]

    trouvees = video_cards.find_cards(segments, index)

    assert trouvees[0]["key"] == "oracle-anneau"
    assert trouvees[0]["first_seconds"] == 12
