"""
Connector management.

Flow:
  GET    /connectors/{platform}/authorize?org_id=  -> {redirect_url}
  GET    /connectors/{platform}/callback?code&state -> stores encrypted tokens
  GET    /connectors?org_id=                        -> list connected accounts
  DELETE /connectors/{account_id}                   -> disconnect

A row in `oauth_states` is created when the flow starts and consumed on
callback. It carries org_id/user_id and (for X) the PKCE code_verifier, so the
flow is safe across multiple gunicorn workers and restarts.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.core.deps import get_current_user
from app.core.security import encrypt_token
from app.core.pkce import generate_pkce_pair, random_state
from app.models import User, SocialAccount, Platform, AccountStatus, OAuthState, PostTarget, AnalyticsSnapshot
from app.schemas.api import ConnectorOut
from app.services.connectors.registry import get_connector

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("/{platform}/authorize")
def authorize(
    platform: str,
    org_id: int = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    connector = get_connector(platform)
    state = random_state()
    code_verifier = code_challenge = None
    if connector.uses_pkce:
        code_verifier, code_challenge = generate_pkce_pair()

    db.add(OAuthState(
        state=state, platform=platform, organization_id=org_id,
        user_id=user.id, code_verifier=code_verifier,
    ))
    db.commit()

    return {"redirect_url": connector.authorize_url(state, code_challenge)}


@router.get("/{platform}/callback")
def callback(
    platform: str,
    state: str,
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: Session = Depends(get_db),
):
    st = db.query(OAuthState).filter(OAuthState.state == state).first()
    frontend_url = settings.FRONTEND_ORIGIN.split(",")[0].strip()

    if not st or st.platform != platform:
        # Browser might double-request due to devtools/prefetch. Redirect gracefully.
        return RedirectResponse(url=f"{frontend_url}/connectors?connected={platform}", status_code=302)
        
    if error or not code:
        db.delete(st)
        db.commit()
        return RedirectResponse(url=f"{frontend_url}/connectors?error={error or 'missing_code'}", status_code=302)

    org_id = st.organization_id
    code_verifier = st.code_verifier

    connector = get_connector(platform)
    try:
        token = connector.exchange_code(code, code_verifier)
        accounts = connector.fetch_accounts(token)
    except Exception as e:
        db.delete(st)
        db.commit()
        return RedirectResponse(url=f"{frontend_url}/connectors?error=oauth_failed", status_code=302)
    
    if not accounts:
        db.delete(st)
        db.commit()
        return RedirectResponse(url=f"{frontend_url}/connectors?error=no_account_found", status_code=302)

    for acc in accounts:
        existing = (
            db.query(SocialAccount)
            .filter(
                SocialAccount.organization_id == org_id,
                SocialAccount.platform == Platform(platform),
                SocialAccount.external_id == acc.external_id,
            )
            .first()
        )
        record = existing or SocialAccount(
            organization_id=org_id,
            platform=Platform(platform),
            external_id=acc.external_id,
        )
        record.display_name = acc.display_name
        record.avatar_url = acc.avatar_url
        record.status = AccountStatus.active
        record.access_token_enc = encrypt_token(token.access_token)
        record.refresh_token_enc = (
            encrypt_token(token.refresh_token) if token.refresh_token else None
        )
        record.token_expires_at = token.expires_at
        record.extra = acc.extra
        if not existing:
            db.add(record)

    db.delete(st)  # one-time use
    db.commit()

    frontend_url = settings.FRONTEND_ORIGIN.split(",")[0].strip()
    return RedirectResponse(url=f"{frontend_url}/connectors?connected={platform}", status_code=302)


@router.get("", response_model=list[ConnectorOut])
def list_connectors(
    org_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    accounts = (
        db.query(SocialAccount)
        .filter(SocialAccount.organization_id == org_id)
        .all()
    )
    return [
        ConnectorOut(
            id=a.id, platform=a.platform.value, display_name=a.display_name,
            avatar_url=a.avatar_url, status=a.status.value,
        )
        for a in accounts
    ]


@router.delete("/{account_id}")
def disconnect(
    account_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    acc = db.get(SocialAccount, account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")

    # Delete referencing post targets and analytics snapshots to avoid FK constraint failures
    for t in db.query(PostTarget).filter(PostTarget.social_account_id == account_id).all():
        db.delete(t)
    for s in db.query(AnalyticsSnapshot).filter(AnalyticsSnapshot.social_account_id == account_id).all():
        db.delete(s)

    db.delete(acc)
    db.commit()
    return {"ok": True}
