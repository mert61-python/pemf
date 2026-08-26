# Author: mertaygn, cglrgrkn
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
    ("/api/ai/log/review", "POST"),  # 2026-08-06 hekim degerlendirmesi (onay/red/duzeltme)
    # 2026-08-08 KVKK silme hakki: AI gecmisini silmenin HICBIR yolu yoktu (kaldirma da silmiyor).
    ("/api/ai/log/delete", "POST"),
    ("/api/ai/log/delete_all", "POST"),
    # 2026-08-08 cihaz tasima: kayitlar makinede kaliyor (bulut senkronu YOK) → sifreli dosya.
    ("/api/data/export", "POST"),
    ("/api/data/import", "POST"),
    # 2026-08-08 cihaz operatorleri: tek makine, coklu veteriner (PIN ile cevrimdisi gecis).
    ("/api/operators", "GET"),
    ("/api/operators/enroll", "POST"),
    ("/api/operators/verify", "POST"),
    ("/api/operators/remove", "POST"),
    ("/api/ai/log", "POST"),
    ("/api/ai/pro/calibrate", "POST"),
    ("/api/ai/pro/organ", "POST"),
    ("/api/ai/pro/start", "POST"),
    ("/api/ai/pro/status", "GET"),
    ("/api/ai/pro/stop", "POST"),
    # 2026-08-06 — hekim onay kapısı (sahip kararı: onaysız otonom tedavi başlamaz):
    ("/api/ai/pro/propose", "POST"),
    ("/api/ai/pro/approve", "POST"),
    ("/api/ai/pro/reject", "POST"),
    # 2026-08-25 — web/sunucu-kamerali kapali-dongu duzeltmesi (hazirlik onizlemesi:
    # organi lokalize eder, bobin surmez, seans baslatmaz — propose artik calisir):
    ("/api/ai/pro/hazirlik/baslat", "POST"),
    ("/api/ai/pro/hazirlik/durdur", "POST"),
    ("/api/ai/rna/kidney", "POST"),
    ("/api/ai/sound/cat", "POST"),
    ("/api/ai/vision/cat_organ", "POST"),
    ("/api/ai/vision/em_fantom", "POST"),
    ("/api/ai/vision/em_petri", "POST"),
    ("/api/ai/vision/histopath", "POST"),
    ("/api/ai/vision/scratch", "POST"),
    ("/api/ai/vision/kidney_ct", "POST"),
    ("/api/ai/vision/landmark", "POST"),
    ("/api/ai/vision/reticulocytes", "POST"),
    ("/api/ai/vision/segmentation", "POST"),
    ("/api/ai/vision/thermal", "POST"),
    ("/api/auth/admin-code", "GET"),  # yönetici şifre-sıfırlama kodu (Ayarlar'da gösterilir; X-API-Key korumalı)
    # 2026-08-06 — masaüstü oturum devri (E-özelliği): Tauri client Supabase oturumunu backend'e
    # devreder, uygulama alıp kendi giriş ekranını atlar (çift giriş yok). Yalnız bellekte + yalnız
    # 127.0.0.1/::1 (bkz. servers/auth_router.py, tests/test_desktop_session.py).
    ("/api/auth/desktop-session", "DELETE"),
    ("/api/auth/desktop-session", "GET"),
    ("/api/auth/desktop-session", "POST"),
    ("/api/auth/exchange", "POST"),
    ("/api/auth/login", "POST"),  # operatör hesap girişi (e-posta/şifre; .edu → araştırma modu)
    ("/api/auth/register", "POST"),  # operatör hesap kaydı (PBKDF2)
    ("/api/auth/reset", "POST"),  # 'Şifremi unuttum' — yönetici koduyla operatör şifre sıfırlama
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
    # 2026-08-09 (Tier 1) VERI SAKLAMA AYARI: seans PII'si sure dolunca `[REDACTED]` ile GERI
    # DONUSSUZ maskeleniyordu ve bu SESSIZ oluyordu; sure yalnizca PEMF_RETAIN_PII_DAYS ortam
    # degiskeniyle ayarlanabiliyordu (hicbir veteriner bilmez). Klinik 366. gunde hasta adi
    # yerine [REDACTED] gorup sebebini bulamiyordu. Karar artik operatorun ve GORUNUR.
    ("/api/settings/retention", "GET"),
    ("/api/settings/retention", "POST"),
    # 2026-08-09 DENETIM IZI (Tier 3): geri donussuz islemlerin (toplu silme, disa/ice aktarma,
    # operator ekleme-cikarma, PII redaksiyonu) tek izi 60 MB'lik DONEN bir metin log'unda
    # KIMLIKSIZ tek bir satirdi. Artik sifreli DB icinde EKLEME-ONLY `audit_events` tablosu var;
    # bu uc onu okunabilir kilar (yazilip hic bakilmayan iz, olmayan izle aynidir).
    ("/api/audit/events", "GET"),
    # 2026-08-09 DESTEK PAKETI (Tier 3): saha teshisi "telefonda ProgramData yolunu tarif etmek"ti;
    # 60 MB'lik loglarin ICINDE hasta adi gecebiliyor → "logu yolla" demek kontrolsuz kisisel veri
    # aktarimi istemekti. Bu uc, cihazdaki GERCEK hasta adlarini maskeler, sir/DB dosyalarini
    # PAKETE ALMAZ ve ne yaptigini OZET.json ile soyler.
    ("/api/support/bundle", "POST"),
    ("/api/system/info", "GET"),
    # 2026-08-09 FELAKET KURTARMA GORUNURLUGU (denetim, ENGEL): kurtarma kodu uretiliyor ve
    # dosyaya yaziliyordu ama operatore YALNIZ log'dan soyleniyordu → kod sifreli DB ile AYNI
    # diskte kaliyor, disk olunce off-site yedekler bile acilamiyordu. Arayuz artik onaylanana
    # kadar kalici uyari gosterir. `recovery-code` KATI LOOPBACK'tir (kod = tum verinin ana
    # anahtari; LAN'a/tunele sizmasi at-rest sifrelemeyi anlamsiz kilar).
    ("/api/system/recovery-status", "GET"),
    ("/api/system/recovery-code", "GET"),
    ("/api/system/recovery-ack", "POST"),
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


