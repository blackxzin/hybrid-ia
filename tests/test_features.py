import contextlib
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from config import Settings
from core.patches import PatchManager
from core.project_tools import ProjectTools
from providers.models import discover, select
from providers.streaming import Cancellation, Cancelled, stream_completion
from providers.types import ProviderError
from benchmarks.functional import CASES, RUNNER, assess_functional
from main import main

DIFF = '--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n'


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = Settings(project_root=self.root)
        self.manager = PatchManager(self.settings)
        (self.root / 'a.py').write_text('x = 1\n')

    def test_patch_preview_does_not_write(self):
        self.assertEqual(self.manager.preview(DIFF)['files'], ['a.py'])
        self.assertEqual((self.root / 'a.py').read_text(), 'x = 1\n')

    def test_patch_apply_and_permissions(self):
        (self.root / 'a.py').chmod(0o755)
        self.manager.apply(DIFF, self.manager.preview(DIFF)['id'])
        self.assertEqual((self.root / 'a.py').read_text(), 'x = 2\n')
        self.assertEqual((self.root / 'a.py').stat().st_mode & 0o777, 0o755)

    def test_stale_patch_rejected(self):
        preview = self.manager.preview(DIFF)
        (self.root / 'a.py').write_text('x = 3\n')
        with self.assertRaises(ValueError):
            self.manager.apply(DIFF, preview['id'])

    def test_change_outside_hunk_invalidates_preview(self):
        (self.root / 'a.py').write_text('x = 1\ny = 1\n')
        preview = self.manager.preview(DIFF)
        (self.root / 'a.py').write_text('x = 1\ny = 2\n')
        with self.assertRaises(ValueError):
            self.manager.apply(DIFF, preview['id'])

    def test_patch_private_and_escape_paths(self):
        for name in ('../escape.py', '/tmp/a.py', '.env', '.env.local', '.git/config', '.codex/instructions', 'private/a.py', 'data/a.py', 'a.key'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.manager.target(name)

    def test_patch_symlink_rejected(self):
        (self.root / 'link.py').symlink_to(self.root / 'a.py')
        with self.assertRaises(ValueError):
            self.manager.target('link.py')

    def test_create_and_delete(self):
        diff = '--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+hello\n'
        self.manager.apply(diff, self.manager.preview(diff)['id'])
        self.assertEqual((self.root / 'new.py').read_text(), 'hello\n')
        diff = '--- a/new.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-hello\n'
        self.manager.apply(diff, self.manager.preview(diff)['id'])
        self.assertFalse((self.root / 'new.py').exists())

    def test_multiple_hunks(self):
        (self.root / 'a.py').write_text('a\nb\nc\n')
        diff = '--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n+A\n@@ -3 +3 @@\n-c\n+C\n'
        self.manager.apply(diff, self.manager.preview(diff)['id'])
        self.assertEqual((self.root / 'a.py').read_text(), 'A\nb\nC\n')

    def test_no_newline(self):
        (self.root / 'a.py').write_text('x = 1')
        diff = '--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x = 1\n\\ No newline at end of file\n+x = 2\n\\ No newline at end of file\n'
        self.manager.apply(diff, self.manager.preview(diff)['id'])
        self.assertEqual((self.root / 'a.py').read_text(), 'x = 2')

    def test_malformed_hunk(self):
        with self.assertRaises(ValueError):
            self.manager.preview(DIFF.replace('@@ -1 +1 @@', '@@ -1,2 +1 @@'))

    def test_all_files_validated_before_write(self):
        invalid = DIFF + '--- a/missing.py\n+++ b/missing.py\n@@ -1 +1 @@\n-old\n+new\n'
        with self.assertRaises(ValueError):
            self.manager.apply(invalid, 'anything')
        self.assertEqual((self.root / 'a.py').read_text(), 'x = 1\n')

    def test_rollback_on_write_failure(self):
        (self.root / 'b.py').write_text('x = 1\n')
        diff = DIFF + DIFF.replace('a/a.py', 'a/b.py').replace('b/a.py', 'b/b.py')
        original = self.manager._write
        def write(target, content):
            if target.name == 'b.py':
                raise OSError('fixture')
            original(target, content)
        with patch.object(self.manager, '_write', side_effect=write), self.assertRaises(OSError):
            self.manager.apply(diff, self.manager.preview(diff)['id'])
        self.assertEqual((self.root / 'a.py').read_text(), 'x = 1\n')

    def test_search_private_binary_and_redaction(self):
        (self.root / '.env').write_text('needle=private')
        (self.root / 'code.py').write_text('def needle():\n    token="hidden-value"\n    return 1\n')
        (self.root / 'binary').write_bytes(b'needle\0')
        result = ProjectTools(self.settings).search('needle')
        self.assertEqual(result['matches'][0]['file'], 'code.py')
        self.assertNotIn('hidden-value', result['context'])
        self.assertNotIn('private', result['context'])
        self.assertLessEqual(len(result['context']), 6000)

    def test_search_missing(self):
        self.assertFalse(ProjectTools(self.settings).search('unfindable')['matches'])

    @patch('providers.models.request_text', return_value='{"data":[{"id":"hermes3:latest"}]}')
    def test_model_discovery_and_ambiguous_names(self, _):
        catalog = discover(self.settings)
        self.assertEqual(len(catalog['models']), 2)
        selected = select(self.settings, 'ollama:hermes3:latest')
        self.assertEqual(selected.local_base_url, self.settings.ollama_base_url)
        with self.assertRaises(ValueError):
            select(self.settings, 'hermes3:latest')

    @patch('providers.models.request_text', side_effect=ProviderError('offline'))
    def test_offline_discovery(self, _):
        self.assertEqual(len(discover(self.settings)['errors']), 2)

    def stream(self, raw, callback=None, cancel=None):
        response = io.BytesIO(raw)
        with patch('providers.streaming.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = response
            return stream_completion(None, 5, callback, cancel)

    def test_incremental_stream_and_usage(self):
        parts = []
        result = self.stream(b'data: {"choices":[{"delta":{"content":"ola"}}]}\n\ndata: {"choices":[],"usage":{"completion_tokens":1}}\n\ndata: [DONE]\n\n', parts.append)
        self.assertEqual(parts, ['ola'])
        self.assertEqual(result['usage']['completion_tokens'], 1)

    def test_truncated_stream_fails(self):
        with self.assertRaises(ProviderError):
            self.stream(b'data: {"choices":[{"delta":{"content":"partial"}}]}\n')

    def test_stream_cancel(self):
        cancel = Cancellation()
        cancel.cancel()
        with self.assertRaises(Cancelled):
            self.stream(b'', cancel=cancel)

    def test_stream_malformed(self):
        with self.assertRaises(ProviderError):
            self.stream(b'data: []\n')

    def test_cli_patch_requires_yes(self):
        path = self.root / 'change.diff'; path.write_text(DIFF)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--root', str(self.root), '--apply-patch', str(path)]), 0)
        self.assertEqual((self.root / 'a.py').read_text(), 'x = 1\n')

    def test_cli_patch_apply(self):
        path = self.root / 'change.diff'; path.write_text(DIFF)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--root', str(self.root), '--apply-patch', str(path), '--yes']), 0)
        self.assertEqual((self.root / 'a.py').read_text(), 'x = 2\n')

    def test_functional_syntax_failure_does_not_execute(self):
        with patch('benchmarks.functional.subprocess.run') as run:
            self.assertEqual(assess_functional('def (', 'simple_clamp')['functional_quality'], 'failed')
            run.assert_not_called()

    def test_acceptance_runner_rejects_incorrect_clamp(self):
        # Only known fixture code is executed in this test; generated code uses Docker.
        for source, expected in [('def clamp(x,lo,hi): return x', 'failed'), ('def clamp(x,lo,hi):\n if lo>hi: raise ValueError()\n return max(lo,min(x,hi))', 'passed')]:
            output = io.StringIO()
            with patch('sys.stdin', io.StringIO(json.dumps({'source': source, 'cases': CASES['simple_clamp']}))), contextlib.redirect_stdout(output):
                exec(RUNNER, {})
            self.assertEqual(json.loads(output.getvalue())['functional_quality'], expected)

    def test_syntax_check_large_file_without_expanding_prompt_budget(self):
        (self.root / 'large.py').write_text('# padding\n' * 2000 + 'value = 1\n')
        project = ProjectTools(self.settings)
        self.assertTrue(project.check('syntax')['ok'])
        self.assertFalse(project.read(['large.py']).included_files)
        self.assertIn('large.py', project.search('value')['context'])

    def test_search_preserves_line_numbers_after_multiline_redaction(self):
        (self.root / 'example.txt').write_text('-----BEGIN PRIVATE KEY-----\nsecret text\n-----END PRIVATE KEY-----\nneedle\n')
        result = ProjectTools(self.settings).search('needle')
        self.assertEqual(result['matches'][0]['line'], 4)
        self.assertNotIn('secret text', result['context'])
