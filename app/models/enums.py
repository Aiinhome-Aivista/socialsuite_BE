import enum


class Platform(str, enum.Enum):
    facebook = "facebook"
    instagram = "instagram"
    linkedin = "linkedin"
    x = "x"
    youtube = "youtube"
    pinterest = "pinterest"
    google_analytics = "google_analytics"


class Role(str, enum.Enum):
    owner = "owner"        # full control incl. billing
    manager = "manager"    # manage content, approve, view analytics
    creator = "creator"    # create/draft content, submit for approval
    client = "client"      # review/approve only, read-only otherwise


class PostStatus(str, enum.Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    scheduled = "scheduled"
    publishing = "publishing"
    published = "published"
    failed = "failed"


class TargetStatus(str, enum.Enum):
    pending = "pending"
    publishing = "publishing"
    published = "published"
    failed = "failed"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class AccountStatus(str, enum.Enum):
    active = "active"
    expired = "expired"      # token expired, needs reconnect
    revoked = "revoked"
    error = "error"
