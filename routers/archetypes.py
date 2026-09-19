"""
routers/archetypes.py — le catalogue des archétypes, et l'article de chacun.

Deux écrans, deux questions. La liste répond à « qu'est-ce qui se joue dans ce
format » ; l'article répond à « comment ça marche, qui le pilote, et
qu'est-ce que ça me coûterait ».

C'est la seule page du projet qui parle de cartes qu'on ne possède pas **et**
de commandants qu'on ne possède pas : toutes les autres partent de la
collection. Une page de découverte qui n'irait pas au-delà ne ferait rien
découvrir — mais le chiffrage, lui, reste ancré sur la collection réelle, sans
quoi « ça me coûterait » n'aurait aucun sens.
"""
from fastapi import APIRouter, HTTPException, Query

import db.archetypes as archetypes_db
import services.card_images as card_images
from services import archetype_notes
from services.suggestions import DEFAULT_MAX_PRICE_EUR

router = APIRouter(prefix="/archetypes", tags=["archetypes"])

FORMATS = tuple(archetypes_db.LEGALITY_COLUMNS)

CATALOGUE_ABSENT = ("Aucun archétype en base : lance "
                    "`python scripts/sync_archetypes.py`.")


def _check_format(format: str) -> str:
    if format not in FORMATS:
        raise HTTPException(400, f"Format inconnu : {', '.join(FORMATS)}")
    return format


@router.get("")
def list_archetypes(format: str = Query(default="commander", pattern="^(commander|duel)$")):
    """
    Le catalogue, du plus joué au moins joué.

    Les alias partent avec la liste parce que **la recherche se fait dans le
    navigateur** : le catalogue tient en une réponse, et taper « superfriends »
    doit trouver « Planeswalkers », qui est le nom d'EDHREC. Une requête par
    frappe pour cent quatre-vingts lignes déjà chargées serait du gaspillage.
    """
    rows = archetypes_db.list_all(format)
    catalogue = []
    for row in rows:
        note = archetype_notes.note_for(row["slug"])
        catalogue.append({
            **row,
            # Le principe part avec la liste : il rend le catalogue lisible
            # sans ouvrir chaque article, et il est déjà en mémoire.
            "principle": note["principle"] if note else None,
            "aliases": note["aliases"] if note else [],
        })
    return {"archetypes": catalogue,
            "documented": sum(1 for entry in catalogue if entry["principle"]),
            "error": None if rows else CATALOGUE_ABSENT}


@router.get("/{slug}")
def get_archetype(slug: str,
                  format: str = Query(default="commander", pattern="^(commander|duel)$"),
                  max_price: float = Query(default=DEFAULT_MAX_PRICE_EUR, gt=0)):
    """
    L'article : le principe, les commandants qui le pilotent, les cartes.

    `ensure_images` ne porte que sur les commandants et les trois sections mises
    en avant — une trentaine de visuels. Le catalogue complet en compte plus de
    trois cents, et les rapatrier six par six ferait attendre le premier
    affichage une vingtaine de secondes pour des cartes qu'on ne regardera pas.
    C'est la même règle que `/must-have` : au-delà de quelques dizaines
    d'images, on laisse Scryfall servir et le navigateur charger à la demande.
    """
    _check_format(format)
    archetype = archetypes_db.get(slug)
    if archetype is None:
        raise HTTPException(404, CATALOGUE_ABSENT if not archetypes_db.has_data()
                            else f"Archétype inconnu : {slug}")

    commanders = archetypes_db.commanders_for(slug, format, max_price=max_price)
    cards = archetypes_db.cards_for(slug, format)

    card_images.ensure_images(commanders)
    card_images.ensure_images([card for card in cards
                               if card["section"] in archetypes_db.HEADLINE_SECTIONS])

    return {
        "archetype": archetype,
        # Nul pour un archétype non décrit : l'interface montre alors les
        # chiffres sans inventer d'avis.
        "note": archetype_notes.note_for(slug),
        "commanders": commanders,
        "cards": cards,
        "core_slots": archetypes_db.CORE_SLOTS,
        "headline_sections": list(archetypes_db.HEADLINE_SECTIONS),
        "max_price": max_price,
        "format": format,
    }
