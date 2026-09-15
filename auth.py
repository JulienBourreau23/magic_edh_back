"""
auth.py — authentification mono-utilisateur.

L'application est personnelle : il n'y a **pas d'inscription et pas de table
utilisateurs**, juste un compte unique dont les identifiants viennent de
l'environnement. C'est le strict nécessaire pour empêcher un inconnu de créer
des decks (et donc de faire grossir la base et le dossier d'images).

Le mot de passe n'existe jamais en clair dans le code ni en base : seul son
hash bcrypt est configuré, via `scripts/hash_password.py`.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from config import AUTH_PASSWORD_HASH, AUTH_USERNAME, JWT_ALGORITHM, JWT_EXPIRE_DAYS, JWT_SECRET

_bearer = HTTPBearer(auto_error=False)


def _require_configuration() -> None:
    """
    Échec explicite plutôt qu'ouverture silencieuse : un JWT_SECRET vide
    signerait des jetons que n'importe qui pourrait fabriquer.
    """
    if not AUTH_PASSWORD_HASH:
        raise HTTPException(
            500,
            "AUTH_PASSWORD_HASH n'est pas configuré : génère-le avec "
            "`python scripts/hash_password.py` et mets-le dans l'environnement.",
        )
    if not JWT_SECRET:
        raise HTTPException(500, "JWT_SECRET n'est pas configuré.")


def verify_credentials(username: str, password: str) -> bool:
    _require_configuration()
    # La comparaison du nom d'utilisateur passe aussi par bcrypt côté mot de
    # passe, donc pas de fuite de temps exploitable sur le seul nom.
    if username != AUTH_USERNAME:
        return False
    return bcrypt.checkpw(password.encode(), AUTH_PASSWORD_HASH.encode())


def create_token(username: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    return jwt.encode({"sub": username, "exp": expires}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def require_auth(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    """Dépendance FastAPI : lève 401 si le jeton est absent, invalide ou expiré."""
    _require_configuration()
    if credentials is None:
        raise HTTPException(401, "Authentification requise")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(401, "Session expirée ou jeton invalide")

    username = payload.get("sub")
    if username != AUTH_USERNAME:
        raise HTTPException(401, "Jeton non reconnu")
    return username
