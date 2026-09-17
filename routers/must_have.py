from fastapi import APIRouter, Query

from services import must_have as must_have_service

router = APIRouter(prefix="/must-have", tags=["must-have"])


@router.get("")
def list_must_have(
    format: str = Query(default="commander", pattern="^(commander|duel)$"),
    max_price: float = Query(default=must_have_service.DEFAULT_MAX_PRICE_EUR, gt=0),
):
    """
    Les cartes les plus jouées de chaque type, achetables sous le plafond.

    Pas d'appel à `card_images.ensure_images` ici, contrairement aux écrans qui
    montrent des vignettes : la page couvre huit types à cinquante cartes, donc
    près de quatre cents visuels à rapatrier six par six au premier
    chargement — une vingtaine de secondes d'attente et autant de requêtes chez
    Scryfall, pour un écran qui se lit en tableau. Le front retombe sur l'URL
    Scryfall comme partout ailleurs.
    """
    return must_have_service.must_have(format=format, max_price=max_price)
