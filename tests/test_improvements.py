import contextlib
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from config import Settings
from core.context_manager import ContextManager
from core.memory import TechnicalMemory
from core.orchestrator import Orchestrator
from core.project_tools import ProjectTools
from core.session import load_session, save_session, session_path
from main import main
from providers.http import validate_completion
from providers.router9 import Router9Client
from providers.types import ChatMessage, Completion, ProviderError
from security.sanitizer import ExternalContentSanitizer
from tests.test_orchestrator import FakeLocal, FakeRemote


class ImprovingRemote(FakeRemote):
    def chat(self, model, messages, **kwargs):
        self.calls.append((model, messages))
        text = ["Etapas: implementar; testar", "Corrija o caso vazio", "APROVADO"][len(self.calls) - 1]
        return Completion(text, model, 8, 3, 0.01)


class BrokenRemote(FakeRemote):
    def chat(self, *args, **kwargs):
        raise ProviderError("9Router HTTP 503")


class ImprovementsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = Settings(project_root=self.root)
        self.sanitizer = ExternalContentSanitizer(self.root, ("nested/private",), 1000)

    def app(self, remote=None, local=None, **changes):
        return Orchestrator(replace(self.settings, **changes), local=local or FakeLocal(), remote=remote or FakeRemote())

    def test_invalid_context_settings(self):
        with self.assertRaises(ValueError):
            replace(self.settings, local_context_tokens=1024)

    def test_invalid_budget_settings(self):
        with self.assertRaises(ValueError):
            replace(self.settings, max_external_calls=-1)

    def test_oversized_request_without_tokenizer_never_generates(self):
        local = FakeLocal()
        with self.assertRaises(ProviderError):
            self.app(local=local).run("漢" * 3000, mode="local")
        self.assertFalse(local.calls)

    def test_memory_zero_budget(self):
        memory = TechnicalMemory()
        memory.add("constraints", "must not appear")
        self.assertEqual(memory.compact_text(0), "")

    def test_memory_invalid_category(self):
        with self.assertRaises(ValueError):
            TechnicalMemory().add("save", "invalid")

    def test_no_automatic_request_persistence(self):
        self.app().run("token=very-secret", mode="local")
        self.assertFalse((self.root / "data" / "technical-memory.json").exists())
        self.assertNotIn("very-secret", (self.root / "logs" / "runs.jsonl").read_text())

    def test_memory_disabled_ignores_corrupted_file(self):
        path = self.root / "data" / "technical-memory.json"
        path.parent.mkdir()
        path.write_text("corrupted")
        result = self.app(memory_enabled=False).run("hello", mode="local")
        self.assertEqual(result.answer, "local answer")
        self.assertEqual(path.read_text(), "corrupted")

    def test_expert_corrects_and_checks_final(self):
        local, remote = FakeLocal(), ImprovingRemote()
        result = self.app(local=local, remote=remote).run("arquitetura", mode="expert")
        self.assertEqual(len(remote.calls), 3)
        self.assertEqual(len(local.calls), 2)
        self.assertIn("Código original:\nlocal answer", local.calls[-1][0].content)
        self.assertEqual(result.metrics.review_status, "approved")

    def test_approval_must_be_exact(self):
        class Remote(FakeRemote):
            def chat(self, *args, **kwargs):
                result = super().chat(*args, **kwargs)
                return replace(result, content="APROVADO, mas há um bug")
        result = self.app(remote=Remote()).run("hello", mode="expert")
        self.assertEqual(result.metrics.review_status, "unresolved")
        self.assertEqual(result.metrics.status, "degraded")

    def test_budget_preserves_answer_and_marks_review_incomplete(self):
        result = self.app(remote=ImprovingRemote(), max_external_calls=2).run("hello", mode="expert")
        self.assertEqual(result.metrics.external_attempts, 2)
        self.assertEqual(result.answer, "local answer")
        self.assertEqual(result.metrics.review_status, "incomplete")

    def test_failed_remote_attempt_is_counted(self):
        result = self.app(remote=BrokenRemote()).run("hello", mode="fast")
        self.assertEqual(result.metrics.external_attempts, 1)
        self.assertEqual(result.metrics.external_calls, 0)
        self.assertEqual(result.metrics.effective_mode, "local")

    def test_zero_token_budget_skips_remote(self):
        remote = FakeRemote()
        result = self.app(remote=remote, external_token_budget=0).run("hello", mode="expert")
        self.assertFalse(remote.calls)
        self.assertEqual(result.metrics.status, "degraded")

    def test_private_context_remains_local(self):
        remote = FakeRemote()
        self.app(remote=remote).run("hello", mode="expert", local_context="private function")
        self.assertFalse(remote.calls)

    def test_local_analysis_secrets_are_redacted(self):
        class SecretLocal(FakeLocal):
            def chat(self, *args, **kwargs):
                return replace(super().chat(*args, **kwargs), content='ROUTER9_API_KEY="never-send-this"')
        remote = FakeRemote()
        self.app(remote=remote, local=SecretLocal()).run("hello", mode="hybrid")
        self.assertNotIn("never-send-this", str(remote.calls))

    def test_fast_includes_authorized_file(self):
        (self.root / "test.py").write_text("print('authorized')")
        remote = FakeRemote()
        self.app(remote=remote).run("hello", mode="fast", external_files=[Path("test.py")])
        self.assertIn("authorized", str(remote.calls))

    def test_exact_counter_rejects_before_generation(self):
        local = FakeLocal()
        local.count_messages = lambda messages: 99999
        with self.assertRaises(ProviderError):
            self.app(local=local).run("hello", mode="local")
        self.assertFalse(local.calls)

    def test_nested_private_path(self):
        path = self.root / "nested" / "private" / "a.py"
        path.parent.mkdir(parents=True)
        path.write_text("private")
        self.assertFalse(self.sanitizer.build_excerpt([path]).included_files)

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as outside:
            path = Path(outside) / "file.py"
            path.write_text("outside")
            (self.root / "link.py").symlink_to(path)
            self.assertFalse(self.sanitizer.build_excerpt([Path("link.py")]).included_files)

    def test_case_insensitive_private_directory(self):
        path = self.root / "SECRETS" / "a.py"
        path.parent.mkdir()
        path.write_text("secret")
        self.assertFalse(self.sanitizer.build_excerpt([path]).included_files)

    def test_env_directory_blocked(self):
        path = self.root / ".env.local" / "a.py"
        path.parent.mkdir()
        path.write_text("secret")
        self.assertFalse(self.sanitizer.build_excerpt([path]).included_files)

    def test_total_limit_includes_headers(self):
        (self.root / "a.py").write_text("x" * 1000)
        self.assertFalse(self.sanitizer.build_excerpt([Path("a.py")]).included_files)

    def test_secret_variants(self):
        for text, secret in [('"api_key": "secret with spaces"', "secret with spaces"), ('Authorization: Bearer short', "short"), ('ROUTER9_API_KEY=abcdef', "abcdef"), ('sk-proj-abcdefghijklmnop', "abcdefghijklmnop"), ('postgres://user:password@host', "password"), ('-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----', "secret")]:
            with self.subTest(text=text):
                self.assertNotIn(secret, self.sanitizer.sanitize_text(text)[0])

    def test_malformed_completions_raise_provider_error(self):
        for data in ({}, {"choices": []}, {"choices": [{"message": {"content": ""}}]}, {"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": "invalid"}}):
            with self.assertRaises(ProviderError):
                validate_completion(data, "test")

    def test_sse_comments_done_and_trailing_whitespace(self):
        result = Router9Client._decode_payload(': heartbeat\nevent: message\ndata: {"choices":[{"delta":{"content":"ok"}}]}\ndata: [DONE]\n\n')
        self.assertEqual(len(result["_stream_chunks"]), 1)

    def test_scalar_json_is_invalid(self):
        with self.assertRaises(ProviderError):
            Router9Client._decode_payload('[]')

    def test_session_path_escape(self):
        with self.assertRaises(ValueError):
            session_path(self.root, "../secret")

    def test_session_persistence_redacts(self):
        path = session_path(self.root, "example")
        save_session(path, [ChatMessage("user", "token=hidden")], self.sanitizer)
        self.assertNotIn("hidden", load_session(path)[0].content)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_syntax_check_reports_real_error(self):
        (self.root / "broken.py").write_text("def broken(:")
        result = ProjectTools(self.settings).check("syntax")
        self.assertFalse(result["ok"])
        self.assertEqual(result["errors"][0]["file"], "broken.py")

    def test_cli_requires_execution_authorization(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--root", str(self.root), "--check", "unittest"]), 1)

    def test_cli_memory_crud(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--root", str(self.root), "--memory", "add", "token=hidden"]), 0)
            path = self.root / "data" / "technical-memory.json"
            self.assertNotIn("hidden", path.read_text())
            self.assertEqual(main(["--root", str(self.root), "--memory", "remove", "--index", "0"]), 0)
            self.assertFalse(TechnicalMemory.load(path).requirements)
            self.assertEqual(main(["--root", str(self.root), "--memory", "clear"]), 0)
            self.assertFalse(path.exists())

    def test_cli_default_mode_is_respected(self):
        app = self.app(default_mode="fast")
        self.assertEqual(app.run("hello").decision.mode, "fast")
