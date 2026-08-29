"""
Where conversations live between visits.

Until now a conversation existed only in React state: a refresh lost it, and
there were no accounts, so there was nothing to lose it *from*. That is fine
for a demo and wrong for a legal tool, where the thing a person most wants to
come back to is the answer they were given about their own matter.

**SQLite by default, Postgres by configuration.** `DATABASE_URL` picks. SQLite
is a file on the same volume as the vector store, which makes a single-container
deployment complete with no second service to run and back up. It has one real
limit -- writers serialise -- and this workload is overwhelmingly reads plus a
handful of small writes per conversation, so that limit is far away. When it
stops being far away, the URL changes and nothing else does.

**Every row belongs to a user, and every query filters by that user.** Not
because the API is untrusted but because the *client* is: a thread id is a
guessable integer, and an endpoint that fetched by id alone would serve one
person's legal questions to another. The user comes from the session cookie,
never from the request body.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "lawai.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    """
    Someone who has signed in.

    Identified by Google's ``sub`` rather than by email. An email address can
    be reassigned within a Google Workspace domain, and if it were the key the
    new holder would inherit the previous person's conversations. ``sub`` is
    stable and is what Google documents as the identifier.

    Email and name are stored for display only, and are refreshed on each
    sign-in rather than treated as fixed.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_sub: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(200), default="")
    picture: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    threads: Mapped[list[Thread]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Thread(Base):
    """One conversation."""

    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    """Taken from the first question rather than generated. A title is not worth
    a model call, and one derived from the user's own words is more recognisable
    in a list than a summary would be."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped[User] = relationship(back_populates="threads")
    messages: Mapped[list[Message]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )

    __table_args__ = (Index("ix_threads_user_updated", "user_id", "updated_at"),)


class Message(Base):
    """
    One turn, and everything the UI needs to render it again.

    ``payload`` holds the structured half -- claims, verdicts, sources, the
    agent trail -- as JSON text. Kept whole rather than normalised into tables
    because it is *rendered*, never queried: no feature asks "which answers
    cited BNS 103", and building four tables to answer a question nobody has is
    how a schema becomes the thing you fight.

    Storing it at all is what makes a reloaded conversation the same
    conversation. Without it a returning user would see the prose and lose the
    claim types, the citations and the record of what was removed -- which is
    the part that makes an answer defensible.
    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    payload: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    thread: Mapped[Thread] = relationship(back_populates="messages")


def _make_engine():
    """
    The engine, with the one SQLite-specific setting that matters.

    ``check_same_thread=False`` because FastAPI serves requests from a thread
    pool and a session created on one thread is committed on another. The
    per-request session below is what keeps that safe: nothing is shared
    between requests.
    """
    connect_args = {}
    if DATABASE_URL.startswith("sqlite"):
        DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        connect_args["check_same_thread"] = False
    return create_engine(DATABASE_URL, connect_args=connect_args, future=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """
    Create the tables if they are absent.

    Enough for one service and a schema this small. It is not a migration
    story, and the moment a column has to change on a database with rows in it,
    this needs Alembic rather than a bigger version of itself.
    """
    Base.metadata.create_all(engine)


def get_session():
    """A session per request, closed whatever happens."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
