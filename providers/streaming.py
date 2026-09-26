"""Bounded SSE transport and cooperative cancellation."""
import http.client
import json
import socket
import threading
import time
import urllib.error
import urllib.request

from providers.http import MAX_RESPONSE_BYTES, NoRedirect, validate_completion
from providers.types import ProviderError


class Cancelled(RuntimeError):
    pass


class Cancellation:
    def __init__(self):
        self.event = threading.Event()
        self.lock = threading.Lock()
        self.connection = None

    def cancel(self):
        self.event.set()
        with self.lock:
            connection = self.connection
        if connection:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def attach(self, response):
        # urllib HTTPResponse uses a SocketIO reader on supported CPython versions.
        connection = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
        with self.lock:
            self.connection = connection
        if self.event.is_set():
            self.cancel()
            self.check()

    def detach(self):
        with self.lock:
            self.connection = None

    def check(self):
        if self.event.is_set():
            raise Cancelled("Geração cancelada")


def stream_completion(request, timeout, on_token, cancel=None):
    chunks, total, usage, model, finish = [], 0, {}, None, None
    deadline = time.monotonic() + timeout
    ended = False
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
            if cancel:
                cancel.attach(response)
            while True:
                if cancel:
                    cancel.check()
                if time.monotonic() > deadline:
                    raise ProviderError("Tempo de streaming esgotado")
                line = response.readline(65537)
                if not line:
                    break
                total += len(line)
                if len(line) > 65536 or total > MAX_RESPONSE_BYTES:
                    raise ProviderError("Stream excedeu limite")
                if not line.startswith(b"data:"):
                    continue
                payload = line[5:].strip()
                if payload == b"[DONE]":
                    ended = True
                    break
                data = json.loads(payload)
                if "error" in data:
                    raise ProviderError("Servidor recusou geração")
                model = data.get("model", model)
                usage = data.get("usage") or usage
                for choice in data.get("choices", []):
                    if choice.get("index", 0) != 0:
                        continue
                    part = choice.get("delta", {}).get("content") or ""
                    if not isinstance(part, str):
                        raise ValueError()
                    if part:
                        chunks.append(part)
                        if on_token:
                            on_token(part)
                    finish = choice.get("finish_reason") or finish
        if cancel:
            cancel.check()
        if not ended and not finish:
            raise ProviderError("Stream interrompido antes da conclusão")
        result = {"model": model, "usage": usage, "choices": [{"message": {"content": "".join(chunks)}, "finish_reason": finish}]}
        validate_completion(result, "Streaming")
        return result
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"Streaming HTTP {exc.code}") from exc
    except (OSError, http.client.HTTPException, ValueError, TypeError, KeyError, AttributeError) as exc:
        if cancel:
            cancel.check()
        raise ProviderError("Streaming: conexão ou resposta inválida") from exc
    finally:
        if cancel:
            cancel.detach()
