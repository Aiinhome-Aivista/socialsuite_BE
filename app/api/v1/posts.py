from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import get_current_user, require_role
from app.models import User, Post, PostTarget, PostStatus, Platform, Role
from app.schemas.api import PostIn, PostOut
from app.services.scheduler import schedule_post, cancel_scheduled_post
from app.services.publisher import publish_post

router = APIRouter(prefix="/posts", tags=["posts"])


@router.post("", response_model=PostOut)
def create_post(
    payload: PostIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    post = Post(
        organization_id=payload.org_id,
        author_id=user.id,
        body=payload.body,
        media=payload.media,
        link=payload.link,
        scheduled_at=payload.scheduled_at,
        status=PostStatus.scheduled if payload.scheduled_at else PostStatus.draft,
    )
    db.add(post)
    db.flush()

    for t in payload.targets:
        db.add(PostTarget(
            post_id=post.id,
            social_account_id=t.social_account_id,
            platform=Platform(t.platform),
        ))
    db.commit()
    db.refresh(post)

    if payload.scheduled_at:
        schedule_post(post.id, payload.scheduled_at)

    return post


@router.get("", response_model=list[PostOut])
def list_posts(
    org_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Post)
        .filter(Post.organization_id == org_id)
        .order_by(Post.created_at.desc())
        .all()
    )


@router.post("/{post_id}/publish", response_model=PostOut)
def publish_now(
    post_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    cancel_scheduled_post(post.id)
    publish_post(post.id)        # synchronous for the starter; move to background for scale
    db.refresh(post)
    return post


@router.get("/debug_posts")
def debug_posts(db: Session = Depends(get_db)):
    posts = db.query(Post).order_by(Post.id.desc()).limit(10).all()
    targets = db.query(PostTarget).order_by(PostTarget.id.desc()).limit(10).all()
    return {
        "posts": [{"id": p.id, "status": p.status.value, "scheduled_at": p.scheduled_at} for p in posts],
        "targets": [{"id": t.id, "post_id": t.post_id, "platform": t.platform.value, "status": t.status.value, "error": t.error} for t in targets]
    }

@router.get("/debug_trigger")
def debug_trigger(db: Session = Depends(get_db)):
    publish_post(8)
    return {"status": "triggered"}


@router.delete("/{post_id}")
def delete_post(
    post_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if post.status != PostStatus.scheduled:
        raise HTTPException(status_code=400, detail="Only scheduled posts can be deleted")
        
    if post.scheduled_at and post.scheduled_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Cannot delete a post whose scheduled time has passed")

    cancel_scheduled_post(post.id)
    db.delete(post)
    db.commit()
    return {"status": "deleted"}

