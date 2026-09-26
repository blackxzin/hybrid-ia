"""Explicit opt-in file selection and conservative secret redaction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S),
    re.compile(r"(?i)\b(?:[a-z0-9]+[_-])*(?:api[_-]?key|token|secret|password|passwd|authorization)[\"']?\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)(?:https?|postgres(?:ql)?|mysql|redis)://[^\s/@:]+:[^\s/@]+@"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|authorization)\b\s*([:=])\s*(['\"]?)[^\s,'\"]+\3"),
    re.compile(r"\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{12,}"),
)
SENSITIVE_NAMES = {".env", ".git", "secrets", "private", "credentials", "id_rsa", "id_ed25519"}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}


@dataclass(frozen=True)
class SanitizedExcerpt:
    text: str
    included_files: tuple[str, ...]
    rejected_files: tuple[str, ...]
    redactions: int


class ExternalContentSanitizer:
    def __init__(self, root: Path, private_paths: tuple[str, ...], max_chars: int) -> None:
        self.root = root.resolve()
        self.private_paths = {item.strip("/").casefold() for item in private_paths}
        self.max_chars = max_chars

    def sanitize_text(self, text: str) -> tuple[str, int]:
        redactions = 0
        for pattern in SECRET_PATTERNS:
            text, count = pattern.subn("[REDACTED]", text)
            redactions += count
        return text, redactions

    def resolve_allowed(self, candidate: Path) -> tuple[Path, Path]:
        lexical = candidate if candidate.is_absolute() else self.root / candidate
        resolved = lexical.resolve()
        relative = resolved.relative_to(self.root)
        lexical_relative = lexical.absolute().relative_to(self.root)
        for path in (relative, lexical_relative):
            parts = {part.casefold() for part in path.parts}
            name = path.name.casefold()
            private = any(path.as_posix().casefold() == item or path.as_posix().casefold().startswith(item + "/") or item in parts for item in self.private_paths)
            if private or parts & SENSITIVE_NAMES or any(part.startswith(".env") or part.startswith("credentials") for part in parts) or path.suffix.lower() in SENSITIVE_SUFFIXES:
                raise ValueError("Caminho privado")
        if not resolved.is_file():
            raise ValueError("Arquivo inexistente")
        return resolved, relative

    def build_excerpt(self, requested_paths: list[Path]) -> SanitizedExcerpt:
        included, rejected, chunks = [], [], []
        redactions = 0
        remaining = self.max_chars
        for candidate in requested_paths:
            try:
                resolved, relative = self.resolve_allowed(candidate)
                label = relative.as_posix()
                if label in included:
                    continue
                header = f"\n--- {label} ---\n"
                # Reject oversized input rather than cutting a credential in half.
                with resolved.open("rb") as source:
                    raw = source.read(self.max_chars * 4 + 1)
                if len(raw) > self.max_chars * 4:
                    raise ValueError("Arquivo muito grande")
                content = raw.decode("utf-8")
                if "\0" in content:
                    raise ValueError("Arquivo binário")
                safe, count = self.sanitize_text(content)
                chunk = header + safe
                if len(chunk) > remaining:
                    raise ValueError("Limite de contexto de arquivos")
            except (OSError, ValueError, RuntimeError):
                try:
                    label = candidate.relative_to(self.root).as_posix() if candidate.is_absolute() else candidate.as_posix()
                except ValueError:
                    label = candidate.name
                rejected.append(label)
                continue
            chunks.append(chunk)
            included.append(label)
            remaining -= len(chunk)
            redactions += count
        return SanitizedExcerpt("".join(chunks), tuple(included), tuple(rejected), redactions)
