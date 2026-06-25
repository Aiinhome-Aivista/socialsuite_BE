from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.security import decode_access_token
from app.models import User, Membership, Role

CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> User:
    if not authorization.lower().startswith("bearer "):
        raise CREDENTIALS_EXC
    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise CREDENTIALS_EXC
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise CREDENTIALS_EXC
    return user


def get_membership(
    org_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Membership:
    m = (
        db.query(Membership)
        .filter(Membership.user_id == user.id, Membership.organization_id == org_id)
        .first()
    )
    if not m:
        raise HTTPException(status_code=403, detail="Not a member of this organization")
    return m


# Role hierarchy for permission checks
_ROLE_RANK = {Role.client: 1, Role.creator: 2, Role.manager: 3, Role.owner: 4}


def require_role(minimum: Role):
    """Dependency factory: ensures the caller's role >= minimum for the org."""
    def _guard(m: Membership = Depends(get_membership)) -> Membership:
        if _ROLE_RANK[m.role] < _ROLE_RANK[minimum]:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return m
    return _guard
