from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Organization, Membership, Role
from app.core.security import hash_password, verify_password, create_access_token
from app.core.deps import get_current_user
from app.schemas.api import RegisterIn, LoginIn, TokenOut, GoogleLoginIn
from app.config import settings

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.flush()  # get user.id

    org = Organization(name=payload.organization_name)
    db.add(org)
    db.flush()

    db.add(Membership(user_id=user.id, organization_id=org.id, role=Role.owner))
    db.commit()

    return TokenOut(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenOut(access_token=create_access_token(str(user.id)))


@router.post("/google", response_model=TokenOut)
def google_login(payload: GoogleLoginIn, db: Session = Depends(get_db)):
    try:
        idinfo = id_token.verify_oauth2_token(
            payload.credential, 
            google_requests.Request(), 
            settings.GOOGLE_CLIENT_ID
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {e}")

    email = idinfo.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Google token missing email")

    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        # Register new user
        user = User(
            email=email,
            hashed_password="", # No password for Google users
            full_name=idinfo.get("name", ""),
        )
        db.add(user)
        db.flush()

        org = Organization(name="My Workspace")
        db.add(org)
        db.flush()

        db.add(Membership(user_id=user.id, organization_id=org.id, role=Role.owner))
        db.commit()

    return TokenOut(access_token=create_access_token(str(user.id)))


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    memberships = db.query(Membership).filter(Membership.user_id == user.id).all()
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "organizations": [
            {"org_id": m.organization_id, "role": m.role.value} for m in memberships
        ],
    }
