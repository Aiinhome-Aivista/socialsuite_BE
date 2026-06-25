from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import get_current_user, require_role
from app.models import (
    User, SocialAccount, AnalyticsSnapshot, Post, Approval,
    ApprovalStatus, PostStatus, Role,
)

router = APIRouter(tags=["analytics-approvals"])


from datetime import datetime, timezone, timedelta
from app.services.publisher import _ensure_fresh_token
from app.services.connectors.registry import get_connector

@router.get("/analytics/summary")
def analytics_summary(
    org_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Latest snapshot per account + org totals. Fetches live metrics if stale."""
    accounts = db.query(SocialAccount).filter(SocialAccount.organization_id == org_id).all()
    per_account = []
    totals = {"followers": 0, "likes": 0, "impressions": 0, "watch_time_seconds": 0}
    
    now = datetime.now(timezone.utc)
    twelve_hours_ago = now - timedelta(hours=12)
    
    for a in accounts:
        latest = (
            db.query(AnalyticsSnapshot)
            .filter(AnalyticsSnapshot.social_account_id == a.id)
            .order_by(AnalyticsSnapshot.captured_at.desc())
            .first()
        )
        
        # If no snapshot or it's older than 12 hours, try to fetch a new one
        if not latest or (latest.captured_at.replace(tzinfo=timezone.utc) < twelve_hours_ago):
            try:
                connector = get_connector(a.platform.value)
                token = _ensure_fresh_token(db, a, connector)
                metrics = connector.fetch_metrics(token, a.external_id)
                
                new_snapshot = AnalyticsSnapshot(
                    social_account_id=a.id,
                    followers=metrics.followers,
                    likes=metrics.likes,
                    comments=metrics.comments,
                    shares=metrics.shares,
                    impressions=metrics.impressions,
                    watch_time_seconds=metrics.watch_time_seconds,
                    demographics=metrics.demographics,
                )
                db.add(new_snapshot)
                db.commit()
                db.refresh(new_snapshot)
                latest = new_snapshot
            except Exception as e:
                # If fetching fails (e.g., token revoked, network issue), just use old data if it exists
                # In production, we'd log this properly
                print(f"Failed to fetch metrics for {a.platform.value} account {a.id}: {e}")

        if latest:
            per_account.append({
                "account_id": a.id,
                "platform": a.platform.value,
                "display_name": a.display_name,
                "followers": latest.followers,
                "likes": latest.likes,
                "impressions": latest.impressions,
                "watch_time_seconds": latest.watch_time_seconds,
                "demographics": latest.demographics,
            })
            for k in totals:
                totals[k] += getattr(latest, k)
                
    return {"totals": totals, "accounts": per_account}


# ---------------- Approvals ----------------
@router.post("/approvals/{post_id}/request")
def request_approval(
    post_id: int,
    assigned_to: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    post.status = PostStatus.pending_approval
    db.add(Approval(post_id=post_id, requested_by=user.id, assigned_to=assigned_to))
    db.commit()
    return {"ok": True}


@router.post("/approvals/{approval_id}/decide")
def decide_approval(
    approval_id: int,
    approve: bool,
    comment: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    appr = db.get(Approval, approval_id)
    if not appr:
        raise HTTPException(status_code=404, detail="Approval not found")
    appr.status = ApprovalStatus.approved if approve else ApprovalStatus.rejected
    appr.comment = comment
    appr.decided_at = datetime.now(timezone.utc)

    post = db.get(Post, appr.post_id)
    if post:
        post.status = PostStatus.approved if approve else PostStatus.draft
    db.commit()
    return {"status": appr.status.value}
