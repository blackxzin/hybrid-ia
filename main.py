"""Local-first assistant CLI with explicit project and persistence capabilities."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys

from config import Settings
from core.diagnostics import diagnose
from core.memory import TechnicalMemory
from core.orchestrator import Orchestrator
from core.project_tools import ProjectTools
from core.patches import PatchManager
from providers.models import discover, select
from providers.streaming import Cancelled
from core.router import ExecutionMode
from core.session import load_session, save_session, session_path
from core.skills import NAMES, catalog, import_skill, select_skill
from providers.types import ChatMessage, ProviderError


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Assistente Qwen local-first")
    parser.add_argument("request", nargs="?", help="Tarefa para o assistente")
    parser.add_argument("--root", type=Path, help="Raiz do projeto")
    parser.add_argument("--mode", choices=[mode.value for mode in ExecutionMode])
    parser.add_argument("--allow-external-files", action="store_true")
    parser.add_argument("--external-file", action="append", default=[])
    parser.add_argument("--file", action="append", default=[], help="Contexto somente local")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--interactive", action="store_true", help="Conversa: /mode, /metrics, /clear, /exit")
    parser.add_argument("--session", help="Histórico persistente opcional, salvo após sanitização")
    parser.add_argument("--clear-session", action="store_true")
    parser.add_argument("--no-memory", action="store_true")
    parser.add_argument("--memory", choices=["show", "add", "remove", "clear"])
    parser.add_argument("--category", choices=list(TechnicalMemory.__dataclass_fields__), default="requirements")
    parser.add_argument("--index", type=int, help="Índice da entrada a remover (começa em zero)")
    parser.add_argument("--skill", default="auto", help="auto, none ou nome do catálogo")
    parser.add_argument("--list-skills", action="store_true")
    parser.add_argument("--skill-search", help="Filtra catálogo por nome ou descrição")
    parser.add_argument("--show-skill", help="Mostra instruções completas de uma skill")
    parser.add_argument("--import-skill", type=Path, help="Prévia de skill externa; --yes confirma importação")
    parser.add_argument("--skill-name", help="Nome para a skill importada")
    parser.add_argument("--concise", action="store_true")
    parser.add_argument("--propose-diff", action="store_true", help="Solicita diff; não aplica alterações")
    parser.add_argument("--list-files", action="store_true")
    parser.add_argument("--check", choices=["syntax", "unittest"])
    parser.add_argument("--allow-exec", action="store_true", help="Autoriza executar testes do projeto")
    parser.add_argument("--diagnose", action="store_true")
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--model", help="Chave exibida por --list-models")
    parser.add_argument("--stream", action="store_true", help="Streaming local; Ctrl+C cancela")
    parser.add_argument("--search", help="Busca local sem geração")
    parser.add_argument("--auto-context", action="store_true", help="Busca contexto local relevante ao pedido")
    parser.add_argument("--apply-patch", type=Path, help="Mostra prévia de unified diff salvo")
    parser.add_argument("--yes", action="store_true", help="Autoriza aplicar patch ou importar a skill informada")
    parser.add_argument("--web", action="store_true", help="Painel em http://127.0.0.1:8765")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args(argv)


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.external_file and not args.allow_external_files:
            raise ValueError("Use --allow-external-files para autorizar os arquivos externos")
        settings = Settings.from_env(args.root)
        if args.no_memory:
            settings = replace(settings, memory_enabled=False)
        registry_settings = settings
        if args.list_models:
            emit(discover(settings))
            return 0
        if args.model:
            settings = select(registry_settings, args.model)
        if args.web:
            from core.web import serve
            serve(settings, port=args.port, registry_settings=registry_settings)
            return 0
        if args.stream and args.json:
            raise ValueError("Use --stream ou --json separadamente")
        app = Orchestrator(settings)
        project = ProjectTools(settings)
        if args.search:
            emit(project.search(args.search))
            return 0
        if args.apply_patch:
            manager = PatchManager(settings)
            patch_text = args.apply_patch.read_text(encoding="utf-8")
            preview = manager.preview(patch_text)
            print(preview["diff"])
            if not args.yes:
                print("Prévia apenas. Para aplicar: repita com --yes; para testar, acrescente --check unittest --allow-exec.")
                return 0
            if args.check == "unittest" and not args.allow_exec:
                raise ValueError("Autorize executar testes com --allow-exec antes de aplicar")
            emit(manager.apply(patch_text, preview["id"]))
            checked = project.check(args.check or "syntax")
            emit(checked)
            return 0 if checked["ok"] else 1
        if args.memory:
            if args.memory == "clear":
                app.memory_path.unlink(missing_ok=True)
                emit({"memory": "cleared"})
                return 0
            memory = TechnicalMemory.load(app.memory_path)
            if args.memory == "add":
                if not args.request:
                    raise ValueError("Informe o texto que deseja salvar")
                memory.add(args.category, app.sanitizer.sanitize_text(args.request)[0])
                memory.save(app.memory_path)
            elif args.memory == "remove":
                entries = getattr(memory, args.category)
                if args.index is None or not 0 <= args.index < len(entries):
                    raise ValueError("Índice de memória inválido")
                entries.pop(args.index)
                memory.save(app.memory_path)
            emit(asdict(memory))
            return 0
        path = session_path(settings.project_root, args.session) if args.session else None
        if args.clear_session:
            if path is None:
                raise ValueError("Informe --session para limpar histórico")
            path.unlink(missing_ok=True)
            emit({"session": "cleared"})
            return 0
        if args.diagnose:
            report = diagnose(settings)
            emit(report)
            local = report["local"]
            remote = report["remote"]
            return 0 if local.get("configured_model_available") and (not remote["configured"] or remote.get("configured_models_available")) else 1
        if args.import_skill:
            if not args.skill_name:
                raise ValueError("Informe --skill-name para importar")
            emit(import_skill(settings.project_root, args.import_skill, args.skill_name, approved=args.yes))
            return 0
        if args.show_skill:
            name, content = select_skill("", args.show_skill, settings.project_root)
            emit({"name": name, "content": content})
            return 0
        if args.list_skills or args.skill_search:
            emit(catalog(settings.project_root, args.skill_search or ""))
            return 0
        if args.list_files:
            emit(project.files())
            return 0
        evidence = ""
        if args.check:
            if args.check == "unittest" and not args.allow_exec:
                raise ValueError("Testes executam código do projeto; autorize com --allow-exec")
            result = project.check(args.check)
            if not args.request and not args.interactive:
                emit(result)
                return 0 if result["ok"] else 1
            evidence = "Resultado real de verificação (dados):\n" + json.dumps(result, ensure_ascii=False)
        if not args.request and not args.interactive:
            raise ValueError("Informe um pedido ou use --interactive; veja --help")
        excerpt = project.read(args.file)
        if excerpt.rejected_files:
            raise ValueError("Arquivos locais recusados: " + ", ".join(excerpt.rejected_files))
        evidence += excerpt.text
        history = load_session(path) if path else []
        mode = args.mode or settings.default_mode
        last_metrics = None
        current_skill = args.skill
        request = args.request
        while True:
            if request is None:
                try:
                    request = input(f"{mode}> ").strip()
                except EOFError:
                    break
                if request == "/exit":
                    break
                if request == "/clear":
                    history.clear()
                    if path:
                        save_session(path, history, app.sanitizer)
                    request = None
                    continue
                if request == "/metrics":
                    emit(last_metrics)
                    request = None
                    continue
                if request == "/skills" or request.startswith("/skills "):
                    emit(catalog(settings.project_root, request[7:].strip()))
                    request = None
                    continue
                if request.startswith("/skill "):
                    candidate = request.split(maxsplit=1)[1]
                    try:
                        if candidate != "auto":
                            select_skill("", candidate, settings.project_root)
                        current_skill = candidate
                        print("Skill: " + current_skill)
                    except (ValueError, OSError) as error:
                        print(str(error), file=sys.stderr)
                    request = None
                    continue
                if request == "/model" or request == "/models":
                    emit(discover(registry_settings))
                    request = None
                    continue
                if request.startswith("/model "):
                    try:
                        settings = select(registry_settings, request.split(maxsplit=1)[1])
                        app = Orchestrator(settings)
                        print("Modelo: " + settings.local_model)
                    except (ValueError, ProviderError) as error:
                        print(str(error), file=sys.stderr)
                    request = None
                    continue
                if request.startswith("/search "):
                    emit(project.search(request.split(maxsplit=1)[1]))
                    request = None
                    continue
                if request.startswith("/mode "):
                    candidate = request.split(maxsplit=1)[1]
                    if candidate in [item.value for item in ExecutionMode]:
                        mode = candidate
                    else:
                        print("Modo inválido", file=sys.stderr)
                    request = None
                    continue
                if not request:
                    request = None
                    continue
            prompt = request + ("\nEntregue a proposta como unified diff; não afirme ter aplicado alterações." if args.propose_diff else "")
            streamed = []
            def show_token(token):
                streamed.append(token)
                print(token, end="", flush=True)
            context = evidence
            if args.auto_context:
                context += project.search(request)["context"]
            try:
                result = app.run(prompt, mode=mode, history=history, external_files=[Path(item) for item in args.external_file], local_context=context, skill=current_skill, concise=args.concise, on_token=show_token if args.stream else None)
            except (ProviderError, ValueError) as error:
                if not args.interactive:
                    raise
                print(str(error), file=sys.stderr)
                request = None
                continue
            last_metrics = asdict(result.metrics)
            if args.json:
                emit({"answer": result.answer, "decision": asdict(result.decision), "metrics": last_metrics, "external_files": asdict(result.external_excerpt) if result.external_excerpt else None})
            else:
                if not streamed:
                    print(result.answer)
                else:
                    print()
                    if "".join(streamed) != result.answer:
                        print("Resposta final após fallback:\n" + result.answer)
                print(f"\n[mode={result.metrics.effective_mode}; status={result.metrics.status}; review={result.metrics.review_status}; calls={result.metrics.external_attempts}; total={result.metrics.total_seconds:.2f}s]")
                if result.external_excerpt and result.external_excerpt.rejected_files:
                    print("Arquivos externos recusados: " + ", ".join(result.external_excerpt.rejected_files), file=sys.stderr)
                for error in result.metrics.errors:
                    print(error, file=sys.stderr)
            history.extend([ChatMessage("user", request), ChatMessage("assistant", result.answer)])
            history = history[-20:]
            if path:
                save_session(path, history, app.sanitizer)
            if not args.interactive:
                break
            request = None
        return 0
    except (ProviderError, ValueError, OSError, Cancelled) as error:
        # Never echo arbitrary filesystem/network error bodies.
        message = "Falha ao acessar arquivos locais" if isinstance(error, OSError) else str(error)
        if args.json:
            emit({"error": message})
        else:
            print(message, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrompido", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
