# Author: mertaygn, cglrgrkn
import os
import platform
import shutil
import sys
import uuid
from pathlib import Path

#: Depo kökünü BENZERSİZ biçimde işaretleyen dosyalar. Üçü BİRDEN aranır — tek dosya yetmez,
#: çünkü alt dizinlerde de `VERSION` bulunabilir ve kök yanlış yere düşerdi.
KOK_ISARETLERI = ("VERSION", "pyproject.toml", "versions.json")


def kaynak_kokunu_bul(baslangic=None):
    """Kaynak ağacında depo kökünü **derinlikten bağımsız** bulur.

    ⚠️ NEDEN VAR (2026-09-18): kökü `Path(__file__).resolve().parents[1]` ile bulan 13 ayrı yer
    vardı. Hepsi SABİT DERİNLİK varsayıyordu; monorepo taşımasında (`utils/` →
    `apps/backend/pemf_backend/utils/`) bu varsayım iki seviye kayar ve kök SESSİZCE yanlış
    dizine düşerdi. Sessiz, çünkü çağıran yerlerin hepsi aday listesi kuruyor
    (`roots.append(...)`) — yanlış aday bulunamaz, sıradakine geçilir ve hata VERİLMEZ.
    Etkisi ölçülebilir olurdu: `bin/cloudflared` (uzaktan erişim), `release_assets/ai_models`
    (640 MB'lık model — bulunamazsa YENİDEN İNDİRME), `data/cloud_mqtt_provision.json` (sır),
    `VERSION`/`frontend_version.json` bulunamazdı.

    ⚠️ Bu yol YALNIZ kaynak ağacı içindir. Donmuş EXE'de `_MEIPASS` kullanılır; işaret dosyaları
    pakete girmediği için burada arama YAPILMAZ (bkz. `packaged_resource_path`).
    """
    # ⚠️⚠️ DONMUS EXE'DE ASLA YUKARI YURUME (2026-09-18'de OLCULDU, kod korumasini KIRDI).
    # Paket icinde `VERSION` VAR ama `pyproject.toml`/`versions.json` YOK; yuruyus paketi
    # gecip DEPO KOKUNE cikiyor ve cagiran orayi `sys.path`e ekliyor. Depo kokunde `ai_hub/`
    # DUZ KAYNAK olarak duruyor -> paketlenmis `.pyd`/`.pyenc` GOLGELENIYOR ve kod korumasi
    # SESSIZCE ETKISIZ kaliyor. Build kapisi olctu: "16/16 modul .pyd/.pyenc DISINDAN
    # yukleniyor" (sevk edilen surumde oran 64/65 idi).
    # Donmus calisirken tek dogru kok `_MEIPASS`tir; arama YAPILMAZ.
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        return Path(meipass) if meipass else (Path(sys.executable).resolve().parent / "_internal")

    p = Path(baslangic or __file__).resolve()
    for aday in p.parents:
        if all((aday / ad).exists() for ad in KOK_ISARETLERI):
            return aday
    # İşaretler bulunamadıysa eski davranışa düş — hiçbir durumda bugünkünden kötü olmasın.
    return p.parents[1] if len(p.parents) > 1 else p.parent


def resource_path(relative_path):
    """EXE içindeki gömülü dosyaları bulur (Okuma amaçlı)"""
    try:
        base_path = Path(sys._MEIPASS)
    except Exception:
        base_path = kaynak_kokunu_bul(__file__)

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

#: D3I-O.1: eski kökten taşınan at-rest anahtarları (`pemf_secrets.json` → `auto`). `patient_fernet_key` hasta ALANLARINI (ad / sahip /
#: tür …) şifreler — DB SQLCipher olsun olmasın. Eskiden yalnız `sqlcipher_key` taşınıyor, hedef alan anahtarını YENİDEN üretiyor ve
#: göçen her hasta "[okunamayan kayıt]" görünüyordu (ölçüldü). Cihaz kimliği / eşleştirme / operatör sırları TAŞINMAZ.
_GOC_ANAHTARLARI = ("sqlcipher_key", "patient_fernet_key")

#: D3I-O.1: alanları `patient_fernet_key` ile şifreli DB'ler (bkz. `_tasinabilir_mi`).
_GOC_ALAN_SIFRELI = frozenset({"patients.db"})

