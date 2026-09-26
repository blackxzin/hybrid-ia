"""OpenAI-compatible client for a llama-server hosted Qwen."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from providers.http import object_json, request_text, validate_completion
from providers.streaming import stream_completion
from providers.types import ChatMessage, Completion, ProviderError


class LocalQwenClient:
    def __init__(self, base_url: str, model: str, timeout_seconds: int = 600) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def _post(self, suffix: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_to(f"{self.base_url}{suffix}", payload)

    def chat(self, messages: list[ChatMessage], *, max_tokens: int = 1024, temperature: float = 0, on_token=None, cancel=None) -> Completion:
        start = time.monotonic()
        payload = {
                "model": self.model,
                "messages": [message.__dict__ for message in messages],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "cache_prompt": False,
                "chat_template_kwargs": {"enable_thinking": False},
            }
        if on_token is not None or cancel is not None:
            payload.update(stream=True, stream_options={"include_usage": True})
            request = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
            data = stream_completion(request, self.timeout_seconds, on_token, cancel)
            data["model"] = data.get("model") or self.model
        else:
            data = self._post("/chat/completions", payload)
        validate_completion(data, "Local Qwen")
        message = data["choices"][0]["message"]
        usage = data.get("usage", {})
        return Completion(
            content=message.get("content") or "",
            model=data.get("model", self.model),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            elapsed_seconds=time.monotonic() - start,
            timings=data.get("timings", {}),
            finish_reason=data["choices"][0].get("finish_reason"),
        )

    def count_messages(self, messages: list[ChatMessage]) -> int | None:
        """Count exactly with llama-server when its tokenizer endpoints are present."""
        try:
            server_base = self.base_url.rsplit("/v1", 1)[0]
            template = self._post_to(
                server_base + "/apply-template",
                {"messages": [message.__dict__ for message in messages], "chat_template_kwargs": {"enable_thinking": False}},
            )
            token_data = self._post_to(server_base + "/tokenize", {"content": template["prompt"], "add_special": False})
            return len(token_data["tokens"])
        except (KeyError, TypeError, ProviderError):
            return None

    def _post_to(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        return object_json(request_text(request, self.timeout_seconds, "Local Qwen"), "Local Qwen")
