"""Exercise every acceptance contract using trusted fixture implementations."""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

from benchmarks.functional import CASES, RUNNER

FIXTURES = {
    'simple_clamp': 'def clamp(x, lo, hi):\n if lo > hi: raise ValueError()\n return max(lo, min(x, hi))',
    'medium_debug': 'def average(values):\n values = list(values)\n if not values: raise ValueError()\n return sum(values) / len(values)',
    'simple_unique': 'def unique(values): return list(dict.fromkeys(values))',
    'medium_json': '''import json
def parse_object(text):
    try: value = json.loads(text)
    except ValueError: raise ValueError('invalid') from None
    if not isinstance(value, dict): raise ValueError('object expected')
    return value
''',
    'complex_refactor_plan': '''from pathlib import Path
def validate_path(root, candidate):
    root = Path(root).resolve()
    path = Path(candidate)
    if not path.is_absolute(): path = root / path
    result = path.resolve()
    for relative in (path.relative_to(root), result.relative_to(root)):
        if any(p.startswith('.env') or p in ('.git','secrets') for p in relative.parts) or relative.suffix in ('.pem','.key'): raise ValueError('private')
    if not result.is_file(): raise ValueError('missing')
    return result
''',
    'complex_budget': '''class Budget:
    def __init__(self, max_calls, max_tokens):
        if min(max_calls,max_tokens)<0: raise ValueError()
        self.max_calls, self.max_tokens = max_calls,max_tokens
        self.calls = self.reserved_tokens = 0
    def reserve(self, tokens):
        if tokens<0 or self.calls>=self.max_calls or self.reserved_tokens+tokens>self.max_tokens: raise ValueError()
        self.calls+=1
        self.reserved_tokens+=tokens
''',
}


class FunctionalContractsTests(unittest.TestCase):
    def test_all_contracts_accept_valid_fixture_and_reject_missing_implementation(self):
        self.assertEqual(set(FIXTURES), set(CASES))
        for task, source in FIXTURES.items():
            for candidate, expected in ((source, 'passed'), ('pass', 'failed')):
                with self.subTest(task=task, expected=expected):
                    output = io.StringIO()
                    with patch('sys.stdin', io.StringIO(json.dumps({'source': candidate, 'cases': CASES[task]}))), contextlib.redirect_stdout(output):
                        exec(RUNNER, {})
                    result = json.loads(output.getvalue())
                    self.assertEqual(result['functional_quality'], expected)
                    if expected == 'passed':
                        self.assertGreater(result['passed_checks'], 3)
