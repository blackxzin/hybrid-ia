"""Opt-in conversation persistence using private, atomic files."""
import json
import os
from pathlib import Path
import re
import tempfile

from providers.types import ChatMessage


def session_path(root: Path, name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise ValueError("Nome da sessão: use até 64 letras, números, _ ou -")
    return root / "data" / "sessions" / (name + ".json")


def load_session(path):
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError()
        messages = [ChatMessage(**item) for item in data]
        if any(item.role not in ("user", "assistant") or not isinstance(item.content, str) for item in messages):
            raise ValueError()
        return messages[-20:]
    except (ValueError, TypeError) as exc:
        raise ValueError("Histórico de sessão inválido") from exc


def save_session(path, messages, sanitizer):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [{"role": item.role, "content": sanitizer.sanitize_text(item.content)[0]} for item in messages[-20:]]
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".session-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            json.dump(data, target, ensure_ascii=False)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
