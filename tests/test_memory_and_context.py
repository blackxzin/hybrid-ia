import tempfile
import unittest
from pathlib import Path

from core.context_manager import ContextManager
from core.memory import TechnicalMemory
from providers.types import ChatMessage


class MemoryAndContextTests(unittest.TestCase):
    def test_memory_persists_structured_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            memory = TechnicalMemory()
            memory.add("architectural_decisions", "Qwen é executor principal")
            memory.add("test_results", "9 testes passaram")
            memory.save(path)
            loaded = TechnicalMemory.load(path)
            self.assertIn("Qwen é executor", loaded.compact_text())
            self.assertIn("9 testes", loaded.compact_text())

    def test_context_drops_old_history_to_fit_budget(self) -> None:
        manager = ContextManager(100)
        history = [ChatMessage("user", "x" * 200) for _ in range(4)]
        built = manager.build("pedido", history, TechnicalMemory())
        self.assertLessEqual(built.estimated_tokens, 100)
        self.assertGreater(built.dropped_messages, 0)
