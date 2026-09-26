"""Fixed acceptance tests run only inside a resource-limited Docker container."""
import ast
import json
import re
import subprocess

IMAGE = "python:3.11-slim"
CONTRACTS = {
    "simple_clamp": "Exporte clamp(x, lo, hi).",
    "medium_debug": "Exporte average(values).",
    "simple_unique": "Exporte unique(values), retornando list.",
    "medium_json": "Exporte parse_object(text).",
    "complex_refactor_plan": "Exporte validate_path(root, candidate): retorna pathlib.Path absoluto resolvido para arquivo existente permitido. candidate pode ser relativo à raiz ou absoluto. Recuse arquivos inexistentes, fora da raiz (inclusive symlinks), partes .env*, .git, secrets e sufixos .pem/.key com ValueError.",
    "complex_budget": "Exporte Budget(max_calls, max_tokens), atributos calls e reserved_tokens inicialmente zero, método reserve(tokens). Limites e tokens negativos lançam ValueError. Ao esgotar chamadas ou tokens, reserve lança ValueError sem alterar contadores. Reserva aceita incrementa calls em 1 e reserved_tokens em tokens, antes da chamada externa; uma falha externa não devolve a reserva.",
}
CASES = {
    "simple_clamp": '''f = ns['clamp']
check(f(5, 0, 10) == 5)
check(f(-1, 0, 10) == 0)
check(f(11, 0, 10) == 10)
check(f(2, 2, 2) == 2)
check(f(0.5, 0, 1) == 0.5)
raises(lambda: f(1, 3, 2))''',
    "medium_debug": '''f = ns['average']
check(f([1, 2, 3]) == 2)
check(f(iter([2, 4, 6])) == 4)
check(f((i for i in [1, 3])) == 2)
check(f([-2, 2]) == 0)
raises(lambda: f([]))
raises(lambda: f(iter([])))''',
    "simple_unique": '''f = ns['unique']
check(f([3, 1, 3, 2, 1]) == [3, 1, 2])
check(f(iter([2, 2, 1])) == [2, 1])
check(f([]) == [])
check(f(['a', 'b', 'a']) == ['a', 'b'])
check(f([None, None, 0]) == [None, 0])''',
    "medium_json": '''f = ns['parse_object']
check(f('{}') == {})
check(f(' {"a": [1, true]} ') == {'a': [1, True]})
for value in ('[]', 'null', '1', 'true', '"hello"', '{bad'):
    raises(lambda value=value: f(value))
try:
    f('secret-value-invalid-json')
except ValueError as error:
    check('secret-value' not in str(error))''',
    "complex_refactor_plan": '''from pathlib import Path
import tempfile
f = ns['validate_path']
with tempfile.TemporaryDirectory() as folder:
    base = Path(folder); root = base / 'project'; root.mkdir()
    (root / 'ok.txt').write_text('ok')
    (base / 'outside.txt').write_text('outside')
    check(f(root, 'ok.txt') == (root / 'ok.txt').resolve())
    check(f(root, root / 'ok.txt') == (root / 'ok.txt').resolve())
    raises(lambda: f(root, '../outside.txt'))
    raises(lambda: f(root, base / 'outside.txt'))
    raises(lambda: f(root, 'missing.txt'))
    (root / 'link').symlink_to(base / 'outside.txt')
    raises(lambda: f(root, 'link'))
    for name in ('.env', '.env.local', '.git/config', 'secrets/key.txt', 'cert.pem', 'cert.key'):
        path = root / name; path.parent.mkdir(exist_ok=True); path.write_text('private')
        raises(lambda name=name: f(root, name))''',
    "complex_budget": '''B = ns['Budget']
raises(lambda: B(-1, 10))
raises(lambda: B(1, -1))
b = B(2, 10)
check((b.calls, b.reserved_tokens) == (0, 0))
b.reserve(4)
check((b.calls, b.reserved_tokens) == (1, 4))
raises(lambda: b.reserve(7))
check((b.calls, b.reserved_tokens) == (1, 4))
raises(lambda: b.reserve(-1))
b.reserve(6)
check((b.calls, b.reserved_tokens) == (2, 10))
raises(lambda: b.reserve(0))
check((b.calls, b.reserved_tokens) == (2, 10))
raises(lambda: B(0, 10).reserve(0))
c = B(1, 0); c.reserve(0)
check((c.calls, c.reserved_tokens) == (1, 0))''',
}
RUNNER = '''import json, sys, contextlib, io
payload = json.load(sys.stdin)
passed = 0
def check(value):
    global passed
    if not value: raise AssertionError('Critério não atendido')
    passed += 1
def raises(fn):
    try: fn()
    except ValueError: check(True)
    else: raise AssertionError('ValueError esperado')
try:
    ns = {'__name__': 'candidate'}
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        exec(compile(payload['source'], '<candidate>', 'exec'), ns)
        exec(compile(payload['cases'], '<acceptance>', 'exec'))
    result = {'functional_quality': 'passed', 'passed_checks': passed}
except BaseException as error:
    result = {'functional_quality': 'failed', 'passed_checks': passed, 'failure_type': type(error).__name__}
print(json.dumps(result))
'''


def extract_source(answer):
    blocks = re.findall(r"```(?:python|py)\s*\n(.*?)```", answer, re.S)
    return "\n".join(blocks) if blocks else answer


def assess_functional(answer, task_id):
    if task_id not in CASES:
        raise ValueError("Tarefa sem critérios funcionais")
    source = extract_source(answer)
    try:
        ast.parse(source)
    except SyntaxError:
        return {"functional_quality": "failed", "generated_code_executed": False, "failure_type": "SyntaxError", "passed_checks": 0}
    command = ["docker", "run", "--rm", "--pull=never", "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=32", "--memory=256m", "--cpus=1", "--user=65534:65534", "--tmpfs=/tmp:rw,noexec,nosuid,size=32m", "-i", IMAGE, "python", "-I", "-c", RUNNER]
    # The container is named so timeout cleanup also stops the container itself.
    import uuid
    name = "hybrid-eval-" + uuid.uuid4().hex
    command[2:2] = ["--name", name]
    try:
        result = subprocess.run(command, input=json.dumps({"source": source, "cases": CASES[task_id]}), text=True, capture_output=True, timeout=20)
        if result.returncode != 0:
            return {"functional_quality": "error", "generated_code_executed": None, "error": "Contêiner indisponível ou encerrado; requer imagem local python:3.11-slim"}
        data = json.loads(result.stdout)
        if data.get("functional_quality") not in ("passed", "failed"):
            raise ValueError()
        return {**data, "generated_code_executed": True, "isolation": "docker", "image": IMAGE}
    except subprocess.TimeoutExpired:
        return {"functional_quality": "failed", "generated_code_executed": True, "failure_type": "Timeout", "passed_checks": 0}
    except (OSError, ValueError):
        return {"functional_quality": "error", "generated_code_executed": None, "error": "Docker indisponível ou resultado inválido"}
    finally:
        try:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
