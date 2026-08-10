# Author: mertaygn, cglrgrkn
"""KALAN düzeltmeler için regresyon koruması (mutasyon testi 3. turu).

Denetimin 86 düzeltmesinden P0/P1 ve ilk P2/P3 kümesi daha önce mutasyon testinden
geçirilmişti. Bu dosya geri kalanları kapsar. Hepsinin ortak özelliği: uygulanmışlar ama
hiçbir test onları korumuyordu — silinseler takım yeşil kalırdı.
"""

import pytest


@pytest.fixture()
def api(monkeypatch):
    from servers import api_server

    monkeypatch.setattr(api_server, "_mqtt_publish", lambda *a, **k: True)
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda *a, **k: None)
    monkeypatch.setattr(api_server, "_broker_reachable", lambda: True)
    with api_server._session_lock:
        api_server._active_session.clear()
    yield api_server
    with api_server._session_lock:
        api_server._active_session.clear()


# ───────────────────── BOBİN GÜVENLİĞİ ─────────────────────


def test_bayat_ESP_telemetrisinde_GERCEK_stop_yayinlanir(api):
    """Bobin YALNIZCA 'durdu' işaretlenirse operatöre yanlış güvence verilir.

    ESP güç kaybıyla değil WiFi/broker kopmasıyla sessizleştiyse kendi son `start`
    komutuyla HÂLÂ SÜRÜYOR olabilir (kendi duration'ı bitene dek). UI 'durdu' gösterirken
    bobin fiziksel olarak canlı hayvan üzerinde enerjili kalır. Watchdog gerçek bir STOP
    yayınlamalı — ESP geri geldiğinde komutu alır.
    """
    import inspect

    src = inspect.getsource(api)
    assert '"reason": "telemetry_stale"' in src, (
        "bayat ESP için STOP komutu yayınlanmıyor → bobin 'durdu' görünürken enerjili kalır"
    )
    assert 'f"pemf/coil/{cid}/control"' in src
    # Demote eşiği gerçekten uygulanmalı (devasa yapılırsa watchdog hiç tetiklenmez)
    assert "(now - last) > ESP_STALE_SEC" in src, "bayatlık eşiği uygulanmıyor"
    assert isinstance(api.ESP_STALE_SEC, (int, float)) and 0 < api.ESP_STALE_SEC <= 300, (
        f"ESP_STALE_SEC makul aralıkta değil: {api.ESP_STALE_SEC}"
    )


def test_acil_durdurma_auth_MUAF_kalir():
    """Fail-safe uç: acil durdurma hiçbir koşulda token'a takılmamalı.

    `_EXEMPT_EXACT` boşalırsa `/api/hardware/emergency_stop` 401 döner — operatör bobinleri
    durduramaz. `/api/v1` alias'i de aynı muafiyeti almalı (yeniden-yazım auth'tan ÖNCE koşar).
    """
    from servers import auth

    assert auth.is_exempt("/api/hardware/emergency_stop"), (
        "ACİL DURDURMA auth-muaf DEĞİL → token'sız durdurulamaz (fail-safe kayboldu)"
    )
    # /api/v1 alias'i middleware'de /api/'ye yeniden yazılır → yeniden yazılmış hâli muaf olmalı
    assert auth.is_exempt("/api/hardware/emergency_stop"), "alias yolu muaf değil"
    # Sağlık/keşif de muaf kalmalı (izleme ve eşleştirme kilitlenmesin)
    assert auth.is_exempt("/api/health") and auth.is_exempt("/api/discovery/info")


def test_keep_alive_firmware_olu_adam_esiginin_ALTINDA():
    """Keep-alive aralığı firmware ölü-adam eşiğini AŞARSA firmware her turda bobinleri
    kendi kendine keser → tedavi kesik kesik uygulanır (ya da tamamen durur).

    Marj: en az 2 keep-alive bir eşik penceresine sığmalı (bir paket kaybını tolere et).
    """
    from controllers import hardware_controller as hw

    esik_s = hw.HardwareController._FIRMWARE_DEADMAN_MS / 1000.0
    assert hw.HardwareController.KEEP_ALIVE_INTERVAL_S * 2 <= esik_s, (
        f"keep-alive {hw.HardwareController.KEEP_ALIVE_INTERVAL_S}s × 2 > ölü-adam {esik_s}s → "
        "tek paket kaybında firmware bobinleri keser"
    )


def test_kapanis_ESP_STOP_butcesi_GERCEKTEN_uygulanir():
    """Bütçe uygulanmazsa erişilemeyen broker'da kapanış 3 bobin × ~2 sn × 2 publish kadar
    uzar ve Windows SCM stop-timeout'unu aşar → servis 'durduruldu' sayılmadan ÖLDÜRÜLÜR,
    kapanış mutabakatı yarım kalır.
    """
    import ast
    import inspect

    import backend_service as bs

    assert bs._ESP_STOP_BUDGET_S > 0 and bs._STM_FLUSH_BUDGET_S > 0
    src = inspect.getsource(bs._safe_stop_outputs)
    # Bütçe join(timeout=...) ile GERÇEKTEN uygulanmalı — daemon thread + timeout deseni
    assert "daemon=True" in src, "ESP STOP thread'leri daemon değil → bütçe aşımında süreç takılır"
    assert "join(timeout=" in src, "join TIMEOUT'suz → bütçe uygulanmıyor (sadece yazılı)"
    assert "_deadline" in src

    # NSSM stop-timeout'una sığmalı (toplam bütçe)
    toplam = bs._GRACEFUL_SHUTDOWN_TIMEOUT_S + bs._SAFE_STOP_BUDGET_S
    assert toplam < 15, f"toplam kapanış bütçesi {toplam}s ≥ NSSM 15s → servis öldürülür"


