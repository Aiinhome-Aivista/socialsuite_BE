"""
Google Analytics (GA4) connector — Google OAuth2.
Provides read-only access to GA4 web property metrics (Active Users, Sessions, Page Views).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.services.connectors.base import (
    BaseConnector, TokenBundle, RemoteAccount, MetricsBundle,
)

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
ADMIN_API = "https://analyticsadmin.googleapis.com/v1beta"
DATA_API = "https://analyticsdata.googleapis.com/v1beta"
SCOPES = "https://www.googleapis.com/auth/analytics.readonly"


class GoogleAnalyticsConnector(BaseConnector):
    platform = "google_analytics"

    def authorize_url(self, state: str, code_challenge: str | None = None) -> str:
        client_id = settings.GOOGLE_ANALYTICS_CLIENT_ID or settings.YOUTUBE_CLIENT_ID
        redirect_uri = settings.GOOGLE_ANALYTICS_REDIRECT_URI or settings.YOUTUBE_REDIRECT_URI
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",   # get a refresh token
            "prompt": "consent",
            "state": state,
        }
        return f"{AUTH}?{urlencode(params)}"

    def exchange_code(self, code: str, code_verifier: str | None = None) -> TokenBundle:
        client_id = settings.GOOGLE_ANALYTICS_CLIENT_ID or settings.YOUTUBE_CLIENT_ID
        client_secret = settings.GOOGLE_ANALYTICS_CLIENT_SECRET or settings.YOUTUBE_CLIENT_SECRET
        redirect_uri = settings.GOOGLE_ANALYTICS_REDIRECT_URI or settings.YOUTUBE_REDIRECT_URI
        with httpx.Client(timeout=30) as c:
            r = c.post(TOKEN, data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            })
            r.raise_for_status()
            d = r.json()
        expires = datetime.now(timezone.utc) + timedelta(seconds=d.get("expires_in", 3600))
        return TokenBundle(d["access_token"], d.get("refresh_token"), expires)

    def refresh(self, token: TokenBundle) -> TokenBundle:
        if not token.refresh_token:
            return token
        client_id = settings.GOOGLE_ANALYTICS_CLIENT_ID or settings.YOUTUBE_CLIENT_ID
        client_secret = settings.GOOGLE_ANALYTICS_CLIENT_SECRET or settings.YOUTUBE_CLIENT_SECRET
        with httpx.Client(timeout=30) as c:
            r = c.post(TOKEN, data={
                "refresh_token": token.refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
            })
            r.raise_for_status()
            d = r.json()
        expires = datetime.now(timezone.utc) + timedelta(seconds=d.get("expires_in", 3600))
        return TokenBundle(d["access_token"], token.refresh_token, expires)

    def fetch_accounts(self, token: TokenBundle) -> list[RemoteAccount]:
        """Lists GA4 properties the user has access to."""
        headers = {"Authorization": f"Bearer {token.access_token}"}
        accounts_list = []
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{ADMIN_API}/accountSummaries", headers=headers)
            r.raise_for_status()
            summaries = r.json().get("accountSummaries", [])
            for summary in summaries:
                props = summary.get("propertySummaries", [])
                for p in props:
                    # property matches: "properties/123456"
                    prop_id = p.get("property", "")
                    display_name = p.get("displayName", "GA4 Property")
                    accounts_list.append(RemoteAccount(
                        external_id=prop_id,
                        display_name=f"{summary.get('displayName', 'Analytics')} - {display_name}",
                        avatar_url="",
                    ))
        return accounts_list

    def publish(self, access_token: str, external_id: str, body: str,
                media: list[dict], link: str | None) -> str:
        raise NotImplementedError("Google Analytics is a read-only platform.")

    def fetch_metrics(self, access_token: str, external_id: str) -> MetricsBundle:
        """Fetches activeUsers, sessions, and screenPageViews reports from GA4 Data API."""
        headers = {"Authorization": f"Bearer {access_token}"}
        body = {
            "dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
            "metrics": [
                {"name": "activeUsers"},
                {"name": "sessions"},
                {"name": "screenPageViews"}
            ]
        }
        
        # external_id is formatted as "properties/123456"
        url = f"{DATA_API}/{external_id}:runReport"
        
        active_users = 0
        sessions = 0
        page_views = 0
        
        try:
            with httpx.Client(timeout=30) as c:
                r = c.post(url, json=body, headers=headers)
                r.raise_for_status()
                data = r.json()
                
                rows = data.get("rows", [])
                if rows:
                    metric_values = rows[0].get("metricValues", [])
                    if len(metric_values) >= 3:
                        active_users = int(metric_values[0].get("value", 0))
                        sessions = int(metric_values[1].get("value", 0))
                        page_views = int(metric_values[2].get("value", 0))
        except Exception as e:
            # log or handle fetch error
            print(f"Error fetching GA4 metrics for {external_id}: {e}")
            
        return MetricsBundle(
            followers=active_users,       # Active Users -> Followers column
            likes=sessions,               # Sessions -> Likes column
            impressions=page_views,       # Page Views -> Impressions column
        )
