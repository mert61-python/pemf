import shutil
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

class DigitalTwinFileCopyThread(QThread):
    """
    Tek EXE performans optimizasyonu:
    Dosyaları her seferinde Temp'e açmak yerine, AppData'ya bir kez açar.
    Sadece sürüm değişirse tekrar kopyalar.
    """
    # Signal: İlerleme bilgisini ana thread'e iletir
    # Parametreler: current_step (int), total_steps (int), message (str)
    progress_updated = pyqtSignal(int, int, str)
    
    # Signal: Hata oluştuğunda
    # Parametre: error_message (str)
    error_occurred = pyqtSignal(str)
    
    # Signal: Kopyalama tamamlandığında
    # Parametreler: exe_path (str), pemf_temp_dir (str), success (bool)
    copy_completed = pyqtSignal(str, str, bool)
    
    def __init__(self, build_pemf_path, pemf_temp_dir, logger, parent=None):
        super().__init__(parent)
        self.build_pemf_path = Path(build_pemf_path)  # PyInstaller içindeki gömülü kaynak (_MEIPASS)
        self.pemf_temp_dir = Path(pemf_temp_dir)      # Kalıcı hedef klasör (AppData)
        self.logger = logger
    
    def get_embedded_version(self):
        """Gömülü dosyaların versiyonunu (veya tarihini) alır"""
        try:
            # En basit yöntem: Gömülü EXE'nin boyutunu ve tarihini referans al
            # Veya build sırasında koyduğunuz bir version.txt dosyasını okuyun
            embedded_exe = self.build_pemf_path / "PEMF.exe"
            if embedded_exe.exists():
                stat = embedded_exe.stat()
                return f"{stat.st_size}_{stat.st_mtime}"
            return "0"
        except Exception:
            return "0"
    
    def run(self):
        """
        Thread'in ana çalışma metodu.
        Sürüm kontrolü yapar, gerekirse dosyaları kopyalar.
        """
        try:
            # Hedef klasör yoksa oluştur
            self.pemf_temp_dir.mkdir(parents=True, exist_ok=True)
            
            # 1. VERSİYON KONTROLÜ (Performansın Sırrı Burası)
            current_version_hash = self.get_embedded_version()
            version_file = self.pemf_temp_dir / "version.lock"
            
            should_copy = True
            
            # Eğer hedefte sürüm dosyası varsa ve uyuşuyorsa kopyalamayı atla
            if version_file.exists() and (self.pemf_temp_dir / "PEMF.exe").exists():
                try:
                    with open(version_file, 'r') as f:
                        installed_version = f.read().strip()
                    
                    if installed_version == current_version_hash:
                        if self.logger:
                            self.logger.info("Digital Twin dosyaları güncel. Kopyalama atlanıyor (Hızlı Başlatma).")
                        should_copy = False
                except Exception:
                    should_copy = True  # Dosya bozuksa tekrar kopyala
            
            if not should_copy:
                # HIZLI YOL: Kopyalama yok, direkt bitir
                exe_path = self.pemf_temp_dir / "PEMF.exe"
                self.progress_updated.emit(100, 100, "Hazır!")
                self.copy_completed.emit(str(exe_path), str(self.pemf_temp_dir), True)
                return
            
            # --- KOPYALAMA İŞLEMİ (Sadece ilk kez veya güncellemede çalışır) ---
            if self.logger:
                self.logger.info("Digital Twin kurulumu yapılıyor (İlk Çalıştırma)...")
            
            # Temiz kurulum için eski dosyaları sil
            if self.pemf_temp_dir.exists():
                try:
                    shutil.rmtree(self.pemf_temp_dir)
                    self.pemf_temp_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    if self.logger:
                        self.logger.warning("Eski dosyalar temizlenirken hata (kritik değil): %s", e)
            
            # Kopyalanacaklar listesi (Unity Build Klasör Yapısı)
            items_to_copy = [
                "PEMF.exe",
                "UnityPlayer.dll",
                "UnityCrashHandler64.exe",
                "PEMF_Data",
                "MonoBleedingEdge"
            ]
            
            total_items = len(items_to_copy)
            
            for index, item_name in enumerate(items_to_copy):
                src = self.build_pemf_path / item_name
                dst = self.pemf_temp_dir / item_name
                
                self.progress_updated.emit(index + 1, total_items + 1, f"Kuruluyor: {item_name}...")
                
                if not src.exists():
                    # Bazı buildlerde MonoBleedingEdge olmayabilir, devam et
                    if self.logger:
                        self.logger.debug("Kaynak bulunamadı (atlanıyor): %s", src)
                    continue
                    
                try:
                    if src.is_dir():
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                    if self.logger:
                        self.logger.debug("Kopyalandı: %s -> %s", item_name, dst)
                except Exception as e:
                    if self.logger:
                        self.logger.warning("Kopyalama hatası (%s): %s", item_name, e)
                    # Kritik dosya değilse devam et
            
            # Yeni versiyon bilgisini yaz
            try:
                with open(self.pemf_temp_dir / "version.lock", 'w') as f:
                    f.write(current_version_hash)
            except Exception as e:
                if self.logger:
                    self.logger.warning("Versiyon dosyası yazılamadı: %s", e)
            
            # --- DÜZELTME 1: Dosya sisteminin rahatlaması için bekleme ---
            # Antivirüs taraması ve I/O flush için işletim sistemine zaman tanıyoruz
            # QThread.msleep kullanılarak thread-safe bekleme yapılır (time.sleep yerine)
            self.msleep(1500)  # 1.5 saniye bekle
            # -------------------------------------------------------------
            
            exe_path = self.pemf_temp_dir / "PEMF.exe"
            self.progress_updated.emit(total_items + 1, total_items + 1, "Kurulum tamamlandı!")
            self.copy_completed.emit(str(exe_path), str(self.pemf_temp_dir), True)
            
        except Exception as e:
            error_msg = f"Dosya kopyalama hatası: {str(e)}"
            if self.logger:
                self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            self.copy_completed.emit("", "", False)
