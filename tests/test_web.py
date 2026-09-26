"""Opt-in HTTP integration tests: HYBRID_NETWORK_TESTS=1 python -m unittest tests.test_web."""
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from config import Settings
from core.web import make_server
from core.orchestrator import Orchestrator
from tests.test_orchestrator import FakeLocal, FakeRemote


@unittest.skipUnless(os.getenv('HYBRID_NETWORK_TESTS') == '1', 'requires loopback sockets')
class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(project_root=Path(self.temp.name), memory_enabled=False)
        (self.settings.project_root / 'code.py').write_text('x = 1\n')
        self.server, self.token = make_server(self.settings, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, body=None, auth=True, extra=None):
        headers = {'Authorization': 'Bearer ' + self.token} if auth else {}
        headers.update(extra or {})
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.read().decode()

    def test_static_page(self):
        self.assertIn('Hybrid IA', self.request('/', auth=False))
        self.assertIn('crypto.randomUUID', self.request('/app.js', auth=False))

    def test_auth_required(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/sessions', auth=False)
        self.assertEqual(error.exception.code, 403)

    def test_cross_origin_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/sessions', extra={'Origin': 'https://evil.test'})
        self.assertEqual(error.exception.code, 403)

    def test_host_refused(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/', extra={'Host': 'evil.test'})

    def test_session_traversal_refused(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/session', {'name': '../private'})

    def test_preview_apply_and_stale(self):
        diff = '--- a/code.py\n+++ b/code.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n'
        result = json.loads(self.request('/api/patch/preview', {'patch': diff}))
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/patch/apply', {'id': result['id']})
        result = json.loads(self.request('/api/patch/apply', {'id': result['id'], 'confirm': True}))
        self.assertTrue(result['applied'])
        self.assertTrue(result['check']['ok'])

    def test_chat_stream_and_session(self):
        class Local(FakeLocal):
            def chat(self, messages, **kwargs):
                if kwargs.get('on_token'):
                    kwargs['on_token']('local answer')
                return super().chat(messages, **kwargs)
        app = Orchestrator(self.settings, local=Local(), remote=FakeRemote())
        with patch('core.web.Orchestrator', return_value=app):
            result = self.request('/api/chat', {'id': 'test', 'request': 'hello', 'mode': 'local', 'session': 'test'})
        events = [json.loads(line) for line in result.splitlines()]
        self.assertEqual([e['type'] for e in events], ['start', 'token', 'done'])
        self.assertEqual(events[-1]['answer'], 'local answer')
        session = json.loads(self.request('/api/session', {'name': 'test'}))
        self.assertEqual(len(session['messages']), 2)

    def test_skill_catalog_and_contents(self):
        data = json.loads(self.request('/api/skills'))
        self.assertEqual(len(data['skills']), 7)
        data = json.loads(self.request('/api/skill', {'name': 'patch'}))
        self.assertIn('unified diff', data['content'])

    def test_cancellation_interrupts_stalled_socket(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from providers.streaming import Cancellation, Cancelled, stream_completion
        ready, release = threading.Event(), threading.Event()
        class StreamHandler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n')
                self.wfile.flush()
                release.wait(5)
        server = ThreadingHTTPServer(('127.0.0.1', 0), StreamHandler)
        server.daemon_threads = True
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        cancel, outcome = Cancellation(), []
        def read():
            try:
                stream_completion(urllib.request.Request('http://127.0.0.1:' + str(server.server_port)), 10, lambda _: ready.set(), cancel)
            except Cancelled:
                outcome.append('cancelled')
        client = threading.Thread(target=read, daemon=True)
        try:
            client.start()
            self.assertTrue(ready.wait(3))
            cancel.cancel()
            client.join(2)
            self.assertFalse(client.is_alive())
            self.assertEqual(outcome, ['cancelled'])
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            worker.join()
            client.join(3)
