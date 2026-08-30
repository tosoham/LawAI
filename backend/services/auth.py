"""
Who is asking, established once and carried in a cookie.

Sign-in is Google only, and deliberately so: this stores nothing a password
could protect and holds no password of its own. Delegating identity means there
is no password to leak here, no reset flow to get wrong, and no credential this
service ever sees.

**The ID token is verified, not decoded.** `google.oauth2.id_token.verify_oauth2_token`
checks the signature against Google's rotating keys, the issuer, the audience
and the expiry. Reading the claims out of an unverified JWT is the classic
mistake -- the payload is base64, not encryption, so anyone can write one that
says whatever they like. Nothing here trusts a token it has not checked.

**The session is a signed cookie, not a JWT.** It carries one thing, the user's
row id, signed with `SESSION_SECRET` and timestamped. A JWT would let this
service skip a database read at the cost of being unable to revoke anything
before expiry; a signed id costs one indexed lookup and means deleting the row
ends the session. For a legal tool the second trade is the right one.

Set on the cookie and worth stating:

* ``httponly`` -- script cannot read it, so an XSS bug cannot exfiltrate the session
* ``samesite=lax`` -- not sent on cross-site POSTs, which is CSRF cover for the
  mutating routes without needing a token dance
* ``secure`` -- on unless ``AUTH_INSECURE_COOKIES=true``, which exists so
  ``http://localhost`` works in development and is named to be uncomfortable in
  anything else
"""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from models.db import User, get_session

logger = logging.getLogger(__name__)

SESSION_COOKIE = "lawai_session"
SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(30 * 24 * 3600)))


def google_client_id() -> str:
    return os.getenv("GOOGLE_CLIENT_ID", "").strip()


def require_sign_in() -> bool:
    """
    Whether answering a question needs an account.

    Off by default so localhost and any deployment without Google credentials
    keep working exactly as before. On, it is what turns "anyone on the
    internet" into "accounts you allow" -- the whole difference between bounded
    and unbounded spend on a paid model key.

    Only meaningful when sign-in is actually available; `main.py` refuses to
    start if this is on without a client id, because the alternative is an app
    that serves 401 to everyone and looks broken rather than misconfigured.
    """
    return os.getenv("REQUIRE_SIGN_IN", "false").strip().lower() in {"1", "true", "yes"}


def auth_enabled() -> bool:
    """
    Whether sign-in is available.

    Off when no client id is configured, and the API says so plainly rather
    than erroring: a deployment without Google credentials is a valid one --
    every existing endpoint works without an account, and only conversation
    history needs identity.
    """
    return bool(google_client_id())


def _secret() -> str:
    """
    The session signing key.

    Refused rather than defaulted when auth is on. A generated fallback would
    look like it worked and would silently invalidate every session on restart,
    and a hardcoded one would let anyone forge a cookie.
    """
    secret = os.getenv("SESSION_SECRET", "").strip()
    if not secret:
        raise RuntimeError(
            "SESSION_SECRET is not set. Generate one with "
            "`python -c 'import secrets; print(secrets.token_urlsafe(48))'`."
        )
    return secret


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_secret(), salt="lawai-session")


def verify_google_token(credential: str) -> dict:
    """
    Check a Google ID token and return its claims.

    Raises 401 on anything wrong. The reason is logged and not returned: a
    caller with a bad token does not need to be told which check failed, and
    the distinction is useful mainly to someone probing.
    """
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_oauth2_token(
            credential, google_requests.Request(), google_client_id()
        )
    except Exception as error:
        logger.warning(f"rejected a Google credential: {error}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign-in failed."
        ) from error

    if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        logger.warning(f"rejected a token from issuer {claims.get('iss')!r}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign-in failed."
        )
    if not claims.get("email_verified", False):
        # An unverified address can be claimed by someone else later, and the
        # account would follow the address.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="That Google account has no verified email address.",
        )
    return claims


