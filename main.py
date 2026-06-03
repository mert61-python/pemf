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

    # ─── Expo/React Native frontend için local HTTP backend köprüsü ─────────
    # Port config/config.json içindeki http_port'tan okunur (varsayılan 5050).
    try:
        from servers.frontend_bridge import start_frontend_bridge
        frontend_backend = start_frontend_bridge(project_root=project_root)
        if frontend_backend:
            import logging
            logging.getLogger(__name__).info(
                "Frontend backend köprüsü çalışıyor: http://%s:%s",
                frontend_backend[0],
                frontend_backend[1],
            )
            import webbrowser
            import sys
            
            # Geliştirme (Development) ortamındaysak, Expo React Frontend genelde 3001 portunda çalışır.
            # EXE olarak (Production) derlendiğinde ise backend kendi dist klasörünü 5050'den sunar.
            dist_path = project_root / "frontend" / "dist" / "index.html"
            if getattr(sys, "frozen", False) or dist_path.exists():
                url = f"http://{frontend_backend[0]}:{frontend_backend[1]}"
            else:
                url = "http://localhost:3001"
                
            webbrowser.open(url)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Frontend backend köprüsü başlatılamadı: %s",
            exc,
        )

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
    
    # FastAPI Server Thread başlat
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
    
    logging.getLogger(__name__).info("Arayüzlü sistem başarıyla başlatıldı.")
    logging.getLogger(__name__).info("Uygulamayı sonlandırmak için pencereyi kapatabilirsiniz.")
    
    # Event loop başlat
    sys.exit(app.exec())
