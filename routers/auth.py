from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import create_token, require_auth, verify_credentials
from config import JWT_EXPIRE_DAYS

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(payload: LoginRequest):
    if not verify_credentials(payload.username, payload.password):
        # Message volontairement identique pour un nom inconnu et un mauvais
        # mot de passe : inutile d'indiquer lequel des deux est faux.
        raise HTTPException(401, "Identifiants invalides")
    return {"token": create_token(payload.username), "expires_in_days": JWT_EXPIRE_DAYS}


@router.get("/me")
def me(username: str = Depends(require_auth)):
    """Permet au front de savoir si le jeton stocké est encore valable."""
    return {"username": username}
