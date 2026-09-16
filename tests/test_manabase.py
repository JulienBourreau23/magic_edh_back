"""
Le diagnostic de manabase conseille de déplacer des terrains : une erreur y est
silencieuse, elle ressort en conseil plausible mais faux. Ces tests figent les
deux propriétés qui portent tout — la cible dépend de la demande de la couleur,
et la répartition conseillée se juge au nombre de cartes bloquées, pas à un
ratio par couleur.
"""
from services import deck_analysis
from services.card_categories import LAND


def spell(name, mana_cost, cmc, colors, quantity=1, is_commander=False):
    return {"name": name, "mana_cost": mana_cost, "cmc": cmc, "quantity": quantity,
            "color_identity": colors, "categories": [], "produced_mana": [],
            "type_line": "Instant", "is_commander": is_commander}


def land(name, produces, quantity=1, basic=False):
    return {"name": name, "mana_cost": None, "cmc": 0, "quantity": quantity,
            "color_identity": [], "categories": [LAND], "produced_mana": produces,
            "type_line": "Basic Land — Island" if basic else "Land",
            "is_commander": False}


def test_a_sources_egales_le_verdict_suit_la_demande():
    # Le cœur du correctif : dix-huit sources suffisent à un splash à un
    # symbole et pas à une couleur réclamée en double. Un plancher commun —
    # l'ancien MIN_SOURCES_PER_COLOR — donnait le même verdict aux deux.
    cards = [spell("Commandant", "{1}{U}{R}", 3, ["U", "R"], is_commander=True)]
    cards += [spell(f"Contresort {i}", "{1}{U}{U}", 3, ["U"]) for i in range(15)]
    cards += [spell("Sort rouge", "{1}{R}", 2, ["R"]),
              land("Montagne", ["R"], quantity=18, basic=True),
              land("Île", ["U"], quantity=18, basic=True)]
    colors = deck_analysis.manabase(cards)["colors"]
    assert colors["R"]["sources"] == colors["U"]["sources"] == 18
    assert not colors["R"]["under_supplied"]
    assert colors["U"]["under_supplied"]


def test_une_couleur_tres_demandee_est_signalee_malgre_beaucoup_de_sources():
    # Seize sources pour une couleur réclamée en double partout : c'est le cas
    # que le plancher absolu (dix sources) laissait passer.
    cards = [spell("Commandant", "{1}{U}{U}", 3, ["U"], is_commander=True)]
    cards += [spell(f"Contresort {i}", "{1}{U}{U}", 3, ["U"]) for i in range(20)]
    cards += [land("Île", ["U"], quantity=16, basic=True),
              land("Plaine", ["W"], quantity=21, basic=True)]
    colors = deck_analysis.manabase(cards)["colors"]
    assert colors["U"]["under_supplied"]
    assert colors["U"]["sources"] == 16 < colors["U"]["target"]


def test_les_cartes_mal_servies_sont_nommees():
    cards = [spell("Commandant", "{U}", 1, ["U"], is_commander=True),
             spell("Triple bleu", "{U}{U}{U}", 3, ["U"]),
             land("Île", ["U"], quantity=6, basic=True),
             land("Plaine", ["W"], quantity=30, basic=True)]
    strained = deck_analysis.manabase(cards)["strained_cards"]
    assert [entry["name"] for entry in strained][:1] == ["Triple bleu"]
    assert strained[0]["needed"] > strained[0]["sources"]


def test_le_conseil_suit_le_nombre_de_cartes_pas_le_nombre_de_symboles():
    # Dix sorts à un symbole bleu contre deux sorts à double blanc : le blanc a
    # la cible la plus haute, mais c'est le bleu qui bloque le plus de cartes.
    cards = [spell("Commandant", "{1}{W}{U}", 3, ["W", "U"], is_commander=True)]
    cards += [spell(f"Cantrip {i}", "{1}{U}", 2, ["U"]) for i in range(10)]
    cards += [spell(f"Double blanc {i}", "{1}{W}{W}", 3, ["W"]) for i in range(2)]
    cards += [land("Île", ["U"], quantity=2, basic=True),
              land("Plaine", ["W"], quantity=18, basic=True)]
    advice = deck_analysis.manabase(cards)["basic_lands"]
    assert advice["suggested"]["Île"] > advice["current"]["Île"]
    assert advice["stuck_after"] < advice["stuck_before"]


def test_le_conseil_ne_change_pas_le_nombre_de_terrains():
    cards = [spell("Commandant", "{1}{W}{U}", 3, ["W", "U"], is_commander=True)]
    cards += [spell(f"Cantrip {i}", "{1}{U}", 2, ["U"]) for i in range(10)]
    cards += [land("Île", ["U"], quantity=3, basic=True),
              land("Plaine", ["W"], quantity=17, basic=True)]
    advice = deck_analysis.manabase(cards)["basic_lands"]
    assert sum(advice["suggested"].values()) == sum(advice["current"].values()) == 20


