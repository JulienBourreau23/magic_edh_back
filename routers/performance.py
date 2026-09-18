from fastapi import APIRouter, Query

import db.performance as performance_db

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("")
def ranking(limit: int = Query(default=10, ge=1, le=50)):
    """
    Le classement mesuré, tel qu'il a été calculé la dernière fois.

    Lecture seule : le calcul dure plusieurs minutes et vit dans
    `scripts/rank_commanders.py`. Le déclencher ici se ferait couper par
    Cloudflare bien avant la fin.
    """
    return performance_db.ranking(limit)