#: D3I-A2.6: hedefte `<ad>`ın bir an YOK olduğu pencerelerin artık adları — at-rest göçü (`sqlcipher_util.migrate_to_encrypted_if_needed`:
#: `db → .plain.bak`, `.enc.tmp → db`; önceki yedek `.plain.bak.<zaman>`) ve karantina (`karantinaya_al`: `db → .acilamadi-<zaman>`).
#: Biri varsa hedef KULLANILMIŞ bir köktür → eski kökün BAYAT kopyası getirilmez. `-wal` / `-shm` BİLEREK yok: D3.37'nin yarım kalan
#: kendi WAL kopyası sonraki açılışta DB'yle eşlenir.
_HEDEF_GOC_ARTIKLARI = (".plain.bak", ".plain.bak.*", ".enc.tmp", ".acilamadi-*")


def _hedefte_goc_artigi(hedef: Path, ad: str) -> str | None:
    """Hedefte `ad` için göç / karantina artığının adı (yoksa None) — saf dizin listesi, sır / kripto katmanına dokunmaz."""
    import glob

    for ek in _HEDEF_GOC_ARTIKLARI:
        for p in sorted(hedef.glob(glob.escape(ad) + ek)):
            return p.name
    return None


def _sqlcipher_anahtarini_gocur(eski: Path, hedef: Path, ad: str = "sqlcipher_key") -> bool:
    """Eski kökteki at-rest anahtarını YENİ köke taşı — YALNIZ `ad` (`_GOC_ANAHTARLARI`: `sqlcipher_key`, `patient_fernet_key`).

    NEDEN GEREKLİ. Tıbbi kayıt göçü şifreli DB'leri taşıyamıyordu: anahtar
    `pemf_secrets.json`dadır ve o dosya BÜTÜN olarak göçemez (içinde `device_id`,
    `pairing_code`, `device_registry_secret` var — kopyalanırsa iki kurulum aynı cihaz
    kimliğini paylaşır). Sonuç: şifreli kurulumlarda eski veri eski konumda kalıyor ve
    vardiyalı klinikte ikinci hesapla açan veteriner hâlâ "BOŞ KLİNİK" görüyordu.

    Bu fonksiyon SADECE `auto.<ad>` alanını taşır; cihaz kimliği DOKUNULMAZ.

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
        anahtar = (src.get("auto") or {}).get(ad)
        if not anahtar:
            return False

        dst = {}
        if hedef_j.is_file():
            dst = json.loads(hedef_j.read_text(encoding="utf-8"))
        if (dst.get("auto") or {}).get(ad):
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
                "VERİ GÖÇÜ ATLANDI: eski kökteki at-rest anahtarı (%s) BU MAKİNEDE ÇÖZÜLEMİYOR "
                "(başka makine/kullanıcı bağlamında sarılmış olabilir). Kopyalansaydı hedefte "
                "'saklanmış ama çözülemeyen' bir sır kalır ve backend BİR DAHA HİÇ AÇILMAZDI. "
                "Eski veri kaynağında DURUYOR: %s",
                ad,
                kaynak_j,
            )
            return False

        dst.setdefault("auto", {})[ad] = anahtar
        dst.setdefault("_comment", src.get("_comment", ""))
        dst.setdefault("_version", src.get("_version", 1))
        # Atomik yaz: yarım kalan bir sır dosyası TÜM kurulumu açılamaz hâle getirir.
        gecici = hedef_j.with_suffix(".json.goc-tmp")
        gecici.write_text(json.dumps(dst, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(gecici, hedef_j)
        logging.getLogger(__name__).warning(
            "VERİ GÖÇÜ: at-rest anahtarı yeni köke taşındı (YALNIZ %s; cihaz "
            "kimliği taşınmadı) → eski şifreli tıbbi kayıt yeni kökte okunabilir.",
            ad,
        )
        return True
    except Exception:
        logging.getLogger(__name__).warning("VERİ GÖÇÜ: at-rest anahtarı taşınamadı (%s).", ad, exc_info=True)
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
      * D3I-O.1: hasta DB'si (`_GOC_ALAN_SIFRELI`) — SQLCipher olsun olmasın — kaynakta `patient_fernet_key` VARSA ancak hedefteki
        ham değer AYNIYSA taşınır; değilse kopya hedefte "[okunamayan kayıt]" gösterir (eski kayıt eski kökte okunur kalır).
    """
    if dosya.name in _GOC_ALAN_SIFRELI:
        f_eski = _ham_sqlcipher_anahtari(eski, "patient_fernet_key")
        if f_eski and f_eski != _ham_sqlcipher_anahtari(hedef, "patient_fernet_key"):
            return False
    if not _sifreli_mi(dosya):
        return True
    k_eski = _ham_sqlcipher_anahtari(eski)
    k_hedef = _ham_sqlcipher_anahtari(hedef)
    return bool(k_eski) and k_eski == k_hedef


