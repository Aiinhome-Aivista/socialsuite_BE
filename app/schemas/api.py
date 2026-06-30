from datetime import datetime
from pydantic import BaseModel, EmailStr
import pydantic


# ---- Auth ----
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""
    organization_name: str = "My Workspace"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class GoogleLoginIn(BaseModel):
    credential: str


# ---- AI ----
class CaptionIn(BaseModel):
    org_id: int
    brief: str
    platform: str = "instagram"
    tone: str = "friendly"


class HashtagIn(BaseModel):
    brief: str
    platform: str = "instagram"
    count: int = 10


class IdeasIn(BaseModel):
    org_id: int
    topic: str
    n: int = 5


class AnalysisIn(BaseModel):
    platform: str
    followers: int = 0
    likes: int = 0
    impressions: int = 0
    watch_time_seconds: int = 0
    demographics: dict = {}


# ---- Posts ----
class TargetIn(BaseModel):
    social_account_id: int
    platform: str


class PostIn(BaseModel):
    org_id: int
    body: str = ""
    media: list[dict] = []
    link: str | None = None
    targets: list[TargetIn] = []
    scheduled_at: datetime | None = None   # if set -> schedule, else draft


class PostOut(BaseModel):
    id: int
    body: str
    status: str
    scheduled_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True

    @pydantic.field_serializer("scheduled_at", "created_at", when_used="json")
    def serialize_datetime(self, dt: datetime | None) -> str | None:
        if dt:
            if dt.tzinfo is None:
                from datetime import timezone
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        return None


# ---- Connectors ----
class ConnectorOut(BaseModel):
    id: int
    platform: str
    display_name: str
    avatar_url: str
    status: str

    class Config:
        from_attributes = True
