"""Small trusted, role-specific instructions selected without model permissions."""
from pathlib import Path

LIBRARY = Path(__file__).resolve().parents[1] / "skills"
NAMES = ("minimal", "debug", "security")


def select_skill(request: str, requested: str = "auto") -> tuple[str, str]:
    name = requested
    if name == "auto":
        text = request.casefold()
        name = "security" if any(word in text for word in ("segurança", "security", "vulnerab")) else "debug" if any(word in text for word in ("erro", "bug", "falha")) else "minimal"
    if name == "none":
        return name, ""
    if name not in NAMES:
        raise ValueError("Skill desconhecida")
    return name, (LIBRARY / f"{name}.md").read_text(encoding="utf-8")
