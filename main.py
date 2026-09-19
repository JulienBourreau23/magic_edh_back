"""
main.py — Magic EDH API
"""
import os
from contextlib import asynccontextmanager

import anyio.to_thread
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import CARD_IMAGES_DIR, CORS_ORIGINS, DB_POOL_MAX
from db.core import close_pool
from auth import require_auth
from routers import (admin, auth, balance, budget_lands, build, cards, collection,
                     competitive, deck_ideas,
                     deck_plans, decks, matchup, must_have, performance, videos,
                     wishlist)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Les endpoints synchrones tournent dans le threadpool anyio (40 threads
    # par défaut) et empruntent chacun une connexion : le brider à la taille
    # du pool évite d'épuiser celui-ci sous charge.
    anyio.to_thread.current_default_thread_limiter().total_tokens = DB_POOL_MAX
    yield
    close_pool()


app = FastAPI(title="Magic EDH API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(CARD_IMAGES_DIR, exist_ok=True)
app.mount("/card-images", StaticFiles(directory=CARD_IMAGES_DIR), name="card-images")


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router)

# Application personnelle : tout le reste exige un jeton. Restent publics
# `/health` (sonde) et `/card-images` (visuels Scryfall, déjà publics à la
# source, et les servir ne fait pas grossir le disque).
protected = [Depends(require_auth)]
app.include_router(decks.router, dependencies=protected)
app.include_router(cards.router, dependencies=protected)
app.include_router(matchup.router, dependencies=protected)
app.include_router(collection.router, dependencies=protected)
app.include_router(balance.router, dependencies=protected)
app.include_router(deck_ideas.router, dependencies=protected)
app.include_router(deck_plans.router, dependencies=protected)
app.include_router(competitive.router, dependencies=protected)
app.include_router(wishlist.router, dependencies=protected)
app.include_router(must_have.router, dependencies=protected)
app.include_router(build.router, dependencies=protected)
app.include_router(budget_lands.router, dependencies=protected)
app.include_router(videos.router, dependencies=protected)
app.include_router(performance.router, dependencies=protected)
app.include_router(admin.router, dependencies=protected)
