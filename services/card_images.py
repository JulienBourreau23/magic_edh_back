"""
services/card_images.py — téléchargement à la demande des images de cartes
depuis Scryfall, stockées à plat dans CARD_IMAGES_DIR (servi en StaticFiles
par main.py, comme /srv/monsters côté sw-coaching).

Le drapeau `image_downloaded` en base peut diverger du disque (volume remonté,
dossier vidé, migration de LXC). On ne lui fait donc pas confiance : l'état de
référence est le fichier. Un drapeau à vrai sans fichier serait le pire cas —
le front construirait une URL locale qui renvoie 404 au lieu de retomber sur
Scryfall.
"""
import os
from concurrent.futures import ThreadPoolExecutor

import httpx

import db.cards as cards_db
from config import CARD_IMAGES_DIR, SCRYFALL_HEADERS

# Une fiche deck neuve, c'est ~100 images. En séquentiel la première ouverture
# prenait des dizaines de secondes ; on parallélise en restant poli avec le CDN.
MAX_PARALLEL_DOWNLOADS = 6


def image_path(scryfall_id: str) -> str:
    return os.path.join(CARD_IMAGES_DIR, f"{scryfall_id}.jpg")


def _download(client: httpx.Client, card: dict) -> str | None:
    """Renvoie le scryfall_id si l'image est sur disque à la sortie, sinon None."""
    try:
        resp = client.get(card["image_uri"])
        resp.raise_for_status()
    except httpx.HTTPError:
        return None  # une image manquante ne doit pas casser l'affichage de la fiche

    # Écriture atomique : un fichier partiel (process tué en plein
    # téléchargement) serait servi tel quel et marqué comme valide.
    dest = image_path(card["scryfall_id"])
    tmp = f"{dest}.part"
    with open(tmp, "wb") as f:
        f.write(resp.content)
    os.replace(tmp, dest)
    return card["scryfall_id"]


def ensure_images(cards: list[dict]) -> None:
    candidates = [card for card in cards if card.get("image_uri")]
    if not candidates:
        return

    os.makedirs(CARD_IMAGES_DIR, exist_ok=True)

    on_disk, missing = [], []
    for card in candidates:
        (on_disk if os.path.exists(image_path(card["scryfall_id"])) else missing).append(card)

    downloaded: list[str] = []
    if missing:
        with httpx.Client(timeout=15, follow_redirects=True, headers=SCRYFALL_HEADERS) as client:
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_DOWNLOADS) as pool:
                downloaded = [sid for sid in pool.map(lambda c: _download(client, c), missing) if sid]

    present = {card["scryfall_id"] for card in on_disk} | set(downloaded)
    flagged = {card["scryfall_id"]: bool(card.get("image_downloaded")) for card in candidates}

    # Remettre les drapeaux en accord avec le disque, dans les deux sens.
    cards_db.mark_images_downloaded([sid for sid in present if not flagged[sid]])
    cards_db.mark_images_missing(
        [sid for sid in flagged if flagged[sid] and sid not in present]
    )
