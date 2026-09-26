"""Explicit read/check capabilities; model text cannot invoke these functions."""
import ast
import os
import re
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

    def search(self, query, limit=12):
        """Rank bounded, sanitized excerpts; no index or external requests."""
        terms = set(re.findall(r"[\w]{3,}", query.casefold()))
        terms -= {"para", "como", "uma", "que", "the", "and", "this", "com", "por", "arquivo", "função"}
        if not terms:
            return {"matches": [], "context": ""}
        hits, scanned = [], 0
        for name in self.files():
            try:
                path, _ = self.sanitizer.resolve_allowed(Path(name))
                with path.open("rb") as source:
                    raw = source.read(256_001)
                scanned += len(raw)
                if scanned > 8_000_000:
                    break
                if len(raw) > 256_000 or b"\0" in raw:
                    continue
                content, _ = self.sanitizer.sanitize_text(raw.decode("utf-8"), preserve_lines=True)
            except (OSError, ValueError):
                continue
            lines = content.splitlines()
            path_score = sum(3 for term in terms if term in name.casefold())
            candidates = []
            for index, line in enumerate(lines):
                score = path_score + sum(1 for term in terms if term in line.casefold())
                if score:
                    candidates.append((score, index))
            for score, index in sorted(candidates, key=lambda item: (-item[0], item[1]))[:24]:
                first, last = max(0, index - 2), min(len(lines), index + 3)
                snippet = "\n".join(f"{n + 1}: {lines[n][:300]}" for n in range(first, last))
                hits.append({"file": name, "line": index + 1, "score": score, "text": snippet})
        hits.sort(key=lambda hit: (-hit["score"], hit["file"], hit["line"]))
        matches, chunks, used = [], [], 0
        for hit in hits:
            if any(old["file"] == hit["file"] and abs(old["line"] - hit["line"]) < 5 for old in matches):
                continue
            chunk = f"\n--- {hit['file']}:{hit['line']} ---\n{hit['text']}\n"
            if used + len(chunk) > min(6000, self.sanitizer.max_chars):
                continue
            matches.append(hit)
            chunks.append(chunk)
            used += len(chunk)
            if len(matches) >= max(1, min(limit, 30)):
                break
        return {"matches": matches, "context": "".join(chunks)}

    def check(self, kind, timeout=30):
        if kind == "syntax":
            errors, count = [], 0
            for name in self.files():
                if not name.endswith(".py"):
                    continue
                try:
                    # Validate original source, not the redacted excerpt.
                    path, _ = self.sanitizer.resolve_allowed(Path(name))
                    with path.open("rb") as source:
                        raw = source.read(1_000_001)
                    if len(raw) > 1_000_000:
                        errors.append({"file": name, "error": "Arquivo excede limite de análise (1 MB)"})
                        continue
                    ast.parse(raw.decode("utf-8"), filename=name)
                    count += 1
                except SyntaxError as error:
                    errors.append({"file": name, "line": error.lineno, "error": error.msg})
                except (OSError, ValueError):
                    errors.append({"file": name, "error": "Não foi possível analisar o arquivo"})
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
