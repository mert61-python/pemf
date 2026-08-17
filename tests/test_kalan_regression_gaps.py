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


def _yorumsuz_kaynak(modul_ya_da_nesne) -> str:
    """Kaynağı YORUM ve DOCSTRING'lerden SOYARAK döndür — YERLEŞİMİ BOZMADAN.

    ⚠️ NEDEN (denetim 2026-08-17): bu dosyadaki kapılar `inspect.getsource(...)` + `"<dize>" in src`
    ile çalışıyordu, yani gerçek kontrolü SİLİP yerine aynı metni içeren bir YORUM bırakan biri
    kapıdan GEÇEBİLİYORDU (deneysel olarak kanıtlandı). Bu depoda "yapısal kapı kendi yorumuyla
    kandırıldı" hatası DÖRT kez oldu.

    ⚠️ YERLEŞİM KORUNUR: yorum/docstring aralıkları BOŞLUKLA doldurulur, kaynak yeniden
    üretilmez. `ast.unparse` (normalleştirir: tırnak biçimi, boşluk) ve token'ları boşlukla
    birleştirmek (`_minute_acc.clear()` → `_minute_acc . clear ( )`) DENENDİ ve ikisi de mevcut
    kapıları YANLIŞ-KIRMIZI'ya çevirdi — ölçüldü.
    """
    import inspect
    import io as _io
    import tokenize

    ham = inspect.getsource(modul_ya_da_nesne)
    satirlar = ham.splitlines(keepends=True)
    # Satır başlangıç ofsetleri (1-tabanlı satır no → mutlak indeks)
    ofset, top = [0], 0
    for sat in satirlar:
        top += len(sat)
        ofset.append(top)

    parcalar = list(ham)
    onceki = tokenize.NEWLINE
    try:
        for tok in tokenize.generate_tokens(_io.StringIO(ham).readline):
            docstring = tok.type == tokenize.STRING and onceki in (
                tokenize.NEWLINE,
                tokenize.NL,
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.ENCODING,
            )
            if tok.type == tokenize.COMMENT or docstring:
                bas = ofset[tok.start[0] - 1] + tok.start[1]
                son = ofset[tok.end[0] - 1] + tok.end[1]
                for k in range(bas, min(son, len(parcalar))):
                    if parcalar[k] != "\n":  # satır yapısı bozulmasın
                        parcalar[k] = " "
            if tok.type != tokenize.NL:
                onceki = tok.type
    except tokenize.TokenError:
        raise AssertionError("kaynak tokenize edilemedi; kapi guvenilir degil") from None
    return "".join(parcalar)


def test_bayat_ESP_telemetrisinde_GERCEK_stop_yayinlanir(api):
    """Bobin YALNIZCA 'durdu' işaretlenirse operatöre yanlış güvence verilir.

    ESP güç kaybıyla değil WiFi/broker kopmasıyla sessizleştiyse kendi son `start`
    komutuyla HÂLÂ SÜRÜYOR olabilir (kendi duration'ı bitene dek). UI 'durdu' gösterirken
    bobin fiziksel olarak canlı hayvan üzerinde enerjili kalır. Watchdog gerçek bir STOP
    yayınlamalı — ESP geri geldiğinde komutu alır.
    """
    src = _yorumsuz_kaynak(api)  # ⚠️ yorum/docstring SOYULU
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


