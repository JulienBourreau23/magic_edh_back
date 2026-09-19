"""
L'étape facultative « choisir l'archétype avant le commandant ».

L'erreur que ces tests guettent est silencieuse : une liste qui annonce suivre
l'archétype demandé tout en restant classée sur autre chose. Rien ne lève, rien
ne s'affiche de travers — on choisit simplement le mauvais commandant.

Aucune base ici : `rank_commanders` et `archetypes` ne font que croiser deux
lectures, faites une seule fois par le routeur.
"""
from db.themes import ALL_THEMES_SLUG
from services.competitive import archetypes, rank_commanders


def commandant(nom: str) -> dict:
    return {"oracle_id": f"oracle-{nom}", "name": nom, "name_fr": None}


def score(commandant: str, slug: str, label: str, *, reachable: float,
          owned: int = 40, ideal: float = 30.0, decks: int = 1000) -> dict:
    return {"commander_oracle_id": f"oracle-{commandant}", "theme_slug": slug,
            "label": label, "deck_count": decks, "owned_cards": owned,
            "score": reachable / ideal, "reachable": reachable}


# Atraxa monte mieux le superfriends, Ellivère mieux l'aura — mais sur l'aura,
# c'est Ellivère qui l'emporte alors qu'Atraxa domine le classement général.
SCORES = [
    score("atraxa", "superfriends", "Superfriends", reachable=29.0),
    score("atraxa", "auras", "Auras", reachable=12.0),
    score("atraxa", ALL_THEMES_SLUG, "Toutes stratégies", reachable=22.0),
    score("ellivere", "auras", "Auras", reachable=20.0, owned=51, decks=400),
    score("ellivere", ALL_THEMES_SLUG, "Toutes stratégies", reachable=18.0),
]
COMMANDANTS = [commandant("atraxa"), commandant("ellivere")]


def test_sans_archetype_chacun_est_juge_sur_son_meilleur():
    classement = rank_commanders(COMMANDANTS, SCORES)

    assert [entry["name"] for entry in classement] == ["atraxa", "ellivere"]
    assert classement[0]["best_theme"]["slug"] == "superfriends"
    assert classement[0]["selected_theme"] is None


def test_l_archetype_demande_decide_le_classement():
    # Le piège : Atraxa gagne le classement général mais pas celui-ci. Un tri
    # resté sur `best_theme` la mettrait en tête sans rien dire.
    classement = rank_commanders(COMMANDANTS, SCORES, "auras")

    assert [entry["name"] for entry in classement] == ["ellivere", "atraxa"]
    assert classement[0]["selected_theme"]["consensus"] == 20.0
    assert classement[0]["selected_theme"]["cards_usable"] == 51


def test_un_commandant_qui_ne_joue_pas_l_archetype_sort_de_la_liste():
    classement = rank_commanders(COMMANDANTS, SCORES, "superfriends")
    assert [entry["name"] for entry in classement] == ["atraxa"]


def test_le_meilleur_archetype_reste_visible_quand_il_differe():
    # Choisir « auras » sur Atraxa est permis, mais l'écran doit pouvoir dire
    # qu'un autre plan la servirait mieux.
    atraxa = rank_commanders(COMMANDANTS, SCORES, "auras")[1]
    assert atraxa["best_theme"]["slug"] == "superfriends"
    assert atraxa["selected_theme"]["slug"] == "auras"


def test_un_commandant_sans_donnees_edhrec_reste_affiche():
    classement = rank_commanders(COMMANDANTS + [commandant("inconnu")], SCORES)

    assert [entry["name"] for entry in classement] == ["atraxa", "ellivere", "inconnu"]
    assert classement[-1]["best_theme"] is None


def test_la_liste_des_archetypes_ignore_l_agregat():
    # « Toutes stratégies » n'est pas une stratégie : le proposer comme filtre
    # reviendrait à ne rien filtrer.
    slugs = [entry["slug"] for entry in archetypes(COMMANDANTS, SCORES)]
    assert ALL_THEMES_SLUG not in slugs
    assert slugs == ["superfriends", "auras"]


def test_chaque_archetype_porte_son_meilleur_commandant():
    auras = next(entry for entry in archetypes(COMMANDANTS, SCORES)
                 if entry["slug"] == "auras")

    assert auras["best"]["name"] == "ellivere"
    assert auras["commanders"] == 2
    # Somme des decks recensés chez les commandants possédés, pas la
    # popularité de l'archétype dans le format.
    assert auras["deck_count"] == 1400


def test_un_archetype_d_un_commandant_non_possede_n_est_pas_propose():
    # `theme_scores` couvre aussi les commandants d'un deck enregistré sans
    # être en collection : les proposer mènerait à un écran vide.
    scores = SCORES + [score("etranger", "stax", "Stax", reachable=40.0)]
    slugs = [entry["slug"] for entry in archetypes(COMMANDANTS, scores)]
    assert "stax" not in slugs