def test_pas_de_conseil_quand_la_repartition_est_deja_la_bonne():
    cards = [spell("Commandant", "{U}", 1, ["U"], is_commander=True),
             land("Île", ["U"], quantity=20, basic=True)]
    assert deck_analysis.manabase(cards)["basic_lands"] is None


def test_un_deck_sans_terrain_de_base_ne_recoit_pas_de_conseil():
    # Rien à déplacer : conseiller une manabase entièrement non-basique
    # reviendrait à conseiller des achats, ce que cette fonction ne fait pas.
    cards = [spell("Commandant", "{1}{W}{U}", 3, ["W", "U"], is_commander=True),
             land("Fontaine sacrée", ["U", "W"], quantity=36)]
    assert deck_analysis.manabase(cards)["basic_lands"] is None


def test_le_commandant_pese_plus_qu_une_carte_du_deck():
    # Il est disponible à chaque tour : sa couleur ne doit pas être traitée
    # comme une carte sur 99, sinon un splash de commandant se fait affamer.
    commander = spell("Commandant", "{R}", 1, ["R"], is_commander=True)
    autre = spell("Sort rouge", "{R}", 1, ["R"])
    assert deck_analysis.availability(commander, 1) > deck_analysis.availability(autre, 1)
    assert deck_analysis.availability(commander, 1) == 1.0


def rock(name, mana_cost, cmc, produces):
    return {"name": name, "mana_cost": mana_cost, "cmc": cmc, "quantity": 1,
            "color_identity": [], "categories": ["ramp"], "produced_mana": produces,
            "type_line": "Artifact", "oracle_text": "{T}: Add {W}.", "is_commander": False}


def test_un_rocher_de_mana_compte_mais_pas_des_le_premier_tour():
    # Il faut d'abord le lancer : le compter disponible au tour 1, comme un
    # terrain, surestimait la stabilité de tout deck à rochers.
    cards = [spell("Commandant", "{W}", 1, ["W"], is_commander=True),
             rock("Cachet", "{2}", 2, ["W"]),
             land("Plaine", ["W"], quantity=20, basic=True)]
    identity = {"W"}
    ready = deck_analysis._sources_by_turn(cards, identity)
    assert deck_analysis._available(ready["W"], 1) == 20   # les terrains seuls
    assert deck_analysis._available(ready["W"], 3) == 21   # le cachet a pu être lancé
    # Il reste bien compté comme source de la couleur, lui aussi.
    assert deck_analysis.manabase(cards)["colors"]["W"]["sources"] == 21


def test_le_mode_rapide_ne_lance_aucune_simulation():
    cards = [spell("Commandant", "{W}", 1, ["W"], is_commander=True),
             land("Plaine", ["W"], quantity=20, basic=True)]
    assert deck_analysis.manabase(cards)["measured_stuck_rate"] is None


def test_le_mode_complet_mesure_et_tranche():
    cards = [spell("Commandant", "{1}{W}{U}", 3, ["W", "U"], is_commander=True)]
    cards += [spell(f"Cantrip {i}", "{1}{U}", 2, ["U"]) for i in range(20)]
    cards += [land("Île", ["U"], quantity=2, basic=True),
              land("Plaine", ["W"], quantity=18, basic=True)]
    manabase = deck_analysis.manabase(cards, deep=True)
    assert manabase["measured_stuck_rate"] is not None
    advice = manabase["basic_lands"]
    assert advice["confirmed"] is True
    assert advice["measured_after"] < advice["measured_before"]


def test_la_mesure_est_reproductible():
    cards = [spell("Commandant", "{1}{W}{U}", 3, ["W", "U"], is_commander=True)]
    cards += [spell(f"Sort {i}", "{1}{U}", 2, ["U"]) for i in range(20)]
    cards += [land("Île", ["U"], quantity=4, basic=True),
              land("Plaine", ["W"], quantity=16, basic=True)]
    assert (deck_analysis.manabase(cards, deep=True)["measured_stuck_rate"]
            == deck_analysis.manabase(cards, deep=True)["measured_stuck_rate"])


def test_un_gain_derisoire_n_est_pas_conseille():
    """
    Une manabase déjà saine se voit proposer des déplacements dont le gain tient
    dans le bruit. Les appliquer coûterait au joueur un remaniement pour rien.
    """
    cards = [spell("Commandant", "{1}{W}{U}", 3, ["W", "U"], is_commander=True)]
    cards += [spell(f"Sort {i}", "{1}{U}", 2, ["U"]) for i in range(10)]
    cards += [spell(f"Autre {i}", "{1}{W}", 2, ["W"]) for i in range(10)]
    cards += [land("Île", ["U"], quantity=18, basic=True),
              land("Plaine", ["W"], quantity=18, basic=True)]
    advice = deck_analysis.manabase(cards, deep=True)["basic_lands"]
    if advice is not None:
        gain = advice["measured_before"] - advice["measured_after"]
        assert advice["confirmed"] == (gain >= deck_analysis.MIN_MEASURED_GAIN)
