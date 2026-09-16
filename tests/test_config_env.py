"""
Le `.env` est lu par deux lecteurs différents : systemd pour le service, et
`config._load_env_file` pour les scripts en ligne de commande. Ils doivent
comprendre le fichier de la même façon, sans quoi un script se connecte
ailleurs que le service — c'est exactement la panne qu'on corrige ici.
"""
import os

from config import _load_env_file


def test_lit_les_paires_et_retire_les_guillemets(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# commentaire\n"
        "\n"
        "PG_HOST=192.168.1.104\n"
        "  PG_PORT = 5432 \n"
        # Un hash bcrypt contient des `$` : aucune expansion ne doit avoir lieu.
        "AUTH_PASSWORD_HASH='$2b$12$abcdef'\n"
        'JWT_SECRET="un-secret"\n',
        encoding="utf-8",
    )
    for key in ("PG_HOST", "PG_PORT", "AUTH_PASSWORD_HASH", "JWT_SECRET"):
        monkeypatch.delenv(key, raising=False)

    _load_env_file(env)

    assert os.environ["PG_HOST"] == "192.168.1.104"
    assert os.environ["PG_PORT"] == "5432"
    assert os.environ["AUTH_PASSWORD_HASH"] == "$2b$12$abcdef"
    assert os.environ["JWT_SECRET"] == "un-secret"


def test_l_environnement_existant_gagne(tmp_path, monkeypatch):
    # Le service passe déjà ses variables : le fichier ne doit pas les écraser.
    env = tmp_path / ".env"
    env.write_text("PG_HOST=depuis-le-fichier\n", encoding="utf-8")
    monkeypatch.setenv("PG_HOST", "depuis-systemd")

    _load_env_file(env)

    assert os.environ["PG_HOST"] == "depuis-systemd"


def test_fichier_absent_ne_casse_rien(tmp_path):
    _load_env_file(tmp_path / "absent")
