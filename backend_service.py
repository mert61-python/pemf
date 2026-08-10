from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ŞİFRELİ KAYNAK YÜKLEYİCİ (2026-08-06) — ai_hub gibi `.pyenc`'e çevrilmiş modüller
# import edilebilsin diye HER ŞEYDEN ÖNCE kurulur (ilk AI importundan önce olmalı).
# Şifresiz build'de sessizce devre dışı kalır → geliştirme/test akışı ETKİLENMEZ.
try:
    from utils.encrypted_import import install as _install_enc_loader

    _install_enc_loader()
except Exception:  # yükleyici yoksa/başarısızsa uygulama normal (şifresiz) açılmaya devam eder
    pass

import uvicorn

from controllers.hardware_controller import HardwareController
from event_bus import get_event_bus
from headless_core import HeadlessCore
from utils.path_utils import get_app_data_directory, initialize_database

# anon publishable anahtar, FE deviceRegistry.ts'dekiyle AYNI; backend registry'ye
# yazabilsin diye. service_role DEĞİL (sadece publishable/anon yetkisi).
_DEFAULT_SUPABASE_URL = "https://wmsxonunkphjeregpvuj.supabase.co"
_DEFAULT_SUPABASE_ANON_KEY = "sb_publishable_D2SaRML_PIhRtr3kqlXxaw_1cS75GKT"


class _JsonLogFormatter(logging.Formatter):
    """Yapısal (JSON) log satırı (audit B-5.2): PEMF_LOG_JSON=1 iken. Log toplama/sorgulama
    (Loki/ELK/CloudWatch) düz-metin regex yerine alan-bazlı çalışsın. Harici bağımlılık yok."""

    def format(self, record: logging.LogRecord) -> str:
        import json as _json

        from utils.request_context import get_request_id

        doc = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "rid": get_request_id(),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            doc["exc"] = self.formatException(record.exc_info)
        return _json.dumps(doc, ensure_ascii=False)


class _PlainLogFormatter(logging.Formatter):
    """Düz-metin (insan-okur, varsayılan) log + request-correlation-id (O-2). `rid` artık yalnız
    JSON-log'da değil, varsayılan formatta da her satıra [rid] olarak eklenir → 7/24 saha-cihazında
    normal-yol izlenebilirliği (istek başına id log+header'da eşleşir). İstek-dışı (arka-plan) → '-'."""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "rid"):
            try:
                from utils.request_context import get_request_id

                record.rid = get_request_id() or "-"
            except Exception:
                record.rid = "-"
        # Audit P2: mesaj + string arg'lardaki CR/LF'yi nötralize et — güvenilmez girdi (ör. anonim-broker
        # MQTT topic'i on_message except'inde loglanınca) kalıcı denetim-loguna SAHTE SATIR ekleyip
        # kayıt-forgery yapabilirdi. Traceback (exc_text) etkilenmez.
        if isinstance(record.msg, str) and ("\r" in record.msg or "\n" in record.msg):
            record.msg = record.msg.replace("\r", "\\r").replace("\n", "\\n")
        if isinstance(record.args, tuple):
            record.args = tuple(
                (a.replace("\r", "\\r").replace("\n", "\\n") if isinstance(a, str) else a) for a in record.args
            )
        return super().format(record)


def _configure_logging(app_data_dir: Path, level: str) -> None:
    # Windows consoles and NSSM-redirected pipes default to the legacy ANSI
    # codepage (e.g. cp1254 on Turkish Windows), which raises UnicodeEncodeError
    # on log lines containing ✓ / → / Türkçe characters and spams the log with
    # "Logging error" tracebacks. Force UTF-8 so the 24/7 service logs cleanly.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    log_dir = Path(os.environ.get("PEMF_LOG_DIR", app_data_dir / "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_level = getattr(logging, level.upper(), logging.INFO)

    # PEMF_LOG_JSON=1 → yapısal JSON log (toplama/sorgulama); aksi düz-metin (varsayılan, insan-okur).
    if os.environ.get("PEMF_LOG_JSON") == "1":
        formatter: logging.Formatter = _JsonLogFormatter()
    else:
        formatter = _PlainLogFormatter(
            "%(asctime)s %(levelname)s [%(name)s] [%(rid)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    file_handler = RotatingFileHandler(
        log_dir / "backend_service.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    # stdout StreamHandler'ı YALNIZ gerçek interaktif konsolda ekle. Frozen/headless serviste
    # (launcher CREATE_NO_WINDOW ya da NSSM stdout'u DRENAJSIZ pipe'a bağlar) stdout'a yazmak,
    # pipe buffer'ı dolunca `sys.stdout.flush()`'ı SÜRESİZ BLOKE eder → thread Python logging kilidini
    # tutarak asılır → o kilidi bekleyen TÜM AI model yüklemeleri + STM + telemetri DEADLOCK olur
    # (py-spy ile doğrulandı). RotatingFileHandler zaten her şeyi yakalar. (Launcher tarafı da backend
    # stdout'unu NUL'e yönlendirir → bu ikinci/derinlemesine savunma.)
    handlers = [file_handler]
    try:
        _interactive = bool(sys.stdout is not None and sys.stdout.isatty())
    except Exception:
        _interactive = False
    if _interactive and not getattr(sys, "frozen", False):
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)

    logging.basicConfig(level=log_level, handlers=handlers, force=True)