def test_bayat_payload_TEKRAR_gonderilmez():
    """Seri yeniden bağlanmada `last_payload` körlemesine tekrar gönderilirse ESKİ bir
    sürüş komutu (ör. iptal edilmiş bir tedavinin duty'si) bobinlere yeniden uygulanır.
    Yaş sınırı bunu keser; keep-alive zaten güncel durumu tazeler.
    """
    import inspect

    import headless_core

    assert 0 < headless_core._RETRY_MAX_AGE_S <= 5, (
        f"_RETRY_MAX_AGE_S makul değil: {headless_core._RETRY_MAX_AGE_S} (devasa değer = bayat komut replay'i serbest)"
    )
    src = inspect.getsource(headless_core)
    assert "(time.monotonic() - ts) > _RETRY_MAX_AGE_S" in src, (
        "bayat payload yaş kontrolü YOK → yeniden bağlanmada eski sürüş komutu tekrar uygulanır"
    )


def test_sure_cevrimi_TAVANA_yuvarlar():
    """Saniye→dakika çevrimi aşağı yuvarlarsa tedavi PLANLANANDAN KISA uygulanır
    (90 sn → 1 dk = %33 eksik doz). Tavana yuvarlama eksik-doza karşı korur."""
    from servers import api_server as api

    f = api._duration_seconds_to_stm_minutes
    assert f(60) == 1
    assert f(61) == 2, "61 sn → 1 dk (aşağı yuvarlama) = eksik doz"
    assert f(90) == 2, "90 sn → 1 dk = %33 eksik tedavi"
    assert f(119) == 2 and f(120) == 2 and f(121) == 3
    # Geçersiz/negatif girdi güvenli
    assert f(0) == 0 and f(-5) == 0 and f("abc") == 0 and f(None) == 0


def test_dakika_birikimi_YENI_seansta_sifirlanir(api):
    """`_minute_acc` seanslar arası taşırsa önceki hastanın sensör örnekleri YENİ hastanın
    dakika-ortalamasına karışır → yanlış hastaya ait tıbbi kayıt."""
    import inspect

    src = inspect.getsource(api)
    # Hem manuel hem AI seans kurulumunda temizlenmeli
    assert src.count("_minute_acc.clear()") >= 2, (
        "_minute_acc yeni seansta temizlenmiyor → önceki hastanın ölçümleri karışır"
    )


# ───────────────────── AI PRO ─────────────────────


def test_landmark_auto_aktif_AI_Pro_seansini_GASP_ETMEZ():
    """AI Pro sürüyorken gelen bir landmark auto_adjust isteği (ikinci istemci / doğrudan API)
    AI Pro'nun per-bobin duty/fazının üzerine TEK-TİP değerler yazıyor, AI Pro'nun sürmediği
    bobin 8'i de enerjilendiriyor ve seans meta-verisini sessizce devralıyordu — iki otonom
    sürücü aynı donanımda çatışır, kayıtta yanlış mod görünür.
    """
    import inspect

    from servers import ai_router

    src = inspect.getsource(ai_router)
    assert 'return "skipped_session_active", {}' in src, (
        "landmark-auto çatışma koruması YOK → AI Pro sürerken donanımı gasp eder"
    )
    assert "if _ai_loop_active:" in src, "AI Pro aktiflik kontrolü yok"
    # Farklı modda aktif seans da korunmalı (Manuel/Otomatik)
    assert '_cur_active and _cur_mode != "AI (Auto)"' in src, (
        "farklı moddaki aktif seans landmark-auto tarafından devralınabiliyor"
    )


def test_ai_pro_sure_olcumu_MONOTONIC(api):
    """AI Pro süresi duvar saatiyle ölçülürse NTP sıçraması otonom tedaviyi erken keser
    ya da uzatır (aşırı doz)."""
    import inspect

    from servers import ai_router

    src = inspect.getsource(ai_router)
    assert "_ai_started_at = time.monotonic()" in src, (
        "AI Pro başlangıcı monotonic damgalanmıyor → NTP sıçraması süreyi bozar"
    )
    assert "time.monotonic() - _ai_started_at" in src, "kalan süre monotonic farkıyla hesaplanmıyor"


def test_ai_pro_hedef_kaybinda_bobinler_DURDURULUR():
    """Hedef kadraj dışına çıkınca/kımıldayınca HEDEFSİZ tedavi seans sonuna kadar
    sürüyordu; üstelik WS `perCoil` %0 yayınladığı için operatör bobinleri kapalı sanıyordu.
    Tek kare kaybında durdurmak kırılgan olurdu → ARDIŞIK eşik.
    """
    import inspect

    from servers import ai_router

    assert 1 <= ai_router._AI_LOST_STOP_STREAK <= 10, (
        f"_AI_LOST_STOP_STREAK makul değil: {ai_router._AI_LOST_STOP_STREAK}"
    )
    src = inspect.getsource(ai_router)
    assert "if _lost_streak == _AI_LOST_STOP_STREAK:" in src, (
        "hedef-kaybı STOP'u YOK → hedefsiz tedavi seans sonuna kadar sürer"
    )
    assert "_stop_session_coils" in src
