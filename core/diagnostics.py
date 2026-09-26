"""Connectivity/model discovery without generation or credential output."""
import urllib.request

from providers.http import object_json, request_text
from providers.router9 import Router9Client
from providers.types import ProviderError


def diagnose(settings):
    report = {"local_input_budget": settings.local_input_budget, "memory_enabled": settings.memory_enabled, "max_external_calls": settings.max_external_calls}
    try:
        request = urllib.request.Request(settings.local_base_url + "/models")
        data = object_json(request_text(request, 5, "Qwen"), "Qwen")
        models = [item["id"] for item in data.get("data", [])]
        report["local"] = {"reachable": True, "models": models, "configured_model_available": settings.local_model in models}
    except (ProviderError, KeyError, TypeError):
        report["local"] = {"reachable": False, "error": "Qwen indisponível ou resposta inválida"}
    remote = Router9Client(settings.router9_base_url, settings.router9_api_key, 5, settings.router9_enabled)
    report["remote"] = {"configured": remote.configured}
    if remote.configured:
        try:
            models = remote.list_models()
            report["remote"].update(reachable=True, models=models, configured_models_available=all(model in models for model in (settings.planner_model, settings.reviewer_model, settings.fast_model)))
        except (ProviderError, KeyError, TypeError):
            report["remote"].update(reachable=False, error="9Router indisponível ou resposta inválida")
    return report