def publish_bind_host(host: str) -> str:
    """GERÇEKTEN bağlanılan host'u PEMF_API_HOST'a yaz (tek gerçek kaynak).

    DENETIM P0 (proxy-auth): `servers/auth._loopback_only_bind()` yerel/uzak kararını
    bağlanılan host'a göre verir ama bunu env'den okur. `--host` CLI'da verilebildiğinden
    (ör. `scripts/install_backend_service.ps1` "--host 0.0.0.0" sabitler) env ile GERÇEK
    ayrışabiliyordu → güvenlik kararı yanlış girdiyle alınırdı. Ayrı fonksiyon: `main()`
    tüm servisi ayağa kaldırdığı için testten çağrılamaz; bu sözleşme tek başına sınanabilir.
    """
    os.environ["PEMF_API_HOST"] = str(host)
    return os.environ["PEMF_API_HOST"]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PEMF headless backend service")
    parser.add_argument("--host", default=os.environ.get("PEMF_API_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PEMF_API_PORT", "8000")))
    parser.add_argument("--log-level", default=os.environ.get("PEMF_LOG_LEVEL", "INFO"))
    parser.add_argument(
        "--no-headless-services",
        action="store_true",
        help="Do not start Mosquitto/network/UDP discovery support services.",
    )
    parser.add_argument(
        "--no-mosquitto-ensure",
        action="store_true",
        help="Monitor Mosquitto but do not try to start the broker automatically.",
    )
    return parser


def _safe_stop_outputs(api_server_module) -> None:
    """Best-effort safe output shutdown used during service stop."""
    logger = logging.getLogger("backend_service")
    try:
        if api_server_module.state.hardware:
            api_server_module.state.hardware.stop_all_coils()
            # STM STOP yalnız async _hw_send_queue'ye konuyor; sender thread core.quit() ile
            # join edilmeden ÖNCE seri porta yazdığından emin ol — kuyruk boşalana kadar kısa
            # süre bekle (audit #21). Aksi halde STOP gönderilmeden süreç kapanıp bobinler
            # firmware süre-watchdog'u dolana kadar çalışmaya devam edebilir.
            import time as _t

            _q = getattr(getattr(api_server_module.state, "core", None), "_hw_send_queue", None)
            if _q is not None:
                _deadline = _t.time() + _STM_FLUSH_BUDGET_S
                while not _q.empty() and _t.time() < _deadline:
                    _t.sleep(0.05)
    except Exception:
        logger.exception("STM safe stop failed")

    try:
        import threading
        import time

        # Audit P3: ESP STOP'larını PARALEL gönder + sıkı süre-bütçesi. Eskiden 6 publish SIRAYLA
        # (broker yavaşken ~14s worst-case) SCM/NSSM stop-timeout'unu aşıp süreç kill → ESP STOP almadan
        # bobinler firmware süre-watchdog'una kadar açık kalabiliyordu. emergency_stop zaten paralel.
        def _stop_esp(coil_id):
            command_id = f"service_stop_{coil_id}_{int(time.time() * 1000)}"
            payload = {
                "command": "stop",
                "command_id": command_id,
                "emergency": True,
                "source": "backend_service_shutdown",
                "timestamp": time.time(),
            }
            api_server_module._mqtt_publish(f"pemf/coil/{coil_id}/control", payload)
            api_server_module._mqtt_publish(f"pemf/esp32_{coil_id}/command", payload)

        # DENETIM P3: eskiden `with ThreadPoolExecutor(...) as _ex:` kullaniliyordu. Context
        # manager cikisi shutdown(wait=True) cagirir → `_cf.wait(timeout=3.0)` dolsa BILE blok
        # devam eder; ayrica concurrent.futures bir atexit kancasiyla is thread'lerini join eder.
        # Sonuc: "toplam ~3 sn butce" HIC uygulanmiyordu; broker erisilemezken kapanis
        # 3 bobin x ~2 sn x 2 publish kadar uzayip Windows SCM stop-timeout'unu asabiliyordu
        # (servis "durduruldu" sayilmadan oldurulur → kapanis mutabakati yarim kalir).
        # DAEMON thread + join(timeout): butce GERCEKTEN uygulanir, kalanlar surec bitince duser.
        _threads = [
            threading.Thread(target=_stop_esp, args=(c,), daemon=True, name=f"shutdown-estop-{c}") for c in range(6, 9)
        ]
        for _t in _threads:
            _t.start()
        _deadline = time.monotonic() + _ESP_STOP_BUDGET_S  # ESP durdurma bütçesi
        for _t in _threads:
            _t.join(timeout=max(0.0, _deadline - time.monotonic()))
        if any(_t.is_alive() for _t in _threads):
            logger.warning(
                "Kapanis ESP STOP butcesi (3 sn) doldu — kalan publish'ler birakildi "
                "(bobinler firmware olu-adam devresiyle de durur)."
            )
    except Exception:
        logger.exception("MQTT safe stop failed")


