"""
services/land_cycles.py — les cycles de terrains, constatés dans le texte oracle.

Une vidéo « terrains budget » ne recommande pas des cartes une par une : elle
recommande des **cycles** — checklands, tango, filter, pain… Chacun est une
famille de dix terrains, un par paire de couleurs, qui partagent le même texte.
C'est donc une donnée calculable : le cycle se reconnaît à son oracle, et la
carte utile pour *ta* paire de couleurs s'en déduit.

Rien n'est saisi à la main ici, sauf les motifs : la liste des cartes d'un cycle
est le résultat d'une requête, donc elle suit les sorties de sets toute seule.

**Le prix décide de l'ordre, pas la qualité supposée.** Un cycle n'est pas
« meilleur » qu'un autre dans l'absolu : un checkland est excellent dans un deck
à deux couleurs et mauvais dans un tricolore. Les libellés disent la condition,
au joueur de trancher.
"""

import re

# Chaque motif est un `ILIKE` (ou une regex quand la ponctuation compte), validé
# contre le catalogue : le compte attendu est indiqué, un écart franc signale un
# motif devenu trop large après une sortie de set.
CYCLES = [
    {
        "key": "tango",
        "label": "Tango (terrains de bataille)",
        "condition": "Arrive engagé sauf si tu contrôles deux terrains de base ou plus.",
        "pattern": "%unless you control two or more basic lands%",
        "regex": False,
    },
    {
        "key": "check",
        "label": "Checklands",
        "condition": "Arrive dégagé si tu contrôles déjà un terrain du bon type.",
        "pattern": "%enters tapped unless you control a%",
        "regex": False,
    },
    {
        "key": "slow",
        "label": "Slowlands",
        "condition": "Arrive dégagé à partir du troisième terrain posé.",
        "pattern": "%unless you control two or more other lands%",
        "regex": False,
    },
    {
        "key": "pain",
        "label": "Painlands",
        "condition": "Mana de couleur immédiat, au prix d'un point de vie.",
        "pattern": "%deals 1 damage to you%",
        "regex": False,
    },
    {
        "key": "filter",
        "label": "Filterlands",
        "condition": "Transforme un mana en deux : puissant, mais il faut déjà du mana.",
        "pattern": r"\{[WUBRG/]+\}, \{T\}: Add",
        "regex": True,
    },
    {
        "key": "horizon",
        "label": "Horizon (terrains à sacrifier)",
        "condition": "Mana de couleur contre un point de vie, et se sacrifie pour piocher.",
        "pattern": "%Pay 1 life: Add%",
        "regex": False,
    },
    {
        "key": "bounce",
        "label": "Bouncelands (Ravnica)",
        "condition": "Arrive engagé et renvoie un terrain, mais donne deux manas.",
        "pattern": "%return a land you control to its owner%",
        "regex": False,
    },
    {
        "key": "scry",
        "label": "Temples (scrylands)",
        "condition": "Arrive engagé, mais scrute 1.",
        "pattern": "%enters tapped.%scry 1%",
        "regex": False,
    },
    {
        "key": "gain",
        "label": "Terrains à gain de vie",
        "condition": "Arrive engagé, fait gagner 1 point de vie. Le moins cher de tous.",
        "pattern": "%enters tapped.%you gain 1 life%",
        "regex": False,
    },
    {
        "key": "creature",
        "label": "Terrains-créatures",
        "condition": "Devient une créature : une menace qui échappe aux board wipes.",
        "pattern": "%becomes a%creature%until end of turn%",
        "regex": False,
    },
]

CYCLES_BY_KEY = {cycle["key"]: cycle for cycle in CYCLES}

# Les mots par lesquels une vidéo francophone désigne ces cycles. Sert à
# rattacher une recommandation vidéo au cycle dont elle parle — les chapitres
# d'une vidéo s'appellent « TANGO LANDS », pas « terrains de bataille ».
ALIASES = {
    "tango": ("tango", "battle land", "terrain de bataille"),
    "check": ("checkland", "check land", "terrain de vérification"),
    "slow": ("slowland", "slow land", "terrain lent"),
    "pain": ("painland", "pain land", "terrain de douleur"),
    "filter": ("filterland", "filter land", "filtre", "odissey filter", "odyssey filter"),
    "horizon": ("horizon",),
    "bounce": ("bounceland", "bounce land", "karoo"),
    "scry": ("scryland", "scry land", "temple"),
    "gain": ("gainland", "gain land", "life land", "terrain de gain"),
    "creature": ("creatureland", "creature land", "manland", "terrain creature"),
}


def _matches(oracle_text: str, cycle: dict) -> bool:
    """
    Le même test qu'en SQL, joué en Python.

    Les motifs sont écrits une seule fois et servent aux deux côtés : classer en
    Python après une requête large évite dix balayages du catalogue, mais le
    jour où l'un des deux dériverait, les cycles changeraient de contenu sans
    que rien ne le dise.
    """
    if cycle["regex"]:
        return re.search(cycle["pattern"], oracle_text) is not None
    # `%a%b%` en ILIKE : les fragments doivent apparaître dans cet ordre.
    position = 0
    for fragment in [f for f in cycle["pattern"].split("%") if f]:
        trouve = oracle_text.lower().find(fragment.lower(), position)
        if trouve < 0:
            return False
        position = trouve + len(fragment)
    return True


def classify(card: dict) -> str | None:
    """Le cycle d'un terrain, ou None s'il n'appartient à aucun de ceux qu'on suit."""
    texte = card.get("oracle_text") or ""
    for cycle in CYCLES:
        if _matches(texte, cycle):
            return cycle["key"]
    return None


def cycle_of_text(text: str) -> str | None:
    """Le cycle qu'un titre de chapitre ou une phrase désigne, s'il en désigne un."""
    lowered = text.lower()
    for key, mots in ALIASES.items():
        if any(mot in lowered for mot in mots):
            return key
    return None
