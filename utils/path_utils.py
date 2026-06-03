import sys
import os
import shutil
import platform
import uuid
from pathlib import Path

def resource_path(relative_path):
    """EXE içindeki gömülü dosyaları bulur (Okuma amaçlı)"""
    try:
        base_path = Path(sys._MEIPASS)
    except Exception:
        base_path = Path(__file__).resolve().parent.parent
    
    path = base_path / relative_path
    if not path.exists():
        fallback_path = base_path / "pemf_gui" / relative_path
        if fallback_path.exists():
            return str(fallback_path)
            
    return str(path)

def get_icon_path(icon_name):
    """
    Constructs the full path for an icon.
    This helps centralize the logic for locating icons, especially when dealing with
    PyInstaller's bundled application structure.
    """
    return str(resource_path(os.path.join('pemf_gui', 'resources', 'icons', icon_name)))

def get_app_data_directory():
    """Verilerin saklanacağı kalıcı klasörü belirler"""
    if platform.system() == "Windows":
        base_path = Path(os.getenv('APPDATA'))
    elif platform.system() == "Darwin":
        base_path = Path.home() / "Library" / "Application Support"
    else:
        base_path = Path.home() / ".local" / "share"

    app_data_dir = base_path / "PEMF_GUI"
    app_data_dir.mkdir(parents=True, exist_ok=True)
    return app_data_dir

def get_unique_device_id():
    """Her bilgisayar için benzersiz bir ID üretir (MAC adresinden)"""
    # Bu ID, uzaktan izleme yaparken hangi verinin kimden geldiğini anlamanızı sağlar.
    return str(uuid.getnode())

def initialize_database():
    """
    0 KM Veritabanı Oluşturucu (Çoklu DB Desteği):
    Eğer müşteride veritabanları yoksa, EXE içindeki şablonları oraya kopyalar.
    """
    app_data_dir = get_app_data_directory()
    
    # Yönetilecek veritabanı dosyaları listesi
    # (Gerçek dosya adı : Şablon dosya adı)
    db_files = {
        "pemf_treatment_history.db": "pemf_treatment_history_template.db",
        "patients.db": "patients_template.db"
    }
    
    generated_paths = {}

    for real_name, template_name in db_files.items():
        target_db_path = app_data_dir / real_name
        
        # Müşteride zaten varsa dokunma (Veri kaybını önler)
        if target_db_path.exists():
            # print(f"Mevcut DB bulundu: {real_name}")
            generated_paths[real_name] = target_db_path
            continue

        # Yoksa, şablonu kopyala
        source_template = resource_path(os.path.join('database', template_name))
        
        try:
            if Path(source_template).exists():
                # Konsolsuz (console=False) uygulamalarda print hata fırlatabilir, bu nedenle pass/log kullanılır
                shutil.copy2(source_template, target_db_path)
            else:
                pass
        except Exception as e:
            pass
            
        generated_paths[real_name] = target_db_path
        
    return generated_paths
