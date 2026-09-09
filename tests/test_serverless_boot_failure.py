"""Startup failures retain diagnostics in logs without disclosing them publicly."""

import builtins
import importlib.util
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_import_failure_exposes_generic_service_unavailable_and_logs_traceback(monkeypatch, caplog):
    secret = "startup-secret-sentinel"
    original_import = builtins.__import__

    def fail_app_import(name, *args, **kwargs):
        if name == "web.app":
            raise RuntimeError(f"Database connection failed: postgres://user:{secret}@db/private")
        return original_import(name, *args, **kwargs)

    entrypoint = Path(__file__).resolve().parents[1] / "api" / "index.py"
    spec = importlib.util.spec_from_file_location("serverless_boot_failure_test", entrypoint)
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", fail_app_import)
        with caplog.at_level(logging.ERROR):
            spec.loader.exec_module(module)

    # Executing the entry point must still produce the module-level ASGI app
    # that Vercel discovers, even when importing the real application fails.
    assert isinstance(module.app, FastAPI)
    assert "Traceback (most recent call last)" in caplog.text
    assert secret in caplog.text
    assert "Backend import failed during cold start" in caplog.text

    with TestClient(module.app) as client:
        for method, path in [("GET", "/api/health"), ("POST", "/webhooks/retell"),
                             ("GET", "/docs"), ("OPTIONS", "/")]:
            response = client.request(method, path)
            assert response.status_code == 503
            assert response.text == "Service temporarily unavailable. Please try again later."
            assert secret not in response.text
            assert "postgres://" not in response.text
            assert "Traceback" not in response.text
