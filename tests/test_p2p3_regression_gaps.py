# Author: mertaygn, cglrgrkn
"""P2/P3 MUTASYON TESTİ BULGULARI — uygulanmış ama HİÇBİR testin korumadığı düzeltmeler.

P0/P1 düzeltmeleri ayrı bir turda mutasyon testinden geçirilmişti (33/33 yakalandı). Bu tur
P2/P3 kümesini kapsadı: 19 mutasyonun 10'u kaçtı. Üçü mutasyonun kendi hatasıydı (isim
mutasyonunu replace-ALL yapmak = tutarlı yeniden-adlandırma = davranış değişmez; ve bir
etiket/desen uyuşmazlığı). Geri kalanlar GERÇEK koruma boşluğuydu — bu dosya onları kapatır.

Ortak nokta: hepsi "sessizce yanlış davran" sınıfı. Hata vermezler, log basmazlar; yalnız
hasta kaydı bozulur, bobin yanlış anda durur ya da bir güvenlik geçidi etkisizleşir.
"""

import asyncio
import threading

import pytest


@pytest.fixture()
def api(monkeypatch):
    """İzole api_server (test_session_lifecycle.py'deki yerleşik desen)."""
    from servers import api_server

    monkeypatch.setattr(api_server, "_mqtt_publish", lambda *a, **k: True)
    monkeypatch.setattr(api_server, "_get_treatment_db", lambda *a, **k: None)
    monkeypatch.setattr(api_server, "_broker_reachable", lambda: True)
    with api_server._session_lock:
        api_server._active_session.clear()
    yield api_server
    with api_server._session_lock:
        api_server._active_session.clear()


# ───────────────────────── HASTA GÜVENLİĞİ ─────────────────────────


def test_stop_devralinan_seansin_TAZE_bobinlerini_DURDURMAZ(api, monkeypatch):
    """P2 TOCTOU mührü — kaçan mutasyon: `_takeover` kontrolü etkisizleştirilince takım yeşil kaldı.

    `/api/session/stop` önce kilit altında `is_active=False` yapıp kilidi BIRAKIR, sonra
    `await asyncio.to_thread(_stop_session_coils, ...)` ile donanıma iner. O await penceresinde
    başka bir istemci `/api/session/start` atarsa YENİ seans bobinleri enerjiler ve hemen
    ardından bu eski `/stop` AYNI fiziksel bobinleri durdurur: yeni seans sessizce ölür,
    UI 'sürüyor' sanır, coil-run/sensör kayıtları bozulur.
    """
    durdurulan = []
    monkeypatch.setattr(api, "_stop_session_coils", lambda ids: durdurulan.append(list(ids)))

    with api._session_lock:
        api._active_session.update(
            {
                "is_active": True,
                "session_id": "seans_A",
                "coil_ids": [1, 2],
                "duration_minutes": 20,
                "start_time": 0,
                "started_epoch": 0,
            }
        )

    # Pencere `is_active=False` ile mühür kontrolü ARASIDIR; oradaki tek ara adım
    # `_emit_minute_averages`. Başka bir istemcinin tam o anda /session/start atmasını
    # birebir bu noktada taklit ediyoruz.
    def _devral(_ts):
        with api._session_lock:
            api._active_session.update({"is_active": True, "session_id": "seans_B", "coil_ids": [1, 2]})

    monkeypatch.setattr(api, "_emit_minute_averages", _devral)

    async def _duz(fn, *a, **kw):
        return fn(*a, **kw)

    monkeypatch.setattr(api.asyncio, "to_thread", _duz)
    asyncio.run(api.stop_session())

    assert durdurulan == [], (
        "eski /stop, devralan YENİ seansın taze bobinlerini durdurdu → hasta tedavisi "
        "sessizce kesilir (TOCTOU mührü etkisiz)"
    )


