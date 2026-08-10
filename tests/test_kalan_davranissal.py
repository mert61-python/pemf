# Author: mertaygn, cglrgrkn
"""KAÇAN 11 mutasyon için DAVRANIŞSAL regresyon koruması.

Bu turun en önemli dersi: `assert "..." in inspect.getsource(...)` tipi kaynak-dizgesi
iddiaları koruma SAĞLAMIYOR. Üç ayrı biçimde deliniyorlar:

  1. Değer bozulur, dizge yerinde kalır      → `_deadline = monotonic() - 1`
  2. Kod erişilemez olur, dizge yerinde kalır → `for cid, snap in []:`
  3. Arama İSTENMEYEN ikinci eşleşmeye takılır → `if not _backup_ok` iki kez geçiyor;
     mutasyon asıl korumayı silse bile `.index()` diğerini bulup testi yeşil bırakıyor.

(2) ve (3) yalnız benim yazdıklarımda değil, denetimden kalan MEVCUT testlerde de vardı —
yani takım bir süredir boş güvence veriyordu. Buradaki testler kodu GERÇEKTEN çalıştırır.
"""

import time

import pytest

# ───────────────────── BOBİN GÜVENLİĞİ ─────────────────────


def test_bayat_ESP_bobinine_GERCEK_stop_yayinlanir(monkeypatch):
    """Kaçan mutasyon: `for cid, snap in changed:` → `in []:` (publish kodu kaynakta DURUYOR
    ama erişilemez). Kaynak-varlığı iddiası bunu göremez; watchdog'u gerçekten koştururuz.

    ESP güç kaybıyla değil WiFi/broker kopmasıyla sessizleştiyse kendi son `start` komutuyla
    HÂLÂ SÜRÜYOR olabilir. UI 'durdu' gösterirken bobin canlı hayvan üzerinde enerjili kalır.
    """
    from servers import api_server as api

    yayinlar = []
    monkeypatch.setattr(api, "_mqtt_publish", lambda t, p: yayinlar.append((t, p)) or True)
    monkeypatch.setattr(api, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(api, "_push_notification", lambda *a, **k: None)

    # Bobin 6: telemetri ALMIŞ ama eşiği aşacak kadar eski + hâlâ connected
    idx = 5
    with api._live_state_lock:
        api._live_state["coils"][idx]["connected"] = True
        api._live_state["coils"][idx]["running"] = True
    api._coil_last_telemetry[idx] = time.monotonic() - (api.ESP_STALE_SEC + 10)

    # Sonsuz döngüyü TEK tur çalıştır: sleep `try` bloğunun DIŞINDA → oradan çık.
    class _Dur(Exception):
        pass

    def _sleep(_s):
        raise _Dur()

    monkeypatch.setattr(api.time, "sleep", _sleep)
    with pytest.raises(_Dur):
        api._esp_telemetry_watchdog()

    stoplar = [(t, p) for t, p in yayinlar if p.get("command") == "stop"]
    assert stoplar, (
        "bayat ESP bobinine STOP YAYINLANMADI → UI 'durdu' derken bobin kendi duration'ı bitene kadar enerjili kalır"
    )
    assert any(t == "pemf/coil/6/control" for t, _ in stoplar), f"yanlış konu: {stoplar}"
    assert any(p.get("reason") == "telemetry_stale" for _, p in stoplar)


def test_kapanis_ESP_STOP_butcesi_thread_leri_GERCEKTEN_bekler(monkeypatch):
    """Kaçan mutasyon: `_deadline = monotonic() + BUDGET` → `- 1` (join(timeout=0)).
    Dizge `_deadline`/`join(timeout=` kaynakta kaldığı için kaynak testi kaçırdı.

    Bütçe uygulanmazsa fonksiyon publish thread'lerini BEKLEMEDEN döner → süreç kapanırken
    ESP'lere STOP ulaşmaz ve bobinler firmware ölü-adam devresine kadar açık kalır.
    """
    import backend_service as bs

    yayinlar = []

    class _Sahte:
        class state:
            hardware = None
            core = None

        @staticmethod
        def _mqtt_publish(topic, payload):
            time.sleep(0.25)  # yavaş broker
            yayinlar.append(topic)
            return True

    bs._safe_stop_outputs(_Sahte)

    # DÖNER DÖNMEZ: 3 ESP bobini × 2 konu = 6 publish tamamlanmış olmalı (bütçe 3 sn > 0,25 sn)
    assert len(yayinlar) == 6, (
        f"kapanışta yalnız {len(yayinlar)}/6 STOP yayınlandı → bütçe thread'leri beklemiyor, "
        "bobinler STOP almadan süreç kapanır"
    )


def test_kapanis_STM_flush_butcesi_kuyrugu_GERCEKTEN_bekler(monkeypatch):
    """Kaçan mutasyon: `_deadline = time() + BUDGET` → `- 1` (while koşulu anında False).

    STM STOP yalnız async kuyruğa konur; sender thread seri porta YAZMADAN süreç kapanırsa
    bobinler firmware süre-watchdog'u dolana kadar çalışmaya devam eder.
    """
    import backend_service as bs

    bos_cagrilari = {"n": 0}

    class _Kuyruk:
        def empty(self):
            bos_cagrilari["n"] += 1
            return bos_cagrilari["n"] > 3  # ilk 3 yoklamada DOLU

    class _Donanim:
        def __init__(self):
            self.durduruldu = False

        def stop_all_coils(self):
            self.durduruldu = True

    hw = _Donanim()

    class _Sahte:
        class state:
            hardware = hw

            class core:
                _hw_send_queue = _Kuyruk()

        @staticmethod
        def _mqtt_publish(topic, payload):
            return True

    bs._safe_stop_outputs(_Sahte)

    assert hw.durduruldu, "stop_all_coils çağrılmadı"
    assert bos_cagrilari["n"] >= 2, (
        f"kuyruk yalnız {bos_cagrilari['n']} kez yoklandı → flush bütçesi BEKLEMİYOR; "
        "STM STOP seri porta yazılmadan süreç kapanır"
    )


def test_landmark_auto_AI_Pro_aktifken_donanima_DOKUNMAZ():
    """Kaçan mutasyon: `if _ai_loop_active:` gövdesindeki return `pass` yapıldı — ama
    `return "skipped_session_active", {}` kaynakta İKİNCİ kez geçtiği için dizge iddiası
    yeşil kaldı. Konumu bağlayan YAPISAL (AST) iddia gerekiyor.

    `_drive_landmark_auto` iç-içe bir closure olduğundan doğrudan çağrılamıyor.
    """
    import ast
    import inspect

    from servers import ai_router

    tree = ast.parse(inspect.getsource(ai_router))
    hedef = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.If) and isinstance(n.test, ast.Name) and n.test.id == "_ai_loop_active"
    ]
    assert hedef, "`if _ai_loop_active:` koruması KAYBOLMUŞ"

    korumali = False
    for n in hedef:
        for s in n.body:
            if isinstance(s, ast.Return) and "skipped_session_active" in ast.unparse(s):
                korumali = True
    assert korumali, (
        "AI Pro aktifken landmark-auto ERKEN DÖNMÜYOR → iki otonom sürücü aynı donanımda "
        "çatışır, AI Pro'nun per-bobin duty/fazı tek-tip değerlerle ezilir, sürmediği bobin 8 "
        "enerjilenir ve seans meta-verisi sessizce devralınır"
    )


