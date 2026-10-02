"""SSE streaming chat endpoint (R0.11, ARCHITECTURE §8.3).

Endpoint
--------
POST /api/v1/chat
    Stream an LLM answer as Server-Sent Events.  The client receives one
    ``StatusEvent``, one ``TokenEvent`` (full text in R0; per-token in R1),
    and a final ``DoneEvent``—or an ``ErrorEvent`` when something goes wrong.

Rate limiting
-------------
20 requests per 60 seconds per user.  The limit is enforced inside the SSE
generator so the rate-limit counter is incremented even when the response has
already started streaming.  On rate-limit: an ``ErrorEvent(code="rate_limited")``
is emitted and the stream ends.

Spend guard
-----------
A ``PersistedSpendGuard`` is instantiated from settings on each request.
``CapExceededError`` maps to ``ErrorEvent(code="cap_reached")``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncConnection

from src.integrations.llm.base import Message
from src.integrations.llm.ollama_adapter import OllamaAdapter
from src.modules.api.deps import current_user, get_db_conn
from src.modules.assistant.events import (
    DoneEvent,
    ErrorEvent,
    StatusEvent,
    TokenEvent,
    encode_sse,
)
from src.modules.assistant.llm_tool import AnswerLLMTool, AnswerRequest
from src.modules.platform.auth import UserRow
from src.modules.platform.rate_limit import check_and_increment
from src.modules.platform.settings import get_onestop_settings
from src.modules.platform.spend import CapExceededError, PersistedSpendGuard

__all__ = ["router_chat"]

router_chat = APIRouter(prefix="/api/v1", tags=["chat"])


class ChatRequest(BaseModel):
    """Body for POST /api/v1/chat."""

    model_config = ConfigDict(extra="forbid")

    message: str
    conversation_id: str | None = None
    max_tokens: int = 512
    model: str = "llama3.2"


@router_chat.post("/chat")
async def chat(
    request: ChatRequest,
    user: UserRow = Depends(current_user),
    conn: AsyncConnection = Depends(get_db_conn),
) -> StreamingResponse:
    """Stream an LLM answer for *message* as Server-Sent Events.

    The client should open the stream as::

        EventSource("/api/v1/chat")

    or consume the raw ``text/event-stream`` body.  Each event is a JSON
    object on a ``data:`` line; the stream ends after the ``done`` or
    ``error`` event.

    Args:
        request: Chat input including the user message and optional model.
        user: Authenticated user; injected via ``current_user``.
        conn: Database connection; shared with the SSE generator.

    Returns:
        A ``StreamingResponse`` of ``text/event-stream`` events.
    """
    s = get_onestop_settings()

    async def event_generator() -> AsyncGenerator[str, None]:
        conversation_id = request.conversation_id or str(uuid.uuid4())

        # -- Rate limit --------------------------------------------------------
        allowed = await check_and_increment(conn, f"chat:{user.id}", 20, 60)
        if not allowed:
            yield encode_sse(
                ErrorEvent(
                    code="rate_limited",
                    detail="Too many requests. Please wait.",
                    conversation_id=conversation_id,
                )
            )
            return

        yield encode_sse(StatusEvent(state="thinking", conversation_id=conversation_id))

        # -- Build tool --------------------------------------------------------
        guard = PersistedSpendGuard(
            day_cap_usd=Decimal(str(s.spend_cap_day_usd)),
            month_cap_usd=Decimal(str(s.spend_cap_month_usd)),
        )
        tool = AnswerLLMTool(
            provider=OllamaAdapter(model=request.model),
            guard=guard,
        )
        answer_req = AnswerRequest(
            messages=[Message(role="user", content=request.message)],
            max_tokens=request.max_tokens,
            provider_name="ollama",
            model_name=request.model,
        )

        yield encode_sse(StatusEvent(state="answering", conversation_id=conversation_id))

        # -- Execute -----------------------------------------------------------
        try:
            result = await tool.execute(answer_req, conn)
        except CapExceededError:
            yield encode_sse(
                ErrorEvent(
                    code="cap_reached",
                    detail="Spend cap reached. Try again later.",
                    conversation_id=conversation_id,
                )
            )
            return
        except Exception as exc:  # noqa: BLE001
            yield encode_sse(
                ErrorEvent(
                    code="internal_error",
                    detail=str(exc),
                    conversation_id=conversation_id,
                )
            )
            return

        yield encode_sse(TokenEvent(text=result.text, conversation_id=conversation_id))
        yield encode_sse(
            DoneEvent(
                conversation_id=conversation_id,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=float(result.cost_usd),
            )
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
