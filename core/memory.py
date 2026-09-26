"""Small structured technical memory persisted locally as JSON."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class MemoryEntry:
    category: str
    text: str
    created_at: str


@dataclass
class TechnicalMemory:
    requirements: list[MemoryEntry] = field(default_factory=list)
    architectural_decisions: list[MemoryEntry] = field(default_factory=list)
    errors: list[MemoryEntry] = field(default_factory=list)
    modified_files: list[MemoryEntry] = field(default_factory=list)
    commands: list[MemoryEntry] = field(default_factory=list)
    test_results: list[MemoryEntry] = field(default_factory=list)
    todos: list[MemoryEntry] = field(default_factory=list)
    constraints: list[MemoryEntry] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "TechnicalMemory":
        if not path.is_file():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            result = cls(**{name: [MemoryEntry(**entry) for entry in raw.get(name, [])] for name in cls.__dataclass_fields__})
            for name in cls.__dataclass_fields__:
                for entry in getattr(result, name):
                    if not all(isinstance(value, str) for value in (entry.text, entry.category, entry.created_at)):
                        raise ValueError()
            return result
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Memória inválida; consulte ou limpe com --memory clear") from exc

    def add(self, category: str, text: str, *, limit: int = 20) -> None:
        if category not in self.__dataclass_fields__ or limit < 1:
            raise ValueError("Categoria ou limite de memória inválido")
        text = text.strip()
        if not text:
            return
        entries = getattr(self, category)
        if entries and entries[-1].text == text:
            return
        entries.append(MemoryEntry(category, text.strip(), datetime.now(UTC).isoformat()))
        del entries[:-limit]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".memory-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as target:
                target.write(json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n")
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def compact_text(self, max_chars: int = 5_000) -> str:
        if max_chars <= 0:
            return ""
        lines: list[str] = []
        labels = {"requirements": "Requisito", "architectural_decisions": "Decisão", "errors": "Erro", "modified_files": "Arquivo", "commands": "Comando", "test_results": "Teste", "todos": "TODO", "constraints": "Restrição"}
        for category in self.__dataclass_fields__:
            for entry in getattr(self, category)[-5:]:
                lines.append(f"{labels[category]}: {entry.text}")
        return "\n".join(lines)[-max_chars:]