def upsert_user(session: Session, claims: dict) -> User:
    """
    Find or create the user behind a verified token.

    Keyed on ``sub``. Display fields are refreshed on every sign-in because a
    person can change their name or picture, and a stale one in a header is a
    small lie that is easy to avoid.
    """
    sub = claims["sub"]
    user = session.query(User).filter(User.google_sub == sub).one_or_none()
    if user is None:
        user = User(google_sub=sub, email=claims.get("email", ""))
        session.add(user)
    user.email = claims.get("email", user.email)
    user.name = claims.get("name", "") or user.name
    user.picture = claims.get("picture", "") or user.picture
    user.last_seen_at = datetime.now(UTC)
    session.commit()
    return user


def _cookie_policy() -> tuple[str, bool]:
    """
    ``samesite`` and ``secure`` for this deployment.

    ``lax`` is right when the browser talks to one site -- localhost, or an API
    under the same hostname as the app -- and it is free CSRF cover.

    It is **wrong** when the frontend and the API are on different sites, which
    is exactly what a Vercel frontend and a Hugging Face Space backend are. A
    `Lax` cookie is simply not sent cross-site, so sign-in would appear to
    succeed and every request after it would arrive anonymous: the same silent
    shape as the missing `withCredentials`, and just as hard to see.

    `none` gives up what `lax` provided, and the compensating control is the
    explicit CORS origin list in `main.py` -- never `*`, which is also the only
    reason a credentialed cross-origin request is permitted at all. Browsers
    reject `SameSite=None` without `Secure`, so that pairing is forced here
    rather than left to a configuration mistake.
    """
    samesite = os.getenv("COOKIE_SAMESITE", "lax").strip().lower()
    if samesite not in {"lax", "strict", "none"}:
        logger.warning(f"COOKIE_SAMESITE={samesite!r} is not valid; using lax")
        samesite = "lax"
    insecure = os.getenv("AUTH_INSECURE_COOKIES", "false").lower() in {"1", "true", "yes"}
    if samesite == "none" and insecure:
        logger.warning(
            "COOKIE_SAMESITE=none requires a Secure cookie; ignoring "
            "AUTH_INSECURE_COOKIES. Browsers reject the combination outright."
        )
        insecure = False
    return samesite, not insecure


def issue_session(response: Response, user: User) -> None:
    """Sign the user's id into a cookie."""
    samesite, secure = _cookie_policy()
    response.set_cookie(
        SESSION_COOKIE,
        _serializer().dumps(user.id),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite=samesite,
        secure=secure,
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


DbSession = Annotated[Session, Depends(get_session)]


def current_user(request: Request, session: DbSession) -> User | None:
    """
    The signed-in user, or ``None``.

    Returns rather than raises, because most of this API is open: an answer
    does not need an account, and only history does. ``require_user`` is the
    dependency for routes that do.

    A cookie that no longer resolves to a row -- deleted account, wiped
    database -- is treated as signed out rather than as an error. That is what
    it means.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if not token or not auth_enabled():
        return None
    try:
        user_id = _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except SignatureExpired:
        return None
    except BadSignature:
        logger.warning("rejected a session cookie with a bad signature")
        return None
    except RuntimeError:
        return None
    return session.query(User).filter(User.id == user_id).one_or_none()


CurrentUser = Annotated["User | None", Depends(current_user)]


def require_user(user: CurrentUser) -> User:
    """For routes that hold someone's own conversations."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue."
        )
    return user


def paying_user(user: CurrentUser) -> User | None:
    """
    Identity for a route that spends money, and the rate limit that bounds it.

    Returns the user when sign-in is required, ``None`` when it is not -- so a
    localhost or credential-free deployment behaves exactly as it did before
    accounts existed.

    The rate limit is keyed by account where there is one and by a single
    shared bucket where there is not. That shared bucket is deliberately blunt:
    a deployment spending money without sign-in cannot tell callers apart, and
    one global cap is more honest than an IP key that punishes an office NAT
    and misses a phone moving between cells.
    """
    from services.rate_limit import enforce

    if require_sign_in():
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sign in to ask a question.",
            )
        enforce(f"user:{user.id}")
        return user

    enforce(f"user:{user.id}" if user else "anonymous")
    return user


PayingUser = Annotated["User | None", Depends(paying_user)]