def _install_crash_handler(app_data_dir: Path) -> None:
    """Yakalanmamış istisnaları (ana thread + worker thread'ler) AYRI bir crash.log'a + ana
    log'a CRITICAL yaz → saha cihazında çökme/güvenlik olayı görünür olsun (audit #24: merkezi
    telemetri yok). En azından adanmış, kolay-bulunur bir çökme kaydı + (varsa) cloud outbox'a not."""
    import threading as _th

    logger = logging.getLogger("backend_service")
    crash_log = Path(os.environ.get("PEMF_LOG_DIR", app_data_dir / "logs")) / "crash.log"

    def _record(exc_type, exc_value, exc_tb, where: str) -> None:
        try:
            import datetime as _dt
            import traceback as _tb

            crash_log.parent.mkdir(parents=True, exist_ok=True)
            with open(crash_log, "a", encoding="utf-8") as f:
                f.write(f"\n===== CRASH [{where}] {_dt.datetime.now().isoformat()} =====\n")
                _tb.print_exception(exc_type, exc_value, exc_tb, file=f)
        except Exception:
            pass
        logger.critical("YAKALANMAMIS ISTISNA (%s): %s", where, exc_value, exc_info=(exc_type, exc_value, exc_tb))

    def _sys_hook(exc_type, exc_value, exc_tb):
        if not issubclass(exc_type, KeyboardInterrupt):
            _record(exc_type, exc_value, exc_tb, "main")
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    def _thread_hook(args):
        _record(args.exc_type, args.exc_value, args.exc_traceback, f"thread:{getattr(args.thread, 'name', '?')}")

    sys.excepthook = _sys_hook
    try:
        _th.excepthook = _thread_hook  # Python 3.8+
    except Exception:
        pass


def _harden_secret_file_acls(app_data_dir: Path, logger: logging.Logger) -> None:
    """Var olan sır/anahtar dosyalarının NTFS ACL'sini SYSTEM + Administrators'a kilitle (audit B-1.2).
    Yeni yazımlar zaten kilitli üretiliyor; bu geçiş, ÖNCEDEN kurulmuş cihazlardaki (ACL'siz yazılmış)
    mevcut dosyaları da kapatır. Best-effort — hata servisi durdurmaz."""
    try:
        from utils.file_acl import lock_down_file
    except Exception:
        return
    candidates = []
    try:
        from utils.secrets_manager import secrets_path

        candidates.append(secrets_path())
    except Exception:
        pass
    try:
        from servers.auth import _token_file

        candidates.append(_token_file())
    except Exception:
        pass
    for name in (".sqlcipher_key", ".pemf_key_v2", ".pemf_key", "api_token.txt", "pemf_secrets.json"):
        candidates.append(app_data_dir / name)
    # op-doğrulama #8: mevcut *.plain.bak (migration düz-metin PII yedeği) dosyalarını da kilitle —
    # halihazırda dağıtılmış cihazlarda oluşturmada ACL yoktu → startup'ta geriye-dönük SYSTEM+Admin kilit.
    try:
        candidates.extend(app_data_dir.glob("*.plain.bak"))
    except Exception:
        pass
    seen: set[str] = set()
    locked = 0
    for c in candidates:
        try:
            key = str(c).lower()
            if key in seen:
                continue
            seen.add(key)
            if lock_down_file(c):
                locked += 1
        except Exception:
            pass
    if locked:
        logger.info("Sır dosyası ACL kilidi uygulandı: %d dosya (yalnız SYSTEM + Administrators).", locked)


