"""Small built-in skills plus explicitly reviewed project imports."""
from pathlib import Path
import re

LIBRARY = Path(__file__).resolve().parents[1] / "skills"
DESCRIPTIONS = {
    "minimal": "Implementação concisa e mudança mínima",
    "debug": "Diagnóstico de bugs e correção da causa",
    "security": "Revisão de segurança, segredos e entradas",
    "explore": "Busca e entendimento de arquivos e funções",
    "patch": "Preparação de unified diff revisável",
    "testing": "Critérios de aceite e testes funcionais",
    "review": "Revisão de código com evidências",
}
NAMES = tuple(DESCRIPTIONS)
MAX_SKILL_BYTES = 8000


def custom_folder(root):
    folder = Path(root).resolve() / "skills" / "custom"
    if folder.is_symlink() or folder.parent.is_symlink():
        raise ValueError("Diretório de skills não pode ser link simbólico")
    return folder


def read_skill(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Skill inexistente ou link simbólico")
    with path.open('rb') as source:
        raw = source.read(MAX_SKILL_BYTES + 1)
    if len(raw) > MAX_SKILL_BYTES or b'\0' in raw:
        raise ValueError("Skill deve ser texto UTF-8 de até 8000 bytes")
    text = raw.decode('utf-8')
    if not text.strip():
        raise ValueError("Skill vazia")
    return text


def catalog(root=None, query=""):
    items = [{"name": name, "description": description, "source": "builtin", "bytes": (LIBRARY / (name + '.md')).stat().st_size} for name, description in DESCRIPTIONS.items()]
    if root:
        for path in sorted(custom_folder(root).glob('*.md'))[:100]:
            if path.stem in NAMES or not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', path.stem):
                continue
            try:
                text = read_skill(path)
            except (ValueError, OSError):
                continue
            items.append({"name": path.stem, "description": "Skill importada e revisada no projeto", "source": "custom", "bytes": len(text.encode())})
    terms = query.casefold().split()
    return [item for item in items if all(term in (item['name'] + ' ' + item['description']).casefold() for term in terms)]


def select_skill(request: str, requested: str = "auto", root=None) -> tuple[str, str]:
    name = requested
    if name == "auto":
        text = request.casefold()
        rules = (
            ("security", ("segurança", "security", "vulnerab")),
            ("patch", ("unified diff", "patch", "proponha um diff")),
            ("debug", ("erro", "bug", "falha", "debug")),
            ("testing", ("teste", "test ", "tests", "benchmark", "critério de aceite")),
            ("review", ("revise", "revisão", "review")),
            ("explore", ("explique", "encontre", "localize", "onde fica", "como funciona")),
        )
        name = next((key for key, words in rules if any(re.search(r"(?<!\w)" + re.escape(word), text) for word in words)), "minimal")
    if name == "none":
        return name, ""
    if name in NAMES:
        return name, read_skill(LIBRARY / f"{name}.md")
    if root and re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', name):
        return name, read_skill(custom_folder(root) / f"{name}.md")
    raise ValueError("Skill desconhecida; consulte --list-skills")


def import_skill(root, source, name, approved=False):
    """Preview first. Import text only, never dependencies, scripts, or tools."""
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', name) or name in (*NAMES, 'auto', 'none'):
        raise ValueError("Nome de skill inválido ou reservado")
    text = read_skill(Path(source))
    folder = custom_folder(root)
    target = folder / (name + '.md')
    if target.exists() or target.is_symlink():
        raise ValueError("Skill já existe; escolha outro nome")
    if approved:
        folder.mkdir(parents=True, exist_ok=True)
        with target.open('x', encoding='utf-8') as output:
            output.write(text)
    return {"name": name, "content": text, "imported": approved, "bytes": len(text.encode()), "note": "Somente instruções de texto. Scripts, ferramentas e permissões não são importados."}
