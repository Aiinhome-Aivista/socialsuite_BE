"""
Takes a Post and pushes it to each PostTarget's platform. Per-target status is
tracked independently so one platform failing doesn't block the others.
Expired OAuth tokens are refreshed automatically before publishing.
"""
import logging
import traceback
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from tenacity import RetryError

from app.database import SessionLocal
from app.models import Post, PostTarget, SocialAccount, PostStatus, TargetStatus
from app.core.security import decrypt_token, encrypt_token
from app.services.connectors.base import TokenBundle
from app.services.connectors.registry import get_connector

log = logging.getLogger(__name__)


def _ensure_fresh_token(db: Session, account: SocialAccount, connector) -> str:
    """Return a valid access token, refreshing if it's expired/near-expiry."""
    # Facebook/Instagram publish with the long-lived page token in extra.
    if account.extra and account.extra.get("page_access_token"):
        return account.extra["page_access_token"]

    access = decrypt_token(account.access_token_enc)
    expires = account.token_expires_at
    soon = datetime.now(timezone.utc) + timedelta(minutes=5)

    if expires and account.refresh_token_enc and expires.replace(tzinfo=timezone.utc) <= soon:
        bundle = TokenBundle(
            access_token=access,
            refresh_token=decrypt_token(account.refresh_token_enc),
            expires_at=expires,
        )
        refreshed = connector.refresh(bundle)
        account.access_token_enc = encrypt_token(refreshed.access_token)
        if refreshed.refresh_token:
            account.refresh_token_enc = encrypt_token(refreshed.refresh_token)
        account.token_expires_at = refreshed.expires_at
        db.commit()
        return refreshed.access_token

    return access


def _publish_target(db: Session, target: PostTarget, post: Post) -> None:
    account = db.get(SocialAccount, target.social_account_id)
    connector = get_connector(target.platform.value)
    token = _ensure_fresh_token(db, account, connector)

    target.status = TargetStatus.publishing
    db.commit()
    try:
        external_id = connector.publish(
            access_token=token,
            external_id=account.external_id,
            body=post.body,
            media=post.media or [],
            link=post.link,
        )
        target.status = TargetStatus.published
        target.external_post_id = external_id
        target.published_at = datetime.now(timezone.utc)
        target.error = None
    except Exception as e:  # noqa: BLE001 - record any failure per target
        # Unwrap tenacity RetryError so the DB stores the real cause, not the wrapper.
        cause = e
        if isinstance(e, RetryError) and e.last_attempt.failed:
            cause = e.last_attempt.exception()

        log.error(
            "[publisher] failed to publish post=%s target=%s platform=%s: %s",
            post.id, target.id, target.platform.value,
            traceback.format_exc(),
        )
        target.status = TargetStatus.failed
        target.error = f"{type(cause).__name__}: {cause}"[:1000]
    db.commit()


def publish_post(post_id: int) -> None:
    with open("publish_debug.txt", "a") as f:
        f.write(f"Entering publish_post for {post_id}\n")
    """Entry point called by the scheduler or by an immediate-publish request."""
    db = SessionLocal()
    try:
        post = db.get(Post, post_id)
        if not post:
            return
        post.status = PostStatus.publishing
        db.commit()

        for target in post.targets:
            _publish_target(db, target, post)

        statuses = {t.status for t in post.targets}
        if TargetStatus.published in statuses and TargetStatus.failed not in statuses:
            post.status = PostStatus.published
        elif TargetStatus.published in statuses:
            post.status = PostStatus.published  # partial; per-target errors shown in UI
        else:
            post.status = PostStatus.failed
        db.commit()
    finally:
        db.close()