def test_kapanis_ESP_STOP_butcesi_GERCEKTEN_uygulanir(monkeypatch):
    """Bütçe uygulanmazsa erişilemeyen broker'da kapanış 3 bobin × ~2 sn × 2 publish kadar uzar ve
    Windows SCM stop-timeout'unu aşar → servis "durduruldu" sayılmadan ÖLDÜRÜLÜR, kapanış
    mutabakatı yarım kalır.

    ⚠️ DAVRANIŞSAL (denetim 2026-08-17): eskiden `inspect.getsource` + `"daemon=True" in src`
    biçiminde METİN araması yapıyordu. Gerçek `join(timeout=...)`ı silip yerine aynı metni içeren
    bir YORUM bırakan biri kapıdan GEÇİYORDU (deneysel olarak kanıtlandı). Artık fonksiyon
    GERÇEKTEN çağrılıyor ve bütçenin uygulandığı ÖLÇÜLÜYOR.
    """
    import threading
    import time
    import types

    import backend_service as bs

    assert bs._ESP_STOP_BUDGET_S > 0 and bs._STM_FLUSH_BUDGET_S > 0
    toplam = bs._GRACEFUL_SHUTDOWN_TIMEOUT_S + bs._SAFE_STOP_BUDGET_S
    assert toplam < 15, f"toplam kapanis butcesi {toplam}s >= NSSM 15s -> servis oldurulur"

    # Bütçeler KISALTILIR: fonksiyon ikisini de ÇAĞRI ANINDA modül global'inden okuyor.
    monkeypatch.setattr(bs, "_STM_FLUSH_BUDGET_S", 0.4)
    monkeypatch.setattr(bs, "_ESP_STOP_BUDGET_S", 0.3)

    salinim, kayit = threading.Event(), []

    class _Q:  # ASLA boşalmaz → STM flush bütçesi ölçülür
        yoklama = 0

        def empty(self):
            self.yoklama += 1
            return False

    class _HW:
        cagrildi = False

        def stop_all_coils(self):
            self.cagrildi = True

    def _publish(topic, payload):  # broker ERİŞİLEMEZ taklidi
        kayit.append(threading.current_thread())
        salinim.wait(30.0)
        return True

    q, hw = _Q(), _HW()
    sahte = types.SimpleNamespace(
        state=types.SimpleNamespace(hardware=hw, core=types.SimpleNamespace(_hw_send_queue=q)),
        _mqtt_publish=_publish,
    )

    # ⚠️ BEKÇİ ZORUNLU: `join` TIMEOUT'suz hâle dönerse bu test SONSUZA kilitlenirdi
    # (pytest-timeout bu ortamda kurulu DEĞİL). 6 sn'de salınım açılır → test ASILMAZ, KIRMIZI biter.
    bekci = threading.Timer(6.0, salinim.set)
    bekci.daemon = True
    bekci.start()
    t0 = time.monotonic()
    try:
        bs._safe_stop_outputs(sahte)
    finally:
        gecen = time.monotonic() - t0
        salinim.set()  # daemon thread'ler sızmasın
        bekci.cancel()

    ana = threading.main_thread()
    assert hw.cagrildi and q.yoklama > 1, "STM flush dongusu HIC kosmadi"
    assert gecen >= bs._STM_FLUSH_BUDGET_S - 0.05, "STM flush butcesi hic beklenmedi (_deadline yok)"
    assert len(set(kayit)) == 3, f"3 bobin PARALEL denenmedi (farkli thread={len(set(kayit))}, publish={len(kayit)})"
    assert all(t is not ana for t in kayit), "ESP STOP'lari ANA thread'de SIRAYLA gidiyor -> butce YOK"
    assert all(t.daemon for t in kayit), "ESP STOP thread'leri daemon DEGIL -> butce asiminda surec takilir"
    assert gecen < bs._STM_FLUSH_BUDGET_S + bs._ESP_STOP_BUDGET_S + 1.0, (
        f"kapanis {gecen:.2f}s surdu -> join TIMEOUT'suz, butce uygulanmiyor (sadece yazili)"
    )


