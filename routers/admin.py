from fastapi import APIRouter, Query

from services import edhrec

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/sync-edhrec")
def sync_edhrec(
    include_decks: bool = Query(default=False, description="inclure les commandants des decks"),
    delay: float = Query(default=edhrec.DEFAULT_DELAY_SECONDS, ge=0.2, le=10),
):
    """
    Déclenche la récupération EDHREC et renvoie un résumé.

    Synchrone volontairement : quelques dizaines de commandants au plus, donc
    moins d'une minute, et l'ordonnanceur (Kestra) obtient un vrai code de
    retour plutôt qu'un « accepté » sans garantie. Le plancher sur `delay`
    empêche de marteler un site communautaire gratuit depuis un planificateur.
    """
    return edhrec.sync(include_decks=include_decks, delay=delay)
