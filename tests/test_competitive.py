"""
Construction d'un deck compétitif. Ce qui est vérifié ici, ce sont les règles
qu'on ne voit pas sur l'écran : les quotas par type, la courbe de mana, et le
fait qu'un achat proposé remplace une carte précise — trois achats qui évincent
tous la même carte feraient croire à trois gains alors qu'il n'y en a qu'un.

La banlist et l'identité de couleur, elles, sont appliquées en SQL : elles sont
couvertes par `test_competitive_pool.py`, qui a besoin de la base.
"""
from services.competitive import (choose_nonlands, curve_of, land_package,
                                  upgrades, _type_of)


def carte(nom: str, *, type_line: str = "Creature — Phyrexian", cmc: int = 2,
          theme: float = 0.5, commander: float = 0.0, owned: int = 1,
          prix: float | None = 1.0, rang: int = 500) -> dict:
    return {"oracle_id": f"oracle-{nom}", "scryfall_id": f"sid-{nom}", "name": nom,
            "name_fr": None, "type_line": type_line, "cmc": cmc, "mana_cost": "{1}{G}",
            "theme_rate": theme, "commander_rate": commander, "owned_quantity": owned,
            "price_eur": prix, "edhrec_rank": rang, "image_uri": None,
            "image_downloaded": False, "categories": [], "color_identity": ["G"],
            "game_changer": False}


def test_le_type_qui_compte_est_le_premier_trouve():
    # Une carte artefact-créature occupe un seul emplacement, comme dans le
    # camembert d'EDHREC qui ne compte jamais une carte deux fois.
    assert _type_of(carte("x", type_line="Artifact Creature — Golem")) == "Creature"
    assert _type_of(carte("x", type_line="Legendary Land")) == "Land"
    assert _type_of(carte("x", type_line="Instant")) == "Instant"


def test_les_quotas_par_type_sont_respectes():
    pool = ([carte(f"bete{i}", type_line="Creature — Beast") for i in range(10)]
            + [carte(f"choc{i}", type_line="Instant") for i in range(10)])
    chosen = choose_nonlands(pool, {"Creature": 3, "Instant": 2}, {}, slots=5)

    types = [_type_of(card) for card in chosen]
    assert types.count("Creature") == 3
    assert types.count("Instant") == 2


def test_la_courbe_est_respectee_quand_le_vivier_le_permet():
    pool = ([carte(f"un{i}", cmc=1) for i in range(5)]
            + [carte(f"six{i}", cmc=6) for i in range(5)])
    chosen = choose_nonlands(pool, {"Creature": 4}, {1: 3, 6: 1}, slots=4)

    curve = curve_of(chosen)
    assert curve[1] == 3 and curve[6] == 1


def test_un_vivier_trop_etroit_remplit_quand_meme():
    # Un deck de 99 cartes vaut mieux qu'un deck de 84 parfaitement galbé : les
    # passages de relâche existent pour ça.
    pool = [carte(f"bete{i}", cmc=4) for i in range(6)]
    chosen = choose_nonlands(pool, {"Creature": 6}, {1: 5, 2: 1}, slots=6)
    assert len(chosen) == 6


def test_la_carte_la_plus_jouee_passe_devant():
    pool = [carte("rare", theme=0.1), carte("staple", theme=0.9)]
    chosen = choose_nonlands(pool, {"Creature": 1}, {}, slots=1)
    assert chosen[0]["name"] == "staple"


def test_chaque_achat_remplace_une_carte_differente():
    chosen = [carte(f"tiede{i}", theme=0.2) for i in range(3)]
    pool = chosen + [carte(f"mieux{i}", theme=0.8, owned=0, prix=5.0) for i in range(3)]

    proposals = upgrades(pool, chosen, max_price=50)
    remplaces = [item["replace"]["name"] for item in proposals]
    assert len(remplaces) == len(set(remplaces)) == 3


def test_un_achat_hors_budget_ou_moins_joue_n_est_pas_propose():
    chosen = [carte("tenant", theme=0.5)]
    pool = chosen + [
        carte("trop_cher", theme=0.9, owned=0, prix=80.0),
        carte("moins_joue", theme=0.1, owned=0, prix=1.0),
        carte("sans_prix", theme=0.9, owned=0, prix=None),
    ]
    assert upgrades(pool, chosen, max_price=50) == []


def test_la_manabase_prend_les_terrains_possedes_puis_des_basiques():
    pool = [carte("Terrain utile", type_line="Land", cmc=0, owned=1),
            carte("Terrain non possédé", type_line="Land", cmc=0, owned=0)]
    noyau = [carte("sort", cmc=2)]
    commandant = {**carte("Chef", cmc=4), "color_identity": ["G", "W"]}

    plan = land_package(pool, slots=36, identity=["G", "W"],
                        nonland_cards=noyau, commander=commandant)

    assert [land["name"] for land in plan["nonbasic"]] == ["Terrain utile"]
    assert plan["total"] == 36
    assert sum(plan["basics"].values()) == 35