# ⚠️ KOŞULLU MOUNT (2026-08-12). `/simulator` üretimde ŞARTLI bağlanır — `api_server.py`:
#     sim_path = packaged_resource_path("dema-terapi-simülatörü", "dist")
#     if os.path.exists(sim_path): app.mount("/simulator", ...)
# `dist` bir DERLEME ÇIKTISIDIR ve depoda izlenmez (`git ls-files` → 0), dolayısıyla CI'da
# YOKTUR. Sözleşme bunu yansıtmadığı için test CI'da "Route KAYBOLDU: [('/simulator','')]"
# diye düşüyordu — gerçekte hiçbir rota kaybolmamıştı, sadece varlık ortama bağlıydı.
# Koşul üretimin KENDİ yardımcısıyla hesaplanır; api_server'daki şart değişirse burası da
# birlikte değişsin, iki taraf ayrı ayrı eskimesin diye.
def _simulator_mountlu() -> bool:
    from utils.path_utils import packaged_resource_path

    return os.path.exists(str(packaged_resource_path("dema-terapi-simülatörü", "dist")))


_KOSULLU_ROTALAR = {("/simulator", "")}


def _beklenen_rotalar() -> set:
    """Golden sözleşme, bu ortamda gerçekten bağlanabilecek rotalara indirgenmiş hâli."""
    if _simulator_mountlu():
        return GOLDEN_ROUTES
    return GOLDEN_ROUTES - _KOSULLU_ROTALAR


def test_route_contract_unchanged():
    """HTTP route envanteri refactor öncesi golden ile BİREBİR aynı olmalı."""
    current = _current_routes()
    beklenen = _beklenen_rotalar()
    missing = beklenen - current  # route düştü / path-method değişti
    added = current - beklenen  # beklenmeyen route eklendi / path değişti
    assert not missing, f"Route KAYBOLDU veya path/method değişti: {sorted(missing)}"
    assert not added, f"Beklenmeyen/değişmiş route: {sorted(added)}"
    # 72 → 75 (+3 masaüstü oturum devri) → 78 (+3 hekim onay kapısı: propose/approve/reject), 2026-08-06
    # → 83 (+2 KVKK AI-geçmişi silme, +2 cihaz taşıma) → 87 (+4 cihaz operatörleri), 2026-08-08
    # → 90 (+3 felaket kurtarma görünürlüğü: recovery-status/code/ack), 2026-08-09
    # → 92 (+2 veri saklama ayarı: settings/retention GET+POST), 2026-08-09 Tier 1
    # → 93 (+1 denetim izi okuma: audit/events GET), 2026-08-09 Tier 3
    # → 94 (+1 destek paketi: support/bundle POST), 2026-08-09 Tier 3
    # → 96 (+2 web AI Pro hazırlık önizlemesi: ai/pro/hazirlik/baslat+durdur), 2026-08-25
    # Sayı da koşula göre daralır: simülatör derlemesi yoksa 96 değil 95 beklenir. Toplamın
    # KENDİSİ hâlâ sabitlenir (yeni rota sessizce eklenemez) — yalnız koşullu olan düşülür.
    assert len(current) == len(beklenen) == 97 - (0 if _simulator_mountlu() else 1)