def test_devralma_YOKSA_bobinler_normal_durdurulur(api, monkeypatch):
    """Mühür fazla-koruyucu olmamalı: devralma yoksa donanım STOP'u ÇALIŞMALI.
    (Aksi halde 'hiç durdurma' ile testi geçen bozuk bir düzeltme fark edilmezdi.)"""
    durdurulan = []
    monkeypatch.setattr(api, "_stop_session_coils", lambda ids: durdurulan.append(list(ids)))

    with api._session_lock:
        api._active_session.update(
            {
                "is_active": True,
                "session_id": "seans_A",
                "coil_ids": [1, 2],
                "duration_minutes": 20,
                "start_time": 0,
                "started_epoch": 0,
            }
        )

    async def _duz(fn, *a, **kw):
        return fn(*a, **kw)

    monkeypatch.setattr(api.asyncio, "to_thread", _duz)
    asyncio.run(api.stop_session())

    assert durdurulan == [[1, 2]], "devralma yokken bobinler durdurulmadı"


def test_RETAINED_mqtt_alarmi_canli_olcum_sayilmaz(api):
    """P3 — kaçan mutasyon: `not is_retained` kontrolü kalkınca takım yeşil kaldı.

    Broker'a retained bırakılmış ESKİ bir `sensors` mesajı, backend her yeniden bağlandığında
    ANINDA teslim edilir. Canlı ölçüm sayılırsa: (1) bayat sıcaklık canlı görünür,
    (2) alarm eşiğini aşan retained bir değer yeniden bağlanmada acil-durdurma tetikler —
    hasta üzerinde süren tedavi sebepsiz kesilir.
    """
    import inspect

    src = inspect.getsource(api._on_mqtt_message) if hasattr(api, "_on_mqtt_message") else inspect.getsource(api)
    assert 'msg_type == "sensors" and not is_retained' in src, (
        "retained `sensors` mesajı canlı ölçüm gibi işleniyor → bayat veri + sebepsiz E-STOP"
    )
    assert 'msg_type == "status" and not is_retained' in src, "retained `status` mesajı canlı durum gibi işleniyor"


def test_telemetrisiz_bobin_icin_SAHTE_sifir_sensor_yazilmaz(api, monkeypatch):
    """P3 — kaçan mutasyon: telemetri süzgeci kalkınca takım yeşil kaldı.

    Hiç MQTT telemetrisi gelmemiş bir bobin için `_live_state` varsayılanları 0.0'dır.
    Bunları biriktirmek, hasta geçmişine/PDF raporuna "0.0 °C ÖLÇÜLDÜ" diye geçer —
    aşırı-ısınma analizi ve sahibine giden rapor yanlış veriyle üretilir.
    """
    import inspect

    src = inspect.getsource(api)
    assert "_coil_last_telemetry.get(cid - 1) is None" in src, (
        "sensör biriktirme, telemetri KAYNAĞI olmayan bobinleri süzmüyor → geçmişe sahte 0.0 yazılır"
    )


def test_sure_watchdogu_DUVAR_SAATI_sicramasindan_etkilenmez(api, monkeypatch):
    """P2 — ilk mutasyonum zayıftı (start_mono=None geri-düşüşü tetikliyordu); asıl kilitlenmesi
    gereken özellik bu: seans süresi MONOTONIC saatle ölçülmeli.

    NTP düzeltmesi / yaz-kış saati duvar saatini ileri-geri atlatır. Süre ölçümü duvar saatine
    dayanırsa seans ya erken kesilir (tedavi eksik) ya da geç biter (aşırı doz).
    """
    import inspect

    src = inspect.getsource(api)
    assert '"start_mono": time.monotonic()' in src or '"start_mono": _t.monotonic()' in src, (
        "seans başlangıcı monotonic damgalanmıyor"
    )
    # Watchdog monotonic'i TERCİH etmeli (duvar saati yalnız damga yoksa yedek)
    assert "_t.monotonic() - _sm" in src, (
        "süre-watchdog'u monotonic farkı kullanmıyor → NTP sıçraması seansı erken/geç bitirir"
    )


# ───────────────────────── GÜVENLİK / VERİ BÜTÜNLÜĞÜ ─────────────────────────


