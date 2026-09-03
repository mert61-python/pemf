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
# ⚠️ YALNIZ tıbbi kayıt. Cihaz kimliği/eşleştirme dosyaları BİLEREK dışarıda: onlar makineye
# özgüdür ve kopyalanırsa iki kayıt aynı device_id'yi paylaşır. Sır dosyası (`pemf_secrets.json`)
# da AYNI sebeple dışarıdadır — içinde `device_id`/`pairing_code`/`device_registry_secret` var.
# ⚠️ ADLAR ÜRETİMDEKİ GERÇEK DOSYA ADLARIDIR (2026-08-15 düzeltmesi). Burada hasta DB'si
# "pemf_patients.db" yazıyordu; o ad hiçbir sürümde üretim DB adı OLMADI — yalnız YEDEK dosya
# ön-ekidir (`headless_db_maintenance` `pemf_patients_<tarih>.db` üretir). Üretimdeki ad
# `patients.db`dir (`database/patient_database.PatientDatabase.db_file` varsayılanı). Sonuç:
# "vardiyalı klinikte boş klinik" düzeltmesi seans geçmişini taşıyor, HASTA KAYITLARINI HİÇ
# taşımıyordu — ve testi de aynı yanlış adı kullandığı için yeşil kalıyordu.
_GOC_DOSYALARI = (
    "pemf_treatment_history.db",
    "patients.db",
    "auth_users.db",
)

#: Göç listesinden SQLCipher ile şifreli olanlar.
#
# ⚠️ BU KÜME `_GOC_DOSYALARI` İLE BİRLİKTE GÜNCELLENİR. Yalnız yukarıdaki liste düzeltilip
# burası unutulursa `ad in _GOC_SIFRELI` TUTMAZ ve şifreli hasta DB'si, hedefin anahtarıyla
# açılıp açılmayacağı KONTROL EDİLMEDEN körlemesine kopyalanır — düzeltme, düzelttiğinden daha
# kötü bir hâl yaratır.
#
# ⚠️ YORUM DÜZELTMESİ: burada eskiden "kopyalanmadan ÖNCE hedefin anahtarıyla açılabildikleri
# DOĞRULANIR (bkz. `_hedef_anahtariyla_acilir_mi`)" yazıyordu. O FONKSİYON HİÇ YOK — 1.9.11'de
# özyineleme (BSOD) yüzünden KALDIRILDI ve atıf yorumda kaldı. Karar SAF DOSYA OKUMASIYLA
# verilir (`_tasinabilir_mi`: ham anahtar karşılaştırması). "Gerçekten açılıyor mu" sorusunu
# göç DEĞİL, DB açılışındaki karantina zarfı cevaplar (`database/sqlcipher_util.karantinaya_al`).
_GOC_SIFRELI = frozenset({"pemf_treatment_history.db", "patients.db"})


#: Sır dosyasının adı (utils.secrets_manager ile AYNI).
_SIR_DOSYASI = "pemf_secrets.json"


