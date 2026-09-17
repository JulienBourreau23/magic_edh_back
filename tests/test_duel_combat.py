"""
Les règles de combat du duel simulé.

Chaque mot-clé ajouté ici déplace un taux de victoire. Une règle mal branchée
ne lève aucune erreur : elle produit simplement un chiffre faux, qu'on lira
comme une mesure. D'où un test par règle, sur le plus petit plateau qui la
montre.

Les mots-clés viennent de `cards.keywords` (Scryfall) : ils sont constatés, pas
devinés depuis le texte oracle.
"""
from services.duel import (
    COMMANDER_DAMAGE_LETHAL,
    Permanent,
    Player,
    _cast_phase,
    _combat_phase,
    _legal_blockers,
    _resolve_block,
    _take_turn,
    to_duel_card,
)


def card(name, **overrides):
    base = {
        "name": name, "quantity": 1, "cmc": 0, "mana_cost": "", "categories": [],
        "produced_mana": [], "oracle_text": "", "is_commander": False,
        "type_line": "", "power": None, "toughness": None, "keywords": [],
        "oracle_id": name,
    }
    return {**base, **overrides}


def creature(name, power, toughness, keywords=None, **overrides):
    return card(name, type_line="Creature — Test", power=str(power),
                toughness=str(toughness), keywords=keywords or [], **overrides)


def joueur(name="a", life=40, creatures=(), hand=(), sources=0, color="G"):
    terrain = card("Terrain", categories=["land"], produced_mana=[color],
                   oracle_text="({T}: Add {%s}.)" % color, type_line="Basic Land")
    return Player(
        name=name, library=[], commander=None, life=life,
        hand=[to_duel_card(c) for c in hand],
        mana_sources=[to_duel_card(terrain) for _ in range(sources)],
        creatures=[Permanent(to_duel_card(c), summoning_sick=False) for c in creatures],
    )


# --- qui peut bloquer quoi ------------------------------------------------

def test_le_vol_ne_se_bloque_pas_au_sol():
    voleur = Permanent(to_duel_card(creature("Ange", 3, 3, ["Flying"])))
    sol = Permanent(to_duel_card(creature("Ours", 4, 4)))
    portée = Permanent(to_duel_card(creature("Araignée", 2, 4, ["Reach"])))
    autre_voleur = Permanent(to_duel_card(creature("Drake", 2, 2, ["Flying"])))

    légaux = _legal_blockers(voleur, [sol, portée, autre_voleur])

    assert sol not in légaux
    assert portée in légaux and autre_voleur in légaux


def test_un_attaquant_au_sol_se_bloque_par_n_importe_qui():
    ours = Permanent(to_duel_card(creature("Ours", 2, 2)))
    ange = Permanent(to_duel_card(creature("Ange", 3, 3, ["Flying"])))
    assert _legal_blockers(ours, [ange]) == [ange]


def test_le_vol_passe_et_fait_des_degats():
    attaquant = joueur(creatures=[creature("Ange", 3, 3, ["Flying"])])
    défenseur = joueur("b", creatures=[creature("Ours", 4, 4)])

    _combat_phase(attaquant, défenseur)

    assert défenseur.life == 37
    assert len(défenseur.creatures) == 1   # l'ours n'a pas pu bloquer


def test_la_menace_passe_face_a_un_seul_bloqueur():
    attaquant = joueur(creatures=[creature("Brute", 3, 3, ["Menace"])])
    défenseur = joueur("b", creatures=[creature("Ours", 4, 4)])

    _combat_phase(attaquant, défenseur)

    assert défenseur.life == 37


def test_la_menace_est_bloquee_par_deux_creatures():
    attaquant = joueur(creatures=[creature("Brute", 3, 3, ["Menace"])])
    défenseur = joueur("b", creatures=[creature("Ours", 4, 4), creature("Ours", 4, 4)])

    _combat_phase(attaquant, défenseur)

    assert défenseur.life == 40
    assert attaquant.creatures == []       # la brute meurt sur le bloc


# --- résolution des dégâts ------------------------------------------------

def test_le_contact_mortel_tue_n_importe_quoi():
    attaquant = joueur(creatures=[creature("Serpent", 1, 1, ["Deathtouch"])])
    défenseur = joueur("b", creatures=[creature("Colosse", 5, 5)])

    _combat_phase(attaquant, défenseur)

    assert défenseur.creatures == []       # le 5/5 meurt d'un seul point
    assert attaquant.creatures == []       # le serpent meurt aussi


def test_l_initiative_tue_avant_d_etre_touche():
    attaquant = joueur(creatures=[creature("Chevalier", 2, 2, ["First strike"])])
    défenseur = joueur("b", creatures=[creature("Ours", 2, 2)])

    _combat_phase(attaquant, défenseur)

    assert défenseur.creatures == []
    assert len(attaquant.creatures) == 1   # il ne subit rien en retour