# ───────────────────── VERİ BÜTÜNLÜĞÜ ─────────────────────


def test_gecersiz_yedekle_rollback_CANLI_DByi_yok_etmez(temp_app_data, monkeypatch):
    """Kaçan mutasyon: `if not _backup_ok:` → `if False:`.

    Mevcut test (`test_migration_rollback_requires_valid_backup`) bunu kaçırıyordu çünkü
    `src.index("if not _backup_ok")` aynı metotta İKİNCİ bir eşleşme buluyor (yedek
    geçerliliğini HESAPLAYAN satır). Koruma tamamen kaldırılsa bile yeşil kalıyordu.
    Bu test davranışa bakar: geçersiz yedekle canlı DB'nin satırları DURMALI.
    """
    from database.treatment_history_db import TreatmentHistoryDB

    db = TreatmentHistoryDB(temp_app_data)
    sid = db.start_session("Manuel", patient_name="Boncuk")
    assert len(db.get_session_history(limit=10)) == 1
    db.close_connections()

    # Yedek 0-BAYT (disk dolu taklidi) + migration PATLASIN
    def _bos_yedek(path):
        open(path, "wb").close()  # 0 bayt → geçersiz
        return True

    monkeypatch.setattr(TreatmentHistoryDB, "create_backup", lambda self, p: _bos_yedek(p))
    monkeypatch.setattr(
        TreatmentHistoryDB,
        "_ensure_schema_version",
        lambda self: (_ for _ in ()).throw(RuntimeError("migration patladi")),
    )

    # Metot `current_version >= TARGET_SCHEMA_VERSION` ise ERKEN DÖNER; taze DB zaten
    # hedef sürümde olduğundan migration yolunu zorlamak için sürümü 0 gösteriyoruz.
    monkeypatch.setattr(TreatmentHistoryDB, "_get_system_setting", lambda self, k: "0")

    db2 = TreatmentHistoryDB.__new__(TreatmentHistoryDB)
    db2.app_data_dir = temp_app_data
    db2.db_path = temp_app_data / "pemf_treatment_history.db"
    import logging
    import threading as _th

    db2.logger = logging.getLogger("t")
    db2._local = _th.local()
    db2._lock = _th.Lock()
    db2._conn_generation = 0
    db2._live_conns = {}
    db2._pool_lock = _th.Lock()

    with pytest.raises(RuntimeError):
        db2._run_startup_migrations_with_rollback()

    # Yamaları GERİ AL — aksi halde aşağıdaki taze örnek de patlar (ölçtüğümüz şey o değil)
    monkeypatch.undo()

    # KRİTİK: canlı DB hâlâ yerinde ve okunabilir olmalı
    db3 = TreatmentHistoryDB(temp_app_data)
    assert len(db3.get_session_history(limit=10)) == 1, (
        "geçersiz yedekle rollback canlı DB'yi EZDİ → tüm tedavi geçmişi kalıcı kayıp"
    )
    assert sid