def _sqlcipher_anahtarini_gocur(eski: Path, hedef: Path) -> bool:
    """Eski kökteki at-rest anahtarını YENİ köke taşı — YALNIZ `sqlcipher_key`.

    NEDEN GEREKLİ. Tıbbi kayıt göçü şifreli DB'leri taşıyamıyordu: anahtar
    `pemf_secrets.json`dadır ve o dosya BÜTÜN olarak göçemez (içinde `device_id`,
    `pairing_code`, `device_registry_secret` var — kopyalanırsa iki kurulum aynı cihaz
    kimliğini paylaşır). Sonuç: şifreli kurulumlarda eski veri eski konumda kalıyor ve
    vardiyalı klinikte ikinci hesapla açan veteriner hâlâ "BOŞ KLİNİK" görüyordu.

    Bu fonksiyon SADECE `auto.sqlcipher_key` alanını taşır; cihaz kimliği DOKUNULMAZ.

    ⚠️ Değer DPAPI ile `CRYPTPROTECT_LOCAL_MACHINE` kapsamında sarılıdır — yani MAKİNEYE
    bağlıdır, kullanıcıya değil. Bu yüzden şifreli değeri OLDUĞU GİBİ kopyalamak aynı
    makinede geçerlidir; çözüp yeniden sarmaya gerek yok (ve gerekmemeli: göç, backend
    AÇILIŞINDA çalışır, orada kripto katmanına dokunmak gereksiz risktir).

    ⚠️ HEDEFTE ANAHTAR VARSA ASLA EZİLMEZ. Hedefin kendi verisi o anahtarla şifreli olabilir;
    üzerine yazmak ÇALIŞAN bir kurulumu okunamaz hâle getirir — düzeltmeye çalıştığımız
    hatanın ta kendisi.

    Döner: anahtar taşındıysa `True`.
    """
    import json
    import logging

    try:
        kaynak_j, hedef_j = eski / _SIR_DOSYASI, hedef / _SIR_DOSYASI
        if not kaynak_j.is_file():
            return False
        src = json.loads(kaynak_j.read_text(encoding="utf-8"))
        anahtar = (src.get("auto") or {}).get("sqlcipher_key")
        if not anahtar:
            return False

        dst = {}
        if hedef_j.is_file():
            dst = json.loads(hedef_j.read_text(encoding="utf-8"))
        if (dst.get("auto") or {}).get("sqlcipher_key"):
            return False  # ⚠️ EZME: hedefin kendi verisi bu anahtarla şifreli olabilir

        # ⚠️ ÇÖZÜLEBİLİRLİK KAPISI (2026-08-15). Ham değer BU makinede çözülemiyorsa (blob başka
        # bir makine/kullanıcı bağlamında sarılmış) hedefte "saklanmış ama çözülemeyen" bir sır
        # kalır → `get_secret` fail-closed RuntimeError atar → BACKEND BİR DAHA HİÇ AÇILMAZ.
        # Ölçüldü: göç, çalışan bir kurulumu açılamaz hâle getirebiliyordu.
        #
        # ⚠️ YERİ ÖNEMLİ: yukarıdaki "hedefte anahtar VARSA dokunma" dalından SONRA, yazımdan
        # hemen ÖNCE. Daha erken konursa hiçbir şey yazılmayacak durumlarda da operatöre
        # korkutucu bir ERROR loglanır (gereksiz destek çağrısı).
        #
        # ⚠️ `_tasinabilir_mi`nin "SIR/KRİPTO KATMANINA DOKUNMA" kuralına AYKIRI DEĞİLDİR:
        # o kural, YOL katmanına (`get_app_data_directory`) dönen çağrıyı yasaklar — 1.9.9/1.9.10
        # BSOD özyinelemesi oradan geliyordu. Buradaki kontrol saf çözümlemedir ve yol katmanına
        # DOKUNMAZ; test çağrı sayısını 0 olarak ölçüp kilitler.
        from utils.secrets_manager import bu_makinede_cozulebilir_mi

        if not bu_makinede_cozulebilir_mi(anahtar):
            logging.getLogger(__name__).error(
                "VERİ GÖÇÜ ATLANDI: eski kökteki at-rest anahtarı BU MAKİNEDE ÇÖZÜLEMİYOR "
                "(başka makine/kullanıcı bağlamında sarılmış olabilir). Kopyalansaydı hedefte "
                "'saklanmış ama çözülemeyen' bir sır kalır ve backend BİR DAHA HİÇ AÇILMAZDI. "
                "Eski veri kaynağında DURUYOR: %s",
                kaynak_j,
            )
            return False

        dst.setdefault("auto", {})["sqlcipher_key"] = anahtar
        dst.setdefault("_comment", src.get("_comment", ""))
        dst.setdefault("_version", src.get("_version", 1))
        # Atomik yaz: yarım kalan bir sır dosyası TÜM kurulumu açılamaz hâle getirir.
        gecici = hedef_j.with_suffix(".json.goc-tmp")
        gecici.write_text(json.dumps(dst, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(gecici, hedef_j)
        logging.getLogger(__name__).warning(
            "VERİ GÖÇÜ: at-rest anahtarı yeni köke taşındı (YALNIZ sqlcipher_key; cihaz "
            "kimliği taşınmadı) → eski şifreli tıbbi kayıt yeni kökte okunabilir."
        )
        return True
    except Exception:
        logging.getLogger(__name__).warning("VERİ GÖÇÜ: at-rest anahtarı taşınamadı.", exc_info=True)
        return False


def _sifreli_mi(dosya: Path) -> bool:
    """Dosya SQLCipher ile şifreli mi? (düz-metin SQLite başlığı YOKSA şifreli sayılır)"""
    try:
        with open(dosya, "rb") as fh:
            return not fh.read(16).startswith(b"SQLite format 3")
    except Exception:
        return True  # okunamıyorsa güvenli taraf: şifreli varsay → kopyalama


def _tasinabilir_mi(dosya: Path, eski: Path, hedef: Path) -> bool:
    """`dosya` yeni köke KOPYALANABİLİR mi?

    ⚠️⚠️ BU FONKSİYON SIR/KRİPTO KATMANINA **ASLA** DOKUNMAMALI — SONSUZ ÖZYİNELEME.
    İlk yazımı `get_sqlcipher_key()` çağırıyordu ve şu döngüyü kuruyordu:

        get_app_data_directory → _kullanicidan_makineye_gocur → (bu fonksiyon)
          → get_sqlcipher_key → secrets_manager.get_secret → _load → _data_dir
          → get_app_data_directory → ...

    Sonuç: backend AÇILIŞTA sonsuz özyinelemeye girip belleği tüketiyordu. Geliştirme
    makinesinde bu, commit limitini doldurup Windows'u BSOD'a (0x10E) götürdü; klinikte
    cihazın hiç açılmaması demekti. (Bu kusur app 1.9.9 ve 1.9.10'a YAYINLANDI ve
    1.9.11 ile düzeltildi.)

    Bu yüzden karar YALNIZ SAF DOSYA OKUMASIYLA verilir:
      * düz-metin SQLite → taşınır (hedefte şifreleme açıksa backend ilk açılışta şifreler);
      * şifreli → ancak kaynak ile hedefin at-rest anahtarı AYNIYSA taşınır. Anahtarı
        `_sqlcipher_anahtarini_gocur` zaten taşımış olur; ham (DPAPI-sarılı) değerler
        JSON'dan okunup KARŞILAŞTIRILIR — çözülmez, türetilmez.
    """
    if not _sifreli_mi(dosya):
        return True
    k_eski = _ham_sqlcipher_anahtari(eski)
    k_hedef = _ham_sqlcipher_anahtari(hedef)
    return bool(k_eski) and k_eski == k_hedef


def _ham_sqlcipher_anahtari(kok: Path) -> str:
    """`pemf_secrets.json` içindeki HAM (DPAPI-sarılı) `sqlcipher_key` — çözmeden.

    SecretsManager KULLANILMAZ: o `get_app_data_directory`ye geri döner ve özyineleme kurar
    (bkz. `_tasinabilir_mi`). Karşılaştırma için ham değer zaten yeterli."""
    import json

    try:
        p = kok / _SIR_DOSYASI
        if not p.is_file():
            return ""
        return str((json.loads(p.read_text(encoding="utf-8")).get("auto") or {}).get("sqlcipher_key") or "")
    except Exception:
        return ""


#: Göçün SÜREÇ BAŞINA bir kez çalıştığı hedef kökler.
#
# ⚠️ SAHA (2026-08-14) — CİHAZ HİÇ AÇILMIYORDU, kurtarma zarfı GERİ ALINIYORDU. `get_app_data_directory`
# göçü HER çağrıda tetikliyordu ve o fonksiyon sıcak yolda (device_id, pairing_code, SecretsManager…)
# defalarca çağrılıyor. Zincir şuydu:
#   at-rest anahtarı DB'ye uymuyor → kurtarma DB'yi karantinaya alıyor (doğru davranış)
#   → temiz DB açmak için anahtar isteniyor → SecretsManager → get_app_data_directory
#   → GÖÇ YENİDEN ÇALIŞIYOR → az önce kenara alınan BOZUK DB eski kökten GERİ KOPYALANIYOR
#   → yeni bağlantı yine bozuk dosyayı açıyor → "file is not a database" → backend ÖLÜYOR.
# Yani tuğlalaşmayı önlemek için yazılmış zarfın işini, göçün kendisi geri alıyordu.
# Göç zaten TASARIM GEREĞİ tek seferliktir (bkz. fonksiyon başlığı: "bir kez").
_GOC_YAPILDI: set = set()


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
        # ⚠️ SÜREÇ BAŞINA BİR KEZ (bkz. `_GOC_YAPILDI`): tekrar çalışması, karantinaya alınmış
        # bozuk bir DB'yi geri getirip cihazı açılamaz hâle sokuyordu.
        anahtar = str(hedef.resolve()) if hedef.exists() else str(hedef)
        if anahtar in _GOC_YAPILDI:
            return
        _GOC_YAPILDI.add(anahtar)
        eski_kok = os.getenv("APPDATA")
        if not eski_kok:
            return
        eski = Path(eski_kok) / "PEMF_GUI"
        if not eski.is_dir() or eski.resolve() == hedef.resolve():
            return
        import logging

        # ⚠️ SIRA: anahtar ÖNCE taşınır. Aksi hâlde aşağıdaki `_tasinabilir_mi`
        # kontrolü şifreli DB'leri reddeder ve şifreli kurulumlarda göç HİÇ çalışmaz
        # (vardiyalı klinikte "boş klinik" devam ederdi). Anahtar yalnız hedefte HİÇ yoksa
        # taşınır; varsa dokunulmaz.
        _sqlcipher_anahtarini_gocur(eski, hedef)

        for ad in _GOC_DOSYALARI:
            kaynak, varis = eski / ad, hedef / ad
            if not kaynak.is_file() or varis.exists():
                continue
            # ⚠️ Ham anahtarlar UYUŞMUYORSA KOPYALAMA (bkz. `_tasinabilir_mi`). Kopyalanan DB
            # hedefte okunamaz olur; DB açılışındaki karantina zarfı onu kenara alır ve cihaz
            # temiz bir DB ile çalışmaya devam eder — ama ESKİ KAYIT ERİŞİLEMEZ kalır.
            # (Eski yorum "kenara alma bile kurtarmaz" diyordu; 2026-08-14'te kurtarma zarfı
            # düzeltildikten sonra bu artık DOĞRU DEĞİL.)
            if ad in _GOC_SIFRELI and not _tasinabilir_mi(kaynak, eski, hedef):
                logging.getLogger(__name__).error(
                    "VERİ GÖÇÜ ATLANDI: %s ŞİFRELİ ve hedefin at-rest anahtarı FARKLI "
                    "(hedefin kendi anahtarı var, ezilmedi). Kopyalansaydı hedefte okunamaz "
                    "olur ve cihaz her açılışta kırılırdı. Kaynak eski konumda DURUYOR: %s",
                    ad,
                    kaynak,
                )
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

# TEK donanim-surumu kaynagi (M4/denetim 2026-09-03): eskiden system_router.py "HW-2025.1",
# live_state.py "HW-2026.1" derdi -> ayni /status uclari celisen deger donuyordu. Ikisi de
# artik BURADAN okur. ⚠️ Deger sahip tarafindan gercek donanim revizyonuyla teyit edilmeli.
HARDWARE_VERSION = "HW-2026.1"


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
