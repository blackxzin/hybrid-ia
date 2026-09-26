"""Strict unified patches: preview first, reject stale or private targets."""
import hashlib
import os
from pathlib import Path
import re
import tempfile

from security.sanitizer import SENSITIVE_NAMES, SENSITIVE_SUFFIXES


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class PatchManager:
    def __init__(self, settings):
        self.root = settings.project_root.resolve()
        self.private = settings.private_paths

    def target(self, name):
        path = Path(name)
        if path.is_absolute() or not path.parts or any(part in ("..", ".git", ".agents", ".codex") for part in path.parts):
            raise ValueError("Caminho de patch recusado")
        parts = {part.casefold() for part in path.parts}
        if parts & SENSITIVE_NAMES or path.suffix.casefold() in SENSITIVE_SUFFIXES or any(part.startswith((".env", "credentials")) for part in parts):
            raise ValueError("Patch em arquivo privado recusado")
        for private in self.private:
            key = private.strip("/").casefold()
            if key in parts or path.as_posix().casefold() == key or path.as_posix().casefold().startswith(key + "/"):
                raise ValueError("Patch em arquivo privado recusado")
        target = self.root / path
        for parent in [target, *target.parents]:
            if parent == self.root:
                break
            if parent.is_symlink():
                raise ValueError("Links simbólicos não são aceitos em patches")
        target.resolve().relative_to(self.root)
        if target.exists() and (not target.is_file() or target.stat().st_size > 1_000_000):
            raise ValueError("Destino inválido ou grande demais")
        return target

    def preview(self, patch):
        if len(patch.encode()) > 1_000_000:
            raise ValueError("Patch excedeu limite")
        if patch.startswith("```diff\n") and patch.rstrip().endswith("```"):
            patch = patch.split("\n", 1)[1].rsplit("```", 1)[0]
        lines = patch.splitlines(keepends=True)
        changes, i = [], 0
        while i < len(lines):
            if lines[i].startswith(("diff --git ", "index ")) or not lines[i].strip():
                i += 1
                continue
            if not lines[i].startswith("--- ") or i + 1 >= len(lines) or not lines[i + 1].startswith("+++ "):
                raise ValueError("Esperado unified diff sem renomes ou metadados de modo")
            old = lines[i][4:].rstrip("\r\n").split("\t")[0]
            new = lines[i + 1][4:].rstrip("\r\n").split("\t")[0]
            old = old[2:] if old.startswith("a/") else old
            new = new[2:] if new.startswith("b/") else new
            if old != new and old != "/dev/null" and new != "/dev/null":
                raise ValueError("Renomes não são suportados")
            name = old if new == "/dev/null" else new
            target = self.target(name)
            if any(change["file"] == name for change in changes):
                raise ValueError("Destino duplicado")
            if old == "/dev/null":
                if target.exists():
                    raise ValueError("Novo arquivo já existe")
                before = None
            else:
                if not target.is_file():
                    raise ValueError("Arquivo original inexistente")
                before = target.read_bytes().decode("utf-8")
            if before is not None and "\0" in before:
                raise ValueError("Arquivo binário recusado")
            source = (before or "").splitlines(keepends=True)
            result, cursor, hunks = [], 0, 0
            i += 2
            while i < len(lines) and lines[i].startswith("@@ "):
                match = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n?", lines[i])
                if not match:
                    raise ValueError("Cabeçalho de hunk inválido")
                start, count, new_start, new_count = (int(value) if value is not None else 1 for value in match.groups())
                pos = start - 1 if count else start
                if pos < cursor or pos > len(source):
                    raise ValueError("Posição de hunk inválida")
                result.extend(source[cursor:pos])
                if (new_start - 1 if new_count else new_start) != len(result):
                    raise ValueError("Posição de saída inválida")
                cursor = pos
                consumed = produced = 0
                i += 1
                while i < len(lines) and (consumed < count or produced < new_count):
                    line = lines[i]
                    if not line or line[0] not in " +-":
                        break
                    prefix, body = line[0], line[1:]
                    i += 1
                    if i < len(lines) and lines[i].startswith("\\ No newline at end of file"):
                        body = body.rstrip("\r\n")
                        i += 1
                    if prefix in " -":
                        if cursor >= len(source) or source[cursor] != body:
                            raise ValueError("Patch desatualizado: contexto não corresponde ao arquivo")
                        cursor += 1
                        consumed += 1
                    if prefix in " +":
                        result.append(body)
                        produced += 1
                    if consumed == count and produced == new_count:
                        break
                if (consumed, produced) != (count, new_count):
                    raise ValueError("Contagem de linhas do hunk inválida")
                hunks += 1
            if not hunks:
                raise ValueError("Patch sem hunks")
            result.extend(source[cursor:])
            after = "".join(result)
            if new == "/dev/null" and after:
                raise ValueError("Remoção incompleta")
            changes.append({"file": name, "before": before, "after": None if new == "/dev/null" else after})
        if not changes:
            raise ValueError("Patch vazio")
        fingerprint = digest(repr(changes))
        return {"id": fingerprint, "files": [item["file"] for item in changes], "diff": patch, "changes": changes}

    def apply(self, patch, expected_id):
        preview = self.preview(patch)
        if preview["id"] != expected_id:
            raise ValueError("A prévia mudou; revise novamente")
        written = []
        try:
            for change in preview["changes"]:
                target = self.target(change["file"])
                current = target.read_bytes().decode("utf-8") if target.exists() else None
                if current != change["before"]:
                    raise ValueError("Arquivo mudou durante aplicação")
                self._write(target, change["after"])
                written.append(change)
        except Exception:
            for change in reversed(written):
                self._write(self.target(change["file"]), change["before"])
            raise
        return {"applied": True, "files": preview["files"], "id": preview["id"]}

    @staticmethod
    def _write(target, content):
        if content is None:
            target.unlink()
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
        fd, name = tempfile.mkstemp(dir=target.parent, prefix=".hybrid-patch-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as output:
                output.write(content)
            os.chmod(name, mode)
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
