"""
services/archetype_notes.py — le principe de chaque archétype, écrit à la main.

**C'est le seul contenu rédigé du projet, et il l'est par nécessité.** Les
pages d'EDHREC portent un champ `description` : il est vide, sur les pages
archétypes comme sur les pages commandants. Personne ne publie « ce que fait un
deck aristocrats » sous une forme exploitable — ce n'est ni un compte ni un
taux, donc rien ici ne peut le calculer, et le faire produire par un modèle de
langage reviendrait à inventer ce que le projet refuse d'inventer partout
ailleurs.

D'où la règle de lecture, affichée à l'écran : **les textes sont d'un joueur,
les chiffres sont mesurés.** Les deux ne se mélangent pas. Aucun nombre n'entre
dans ces notes — pas de « environ trente créatures », pas de « il faut dix
sources » : ces grandeurs-là sont déjà calculées ailleurs, et les écrire deux
fois les ferait diverger.

Tous les archétypes ne sont pas décrits, et c'est assumé : le catalogue en
recense cent quatre-vingts, dont une longue traîne que personne ne cherche. Un
archétype sans note affiche ses chiffres sans faire semblant d'avoir un avis.

`aliases` sert la recherche, exactement comme dans `land_cycles` : EDHREC range
le superfriends sous « planeswalkers », et un joueur francophone tape
« jetons », « pioche » ou « contrôle ». Sans ces mots, la moitié des recherches
ne trouvent rien alors que l'archétype existe.
"""

