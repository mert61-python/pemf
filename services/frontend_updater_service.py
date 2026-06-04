import os
import json
import urllib.request
import zipfile
import shutil
import logging
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

class FrontendUpdaterThread(QThread):
    """
    Arka planda çalışarak React Frontend için güncelleme olup olmadığını kontrol eder.
    Güncelleme varsa indirir ve APPDATA/PEMF_GUI/frontend_dist içerisine çıkartır.
    """
    # Signals
    update_available = pyqtSignal(str) # version
    update_finished = pyqtSignal(str)  # success message
    update_error = pyqtSignal(str)     # error message

    def __init__(self, current_version="1.0.0", parent=None):
        super().__init__(parent)
        self.current_version = current_version
        
        # Test/Production URL'leri (GitHub Raw veya kendi sunucunuz)
        # Örnek JSON Formatı: {"version": "1.0.1", "download_url": "https://.../dist.zip"}
        self.version_url = "https://raw.githubusercontent.com/mert61-python/pemf-update/main/frontend_version.json"
        
        self.app_data_dir = Path(os.environ.get("APPDATA", "C:/")) / "PEMF_GUI"
        self.frontend_dist_dir = self.app_data_dir / "frontend_dist"
        self.logger = logging.getLogger(__name__)

    def get_local_version(self):
        """Lokalde (AppData) yüklü olan sürümü oku."""
        version_file = self.frontend_dist_dir / "version.json"
        if version_file.exists():
            try:
                with open(version_file, "r") as f:
                    data = json.load(f)
                    return data.get("version", self.current_version)
            except Exception:
                pass
        return self.current_version

    def get_bundled_version(self):
        """Uygulamanın içine gömülü olan sürümü oku."""
        try:
            from utils.path_utils import packaged_resource_path
            version_file = packaged_resource_path("frontend", "dist", "version.json")
            if version_file.exists():
                with open(version_file, "r") as f:
                    data = json.load(f)
                    return data.get("version", self.current_version)
        except Exception:
            pass
        return self.current_version

    def run(self):
        try:
            if os.environ.get("PEMF_DISABLE_FRONTEND_UPDATER") == "1":
                self.logger.info("Frontend Oto-Güncelleyici devredışı bırakıldı (PEMF_DISABLE_FRONTEND_UPDATER=1).")
                return

            local_version = self.get_local_version()
            bundled_version = self.get_bundled_version()
            effective_version = max(local_version, bundled_version)
            self.logger.info(f"Frontend Oto-Güncelleyici Başladı. Sürümler: AppData={local_version}, Bundled={bundled_version}, Effective={effective_version}")
            
            # Sunucudan versiyon JSON'unu çek
            req = urllib.request.Request(self.version_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                
            remote_version = data.get("version")
            download_url = data.get("download_url")
            
            if not remote_version or not download_url:
                self.logger.warning("Sunucu yanıtında version veya download_url bulunamadı.")
                return

            if remote_version > effective_version:
                self.logger.info(f"Yeni frontend sürümü bulundu: {remote_version} (Current: {effective_version})")
                self.update_available.emit(remote_version)
                
                # ZIP dosyasını indir
                zip_path = self.app_data_dir / "frontend_update.zip"
                urllib.request.urlretrieve(download_url, str(zip_path))
                
                # Temp klasörde çıkart ve doğrula
                temp_extract_dir = self.app_data_dir / "frontend_dist_temp"
                if temp_extract_dir.exists():
                    shutil.rmtree(str(temp_extract_dir), ignore_errors=True)
                temp_extract_dir.mkdir(parents=True, exist_ok=True)
                
                # ZIP'i çıkart
                with zipfile.ZipFile(str(zip_path), 'r') as zip_ref:
                    zip_ref.extractall(str(temp_extract_dir))
                
                # Yeni paketin doğrulanması (index.html ve js var mı?)
                is_valid = True
                if not (temp_extract_dir / "index.html").exists():
                    is_valid = False
                    self.logger.error("İndirilen frontend güncellemesi hatalı: index.html bulunamadı.")
                
                js_dir = temp_extract_dir / "_expo" / "static" / "js" / "web"
                if is_valid and not (js_dir.exists() and any(f.endswith('.js') for f in os.listdir(js_dir))):
                    is_valid = False
                    self.logger.error("İndirilen frontend güncellemesi hatalı: JS bundle bulunamadı.")

                if not is_valid:
                    self.logger.error("Güncelleme reddedildi. Temp klasör temizleniyor.")
                    shutil.rmtree(str(temp_extract_dir), ignore_errors=True)
                    self.update_error.emit("İndirilen paket geçersiz/eksik.")
                    if zip_path.exists():
                        os.remove(str(zip_path))
                    return

                # Güvenli Swap (Atomic-like)
                old_backup_dir = self.app_data_dir / "frontend_dist_old"
                if old_backup_dir.exists():
                    shutil.rmtree(str(old_backup_dir), ignore_errors=True)
                
                if self.frontend_dist_dir.exists():
                    os.rename(str(self.frontend_dist_dir), str(old_backup_dir))
                
                os.rename(str(temp_extract_dir), str(self.frontend_dist_dir))
                
                if old_backup_dir.exists():
                    shutil.rmtree(str(old_backup_dir), ignore_errors=True)

                # Yeni versiyonu kaydet
                with open(self.frontend_dist_dir / "version.json", "w") as f:
                    json.dump({"version": remote_version}, f)
                
                # İndirilen ZIP dosyasını sil
                if zip_path.exists():
                    os.remove(str(zip_path))
                
                self.logger.info("Frontend güncellemesi başarıyla tamamlandı.")
                self.update_finished.emit(f"Yeni arayüz (v{remote_version}) yüklendi. Bir sonraki açılışta aktif olacak.")
            else:
                self.logger.info("Frontend zaten güncel.")
                
        except Exception as e:
            self.logger.error(f"Frontend güncelleme kontrolü sırasında hata: {str(e)}")
            self.update_error.emit(str(e))
