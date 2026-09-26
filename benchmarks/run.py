"""Comparable runs with isolated memory; generated code is never executed."""
from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, replace
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Settings
from core.orchestrator import Orchestrator
from providers.types import ProviderError


def assess(answer):
    blocks = re.findall(r"```(?:python|py)\s*\n(.*?)```", answer, re.S)
    source = "\n".join(blocks) if blocks else answer
    try:
        tree = ast.parse(source)
        syntax = True
        definitions = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
    except SyntaxError:
        syntax, definitions = False, []
    return {"python_syntax_valid": syntax, "definitions": definitions, "functional_quality": "not_evaluated", "generated_code_executed": False}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Autoriza inferência local e externa nos modos selecionados")
    parser.add_argument("--modes", nargs="+", choices=["local", "hybrid", "expert"], default=["local", "hybrid", "expert"])
    parser.add_argument("--skills", nargs="+", choices=["none", "auto", "minimal", "debug", "security"], default=["auto"])
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--task", action="append", help="ID de tarefa; repetível")
    args = parser.parse_args(argv)
    if not 1 <= args.repeat <= 10:
        parser.error("--repeat deve estar entre 1 e 10")
    tasks = json.loads((ROOT / "benchmarks" / "tasks.json").read_text(encoding="utf-8"))
    if args.task:
        unknown = set(args.task) - {task["id"] for task in tasks}
        if unknown:
            parser.error("ID de tarefa desconhecido")
        tasks = [task for task in tasks if task["id"] in args.task]
    if not args.live:
        print(json.dumps({"live": False, "modes": args.modes, "skills": args.skills, "runs": len(tasks) * len(args.modes) * len(args.skills) * args.repeat, "tasks": tasks}, ensure_ascii=False, indent=2))
        return 0
    settings = Settings.from_env(ROOT)
    output = ROOT / "reports" / f"benchmark-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S-%f')}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"created_at": datetime.now(UTC).isoformat(), "settings": {"local_model": settings.local_model, "planner_model": settings.planner_model, "reviewer_model": settings.reviewer_model, "router_configured": bool(settings.router9_api_key) and settings.router9_enabled}, "cost": None, "cost_note": "Preços não configurados; nenhum custo monetário inferido", "results": []}
    failed = False
    with tempfile.TemporaryDirectory(prefix="hybrid-benchmark-") as directory:
        isolated = replace(settings, project_root=Path(directory), memory_enabled=False)
        for task in tasks:
            for mode in args.modes:
                for skill in args.skills:
                    for repeat in range(args.repeat):
                        row = {"task": task["id"], "category": task["category"], "requested_mode": mode, "skill": skill, "repeat": repeat}
                        try:
                            result = Orchestrator(isolated).run(task["request"], mode=mode, skill=skill)
                            row.update(answer=result.answer, metrics=asdict(result.metrics), assessment=assess(result.answer))
                            if result.metrics.status != "completed":
                                failed = True
                        except (ProviderError, ValueError, OSError) as error:
                            row.update(error=str(error) if not isinstance(error, OSError) else "Falha de persistência local")
                            failed = True
                        report["results"].append(row)
                        # Checkpoint every task; interruption does not discard completed runs.
                        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
