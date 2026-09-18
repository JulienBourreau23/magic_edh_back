"""
Le plan de quatre decks décide de ce qu'il faut acheter : une erreur ici coûte
de l'argent en silence. On vérifie les règles qui ne se voient pas à l'œil sur
la page — la réservation des exemplaires, le plafond de prix, le plancher de
rôles et le choix du groupe.
"""
from services import deck_plans
from services.card_categories import BOARD_WIPE, DRAW, LAND, RAMP, REMOVAL

ROLES = [RAMP, DRAW, REMOVAL, BOARD_WIPE]


def card(name: str, *, categories: list[str] | None = None, price: float | None = 1.0,
         owned: int = 0, inclusion: float = 0.5, game_changer: bool = False,
         mana_cost: str = "{1}{B}") -> dict:
    """Une ligne telle que `db.commanders.recommendation_pool` la renvoie."""
    return {
        "oracle_id": f"oracle-{name}",
        "scryfall_id": f"scryfall-{name}",
        "name": name,
        "name_fr": None,
        "type_line": "Land" if categories and LAND in categories else "Artifact",
        "mana_cost": mana_cost,
        "cmc": 2,
        "color_identity": ["B"],
        "price_eur": price,
        "image_uri": None,
        "image_downloaded": False,
        "categories": categories or [],
        "game_changer": game_changer,
        "inclusion_rate": inclusion,
        "owned_quantity": owned,
    }


def commander(name: str = "Chef", identity: list[str] | None = None) -> dict:
    return {
        "oracle_id": f"oracle-{name}", "scryfall_id": f"scryfall-{name}", "name": name,
        "name_fr": None, "color_identity": identity or ["B"], "image_uri": None,
        "image_downloaded": False, "mana_cost": "{2}{B}", "categories": [],
        "game_changer": False, "existing_deck_id": None,
    }


def full_pool(prefix: str, *, price: float = 1.0, owned_names: set[str] | None = None) -> list[dict]:
    """De quoi remplir un noyau complet : assez de cartes dans chaque rôle."""
    owned_names = owned_names or set()
    pool = []
    for role in ROLES:
        for index in range(15):
            name = f"{prefix}-{role}-{index}"
            pool.append(card(name, categories=[role], price=price,
                             owned=1 if name in owned_names else 0))
    for index in range(30):
        name = f"{prefix}-neutre-{index}"
        pool.append(card(name, price=price, owned=1 if name in owned_names else 0))
    return pool


def test_le_noyau_atteint_les_planchers_de_role():
    plan = deck_plans.build_deck(commander(), full_pool("a"), {}, max_price=50, target_bracket=None)

    assert plan["core_size"] == deck_plans.CORE_SIZE
    assert plan["role_gap"] == 0
    assert plan["role_counts"][RAMP] >= 10
    assert plan["role_counts"][BOARD_WIPE] >= 2


def test_une_carte_trop_chere_et_non_possedee_n_est_pas_retenue():
    pool = [card("Chere", categories=[RAMP], price=80.0), *full_pool("b")]
    plan = deck_plans.build_deck(commander(), pool, {}, max_price=50, target_bracket=None)

    assert "Chere" not in [item["name"] for item in plan["core"]]


def test_une_carte_chere_deja_possedee_reste_gratuite():
    # Le plafond de prix ne concerne que les achats : posséder une carte à 80 €
    # ne coûte rien de plus.
    pool = [card("Chere", categories=[RAMP], price=80.0, owned=1), *full_pool("c")]
    plan = deck_plans.build_deck(commander(), pool, {"oracle-Chere": 1}, max_price=50,
                                 target_bracket=None)

    chere = next(item for item in plan["core"] if item["name"] == "Chere")
    assert chere["owned"] is True
    assert chere["price_eur"] == 80.0
    assert plan["cost_eur"] < 80


def test_un_exemplaire_ne_sert_qu_a_un_deck():
    partagee = card("Partagee", categories=[RAMP], price=9.0, owned=1, inclusion=0.99)
    pool_a = [partagee, *full_pool("d")]
    pool_b = [partagee, *full_pool("e")]
    available = {"oracle-Partagee": 1}

    premier = deck_plans.build_deck(commander("A"), pool_a, available, 50, None)
    second = deck_plans.build_deck(commander("B"), pool_b, available, 50, None)

    assert next(i for i in premier["core"] if i["name"] == "Partagee")["owned"] is True
    assert next(i for i in second["core"] if i["name"] == "Partagee")["owned"] is False

    achats = deck_plans._shopping_list([premier, second])
    ligne = next(item for item in achats if item["name"] == "Partagee")
    assert ligne["quantity"] == 1
    assert ligne["total_eur"] == 9.0
    assert ligne["decks"] == ["B"]


def test_viser_le_bracket_2_ecarte_les_game_changers():
    pool = [card("GC", categories=[RAMP], game_changer=True, inclusion=0.99), *full_pool("f")]

    libre = deck_plans.build_deck(commander(), pool, {}, 50, target_bracket=None)
    contenu = deck_plans.build_deck(commander(), pool, {}, 50, target_bracket=2)

    assert "GC" in [item["name"] for item in libre["core"]]
    assert "GC" not in [item["name"] for item in contenu["core"]]
    assert contenu["bracket"]["min"] <= 2


