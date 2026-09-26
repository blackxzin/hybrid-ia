"""Configuration for the local-first hybrid assistant."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def load_dotenv(path: Path) -> None:
    """Load simple KEY=value pairs without overriding the shell environment."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    project_root: Path
    local_base_url: str = "http://127.0.0.1:8080/v1"
    local_model: str = "local-qwen"
    router9_base_url: str = "http://127.0.0.1:20128/v1"
    router9_api_key: str | None = None
    router9_enabled: bool = True
    planner_model: str = "kc/kilo-auto/free"
    reviewer_model: str = "kc/kilo-auto/free"
    default_mode: str = "auto"
    local_context_tokens: int = 8192
    response_reserve_tokens: int = 1024
    context_safety_tokens: int = 256
    external_file_char_limit: int = 12_000
    memory_enabled: bool = True
    max_external_calls: int = 3
    external_token_budget: int = 1600
    task_timeout_seconds: int = 900
    provider_timeout_seconds: int = 120
    fast_model: str = "kc/kilo-auto/free"
    private_paths: tuple[str, ...] = field(
        default=(".env", ".git", "secrets", "private", "credentials", "runtime", "data")
    )

    @property
    def local_input_budget(self) -> int:
        return self.local_context_tokens - self.response_reserve_tokens - self.context_safety_tokens

    def __post_init__(self) -> None:
        for name in ("local_context_tokens", "response_reserve_tokens", "external_file_char_limit", "task_timeout_seconds", "provider_timeout_seconds"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} deve ser positivo")
        if min(self.context_safety_tokens, self.max_external_calls, self.external_token_budget) < 0:
            raise ValueError("Margens e orçamentos não podem ser negativos")
        if self.local_input_budget < 128:
            raise ValueError("Configuração deixa menos de 128 tokens para entrada local")
        if self.default_mode not in {"auto", "local", "hybrid", "expert", "fast"}:
            raise ValueError("HYBRID_DEFAULT_MODE inválido")

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> "Settings":
        root = (project_root or Path(__file__).resolve().parent).resolve()
        load_dotenv(root / ".env")
        private_paths = tuple(
            item.strip() for item in os.getenv("HYBRID_PRIVATE_PATHS", "").split(",") if item.strip()
        )
        defaults = cls(project_root=root)
        return cls(
            project_root=root,
            local_base_url=os.getenv("LOCAL_QWEN_BASE_URL", defaults.local_base_url).rstrip("/"),
            local_model=os.getenv("LOCAL_QWEN_MODEL", defaults.local_model),
            router9_base_url=os.getenv("ROUTER9_BASE_URL", defaults.router9_base_url).rstrip("/"),
            router9_api_key=os.getenv("ROUTER9_API_KEY") or None,
            router9_enabled=os.getenv("ROUTER9_ENABLED", "true").strip().casefold() in {"1", "true", "yes", "on"},
            planner_model=os.getenv("ROUTER9_PLANNER_MODEL", defaults.planner_model),
            reviewer_model=os.getenv("ROUTER9_REVIEWER_MODEL", defaults.reviewer_model),
            default_mode=os.getenv("HYBRID_DEFAULT_MODE", defaults.default_mode).lower(),
            local_context_tokens=int(os.getenv("LOCAL_CONTEXT_TOKENS", defaults.local_context_tokens)),
            response_reserve_tokens=int(os.getenv("LOCAL_RESPONSE_RESERVE_TOKENS", defaults.response_reserve_tokens)),
            context_safety_tokens=int(os.getenv("LOCAL_CONTEXT_SAFETY_TOKENS", defaults.context_safety_tokens)),
            external_file_char_limit=int(os.getenv("EXTERNAL_FILE_CHAR_LIMIT", defaults.external_file_char_limit)),
            private_paths=defaults.private_paths + private_paths,
            memory_enabled=os.getenv("HYBRID_MEMORY_ENABLED", "true").casefold() in {"1", "true", "yes", "on"},
            max_external_calls=int(os.getenv("HYBRID_MAX_EXTERNAL_CALLS", "3")),
            external_token_budget=int(os.getenv("HYBRID_EXTERNAL_TOKEN_BUDGET", "1600")),
            task_timeout_seconds=int(os.getenv("HYBRID_TASK_TIMEOUT_SECONDS", "900")),
            provider_timeout_seconds=int(os.getenv("HYBRID_PROVIDER_TIMEOUT_SECONDS", "120")),
            fast_model=os.getenv("ROUTER9_FAST_MODEL", defaults.fast_model),
        )