def test_la_double_initiative_frappe_deux_fois():
    attaquant = joueur(creatures=[creature("Lame", 2, 2, ["Double strike"])])
    défenseur = joueur("b")

    _combat_phase(attaquant, défenseur)

    assert défenseur.life == 36            # 2 de force, deux étapes de dégâts


def test_le_pietinement_laisse_passer_l_excedent():
    # Testé sur la résolution d'un bloc, et non sur une phase de combat
    # entière : un défenseur à 40 points de vie a raison de ne pas bloquer un
    # 6/6 avec un 1/2, donc la phase complète ne montrerait jamais le cas.
    attaquant = joueur()
    défenseur = joueur("b", creatures=[creature("Ourson", 1, 2)])
    béhémoth = Permanent(to_duel_card(creature("Béhémoth", 6, 6, ["Trample"])),
                         summoning_sick=False)
    attaquant.creatures.append(béhémoth)

    excédent = _resolve_block(béhémoth, défenseur.creatures[0], attaquant, défenseur)

    assert défenseur.creatures == []
    assert excédent == 4                   # 6 de force - 2 d'endurance


def test_sans_pietinement_rien_ne_passe():
    attaquant = joueur()
    défenseur = joueur("b", creatures=[creature("Ourson", 1, 2)])
    colosse = Permanent(to_duel_card(creature("Colosse", 6, 6)), summoning_sick=False)
    attaquant.creatures.append(colosse)

    excédent = _resolve_block(colosse, défenseur.creatures[0], attaquant, défenseur)

    assert défenseur.creatures == []
    assert excédent == 0


def test_le_lien_de_vie_fait_gagner_des_points_de_vie():
    attaquant = joueur(life=20, creatures=[creature("Vampire", 3, 3, ["Lifelink"])])
    défenseur = joueur("b")

    _combat_phase(attaquant, défenseur)

    assert attaquant.life == 23
    assert défenseur.life == 37


def test_l_indestructible_survit_au_combat():
    attaquant = joueur(creatures=[creature("Colosse", 9, 9)])
    défenseur = joueur("b", creatures=[creature("Statue", 1, 1, ["Indestructible"])])

    _combat_phase(attaquant, défenseur)

    assert len(défenseur.creatures) == 1


def test_l_indestructible_survit_au_board_wipe():
    player = joueur(creatures=[creature("Statue", 1, 1, ["Indestructible"]),
                               creature("Ours", 2, 2)])
    player.destroy(list(player.creatures))
    assert [p.card.name for p in player.creatures] == ["Statue"]


# --- attaquer a un coût ---------------------------------------------------

def test_attaquer_engage_la_creature_qui_ne_bloque_plus():
    """
    Sans ça, tout le monde jouait comme s'il avait la vigilance : attaquer ne
    coûtait rien, et le modèle surestimait l'agression.
    """
    attaquant = joueur(creatures=[creature("Ours", 2, 2)])
    défenseur = joueur("b")

    _combat_phase(attaquant, défenseur)

    assert attaquant.creatures[0].tapped is True
    assert attaquant.creatures[0].can_block is False


def test_la_vigilance_laisse_la_creature_disponible():
    attaquant = joueur(creatures=[creature("Sentinelle", 2, 2, ["Vigilance"])])
    défenseur = joueur("b")

    _combat_phase(attaquant, défenseur)

    assert attaquant.creatures[0].tapped is False
    assert attaquant.creatures[0].can_block is True


def test_une_creature_fraiche_n_attaque_pas_sauf_celerite():
    lente = Permanent(to_duel_card(creature("Ours", 2, 2)))
    rapide = Permanent(to_duel_card(creature("Gobelin", 2, 2, ["Haste"])))
    assert lente.can_attack is False
    assert rapide.can_attack is True


def test_un_defenseur_n_attaque_pas():
    mur = Permanent(to_duel_card(creature("Mur", 0, 6, ["Defender"])),
                    summoning_sick=False)
    assert mur.can_attack is False


# --- dégâts de commandant -------------------------------------------------

def test_vingt_et_un_degats_de_commandant_font_perdre():
    attaquant = joueur()
    chef = Permanent(to_duel_card(creature("Chef", COMMANDER_DAMAGE_LETHAL, 5)),
                     summoning_sick=False, is_commander=True)
    attaquant.creatures.append(chef)
    défenseur = joueur("b", life=40)

    _combat_phase(attaquant, défenseur)

    assert défenseur.commander_damage == COMMANDER_DAMAGE_LETHAL
    # Les points de vie ne sont pas à zéro : c'est bien la seconde horloge qui
    # décide, et elle n'existait pas avant.
    assert défenseur.life == 19


