import hashlib
import secrets as pysecrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_db
from ..models import ApiToken
from ..schemas import TokenCreate, TokenCreated, TokenOut
from .security import User, get_current_user

router = APIRouter(prefix="/api/v1/me/tokens", tags=["tokens"])


@router.post("", response_model=TokenCreated, status_code=201)
def create_token(
    payload: TokenCreate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
):
    ttl_days = payload.ttl_days or settings.api_token_max_ttl_days
    if ttl_days > settings.api_token_max_ttl_days:
        raise HTTPException(
            422,
            f"ttl_days cannot exceed the platform max of {settings.api_token_max_ttl_days}",
        )
    secret = f"orbpat_{pysecrets.token_urlsafe(32)}"
    token = ApiToken(
        email=user.email,
        name=payload.name,
        token_hash=hashlib.sha256(secret.encode()).hexdigest(),
        groups=user.groups,
        expires_at=datetime.now(UTC) + timedelta(days=ttl_days),
    )
    db.add(token)
    db.flush()
    return TokenCreated(
        id=token.id,
        name=token.name,
        token=secret,
        created_at=token.created_at,
        expires_at=token.expires_at,
    )


@router.get("", response_model=list[TokenOut])
def list_tokens(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return db.scalars(
        select(ApiToken).where(ApiToken.email == user.email).order_by(ApiToken.created_at.desc())
    ).all()


@router.delete("/{token_id}", status_code=202)
def revoke_token(
    token_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    token = db.get(ApiToken, token_id)
    if token is None or token.email != user.email:
        raise HTTPException(404, "token not found")
    token.revoked_at = datetime.now(UTC)
    return {"status": "revoked"}
