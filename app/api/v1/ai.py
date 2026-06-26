from fastapi import APIRouter, Depends
from app.core.deps import get_current_user
from app.models import User
from app.schemas.api import CaptionIn, HashtagIn, IdeasIn, AnalysisIn
from app.services.ai.content import generate_caption, generate_hashtags, generate_ideas, generate_analysis

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


@router.post("/analyze")
def analyze(payload: AnalysisIn, _: User = Depends(get_current_user)):
    return generate_analysis(
        platform=payload.platform,
        followers=payload.followers,
        likes=payload.likes,
        impressions=payload.impressions,
        watch_time_seconds=payload.watch_time_seconds,
        demographics=payload.demographics
    )
