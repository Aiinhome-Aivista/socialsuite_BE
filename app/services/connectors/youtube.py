"""
YouTube connector — Google OAuth2; "publishing" means uploading a video.

Requirements: a Google Cloud project with the YouTube Data API v3 enabled and an
OAuth consent screen **verified** for the upload scope. Scopes:
youtube.upload, youtube.readonly.

A YouTube "post" is a video upload, so publish() expects media[0] to be a video
URL. Upload uses Google's resumable protocol. Watch-time/impression analytics
require the separate YouTube Analytics API (noted in fetch_metrics).
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

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
DATA = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload "
    "https://www.googleapis.com/auth/youtube.readonly"
)


class YouTubeConnector(BaseConnector):
    platform = "youtube"

    def authorize_url(self, state: str, code_challenge: str | None = None) -> str:
        params = {
            "client_id": settings.YOUTUBE_CLIENT_ID,
            "redirect_uri": settings.YOUTUBE_REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",   # get a refresh token
            "prompt": "consent",
            "state": state,
        }
        return f"{AUTH}?{urlencode(params)}"

    def exchange_code(self, code: str, code_verifier: str | None = None) -> TokenBundle:
        with httpx.Client(timeout=30) as c:
            r = c.post(TOKEN, data={
                "code": code,
                "client_id": settings.YOUTUBE_CLIENT_ID,
                "client_secret": settings.YOUTUBE_CLIENT_SECRET,
                "redirect_uri": settings.YOUTUBE_REDIRECT_URI,
                "grant_type": "authorization_code",
            })
            r.raise_for_status()
            d = r.json()
        expires = datetime.now(timezone.utc) + timedelta(seconds=d.get("expires_in", 3600))
        return TokenBundle(d["access_token"], d.get("refresh_token"), expires)

    def refresh(self, token: TokenBundle) -> TokenBundle:
        if not token.refresh_token:
            return token
        with httpx.Client(timeout=30) as c:
            r = c.post(TOKEN, data={
                "refresh_token": token.refresh_token,
                "client_id": settings.YOUTUBE_CLIENT_ID,
                "client_secret": settings.YOUTUBE_CLIENT_SECRET,
                "grant_type": "refresh_token",
            })
            r.raise_for_status()
            d = r.json()
        expires = datetime.now(timezone.utc) + timedelta(seconds=d.get("expires_in", 3600))
        # Google doesn't return a new refresh token on refresh
        return TokenBundle(d["access_token"], token.refresh_token, expires)

    def fetch_accounts(self, token: TokenBundle) -> list[RemoteAccount]:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{DATA}/channels", params={
                "part": "snippet,statistics", "mine": "true",
            }, headers={"Authorization": f"Bearer {token.access_token}"})
            r.raise_for_status()
            items = r.json().get("items", [])
        if not items:
            return []
        ch = items[0]
        sn = ch["snippet"]
        return [RemoteAccount(
            external_id=ch["id"],
            display_name=sn.get("title", "YouTube channel"),
            avatar_url=sn.get("thumbnails", {}).get("default", {}).get("url", ""),
        )]

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=10))
    def publish(self, access_token, external_id, body, media, link) -> str:
        if not media or media[0].get("type") != "video":
            raise ValueError("YouTube publishing requires a video in media[0]")
        video_url = media[0]["url"]
        title = (body.splitlines()[0] if body else "Untitled")[:100]
        metadata = {
            "snippet": {"title": title, "description": body},
            "status": {"privacyStatus": "public"},
        }
        with httpx.Client(timeout=None) as c:
            # 1) start a resumable session
            init = c.post(
                f"{UPLOAD}?uploadType=resumable&part=snippet,status",
                json=metadata,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Upload-Content-Type": "video/*",
                },
            )
            init.raise_for_status()
            session_url = init.headers["Location"]

            # 2) read the source video from local disk
            import os
            file_name = video_url.split("/")[-1]
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
            file_path = os.path.join(base_dir, "uploads", file_name)
            
            with open(file_path, "rb") as f:
                video_bytes = f.read()
                
            up = c.put(session_url, content=video_bytes,
                       headers={"Content-Type": "video/*"})
            up.raise_for_status()
            return up.json().get("id", "")

    def fetch_metrics(self, access_token, external_id) -> MetricsBundle:
        with httpx.Client(timeout=30) as c:
            # Channel-level stats: subscribers + total views
            r = c.get(f"{DATA}/channels", params={
                "part": "statistics", "id": external_id,
            }, headers={"Authorization": f"Bearer {access_token}"})
            r.raise_for_status()
            items = r.json().get("items", [])
            if not items:
                return MetricsBundle()
            st = items[0]["statistics"]

            # Fetch up to 50 recent videos and sum their likeCount
            total_likes = 0
            try:
                search_r = c.get(f"{DATA}/search", params={
                    "part": "id",
                    "channelId": external_id,
                    "type": "video",
                    "maxResults": 50,
                    "order": "date",
                }, headers={"Authorization": f"Bearer {access_token}"})
                search_r.raise_for_status()
                video_ids = [
                    item["id"]["videoId"]
                    for item in search_r.json().get("items", [])
                    if item.get("id", {}).get("videoId")
                ]
                if video_ids:
                    stats_r = c.get(f"{DATA}/videos", params={
                        "part": "statistics",
                        "id": ",".join(video_ids),
                    }, headers={"Authorization": f"Bearer {access_token}"})
                    stats_r.raise_for_status()
                    for vid in stats_r.json().get("items", []):
                        total_likes += int(vid.get("statistics", {}).get("likeCount", 0))
            except Exception:
                pass  # like count is best-effort; don't fail the whole metrics call

        # watch_time_seconds needs the YouTube Analytics API (estimatedMinutesWatched)
        return MetricsBundle(
            followers=int(st.get("subscriberCount", 0)),
            likes=total_likes,
            impressions=int(st.get("viewCount", 0)),
        )
