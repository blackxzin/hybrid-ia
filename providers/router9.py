"""OpenAI-compatible 9Router client. The caller supplies the API key via env."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from providers.http import request_text, validate_completion
from providers.streaming import stream_completion
from providers.types import ChatMessage, Completion, ProviderError


class Router9Client:
    def __init__(self, base_url: str, api_key: str | None, timeout_seconds: int = 120, enabled: bool = True) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled

    @property
    def configured(self) -> bool:
        return bool(self.api_key) and self.enabled

    def _request(self, method: str, suffix: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.api_key or not self.enabled:
            raise ProviderError("9Router externo não está habilitado")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        request = urllib.request.Request(
            f"{self.base_url}{suffix}",
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers=headers,
            method=method,
        )
        return self._decode_payload(request_text(request, self.timeout_seconds, "9Router"))

    @staticmethod
    def _decode_payload(payload: str) -> dict[str, Any]:
        """Accept normal JSON, concatenated JSON, and server-sent event chunks."""
        try:
            data = json.loads(payload)
            if not isinstance(data, dict):
                raise ProviderError("9Router retornou JSON inválido")
            return data
        except json.JSONDecodeError:
            pass
        chunks: list[dict[str, Any]] = []
        decoder = json.JSONDecoder()
        index = 0
        while index < len(payload):
            while index < len(payload) and payload[index].isspace():
                index += 1
            if index >= len(payload):
                break
            if index == 0 and payload.startswith("\ufeff"):
                index += 1
                continue
            if any(payload.startswith(prefix, index) for prefix in ("event:", ":", "id:", "retry:")):
                newline = payload.find("\n", index)
                index = len(payload) if newline == -1 else newline + 1
                continue
            if payload.startswith("data:", index):
                index += len("data:")
                while index < len(payload) and payload[index].isspace():
                    index += 1
                if payload.startswith("[DONE]", index):
                    index += len("[DONE]")
                    continue
            try:
                item, index = decoder.raw_decode(payload, index)
            except json.JSONDecodeError as exc:
                raise ProviderError("9Router retornou resposta inválida") from exc
            if isinstance(item, dict):
                chunks.append(item)
        if not chunks:
            raise ProviderError("9Router retornou resposta vazia")
        return {"_stream_chunks": chunks}

    def list_models(self) -> list[str]:
        response = self._request("GET", "/models")
        return [str(item["id"]) for item in response.get("data", []) if "id" in item]

    def chat(self, model: str, messages: list[ChatMessage], *, max_tokens: int = 800, temperature: float = 0, on_token=None, cancel=None) -> Completion:
        start = time.monotonic()
        payload = {"model": model, "messages": [message.__dict__ for message in messages], "max_tokens": max_tokens, "temperature": temperature, "stream": False}
        if on_token is not None or cancel is not None:
            if not self.configured:
                raise ProviderError("9Router externo não está habilitado")
            payload.update(stream=True, stream_options={"include_usage": True})
            request = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
            data = stream_completion(request, self.timeout_seconds, on_token, cancel)
            data["model"] = data.get("model") or model
        else:
            data = self._request("POST", "/chat/completions", payload)
        try:
            return self._completion(data, model, start)
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ProviderError("9Router retornou stream inválido") from exc

    def _completion(self, data, model, start):
        if "_stream_chunks" in data:
            chunks = data["_stream_chunks"]
            content = "".join(
                str(
                    choice.get("delta", {}).get("content")
                    or choice.get("message", {}).get("content")
                    or ""
                )
                for chunk in chunks
                for choice in chunk.get("choices", [])
            )
            data = next((chunk for chunk in reversed(chunks) if "usage" in chunk), chunks[-1])
            final_choices = data.get("choices") or [{}]
            data["choices"] = [{"message": {"content": content}, "finish_reason": final_choices[0].get("finish_reason")}]
        validate_completion(data, "9Router")
        usage = data.get("usage", {})
        return Completion(
            content=data["choices"][0]["message"].get("content") or "",
            model=data.get("model", model),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            elapsed_seconds=time.monotonic() - start,
            timings={},
            finish_reason=data["choices"][0].get("finish_reason"),
        )
