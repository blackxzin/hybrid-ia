"""Bounded HTTP transport. Errors never include payloads or credentials."""
import http.client
import json
import urllib.error
import urllib.request

from providers.types import ProviderError

MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_text(request, timeout, label):
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ProviderError(f"{label}: resposta excedeu limite")
            return raw.decode("utf-8-sig")
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"{label} HTTP {exc.code}") from exc
    except (OSError, http.client.HTTPException, UnicodeError) as exc:
        raise ProviderError(f"{label}: falha de conexão ou resposta inválida") from exc


def object_json(text, label):
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except ValueError as exc:
        raise ProviderError(f"{label}: JSON inválido") from exc


def validate_completion(data, label):
    try:
        choice = data["choices"][0]
        content = choice["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError()
        usage = data.get("usage") or {}
        if not isinstance(usage, dict):
            raise ValueError()
        for key in ("prompt_tokens", "completion_tokens"):
            value = usage.get(key)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError()
        data["usage"] = usage
        if not isinstance(data.get("timings", {}), dict):
            raise ValueError()
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ProviderError(f"{label}: resposta de conclusão inválida ou vazia") from exc
