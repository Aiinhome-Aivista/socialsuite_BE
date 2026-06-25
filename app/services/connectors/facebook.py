"""
Facebook (Pages) connector — reference implementation of the connector contract.

NOTE: This uses the Meta Graph API. To go live you must create a Meta app,
request the pages_manage_posts / pages_read_engagement / read_insights
permissions, and pass Meta's App Review. The same code structure applies to
Instagram (via the linked IG Business account on the Graph API).
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

GRAPH = "https://graph.facebook.com/v21.0"


class FacebookConnector(BaseConnector):
    platform = "facebook"

    def authorize_url(self, state: str, code_challenge: str | None = None) -> str:
        params = {
            "client_id": settings.FACEBOOK_APP_ID,
            "redirect_uri": settings.FACEBOOK_REDIRECT_URI,
            "state": state,
            "scope": "pages_show_list,pages_manage_posts,pages_read_engagement,read_insights",
        }
        return "https://www.facebook.com/v21.0/dialog/oauth?" + urlencode(params)

    def exchange_code(self, code: str, code_verifier: str | None = None) -> TokenBundle:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{GRAPH}/oauth/access_token", params={
                "client_id": settings.FACEBOOK_APP_ID,
                "client_secret": settings.FACEBOOK_APP_SECRET,
                "redirect_uri": settings.FACEBOOK_REDIRECT_URI,
                "code": code,
            })
            r.raise_for_status()
            data = r.json()
        expires = None
        if "expires_in" in data:
            expires = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])
        return TokenBundle(access_token=data["access_token"], expires_at=expires)

    def fetch_accounts(self, token: TokenBundle) -> list[RemoteAccount]:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{GRAPH}/me/accounts", params={
                "access_token": token.access_token,
                "fields": "id,name,picture,access_token",
            })
            r.raise_for_status()
            pages = r.json().get("data", [])
        out = []
        for p in pages:
            out.append(RemoteAccount(
                external_id=p["id"],
                display_name=p.get("name", ""),
                avatar_url=p.get("picture", {}).get("data", {}).get("url", ""),
                # Page access token is what we actually publish with
                extra={"page_access_token": p.get("access_token", "")},
            ))
        return out

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def publish(self, access_token, external_id, body, media, link) -> str:
        # access_token here should be the PAGE token (stored in account.extra)
        with httpx.Client(timeout=60) as c:
            if media:
                m = media[0]
                if m.get("type") == "video":
                    import os
                    file_name = m["url"].split("/")[-1]
                    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
                    file_path = os.path.join(base_dir, "uploads", file_name)
                    with open(file_path, "rb") as f:
                        video_bytes = f.read()
                        
                    r = c.post(f"{GRAPH}/{external_id}/videos", data={
                        "access_token": access_token,
                        "description": body,
                    }, files={"source": (file_name, video_bytes, "video/mp4")})
                else:
                    import os
                    file_name = m["url"].split("/")[-1]
                    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
                    file_path = os.path.join(base_dir, "uploads", file_name)
                    with open(file_path, "rb") as f:
                        image_bytes = f.read()

                    r = c.post(f"{GRAPH}/{external_id}/photos", data={
                        "access_token": access_token,
                        "caption": body,
                    }, files={"source": (file_name, image_bytes, "image/jpeg")})
            else:
                payload = {"access_token": access_token, "message": body}
                if link:
                    payload["link"] = link
                r = c.post(f"{GRAPH}/{external_id}/feed", data=payload)
            r.raise_for_status()
            return r.json().get("id", "")

    def fetch_metrics(self, access_token, external_id) -> MetricsBundle:
        with httpx.Client(timeout=30) as c:
            # Follower count
            r = c.get(f"{GRAPH}/{external_id}", params={
                "access_token": access_token,
                "fields": "followers_count,fan_count",
            })
            r.raise_for_status()
            d = r.json()
            followers = d.get("followers_count") or d.get("fan_count", 0)

            # Total likes: sum reactions across the 25 most recent posts
            total_likes = 0
            try:
                posts_r = c.get(f"{GRAPH}/{external_id}/posts", params={
                    "access_token": access_token,
                    "fields": "reactions.summary(true)",
                    "limit": 25,
                })
                posts_r.raise_for_status()
                for post in posts_r.json().get("data", []):
                    total_likes += post.get("reactions", {}).get("summary", {}).get("total_count", 0)
            except Exception:
                pass  # like count is best-effort

        return MetricsBundle(followers=followers, likes=total_likes)