def test_plain_bak_ACL_basarisizsa_SILINIR(temp_app_data, monkeypatch):
    """`.plain.bak` = tüm eski hasta PII'sinin DÜZ-METİN tam kopyası; SQLCipher'ı tamamen
    baypas eder. ACL uygulanamıyorsa korumasız escrow şifrelemenin kendisini anlamsız kılar
    → dosya SİLİNMELİ (fail-closed)."""
    import inspect
    import re

    from database import treatment_history_db as thdb

    src = inspect.getsource(thdb.TreatmentHistoryDB._migrate_to_encrypted_if_needed)

    # ⚠️ `"PEMF_KEEP_PLAIN_BAK" in src` YETMEZ: `PEMF_KEEP_PLAIN_BAK_MUT` gibi bir yeniden
    # adlandırma o iddiayı SUBSTRING olarak karşılar (mutasyon testi bunu yakaladı — aynı
    # tuzağa `if not _backup_ok` ve `skipped_session_active` testlerinde de düşülmüştü).
    # Tam-kelime + gerçek okuma biçimi aranır.
    assert re.search(r'os\.getenv\(\s*["\']PEMF_KEEP_PLAIN_BAK["\']', src), (
        "PEMF_KEEP_PLAIN_BAK bayrağı okunmuyor → escrow'u kapatma yolu kayıp"
    )

    # Fail-closed sözleşmesi: escrow İSTENSE bile ACL uygulanamıyorsa dosya SİLİNİR.
    assert re.search(r'_locked\s*=\s*bool\(\s*lock_down_file\(', src), "ACL sonucu okunmuyor"

    # ⚠️ 2026-08-08: VARSAYILAN TERSİNE ÇEVRİLDİ (escrow-sakla → güvenli-sil), çünkü hasta DB'si
    # (`sqlcipher_util`) bu kararı Audit P3'te zaten almıştı ve tedavi DB'si geride kalmıştı.
    # Eski yapı `if not _locked or not _keep:` idi; artık `if _keep:` bloğu içinde ACL denenir,
    # kilitlenemezse (ve varsayılanda hep) güvenli-silmeye düşülür.
    assert re.search(r'os\.getenv\(\s*["\']PEMF_KEEP_PLAIN_BAK["\']\s*,\s*["\']0["\']', src), (
        "escrow VARSAYILAN AÇIK kalmış → at-rest şifreleme açılınca her klinikte tüm geçmişin "
        "düz-metin tam kopyası diskte kalır (site 'cihazda şifreli' diye beyan ederken)"
    )

    # Silmenin GÜVENLİ olması: yalnız `os.remove` içeriği diskte bırakır (kurtarılabilir).
    assert "os.urandom" in src and "fsync" in src, (
        "yedek silinmeden ÖNCE üzerine yazılmıyor → düz-metin PII disk kurtarma araçlarıyla geri gelir"
    )

    # DAVRANIŞ (metin değil): varsayılanda göç sonrası düz-metin yedek diskte KALMAMALI.
    # (Ayrıntılı senaryolar: tests/test_at_rest_encryption_rollout.py)
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(thdb.TreatmentHistoryDB, "_import_sqlcipher", lambda self: None)
    db = thdb.TreatmentHistoryDB(temp_app_data)
    db.start_session("Manuel", patient_name="ArtikHasta")
    db.close_connections()
    monkeypatch.undo()
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    thdb.TreatmentHistoryDB(temp_app_data)  # göç
    assert not (temp_app_data / "pemf_treatment_history.db.plain.bak").exists(), (
        "goc sonrasi duz-metin yedek diskte kaldi"
    )

    # Silme, o koşulun İÇİNDE olmalı (sırayla değil, yapısal)
    import ast
    import textwrap

    fn = ast.parse(textwrap.dedent(src)).body[0]
    # ⚠️ 2026-08-08 yapı değişti: silme artık BİR KOŞULUN İÇİNDE değil, VARSAYILAN YOL.
    # Escrow yalnız `if _keep:` bloğunda ve ACL başarılıysa `return` ile korunur; diğer TÜM
    # yollar güvenli-silmeye düşer. Kilitlenecek sözleşme: escrow bloğundan ACL BAŞARILIYKEN
    # erken çıkılır, aksi halde silme kaçınılmazdır.
    escrow_erken_cikis = False
    for n in ast.walk(fn):
        if isinstance(n, ast.If) and ast.unparse(n.test).strip() == "_keep":
            govde = ast.unparse(n.body)
            if "_locked" in govde and "return" in govde:
                escrow_erken_cikis = True
    assert escrow_erken_cikis, (
        "escrow bloğu ACL başarılıyken erken çıkmıyor → ya escrow hiç saklanmıyor "
        "ya da korumasız escrow silinmeden bırakılıyor"
    )

    # Silme yolu koşulsuz erişilebilir olmalı: fonksiyonun sonunda (escrow return'ü dışında)
    # `os.remove(backup)` bulunmalı.
    assert "os.remove(backup)" in ast.unparse(fn), "düz-metin yedeği silen yol kayıp"