def _log_pairing_info(logger: logging.Logger) -> None:
    """Eşleştirme kodu + cihaz kimliğini GÖRÜNÜR logla → operatör LattePanda konsolunda
    okuyup mobil uygulamaya girebilsin (TEMASSIZ/QR'sız eşleştirme)."""
    try:
        from utils.path_utils import get_pairing_code, get_unique_device_id

        # Audit P3: eşleştirme kodu auth-bearer SIR (kod→/api/auth/exchange→token) → kalıcı log dosyasına
        # DÜZ yazma. Maskele; tam kodu operatör /api/system/info (local-gate) veya cihaz ekranından alır.
        _pc = get_pairing_code() or ""
        _pc_masked = (_pc[:1] + "*****") if len(_pc) >= 6 else "******"
        logger.info("=" * 60)
        logger.info(
            "EŞLEŞTİRME KODU: %s (tam kod: /api/system/info veya cihaz ekranı — güvenlik) | Cihaz Kimliği: %s",
            _pc_masked,
            get_unique_device_id(),
        )
        logger.info("=" * 60)
    except Exception:
        logger.exception("Eşleştirme kodu loglanamadı (non-fatal).")


def _initialize_database_safe(logger: logging.Logger) -> None:
    """Şemayı hazırla; başarısız olsa bile servis runtime DB açılışıyla devam etsin."""
    try:
        initialize_database()
    except Exception:
        logger.exception("Database initialization failed; continuing with runtime DB open.")


def _wire_api_server(core: HeadlessCore):
    """api_server modülünü HeadlessCore + HardwareController ile bağla ve modülü döndür."""
    from servers import api_server

    api_server.state.core = core
    api_server.state.hardware = HardwareController(core)
    api_server._register_event_bus_handlers()
    return api_server


def _start_startup_reconcile(api_server, logger: logging.Logger) -> None:
    """Çökme-kurtarma mutabakatı (audit #15): önceki süreç seans ortasında çöktüyse ESP bobinleri
    firmware kendi süresince çalışmaya devam edebilir (STM keep-alive durduğundan STM kendi
    duration'ı bitince durur). Yeni süreç TEMİZ başlasın diye broker/STM hazır olunca bir kez
    TÜM bobinlere STOP gönder. Eşzamanlı kilit yalnız in-memory olduğundan bu, crash sonrası
    orphan/ghost donanım durumunu temizler."""

    def _reconcile() -> None:
        try:
            import time as _t

            _t.sleep(3.0)  # broker + STM bağlantısının oturması için
            with api_server._session_lock:
                if api_server._active_session.get("is_active"):
                    logger.info("Başlangıç mutabakatı atlandı: bu arada aktif seans başlatılmış.")
                    return
            if api_server.state.hardware:
                api_server.state.hardware.stop_all_coils()
            for _cid in range(1, 9):
                api_server._mqtt_publish(
                    f"pemf/coil/{_cid}/control", {"command": "stop", "command_id": f"startup_reconcile_{_cid}"}
                )
            logger.info("Başlangıç donanım mutabakatı: tüm bobinlere STOP (orphan/ghost temizliği).")
        except Exception:
            logger.warning("Başlangıç mutabakatı başarısız (non-fatal).", exc_info=True)

    import threading

    threading.Thread(target=_reconcile, daemon=True, name="startup-reconcile").start()


def _resolve_supabase_credentials() -> tuple[str, str]:
    """Supabase URL + anon anahtarını çözümle: SecretsManager → env → pemf_gui.config → gömülü
    varsayılan (TEK-DOSYA: pemf_secrets.json embedded; varsayılan anon key dahil)."""
    try:
        from utils.secrets_manager import get_secret

        sb_url = get_secret("supabase_url")
        sb_key = get_secret("supabase_anon_key")
    except Exception:
        sb_url = os.environ.get("SUPABASE_URL", "")
        sb_key = os.environ.get("SUPABASE_KEY", "")
    if not (sb_url and sb_key):
        try:
            from pemf_gui.config import get_config

            cfg = get_config()
            sb_url = sb_url or cfg.get("supabase_url", _DEFAULT_SUPABASE_URL)
            sb_key = sb_key or cfg.get("supabase_key", "") or _DEFAULT_SUPABASE_ANON_KEY
        except Exception:
            sb_url = sb_url or _DEFAULT_SUPABASE_URL
            sb_key = sb_key or _DEFAULT_SUPABASE_ANON_KEY
    return sb_url, sb_key


def _start_cloud_sync(logger: logging.Logger) -> None:
    """Cloud sync + device registry (offline-first + TEMASSIZ uzaktan erişim). Headless servis,
    güncel tunnel URL'sini/IP'sini Supabase 'devices' tablosuna yazar; mobil uygulama farklı
    ağdayken device_id ile QR'sız bağlanabilir."""
    try:
        from servers.sync_worker import init_cloud_sync

        sb_url, sb_key = _resolve_supabase_credentials()
        init_cloud_sync(supabase_url=sb_url, supabase_key=sb_key)
        logger.info("Cloud sync + device registry started.")
    except Exception:
        logger.exception("Cloud sync init failed (non-fatal).")


