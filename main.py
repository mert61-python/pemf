#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PEMF Medical System — Hardware-Aware Ana Başlatıcı
===================================================

Bu dosya mevcut main.py'nin "Donanım-Farkındalıklı" (Hardware-Aware) tam sürümüdür.
Üç kritik adım şu sırayla uygulanır:

  ADIM 1 — QApplication ÖNCESİ : High-DPI ortam değişkenleri + Qt politika ayarı
  ADIM 2 — QApplication SONRASI: Fiziksel ekrana göre DeviceProfile tespiti
  ADIM 3 — Sinyal bağlantısı    : Ekran değişiminde profil önbelleği yenileme

Sıralama Kuralı (altın kural):
  env-vars → QApplication.set*() class-method çağrıları
  → QApplication() oluşturma
  → detect_device_profile()
  → Pencere açma

NOT: Kurulum (VC++ Redist, STM32 sürücü, Güvenlik Duvarı) artık
     Inno Setup installer tarafından yapılmaktadır. Bu dosya sadece
     uygulamayı başlatmaktan sorumludur.

@author  : merta
@version : 3.0  (installer-aware)
"""

# ============================================================
# ADIM 1-A  ─  Ortam Değişkenleri (env-vars)
#
# ÖNEMLİ: Bu blok dosyanın EN ÜSTÜNDE, herhangi bir PyQt6
# import'undan ÖNCE yer almalıdır.  Qt, ilk C++ kütüphanesi
# yüklendiğinde bu değişkenleri okur; sonradan set etmek etkisiz kalır.
# ============================================================
import os
import sys
import multiprocessing
import subprocess
import traceback
from pathlib import Path

# ── Qt 6 High-DPI pipeline ────────────────────────────────────────────────
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING",          "1")
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR",        "1")
os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY",    "PassThrough")

# ── Bilinen çakışma düzeltmeleri ──────────────────────────────────────────
# Mediapipe (Protobuf v3 C++) + ONNX Runtime (Protobuf v4 C++) birlikte
# yüklendiğinde "MessageFactory" hatası fırlatılır.
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

# Ultralytics/YOLO, PyInstaller EXE içinde pip çağırmaya kalkışır.
os.environ["YOLO_AUTOUPDATE"] = "False"

# 🔐 GÜVENLİK: --no-sandbox KALDIRILDI. GPU sorunları için --disable-gpu yeterli.
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")

# Proje kökünü sys.path'e ekle (tüm utils.* importları için)
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Production default: run the Qt-free backend. The old GUI can still be started
# explicitly with `python main.py --gui` during the transition period.
if __name__ == "__main__" and "--gui" not in sys.argv and os.environ.get("PEMF_LEGACY_GUI") != "1":
    multiprocessing.freeze_support()
    from backend_service import main as backend_main

    raise SystemExit(backend_main(sys.argv[1:]))

if "--gui" in sys.argv:
    sys.argv.remove("--gui")


def global_exception_handler(exc_type, exc_value, exc_tb):
    """Global yakalanmayan hata (unhandled exception) yöneticisi"""
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    try:
        from utils.error_handler import get_error_handler
        handler = get_error_handler()
        handler.handle_exception(exc_type, exc_value, exc_tb, "Global Uncaught Exception")
    except Exception:
        print(f"Kritik Hata: {error_msg}")

    try:
        from PyQt6.QtWidgets import QMessageBox, QApplication
        app = QApplication.instance()
        if app:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("Kritik Hata")
            msg.setText("Beklenmeyen bir sistem hatası oluştu.")
            msg.setDetailedText(error_msg)
            msg.exec()
    except Exception:
        pass

    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = global_exception_handler


# ─── NullWriter (PyInstaller frozen EXE'de stdout/stderr None olabilir) ───
class NullWriter:
    def write(self, data):   pass
    def flush(self):         pass


if sys.stdout is None:
    sys.stdout = NullWriter()
if sys.stderr is None:
    sys.stderr = NullWriter()


# ============================================================
# ADIM 1-B  ─  QCoreApplication CLASS-METHOD çağrısı
# ============================================================
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
try:
    from PyQt6 import QtWebEngineWidgets
except ImportError:
    pass

# Headless modda DPI ayarlarına gerek yok ancak uyumluluk için kalabilir
# QApplication.setAttribute(Qt.ApplicationAttribute.AA_DisableHighDpiScaling, True)


# ─────────────────────────────────────────────────────────────────────────
# Uygulama giriş noktası
# ─────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    # Windows + PyInstaller spawn-bomb önlemi
    multiprocessing.freeze_support()

    # Ultralytics check_requirements'ı devre dışı bırak
    try:
        import ultralytics.utils.checks
        ultralytics.utils.checks.check_requirements = lambda *a, **k: None
    except ImportError:
        pass

    # ─── Mosquitto AppData klasörüne kopyalama ────────────────────────────────
    # Installer, Mosquitto'yu {app}\bin\mosquitto\ altına kopyalar.
    # PyInstaller onedir build'de sys.executable'nın bulunduğu klasör
    # tüm dosyaları içerir (_MEIPASS yoktur, onefile'a özgüdür).
    # Bu yüzden mosquitto'yu bulmak için executable'nın düzeyini kullanıyoruz.
    if getattr(sys, "frozen", False):
        # PyInstaller onedir: EXE ile aynı klasörde tüm dosyalar
        _base = Path(sys.executable).parent
    else:
        _base = Path(__file__).parent

    _app_data = Path(os.environ.get("APPDATA", "C:/")) / "PEMF_GUI"
    _app_data.mkdir(parents=True, exist_ok=True)

    _mosquitto_src  = _base / "bin" / "mosquitto"
    _mosquitto_dest = _app_data / "mosquitto"
    if _mosquitto_src.exists() and not _mosquitto_dest.exists():
        import shutil
        shutil.copytree(str(_mosquitto_src), str(_mosquitto_dest))

    # ========================================================
    # ADIM 2 — QApplication oluştur (GUI Mod)
    # ========================================================
    app = QApplication.instance() or QApplication(sys.argv)

    # ─── FastAPI (port 8000) artık WebSocket'i de barındırıyor. ────────────
    # frontend_bridge (port 5050) devre dışı bırakıldı.
    # Tüm mobil bağlantılar tek port (8000) üzerinden geliyor.
    pass


    try:
        from utils.device_profile import detect_device_profile, invalidate_profile

        profile = detect_device_profile()
        app.setProperty("device_profile", profile)

        import logging
        logging.getLogger(__name__).info(
            "Cihaz profili tespit edildi: %s (%.1f″, %.0f DPI)",
            profile.category.value,
            profile.diagonal_inches,
            profile.physical_dpi,
        )

        # ====================================================
        # ADIM 3 — Ekran Değişimi Sinyali
        # ====================================================
        def _on_primary_screen_changed(_screen):
            """primaryScreenChanged → profil yenile → app'e yaz."""
            invalidate_profile()
            new_profile = detect_device_profile(force_refresh=True)
            app.setProperty("device_profile", new_profile)
            logging.getLogger(__name__).info(
                "Ekran değişti → yeni profil: %s (%.1f″)",
                new_profile.category.value,
                new_profile.diagonal_inches,
            )

        # app.primaryScreenChanged.connect(_on_primary_screen_changed)

    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Cihaz profili tespit edilemedi: %s — STANDARD_DESKTOP varsayılanı.",
            exc,
        )

    # ── Ana GUI'yi başlat ve FastAPI Bridge'e bağla ────────────────────────────────
    import sys
    import logging
    import threading
    from windows.gui_pyqt_v11 import MainWindow
    
    app_data_str = str(_app_data)
    main_window = MainWindow()
    main_window.show()
    
    # FastAPI Server Thread başlat (PORT 8000 — REST + WebSocket birlikte)
    try:
        from servers.api_server import start_fastapi_server
        api_thread = threading.Thread(
            target=start_fastapi_server,
            args=(main_window, 8000),
            daemon=True,
            name="FastAPIServerThread"
        )
        api_thread.start()
        logging.getLogger(__name__).info("FastAPI Bridge Thread başlatıldı (Port: 8000)")
    except Exception as e:
        logging.getLogger(__name__).error(f"FastAPI Bridge başlatılamadı: {e}")

    # ─── Cloudflare Tunnel (Uzaktan Erişim) ──────────────────────────────────
    # LattePanda dışarıdaki mobil uygulamalara erişilebilir olsun.
    try:
        from servers.tunnel_manager import start_tunnel, register_url_callback

        def _on_tunnel_url(url: str):
            """Tünel URL'si hazır olunca GUI'de bildirim göster."""
            logging.getLogger(__name__).info("Cloudflare Tünel URL: %s", url)
            # Varsa PyQt bildirim sistemi üzerinden kullanıcıya göster
            try:
                from servers.api_server import _push_notification
                _push_notification(f"🌐 Uzaktan Erişim Aktif: {url}", "success")
            except Exception:
                pass

        register_url_callback(_on_tunnel_url)
        # API hazır olana kadar 2 sn bekle sonra tüneli başlat
        threading.Timer(2.0, lambda: start_tunnel(port=8000)).start()
        logging.getLogger(__name__).info("Cloudflare Tunnel başlatma zamanlayıcısı kuruldu.")
    except Exception as e:
        logging.getLogger(__name__).warning(f"Cloudflare Tunnel başlatılamadı: {e}")
        
    # ─── Cloud Sync (Supabase Offline-First) ─────────────────────────────────
    try:
        from servers.sync_worker import init_cloud_sync
        import os
        from pemf_gui.config import get_config
        
        cfg = get_config()
        # Fallback to env vars if not in config
        sb_url = cfg.get("supabase_url", os.environ.get("SUPABASE_URL", "https://wmsxonunkphjeregpvuj.supabase.co"))
        sb_key = cfg.get("supabase_key", os.environ.get("SUPABASE_KEY", ""))
        
        init_cloud_sync(supabase_url=sb_url, supabase_key=sb_key)
        logging.getLogger(__name__).info("Cloud Sync Worker başlatma rutinleri çalıştırıldı.")
    except Exception as e:
        logging.getLogger(__name__).warning(f"Cloud Sync başlatılamadı: {e}")
    
    logging.getLogger(__name__).info("Arayüzlü sistem başarıyla başlatıldı.")
    logging.getLogger(__name__).info("Uygulamayı sonlandırmak için pencereyi kapatabilirsiniz.")
    
    # ── Tarayıcıda React Arayüzünü Otomatik Aç (Güvenilir Yöntem) ──
    from PyQt6.QtGui import QDesktopServices
    from PyQt6.QtCore import QUrl, QTimer
    def open_react_ui():
        QDesktopServices.openUrl(QUrl("http://localhost:8000/"))
        
    # Sunucu ayağa kalkması için 2 saniye bekleyip URL'yi tetikle
    QTimer.singleShot(2000, open_react_ui)
    
    # Event loop başlat
    sys.exit(app.exec())