def test_stm_baglanti_durumu_ve_emit_AYNI_kilitte(api):
    """P3 — kaçan mutasyon: emit kilidin dışına çıkarılınca takım yeşil kaldı.

    Karşılaştırma kilit içinde, emit dışında yapılırsa iki thread (reader/sender/reconnect)
    aynı geçişi eş-zamanlı görüp ÇİFT emit edebilir; ters sıralanan emit'lerde 'kopuk' bildirimi
    'bağlı'dan sonra işlenip son durum KAYBOLUR → UI ve acil-durdurma zinciri yanlış durumda kalır.
    """
    import ast
    import inspect
    import textwrap

    import headless_core

    # metot kaynağı girintili gelir → ast.parse için dedent şart
    kaynak = textwrap.dedent(inspect.getsource(headless_core.HeadlessCore._set_stm_connected))
    fn = ast.parse(kaynak).body[0]
    withler = [n for n in ast.walk(fn) if isinstance(n, ast.With)]
    assert withler, "_set_stm_connected artık kilit KULLANMIYOR"

    # emit/publish çağrısı bir `with <lock>` bloğunun İÇİNDE olmalı
    def _emit_cagrilari(node):
        return [
            c
            for c in ast.walk(node)
            if isinstance(c, ast.Call) and getattr(c.func, "attr", "") in ("_publish_event", "emit", "publish")
        ]

    tum = _emit_cagrilari(fn)
    assert tum, "_set_stm_connected hiç bildirim yapmıyor (test kurulumu uçla eşleşmiyor)"
    kilitli = [c for w in withler for c in _emit_cagrilari(w)]
    assert len(kilitli) == len(tum), (
        "durum bildirimi kilidin DIŞINDA yapılıyor → çift/ters-sıralı emit, kaybolan son durum"
    )


def test_auth_db_ACL_sureci_disari_kilitlemez():
    """P3 — kaçan mutasyon: `keep_current_user=False` yapılınca takım yeşil kaldı.

    `lock_down_file` yalnız SYSTEM+Administrators verir. auth DB'si sürekli AÇIK tutulur;
    süreç kendi hesabını kaybederse `unable to open database file` alır ve backend BAŞLAMAZ.
    Bu gerçek makinede yaşandı (auth_users.db kilitlendi, elle icacls ile kurtarıldı).
    """
    import inspect

    from database import auth_db

    src = inspect.getsource(auth_db)
    assert "keep_current_user=True" in src, (
        "auth DB ACL'i keep_current_user=True KULLANMIYOR → süreç kendi DB'sini açamaz hale gelir"
    )
    assert "keep_current_user=False" not in src


def test_acilis_VACUUM_u_AKTIF_SEANSTA_calismaz(api):
    """P3 — kaçan mutasyon: `and not _sess_active` kalkınca takım yeşil kaldı.

    VACUUM tüm DB'yi yeniden yazar ve ÖZEL kilit tutar. `busy_timeout` 5 sn olduğundan tedavi
    sırasındaki sensör/coil-run yazımları zaman aşımına düşer → o dakikanın telemetrisi KAYBOLUR.
    """
    import inspect

    src = inspect.getsource(api)
    assert "run_count % 7 == 0 and not _sess_active" in src, (
        "VACUUM aktif seans kontrolü YOK → tedavi sırasında DB kilitlenir, telemetri kaybolur"
    )
    # ⚠️ BOŞLUĞA DUYARSIZ. Eskiden satır birebir aranıyordu (`= True   # emin...`, üç boşluk);
    # `ruff format` boşluğu ikiye indirince test kırıldı — oysa DAVRANIŞ hiç değişmemişti.
    # Kaynak-metin iddiası ne kadar dar olursa, biçimlendiriciyle o kadar yalancı kırılır.
    import re as _re

    assert _re.search(r"_sess_active\s*=\s*True\s*#\s*emin degilsek VACUUM YAPMA", src), (
        "seans durumu okunamazsa fail-safe VACUUM-YAPMA davranışı kalkmış"
    )


