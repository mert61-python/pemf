# Author: mertaygn, cglrgrkn
import os
import platform
import shutil
import sys
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


#: Kullanıcı-başına eski konumdan makine-geneline taşınacak dosyalar.
#
# ⚠️ YALNIZ tıbbi kayıt + onu açan anahtar. Cihaz kimliği/eşleştirme dosyaları BİLEREK dışarıda:
# onlar makineye özgüdür ve kopyalanırsa iki kayıt aynı device_id'yi paylaşır.
_GOC_DOSYALARI = (
    "pemf_treatment_history.db",
    "pemf_patients.db",
    "auth_users.db",
)


def _kullanicidan_makineye_gocur(hedef: Path) -> None:
    """Tıbbi kaydı `%APPDATA%\\PEMF_GUI`den makine-geneli köke TAŞI (bir kez).

    ⚠️ DENETİM 2026-08-09 (Tier 1): launcher `PEMF_DATA_DIR` vermiyordu → veri Windows
    KULLANICISINA ÖZELdi. Vardiyalı klinikte ikinci hesapla açan veteriner "BOŞ KLİNİK"
    görüyordu: hasta listesi yok, geçmiş yok. Kullanıcı açısından VERİ KAYBINDAN ayırt edilemez.
    Launcher artık makine-geneli kök veriyor; bu fonksiyon eski verinin kaybolmamasını sağlar.

    KURALLAR (tıbbi veriyle çalışıyoruz, geri dönüşü yok):
      * Hedefte AYNI ADLI dosya VARSA DOKUNULMAZ — üzerine yazmak, yeni kliniğin kaydını siler.
      * KOPYALANIR, kaynak SİLİNMEZ. Kopya bozulursa eski dosya hâlâ yerinde durur; temizlik
        operatörün bilinçli kararına bırakılır.
      * Tek bir dosya kopyalanamazsa diğerleri denenir ve durum loglanır; göç YARIM kalabilir
        ama hiçbir veri KAYBOLMAZ.
    """
    try:
        if platform.system() != "Windows":
            return
        eski_kok = os.getenv("APPDATA")
        if not eski_kok:
            return
        eski = Path(eski_kok) / "PEMF_GUI"
        if not eski.is_dir() or eski.resolve() == hedef.resolve():
            return
        import logging

        for ad in _GOC_DOSYALARI:
            kaynak, varis = eski / ad, hedef / ad
            if not kaynak.is_file() or varis.exists():
                continue
            try:
                shutil.copy2(kaynak, varis)
                logging.getLogger(__name__).warning(
                    "VERİ GÖÇÜ: %s kullanıcı klasöründen makine geneline kopyalandı (kaynak SİLİNMEDİ: %s).", ad, kaynak
                )
            except Exception:
                logging.getLogger(__name__).warning(
                    "VERİ GÖÇÜ: %s kopyalanamadı, eski konumda kaldı.", ad, exc_info=True
                )
    except Exception:
        # Göç bir KOLAYLIKtır; başarısız olması backend'i başlatmamalı.
        pass


