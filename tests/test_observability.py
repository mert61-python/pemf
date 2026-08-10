# Author: mertaygn, cglrgrkn
"""Gözlemlenebilirlik + hata yönetimi (audit B-4.1, B-5.2): global exception handler'lar (tutarlı
zarf, PII/str(e) sızmaz) + /metrics Prometheus endpoint + opsiyonel telemetri no-op."""

import os

os.environ.pop("PEMF_SIMULATE", None)

import pytest
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def api():
    from servers import api_server

    return api_server


@pytest.fixture(scope="module")
def client(api):
    return TestClient(api.app, raise_server_exceptions=False)


# ── B-4.1: global exception handler'ları ──────────────────────────────────────
def test_exception_handlers_registered(api):
    assert Exception in api.app.exception_handlers
    assert RequestValidationError in api.app.exception_handlers


def test_validation_error_consistent_envelope_no_pii(client):
    # Geçersiz tip → 422 + tutarlı zarf; ham girdi (PII) SIZMAZ.
    r = client.post("/api/session/start", json={"frequency": "sayı-değil"})
    assert r.status_code == 422
    body = r.json()
    assert body["detail"] == "Geçersiz istek verisi."
    assert "errors" in body
    # 'input' (ham girdi/PII) hiçbir hata girdisinde olmamalı
    assert all("input" not in e for e in body["errors"])


# ── B-5.2: /metrics Prometheus endpoint ───────────────────────────────────────
def test_metrics_prometheus_format(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers.get("content-type", "")
    body = r.text
    assert "pemf_ws_clients" in body
    assert "pemf_active_session" in body
    assert "# TYPE pemf_ws_clients gauge" in body
    # değer satırı sayısal olmalı
    val_line = next(l for l in body.splitlines() if l.startswith("pemf_ws_clients "))
    assert val_line.split()[1].isdigit()


# ── B-5.1: telemetri opt-in (DSN yoksa no-op) ─────────────────────────────────
def test_telemetry_noop_without_dsn(monkeypatch):
    monkeypatch.delenv("PEMF_SENTRY_DSN", raising=False)
    import utils.telemetry as t

    t._initialized = False
    assert t.init_telemetry() is False  # opt-in değil → kapalı


def test_telemetry_noop_when_sdk_missing(monkeypatch):
    monkeypatch.setenv("PEMF_SENTRY_DSN", "https://x@example.com/1")
    import builtins

    import utils.telemetry as t

    t._initialized = False
    _real_import = builtins.__import__

    def _no_sentry(name, *a, **k):
        if name == "sentry_sdk":
            raise ImportError("yok")
        return _real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _no_sentry)
    assert t.init_telemetry() is False  # sentry-sdk yoksa graceful no-op
