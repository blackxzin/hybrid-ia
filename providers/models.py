"""Discover local servers without generating or downloading models."""
from dataclasses import replace
import urllib.request

from providers.http import object_json, request_text
from providers.types import ProviderError


def discover(settings):
    models, errors = [], []
    for provider, base in (("qwen", settings.local_base_url), ("ollama", settings.ollama_base_url)):
        try:
            data = object_json(request_text(urllib.request.Request(base + "/models"), 3, provider), provider)
            for item in data.get("data", []):
                name = item["id"]
                if not isinstance(name, str) or not name:
                    raise ValueError()
                models.append({"key": provider + ":" + name, "model": name, "provider": provider, "base_url": base})
        except (ProviderError, KeyError, TypeError, ValueError):
            errors.append({"provider": provider, "error": "Servidor indisponível ou catálogo inválido"})
    return {"models": models, "errors": errors}


def select(settings, key):
    catalog = discover(settings)
    matches = [item for item in catalog["models"] if key in (item["key"], item["model"])]
    if len(matches) != 1:
        raise ValueError("Modelo indisponível ou ambíguo; consulte --list-models ou /model")
    item = matches[0]
    return replace(settings, local_base_url=item["base_url"], local_model=item["model"])