def _start_db_maintenance(core: HeadlessCore, logger: logging.Logger) -> None:
    """DB bakım/retention/PII-redaction/backup/disk-check (Qt'siz). Eskiden yalnız legacy GUI'de
    çalışıyordu → headless üretimde KVKK/GDPR retention + yedek HİÇ çalışmıyordu."""
    try:
        from services.headless_db_maintenance import start_headless_db_maintenance

        start_headless_db_maintenance(getattr(core, "app_data_dir", None))
        logger.info("Headless DB maintenance started.")
    except Exception:
        logger.exception("DB maintenance init failed (non-fatal).")


def _force_auth_for_tunnel(logger: logging.Logger) -> None:
    """GÜVENLİK (fail-closed): Tünel cihazı İNTERNETE açar → auth ZORUNLU olmalı. Operatör
    PEMF_REQUIRE_AUTH'u kapalı bıraktıysa burada ZORLA aç → internete KİMLİKSİZ donanım/hasta
    erişimi engellenir. (Eskiden coupling yalnız .env'e güveniyordu = fail-open risk.)"""
    if os.environ.get("PEMF_REQUIRE_AUTH") == "1":
        return
    os.environ["PEMF_REQUIRE_AUTH"] = "1"
    try:
        from servers import auth as _auth

        _auth._require = True  # lazy-cache'i de güncelle (ilk isteği beklemeden)
    except Exception:
        pass
    logger.warning(
        "GÜVENLİK: Tünel AÇIK → PEMF_REQUIRE_AUTH=1 ZORLA etkinleştirildi "
        "(internete kimliksiz erişim engellendi). API token'ı istemcilere dağıtın."
    )


def _maybe_start_tunnel(port: int, logger: logging.Logger) -> None:
    """Cloudflare tünel (OPT-IN) — DEPLOYMENT.md'de vaat edilen farklı-ağdan TEMASSIZ uzaktan
    erişim. Cihazı internete açtığından VARSAYILAN KAPALI; PEMF_ENABLE_TUNNEL=1 ile aç. Eskiden
    tunnel_manager headless serviste HİÇ çağrılmıyordu → yalnız LAN çalışıyordu (audit P1)."""
    if os.environ.get("PEMF_ENABLE_TUNNEL") != "1":
        return
    _force_auth_for_tunnel(logger)
    try:
        from servers.tunnel_manager import start_tunnel_watchdog

        # Tek-seferlik start yerine WATCHDOG (SIFIR-MÜDAHALE): internet gelince/giderse veya
        # cloudflared ölürse tüneli OTOMATİK (yeniden) başlatır → "WiFi sonradan bağlanınca
        # uzaktan erişim otomatik açılır", boot'ta internetsizse yerel çalışmaya devam eder.
        start_tunnel_watchdog(port=port)
        logger.info("Cloudflare tunnel watchdog aktif (uzaktan erişim internet geldikçe otomatik).")
    except Exception:
        logger.exception("Tunnel watchdog init failed (non-fatal).")


def _start_update_checker_safe(logger: logging.Logger) -> None:
    """Oto-güncelleme denetleyici (BİLDİRİM + tek-tık onay): GitHub 'exe' branch latest.json'ı
    periyodik kontrol eder → yeni sürüm varsa UI'da bildirilir (UYGULAMAZ; operatör
    /api/update/apply ile onaylar → indir+SHA256+aktif-tedavi-yoksa sessiz kur). Tünelden bağımsız."""
    try:
        from servers.update_manager import start_update_checker

        start_update_checker()
    except Exception:
        logger.exception("Update checker init failed (non-fatal).")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# PEMF-Gateway HOTSPOT — BACKEND BAŞLARKEN OTOMATİK (2026-08-10, sahip kararı)
