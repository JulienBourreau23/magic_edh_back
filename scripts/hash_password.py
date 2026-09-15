"""
scripts/hash_password.py — génère le hash bcrypt à mettre dans
AUTH_PASSWORD_HASH, et un JWT_SECRET si besoin.

Le mot de passe est saisi sans écho et n'est ni affiché, ni écrit sur disque,
ni passé en argument de ligne de commande (il resterait dans l'historique du
shell).

Usage : python scripts/hash_password.py
"""
import secrets
from getpass import getpass

import bcrypt


def main() -> None:
    password = getpass("Mot de passe : ")
    if not password:
        raise SystemExit("Mot de passe vide, abandon.")
    if password != getpass("Confirmation  : "):
        raise SystemExit("Les deux saisies diffèrent, abandon.")

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    print("\nÀ placer dans l'environnement du back (.env ou unité systemd) :\n")
    print(f"AUTH_PASSWORD_HASH='{hashed}'")
    print(f"JWT_SECRET='{secrets.token_urlsafe(48)}'")
    print("\n(le JWT_SECRET ci-dessus est nouveau : le régénérer déconnecte "
          "les sessions existantes)")


if __name__ == "__main__":
    main()