def _ham_sqlcipher_anahtari(kok: Path, ad: str = "sqlcipher_key") -> str:
    """`pemf_secrets.json` içindeki HAM (DPAPI-sarılı) `ad` (varsayılan `sqlcipher_key`) — çözmeden.

    SecretsManager KULLANILMAZ: o `get_app_data_directory`ye geri döner ve özyineleme kurar
    (bkz. `_tasinabilir_mi`). Karşılaştırma için ham değer zaten yeterli."""
    import json

    try:
        p = kok / _SIR_DOSYASI
        if not p.is_file():
            return ""
        return str((json.loads(p.read_text(encoding="utf-8")).get("auto") or {}).get(ad) or "")
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


#: D3.37 · Y10 (sahip): bu süreçte DOĞRULANAMAYAN veri göçü (hedef DB yolu → neden). DB kurucuları bu dosyayı AÇMAZ — boş DB kurup
#: "boş klinik" göstermek yerine backend kısıtlı kipte (Y9) açılır, neden `/api/health`e gider ("göç bekliyor"); kaynak eski kökte
#: DEĞİŞMEDEN durur, sonraki açılışta göç yeniden denenir.
_GOC_ENGELI: dict[str, str] = {}


def _goc_anahtari(yol) -> str:
    return os.path.normcase(os.path.abspath(str(yol)))


def goc_engeli(db_yolu) -> str | None:
    """Bu DB dosyasının göçü bu süreçte doğrulanamadıysa nedeni (DB kurucuları açmadan önce sorar); yoksa None."""
    return _GOC_ENGELI.get(_goc_anahtari(db_yolu))


def goc_engelini_denetle(db_yolu) -> None:
    """D3.37 · Y10: göçü bu süreçte doğrulanamayan DB AÇILMAZ — `GocBekliyorHatasi` (açılış: DB'siz kısıtlı kip + "göç bekliyor")."""
    sebep = goc_engeli(db_yolu)
    if sebep:
        from database.sqlcipher_util import GocBekliyorHatasi

        raise GocBekliyorHatasi(
            f"Veri gocu dogrulanamadi ({sebep}); eski kok DEGISTIRILMEDI, sonraki acilista yeniden denenir."
        )


def goc_engelini_yeniden_dene(db_yolu) -> bool:
    """D3I-A2.3 · Y61: engelli DB'nin göçünü (YALNIZ o dosya, D3.37 · Y10 kurallarıyla) yeniden dener — Y43 / Y61 arka plan yeniden
    açması (`acilista_acilamayani_yeniden_ac`, olay döngüsü DIŞI) kurucudan ÖNCE çağırır. Eskiden engel süreç ömrü boyunca kalıyordu:
    geçici neden (AV kilidi / anlık disk dolu / salt-okur) kalksa da DB yalnız yeniden başlatmayla açılıyordu.

    `_GOC_YAPILDI` ("süreç başına bir kez") sözleşmesi bozulmaz: anahtar göçü ve tüm liste YENİDEN koşmaz; yalnız hedefte İZİ OLMAYAN
    (engel = kopya yerleşmedi, DB hiç açılmadı → karantina olamaz) dosya denenir; sır / kripto katmanına dokunulmaz. Döner: engel YOK mu."""
    anahtar = _goc_anahtari(db_yolu)
    onceki = _GOC_ENGELI.get(anahtar)
    if not onceki:
        return True
    varis = Path(db_yolu)
    eski_kok = os.getenv("APPDATA")
    if not eski_kok or varis.exists() or not (Path(eski_kok) / "PEMF_GUI" / varis.name).is_file():
        return False  # kaynak yok / hedefte bir şey belirdi → engel KALIR (boş DB kurulmaz)
    _GOC_ENGELI.pop(anahtar, None)
    try:
        _dosyalari_gocur(Path(eski_kok) / "PEMF_GUI", varis.parent, (varis.name,))
    except Exception as e:  # noqa: BLE001 — yeniden deneme hatası engeli GERİ KOYAR (DB açılmaz), açılışı düşürmez
        _GOC_ENGELI.setdefault(anahtar, f"{type(e).__name__}: {e}")
        import logging

        logging.getLogger(__name__).warning("VERİ GÖÇÜ yeniden denenemedi: %s", varis, exc_info=True)
    if not varis.exists():
        # D3I çapraz (C1): göç dosyayı ATLADIYSA (kaynak o an okunamaz → "şifreli" sayılır → anahtarsız kurulumda taşınamaz; artık)
        # kopya yerleşmedi → engel GERİ konur. Eskiden True dönüyordu → kurucu BOŞ DB kuruyor, göç bir daha hiç denenmiyordu.
        _GOC_ENGELI.setdefault(anahtar, onceki)
    return anahtar not in _GOC_ENGELI