# ─────────────────────────────────────────────────────────────────────────────────────────────
# ⚠️ NEDEN BURADA: ESP bobinleri (6-8) `PEMF-Gateway` WiFi'sine bağlanıp yerel mosquitto'ya MQTT
# yapar. Hotspot'u kuran tek yol `setup_services.ps1 -Mode device`in kaydettiği logon-task'tı —
# ama SİTEDEN İNDİRİP KURAN yol (PEMF Vet Client) `setup_services.ps1`i HİÇ ÇALIŞTIRMIYOR
# (2026-08-10'da ölçüldü: launcher kaynağında ne `setup_services` ne `schtasks` geçiyor).
# Sonuç: launcher ile kuran HER kullanıcıda hotspot hiç açılmıyor ve 8 bobinin 3'ü bağlanamıyordu.
#
# ⚠️ NEDEN ÇALIŞIR: Windows Mobile Hotspot API'si KULLANICI OTURUMU ister; LocalSystem servisi
# (session 0) başlatamaz. Launcher backend'i KENDİ oturumunda çocuk süreç olarak başlatır
# (`launcher/core/src/backend.rs` → `Command::spawn`), yani bu kısıt burada GEÇERLİ DEĞİLDİR.
# Eski servis kurulumunda ise `_oturum_var_mi()` False döner ve bu yol kendini devre dışı bırakır
# — logon-task orada zaten işi yapıyor, iki başlatıcı çakışmasın.
#
# SSID/parola: `scripts/start_hotspot.ps1` içindeki TEK KAYNAKtan gelir (PEMF-Gateway/pemf1234).
# ESP firmware'i bunları kendi içinde taşıdığı için DEĞİŞTİRİLEMEZ — burada parametre GEÇİLMEZ.
#
# Kapatmak için: PEMF_HOTSPOT=0
# ═════════════════════════════════════════════════════════════════════════════════════════════


def _oturum_var_mi() -> bool:
    """Etkileşimli bir kullanıcı oturumunda mıyız? (session 0 = servis → Mobile Hotspot açamaz)"""
    if os.name != "nt":
        return False
    try:
        import ctypes

        pid = ctypes.windll.kernel32.GetCurrentProcessId()
        oturum = ctypes.c_ulong()
        if not ctypes.windll.kernel32.ProcessIdToSessionId(pid, ctypes.byref(oturum)):
            return False
        return oturum.value != 0
    except Exception:
        return False


def _hotspot_betigi():
    """Paketlenmiş `start_hotspot.ps1`in yolu (frozen: exe yanı; kaynak: scripts/)."""
    from pathlib import Path

    adaylar = []
    try:
        from utils.path_utils import packaged_resource_path

        adaylar.append(Path(packaged_resource_path("start_hotspot.ps1")))
    except Exception:
        pass
    try:
        adaylar.append(Path(sys.executable).resolve().parent / "start_hotspot.ps1")
    except Exception:
        pass
    adaylar.append(Path(__file__).resolve().parent / "scripts" / "start_hotspot.ps1")
    for p in adaylar:
        try:
            if p.is_file():
                return p
        except Exception:
            continue
    return None


def _start_hotspot_safe(logger: logging.Logger) -> None:
    """PEMF-Gateway hotspot'unu ARKA PLANDA başlat. Açılışı ASLA bloklamaz, ASLA düşürmez."""
    if os.environ.get("PEMF_HOTSPOT", "1").strip() in ("0", "false", "False"):
        logger.info("Hotspot otomatik başlatma KAPALI (PEMF_HOTSPOT=0).")
        return
    if os.name != "nt":
        return
    if not _oturum_var_mi():
        # Servis (session 0) → Mobile Hotspot API çalışmaz; logon-task'ın işi.
        logger.info("Hotspot: servis oturumunda (session 0) — başlatma ATLANDI (logon-task'ın işi).")
        return
    betik = _hotspot_betigi()
    if betik is None:
        logger.warning("Hotspot: start_hotspot.ps1 bulunamadı → PEMF-Gateway açılmayacak (ESP'ler bağlanamaz).")
        return

    # ⚠️ `threading` bu modülde FONKSİYON İÇİNDE import ediliyor (mevcut desen) — modül düzeyinde
    # yok; buraya da öyle alınır, yoksa NameError.
    import threading

    def _calistir() -> None:
        try:
            import subprocess

            # PowerShell 5.1 yeter; `-WindowStyle Hidden` + CREATE_NO_WINDOW → pencere YOK.
            bayrak = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            r = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-WindowStyle",
                    "Hidden",
                    "-File",
                    str(betik),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=bayrak,
            )
            if r.returncode == 0:
                logger.info("Hotspot: PEMF-Gateway hazır (ESP bobinleri bağlanabilir).")
            else:
                # ÇÖKERTME YOK: hotspot yoksa STM bobinleri (1-5) ve tüm arayüz çalışmaya devam eder.
                logger.warning(
                    "Hotspot başlatılamadı (rc=%s): %s", r.returncode, (r.stdout or r.stderr or "").strip()[-300:]
                )
        except Exception:
            logger.exception("Hotspot başlatma hatası (non-fatal).")

    threading.Thread(target=_calistir, name="PemfHotspot", daemon=True).start()


