from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

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
        doc = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            doc["exc"] = self.formatException(record.exc_info)
        return _json.dumps(doc, ensure_ascii=False)


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
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    file_handler = RotatingFileHandler(
        log_dir / "backend_service.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    logging.basicConfig(level=log_level, handlers=[file_handler, stream_handler], force=True)


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
                _deadline = _t.time() + 1.5
                while not _q.empty() and _t.time() < _deadline:
                    _t.sleep(0.05)
    except Exception:
        logger.exception("STM safe stop failed")

    try:
        import time

        for coil_id in range(6, 9):
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
            import traceback as _tb
            import datetime as _dt
            crash_log.parent.mkdir(parents=True, exist_ok=True)
            with open(crash_log, "a", encoding="utf-8") as f:
                f.write(f"\n===== CRASH [{where}] {_dt.datetime.now().isoformat()} =====\n")
                _tb.print_exception(exc_type, exc_value, exc_tb, file=f)
        except Exception:
            pass
        logger.critical("YAKALANMAMIS ISTISNA (%s): %s", where, exc_value,
                        exc_info=(exc_type, exc_value, exc_tb))

    def _sys_hook(exc_type, exc_value, exc_tb):
        if not issubclass(exc_type, KeyboardInterrupt):
            _record(exc_type, exc_value, exc_tb, "main")
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    def _thread_hook(args):
        _record(args.exc_type, args.exc_value, args.exc_traceback,
                f"thread:{getattr(args.thread, 'name', '?')}")

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
        logger.info("=" * 60)
        logger.info("EŞLEŞTİRME KODU: %s | Cihaz Kimliği: %s",
                    get_pairing_code(), get_unique_device_id())
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
                api_server._mqtt_publish(f"pemf/coil/{_cid}/control",
                                         {"command": "stop", "command_id": f"startup_reconcile_{_cid}"})
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
    logger.warning("GÜVENLİK: Tünel AÇIK → PEMF_REQUIRE_AUTH=1 ZORLA etkinleştirildi "
                   "(internete kimliksiz erişim engellendi). API token'ı istemcilere dağıtın.")


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


def _build_server(app, args: argparse.Namespace) -> uvicorn.Server:
    """Uvicorn sunucusunu servis argümanlarıyla kur (access-log kapalı — NSSM zaten yakalıyor)."""
    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
        access_log=False,
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


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    os.environ.setdefault("PEMF_HEADLESS", "1")

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