def test_les_terrains_possedes_sont_pris_avant_les_basiques():
    terrain = card("Terrain utile", categories=[LAND], price=4.0, owned=1)
    pool = [terrain, *full_pool("g")]
    plan = deck_plans.build_deck(commander(), pool, {"oracle-Terrain utile": 1}, 50, None)

    lands = plan["lands"]
    assert [item["name"] for item in lands["owned_nonbasic"]] == ["Terrain utile"]
    assert lands["total"] == deck_plans.LAND_SLOTS
    assert sum(lands["basics"].values()) == deck_plans.LAND_SLOTS - 1


def test_les_terrains_de_base_couvrent_toutes_les_couleurs_du_commandant():
    plan = deck_plans.build_deck(commander("Bi", ["B", "W"]), full_pool("h"), {}, 50, None)

    basics = plan["lands"]["basics"]
    assert set(basics) == {"Marais", "Plaine"}
    assert sum(basics.values()) == deck_plans.LAND_SLOTS


def test_le_groupe_retenu_ecarte_le_commandant_le_plus_cher():
    prix = {"Econome": 0.5, "PasCheres": 1.0, "Moyennes": 5.0, "Correct": 6.0, "Cheres": 20.0}
    commanders = [commander(name) for name in prix]
    pools = {f"oracle-{name}": full_pool(name, price=price) for name, price in prix.items()}

    result = deck_plans.plan_decks(commanders, pools, {}, max_price=50)

    retenus = sorted(plan["commander"]["name"] for plan in result["selection"]["plans"])
    assert retenus == ["Correct", "Econome", "Moyennes", "PasCheres"]
    # La comparaison, elle, montre bien les cinq, du moins cher au plus cher.
    assert [plan["commander"]["name"] for plan in result["commanders"]][0] == "Econome"
    assert result["commanders_compared"] == 5


def test_la_selection_imposee_est_respectee():
    commanders = [commander(f"C{index}") for index in range(5)]
    pools = {f"oracle-C{index}": full_pool(f"m{index}") for index in range(5)}

    result = deck_plans.plan_decks(commanders, pools, {}, 50,
                                   chosen_oracle_ids=["oracle-C4", "oracle-C0"])

    assert result["selection_forced"] is True
    assert sorted(plan["commander"]["name"] for plan in result["selection"]["plans"]) == ["C0", "C4"]


def test_sans_donnees_edhrec_on_le_dit():
    result = deck_plans.plan_decks([commander()], {}, {}, 50)

    assert "EDHREC" in result["error"]
    assert result["selection"] is None


def test_sans_achat_ne_propose_que_ce_qu_on_possede():
    # « Que puis-je monter ce soir sans rien acheter » : une carte absente de la
    # collection ne doit pas entrer dans la liste, même à 0,50 € — sinon la page
    # répond à une autre question que celle posée.
    possedees = {f"n-{RAMP}-{i}" for i in range(5)} | {f"n-neutre-{i}" for i in range(10)}
    pool = full_pool("n", owned_names=possedees)
    available = {f"oracle-{name}": 1 for name in possedees}

    plan = deck_plans.build_deck(commander(), pool, available, 50, None, owned_only=True)

    assert plan["to_buy"] == []
    assert plan["cost_eur"] == 0
    assert plan["core_size"] == len(possedees)
    assert all(item["owned"] for item in plan["core"])


def test_sans_achat_un_noyau_incomplet_est_dit_tel_quel():
    # Le noyau peut faire moins de 63 cartes : c'est un fait sur la collection,
    # pas un échec à masquer. Le compter comme complet ferait croire à un deck
    # jouable en l'état.
    possedees = {f"m-{DRAW}-{i}" for i in range(3)}
    pool = full_pool("m", owned_names=possedees)

    plan = deck_plans.build_deck(commander(), pool, {f"oracle-{n}": 1 for n in possedees},
                                 50, None, owned_only=True)

    assert plan["core_size"] == 3
    assert plan["role_gap"] > 0


def test_le_vivier_sans_achat_s_elargit_a_la_collection():
    # Les recommandations EDHREC ne connaissent que ce que les autres jouent
    # derrière ce commandant : s'y limiter laisserait dormir la moitié de la
    # collection. L'identité de couleur reste un filtre dur.
    chef = commander("Mono", identity=["B"])
    recommandee = card("deja-conseillee")
    hors_couleur = {**card("rouge"), "color_identity": ["R"]}
    utilisable = card("possedee-noire")

    pools = deck_plans.with_owned_cards(
        {"oracle-Mono": [recommandee]}, [chef],
        [recommandee, hors_couleur, utilisable],
    )

    noms = [c["name"] for c in pools["oracle-Mono"]]
    assert noms == ["deja-conseillee", "possedee-noire"]
    # La carte venue de la collection n'a pas de taux d'inclusion : elle passe
    # donc après les conseillées, jamais devant.
    assert pools["oracle-Mono"][1]["inclusion_rate"] is None


def test_le_deck_enregistre_est_celui_affiche():
    # Ce qui part en base doit être exactement la liste montrée : commandant,
    # noyau, terrains possédés et basiques avec leur quantité. Un écart ici
    # ferait porter tous les conseils suivants sur un autre deck.
    plan = deck_plans.build_deck(commander(), full_pool("p"), {}, 50, None)
    rows = deck_plans.deck_rows(plan, {"Marais": "scryfall-Marais"})

    assert rows[0] == ("scryfall-Chef", 1, True)
    assert sum(1 for _id, _qty, chef in rows if chef) == 1
    assert len(rows) == 1 + plan["core_size"] + len(plan["lands"]["owned_nonbasic"]) + \
        len(plan["lands"]["basics"])
    basiques = [row for row in rows if row[0] == "scryfall-Marais"]
    assert basiques and basiques[0][1] == plan["lands"]["basics"]["Marais"]
