import os
import sys
import json
import ssl
import subprocess
import tempfile
import urllib.request
import urllib.error
from PyQt6.QtCore import QThread, pyqtSignal

class UpdateCheckerThread(QThread):
    """
    Belirtilen URL'den version.json dosyasını çekip sürüm kontrolü yapar.
    """
    update_available = pyqtSignal(str, str, str)  # version, download_url, release_notes
    check_failed = pyqtSignal(str)
    up_to_date = pyqtSignal()

    def __init__(self, current_version, version_json_url, parent=None):
        super().__init__(parent)
        self.current_version = current_version
        self.version_json_url = version_json_url

    def run(self):
        try:
            # SSL doğrulama sorunlarını aşmak için context
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(self.version_json_url, headers={'User-Agent': 'PEMF-Updater'})
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

            latest_version = data.get("version", "")
            download_url = data.get("download_url", "")
            release_notes = data.get("release_notes", "")

            if latest_version and latest_version != self.current_version:
                # Basit bir eşitsizlik kontrolü yaptık, isterseniz semver kütüphanesi ile daha gelişmiş yapılabilir.
                # String karşılaştırmasında "1.3" > "1.2" olarak çalışır.
                self.update_available.emit(latest_version, download_url, release_notes)
            else:
                self.up_to_date.emit()

        except Exception as e:
            self.check_failed.emit(str(e))

class UpdateDownloaderThread(QThread):
    """
    Setup dosyasını indirir ve kaydeder.
    """
    progress = pyqtSignal(int)
    download_finished = pyqtSignal(str)  # İndirilen dosyanın tam yolu
    download_error = pyqtSignal(str)

    def __init__(self, download_url, parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self.save_path = os.path.join(tempfile.gettempdir(), "PEMF_GUI_Update_Setup.exe")
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(self.download_url, headers={'User-Agent': 'PEMF-Updater'})
            with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
                total_size = int(response.info().get('Content-Length', 0))
                downloaded = 0
                # İndirme hızını artırmak için chunk boyutunu 8KB'dan 1MB'a çıkarıyoruz
                chunk_size = 1024 * 1024 

                with open(self.save_path, 'wb') as f:
                    while not self.is_cancelled:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            self.progress.emit(percent)
                            
            if self.is_cancelled:
                if os.path.exists(self.save_path):
                    os.remove(self.save_path)
                self.download_error.emit("İndirme kullanıcı tarafından iptal edildi.")
            else:
                self.download_finished.emit(self.save_path)

        except Exception as e:
            self.download_error.emit(str(e))

def launch_installer_and_exit(installer_path):
    """
    İndirilen kurulum dosyasını başlatır ve mevcut uygulamayı kapatır.
    /SILENT: Inno Setup sessiz kurulum parametresi.
    """
    try:
        # Popen ile arka planda yeni işlem olarak başlat
        subprocess.Popen([installer_path, '/SILENT'], creationflags=subprocess.CREATE_NEW_CONSOLE)
        
        # Uygulamayı hemen kapat
        import PyQt6.QtWidgets as QtWidgets
        app = QtWidgets.QApplication.instance()
        if app:
            app.quit()
        else:
            sys.exit(0)
    except Exception as e:
        print(f"Güncelleyici başlatılamadı: {e}")
