"""SSE event models for the 1Stop streaming chat API (R0.11, ARCHITECTURE §8.3).

These dataclasses define every event type the ``POST /api/v1/chat`` endpoint
emits.  ``encode_sse`` serialises any of them to the raw SSE wire format so
the chat route only needs one call per event.

Event flow for a successful request::

    StatusEvent(state="thinking")
    StatusEvent(state="answering")
    TokenEvent(text=<full answer text>)   # one event in R0; per-token in R1
    DoneEvent(input_tokens=…, output_tokens=…, cost_usd=…)

On error::

    StatusEvent(state="thinking")
    ErrorEvent(code="cap_reached" | "rate_limited" | "internal_error")
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Literal

__all__ = [
    "DoneEvent",
    "ErrorEvent",
    "SSEEvent",
    "StatusEvent",
    "TokenEvent",
    "encode_sse",
]


@dataclass
class StatusEvent:
    """Signals the current processing state to the client."""

    type: Literal["status"] = dc_field(default="status")
    state: str = "thinking"
    conversation_id: str = ""


@dataclass
class TokenEvent:
    """Carries a text chunk from the model (one per call in R0; per-token in R1)."""

    type: Literal["token"] = dc_field(default="token")
    text: str = ""
    conversation_id: str = ""


@dataclass
class DoneEvent:
    """Final event confirming successful completion with usage accounting."""

    type: Literal["done"] = dc_field(default="done")
    conversation_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class ErrorEvent:
    """Emitted when the request cannot be completed; no DoneEvent follows."""

    type: Literal["error"] = dc_field(default="error")
    code: str = "internal_error"
    detail: str = ""
    conversation_id: str = ""


SSEEvent = StatusEvent | TokenEvent | DoneEvent | ErrorEvent


def encode_sse(event: SSEEvent) -> str:
    r"""Serialise *event* to the raw SSE line format ``data: {json}\n\n``.

    Uses ``dataclasses.asdict`` so all fields are included in the JSON
    payload.  ``cost_usd`` in ``DoneEvent`` is already a ``float`` so the
    JSON encoder does not encounter a ``Decimal``.

    Args:
        event: Any concrete SSE event dataclass.

    Returns:
        A single SSE record ending with the required double newline.
    """
    return f"data: {json.dumps(dataclasses.asdict(event))}\n\n"
