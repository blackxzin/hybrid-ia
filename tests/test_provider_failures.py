import io
import json
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request

from providers.http import NoRedirect
from providers.local_qwen import LocalQwenClient
from providers.router9 import Router9Client
from providers.types import ChatMessage, ProviderError


class ProviderFailureTests(unittest.TestCase):
    def test_timeout_has_safe_error(self):
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect = TimeoutError('credential-do-not-echo')
            with self.assertRaises(ProviderError) as error:
                LocalQwenClient('http://localhost/v1', 'qwen').chat([ChatMessage('user', 'hi')])
            self.assertNotIn('credential-do-not-echo', str(error.exception))

    def test_local_invalid_json_has_safe_error(self):
        with patch('providers.local_qwen.request_text', return_value='secret invalid body'):
            with self.assertRaises(ProviderError) as error:
                LocalQwenClient('http://localhost/v1', 'qwen').chat([])
            self.assertNotIn('secret invalid body', str(error.exception))

    def test_local_invalid_shape_has_safe_error(self):
        with patch('providers.local_qwen.request_text', return_value='{"choices": []}'):
            with self.assertRaises(ProviderError):
                LocalQwenClient('http://localhost/v1', 'qwen').chat([])

    def test_redirect_cannot_forward_authorization(self):
        request = urllib.request.Request('http://localhost/v1', headers={'Authorization': 'Bearer private'})
        self.assertIsNone(NoRedirect().redirect_request(request, None, 302, 'redirect', {}, 'https://other.example'))

    def test_reasoning_is_not_presented_as_final_answer(self):
        client = Router9Client('http://localhost/v1', 'test')
        with patch.object(client, '_request', return_value={'choices': [{'message': {'reasoning': 'internal'}}]}):
            with self.assertRaises(ProviderError):
                client.chat('model', [])

    def test_stream_keeps_content_and_usage(self):
        client = Router9Client('http://localhost/v1', 'test')
        payload = {'_stream_chunks': [
            {'choices': [{'delta': {'reasoning': 'internal'}}]},
            {'choices': [{'delta': {'content': 'answer'}}]},
            {'choices': [], 'usage': {'prompt_tokens': 4, 'completion_tokens': 2}}
        ]}
        with patch.object(client, '_request', return_value=payload):
            result = client.chat('model', [])
        self.assertEqual(result.content, 'answer')
        self.assertEqual(result.input_tokens, 4)

    def test_malformed_stream_is_provider_error(self):
        client = Router9Client('http://localhost/v1', 'test')
        with patch.object(client, '_request', return_value={'_stream_chunks': [{'choices': None}]}):
            with self.assertRaises(ProviderError):
                client.chat('model', [])