# ⚠️ TIBBİ GÜVENLİK — uvicorn graceful-shutdown TAVANI (denetim 2026-08-04, P2).
#
# Bu değer VERİLMEZSE uvicorn.Config varsayılanı `None`'dır ve kapanış
# `asyncio.wait_for(self._wait_tasks_to_complete(), timeout=None)` ile SINIRSIZ bekler.
# `_wait_tasks_to_complete` şu döngüdedir: `while self.server_state.connections and not
# self.force_exit`. `force_exit` YALNIZCA İKİNCİ bir SIGINT'te set edilir; SIGTERM/SIGBREAK
# kaç kez gelirse gelsin ASLA set etmez — NSSM servisi tam da böyle durdurur.
#
# Bu üründe AÇIK WEBSOCKET bağlantıları vardır (klinik UI tarayıcıda açık durur). Yani
# `server_state.connections` boşalmaz → `server.run()` DÖNMEZ → `main()`'deki
# `finally: _shutdown(...)` HİÇ ÇALIŞMAZ → `_safe_stop_outputs()` çağrılmaz → ne STM
# `stop_all_coils()` ne de ESP 6-8 MQTT STOP'ları gönderilir. Operatör servisi durdurur,
# bobinler HASTANIN ÜZERİNDE enerjili kalır (ESP'nin link-watchdog'u yoktur).
#
# 8 sn: uçuşan HTTP istekleri bitsin ama kapanış DAİMA ilerlesin. Bütçe:
#   8 sn (graceful) + ~3 sn (_shutdown güvenli-durdurma) = ~11 sn < NSSM AppStopMethodConsole 15 sn.
# ⚠️ DENETİM 2026-08-04 (P3): güvenli-durdurma bütçeleri koda GÖMÜLÜ sayılardı ve
# `test_graceful_shutdown_nssm_butcesine_sigiyor` bunları ELLE 3.0 diye kopyalamıştı — YANLIŞ:
# gerçek toplam 1.5 (STM kuyruk flush) + 3.0 (ESP stop) = 4.5 sn. Test yanlış bir marj
# doğruluyordu. Sabitler adlandırıldı; test artık BURADAN türetiyor (kopya sürüklenmesi biter).
_STM_FLUSH_BUDGET_S = 1.5
_ESP_STOP_BUDGET_S = 3.0
_SAFE_STOP_BUDGET_S = _STM_FLUSH_BUDGET_S + _ESP_STOP_BUDGET_S
_GRACEFUL_SHUTDOWN_TIMEOUT_S = 8


def _build_server(app, args: argparse.Namespace) -> uvicorn.Server:
    """Uvicorn sunucusunu servis argümanlarıyla kur (access-log kapalı — NSSM zaten yakalıyor)."""
    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
        access_log=False,
        # Bkz. yukarıdaki not: bu OLMADAN açık bir WebSocket kapanışı SÜRESİZ bloklar ve
        # bobin-STOP yolu hiç çalışmaz.
        timeout_graceful_shutdown=_GRACEFUL_SHUTDOWN_TIMEOUT_S,
    )
    return uvicorn.Server(config)


def _install_signal_handlers(server: uvicorn.Server, logger: logging.Logger) -> None:
    """SIGINT/SIGTERM/SIGBREAK'i yakala → uvicorn'a temiz kapanış (should_exit) sinyali ver."""

    def request_shutdown(signum=None, frame=None) -> None:
        logger.info("Shutdown requested%s", f" by signal {signum}" if signum else "")
        server.should_exit = True

    for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                signal.signal(sig, request_shutdown)
            except Exception:
                pass


def _shutdown(logger: logging.Logger, api_server, core: HeadlessCore, event_bus) -> None:
    """Servis dururken donanımı güvene al + tüm alt sistemleri sırayla kapat (her adım best-effort;
    biri hata verse de diğerleri denenir). Zeroconf EN SON kapanır (servisler kendi kayıtlarını
    önce unregister etti)."""
    logger.info("PEMF backend service stopping")
    try:
        _safe_stop_outputs(api_server)
    except Exception:
        logger.exception("Safe output shutdown failed")
    try:
        if api_server.state.hardware:
            api_server.state.hardware.stop()
    except Exception:
        logger.exception("HardwareController shutdown failed")
    try:
        from servers.sync_worker import get_cloud_sync

        cloud = get_cloud_sync()
        if cloud:
            cloud.stop()
    except Exception:
        logger.exception("Cloud sync shutdown failed")
    try:
        from servers.tunnel_manager import stop_tunnel

        stop_tunnel()
    except Exception:
        logger.exception("Tunnel shutdown failed")
    try:
        from services.headless_db_maintenance import stop_headless_db_maintenance

        stop_headless_db_maintenance()
    except Exception:
        logger.exception("DB maintenance shutdown failed")
    try:
        core.quit()
    except Exception:
        logger.exception("HeadlessCore shutdown failed")
    try:
        from utils.zeroconf_singleton import close_shared_zeroconf

        close_shared_zeroconf()
    except Exception:
        logger.exception("Zeroconf shutdown failed")
    try:
        event_bus.shutdown()
    except Exception:
        logger.exception("EventBus shutdown failed")
    logger.info("PEMF backend service stopped")


