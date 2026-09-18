# Author: mertaygn, cglrgrkn
"""DEPO KÖKÜ SABİT DERİNLİKLE BULUNMAZ.

NE OLDU (2026-09-18, klasör düzeni F4 hazırlığı): kökü `Path(__file__).resolve().parents[1]`
ile bulan **13 ayrı yer** ölçüldü (`servers/` `services/` `database/` `utils/` `controllers/`).
Hepsi modülün depo kökünden TAM İKİ seviye aşağıda olduğunu varsayıyordu. Monorepo taşıması
(`utils/` → `apps/backend/pemf_backend/utils/`) bu varsayımı iki seviye kaydırır.

⚠️ KIRILMA SESSİZDİR. Çağıran yerlerin hepsi ADAY LİSTESİ kuruyor:

    roots.append(Path(__file__).resolve().parent.parent / "bin" / "cloudflared")

Yanlış aday `exists()` demez, sıradakine geçilir ve **hata verilmez**. Ölçülen etki alanı:
`bin/cloudflared` (uzaktan erişim ölür), `release_assets/ai_models` (640 MB model bulunamaz →
YENİDEN İNDİRME, metered hat), `data/cloud_mqtt_provision.json` (bulut sırrı), `VERSION` ve
`frontend_version.json` (sürüm raporu yanlışlanır), `config/config.json`, `bin/mosquitto`.

⚠️ 48 ÜRÜN SENARYOSU BUNU GÖREMEZ: onlar donmuş EXE'yi koşturur, orada kök `_MEIPASS`tir.
Kayan şey YALNIZ kaynak-ağacı dalıdır. Yani "senaryolar yeşil" bu sınıf için kanıt DEĞİLDİR.

ÇÖZÜM: tek kaynak `utils.path_utils.kaynak_kokunu_bul()` — kökü işaret dosyalarıyla YUKARI
YÜRÜYEREK bulur, derinlikten bağımsızdır. Bu kapı hem davranışı hem de yeniden elle çıpa
yazılmasını kilitler; böylece F3/F4/F5 taşımaları bu sınıfı bir daha üretemez.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest
from utils.path_utils import KOK_ISARETLERI, kaynak_kokunu_bul, packaged_resource_path

KOK = Path(__file__).resolve().parents[1]

#: Kapının taradığı ürün paketleri. ⚠️ F4 TAMAMLANDI 2026-09-18: bunlar artık
#: `apps/backend/` altında. `git ls-files` DİSK yolu ister; import adları (`utils` vb.)
#: değişmedi ama burada işe yaramaz — ikisi bu taşımadan sonra AYRIŞTI.
PAKETLER = (
    "apps/backend/servers",
    "apps/backend/services",
    "apps/backend/database",
    "apps/backend/utils",
    "apps/backend/controllers",
)

#: Modülün KENDİ dizinine bakan meşru kullanımlar — taşımada modülle birlikte giderler,
#: dolayısıyla derinlik varsayımı İÇERMEZLER.
MUAF = {
    "apps/backend/utils/pdf_report_generator.py",  # Path(__file__).parent / "assets" → modülün yanı
    "apps/backend/utils/path_utils.py",  # `kaynak_kokunu_bul` TANIMI burada
}
MUAF_SAYISI = 2

#: `__file__`den türetilip "bir üst dizin" için kullanılan değişken adları (üründe ölçüldü).
_DIZIN_DEGISKENLERI = {"current_dir", "_DIR", "HERE", "base_dir", "BASE_DIR"}


def _izlenen_moduller() -> list[str]:
    ch = subprocess.run(["git", "ls-files", *PAKETLER], cwd=KOK, capture_output=True, text=True, timeout=120)
    if ch.returncode != 0:
        pytest.skip("git deposu değil")
    return [a for a in ch.stdout.splitlines() if a.endswith(".py") and a not in MUAF]


def kok_capasi_satirlari(kaynak: str) -> list[int]:
    """`__file__`ten SABİT DERİNLİKLE yukarı çıkan ifadelerin satırları.

    AST ile ölçülür; metin araması yorumları ve docstring'leri ihlal sayardı — bu deponun
    tekrar eden tuzağı (bkz. `tests/test_tasinmis_dizin_calisan_kodda_YOK.py`).
    `.parent` TEK başına muaftır: o modülün kendi dizinidir, taşımada birlikte gider.
    """
    try:
        agac = ast.parse(kaynak)
    except SyntaxError:
        return []

    def _file_temelli(d: ast.AST) -> bool:
        for alt in ast.walk(d):
            if isinstance(alt, ast.Name) and alt.id == "__file__":
                return True
        return False

    def _dirname_zinciri(d: ast.AST) -> bool:
        """`os.path.dirname(os.path.dirname(x))` ya da `os.path.dirname(<baska_dizin_degiskeni>)`.

        ⚠️ BU KAPININ KOR NOKTASIYDI (2026-09-18'de ölçüldü). Kapı yalnız `pathlib` biçimini
        (`parents[N]`, `.parent.parent`) arıyordu. `servers/ai_router.py` kökü
        `os.path.dirname(current_dir)` ile buluyordu ve F4 taşımasında SESSİZCE `apps/backend`i
        gösterdi: `ai_hub/` depo kökünde olduğu için FGS bantları yüklenemedi, fonksiyon hata
        ATMADAN boş dict döndü ve panel kayboldu. Aynı hata iki dosyada daha vardı.
        """
        if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "dirname"):
            return False
        if not d.args:
            return False
        ic = d.args[0]
        # dirname(dirname(...)) -> iki kat yukari = kok varsayimi
        if isinstance(ic, ast.Call) and isinstance(ic.func, ast.Attribute) and ic.func.attr == "dirname":
            return True
        # dirname(current_dir) gibi: argüman `__file__`den türetilmiş bir DİZİN değişkeni
        return isinstance(ic, ast.Name) and ic.id in _DIZIN_DEGISKENLERI

    bulgu: list[int] = []
    for d in ast.walk(agac):
        if _dirname_zinciri(d):
            bulgu.append(d.lineno)
        # parents[N]  (N >= 1)
        if isinstance(d, ast.Subscript) and isinstance(d.value, ast.Attribute) and d.value.attr == "parents":
            if _file_temelli(d.value):
                bulgu.append(d.lineno)
        # .parent.parent (iki VEYA daha fazla) — tek `.parent` meşru
        if isinstance(d, ast.Attribute) and d.attr == "parent":
            ic = d.value
            if isinstance(ic, ast.Attribute) and ic.attr == "parent" and _file_temelli(ic):
                bulgu.append(d.lineno)
    return sorted(set(bulgu))


def test_KRITIK_urun_modulleri_kok_capasini_ELLE_YAZMIYOR():
    """🔴 ASIL REGRESYON: elle çıpa = taşımada SESSİZ yanlış yol."""
    moduller = _izlenen_moduller()
    assert len(moduller) > 50, f"tarama çok dar ({len(moduller)}) — kapı boş dönüyor olabilir"

    bulgu = {}
    for rel in moduller:
        satirlar = kok_capasi_satirlari((KOK / rel).read_text(encoding="utf-8", errors="replace"))
        if satirlar:
            bulgu[rel] = satirlar

    assert not bulgu, (
        "Elle yazılmış depo-kökü çıpası var (SABİT DERİNLİK): "
        + "; ".join(f"{k}:{v}" for k, v in sorted(bulgu.items()))
        + ". Taşımada sessizce yanlış dizine düşer. Yerine "
        "`from utils.path_utils import kaynak_kokunu_bul` kullanın."
    )


def test_KRITIK_cagrilar_CAGIRANIN_dosyasini_gecirir():
    """🔴 `kaynak_kokunu_bul()` argümansız çağrılmaz — argümansız hâli TEST DİKİŞİNİ KOPARIR.

    NE OLDU (2026-09-18, ilk denemede): çıpalar `kaynak_kokunu_bul()` biçiminde bağlandı.
    Argümansızken fonksiyon KENDİ `__file__`ını kullanır, yani kök artık ÇAĞIRANA bağlı
    değildir. `tests/test_cekirdek_model_cozumu.py` tam da bu dikişten izole oluyordu
    (`monkeypatch.setattr(model_downloader, "__file__", ...)`) ve **5 test kırmızı döndü**.

    ⚠️ Testin kendi docstring'i neden önemli olduğunu yazıyor: bu makinede
    `release_assets/ai_models` GERÇEKTEN dolu. İzolasyon koparsa test modeli oradan bulur ve
    "çekirdek paketten çözülüyor" sanılır — yani kanıtlamak istediğinin TAM TERSİNİ "ispatlar".
    Sessiz yeşil üreten bir kırılma; bu yüzden sözleşme kapıyla kilitlendi.
    """
    ch = subprocess.run(["git", "ls-files", *PAKETLER], cwd=KOK, capture_output=True, text=True, timeout=120)
    if ch.returncode != 0:
        pytest.skip("git deposu değil")

    cagri = re.compile(r"kaynak_kokunu_bul\(\s*\)")
    kusurlu = {}
    toplam = 0
    for rel in ch.stdout.splitlines():
        if not rel.endswith(".py"):
            continue
        metin = (KOK / rel).read_text(encoding="utf-8", errors="replace")
        toplam += metin.count("kaynak_kokunu_bul(")
        satirlar = [no for no, s in enumerate(metin.splitlines(), 1) if cagri.search(s)]
        if satirlar:
            kusurlu[rel] = satirlar

    assert toplam >= 10, f"çağrı sayısı beklenenden az ({toplam}) — kapı boş dönüyor olabilir"
    assert not kusurlu, (
        "`kaynak_kokunu_bul()` ARGÜMANSIZ çağrılmış: "
        + "; ".join(f"{k}:{v}" for k, v in sorted(kusurlu.items()))
        + ". `kaynak_kokunu_bul(__file__)` yazın — yoksa kök çağırana bağlı olmaz ve "
        "testlerin izolasyon dikişi (modül `__file__`ını yamalamak) KOPAR."
    )


def test_KRITIK_kok_gercekten_depo_koku():
    """Bulunan kök ÜRÜNÜN kökü olmalı — işaretlerin hepsi orada."""
    kok = kaynak_kokunu_bul()
    assert kok == KOK, f"kök yanlış: {kok} (beklenen {KOK})"
    for ad in KOK_ISARETLERI:
        assert (kok / ad).exists(), f"kök işareti yok: {ad}"


def test_KRITIK_DERINLIKTEN_BAGIMSIZ():
    """🔴 F4'ÜN ASIL KAPISI: modül ne kadar derine taşınırsa taşınsın kök AYNI kalmalı.

    Sabit derinliğe dönen bir yama tam burada kırmızı döner.
    """
    for derinlik in range(1, 7):
        sahte = KOK.joinpath(*["kat"] * derinlik) / "modul.py"
        assert kaynak_kokunu_bul(sahte) == KOK, f"{derinlik} seviye derinde kök kaydı"

    # F4'ün gerçek hedef yolu — `utils/` iki seviye derine iner:
    # F4'ün GERÇEKLEŞEN hedef yolu (2026-09-18'de taşındı). Çıpa GERÇEK yola pinli:
    # hayalî bir yol kullanılsaydı taşıma geri alınsa bile test yeşil kalırdı.
    f4_yolu = KOK / "apps" / "backend" / "utils" / "path_utils.py"
    assert f4_yolu.is_file(), "F4 taşıması geri alınmış — çıpa artık ürünü ölçmüyor"
    assert kaynak_kokunu_bul(f4_yolu) == KOK, "F4 taşımasından sonra kök KAYIYOR"


def test_KRITIK_DONMUS_EXEDE_YUKARI_YURUMEZ(monkeypatch, tmp_path):
    """🔴 KOD KORUMASINI KIRAN HATA (2026-09-18'de ölçüldü, build kapısı yakaladı).

    NE OLDU: `kaynak_kokunu_bul` donmuş EXE'de de işaret arıyordu. Paketin içinde `VERSION`
    VAR ama `pyproject.toml`/`versions.json` YOK → yürüyüş paketi geçip **depo köküne** çıktı.
    Çağıran (`servers/ai_router.py`) o kökü `sys.path`e ekliyor ve depo kökünde `ai_hub/`
    **düz kaynak** olarak durduğu için paketlenmiş `.pyd`/`.pyenc` GÖLGELENDİ.

    Sonuç: kod koruması SESSİZCE etkisiz. Beş build kapısı YEŞİL kaldı (PYZ temiz, sevk
    ağacı temiz, 67/67 modül derlendi) — yalnız **çalışma-anı** kapısı gördü:
    "16/16 modül .pyd/.pyenc DIŞINDAN yükleniyor".

    Donmuş çalışırken tek doğru kök `_MEIPASS`tır; arama YAPILMAZ.
    """
    sahte_paket = tmp_path / "_internal"
    sahte_paket.mkdir()
    # Paketin ÜSTÜNDE tam bir "depo kökü" kur — yürüyüş olsaydı BURAYI bulurdu.
    for ad in KOK_ISARETLERI:
        (tmp_path / ad).write_text("x", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(sahte_paket), raising=False)

    bulunan = kaynak_kokunu_bul(str(sahte_paket / "servers" / "ai_router.py"))
    assert bulunan == sahte_paket, (
        f"donmuş EXE'de kök {bulunan} bulundu — paketin DIŞINA çıkıldı. Bu, depo kökündeki "
        "düz `ai_hub/` kaynağının paketlenmiş .pyd'yi gölgelemesine ve kod korumasının "
        "SESSİZCE etkisiz kalmasına yol açar."
    )
    assert bulunan != tmp_path, "yürüyüş sahte depo köküne ulaştı — donmuş dal devre dışı"


def test_KARSIT_KANIT_isaretler_kokU_TEK_BASINA_belirliyor():
    """İşaret kümesi kökü BENZERSİZ göstermeli.

    Tek işaret (ör. yalnız `VERSION`) yetmezdi: bir alt dizinde de `VERSION` bulunursa yukarı
    yürüyüş ORADA durur ve kök sessizce yanlış olur. Üç işaretin birlikte bulunduğu başka bir
    izlenen dizin OLMAMALI.
    """
    assert len(KOK_ISARETLERI) >= 3, f"işaret kümesi daraltılmış: {KOK_ISARETLERI}"

    ch = subprocess.run(["git", "ls-files"], cwd=KOK, capture_output=True, text=True, timeout=120)
    dizinler = {Path(a).parent for a in ch.stdout.splitlines()} - {Path(".")}
    carpisan = [str(d) for d in dizinler if all((KOK / d / ad).exists() for ad in KOK_ISARETLERI)]
    assert not carpisan, f"bu dizinler de kök gibi görünüyor, yürüyüş erken durur: {carpisan}"


def test_KARSIT_KANIT_carpisan_dizin_yuruyusu_ERKEN_DURDURUR(tmp_path):
    """Yukarıdaki taramanın BOŞ GEÇMEDİĞİNİ kanıtlar.

    ⚠️ Bu ayrı bir test olmak ZORUNDA: depoda şu an çarpışan dizin YOK, yani o tarama hiçbir
    şey bulmuyor ve tek başına "geçiyor" olması hiçbir şey ölçmez (2026-09-18'de ölçüldü —
    mutasyon o testi kırmızı yapmıştı ama SAYI kontrolü yüzünden, tarama yüzünden değil).
    Burada gerçek bir çarpışma KURULUR ve yürüyüşün orada durduğu GÖSTERİLİR; işaret kümesi
    daraltılırsa (ör. yalnız `VERSION`) çarpışma ihtimali gerçek dosya sisteminde artar.
    """
    sahte_kok = tmp_path / "depo"
    ic = sahte_kok / "alt" / "paket"
    ic.mkdir(parents=True)
    for ad in KOK_ISARETLERI:
        (sahte_kok / ad).write_text("x", encoding="utf-8")

    # Çarpışma yokken: gerçek kök bulunur.
    assert kaynak_kokunu_bul(ic / "modul.py") == sahte_kok

    # Alt dizin de TÜM işaretleri taşırsa yürüyüş ORADA durur — kök yanlışlanır.
    for ad in KOK_ISARETLERI:
        (ic / ad).write_text("x", encoding="utf-8")
    assert kaynak_kokunu_bul(ic / "modul.py") == ic, (
        "yürüyüş çarpışan dizinde durmuyor — tarama testinin koruduğu şey bu davranıştır"
    )


def test_KARSIT_KANIT_kapi_gercekten_yakaliyor():
    """Kapı boş geçmiyor: 2026-09-18'de kaldırılan gerçek satırlar YAKALANMALI."""
    for bozuk in (
        'roots.append(Path(__file__).resolve().parent.parent / "bin" / "cloudflared")',
        'dirs.append(Path(__file__).resolve().parents[1] / "bin" / "mosquitto")',
        "bases = [Path(__file__).resolve().parent.parent]",
        "dev_path = Path(__file__).parent.parent / relative_path",
        'for base in (x, Path(__file__).resolve().parents[1] / "VERSION"): pass',
        # ⚠️ `os.path` biçimi — kapının 2026-09-18'deki KÖR NOKTASI, üç dosyada vardı:
        "project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))",
        "project_root = os.path.dirname(current_dir)",
    ):
        assert kok_capasi_satirlari(bozuk), f"kapı KAÇIRIYOR: {bozuk}"


def test_KARSIT_KANIT_mesru_kullanim_YANLIS_KIRMIZI_vermez():
    """Modülün KENDİ dizini ve yorum/docstring ihlal DEĞİLDİR."""
    for temiz in (
        'logo_path = Path(__file__).parent / "assets" / "pemf_logo.png"',  # modülle taşınır
        '# eskiden Path(__file__).resolve().parents[1] kullanılıyordu',  # yorum
        '"""Kökü Path(__file__).parent.parent ile bulan 13 yer vardı."""',  # docstring
        'kok = kaynak_kokunu_bul()',
        'base = Path(sys._MEIPASS)',
        # Modülün KENDİ dizini — taşımada birlikte gider, derinlik varsayımı YOK:
        '_DIR = os.path.dirname(os.path.abspath(__file__))',
        'HERE = os.path.dirname(os.path.abspath(__file__))',
    ):
        assert not kok_capasi_satirlari(temiz), f"YANLIŞ KIRMIZI: {temiz}"


def test_KARSIT_KANIT_muafiyet_kapiyi_BOSALTMIYOR():
    """ "Kırmızıyı sustur" diye muafiyet listesini şişiren yamayı yakalar."""
    assert len(MUAF) == MUAF_SAYISI, f"muafiyet listesi değişmiş: {MUAF}"
    assert len(PAKETLER) == 5, f"taranan paket kümesi değişmiş: {PAKETLER}"
    assert all(a.startswith("apps/backend/") for a in PAKETLER), (
        f"paketler `apps/backend/` altında olmalı (F4 taşındı): {PAKETLER}"
    )


def test_packaged_resource_path_URUNDE_dogru_cozuyor():
    """Tek kaynak gerçekten çalışıyor: kaynak ağacında VERSION bulunabilmeli."""
    yol = Path(packaged_resource_path("VERSION"))
    assert yol.exists(), f"packaged_resource_path VERSION'ı bulamıyor: {yol}"
    assert yol.parent == KOK, f"kök yanlış: {yol.parent}"
    # Kaynak dalı sabit derinlik KULLANMAMALI (F4'te kayar) — kaynağı da ölç.
    kaynak = (KOK / "apps" / "backend" / "utils" / "path_utils.py").read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("def packaged_resource_path") :]
    govde = govde[: govde.index("\ndef ", 1)]
    assert not re.search(r"__file__[^\n]*parents\[", govde), (
        "packaged_resource_path kaynak dalı SABİT DERİNLİĞE dönmüş — F4 taşımasında kök kayar"
    )