def test_guncelleme_guardi_installer_baslayinca_ACIK_kalir():
    """P3 — kaçan mutasyon: guard koşulsuz kapatılınca takım yeşil kaldı.

    Installer servisi durdurup EXE'yi değiştirecek. Guard o pencerede kapanırsa
    `/session/start` ve `/ai/pro/start` yeniden serbest kalır ve TAM O ANDA tedavi
    başlatılabilir → bobinler kontrolcüsüz kalır.
    """
    import ast
    import inspect

    from servers import update_manager as um

    for ad in ("apply_update", "rollback_update"):
        fn = getattr(um, ad, None)
        if fn is None:
            continue
        src = inspect.getsource(fn)
        tree = ast.parse(src)
        finallyler = [n for n in ast.walk(tree) if isinstance(n, ast.Try) and n.finalbody]
        assert finallyler, f"{ad}: finally bloğu yok"
        govde = "\n".join(ast.unparse(s) for f in finallyler for s in f.finalbody)
        assert "not _installer_launched" in govde, (
            f"{ad}: guard KOŞULSUZ kapatılıyor → installer EXE'yi değiştirirken tedavi başlatılabilir"
        )


# ── Doğrulama turunda BULUNAN yeni açık (2026-08-05) ─────────────────────────


def test_seans_devralinca_SAHIPSIZ_kalan_bobinler_durdurulur(api, monkeypatch):
    """Devralma önceki seansın DB satırlarını kapatıyordu ama DONANIMA dokunmuyordu.

    Somut yol: `AI (Auto)` landmark sürüşü bobin 1-8'i 30 dk için enerjiler → operatör
    `AI Pro` başlatır; o yalnız 1-7'yi sahiplenir. Bobin 8'i artık ne AI Pro döngüsünün
    hedef-kayıp STOP'u (`range(1,8)`) ne de süre-watchdog'u (`sess["coil_ids"]`=1-7)
    kapsar → ESP kendi 30 dk süresi dolana kadar CANLI HAYVAN ÜZERİNDE enerjili kalır.

    Telafi katmanları var (acil durdurma ESP 6-8'i kapsar, `/ai/pro/stop` 1-8 kullanır,
    ESP kendi süresiyle durur) — bu yüzden felaket değil; ama kök sebep devralmanın
    donanıma hiç dokunmamasıydı.
    """
    durdurulan = []
    monkeypatch.setattr(api, "_stop_session_coils", lambda ids: durdurulan.extend(int(i) for i in ids))
    monkeypatch.setattr(api, "_finish_coil_run", lambda cid: None)

    # Önceki seans: AI (Auto), bobin 1-8
    with api._session_lock:
        api._active_session.update(
            {
                "is_active": True,
                "session_id": "auto_1",
                "mode": "AI (Auto)",
                "coil_ids": list(range(1, 9)),
                "db_session_id": None,
                "start_time": 0,
                "started_epoch": 0,
                "duration_minutes": 30,
            }
        )

    # AI Pro devralır — YALNIZ 1-7'yi sahiplenir
    api.start_ai_session(0.0, 0.0, 20, range(1, 8), "AI Pro")

    assert 8 in durdurulan, "devralmada sahipsiz kalan bobin 8 DURDURULMADI → ESP süresi dolana kadar enerjili kalır"
    # Devredilen bobinlere gereksiz kesinti uygulanmamalı (yeni seans onları sürecek)
    assert not (set(range(1, 8)) & set(durdurulan)), (
        f"yeni seansın sahiplendiği bobinler de durduruldu {durdurulan} → gereksiz kesinti"
    )


def test_devralmada_TUM_bobinler_devredilirse_STOP_gonderilmez(api, monkeypatch):
    """Fazla-koruma olmasın: önceki seansın bobinlerinin hepsi devredildiyse donanıma
    dokunulmamalı (aksi halde her devralmada tedavi bir an kesilirdi)."""
    durdurulan = []
    monkeypatch.setattr(api, "_stop_session_coils", lambda ids: durdurulan.extend(int(i) for i in ids))
    monkeypatch.setattr(api, "_finish_coil_run", lambda cid: None)

    with api._session_lock:
        api._active_session.update(
            {
                "is_active": True,
                "session_id": "manuel_1",
                "mode": "Manuel",
                "coil_ids": [1, 2],
                "db_session_id": None,
                "start_time": 0,
                "started_epoch": 0,
                "duration_minutes": 20,
            }
        )

    api.start_ai_session(0.0, 0.0, 20, [1, 2, 3], "AI Pro")
    assert durdurulan == [], f"tüm bobinler devredildiği hâlde STOP gönderildi: {durdurulan}"
