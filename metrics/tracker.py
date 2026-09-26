"""Append-only, redacted execution metrics."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class RunMetrics:
    mode: str
    task_class: str
    local_model: str | None = None
    external_model: str | None = None
    local_input_tokens: int = 0
    local_output_tokens: int = 0
    external_input_tokens: int = 0
    external_output_tokens: int = 0
    local_seconds: float = 0
    external_seconds: float = 0
    total_seconds: float = 0
    external_calls: int = 0
    external_attempts: int = 0
    external_reserved_tokens: int = 0
    effective_mode: str = "local"
    status: str = "running"
    review_status: str = "not_requested"
    selected_skill: str = "none"
    stages: list[dict[str, Any]] = field(default_factory=list)
    external_redactions: int = 0
    local_context_estimated_tokens: int = 0
    prompt_tokens_per_second: float | None = None
    generation_tokens_per_second: float | None = None
    errors: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class MetricsTracker:
    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, metrics: RunMetrics) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as target:
            target.write(json.dumps(asdict(metrics), ensure_ascii=False) + "\n")
