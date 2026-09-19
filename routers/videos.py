from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db.videos as videos_db
from services import video_cards

router = APIRouter(prefix="/videos", tags=["videos"])


class Segment(BaseModel):
    text: str
    start: float = 0.0


class Chapter(BaseModel):
    title: str
    start: float = 0.0


class ImportRequest(BaseModel):
    video_id: str = Field(min_length=5, max_length=32)
    title: str
    url: str
    channel: str | None = None
    language: str | None = None
    auto_generated: bool = True
    duration_seconds: int | None = None
    chapters: list[Chapter] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list, max_length=20000)


@router.post("/import")
def import_video(payload: ImportRequest):
    """
    Croise une retranscription avec le catalogue et retient ce qu'elle cite.

    **Le texte n'est pas conservé** : seulement des identifiants de cartes, des
    clés de cycles, des comptes et des horodatages. Ce qui se republierait n'a
    rien à faire en base ; ce qui sert, c'est « cette vidéo parle de ce cycle à
    1 min 18 ».

    L'outil qui appelle cet endpoint vit en local (`magic_edh_tools`) : c'est
    lui qui parle à YouTube, jamais le serveur — une dépendance externe fragile
    n'a pas sa place dans le chemin d'un écran.
    """
    segments = [segment.model_dump() for segment in payload.segments]
    chapters = [chapter.model_dump() for chapter in payload.chapters]
    mentions = video_cards.extract(segments, chapters)

    videos_db.replace_video(
        {
            "video_id": payload.video_id, "title": payload.title, "channel": payload.channel,
            "url": payload.url, "language": payload.language,
            "auto_generated": payload.auto_generated,
            "duration_seconds": payload.duration_seconds,
        },
        mentions,
    )
    return {"video_id": payload.video_id, **video_cards.describe(mentions)}


@router.get("")
def list_videos():
    return {"videos": videos_db.list_videos()}


@router.delete("/{video_id}", status_code=204)
def delete_video(video_id: str):
    if not videos_db.delete_video(video_id):
        raise HTTPException(404, "Vidéo introuvable")
