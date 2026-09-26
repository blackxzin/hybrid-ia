"""Shared provider result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class Completion:
    content: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    elapsed_seconds: float
    timings: dict[str, Any] = field(default_factory=dict)
    finish_reason: str | None = None


class ProviderError(RuntimeError):
    """A provider could not complete a request without exposing credentials."""
