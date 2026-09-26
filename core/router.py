"""Conservative task classification and mode selection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TaskClass(StrEnum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class ExecutionMode(StrEnum):
    AUTO = "auto"
    LOCAL = "local"
    HYBRID = "hybrid"
    EXPERT = "expert"
    FAST = "fast"


@dataclass(frozen=True)
class RouteDecision:
    task_class: TaskClass
    mode: ExecutionMode
    reasons: tuple[str, ...]


COMPLEX_TERMS = ("arquitetura", "security", "segurança", "vulnerab", "projeto inteiro", "todos os arquivos", "migração", "grande refatora", "race condition", "path traversal")
MEDIUM_TERMS = ("debug", "erro", "bug", "refator", "vários arquivos", "several files", "testes falhando", "stack trace")


def classify_task(request: str) -> TaskClass:
    # `ValueError` is a Python identifier, not evidence that the user is debugging.
    normalized = request.casefold().replace("valueerror", "")
    if len(request) > 2_000 or any(term in normalized for term in COMPLEX_TERMS):
        return TaskClass.COMPLEX
    if len(request) > 500 or any(term in normalized for term in MEDIUM_TERMS):
        return TaskClass.MEDIUM
    return TaskClass.SIMPLE


def decide_route(request: str, requested_mode: str | ExecutionMode = ExecutionMode.AUTO, external_available: bool = False) -> RouteDecision:
    mode = ExecutionMode(requested_mode)
    task_class = classify_task(request)
    if mode is not ExecutionMode.AUTO:
        return RouteDecision(task_class, mode, ("modo explícito do usuário",))
    if task_class is TaskClass.SIMPLE:
        return RouteDecision(task_class, ExecutionMode.LOCAL, ("tarefa simples",))
    if not external_available:
        return RouteDecision(task_class, ExecutionMode.LOCAL, ("especialista externo não configurado",))
    if task_class is TaskClass.MEDIUM:
        return RouteDecision(task_class, ExecutionMode.HYBRID, ("debug/refatoração ou múltiplos arquivos",))
    return RouteDecision(task_class, ExecutionMode.EXPERT, ("tarefa complexa",))
