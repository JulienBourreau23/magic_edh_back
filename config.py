import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent / ".env"


def _load_env_file(path: Path = ENV_FILE) -> None:
    """
    Charge le `.env` dans l'environnement, sans écraser ce qui s'y trouve déjà.

    Le service lit ce même fichier via l'`EnvironmentFile` de son unit systemd,
    mais un script lancé à la main (sync, backfill) n'en hérite pas : il
    tombait alors sur les valeurs par défaut et cherchait Postgres en
    localhost, sur un conteneur qui n'en héberge pas. On ne garde donc que la
    syntaxe que systemd accepte lui-même — `CLE=valeur`, commentaires, et
    guillemets encadrants retirés — sans expansion de variables : un mot de
    passe contenant `$` doit arriver tel quel.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return  # Pas de .env : l'environnement fait foi (service, CI, tests).

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_env_file()

DB_HOST     = os.environ.get("PG_HOST",     "localhost")
DB_PORT     = int(os.environ.get("PG_PORT", "5432"))
DB_NAME     = os.environ.get("PG_DATABASE", "magic_edh")
DB_USER     = os.environ.get("PG_USER",     "julien")
DB_PASS     = os.environ.get("PG_PASSWORD", "")
# Taille max du pool. Le threadpool FastAPI est aligné dessus au démarrage
# (cf. main.py) pour qu'il ne puisse jamais réclamer plus de connexions que
# le pool n'en contient.
DB_POOL_MAX = int(os.environ.get("PG_POOL_MAX", "20"))

SCRYFALL_API_BASE = "https://api.scryfall.com"
# Scryfall refuse les requêtes avec un User-Agent générique de lib HTTP (règle
# "generic_user_agent") : il faut un identifiant d'appli + contact explicites.
SCRYFALL_HEADERS = {"User-Agent": "MagicEDH/0.1 (+bourreau.julien@gmail.com)", "Accept": "*/*"}
CARD_IMAGES_DIR = os.environ.get("CARD_IMAGES_DIR", "/srv/mtg-cards")

CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "https://mtg-edh.julien-cloud.eu,http://localhost:3000",
).split(",")

# Application personnelle : un seul compte, pas d'inscription, pas de table
# utilisateurs. Le mot de passe n'est connu que par son hash bcrypt, à générer
# avec `python scripts/hash_password.py`. Sans AUTH_PASSWORD_HASH, la connexion
# échoue explicitement plutôt que d'ouvrir l'accès.
AUTH_USERNAME = os.environ.get("AUTH_USERNAME", "julien")
AUTH_PASSWORD_HASH = os.environ.get("AUTH_PASSWORD_HASH", "")

JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = int(os.environ.get("JWT_EXPIRE_DAYS", "30"))