def _kurtarma_mi(argv: list[str] | None) -> list[str] | None:
    """`--kurtarma` verilmişse KALAN argümanları döndür, yoksa None.

    ⚠️ DENETİM 2026-08-09 (ENGEL) — KURTARMA YOLU SAHADA ULAŞILAMAZDI.
    Felaket kurtarma mekanizmasının tamamı vardı (`utils/backup_recovery.py` zarfı +
    `tools/kurtarma.py` aracı) ama aracın çalıştırılma yolu `python tools/kurtarma.py` idi.
    Sahadaki üründe PYTHON YOK (frozen EXE) ve `tools/` pakete girmiyordu. Yani senaryonun
    tam olarak hedeflediği kişi — anakartı ölmüş, elinde yalnız yedek dizini, kurtarma kodu ve
    yeni bir kurulum olan veteriner — kurtarma aracını ÇALIŞTIRAMIYORDU. Yedekler şifreli,
    zarf açılamıyor: koruma kâğıt üzerinde vardı, pratikte yoktu.
    ÇÖZÜM: araç, sahaya ZATEN giden tek çalıştırılabilirin (PEMF_Backend.exe) alt komutu oldu:
        PEMF_Backend.exe --kurtarma --zarf E:\\PEMF_Yedek\\kurtarma-zarfi.enc --kod ABCDE-...
    `argparse` KULLANILMAZ: ana ayrıştırıcı bilinmeyen argümanlarda çıkar; alt komutun kendi
    bayrakları (`--zarf`, `--kod`, `--yaz`) ona sızmamalı.
    """
    av = list(sys.argv[1:] if argv is None else argv)
    if "--kurtarma" not in av:
        return None
    av.remove("--kurtarma")
    return av


def main(argv: list[str] | None = None) -> int:
    kurtarma_argv = _kurtarma_mi(argv)
    if kurtarma_argv is not None:
        # Sunucuyu BAŞLATMADAN kurtarma aracını çalıştır: kurtarma anında backend'in çalışması
        # ne gerekli ne de istenir (donanım/port/DB'ye dokunmaz).
        from tools.kurtarma import main as _kurtarma_main

        return _kurtarma_main(kurtarma_argv)

    args = build_arg_parser().parse_args(argv)
    os.environ.setdefault("PEMF_HEADLESS", "1")
    publish_bind_host(args.host)

    app_data_dir = get_app_data_directory()
    _configure_logging(app_data_dir, args.log_level)
    _install_crash_handler(app_data_dir)
    logger = logging.getLogger("backend_service")
    logger.info("PEMF backend service starting: host=%s port=%s", args.host, args.port)

    # Opsiyonel uzaktan hata-izleme (audit B-5.1) — yalnız PEMF_SENTRY_DSN set + sentry-sdk varsa.
    try:
        from utils.telemetry import init_telemetry

        init_telemetry()
    except Exception:
        logger.debug("Telemetri init atlandı", exc_info=True)
    _harden_secret_file_acls(app_data_dir, logger)
    _log_pairing_info(logger)
    _initialize_database_safe(logger)

    event_bus = get_event_bus()
    core = HeadlessCore(
        app_data_dir,
        api_port=args.port,
        start_headless_services=not args.no_headless_services,
        ensure_mosquitto=not args.no_mosquitto_ensure,
        event_bus=event_bus,
    )
    api_server = _wire_api_server(core)

    # Başlangıç mutabakatı + opsiyonel alt sistemler — hepsi best-effort (biri patlarsa servis yine kalkar).
    _start_startup_reconcile(api_server, logger)
    _start_cloud_sync(logger)
    _start_db_maintenance(core, logger)
    _maybe_start_tunnel(args.port, logger)
    _start_update_checker_safe(logger)
    # ESP bobinleri (6-8) PEMF-Gateway WiFi'sine bağlanır → backend ile BİRLİKTE açılmalı.
    _start_hotspot_safe(logger)

    server = _build_server(api_server.app, args)
    _install_signal_handlers(server, logger)

    try:
        server.run()
        return 0
    except Exception:
        logger.exception("Backend service crashed")
        return 1
    finally:
        _shutdown(logger, api_server, core, event_bus)


if __name__ == "__main__":
    raise SystemExit(main())
