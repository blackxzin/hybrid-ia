import tempfile
import unittest
from pathlib import Path

from config import Settings
from core.orchestrator import Orchestrator
from providers.types import ChatMessage, Completion


class FakeLocal:
    def __init__(self) -> None:
        self.calls: list[list[ChatMessage]] = []

    def chat(self, messages: list[ChatMessage], **_: object) -> Completion:
        self.calls.append(messages)
        return Completion("local answer", "fake-qwen", 10, 5, 0.1, {"prompt_per_second": 10, "predicted_per_second": 5})

    def count_messages(self, messages: list[ChatMessage]) -> None:
        return None


class FakeRemote:
    configured = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[ChatMessage]]] = []

    def chat(self, model: str, messages: list[ChatMessage], **_: object) -> Completion:
        self.calls.append((model, messages))
        return Completion("APROVADO", model, 8, 3, 0.2)


class UnconfiguredRemote:
    configured = False


class OrchestratorTests(unittest.TestCase):
    def test_hybrid_uses_short_local_analysis_then_remote_then_local_final(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local, remote = FakeLocal(), FakeRemote()
            settings = Settings(project_root=root, router9_api_key="test-only")
            result = Orchestrator(settings, local=local, remote=remote).run("Debug este erro", mode="hybrid")
            self.assertEqual(result.answer, "local answer")
            self.assertEqual(len(local.calls), 2)
            self.assertEqual(len(remote.calls), 1)
            self.assertEqual(result.metrics.external_calls, 1)

    def test_expert_plans_implements_and_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local, remote = FakeLocal(), FakeRemote()
            settings = Settings(project_root=root, router9_api_key="test-only")
            result = Orchestrator(settings, local=local, remote=remote).run("Faça arquitetura", mode="expert")
            self.assertEqual(result.answer, "local answer")
            self.assertEqual(len(local.calls), 1)
            self.assertEqual(len(remote.calls), 2)
            self.assertEqual(result.metrics.external_calls, 2)

    def test_external_request_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local, remote = FakeLocal(), FakeRemote()
            settings = Settings(project_root=root, router9_api_key="test-only")
            result = Orchestrator(settings, local=local, remote=remote).run("Debug token=super-secret-value", mode="hybrid")
            remote_text = "\n".join(message.content for message in remote.calls[0][1])
            self.assertNotIn("super-secret-value", remote_text)
            self.assertGreater(result.metrics.external_redactions, 0)

    def test_unconfigured_hybrid_skips_auxiliary_local_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            local = FakeLocal()
            settings = Settings(project_root=Path(directory))
            result = Orchestrator(settings, local=local, remote=UnconfiguredRemote()).run("Debug este erro", mode="hybrid")
            self.assertEqual(len(local.calls), 1)
            self.assertEqual(result.metrics.external_calls, 0)
            self.assertIn("Fallback", result.metrics.errors[-1])
