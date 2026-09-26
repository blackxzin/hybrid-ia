"""Explicit read/check capabilities; model text cannot invoke these functions."""
import ast
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

from security.sanitizer import ExternalContentSanitizer

IGNORED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "logs", "data", "runtime"}


class ProjectTools:
    def __init__(self, settings):
        self.root = settings.project_root.resolve()
        self.sanitizer = ExternalContentSanitizer(self.root, settings.private_paths, settings.external_file_char_limit)

    def files(self):
        result = []
        for parent, directories, files in os.walk(self.root, followlinks=False):
            directories[:] = sorted(name for name in directories if name not in IGNORED and not name.startswith("."))
            for name in sorted(files):
                try:
                    _, relative = self.sanitizer.resolve_allowed(Path(parent) / name)
                    result.append(relative.as_posix())
                except (OSError, ValueError, RuntimeError):
                    continue
                if len(result) >= 1000:
                    return result
        return result

    def read(self, paths):
        return self.sanitizer.build_excerpt([Path(path) for path in paths])

    def check(self, kind, timeout=30):
        if kind == "syntax":
            errors, count = [], 0
            for name in self.files():
                if not name.endswith(".py"):
                    continue
                excerpt = self.read([name])
                if excerpt.rejected_files:
                    errors.append({"file": name, "error": "Arquivo excede limite de leitura"})
                    continue
                try:
                    # Validate original source, not the redacted excerpt.
                    path, _ = self.sanitizer.resolve_allowed(Path(name))
                    ast.parse(path.read_text(encoding="utf-8"), filename=name)
                    count += 1
                except SyntaxError as error:
                    errors.append({"file": name, "line": error.lineno, "error": error.msg})
            return {"kind": kind, "executed": True, "files": count, "ok": not errors, "errors": errors}
        if kind != "unittest":
            raise ValueError("Verificação não permitida")
        command = [sys.executable, "-m", "unittest", "discover", "-v"]
        # Test code is executable project code, authorized only with --allow-exec.
        # Output goes to a temporary file to avoid unbounded in-memory buffering.
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(command, cwd=self.root, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            timed_out = False
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            output.seek(0)
            raw = output.read(16001)
        text, _ = self.sanitizer.sanitize_text(raw[:16000].decode("utf-8", errors="replace"))
        return {"kind": kind, "executed": True, "ok": process.returncode == 0 and not timed_out, "returncode": process.returncode, "timed_out": timed_out, "output": text, "truncated": len(raw) > 16000}
