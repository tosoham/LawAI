"""
Sign in, sign out, and say who you are.

Three routes and nothing more. There is no registration, no password reset, no
email verification and no profile editing, because Google owns all of that and
duplicating it here would mean holding credentials this service has no reason
to hold.
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from models.db import User
from services.auth import (
    DbSession,
    auth_enabled,
    clear_session,
    current_user,
    google_client_id,
    issue_session,
    upsert_user,
    verify_google_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


class GoogleSignIn(BaseModel):
    credential: str = Field(
        ...,
        min_length=16,
        description="The ID token from Google Identity Services.",
    )


class Identity(BaseModel):
    signed_in: bool
    email: str = ""
    name: str = ""
    picture: str = ""


class AuthConfig(BaseModel):
    """What the frontend needs to render a sign-in button, and nothing else."""

    enabled: bool
    client_id: str = ""


@router.get("/config", response_model=AuthConfig)
async def config() -> AuthConfig:
    """
    Whether sign-in is available here, and the public client id.

    Served rather than baked into the frontend build: `NEXT_PUBLIC_*` is
    inlined at build time, so a client id compiled in would mean a separate
    image per deployment. The client id is public by design -- it appears in
    every OAuth redirect -- and the secret is not involved in this flow at all.
    """
    return AuthConfig(enabled=auth_enabled(), client_id=google_client_id())


@router.post("/google", response_model=Identity)
async def sign_in(
    body: GoogleSignIn,
    response: Response,
    session: DbSession,
) -> Identity:
    """
    Exchange a verified Google ID token for a session cookie.

    The token is checked against Google's keys before anything is written --
    see `services/auth.verify_google_token`. Nothing in the request body is
    trusted: the email and name come from the verified claims, not from the
    client.
    """
    claims = verify_google_token(body.credential)
    user = upsert_user(session, claims)
    issue_session(response, user)
    logger.info(f"signed in user {user.id}")
    return Identity(
        signed_in=True, email=user.email, name=user.name, picture=user.picture
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(response: Response) -> None:
    """
    Drop the session cookie.

    Nothing server-side to revoke: the cookie *is* the session, and the row it
    points at is the user rather than a session record. Deleting the user ends
    every session they have, which is the property that made a signed id
    preferable to a JWT.
    """
    # Written to the injected response and *not* returned as a new one. A
    # fresh `Response(...)` here discards the Set-Cookie header this just
    # wrote, so logout returned 204 and left the session intact -- the failure
    # looked exactly like success.
    clear_session(response)


@router.get("/me", response_model=Identity)
async def me(user: Annotated[User | None, Depends(current_user)]) -> Identity:
    """Who the cookie says you are. Never 401 — signed out is an answer."""
    if user is None:
        return Identity(signed_in=False)
    return Identity(
        signed_in=True, email=user.email, name=user.name, picture=user.picture
    )
