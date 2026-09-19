"""
services/bracket_rules.py — le système de brackets, tel qu'il est écrit et tel
que le site le constate.

Deux registres qui ne doivent pas se confondre, et la page les sépare :

- **la règle**, publiée par le Commander Format Panel. C'est du texte, il n'en
  existe aucune version machine, et il est donc recopié ici à la main — comme
  les notes d'archétypes, et pour la même raison : ce n'est ni un compte ni un
  taux, donc rien ne peut le calculer ;
- **ce que le site en constate**, qui est du code — `deck_analysis.bracket_estimate`.

Le lien entre les deux n'est pas recopié mais **exécuté** : chaque critère
porte un mini-deck de démonstration qu'on passe au vrai estimateur, et c'est sa
réponse qui s'affiche. Recopier « 4 Game Changers font un bracket 4 » dans un
texte l'aurait laissé dériver le jour où le seuil change ; ici la page suit le
code, ou elle se trompe en même temps que lui — ce qu'un test attrape.
"""
from services import card_categories as categories
from services.deck_analysis import bracket_estimate

BRACKETS = [
    {
        "level": 1,
        "name": "Exhibition",
        "principle": "Le deck n'est pas là pour gagner. Thème, nostalgie, "
                     "contrainte de construction : la partie est le prétexte.",
        "rules": [
            "aucun Game Changer",
            "aucun combo infini à deux cartes",
            "aucune destruction de terrains de masse",
            "aucun tour supplémentaire",
        ],
    },
    {
        "level": 2,
        "name": "Core",
        "principle": "Le niveau d'un deck préconstruit sorti de sa boîte. "
                     "La partie se décide tard, personne ne verrouille rien.",
        "rules": [
            "aucun Game Changer",
            "aucun combo infini à deux cartes",
            "aucune destruction de terrains de masse",
            "des tours supplémentaires isolés, jamais enchaînés",
            "peu de tuteurs",
        ],
    },
    {
        "level": 3,
        "name": "Upgraded",
        "principle": "Un deck travaillé, avec quelques pièces fortes et un "
                     "plan de jeu assumé, mais qui laisse la partie se jouer.",
        "rules": [
            "jusqu'à trois Game Changers",
            "un combo à deux cartes accepté s'il est un plan de « fin de partie »",
            "aucune destruction de terrains de masse",
            "des tours supplémentaires isolés, jamais enchaînés",
            "les tuteurs sont admis",
        ],
    },
    {
        "level": 4,
        "name": "Optimized",
        "principle": "Le deck le plus fort qu'on sache construire, sans autre "
                     "limite que la banlist du format.",
        "rules": [
            "autant de Game Changers qu'on veut",
            "combos, destruction de terrains, tours enchaînés : tout est permis",
        ],
    },
    {
        "level": 5,
        "name": "cEDH",
        "principle": "Comme le 4, mais joué pour gagner dans un métagame de "
                     "tournoi : le choix des cartes répond à ce que la table joue.",
        "rules": [
            "aucune restriction de construction",
            "ce qui change, c'est l'intention et le métagame, pas la liste permise",
        ],
    },
]


def _carte(nom: str, *, game_changer: bool = False, categories_: list[str] | None = None) -> dict:
    """Une carte de démonstration : le strict nécessaire pour l'estimateur."""
    return {"name": nom, "name_fr": None, "scryfall_id": f"demo-{nom}",
            "is_commander": False, "quantity": 1, "game_changer": game_changer,
            "categories": categories_ or []}


