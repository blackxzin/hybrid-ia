"""Loopback-only web UI with per-process bearer authentication."""
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading

from core.orchestrator import Orchestrator
from core.patches import PatchManager
from core.project_tools import ProjectTools
from core.skills import catalog, select_skill
from core.session import load_session, save_session, session_path
from providers.models import discover, select
from providers.streaming import Cancellation, Cancelled
from providers.types import ChatMessage, ProviderError

UI = Path(__file__).resolve().parents[1] / "ui"


def make_server(settings, port=8765, registry_settings=None):
    registry_settings = registry_settings or settings
    token = secrets.token_urlsafe(32)
    busy = threading.Lock()
    jobs = {}
    previews = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send_headers(self, status=200, content_type="application/json; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()

        def reply(self, data, status=200):
            self.send_headers(status)
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

        def authorized(self):
            expected = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != expected:
                return False
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + expected:
                return False
            return secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token)

        def do_GET(self):
            if self.path in ("/", "/app.js", "/style.css"):
                if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
                    return self.reply({"error": "Host recusado"}, 403)
                name = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}[self.path]
                mime = {"html": "text/html", "js": "text/javascript", "css": "text/css"}[name.rsplit(".", 1)[1]]
                self.send_headers(content_type=mime + "; charset=utf-8")
                self.wfile.write((UI / name).read_bytes())
                return
            if not self.authorized():
                return self.reply({"error": "Acesso recusado; abra a URL mostrada no terminal"}, 403)
            if self.path == "/api/models":
                return self.reply(discover(registry_settings))
            if self.path == "/api/skills":
                return self.reply({"skills": catalog(settings.project_root)})
            if self.path == "/api/sessions":
                folder = settings.project_root / "data" / "sessions"
                return self.reply({"sessions": sorted(path.stem for path in folder.glob("*.json"))[:100]})
            return self.reply({"error": "Rota inexistente"}, 404)

        def do_POST(self):
            if not self.authorized():
                return self.reply({"error": "Acesso recusado"}, 403)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1_000_000:
                    raise ValueError("Corpo inválido ou grande demais")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("Objeto JSON esperado")
                if self.path == "/api/cancel":
                    job = jobs.get(body.get("id"))
                    if job:
                        job.cancel()
                    return self.reply({"cancel_requested": job is not None})
                if not busy.acquire(blocking=False):
                    return self.reply({"error": "Aguarde a tarefa atual terminar"}, 409)
                try:
                    if self.path == "/api/chat":
                        return self.chat(body)
                    if self.path == "/api/session":
                        path = session_path(settings.project_root, body.get("name", ""))
                        return self.reply({"messages": [asdict(item) for item in load_session(path)]})
                    if self.path == "/api/skill":
                        name, content = select_skill("", self.string(body, "name"), settings.project_root)
                        return self.reply({"name": name, "content": content})
                    if self.path == "/api/search":
                        return self.reply(ProjectTools(settings).search(self.string(body, "query")))
                    if self.path == "/api/patch/preview":
                        patch = self.string(body, "patch")
                        preview = PatchManager(settings).preview(patch)
                        previews.clear()
                        previews[preview["id"]] = patch
                        return self.reply({key: preview[key] for key in ("id", "files", "diff")})
                    if self.path == "/api/patch/apply":
                        if body.get("confirm") is not True:
                            raise ValueError("Confirme a aplicação da prévia")
                        key = self.string(body, "id")
                        if key not in previews:
                            raise ValueError("Gere uma nova prévia")
                        result = PatchManager(settings).apply(previews.pop(key), key)
                        result["check"] = ProjectTools(settings).check("unittest" if body.get("allow_exec") is True else "syntax")
                        return self.reply(result)
                    return self.reply({"error": "Rota inexistente"}, 404)
                finally:
                    busy.release()
            except (ValueError, TypeError, KeyError, ProviderError, OSError):
                self.reply({"error": "Pedido inválido, arquivo alterado ou serviço indisponível. Confira os campos e tente novamente."}, 400)

        @staticmethod
        def string(body, key):
            value = body.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Campo de texto obrigatório")
            return value

        def chat(self, body):
            request = self.string(body, "request")
            job_id = self.string(body, "id")
            selected = select(registry_settings, body["model"]) if body.get("model") else settings
            mode = body.get("mode", "local")
            if mode not in ("local", "hybrid", "expert", "fast", "auto"):
                raise ValueError("Modo inválido")
            path = session_path(settings.project_root, body["session"]) if body.get("session") else None
            history = load_session(path) if path else []
            skill = body.get("skill", "auto")
            select_skill(request, skill, settings.project_root)
            app = Orchestrator(selected)
            context = ProjectTools(settings).search(request)["context"] if body.get("auto_context") else ""
            cancel = Cancellation()
            jobs[job_id] = cancel
            self.send_headers(content_type="application/x-ndjson; charset=utf-8")
            def event(kind, **data):
                self.wfile.write((json.dumps({"type": kind, **data}, ensure_ascii=False) + "\n").encode())
                self.wfile.flush()
            try:
                event("start", model=selected.local_model)
                result = app.run(request, mode=mode, history=history, local_context=context, on_token=lambda text: event("token", text=text), cancel=cancel, skill=skill)
                cancel.check()
                if path:
                    history.extend([ChatMessage("user", request), ChatMessage("assistant", result.answer)])
                    save_session(path, history, app.sanitizer)
                event("done", answer=result.answer, metrics=asdict(result.metrics))
            except Cancelled:
                event("cancelled")
            except (ProviderError, ValueError, OSError):
                try:
                    event("error", error="Não foi possível concluir a geração; confira o servidor e o limite de contexto.")
                except OSError:
                    cancel.cancel()
            finally:
                jobs.pop(job_id, None)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server, token


def serve(settings, port=8765, registry_settings=None):
    server, token = make_server(settings, port, registry_settings)
    print(f"Painel local: http://127.0.0.1:{server.server_port}/#token={token}", flush=True)
    print("Ctrl+C encerra. Cancelamento é verificado entre eventos; chamadas sem eventos aguardam o timeout HTTP.", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
