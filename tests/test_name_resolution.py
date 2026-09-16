"""
Résolution des noms de cartes — les seuls tests du projet qui ont besoin de
Postgres, parce que la règle qu'ils vérifient est écrite en SQL
(`normalize_card_name`, migration 011) et non en Python : c'était le seul moyen
de n'avoir qu'une implémentation pour les deux côtés de la comparaison.

Ils se sautent proprement si la base n'est pas joignable, pour qu'un
déploiement ne casse pas là-dessus — mais sur le conteneur comme en dev la base
est là, donc ils tournent.

Chaque cas vient d'une decklist réellement collée dans l'application.
"""
import pytest

import db.cards as cards_db
from db.core import get_conn


def _base_joignable() -> bool:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _base_joignable(),
    reason="Postgres injoignable — ces tests vérifient du SQL, pas de la logique Python.",
)


def _resolu(nom: str) -> str | None:
    carte = cards_db.resolve_names([nom]).get(nom.lower())
    return carte["name"] if carte else None


def test_ile_de_base_avec_ou_sans_accent():
    # Le cas qui a motivé la correction : la base stocke « Ile » sans accent,
    # donc « Île » — l'orthographe correcte, et la carte la plus fréquente d'un
    # deck bleu — ne résolvait pas et se voyait proposer « Île souillée ».
    assert _resolu("Île") == "Island"
    assert _resolu("Ile") == "Island"


def test_ligature_dans_les_deux_sens():
    # La base écrit « Nuée de fÆries » avec ligature, mais « Annonciatrice
    # faerie » sans : l'orthographe qui marche changeait d'une carte à l'autre.
    assert _resolu("Nuée de færies") == "Cloud of Faeries"
    assert _resolu("Nuée de faeries") == "Cloud of Faeries"
    assert _resolu("Annonciatrice faerie") == "Faerie Harbinger"
    assert _resolu("Annonciatrice færie") == "Faerie Harbinger"


def test_accent_absent_du_pdf():
    # magic-ville imprime « Necropède », la base a « Nécropède ».
    assert _resolu("Necropède") is not None
    assert _resolu("Nécropède") is not None


def test_accent_sur_un_nom_anglais():
    # La normalisation vaut pour les deux langues.
    assert _resolu("Marton Stromgald") == "Márton Stromgald"


def test_nom_inconnu_reste_absent():
    # Garde-fou : neutraliser les accents ne doit pas transformer la résolution
    # exacte en filet qui attrape n'importe quoi. Au flou de trancher ensuite.
    assert _resolu("Carte qui n'existe pas 12345") is None


def test_casse_ignoree():
    assert _resolu("anneau solaire") == "Sol Ring"
