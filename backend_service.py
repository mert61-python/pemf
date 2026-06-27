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
        "--legacy-qt-services",
        action="store_true",
        help="Start old Qt-backed helper services. Do not use for production service mode.",
    )
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


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    os.environ.setdefault("PEMF_HEADLESS", "1")

    app_data_dir = get_app_data_directory()
    _configure_logging(app_data_dir, args.log_level)
    logger = logging.getLogger("backend_service")

    logger.info("PEMF backend service starting: host=%s port=%s", args.host, args.port)
    try:
        initialize_database()
    except Exception:
        logger.exception("Database initialization failed; continuing with runtime DB open.")

    event_bus = get_event_bus()
    core = HeadlessCore(
        app_data_dir,
        api_port=args.port,
        start_headless_services=not args.no_headless_services,
        ensure_mosquitto=not args.no_mosquitto_ensure,
        start_legacy_qt_services=args.legacy_qt_services,
        event_bus=event_bus,
    )

    from servers import api_server

    api_server.state.core = core
    api_server.state.hardware = HardwareController(core)
    api_server._register_event_bus_handlers()

    # Cloud sync + device registry (offline-first + TEMASSIZ uzaktan erişim).
    # Headless servis, güncel tunnel URL'sini/IP'sini Supabase 'devices' tablosuna
    # yazar; mobil uygulama farklı ağdayken device_id ile QR'sız bağlanabilir.
    try:
        from servers.sync_worker import init_cloud_sync

        sb_url = os.environ.get("SUPABASE_URL", "")
        sb_key = os.environ.get("SUPABASE_KEY", "")
        if not (sb_url and sb_key):
            try:
                from pemf_gui.config import get_config

                cfg = get_config()
                sb_url = sb_url or cfg.get("supabase_url", "https://wmsxonunkphjeregpvuj.supabase.co")
                sb_key = sb_key or cfg.get("supabase_key", "")
            except Exception:
                sb_url = sb_url or "https://wmsxonunkphjeregpvuj.supabase.co"
                sb_key = sb_key or ""
        init_cloud_sync(supabase_url=sb_url, supabase_key=sb_key)
        logger.info("Cloud sync + device registry started.")
    except Exception:
        logger.exception("Cloud sync init failed (non-fatal).")

    # DB bakım/retention/PII-redaction/backup/disk-check (Qt'siz). Eskiden yalnız legacy GUI'de
    # çalışıyordu → headless üretimde KVKK/GDPR retention + yedek HİÇ çalışmıyordu.
    try:
        from services.headless_db_maintenance import start_headless_db_maintenance
        start_headless_db_maintenance(getattr(core, "app_data_dir", None))
        logger.info("Headless DB maintenance started.")
    except Exception:
        logger.exception("DB maintenance init failed (non-fatal).")

    config = uvicorn.Config(
        api_server.app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
        access_log=False,
    )
    server = uvicorn.Server(config)

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

    try:
        server.run()
        return 0
    except Exception:
        logger.exception("Backend service crashed")
        return 1
    finally:
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
            core.quit()
        except Exception:
            logger.exception("HeadlessCore shutdown failed")
        try:
            event_bus.shutdown()
        except Exception:
            logger.exception("EventBus shutdown failed")
        logger.info("PEMF backend service stopped")


if __name__ == "__main__":
    raise SystemExit(main())
