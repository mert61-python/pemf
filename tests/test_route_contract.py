"""Characterization (golden-master): HTTP route SÖZLEŞMESİ.

Amaç: `api_server.py` domain-router bölünmesi (refactor B1) sırasında HTTP yüzeyinin
BİREBİR korunduğunu kanıtlamak. Bir route düşerse / eklenirse / path'i veya method'u
değişirse bu test KIRILIR → davranış-koruma ihlali erken yakalanır.

Kapsam DIŞI: FastAPI iç uçları (/docs, /openapi.json, /redoc, /docs/oauth2-redirect) —
bunlar framework-üretimi, dep sürümüne bağlı, refactor kapsamı değil.

Baseline: 2026-07-06 (refactor ÖNCESİ), PEMF_SIMULATE=1. 67 route → 68 (+1 F-7 /api/client/error, prod-readiness Faz 2).
"""
import os

os.environ.setdefault("PEMF_SIMULATE", "1")

_FASTAPI_INTERNAL = {"/docs", "/openapi.json", "/redoc", "/docs/oauth2-redirect"}

# (path, virgülle-birleşik-sıralı-methodlar) — refactor ÖNCESİ dondurulmuş sözleşme.
GOLDEN_ROUTES = {
    ("/api/ai/ai_pro/frame", "POST"),
    ("/api/ai/disease", "POST"),
    ("/api/ai/disease/kidney", "POST"),
    ("/api/ai/log", "GET"),
    ("/api/ai/log", "POST"),
    ("/api/ai/pro/calibrate", "POST"),
    ("/api/ai/pro/organ", "POST"),
    ("/api/ai/pro/start", "POST"),
    ("/api/ai/pro/status", "GET"),
    ("/api/ai/pro/stop", "POST"),
    ("/api/ai/rna/kidney", "POST"),
    ("/api/ai/sound/cat", "POST"),
    ("/api/ai/vision/cat_organ", "POST"),
    ("/api/ai/vision/em_fantom", "POST"),
    ("/api/ai/vision/em_petri", "POST"),
    ("/api/ai/vision/histopath", "POST"),
    ("/api/ai/vision/kidney_ct", "POST"),
    ("/api/ai/vision/landmark", "POST"),
    ("/api/ai/vision/reticulocytes", "POST"),
    ("/api/ai/vision/segmentation", "POST"),
    ("/api/ai/vision/thermal", "POST"),
    ("/api/auth/admin-code", "GET"),  # yönetici şifre-sıfırlama kodu (Ayarlar'da gösterilir; X-API-Key korumalı)
    ("/api/auth/exchange", "POST"),
    ("/api/auth/login", "POST"),      # operatör hesap girişi (e-posta/şifre; .edu → araştırma modu)
    ("/api/auth/register", "POST"),   # operatör hesap kaydı (PBKDF2)
    ("/api/auth/reset", "POST"),      # 'Şifremi unuttum' — yönetici koduyla operatör şifre sıfırlama
    ("/api/auth/token", "GET"),
    ("/api/client/error", "POST"),  # F-7 (prod-readiness Faz 2): frontend ErrorBoundary crash raporu
    ("/api/coil/batch", "POST"),
    ("/api/coil/{coil_id}/control", "POST"),
    ("/api/dashboard-snapshot", "GET"),
    ("/api/discovery", "GET"),
    ("/api/gateway/status", "GET"),
    ("/api/hardware/auto_preset", "POST"),
    ("/api/hardware/cleanup_esp", "POST"),
    ("/api/hardware/command", "POST"),
    ("/api/hardware/emergency_stop", "POST"),
    ("/api/hardware/reset_pwm", "POST"),
    ("/api/hardware/selftest", "POST"),
    ("/api/health", "GET"),
    ("/api/history/", "GET"),
    ("/api/history/delete", "POST"),
    ("/api/history/export_csv", "GET"),
    ("/api/history/export_patient_pdf", "GET"),
    ("/api/history/export_pdf", "GET"),
    ("/api/history/statistics", "GET"),
    ("/api/history/update_notes", "POST"),
    ("/api/history/{session_id}", "DELETE"),
    ("/api/history/{session_id}", "GET"),
    ("/api/history/{session_id}/coil_runs.csv", "GET"),
    ("/api/history/{session_id}/details", "GET"),
    ("/api/kpi/summary", "GET"),
    ("/api/notifications/clear", "POST"),
    ("/api/patients", "GET"),
    ("/api/patients", "POST"),
    ("/api/patients/delete_all", "POST"),
    ("/api/patients/{patient_id}", "DELETE"),
    ("/api/patients/{patient_id}/delete", "POST"),
    ("/api/session/active", "GET"),
    ("/api/session/notes", "POST"),
    ("/api/session/start", "POST"),
    ("/api/session/stop", "POST"),
    ("/api/settings/", "GET"),
    ("/api/settings/", "POST"),
    ("/api/system/info", "GET"),
    ("/api/update/apply", "POST"),
    ("/api/update/rollback", "POST"),
    ("/api/update/status", "GET"),
    ("/favicon.ico", "GET"),
    ("/metrics", "GET"),
    ("/simulator", ""),
    ("/ws", ""),
}


def _current_routes():
    from servers.api_server import app

    out = set()
    for r in app.routes:
        path = getattr(r, "path", None)
        if not path or path in _FASTAPI_INTERNAL:
            continue
        methods = ",".join(sorted(getattr(r, "methods", []) or []))
        out.add((path, methods))
    return out


def test_route_contract_unchanged():
    """HTTP route envanteri refactor öncesi golden ile BİREBİR aynı olmalı."""
    current = _current_routes()
    missing = GOLDEN_ROUTES - current  # route düştü / path-method değişti
    added = current - GOLDEN_ROUTES  # beklenmeyen route eklendi / path değişti
    assert not missing, f"Route KAYBOLDU veya path/method değişti: {sorted(missing)}"
    assert not added, f"Beklenmeyen/değişmiş route: {sorted(added)}"
    assert len(current) == len(GOLDEN_ROUTES) == 72