def test_les_degats_d_une_creature_ordinaire_ne_comptent_pas_comme_commandant():
    attaquant = joueur(creatures=[creature("Ours", 5, 5)])
    défenseur = joueur("b")

    _combat_phase(attaquant, défenseur)

    assert défenseur.commander_damage == 0


# --- linceul, contresorts, pioche ----------------------------------------

def test_le_removal_ne_vise_pas_une_creature_au_linceul():
    removal = card("Meurtre", cmc=2, mana_cost="{1}{B}", categories=["removal"],
                   type_line="Instant", produced_mana=[])
    player = joueur(hand=[removal], sources=5)
    adversaire = joueur("b", creatures=[creature("Intouchable", 8, 8, ["Hexproof"])])

    _cast_phase(player, adversaire)

    assert len(adversaire.creatures) == 1


def test_un_contresort_arrete_un_sort_cher():
    gros = creature("Colosse", 7, 7, cmc=6, mana_cost="{6}")
    lanceur = joueur(hand=[gros], sources=8)
    contre = card("Contresort", cmc=2, mana_cost="{U}{U}", categories=["counterspell"],
                  type_line="Instant")
    adversaire = joueur("b", hand=[contre], sources=8)
    adversaire.counter_ready = to_duel_card(contre)

    _cast_phase(lanceur, adversaire)

    assert lanceur.creatures == []
    assert adversaire.counter_ready is None      # le contresort est consommé


def test_un_contresort_ne_part_pas_sur_une_petite_carte():
    petite = creature("Ourson", 1, 1, cmc=1, mana_cost="{G}")
    lanceur = joueur(hand=[petite], sources=8)
    contre = card("Contresort", cmc=2, mana_cost="{U}{U}", categories=["counterspell"],
                  type_line="Instant")
    adversaire = joueur("b")
    adversaire.counter_ready = to_duel_card(contre)

    _cast_phase(lanceur, adversaire)

    assert len(lanceur.creatures) == 1
    assert adversaire.counter_ready is not None  # gardé pour mieux


def test_un_sort_de_pioche_pioche_vraiment():
    pioche = card("Divination", cmc=3, mana_cost="{2}{U}", categories=["draw"],
                  type_line="Sorcery", oracle_text="Draw two cards.")
    player = joueur(hand=[pioche], sources=6, color="U")
    player.library = [to_duel_card(creature("Ours", 2, 2)) for _ in range(5)]

    _cast_phase(player, joueur("b"))

    # On mesure la bibliothèque, pas la main : les cartes piochées sont des
    # créatures à coût nul, donc lancées dans la foulée par la même phase.
    assert len(player.library) == 3
    assert len(player.creatures) == 2


# --- combos gagnants ------------------------------------------------------

def test_un_combo_gagnant_en_main_termine_la_partie():
    """
    Le critère est celui qu'affiche déjà la fiche de deck : les deux pièces
    disponibles, et le mana total payable. Sans ça, un deck qui gagne par combo
    était joué comme s'il ne pouvait gagner qu'au combat — le biais que ce
    travail visait.
    """
    player = joueur(hand=[card("Pièce A", oracle_id="A"), card("Pièce B", oracle_id="B")],
                    sources=4)
    player.winning_combos = [(frozenset({"A", "B"}), 4)]
    assert player.combo_ready() is True


def test_un_combo_sans_le_mana_n_est_pas_execute():
    player = joueur(hand=[card("Pièce A", oracle_id="A"), card("Pièce B", oracle_id="B")],
                    sources=3)
    player.winning_combos = [(frozenset({"A", "B"}), 8)]
    assert player.combo_ready() is False


def test_un_combo_a_une_seule_piece_n_est_pas_execute():
    player = joueur(hand=[card("Pièce A", oracle_id="A")], sources=10)
    player.winning_combos = [(frozenset({"A", "B"}), 2)]
    assert player.combo_ready() is False


def test_une_piece_deja_en_jeu_compte():
    player = joueur(creatures=[creature("Pièce A", 2, 2, oracle_id="A")],
                    hand=[card("Pièce B", oracle_id="B")], sources=5)
    player.winning_combos = [(frozenset({"A", "B"}), 5)]
    assert player.combo_ready() is True


def test_seuls_les_combos_gagnants_sont_retenus():
    from services.duel import winning_combo_pairs

    catalogue = [
        {"oracle_ids": ["A", "B"], "wins_outright": True, "total_mana_value": 6},
        {"oracle_ids": ["C", "D"], "wins_outright": False, "total_mana_value": 3},
    ]
    retenus = winning_combo_pairs(catalogue)

    # Le mana infini demande une troisième carte : il ne finit pas la partie,
    # et ne doit donc pas la gagner ici non plus.
    assert retenus == [(frozenset({"A", "B"}), 6)]