# slug EDHREC -> principe, plan de victoire, piège. Trois champs parce que ce
# sont les trois questions qu'on se pose devant un archétype inconnu : qu'est-ce
# que ça fait, comment ça gagne, et qu'est-ce qui me tombera dessus.
NOTES: dict[str, dict] = {
    "tokens": {
        "aliases": ["jetons", "go wide", "large"],
        "principle": "Fabriquer beaucoup de créatures d'un coup plutôt qu'une "
                     "grosse. Chaque sort laisse deux ou trois corps derrière "
                     "lui, et des permanents les doublent au passage.",
        "wins": "Par l'attaque en masse, ou par un effet qui transforme le "
                "nombre en dégâts sans passer par le combat.",
        "watch": "Un seul board wipe efface une demi-heure de travail. La "
                 "parade est de garder de quoi rejouer, pas de surengager.",
    },
    "plus-1-plus-1-counters": {
        "aliases": ["compteurs", "+1/+1", "counters"],
        "principle": "Poser des marqueurs sur les créatures et les multiplier. "
                     "Les cartes qui en distribuent se renforcent l'une "
                     "l'autre, ce qui rend le deck très dense en synergies.",
        "wins": "Des créatures démesurées assez tôt pour que l'adversaire "
                "n'ait pas encore de réponse propre.",
        "watch": "Tout est sur les créatures : un removal ciblé emporte les "
                 "marqueurs avec. C'est l'archétype où l'indestructible et les "
                 "protections valent le plus cher.",
    },
    "combo": {
        "aliases": ["combos", "boucle", "infini"],
        "principle": "Chercher deux ou trois cartes précises qui, ensemble, "
                     "font une boucle. Le reste du deck ne sert qu'à les "
                     "trouver et à survivre en attendant.",
        "wins": "D'un coup, souvent sans attaquer : la boucle produit assez de "
                "dégâts, de pioche ou de jetons pour finir le tour même.",
        "watch": "C'est le critère le plus surveillé par le système de "
                 "brackets. Un combo à deux cartes qui gagne sur place ferme "
                 "les brackets 1 et 2, quel que soit le reste de la liste.",
    },
    "artifacts": {
        "aliases": ["artefacts"],
        "principle": "Empiler des artefacts et récompenser leur nombre. Ils "
                     "sont incolores, donc l'archétype se monte dans n'importe "
                     "quelle identité de couleur.",
        "wins": "Par une créature qui grandit avec le nombre d'artefacts, ou "
                "par un moteur qui les recycle plus vite que l'adversaire ne "
                "les détruit.",
        "watch": "Les effets qui détruisent tous les artefacts sont joués par "
                 "tout le monde, et ils touchent aussi la manabase quand elle "
                 "repose sur des rochers de mana.",
    },
    "aggro": {
        "aliases": ["agressif", "rush"],
        "principle": "Attaquer tôt et sans relâche, avec des créatures bon "
                     "marché. La courbe de mana est basse, et le deck préfère "
                     "une menace de plus à une réponse.",
        "wins": "Avant que la table n'ait installé son jeu : la fenêtre est "
                "étroite et se referme vite en multijoueur.",
        "watch": "Trois adversaires, c'est trois fois plus de points de vie à "
                 "entamer. L'aggro pur est plus à l'aise en duel qu'à quatre.",
    },
    "spellslinger": {
        "aliases": ["sorts", "prowess", "magie"],
        "principle": "Jouer beaucoup d'éphémères et de rituels, et des "
                     "permanents qui se déclenchent chaque fois qu'on en lance "
                     "un. Les créatures sont peu nombreuses, souvent des "
                     "moteurs plutôt que des attaquants.",
        "wins": "Par accumulation de déclenchements, ou par un gros sort "
                "final rendu payable par le ramp et la pioche.",
        "watch": "Sans ses moteurs, le deck n'a plus qu'une main de cartes qui "
                 "ne font rien seules. Il lui faut de quoi les protéger.",
    },
    "lifegain": {
        "aliases": ["gain de vie", "soin"],
        "principle": "Gagner des points de vie et s'en servir comme d'une "
                     "ressource, pas comme d'un matelas : chaque gain "
                     "déclenche quelque chose.",
        "wins": "Par les déclenchements plutôt que par le total de vie, qui ne "
                "fait gagner aucune partie à lui seul.",
        "watch": "Gagner de la vie sans rien en faire ne fait que retarder la "
                 "défaite, et attire l'attention de toute la table.",
    },
    "reanimator": {
        "aliases": ["réanimation", "cimetière", "reanimation"],
        "principle": "Mettre très tôt une créature énorme au cimetière, puis "
                     "la ramener en jeu pour une fraction de son coût. "
                     "Défausse et auto-meulage sont des accélérateurs, pas des "
                     "accidents.",
        "wins": "Par une menace hors de prix posée avec plusieurs tours "
                "d'avance sur le mana disponible.",
        "watch": "Les cartes qui exilent les cimetières coupent le plan net. "
                 "Un deck de réanimation sans plan B se fait éteindre par une "
                 "seule carte.",
    },
    "aristocrats": {
        "aliases": ["sacrifice", "aristocrates", "drain"],
        "principle": "Sacrifier ses propres créatures volontairement, et "
                     "encaisser un profit à chaque mort. Les jetons servent de "
                     "carburant.",
        "wins": "Par des pertes de vie répétées qui ignorent les bloqueurs — "
                "le combat n'est pas nécessaire.",
        "watch": "Il faut trois pièces qui fonctionnent ensemble : de quoi "
                 "sacrifier, de quoi mourir, et de quoi en profiter. Il en "
                 "manque souvent une.",
    },
    "control": {
        "aliases": ["contrôle", "controle"],
        "principle": "Répondre plutôt qu'agir : contresorts, removal, board "
                     "wipes, et une pioche qui permet d'avoir toujours la "
                     "bonne réponse.",
        "wins": "Tard, par une seule menace posée quand plus personne n'a de "
                "quoi la traiter.",
        "watch": "En multijoueur, une réponse pour trois adversaires ne suffit "
                 "pas. Le contrôle pur y est plus difficile qu'en duel, et il "
                 "s'y fait détester.",
    },
    "burn": {
        "aliases": ["brûlure", "dégâts directs", "brulure"],
        "principle": "Envoyer des dégâts directement, sans passer par les "
                     "créatures. Souvent doublé d'effets qui multiplient les "
                     "dégâts infligés.",
        "wins": "En visant un adversaire à la fois, ou par un effet qui frappe "
                "toute la table simultanément.",
        "watch": "Quarante points de vie par adversaire : une carte qui en "
                 "inflige trois n'est pas un plan de jeu, seulement un "
                 "accélérateur.",
    },
    "lands-matter": {
        "aliases": ["terrains", "landfall"],
        "principle": "Traiter les terrains comme des cartes de jeu : les "
                     "poser plusieurs fois par tour, les récupérer du "
                     "cimetière, les faire produire autre chose que du mana.",
        "wins": "Par une masse de mana qui rend payable ce que les autres ne "
                "peuvent pas lancer, ou par des terrains devenus créatures.",
        "watch": "C'est l'archétype que la destruction de terrains de masse "
                 "punit le plus — et elle ferme les brackets 1 à 3 à qui la "
                 "joue.",
    },
    "ramp": {
        "aliases": ["accélération", "mana", "acceleration"],
        "principle": "Produire plus de mana que le rythme normal d'un terrain "
                     "par tour, pour lancer ses sorts avec un ou deux tours "
                     "d'avance.",
        "wins": "Rarement seul : le ramp est un moyen, et le deck a besoin "
                "d'un plan à payer avec ce mana.",
        "watch": "Un deck qui accélère sans rien à lancer derrière a juste "
                 "joué des cartes qui ne font rien.",
    },
    "voltron": {
        "aliases": ["équipements", "auras", "mono-créature"],
        "principle": "Tout miser sur une créature, en général le commandant, "
                     "et l'équiper jusqu'à ce qu'elle tue en un ou deux coups.",
        "wins": "Par les dégâts de commandant : vingt et un d'une même "
                "créature suffisent, ce qui est bien moins que quarante points "
                "de vie.",
        "watch": "Un seul exil, un seul rebond, et tout l'investissement part "
                 "avec. Les protections ne sont pas optionnelles ici.",
    },
    "enchantress": {
        "aliases": ["enchantements", "enchanteresse"],
        "principle": "Jouer beaucoup d'enchantements et des créatures qui "
                     "piochent une carte à chaque fois. Le deck se remplace "
                     "tout seul pendant qu'il installe son jeu.",
        "wins": "Par accumulation : les enchantements s'empilent et deviennent "
                "difficiles à démonter, car peu de decks en détruisent.",
        "watch": "La mise en route est lente, et tout repose sur les "
                 "créatures-moteur qui piochent.",
    },
    "equipment": {
        "aliases": ["équipement", "equipement", "artefacts"],
        "principle": "Des équipements plutôt que des auras : ils survivent à "
                     "la mort de la créature équipée, ce qui rend le plan bien "
                     "plus résistant que le voltron aux auras.",
        "wins": "Par une créature récurrente et bon marché qui porte tout, "
                "souvent avec de l'évasion.",
        "watch": "Le coût d'équipement se paie chaque tour : sans réduction, "
                 "le deck passe ses tours à rattacher au lieu d'avancer.",
    },
    "midrange": {
        "aliases": ["milieu de partie", "valeur"],
        "principle": "Ni la vitesse de l'aggro ni la patience du contrôle : "
                     "des cartes qui font deux choses à la fois, et qui "
                     "gagnent l'échange à chaque fois.",
        "wins": "Par accumulation d'avantages, un échange favorable après "
                "l'autre.",
        "watch": "C'est l'archétype le plus difficile à évaluer : il n'a pas "
                 "de plan spectaculaire, donc il perd contre un deck qui a la "
                 "bonne carte au bon moment.",
    },
    "mill": {
        "aliases": ["meule", "moulin", "bibliothèque"],
        "principle": "Vider la bibliothèque de l'adversaire plutôt que ses "
                     "points de vie. En multijoueur, il faut le faire trois "
                     "fois.",
        "wins": "Par épuisement de la bibliothèque, ou en utilisant les "
                "cimetières ainsi remplis.",
        "watch": "Meuler un joueur qui joue de la réanimation l'aide au lieu "
                 "de le gêner. C'est la seule stratégie dont l'effet peut "
                 "servir la victime.",
    },
    "cedh": {
        "aliases": ["compétitif", "competitif"],
        "principle": "Le format joué au maximum de sa puissance : combos "
                     "rapides, tuteurs, contresorts, manabase optimale. Les "
                     "parties se décident en quelques tours.",
        "wins": "Par un combo protégé, presque jamais par le combat.",
        "watch": "Ce n'est pas un archétype qu'on monte à moitié : y aller "
                 "avec la moitié des cartes donne un deck plus lent qu'un "
                 "deck casual, sans son plan B.",
    },
    "treasure": {
        "aliases": ["trésors", "tresors", "artefacts"],
        "principle": "Fabriquer des jetons Trésor : du mana stocké, "
                     "sacrifiable, qui compte aussi comme artefact pour tout "
                     "ce qui les compte.",
        "wins": "Par un tour explosif où le mana accumulé permet de vider sa "
                "main d'un coup.",
        "watch": "Un Trésor dépensé est un artefact en moins : les deux "
                 "usages se disputent les mêmes jetons.",
    },
    "blink": {
        "aliases": ["clignotement", "flicker", "exil temporaire"],
        "principle": "Faire revenir ses propres créatures en jeu pour "
                     "redéclencher leurs capacités d'arrivée. Chaque créature "
                     "est un sort réutilisable.",
        "wins": "Par accumulation de valeur : pioche, removal et jetons "
                "répétés tour après tour.",
        "watch": "Sans créature à capacité d'arrivée en jeu, les effets de "
                 "clignotement sont des cartes mortes.",
    },
    "sacrifice": {
        "aliases": ["sacrifices", "aristocrats"],
        "principle": "Se débarrasser volontairement de ses permanents pour en "
                     "tirer un profit, et contourner ainsi tout ce qui "
                     "empêche de cibler ou de détruire.",
        "wins": "Par répétition, en général avec un exutoire gratuit et une "
                "créature qui revient sans cesse.",
        "watch": "Il faut un exutoire « sans coût de mana », sinon la boucle "
                 "s'arrête au troisième tour faute de mana.",
    },
    "discard": {
        "aliases": ["défausse", "defausse", "main vide"],
        "principle": "Attaquer la main de l'adversaire plutôt que son jeu : "
                     "ce qu'il n'a plus en main, il ne le jouera pas.",
        "wins": "Rarement par la défausse elle-même — elle prépare le terrain "
                "pour une menace qui ne trouvera plus de réponse.",
        "watch": "À quatre joueurs, vider une main sur trois laisse deux "
                 "adversaires intacts. C'est une stratégie bien plus forte en "
                 "duel.",
    },
    "auras": {
        "aliases": ["enchantements", "voltron"],
        "principle": "Renforcer une créature par des enchantements. Moins "
                     "résistant que l'équipement, mais nettement plus "
                     "puissant à coût égal.",
        "wins": "Par une créature devenue imblocable ou trop grosse, en "
                "quelques tours.",
        "watch": "Perdre la créature, c'est perdre toutes les auras d'un coup "
                 "— deux cartes, parfois cinq, pour un seul removal.",
    },
    "graveyard": {
        "aliases": ["cimetière", "cimetiere", "recursion"],
        "principle": "Traiter le cimetière comme une seconde main : y mettre "
                     "des cartes volontairement, et les rejouer de là.",
        "wins": "Par des cartes utilisées deux fois, ce qui rend chaque "
                "échange favorable.",
        "watch": "Les effets qui exilent les cimetières sont joués partout, "
                 "et ils sont dévastateurs ici.",
    },
    "clones": {
        "aliases": ["copies", "clone"],
        "principle": "Copier les meilleurs permanents en jeu, y compris ceux "
                     "des adversaires. Le deck n'a pas besoin d'avoir les "
                     "bonnes cartes, seulement d'attendre qu'un autre les "
                     "pose.",
        "wins": "En doublant une menace déjà décisive, souvent la sienne.",
        "watch": "Sans cible, un clone est une carte blanche : c'est un "
                 "archétype qui dépend de la table.",
    },
    "wheels": {
        "aliases": ["roues", "défausse", "pioche massive"],
        "principle": "Faire défausser et repiocher toute la table d'un coup. "
                     "Les permanents qui punissent la pioche ou la défausse "
                     "transforment l'effet symétrique en avantage unilatéral.",
        "wins": "Par les punitions déclenchées en série, pas par les cartes "
                "piochées.",
        "watch": "Sans ces permanents, on vient de donner sept cartes "
                 "fraîches à trois adversaires.",
    },
    "landfall": {
        "aliases": ["terrains", "lands matter"],
        "principle": "Déclencher un effet à chaque terrain posé, et poser "
                     "plusieurs terrains par tour.",
        "wins": "Par des tours où quatre ou cinq déclenchements s'enchaînent, "
                "pas par un seul gros effet.",
        "watch": "Le moteur s'arrête dès que la main n'a plus de terrain : la "
                 "pioche compte autant que les déclenchements.",
    },
    "storm": {
        "aliases": ["tempête", "tempete"],
        "principle": "Enchaîner les sorts dans un même tour en se finançant "
                     "par des rituels, jusqu'à ce qu'un sort final compte tout "
                     "ce qui a été lancé avant lui.",
        "wins": "En un seul tour, généralement sans jamais attaquer.",
        "watch": "Le plan tient dans une main : un contresort ou une taxe "
                 "posée au bon moment annule tout le tour.",
    },
    "stax": {
        "aliases": ["prison", "blocage", "taxes"],
        "principle": "Rendre le jeu coûteux pour tout le monde — taxes, "
                     "engagements forcés, limitations — et s'arranger pour en "
                     "souffrir moins que les autres.",
        "wins": "Lentement, en verrouillant assez la table pour qu'une menace "
                "modeste devienne suffisante.",
        "watch": "Le stax n'est pas un critère officiel de bracket, mais "
                 "il change une partie autant qu'un critère qui l'est. C'est "
                 "une conversation à avoir avant de jouer, pas après.",
    },
    "infect": {
        "aliases": ["infection", "poison", "corruption"],
        "principle": "Ne pas viser les quarante points de vie du tout : dix "
                     "marqueurs poison suffisent, et ils ne se soignent pas.",
        "wins": "Très vite, en rendant imblocable une créature à l'infect et "
                "en la renforçant.",
        "watch": "C'est l'archétype le plus détesté des tables casual, "
                 "précisément parce que le compteur adverse est plus court "
                 "qu'il n'en a l'air.",
    },
    "group-hug": {
        "aliases": ["cadeaux", "hug", "tout le monde pioche"],
        "principle": "Donner des ressources à toute la table — pioche, mana, "
                     "terrains — pour ne devenir la cible de personne.",
        "wins": "Par un retournement tardif qui exploite l'abondance offerte, "
                "sinon pas du tout.",
        "watch": "Sans condition de victoire propre, le deck a surtout aidé "
                 "quelqu'un d'autre à gagner.",
    },
    "planeswalkers": {
        "aliases": ["superfriends", "arpenteurs", "super friends"],
        "principle": "Aligner les planeswalkers et les protéger, souvent avec "
                     "des effets qui les défendent ou qui ajoutent des "
                     "marqueurs de loyauté.",
        "wins": "Par les capacités ultimes, ou par la somme des petites "
                "capacités activées chaque tour.",
        "watch": "Un planeswalkers se défend au combat, et on joue contre "
                 "trois adversaires : sans bloqueurs ni pillow-fort, ils "
                 "meurent avant leur deuxième activation.",
    },
    "extra-turns": {
        "aliases": ["tours supplémentaires", "tours en plus"],
        "principle": "Rejouer, et rejouer encore. Chaque tour supplémentaire "
                     "est une pioche, une pose de terrain et une attaque de "
                     "plus.",
        "wins": "Par enchaînement, quand un moteur rend les tours récurrents.",
        "watch": "Le bracket 1 les interdit purement et simplement, et les "
                 "brackets 2 et 3 interdisent de les enchaîner. Un seul tour "
                 "supplémentaire isolé reste jouable.",
    },
    "pillow-fort": {
        "aliases": ["forteresse", "dissuasion", "défensif"],
        "principle": "Rendre l'attaque contre soi peu rentable — taxes sur "
                     "les attaquants, empêchements, bloqueurs — pour que la "
                     "table se tape dessus ailleurs.",
        "wins": "Tard : la défense n'a jamais fait gagner une partie, elle "
                "achète le temps d'installer autre chose.",
        "watch": "Se protéger du combat ne protège de rien contre un combo, "
                 "qui n'attaque pas.",
    },
    "hatebears": {
        "aliases": ["ours", "créatures gênantes", "taxes"],
        "principle": "Des petites créatures dont chacune interdit quelque "
                     "chose. Prises une à une elles sont anodines ; ensemble "
                     "elles rendent le jeu adverse impraticable.",
        "wins": "Par le combat, pendant que les adversaires cherchent à se "
                "défaire des contraintes.",
        "watch": "Chaque créature est fragile, et la stratégie ne survit pas "
                 "à un board wipe.",
    },
    "theft": {
        "aliases": ["vol", "contrôle de créatures"],
        "principle": "Jouer avec les cartes des autres : prendre le contrôle "
                     "de leurs permanents, lancer les sorts du dessus de leur "
                     "bibliothèque.",
        "wins": "En retournant contre la table ce qu'elle a elle-même posé, "
                "souvent en sacrifiant ce qu'on a emprunté.",
        "watch": "La puissance du deck dépend entièrement de celle des "
                 "adversaires — imprévisible par construction.",
    },
    "extra-combats": {
        "aliases": ["phases de combat", "combats supplémentaires"],
        "principle": "Rejouer la phase de combat dans le même tour. Une "
                     "grosse créature devient deux ou trois attaques.",
        "wins": "Par un tour unique où les attaques cumulées dépassent "
                "largement ce qu'un seul combat aurait fait.",
        "watch": "Sans créature menaçante en jeu, un combat supplémentaire ne "
                 "vaut rien : c'est un multiplicateur, pas un plan.",
    },
    "cascade": {
        "aliases": ["cascade", "gratuit"],
        "principle": "Lancer un sort et en déclencher un second gratuitement, "
                     "de coût inférieur. La construction du deck compte "
                     "autant que les cartes : ce qui est dans la courbe "
                     "détermine ce qu'on touche.",
        "wins": "Par le volume de sorts joués pour un seul paiement.",
        "watch": "Une courbe mal réglée transforme la cascade en loterie — "
                 "chaque carte bon marché de plus dilue le résultat.",
    },
    "big-mana": {
        "aliases": ["gros mana", "ramp", "sorts chers"],
        "principle": "Produire beaucoup plus de mana que nécessaire, et s'en "
                     "servir pour lancer ce que les autres ne peuvent pas "
                     "payer.",
        "wins": "Par des sorts dont l'effet est disproportionné parce qu'ils "
                "sont supposés injouables.",
        "watch": "Le deck est vulnérable pendant toute sa montée en puissance, "
                 "et n'a souvent rien à faire des premiers tours.",
    },
}


def note_for(slug: str) -> dict | None:
    return NOTES.get(slug)


def aliases_for(slug: str) -> list[str]:
    note = NOTES.get(slug)
    return note["aliases"] if note else []
