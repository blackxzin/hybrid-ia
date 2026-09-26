import tempfile
import unittest
from pathlib import Path

from security.sanitizer import ExternalContentSanitizer


class SanitizerTests(unittest.TestCase):
    def test_blocks_env_and_redacts_secret_in_explicit_code_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowed = root / "app.py"
            allowed.write_text("token = 'ghp_abcdefghijklmnopqrstuv'\nprint('ok')\n")
            env = root / ".env.local"
            env.write_text("ROUTER9_API_KEY=not-for-export\n")
            result = ExternalContentSanitizer(root, ("private",), 1000).build_excerpt([allowed, env])
            self.assertEqual(result.included_files, ("app.py",))
            self.assertEqual(result.rejected_files, (".env.local",))
            self.assertNotIn("ghp_abcdefghijkl", result.text)
            self.assertIn("[REDACTED]", result.text)