def test_bayat_payload_TEKRAR_gonderilmez():
    """Seri yeniden bağlanmada `last_payload` körlemesine tekrar gönderilirse ESKİ bir sürüş komutu
    (ör. iptal edilmiş bir tedavinin duty'si) bobinlere yeniden uygulanır. Yaş sınırı bunu keser;
    keep-alive zaten güncel durumu tazeler.

    ⚠️ DAVRANIŞSAL (denetim 2026-08-17): eskiden MODÜL-GENELİ metin araması yapıyordu
    (`"(time.monotonic() - ts) > _RETRY_MAX_AGE_S" in src`) — yani kontrolü silip aynı metni bir
    YORUMA yazmak kapıyı geçiriyordu. Artık GERÇEK closure'ın bytecode'u çalıştırılıyor.
    """
    import logging
    import queue
    import time
    import types

    import headless_core

    assert 0 < headless_core._RETRY_MAX_AGE_S <= 5, (
        f"_RETRY_MAX_AGE_S makul degil: {headless_core._RETRY_MAX_AGE_S} (devasa deger = bayat komut replay'i serbest)"
    )

    # `retry_last_payload` bir CLOSURE. Kod nesnesini alıp GERÇEK bytecode'u koşturuyoruz:
    # yorum/docstring GÖRÜLMEZ ve DB/seri port/thread GEREKMEZ.
    kod = next(
        (
            c
            for c in headless_core.HeadlessCore._hw_sender_worker.__code__.co_consts
            if getattr(c, "co_name", "") == "retry_last_payload"
        ),
        None,
    )
    assert kod is not None, "retry_last_payload closure'i YOK -> yas kapisi silinmis/tasinmis"
    assert kod.co_freevars == ("last_payload", "self"), (
        f"closure sozlesmesi degisti, kapi guncellenmeli: {kod.co_freevars}"
    )

    def _hucre(v):
        return (lambda x: lambda: x)(v).__closure__[0]

    def _kur(yas_s: float):
        class _Self:
            pass

        o = _Self()
        o.logger = logging.getLogger("test-retry")
        o._hw_send_queue = queue.Queue(maxsize=4)
        lp = [("STM_PAKET", b"udp", "1.2.3.4", 5000), time.monotonic() - yas_s]
        fn = types.FunctionType(kod, headless_core.__dict__, "retry_last_payload", None, (_hucre(lp), _hucre(o)))
        return fn, lp, o

    # (1) KARŞIT-KANIT: TAZE paket tekrar GÖNDERİLİR — kapı "her şeyi at"a dönüşmemeli.
    fn, lp, o = _kur(0.0)
    fn()
    assert o._hw_send_queue.qsize() == 1, "TAZE paket tekrar gonderilmedi -> NACK telafisi OLDU"

    # (2) AYIRT EDİCİ İDDİA: BAYAT paket kuyruğa GİRMEZ.
    fn, lp, o = _kur(headless_core._RETRY_MAX_AGE_S + 1.0)
    fn()
    assert o._hw_send_queue.qsize() == 0, (
        "bayat payload yas kontrolu YOK -> yeniden baglanmada eski surus komutu tekrar uygulanir "
        "(STOP'tan SONRA bobin yeniden enerjilenir)"
    )
    # ⚠️ `lp[0] is None` İDDİA EDİLMEZ: başarı yolu da None yazar, yani mutantta da True çıkar
    # (ölçüldü) → tek başına YANLIŞ-YEŞİL olurdu.


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
    src = _yorumsuz_kaynak(api)  # ⚠️ yorum/docstring SOYULU
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
    from servers import ai_router

    src = _yorumsuz_kaynak(ai_router)  # ⚠️ yorum/docstring SOYULU
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
    from servers import ai_router

    src = _yorumsuz_kaynak(ai_router)  # ⚠️ yorum/docstring SOYULU
    assert "_ai_started_at = time.monotonic()" in src, (
        "AI Pro başlangıcı monotonic damgalanmıyor → NTP sıçraması süreyi bozar"
    )
    assert "time.monotonic() - _ai_started_at" in src, "kalan süre monotonic farkıyla hesaplanmıyor"


def test_ai_pro_hedef_kaybinda_bobinler_DURDURULUR():
    """Hedef kadraj dışına çıkınca/kımıldayınca HEDEFSİZ tedavi seans sonuna kadar
    sürüyordu; üstelik WS `perCoil` %0 yayınladığı için operatör bobinleri kapalı sanıyordu.
    Tek kare kaybında durdurmak kırılgan olurdu → ARDIŞIK eşik.
    """
    from servers import ai_router

    assert 1 <= ai_router._AI_LOST_STOP_STREAK <= 10, (
        f"_AI_LOST_STOP_STREAK makul değil: {ai_router._AI_LOST_STOP_STREAK}"
    )
    src = _yorumsuz_kaynak(ai_router)  # ⚠️ yorum/docstring SOYULU
    assert "if _lost_streak == _AI_LOST_STOP_STREAK:" in src, (
        "hedef-kaybı STOP'u YOK → hedefsiz tedavi seans sonuna kadar sürer"
    )
    assert "_stop_session_coils" in src
