"""
LinkedIn connector — member (personal) posting via the versioned Posts API.

Requires a LinkedIn app with Marketing Developer Platform access and these
scopes: `openid`, `profile`, `email`, `w_member_social`.

Image/video posts need the Images/Videos upload API (initializeUpload -> PUT
bytes -> reference the URN). Text posting is fully implemented here; the image
flow is noted inline where it would slot in.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.services.connectors.base import (
    BaseConnector, TokenBundle, RemoteAccount, MetricsBundle,
)

AUTH = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN = "https://www.linkedin.com/oauth/v2/accessToken"
API = "https://api.linkedin.com"
LI_VERSION = "202405"


class LinkedInConnector(BaseConnector):
    platform = "linkedin"

    def authorize_url(self, state: str, code_challenge: str | None = None) -> str:
        params = {
            "response_type": "code",
            "client_id": settings.LINKEDIN_CLIENT_ID,
            "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
            "state": state,
            "scope": "openid profile email w_member_social",
        }
        return f"{AUTH}?{urlencode(params)}"

    def exchange_code(self, code: str, code_verifier: str | None = None) -> TokenBundle:
        with httpx.Client(timeout=30) as c:
            r = c.post(TOKEN, data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
                "client_id": settings.LINKEDIN_CLIENT_ID,
                "client_secret": settings.LINKEDIN_CLIENT_SECRET,
            }, headers={"Content-Type": "application/x-www-form-urlencoded"})
            r.raise_for_status()
            d = r.json()
        expires = datetime.now(timezone.utc) + timedelta(seconds=d.get("expires_in", 3600))
        return TokenBundle(
            access_token=d["access_token"],
            refresh_token=d.get("refresh_token"),
            expires_at=expires,
        )

    def refresh(self, token: TokenBundle) -> TokenBundle:
        if not token.refresh_token:
            return token
        with httpx.Client(timeout=30) as c:
            r = c.post(TOKEN, data={
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
                "client_id": settings.LINKEDIN_CLIENT_ID,
                "client_secret": settings.LINKEDIN_CLIENT_SECRET,
            })
            r.raise_for_status()
            d = r.json()
        expires = datetime.now(timezone.utc) + timedelta(seconds=d.get("expires_in", 3600))
        return TokenBundle(d["access_token"], d.get("refresh_token", token.refresh_token), expires)

    def fetch_accounts(self, token: TokenBundle) -> list[RemoteAccount]:
        # OpenID userinfo gives us the member id ("sub")
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API}/v2/userinfo",
                      headers={"Authorization": f"Bearer {token.access_token}"})
            r.raise_for_status()
            d = r.json()
        return [RemoteAccount(
            external_id=d["sub"],                       # urn built at publish time
            display_name=d.get("name", "LinkedIn member"),
            avatar_url=d.get("picture", ""),
            extra={"author_urn": f"urn:li:person:{d['sub']}"},
        )]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def publish(self, access_token, external_id, body, media, link) -> str:
        author_urn = f"urn:li:person:{external_id}"
        payload = {
            "author": author_urn,
            "commentary": body,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        # For images: initializeUpload -> PUT bytes -> set payload["content"]={"media":{"id":urn}}
        with httpx.Client(timeout=60) as c:
            r = c.post(f"{API}/rest/posts", json=payload, headers={
                "Authorization": f"Bearer {access_token}",
                "LinkedIn-Version": LI_VERSION,
                "X-Restli-Protocol-Version": "2.0.0",
            })
            r.raise_for_status()
            # the created post URN comes back in a response header
            return r.headers.get("x-restli-id") or r.headers.get("x-linkedin-id", "")

    def fetch_metrics(self, access_token, external_id) -> MetricsBundle:
        # Member-level follower counts aren't exposed via the basic member API;
        # organization pages use /rest/organizationalEntityFollowerStatistics.
        # Returning an empty bundle keeps the contract; fill in for org pages.
        return MetricsBundle()