# Chaque critère, avec le deck minimal qui le déclenche. C'est ce deck qu'on
# passe à l'estimateur pour montrer sa réponse, plutôt que de la recopier.
CRITERIA = [
    {
        "key": "game_changers",
        "label": "Game Changers",
        "official": "Zéro aux brackets 1 et 2, jusqu'à trois au bracket 3, "
                    "sans limite au-delà. Le commandant compte s'il est lui-même "
                    "sur la liste.",
        "measured": "Constaté exactement : c'est une liste officielle, publiée "
                    "par Scryfall et rapatriée à chaque synchronisation.",
        "demo": [_carte("Un Game Changer", game_changer=True)],
        "demo_label": "un deck avec 1 Game Changer",
    },
    {
        "key": "game_changers_4",
        "label": "Game Changers (quatre ou plus)",
        "official": "Au-delà de trois, le deck sort du bracket 3.",
        "measured": "Même comptage, seuil franchi.",
        "demo": [_carte(f"Game Changer {i}", game_changer=True) for i in range(4)],
        "demo_label": "un deck avec 4 Game Changers",
    },
    {
        "key": "mass_land_denial",
        "label": "Destruction de terrains de masse",
        "official": "Interdite aux brackets 1, 2 et 3. C'est le critère le "
                    "plus punitif du système.",
        "measured": "Constatée dans le texte oracle, en retirant d'abord les "
                    "clauses qui « épargnent » les terrains — sans quoi Elspeth "
                    "Tirel (« all other permanents except for lands ») tomberait "
                    "avec les vrais Armageddon. Un terrain chacun ne compte pas : "
                    "Tremble prive d'une pose, pas d'une manabase.",
        "demo": [_carte("Armageddon", categories_=[categories.MASS_LAND_DENIAL])],
        "demo_label": "un deck avec 1 destruction de terrains de masse, sans aucun Game Changer",
    },
    {
        "key": "extra_turns",
        "label": "Tours supplémentaires",
        "official": "Le bracket 1 les interdit tout court. Les brackets 2 et 3 "
                    "n'interdisent que de les enchaîner.",
        "measured": "Seule l'interdiction du bracket 1 est constatable : "
                    "« enchaîner » ne se lit pas dans une liste de cartes. On "
                    "plafonne donc au bracket 2 sans prétendre distinguer un "
                    "Time Warp isolé d'un moteur de tours.",
        "demo": [_carte("Time Warp", categories_=[categories.EXTRA_TURN])],
        "demo_label": "un deck avec 1 tour supplémentaire, sans rien d'autre",
    },
    {
        "key": "combos",
        "label": "Combos infinis à deux cartes",
        "official": "Interdits aux brackets 1 et 2. Acceptés au bracket 3 "
                    "s'ils constituent un plan de « fin de partie ».",
        "measured": "Un combo ne se lit pas dans le texte d'une carte : il naît "
                    "de l'interaction. Il est donc constaté contre le catalogue "
                    "Commander Spellbook, et seuls comptent ceux qui gagnent "
                    "la partie sur place. Mana infini ou pioche infinie "
                    "demandent une troisième carte : affichés, mais sans effet "
                    "sur le plancher.",
        "demo": [],
        "demo_combos": [{"wins_outright": True}],
        "demo_label": "un deck avec 1 combo à deux cartes qui gagne la partie",
    },
]

# Ce que le texte officiel évoque sans qu'on puisse le constater, et ce qu'on
# refuse de faire peser. Les énumérer vaut mieux que de les passer sous
# silence : c'est là que le chiffre du site et l'avis d'un joueur divergeront.
NOT_MEASURED = [
    {
        "label": "Le stax",
        "why": "Ce n'est pas un critère officiel, malgré la tentation : "
               "Winter Orb gêne autant qu'un Armageddon, mais le système ne le "
               "nomme nulle part. Le faire peser inventerait une règle et ferait "
               "dériver tous les brackets. Il est affiché en signal brut.",
    },
    {
        "label": "La densité de tuteurs",
        "why": "Le texte officiel en parle — « peu de tuteurs » au bracket 2 — "
               "sans fixer de seuil. Sans nombre, il n'y a pas de plancher à en "
               "tirer : le compte est affiché, il ne décide de rien.",
    },
    {
        "label": "« Plan de fin de partie »",
        "why": "Au-dessus du bracket 3, un combo à deux cartes doit rester un "
               "plan de fin de partie, et le texte ne définit pas le terme. On "
               "renvoie le mana total du combo, à comparer au ramp du deck, sans "
               "trancher à ta place.",
    },
    {
        "label": "Des tours supplémentaires enchaînés",
        "why": "Une liste de cartes ne dit pas si les tours s'enchaînent. Le "
               "plancher s'arrête donc au bracket 2.",
    },
]


def describe() -> dict:
    """
    Les brackets, les critères, et la réponse réelle de l'estimateur sur le
    deck minimal de chaque critère.
    """
    criteria = []
    for critere in CRITERIA:
        estimate = bracket_estimate(critere["demo"], critere.get("demo_combos"))
        criteria.append({
            "key": critere["key"],
            "label": critere["label"],
            "official": critere["official"],
            "measured": critere["measured"],
            "demonstration": {
                "deck": critere["demo_label"],
                "verdict": estimate["label"],
                "min": estimate["min"],
                "max": estimate["max"],
                "reasons": estimate["floor_reasons"],
            },
        })

    # Le repère du bas : un deck qui ne déclenche rien.
    neutre = bracket_estimate([_carte("Une carte ordinaire")])
    return {
        "brackets": BRACKETS,
        "criteria": criteria,
        "baseline": {"deck": "un deck qui ne déclenche aucun critère",
                     "verdict": neutre["label"]},
        "not_measured": NOT_MEASURED,
    }
