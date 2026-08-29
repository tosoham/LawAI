"""
Conversations that survive a refresh.

**Every query filters by the signed-in user, and the user never comes from the
request.** A thread id is a small integer, so an endpoint that fetched by id
alone would hand one person's legal questions to anyone who counted upwards.
The filter is on the query rather than checked after loading, so there is no
version of these handlers that reads a row it is not entitled to.

The structured half of an answer -- claims, verdicts, sources, agent trail --
is stored with each message and returned with it. Without that a reloaded
conversation would show the prose and lose the claim types, the citations and
the record of what was removed, which is the part that makes an answer
defensible. A conversation you cannot re-examine is not the same conversation.
"""
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models.db import Message, Thread, User
from services.auth import DbSession, require_user

SignedIn = Annotated[User, Depends(require_user)]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/threads", tags=["Conversations"])

#: A title is the first question, trimmed. Not generated: a model call to name
#: a conversation is a cost with no answer attached, and the user's own words
#: are more recognisable in a list than a summary would be.
TITLE_CHARS = 80


class MessageIn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., max_length=100_000)
    payload: dict | None = Field(
        default=None,
        description="The structured half of an answer: claims, verdicts, "
        "sources, agent trail. Stored whole and returned unchanged.",
    )


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    payload: dict | None = None
    created_at: str


class ThreadSummary(BaseModel):
    id: int
    title: str
    updated_at: str


class ThreadDetail(ThreadSummary):
    messages: list[MessageOut]


def _message_out(message: Message) -> MessageOut:
    payload = None
    if message.payload:
        try:
            payload = json.loads(message.payload)
        except json.JSONDecodeError:
            # One unreadable payload must not take the conversation with it.
            # The prose is the part the reader needs most.
            logger.warning(f"message {message.id} has an unreadable payload")
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        payload=payload,
        created_at=message.created_at.isoformat(),
    )


def _owned(session: Session, thread_id: int, user: User) -> Thread:
    """
    Load a thread, or 404.

    Filtered by owner in the query. **404 rather than 403 for someone else's
    thread**: telling a caller that a thread exists but is not theirs confirms
    the id is real, which is the one bit of information an enumeration attack
    is looking for.
    """
    thread = (
        session.query(Thread)
        .filter(Thread.id == thread_id, Thread.user_id == user.id)
        .one_or_none()
    )
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such conversation."
        )
    return thread


@router.get("", response_model=list[ThreadSummary])
async def list_threads(
    user: SignedIn, session: DbSession
) -> list[ThreadSummary]:
    """The signed-in user's conversations, most recently used first."""
    threads = (
        session.query(Thread)
        .filter(Thread.user_id == user.id)
        .order_by(Thread.updated_at.desc())
        .limit(200)
        .all()
    )
    return [
        ThreadSummary(id=t.id, title=t.title, updated_at=t.updated_at.isoformat())
        for t in threads
    ]


@router.post("", response_model=ThreadDetail, status_code=status.HTTP_201_CREATED)
async def create_thread(
    user: SignedIn, session: DbSession
) -> ThreadDetail:
    thread = Thread(user_id=user.id)
    session.add(thread)
    session.commit()
    return ThreadDetail(
        id=thread.id,
        title=thread.title,
        updated_at=thread.updated_at.isoformat(),
        messages=[],
    )


@router.get("/{thread_id}", response_model=ThreadDetail)
async def get_thread(
    thread_id: int,
    user: SignedIn,
    session: DbSession,
) -> ThreadDetail:
    thread = _owned(session, thread_id, user)
    return ThreadDetail(
        id=thread.id,
        title=thread.title,
        updated_at=thread.updated_at.isoformat(),
        messages=[_message_out(m) for m in thread.messages],
    )


@router.post("/{thread_id}/messages", response_model=MessageOut, status_code=201)
async def append_message(
    thread_id: int,
    body: MessageIn,
    user: SignedIn,
    session: DbSession,
) -> MessageOut:
    """
    Add one turn.

    The thread takes its title from the first thing the user says, so a list of
    conversations reads as a list of questions rather than of timestamps.
    """
    thread = _owned(session, thread_id, user)
    message = Message(
        thread_id=thread.id,
        role=body.role,
        content=body.content,
        payload=json.dumps(body.payload) if body.payload else "",
    )
    session.add(message)

    if body.role == "user" and not thread.messages:
        title = body.content.strip()[:TITLE_CHARS]
        thread.title = title + ("…" if len(body.content.strip()) > TITLE_CHARS else "")

    session.commit()
    return _message_out(message)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: int,
    user: SignedIn,
    session: DbSession,
):
    """
    Delete a conversation and everything in it.

    A real delete, not a flag. Someone asking a legal question about their own
    matter and then removing it means it should be gone, and a soft delete
    would leave it sitting in the table looking deleted.
    """
    thread = _owned(session, thread_id, user)
    session.delete(thread)
    session.commit()
    return None