def _sha256_dosya(yol: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for parca in iter(lambda: f.read(1 << 20), b""):
            h.update(parca)
    return h.hexdigest()


def _kopyala_dogrula(kaynak: Path, varis: Path) -> str | None:
    """D3.37 · Y10: KOPYALA (geçici ad) → SHA-256 ile DOĞRULA → yerleştir. Uyuşmazlık / hata: hedefte İZ KALMAZ, neden döner.
    Kaynak SİLİNMEZ ve DEĞİŞTİRİLMEZ (yalnız okunur)."""
    gecici = varis.with_name(varis.name + ".goc.part")
    try:
        shutil.copy2(kaynak, gecici)
        if _sha256_dosya(gecici) != _sha256_dosya(kaynak):
            raise OSError("kopya kaynakla ayni degil (SHA-256)")
        os.replace(gecici, varis)
        return None
    except Exception as e:  # noqa: BLE001 — her hata göçü durdurur, açılışı DEĞİL
        try:
            gecici.unlink()
        except OSError:
            pass
        return f"{type(e).__name__}: {e}"


def _dosyalari_gocur(eski: Path, hedef: Path, adlar) -> None:
    """`adlar`daki DB dosyalarını eski kökten hedefe göç ettir (D3.37 · Y10 kuralları). `_kullanicidan_makineye_gocur` (açılışta bir
    kez, tüm liste) ve D3I-A2.3 `goc_engelini_yeniden_dene` (Y43 / Y61 arka plan yeniden açması — YALNIZ engelli dosya) çağırır."""
    import logging

    for ad in adlar:
        kaynak, varis = eski / ad, hedef / ad
        if not kaynak.is_file() or varis.exists():
            continue
        # D3I-A2.6: hedefte bu DB'nin yarım göç / karantina artığı varsa eski kökün BAYAT kopyası GETİRİLMEZ — `initialize_database`
        # → `_yarim_goc_toparla` güncel veriyi geri koyar (eskiden kopya önce yerleşiyor, toparlama `db` VAR görüp duruyordu).
        artik = _hedefte_goc_artigi(hedef, ad)
        if artik:
            logging.getLogger(__name__).warning(
                "VERİ GÖÇÜ ATLANDI: %s hedefte YOK ama hedef kullanılmış (artık: %s) — eski kökün bayat kopyası getirilmedi "
                "(yarım göç toparlanır). Eski kök DEĞİŞMEDİ: %s",
                ad,
                artik,
                kaynak,
            )
            continue
        # ⚠️ Ham anahtarlar UYUŞMUYORSA KOPYALAMA (bkz. `_tasinabilir_mi`). Kopyalanan DB
        # hedefte okunamaz olur; DB açılışındaki karantina zarfı onu kenara alır ve cihaz
        # temiz bir DB ile çalışmaya devam eder — ama ESKİ KAYIT ERİŞİLEMEZ kalır.
        # (Eski yorum "kenara alma bile kurtarmaz" diyordu; 2026-08-14'te kurtarma zarfı
        # düzeltildikten sonra bu artık DOĞRU DEĞİL.)
        if ad in _GOC_SIFRELI and not _tasinabilir_mi(kaynak, eski, hedef):
            logging.getLogger(__name__).error(
                "VERİ GÖÇÜ ATLANDI: %s ŞİFRELİ ve hedefin at-rest / alan anahtarı FARKLI "
                "(hedefin kendi anahtarı var, ezilmedi). Kopyalansaydı hedefte okunamaz "
                "olur ve cihaz her açılışta kırılırdı. Kaynak eski konumda DURUYOR: %s",
                ad,
                kaynak,
            )
            continue
        # D3.37 · Y10: KOPYALA → SHA-256 ile DOĞRULA → kaynak SİLİNMEZ. WAL ÖNCE taşınır (kaynakta henüz DB'ye işlenmemiş
        # kayıtlar oradadır; eskiden yalnız .db kopyalanıyor, son işlemler kayboluyordu); DB yerleşmezse kopyalanan WAL da
        # geri alınır (tek başına kalırsa yeni / boş DB'ye uygulanırdı). `-shm` taşınmaz — SQLite onu WAL'dan yeniden kurar.
        wal_k, wal_v = eski / (ad + "-wal"), hedef / (ad + "-wal")
        wal_tasindi = False
        sebep = None
        if wal_k.is_file() and not wal_v.exists():
            sebep = _kopyala_dogrula(wal_k, wal_v)
            wal_tasindi = sebep is None
        if sebep is None:
            sebep = _kopyala_dogrula(kaynak, varis)
            if sebep is not None and wal_tasindi:
                try:
                    wal_v.unlink()
                except OSError:
                    logging.getLogger(__name__).warning(
                        "VERİ GÖÇÜ: DB yerleşmedi, kopyalanan WAL geri alınamadı: %s (DB açılmaz — göç engeli)",
                        wal_v,
                        exc_info=True,
                    )
        if sebep is None:
            logging.getLogger(__name__).warning(
                "VERİ GÖÇÜ: %s eski kökten kopyalandı ve SHA-256 ile doğrulandı (kaynak SİLİNMEDİ: %s).", ad, kaynak
            )
        else:
            _GOC_ENGELI[_goc_anahtari(varis)] = sebep
            logging.getLogger(__name__).error(
                "VERİ GÖÇÜ DOĞRULANAMADI: %s (%s) — hedefe YERLEŞTİRİLMEDİ, eski kök DEĞİŞMEDİ (%s). Bu açılışta bu DB "
                "AÇILMAZ (kısıtlı kip: ACİL DURDUR ve STOP çalışır); sonraki açılışta yeniden denenir.",
                ad,
                sebep,
                kaynak,
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
        # ⚠️ SIRA: anahtar ÖNCE taşınır. Aksi hâlde aşağıdaki `_tasinabilir_mi`
        # kontrolü şifreli DB'leri reddeder ve şifreli kurulumlarda göç HİÇ çalışmaz
        # (vardiyalı klinikte "boş klinik" devam ederdi). Anahtar yalnız hedefte HİÇ yoksa
        # taşınır; varsa dokunulmaz. D3I-O.1: hasta alanlarının anahtarı (`patient_fernet_key`) da.
        for _ad in _GOC_ANAHTARLARI:
            _sqlcipher_anahtarini_gocur(eski, hedef, _ad)

        _dosyalari_gocur(eski, hedef, _GOC_DOSYALARI)
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


# ⚠️ Y118 (sahip kararı · S-B2B2.3): veri klasörünün (`PEMF_DATA_DIR` / `%APPDATA%`) AĞ PAYLAŞIMINDA olması DESTEKLENMEZ — SQLite'ın
# dosya kilitleri SMB / ağ sürücüsünde güvenilir değil (eşzamanlı yazımda veritabanı bozulabilir). Açılışta günlük + arayüz uyarısı
# (`backend_service._veri_koku_ag_uyarisi`, `/api/health` `veriKokuAgda`); veri kökü DEĞİŞTİRİLMEZ, açılış DURMAZ (B2B2-3'ün UNC
# düzeltmesi kalır). Kapı: tests/test_veri_koku_AG_PAYLASIMI_uyarisi_Y118.py
_DRIVE_REMOTE = 4  # GetDriveTypeW: ağ (eşlenmiş) sürücü


def _surucu_turu(kok: str) -> int:
    """`kok` (ör. `Z:\\`) için Windows sürücü türü (`GetDriveTypeW`); Windows dışında / hata → 0 (bilinmiyor)."""
    if sys.platform != "win32":
        return 0
    try:
        import ctypes

        get_drive_type = ctypes.WinDLL("kernel32").GetDriveTypeW
        get_drive_type.argtypes = [ctypes.c_wchar_p]
        get_drive_type.restype = ctypes.c_uint
        return int(get_drive_type(kok))
    except Exception:
        return 0


def veri_koku_ag_paylasiminda_mi(yol) -> bool:
    """Y118: `yol` bir ağ paylaşımında mı — UNC (`\\\\sunucu\\pay\\…`, `\\\\?\\UNC\\…`) ya da eşlenmiş ağ sürücüsü (DRIVE_REMOTE).
    Uzun yol önekli YEREL yol (`\\\\?\\C:\\…`) ağ DEĞİLDİR. Dosya sistemine dokunmaz (UNC yol için ağa çıkılmaz)."""
    s = str(yol).replace("/", "\\")
    if s[:4] in ("\\\\?\\", "\\\\.\\"):
        govde = s[4:]
        if govde[:4].upper() == "UNC\\":
            return True
        s = govde
    elif s.startswith("\\\\"):
        return True
    surucu = s[:2]
    if len(surucu) == 2 and surucu[1] == ":" and surucu[0].isalpha():
        return _surucu_turu(surucu + "\\") == _DRIVE_REMOTE
    return False


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
    """Açılışta veri kökündeki iki DB için YARIM GÖÇ TOPARLAMASI; DB yollarını döndürür.

    ⚠️ D2.34 (B-9.1 · B-11.13) · Y26 (sahip kararı): "0 KM" ŞABLON KOPYALAYICISI KALDIRILDI. Eskiden `db` yoksa paketteki boş
    DÜZ-METİN şablon (`database/*_template.db`) veri köküne kopyalanıyordu — 09-13 veri kaybının 3. yolu: yarım göç toparlaması
    düşerse canlı DB'nin yerine BOŞ şablon konuyor, klinik geçmişi kaybolmuş görünüyordu (1.9.50 EXE'si şablonları taşıyor). Şema
    DB sınıflarınca (PatientDatabase / TreatmentHistoryDB) TAM kurulur; şablonlar depodan da silindi (spec'i yeniden yönlendirmek
    yolu uyandıramaz). Kapı: tests/test_sablon_KOPYALAYICI_YOK_sema_DB_siniflarindan_D234.py
    """
    app_data_dir = get_app_data_directory()
    generated_paths = {}

    for real_name in ("pemf_treatment_history.db", "patients.db"):
        target_db_path = app_data_dir / real_name

        # ⚠️ YARIM GÖÇ TOPARLAMASI — açılışta DB sınıflarından ÖNCE.
        # At-rest göçü `db → .plain.bak` ve `.enc.tmp → db` diye İKİ taşıma yapar. İkincisi
        # düşerse (Windows dosya kilidi / elektrik) diskte `db` YOK, veri `.plain.bak`ta kalır;
        # toparlanmazsa DB sınıfı BOŞ bir veritabanı kurar ve hasta geçmişi kaybolmuş görünür
        # (veri diskte durur ama kimse bakmaz). ÖLÇÜLDÜ (2026-09-13): toparlama üç yolda da
        # (`sqlcipher_util`, `treatment_history_db`, burası) çağrılmalı.
        # ⚠️ SESSİZ `pass` YASAK: ilk yazımda `except Exception: pass` vardı ve import frozen
        # EXE'de düşerse hiçbir iz bırakmıyordu — teşhis SAATLER aldı. Başarısızlık da,
        # başarı da LOGLANIR.
        import logging as _logging

        _log = _logging.getLogger(__name__)
        try:
            from database.sqlcipher_util import _yarim_goc_toparla

            if _yarim_goc_toparla(str(target_db_path), _log):
                _log.warning("Yarim kalmis goc toparlandi (acilista, DB acilmadan once): %s", target_db_path)
        except Exception:
            _log.exception(
                "Yarim-goc toparlamasi DENENEMEDI (%s) — veri .plain.bak dosyasinda kalabilir ve klinik gecmisi BOS gorunebilir.",
                target_db_path,
            )

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
        # Kaynaktan koşuyoruz. ⚠️ SABİT DERİNLİK KULLANMA: modül taşınırsa kök sessizce kayar
        # (bkz. `kaynak_kokunu_bul` gerekçesi). Kök, işaret dosyalarıyla aranır.
        base = kaynak_kokunu_bul(__file__)

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

    for base in (packaged_resource_path("VERSION"), kaynak_kokunu_bul(__file__) / "VERSION"):
        try:
            v = Path(base).read_text(encoding="utf-8").strip()
            if v:
                _APP_VERSION = v
                return v
        except Exception:
            pass
    for base in (
        packaged_resource_path("frontend_version.json"),
        kaynak_kokunu_bul(__file__) / "frontend_version.json",
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
