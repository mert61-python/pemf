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
        # APPDATA bazı headless/SYSTEM servis bağlamlarında boş olabilir → deterministik fallback
        # (yoksa TypeError ve canonical yollar ~/.pemf_gui'ye düşüp split-brain'e yol açar).
        base_path = Path(os.getenv('APPDATA') or (Path.home() / "AppData" / "Roaming"))
    elif platform.system() == "Darwin":
        base_path = Path.home() / "Library" / "Application Support"
    else:
        base_path = Path.home() / ".local" / "share"

    app_data_dir = base_path / "PEMF_GUI"
    app_data_dir.mkdir(parents=True, exist_ok=True)
    return app_data_dir

def get_unique_device_id():
    """Her bilgisayar için KALICI benzersiz ID.

    uuid.getnode() bazı makinelerde KARARSIZ: gerçek MAC okunamazsa rastgele bir değer
    döner ve restart'ta DEĞİŞİR → device_id sürekli değişirse uzaktan eşleşme bozulur
    (FE'nin sakladığı kimlik bayatlar, devices registry'sinde çöp satırlar birikir).
    Bu yüzden device_id'yi BİR KEZ üretip app_data/device_id.txt'de saklarız; sonraki
    açılışlarda hep aynısını döndürür. (FE bu ID'yi /api/health'ten alıp eşleşme için saklar.)"""
    id_path = None
    try:
        id_path = get_app_data_directory() / "device_id.txt"
        if id_path.exists():
            existing = id_path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
    except Exception:
        pass
    new_id = str(uuid.getnode())
    try:
        if id_path is not None:
            id_path.write_text(new_id, encoding="utf-8")
    except Exception:
        pass
    return new_id

# Eşleştirme kodu için kullanılan karakter kümesi:
# A-Z + 2-9 ama BELİRSİZ olanlar HARİÇ (0, O, 1, I, L → karışmasın).
_PAIRING_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_PAIRING_CODE_LENGTH = 6

def get_pairing_code():
    """Bu cihaza ait KALICI 6 haneli eşleştirme kodunu döndürür.

    Mobil uygulama, cihazı bu kod ile eşleştirir. Kod ilk çağrıda BİR KEZ
    üretilir (secrets modülü → kriptografik) ve app_data/pairing_code.txt
    dosyasına yazılır; sonraki tüm çağrılarda hep aynı dosyadan okunur.
    Karakterler büyük harf, belirsiz olanlar (0,O,1,I,L) hariç tutulur.
    """
    import secrets

    code_path = get_app_data_directory() / "pairing_code.txt"

    # Rotasyon kancası: PEMF_RESET_PAIRING_CODE=1 ise mevcut kodu sil → bir sonraki
    # satırda yeniden üretilsin (kod sızdıysa/operatör yenilemek isterse).
    if os.getenv("PEMF_RESET_PAIRING_CODE") == "1":
        try:
            code_path.unlink(missing_ok=True)
        except Exception:
            pass

    # Daha önce üretildiyse onu oku (kalıcılık).
    try:
        if code_path.exists():
            existing = code_path.read_text(encoding="utf-8").strip().upper()
            # Yalnızca geçerli (doğru uzunluk + alfabe) ise kabul et; bozuksa yeniden üret.
            if (
                len(existing) == _PAIRING_CODE_LENGTH
                and all(ch in _PAIRING_CODE_ALPHABET for ch in existing)
            ):
                return existing
    except Exception:
        pass

    # İlk kez: kriptografik olarak güvenli yeni kod üret ve kalıcı yaz.
    code = "".join(
        secrets.choice(_PAIRING_CODE_ALPHABET) for _ in range(_PAIRING_CODE_LENGTH)
    )
    try:
        code_path.write_text(code, encoding="utf-8")
    except Exception:
        # Yazılamasa bile (ör. salt-okunur FS) çalışma zamanı kodunu döndür.
        pass
    return code

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

def packaged_resource_path(*parts):
    """
    Returns the correct absolute path to bundled resources.
    If running as a PyInstaller bundle, resolves via sys.executable parent + _internal.
    If running from source, resolves relative to project root.
    """
    if getattr(sys, "frozen", False):
        # We are running in a PyInstaller bundle (usually OneDir)
        base = Path(sys.executable).parent / "_internal"
    else:
        # We are running from standard Python source
        base = Path(__file__).resolve().parents[1]
    
    return base.joinpath(*parts)

