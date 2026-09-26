import unittest

from core.router import ExecutionMode, TaskClass, classify_task, decide_route


class RouterTests(unittest.TestCase):
    def test_simple_is_local(self) -> None:
        decision = decide_route("Explique esta função curta.", "auto", external_available=True)
        self.assertEqual(decision.task_class, TaskClass.SIMPLE)
        self.assertEqual(decision.mode, ExecutionMode.LOCAL)

    def test_medium_uses_hybrid_only_when_configured(self) -> None:
        self.assertEqual(decide_route("Debug este erro e revise vários arquivos", "auto", True).mode, ExecutionMode.HYBRID)
        self.assertEqual(decide_route("Debug este erro", "auto", False).mode, ExecutionMode.LOCAL)

    def test_complex_uses_expert(self) -> None:
        self.assertEqual(classify_task("Faça a arquitetura e auditoria de segurança"), TaskClass.COMPLEX)
        self.assertEqual(decide_route("Faça a arquitetura e auditoria de segurança", "auto", True).mode, ExecutionMode.EXPERT)

    def test_value_error_does_not_turn_generation_into_debugging(self) -> None:
        self.assertEqual(classify_task("Escreva uma função que lance ValueError."), TaskClass.SIMPLE)

    def test_path_traversal_is_complex(self) -> None:
        self.assertEqual(classify_task("Implemente defesa contra path traversal."), TaskClass.COMPLEX)
