"""Deterministic server fixture for browser checks; never contacts model servers."""
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import Settings
from core.orchestrator import Orchestrator
from core.web import make_server
from providers.types import Completion


class Local:
    def count_messages(self, messages):
        return None

    def chat(self, messages, **kwargs):
        slow = 'slow' in str(messages)
        parts = ['Resposta ', 'local ', '<script>texto seguro</script>'] if not slow else ['aguarde '] * 40
        for part in parts:
            if kwargs.get('cancel'):
                kwargs['cancel'].check()
            time.sleep(0.2 if slow else 0.02)
            if kwargs.get('on_token'):
                kwargs['on_token'](part)
        return Completion(''.join(parts), 'fixture', 12, 8, .1)


with tempfile.TemporaryDirectory(prefix='hybrid-browser-') as folder:
    root = Path(folder)
    (root / 'example.py').write_text('def needle():\n    return 1\n')
    settings = Settings(project_root=root, memory_enabled=False, router9_enabled=False)
    catalog = {'models': [{'key': 'qwen:fixture', 'model': 'fixture', 'provider': 'qwen', 'base_url': settings.local_base_url}], 'errors': []}
    with patch('core.web.discover', return_value=catalog), patch('core.web.select', return_value=settings), patch('core.web.Orchestrator', side_effect=lambda cfg: Orchestrator(cfg, local=Local())):
        server, token = make_server(settings, 0)
        path = Path('/tmp/hybrid-web-fixture.json')
        path.write_text(json.dumps({'url': f'http://127.0.0.1:{server.server_port}/#token={token}'}))
        path.chmod(0o600)
        print('Browser fixture ready', flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