def test_config_kaydi_ATOMIK(tmp_path, monkeypatch):
    """Kaçan mutasyon: `os.replace` → `shutil.copyfile`. Güç kesintisi veya eş-zamanlı iki
    kaydetme config.json'i YARIM/BOŞ bırakır → tüm kullanıcı ayarları sessizce kaybolur."""
    import inspect

    from utils import production_config_manager as pcm

    src = (
        inspect.getsource(pcm.ProductionConfigManager.save_user_config)
        if hasattr(pcm.ProductionConfigManager, "save_user_config")
        else inspect.getsource(pcm)
    )
    assert "os.replace(" in src, "config yazımı atomik DEĞİL (os.replace yok)"
    assert "os.fsync(" in src, "fsync yok → replace öncesi veri diske inmemiş olabilir"
    # tmp dosyaya yaz → replace sırası
    i_tmp = src.find(".json.tmp")
    i_rep = src.find("os.replace(")
    assert 0 < i_tmp < i_rep, "geçici dosyaya yazıp SONRA replace etme deseni bozulmuş"


# ───────────────────── AĞ / BULUT ─────────────────────


def test_system_info_UZAK_istemciye_tunel_ve_eslestirme_SIZDIRMAZ(monkeypatch):
    """`tunnelUrl`/`pairingCode`/`deviceId` uzak (tünel) istemciye verilirse, tüneli bilen
    herkes cihazı eşleştirebilir. `/api/health` bunu kapatmıştı, `system_info` tutarsızdı."""
    import inspect

    from servers import system_router

    src = inspect.getsource(system_router)
    for alan in ('"tunnelUrl"', '"pairingCode"', '"deviceId"'):
        i = src.find(alan)
        assert i > 0, f"{alan} kaybolmuş"
        satir = src[i : src.find("\n", i)]
        assert "_local" in satir, f"{alan} YEREL kontrolü olmadan dönüyor → uzak istemciye sızar: {satir.strip()}"


def test_pahali_yoklamalar_ONBELLEKLENIR():
    """`_cached_poll` kalkarsa her `/api/health` çağrısı netsh/powershell subprocess'i
    doğurur → saniyede birkaç istekte cihaz 'yoklama fırtınası'na girer (LattePanda'da CPU)."""
    from services import headless_services as hs

    sinif = hs.NetworkStatusService
    assert getattr(sinif, "_EXPENSIVE_POLL_TTL_S", 0) > 0, "poll TTL yok"

    m = sinif.__new__(sinif)
    cagri = {"n": 0}

    def _uretici():
        cagri["n"] += 1
        return {"v": cagri["n"]}

    ilk = m._cached_poll("test", _uretici)
    ikinci = m._cached_poll("test", _uretici)
    assert cagri["n"] == 1, f"önbellek çalışmıyor, üretici {cagri['n']} kez çağrıldı"
    assert ilk == ikinci

    # Üretici PATLARSA son iyi değer korunmalı (health hiç boş dönmesin)
    def _patla():
        raise RuntimeError("netsh timeout")

    m._poll_cache["test"] = (0.0, {"v": 42})  # TTL'i geçmiş yap
    assert m._cached_poll("test", _patla) == {"v": 42}, (
        "üretici hata verince son iyi değer korunmuyor → health boş/yanlış döner"
    )
