from fastapi import APIRouter, Depends
from app.core.deps import get_current_user
from app.models import User
from app.schemas.api import CaptionIn, HashtagIn, IdeasIn
from app.services.ai.content import generate_caption, generate_hashtags, generate_ideas

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/caption")
def caption(payload: CaptionIn, _: User = Depends(get_current_user)):
    text = generate_caption(payload.org_id, payload.brief, payload.platform, payload.tone)
    return {"caption": text}


@router.post("/hashtags")
def hashtags(payload: HashtagIn, _: User = Depends(get_current_user)):
    return {"hashtags": generate_hashtags(payload.brief, payload.platform, payload.count)}


@router.post("/ideas")
def ideas(payload: IdeasIn, _: User = Depends(get_current_user)):
    return {"ideas": generate_ideas(payload.org_id, payload.topic, payload.n)}


@router.post("/auto_fill")
def auto_fill(payload: CaptionIn, _: User = Depends(get_current_user)):
    caption = generate_caption(payload.org_id, payload.brief, payload.platform, payload.tone)
    hashtags = generate_hashtags(payload.brief, payload.platform, 10)
    return {"caption": caption, "hashtags": hashtags}
