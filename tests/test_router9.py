import unittest

from providers.router9 import Router9Client


class Router9PayloadTests(unittest.TestCase):
    def test_decodes_concatenated_json_stream(self) -> None:
        payload = '{"choices":[{"delta":{"content":"O"}}]}\n{"choices":[{"delta":{"content":"K"}}],"usage":{"prompt_tokens":1,"completion_tokens":2}}'
        decoded = Router9Client._decode_payload(payload)
        self.assertEqual(len(decoded["_stream_chunks"]), 2)

    def test_decodes_normal_json(self) -> None:
        decoded = Router9Client._decode_payload('{"data":[{"id":"model"}]}')
        self.assertEqual(decoded["data"][0]["id"], "model")