def get_app_data_directory():
    """Verilerin saklanacağı kalıcı klasörü belirler"""
    # AÇIK OVERRIDE: PEMF_DATA_DIR set ise onu kullan. Servis (LocalSystem) bağlamında APPDATA =
    # ...\systemprofile\AppData\Roaming'e (operatöre GÖRÜNMEZ + yedeklenemez) düşer; bu yüzden
    # device.env/server.env PEMF_DATA_DIR=C:\ProgramData\PEMF_System verir → hasta/tedavi DB +
    # SQLCipher anahtar dosyası + device_id makine-genelinde, erişilebilir, yedeklenebilir olur.
    override = os.getenv('PEMF_DATA_DIR', '').strip()
    if override:
        app_data_dir = Path(override) / "PEMF_GUI"
        app_data_dir.mkdir(parents=True, exist_ok=True)
        _kullanicidan_makineye_gocur(app_data_dir)
        return app_data_dir
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
            if len(existing) == _PAIRING_CODE_LENGTH and all(ch in _PAIRING_CODE_ALPHABET for ch in existing):
                return existing
    except Exception:
        pass

    # İlk kez: kriptografik olarak güvenli yeni kod üret ve kalıcı yaz.
    code = "".join(secrets.choice(_PAIRING_CODE_ALPHABET) for _ in range(_PAIRING_CODE_LENGTH))
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
        "patients.db": "patients_template.db",
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
        except Exception:
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
        # PyInstaller bundle. Datas'ın açıldığı kökü _MEIPASS verir:
        #   • onedir  → <exe_dir>/_internal  (executable/_internal ile aynı)
        #   • onefile → %TEMP%\_MEIxxxxx     (executable yanında _internal YOK!)
        # Bu yüzden _MEIPASS kullan; yoksa (çok eski PyInstaller) onedir'e düş.
        meipass = getattr(sys, "_MEIPASS", None)
        base = Path(meipass) if meipass else (Path(sys.executable).parent / "_internal")
    else:
        # We are running from standard Python source
        base = Path(__file__).resolve().parents[1]

    return base.joinpath(*parts)


_APP_VERSION = None


def get_app_version() -> str:
    """TEK versiyon kaynağı (audit B-8.1): eskiden FastAPI/discovery/system_info farklı sabitler
    (1.0.0 / 1.5 / 1) raporluyordu.

    ⚠️ SIRA DÜZELTİLDİ (2026-08-09 denetimi, Tier 3): eskiden ÖNCE `frontend_version.json`
    okunuyordu. O AYRI bir yayın kanalıdır (`versions.json` → `frontendOta`, bugün **1.4.1**);
    backend sürümü ise `VERSION` (**1.9.5**). Sonuç: `X-API-Version`, FastAPI `/docs` ve
    keşif yanıtları sahaya **1.4.1** diyordu — altı sürüm geride ve YANLIŞ kanaldan. Bir olayda
    "hangi sürüm koşuyor" sorusunun cevabı yanlışsa teşhis de yanlış başlar.

    `update_manager._version_paths()` zaten VERSION'ı önceliyordu; iki yer ayrışmıştı. Doğru
    sıra: VERSION → frontend_version.json (geriye uyum) → sabit. Cache'lenir.
    """
    global _APP_VERSION
    if _APP_VERSION:
        return _APP_VERSION
    import json as _json

    for base in (packaged_resource_path("VERSION"), Path(__file__).resolve().parents[1] / "VERSION"):
        try:
            v = Path(base).read_text(encoding="utf-8").strip()
            if v:
                _APP_VERSION = v
                return v
        except Exception:
            pass
    for base in (
        packaged_resource_path("frontend_version.json"),
        Path(__file__).resolve().parents[1] / "frontend_version.json",
    ):
        try:
            v = str(_json.loads(Path(base).read_text(encoding="utf-8")).get("version", "")).strip()
            if v:
                _APP_VERSION = v
                return v
        except Exception:
            pass
    _APP_VERSION = "1.4.0"
    return _APP_VERSION


def get_build_id() -> str:
    """Kurulu PAKETİN kimliği — sürüm numarasının söyleyemediği şey.

    İki cihaz aynı `1.9.5`i raporlayıp farklı paket içeriği çalıştırabilir (yeniden yayın,
    yarım güncelleme, elle kopyalanmış dosya). Launcher kurduğu paketin sha256'sını
    `PEMF_BASE_SHA` ile geçirir; kısaltılmış hâli olay kaydında "hangi ikili" sorusunu
    tek başına cevaplar. Launcher'sız çalıştırmada boş döner (uydurma değer ÜRETİLMEZ)."""
    import os as _os

    sha = (_os.environ.get("PEMF_BASE_SHA") or "").strip().lower()
    return sha[:12] if len(sha) >= 12 else ""
