# -*- coding: utf-8 -*-
"""BETİKLER AÇILIYOR MU + DOCKER COPY YOLLARI GERÇEK Mİ — taşıma artığı `ModuleNotFoundError`.

🔴 ÖLÇÜLEN DURUM (2026-09-21, sahip isteği "bütün modülleri kontrol et"):
F4 taşıması (`apps/backend/`) import köklerini kaydırdı ve ÜÇ giriş betiği ÖLMÜŞTÜ —
açılışta `ModuleNotFoundError: No module named 'utils'`:

  · `scripts/stm_firmware_kimligi.py`  ⚠️ ürünün KENDİ hata mesajının operatöre önerdiği
    tanılama betiği (`utils/stm32_kimlik.uyum_denetle`: *"Dogrulama: python
    scripts/stm_firmware_kimligi.py"*) — firmware uyumsuzluğunda operatör ÇALIŞMAYAN bir
    komuta yönlendiriliyordu
  · `build_tools/source_crypto.py` · `build_tools/encrypt_sources.py` (kod şifreleme zinciri)

Ve `docker/Dockerfile.ai` altı satırda `COPY utils/...` diyordu; `utils/` artık kökte değil
→ **GPU AI imajı hiç derlenmiyordu** (build context `..`, bkz. `docker-compose.ai.yml`).

⚠️ Aynı sınıf bu depoda daha önce DÖRT kez ısırdı: `tools/e2e_*.py` (2 gün ölü) ·
   beş-biçimli dizin adı · betiğin kendi konumunu kırması · 54 kırık belge bağlantısı.
   Kod tarafında kapı vardı; BETİK + DOCKER yüzeyi ölçülmemişti.

⚠️ BU KAPI ÖNCE KÖRDÜ, MUTASYON YAKALADI: kaynakta `sys.path.insert` DİZESİNİ arıyordu.
   Döngüyü boşaltan mutasyon (`for _yol in ():`) dizeyi yerinde bıraktığı için kapı yeşil
   kaldı. Artık betiğin İMPORT ÖNSÖZÜ gerçekten koşturuluyor (`tests/onsoz_kosucu.py`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from utils.path_utils import kaynak_kokunu_bul

KOK = kaynak_kokunu_bul(__file__)
BETIK_DIZINLERI = ("scripts/", "tools/", "build_tools/")
KOSUCU = Path(__file__).with_name("onsoz_kosucu.py")

#: MUAFİYET — (dosya, modül): GEREKÇE. ⚠️ Kaba dizin muafiyeti YASAK; dosya+modül çifti.
MUAF: dict[tuple[str, str], str] = {}

#: F4'te fonksiyon İÇİNDE ölen dört betiğin ölen import'u — her koşumda GERÇEKTEN denetlenmeli.
#: D0Ö.19 ek-2 (tur 5): her BETIK_DIZINLERI dizininden en az bir çift + `ai_hub` — yalnız scripts/ ve
#: utils/database pinliyken ai_hub ya da tools/ taşınınca küme sessizce düşer, nöbetçi yeşil kalırdı.
NOBETCI_CIFTLER = {
    ("scripts/hasta_anahtari_emanet.py", "utils"),
    ("scripts/vault_emanet.py", "database"),
    ("scripts/xai_batch_rapor.py", "utils"),
    ("scripts/soak_http_ws.py", "utils"),
    ("scripts/xai_batch_rapor.py", "ai_hub"),
    ("tools/kurtarma.py", "utils"),
    ("build_tools/source_crypto.py", "utils"),
    # D0Ö.19 ek-3 (tur 6): `from utils import secrets_manager` — `ad` artık alt modül olarak aranıyor.
    ("scripts/hasta_anahtari_emanet.py", "utils.secrets_manager"),
    ("tools/kurtarma.py", "utils.secrets_manager"),
}
#: Betiklerin fonksiyon içinde import ettiği birinci-taraf kök adlar — kümede OLMALI (klasör taşıma nöbetçisi).
NOBETCI_KUME = {"utils", "database", "ai_hub", "scripts", "tools", "build_tools"}


def _takipli(desenler: list[str]) -> list[str]:
    ham = subprocess.run(["git", "ls-files", "-z"] + desenler, cwd=KOK, capture_output=True, timeout=180).stdout
    return [x.decode("utf-8") for x in ham.split(b"\x00") if x]


def _onsozleri_kostur(
    dosyalar: list[str], kok: Path | None = None, ic_importlar: bool = False
) -> list[tuple[str, str]]:
    """Alt-süreçte önsözleri koştur; [(dosya, hata)] döndür. `ic_importlar`: fonksiyon/try içi import'lar da."""
    return [tuple(x) for x in json.loads(_kosucu_satirlari(dosyalar, kok, ic_importlar)[-1])]


def _kosucu_satirlari(dosyalar: list[str], kok: Path | None, ic_importlar: bool) -> list[str]:
    r = subprocess.run(
        [sys.executable, str(KOSUCU), str(kok or KOK), json.dumps(dosyalar)]
        + (["--ic-importlar"] if ic_importlar else []),
        cwd=str(KOK),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert r.returncode == 0, f"önsöz koşucusu düştü:\n{r.stderr[-1500:]}"
    satirlar = [s for s in r.stdout.strip().splitlines() if s.strip()]
    assert satirlar, f"koşucu çıktı üretmedi:\n{r.stderr[-800:]}"
    return satirlar


# ──────────────────────────────────────────────────────────────────────────
# 0) KARŞIT-KANIT — koşucu GERÇEKTEN ölüyü ölü, sağlamı sağlam görüyor mu
# ──────────────────────────────────────────────────────────────────────────


def test_KARSIT_KANIT_kosucu_OLUYU_GORUYOR(tmp_path):
    """⚠️ Kapı bu koşucuya dayanıyor; önce ONU kanıtla — pozitif VE negatif."""
    (tmp_path / "olu_betik.py").write_text("import kesinlikle_olmayan_modul_xyz\n", encoding="utf-8")
    (tmp_path / "saglam_betik.py").write_text("import json\nX = 1\n", encoding="utf-8")

    sonuc = _onsozleri_kostur(["olu_betik.py", "saglam_betik.py"], kok=tmp_path)
    adlar = {x[0] for x in sonuc}
    assert "olu_betik.py" in adlar, "koşucu ÖLÜ betiği görmedi — kapı hiçbir şey ölçmüyor"
    assert "saglam_betik.py" not in adlar, "koşucu SAĞLAM betiği ölü sandı"


def test_KARSIT_KANIT_D5_55_kosucu_BILESIK_deyimdeki_olu_importu_GORUR(tmp_path):
    """D5.55 (B-10.103, M4b): son düz import'tan sonra `if True:` altındaki kırık import önsözdür — eskiden hiç koşmuyordu."""
    (tmp_path / "bilesik.py").write_text(
        "import json\nif True:\n    import kesinlikle_olmayan_modul_d555\n", encoding="utf-8"
    )
    sonuc = _onsozleri_kostur(["bilesik.py"], kok=tmp_path)
    assert [r for r, _ in sonuc] == ["bilesik.py"], f"bileşik deyimdeki ölü import GÖRÜLMEDİ: {sonuc}"


def test_KARSIT_KANIT_D5_55_ilk_taraf_import_hatasindan_dogan_SystemExit_RAPORLANIR(tmp_path):
    """D5.55 (B-10.111, M2b): `except ImportError: raise SystemExit(...)` birinci-taraf kırığını yutmaz; üçüncü-taraf eksikliği
    (paho deseni) raporlanmaz."""
    (tmp_path / "ilktaraf_d555").mkdir()
    (tmp_path / "ilktaraf_d555" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "ilk.py").write_text(
        "try:\n    from ilktaraf_d555 import olmayan\nexcept ImportError as exc:\n    raise SystemExit('eksik') from exc\n",
        encoding="utf-8",
    )
    (tmp_path / "ucuncu.py").write_text(
        "try:\n    import kesinlikle_olmayan_ucuncu_d555\nexcept ImportError as exc:\n    raise SystemExit('pip install x') from exc\n",
        encoding="utf-8",
    )
    sonuc = _onsozleri_kostur(["ilk.py", "ucuncu.py"], kok=tmp_path)
    assert [r for r, _ in sonuc] == ["ilk.py"], f"SystemExit ayrımı bozuk: {sonuc}"
    assert sonuc[0][1].startswith("SystemExit<-ImportError"), sonuc


def test_KARSIT_KANIT_kosucu_YOLU_DARALTIYOR(tmp_path):
    """`apps/backend` yolu BIRAKILIRSA ölü betik sağlam görünür — daraltma ŞART."""
    (tmp_path / "backend_isteyen.py").write_text("import utils.path_utils\n", encoding="utf-8")
    sonuc = _onsozleri_kostur(["backend_isteyen.py"], kok=tmp_path)
    assert sonuc and sonuc[0][0] == "backend_isteyen.py", (
        "test süreci `conftest` yüzünden `apps/backend`i taşıyor; koşucu yolu daraltmazsa "
        "ölü betikler ÇÖZÜLÜR görünür ve kapı hiçbir şey ölçmez."
    )


def _ic_importlari_kostur(dosyalar: list[str], kok: Path | None = None) -> list[tuple[str, str]]:
    from onsoz_kosucu import IC_IMPORT_ONEKI

    return [(r, h) for r, h in _onsozleri_kostur(dosyalar, kok, ic_importlar=True) if h.startswith(IC_IMPORT_ONEKI)]


def _ic_importlar_ve_denetlenenler(dosyalar: list[str]) -> tuple[list[tuple[str, str]], set[tuple[str, str]]]:
    """Bulgular + koşucunun GERÇEKTEN çözmeyi denediği (betik, ad) çiftleri (vakum ölçüsü)."""
    from onsoz_kosucu import DENETLENEN_ONEKI, IC_IMPORT_ONEKI

    satirlar = _kosucu_satirlari(dosyalar, None, ic_importlar=True)
    denetlenen = {
        tuple(x) for s in satirlar if s.startswith(DENETLENEN_ONEKI) for x in json.loads(s[len(DENETLENEN_ONEKI) :])
    }
    return [(r, h) for r, h in json.loads(satirlar[-1]) if h.startswith(IC_IMPORT_ONEKI)], denetlenen


def _muaf_mi(rel: str, hata: str) -> bool:
    return (rel, hata.split("'")[1] if "'" in hata else "") in MUAF


def test_KARSIT_KANIT_kosucu_FONKSIYON_ICI_olu_importu_GORUYOR(tmp_path):
    """D0Ö.19: fonksiyon/try İÇİNDEKİ birinci-taraf import — gövde koşturulmadan — görülmeli.

    Pozitif (yol kurmadan `apps/backend` paketini fonksiyonda import eden) VE negatif (yolu önsözde
    kuran; `try` içinde BİLEREK eksik üçüncü-taraf; aynı dizindeki kardeş modül) örneklerle.
    """
    (tmp_path / "apps" / "backend" / "arka").mkdir(parents=True)
    (tmp_path / "apps" / "backend" / "arka" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "kardes.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "olu_ic.py").write_text(
        "import json\n\n\ndef f():\n    try:\n        from arka import x\n    except Exception:\n        pass\n",
        encoding="utf-8",
    )
    (tmp_path / "saglam_ic.py").write_text(
        "import sys\nfrom pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent / 'apps' / 'backend'))\n"
        "import json\n\n\ndef f():\n    import arka\n    import kardes\n"
        "    try:\n        import kesinlikle_olmayan_ucuncu_taraf_xyz\n    except ImportError:\n        pass\n",
        encoding="utf-8",
    )
    # Yolu son import'tan SONRA kuran sağlam betik (xai_batch_rapor biçimi) — aradaki BAĞIMSIZ yan
    # etki deyimi KOŞTURULMAMALI (yalnız sys.path dilimi + dayandığı tanımlar koşar; make_base_zip dersi).
    (tmp_path / "saglam_sonra.py").write_text(
        "import sys\nfrom pathlib import Path\n\n"
        "KOK = Path(__file__).resolve().parent\n"
        "(KOK / 'YAN_ETKI_KOSTU.txt').write_text('x')\n"
        "if str(KOK / 'apps' / 'backend') not in sys.path:\n"
        "    sys.path.insert(0, str(KOK / 'apps' / 'backend'))\n\n\n"
        "def f():\n    import arka\n",
        encoding="utf-8",
    )
    sonuc = _ic_importlari_kostur(["olu_ic.py", "saglam_ic.py", "saglam_sonra.py"], kok=tmp_path)
    adlar = {r for r, _ in sonuc}
    assert "olu_ic.py" in adlar, f"koşucu fonksiyon/try içindeki ÖLÜ birinci-taraf import'u görmedi: {sonuc}"
    assert "saglam_ic.py" not in adlar, f"koşucu yolu önsözde kuran sağlam betiği ölü sandı: {sonuc}"
    assert "saglam_sonra.py" not in adlar, f"koşucu yolu son import'tan sonra kuran betiği ölü sandı: {sonuc}"
    assert not (tmp_path / "YAN_ETKI_KOSTU.txt").exists(), "koşucu yol dilimi DIŞINDAKİ üst-düzey deyimi KOŞTURDU"
    # Önsöz kapısı (bayraksız) bu ölüyü GÖREMEZ — yeni adımın gerekçesi.
    assert not _onsozleri_kostur(["olu_ic.py"], kok=tmp_path), "önsöz kapısı fonksiyon içini zaten görüyormuş"


#: `_depo_koku` biçimi (scripts/stm_firmware_kimligi.py) — işaret bulunamayınca RuntimeError.
_KOK_BULUNAMAZ = (
    "import sys\nfrom pathlib import Path\n\n\n"
    "def _depo_koku(bas):\n    raise RuntimeError('depo koku bulunamadi')\n\n\n"
)


def test_KARSIT_KANIT_kosucu_KOK_BULUNAMAYINCA_KIRMIZI(tmp_path):
    """D0Ö.19 ek: `_depo_koku` RuntimeError atan betik AÇILIŞTA ölür — kapı bunu YUTMAMALI.

    Önsözde yutulursa ondan sonraki import'lar hiç denenmez (yeşil); yol diliminde yutulursa
    fonksiyon içi import'lar başka bir yoldan (betik dizini) çözülüp yine yeşil kalabilir.
    """
    (tmp_path / "kardes.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "onsozde_olur.py").write_text(
        _KOK_BULUNAMAZ + "KOK = _depo_koku(Path(__file__))\nsys.path.insert(0, str(KOK))\nimport json\n",
        encoding="utf-8",
    )
    (tmp_path / "dilimde_olur.py").write_text(
        _KOK_BULUNAMAZ + "KOK = _depo_koku(Path(__file__))\nsys.path.insert(0, str(KOK))\n\n\n"
        "def f():\n    import kardes\n",
        encoding="utf-8",
    )
    onsoz = {r for r, _ in _onsozleri_kostur(["onsozde_olur.py"], kok=tmp_path)}
    assert "onsozde_olur.py" in onsoz, "önsözdeki `depo kökü bulunamadı` RuntimeError'ı YUTULDU"
    dilim = {r for r, _ in _ic_importlari_kostur(["dilimde_olur.py"], kok=tmp_path)}
    assert "dilimde_olur.py" in dilim, "yol dilimindeki `depo kökü bulunamadı` RuntimeError'ı YUTULDU"


def test_KARSIT_KANIT_kosucu_GOLGE_BAYAT_KOPYA_ve_AD_ALANI_KIRMIZI(tmp_path):
    """D0Ö.19 ek: çözüm deponun KANONİK konumuna (`kok/<ad>`, `kok/apps/backend/<ad>`) düşmeli.

    · depo DIŞI gölge (bu makinede gerçek: site-packages'taki ultralytics `tests`'i),
    · depo içinde BAYAT kopya (`scripts/arka/` — betik dizini yolda olduğu için önce o bulunur),
    · depoda DÜZENLİ paket olan adın ad-alanı (namespace) parçası (`kok/arka/` `__init__`siz)
    üçü de KIRMIZI olmalı. Kanonik çözüm (yolu doğru kuran betik) yeşil kalmalı.
    """
    kok = tmp_path / "depo"
    (kok / "apps" / "backend" / "arka").mkdir(parents=True)
    (kok / "apps" / "backend" / "arka" / "__init__.py").write_text("", encoding="utf-8")
    golge = tmp_path / "golge_site" / "arka"
    golge.mkdir(parents=True)
    (golge / "__init__.py").write_text("", encoding="utf-8")
    (kok / "golgeli.py").write_text(
        f"import sys\nsys.path.insert(0, {str(golge.parent)!r})\nimport json\n\n\ndef f():\n    import arka\n",
        encoding="utf-8",
    )
    (kok / "scripts" / "arka").mkdir(parents=True)
    (kok / "scripts" / "arka" / "__init__.py").write_text("", encoding="utf-8")
    (kok / "scripts" / "bayat.py").write_text("import json\n\n\ndef f():\n    import arka\n", encoding="utf-8")
    (kok / "arka").mkdir()
    (kok / "arka" / "parca.py").write_text("X = 1\n", encoding="utf-8")
    (kok / "ad_alani.py").write_text("import json\n\n\ndef f():\n    from arka import parca\n", encoding="utf-8")
    (kok / "kanonik.py").write_text(
        "import sys\nfrom pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent / 'apps' / 'backend'))\nimport json\n\n\n"
        "def f():\n    import arka\n",
        encoding="utf-8",
    )
    sonuc = _ic_importlari_kostur(["golgeli.py", "scripts/bayat.py", "ad_alani.py", "kanonik.py"], kok=kok)
    adlar = {r for r, _ in sonuc}
    assert "golgeli.py" in adlar, f"depo DIŞI gölge çözüm sayıldı: {sonuc}"
    assert "scripts/bayat.py" in adlar, f"depo içi BAYAT kopya çözüm sayıldı: {sonuc}"
    assert "ad_alani.py" in adlar, f"düzenli paketin ad-alanı parçası çözüm sayıldı: {sonuc}"
    assert "kanonik.py" not in adlar, f"kanonik konuma çözen sağlam betik ölü sayıldı: {sonuc}"


def test_KARSIT_KANIT_kosucu_UCUNCU_TARAF_RuntimeError_betik_KUSURU_sayilmaz(tmp_path):
    """D0Ö.19 ek-2 (tur 5): önsözdeki RuntimeError yalnız DEPO kodundan geliyorsa bulgudur (`_depo_koku`).
    Üçüncü-taraf içinden gelen (ör. tek süreçte modüller silinip C uzantısı yeniden import edilince) bir
    ortam/koşucu artefaktıdır — sıraya bağlı sahte KIRMIZI üretmemeli (önsöz kapısının konusu import)."""
    site = tmp_path / "site_disi"
    (site / "ucuncu_taraf_xyz").mkdir(parents=True)
    # D0Ö.19 ek-3 (tur 6): encoding AÇIK — koşucu UTF-8 okur; platform kodlamasıyla (cp1254) yazılan ASCII
    # olmayan TEMP yolu (repr kaçışlamaz) okunurken bozulur ve betik sahte KIRMIZI olurdu.
    (site / "ucuncu_taraf_xyz" / "__init__.py").write_text(
        "raise RuntimeError('yeniden import artefakti')\n", encoding="utf-8"
    )
    kok = tmp_path / "depo"
    kok.mkdir()
    (kok / "ucuncu_kullanan.py").write_text(
        f"import sys\nsys.path.insert(0, {str(site)!r})\nimport ucuncu_taraf_xyz\n", encoding="utf-8"
    )
    (kok / "kendi_kok_hatasi.py").write_text(
        _KOK_BULUNAMAZ + "KOK = _depo_koku(Path(__file__))\nsys.path.insert(0, str(KOK))\nimport json\n",
        encoding="utf-8",
    )
    adlar = {r for r, _ in _onsozleri_kostur(["ucuncu_kullanan.py", "kendi_kok_hatasi.py"], kok=kok)}
    assert "ucuncu_kullanan.py" not in adlar, "üçüncü-taraf içinden gelen RuntimeError betik kusuru sayıldı"
    assert "kendi_kok_hatasi.py" in adlar, "betiğin KENDİ RuntimeError'ı yutuldu"


def test_KARSIT_KANIT_kosucu_ALT_MODUL_HARFE_DUYARLI(tmp_path):
    """D0Ö.19 ek-2 (tur 5): import harfe DUYARLIDIR (Windows'ta da, PYTHONCASEOK yokken); `is_file()` NTFS'te
    duyarsız olduğu için harfi yanlış noktalı import Windows'ta YEŞİL kalıyordu (Linux CI yakalardı)."""
    arka = tmp_path / "apps" / "backend" / "arka"
    arka.mkdir(parents=True)
    (arka / "__init__.py").write_text("", encoding="utf-8")
    (arka / "Buyuk.py").write_text("X = 1\n", encoding="utf-8")
    onsoz = (
        "import sys\nfrom pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent / 'apps' / 'backend'))\nimport json\n\n\n"
    )
    (tmp_path / "harf_yanlis.py").write_text(onsoz + "def f():\n    import arka.buyuk\n", encoding="utf-8")
    (tmp_path / "harf_dogru.py").write_text(onsoz + "def f():\n    import arka.Buyuk\n", encoding="utf-8")
    adlar = {r for r, _ in _ic_importlari_kostur(["harf_yanlis.py", "harf_dogru.py"], kok=tmp_path)}
    assert "harf_yanlis.py" in adlar, "harfi yanlış alt modül (arka.buyuk ↔ Buyuk.py) çözülmüş sayıldı"
    assert "harf_dogru.py" not in adlar, "harfi doğru alt modül ölü sayıldı"


def test_KARSIT_KANIT_kosucu_ALT_MODUL_tasininca_KIRMIZI(tmp_path):
    """D0Ö.20 ek (tur 4): yalnız ÜST paket çözülüyordu — `utils.file_acl` taşınsa ya da silinse kapı
    YEŞİL kalırdı (`utils` hâlâ çözülüyor). Noktalı adın her parçası paket konumlarında aranır."""
    arka = tmp_path / "apps" / "backend" / "arka"
    (arka / "alt").mkdir(parents=True)
    (arka / "__init__.py").write_text("", encoding="utf-8")
    (arka / "var.py").write_text("X = 1\n", encoding="utf-8")
    (arka / "alt" / "__init__.py").write_text("", encoding="utf-8")
    (arka / "alt" / "derin.py").write_text("X = 1\n", encoding="utf-8")
    onsoz = (
        "import sys\nfrom pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent / 'apps' / 'backend'))\nimport json\n\n\n"
    )
    govdeler = {
        "tasinmis.py": "def f():\n    from arka.olmayan import x\n",
        "derin_tasinmis.py": "def f():\n    import arka.alt.yok\n",
        "modul_paket_degil.py": "def f():\n    from arka.var.ic import x\n",
        "sabit_dinamik.py": "import importlib\n\n\ndef f():\n    importlib.import_module('arka.yok_dinamik')\n",
        "saglam_alt.py": "def f():\n    from arka.var import X\n    import arka.alt.derin\n    from arka import var\n",
    }
    for ad, govde in govdeler.items():
        (tmp_path / ad).write_text(onsoz + govde, encoding="utf-8")
    sonuc = _ic_importlari_kostur(list(govdeler), kok=tmp_path)
    adlar = {r for r, _ in sonuc}
    olu = {"tasinmis.py", "derin_tasinmis.py", "modul_paket_degil.py", "sabit_dinamik.py"}
    assert olu <= adlar, f"taşınmış/olmayan ALT MODÜL görülmedi: {sorted(olu - adlar)} ({sonuc})"
    assert "saglam_alt.py" not in adlar, f"var olan alt modüller ölü sayıldı: {sonuc}"


def test_KARSIT_KANIT_kosucu_FROM_PAKET_import_ALT_MODUL_tasininca_KIRMIZI(tmp_path):
    """D0Ö.19 ek-3 (tur 6): `from paket import ad`daki `ad` hiç denetlenmiyordu — `utils/secrets_manager.py`
    taşınsa `from utils import secrets_manager` (emanet, kurtarma) YEŞİL kalırdı. `__init__`i ad BAĞLAMAYAN
    (yalnız docstring/yorum ya da hiç yok = ad-alanı) pakette `ad` YALNIZ alt modül olabilir → aranır.
    Karşıt: `__init__` bir şey bağlıyorsa `ad` öznitelik olabilir → karar VERİLMEZ (sahte KIRMIZI yok)."""
    arka = tmp_path / "apps" / "backend"
    (arka / "bos_paket" / "alt").mkdir(parents=True)
    (arka / "bos_paket" / "__init__.py").write_text('"""yalniz docstring"""\n# yorum\n', encoding="utf-8")
    (arka / "bos_paket" / "var_modul.py").write_text("X = 1\n", encoding="utf-8")
    (arka / "bos_paket" / "alt" / "__init__.py").write_text("", encoding="utf-8")
    (arka / "bos_paket" / "alt" / "derin.py").write_text("X = 1\n", encoding="utf-8")
    (arka / "adalani_paket").mkdir()
    (arka / "adalani_paket" / "var2.py").write_text("X = 1\n", encoding="utf-8")
    (arka / "dolu_paket").mkdir()
    (arka / "dolu_paket" / "__init__.py").write_text("OZNITELIK = 1\n", encoding="utf-8")
    (arka / "gelecek_paket").mkdir()
    (arka / "gelecek_paket" / "__init__.py").write_text("from __future__ import annotations\n", encoding="utf-8")
    # D0Ö.19 ek-4 (tur 7): BOM'lu (Notepad UTF-8) yalnız-docstring `__init__` — CPython import eder; karar düşmemeli.
    (arka / "bom_paket").mkdir()
    (arka / "bom_paket" / "__init__.py").write_text('"""bom"""\n', encoding="utf-8-sig")
    (arka / "bom_paket" / "var3.py").write_text("X = 1\n", encoding="utf-8")
    onsoz = (
        "import sys\nfrom pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent / 'apps' / 'backend'))\nimport json\n\n\n"
    )
    govdeler = {
        "from_tasinmis.py": "def f():\n    from bos_paket import secrets_yok as sm\n",
        "from_adalani_tasinmis.py": "def f():\n    from adalani_paket import yok2\n",
        "from_alt_paket_tasinmis.py": "def f():\n    from bos_paket.alt import yok3\n",
        "from_bom_tasinmis.py": "def f():\n    from bom_paket import yok4\n",
        "from_saglam.py": (
            "def f():\n    from bos_paket import var_modul as vm\n    from adalani_paket import var2\n"
            "    from bos_paket.alt import derin\n    from bos_paket import alt\n    from bom_paket import var3\n"
        ),
        "from_dolu_oznitelik.py": (
            "def f():\n    from dolu_paket import OZNITELIK\n    from dolu_paket import belki_modul\n"
            "    from gelecek_paket import annotations\n"
        ),
    }
    for ad, govde in govdeler.items():
        (tmp_path / ad).write_text(onsoz + govde, encoding="utf-8")
    sonuc = _ic_importlari_kostur(list(govdeler), kok=tmp_path)
    adlar = {r for r, _ in sonuc}
    olu = {"from_tasinmis.py", "from_adalani_tasinmis.py", "from_alt_paket_tasinmis.py", "from_bom_tasinmis.py"}
    assert olu <= adlar, f"`from paket import <taşınmış alt modül>` görülmedi: {sorted(olu - adlar)} ({sonuc})"
    assert any("'bos_paket.secrets_yok'" in h for r, h in sonuc if r == "from_tasinmis.py"), sonuc
    assert "from_saglam.py" not in adlar, f"var olan alt modüller ölü sayıldı: {sonuc}"
    assert "from_dolu_oznitelik.py" not in adlar, f"`__init__`i ad bağlayan pakette öznitelik ölü sayıldı: {sonuc}"


def test_KARSIT_KANIT_yol_dilimi_YALNIZ_yol_kurulumunu_kosturur(tmp_path):
    """D0Ö.19 ek (make_base_zip dersi): dilim, bileşik deyimdeki yan etkiyi ve `sys.path`ten SONRAKİ
    yeniden atamayı KOŞTURMAMALI; yolu yine de kurmalı (fonksiyon içi import çözülür)."""
    (tmp_path / "apps" / "backend" / "arka").mkdir(parents=True)
    (tmp_path / "apps" / "backend" / "arka" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "bilesik.py").write_text(
        "import sys\nfrom pathlib import Path\n\n"
        "KOK = Path(__file__).resolve().parent\n"
        "for _yol in (KOK / 'apps' / 'backend',):\n"
        "    (KOK / 'YAN_BILESIK.txt').write_text('x')\n"
        "    if str(_yol) not in sys.path:\n"
        "        sys.path.insert(0, str(_yol))\n"
        "KOK = (KOK / 'YAN_SONRADAN.txt').write_text('x')\n\n\n"
        "def f():\n    import arka\n",
        encoding="utf-8",
    )
    sonuc = _ic_importlari_kostur(["bilesik.py"], kok=tmp_path)
    assert not sonuc, f"dilim yolu kuramadı: {sonuc}"
    assert not (tmp_path / "YAN_BILESIK.txt").exists(), "dilim bileşik deyimdeki YAN ETKİYİ koşturdu"
    assert not (tmp_path / "YAN_SONRADAN.txt").exists(), "dilim `sys.path`ten SONRAKİ yeniden atamayı koşturdu"


def test_KRITIK_fonksiyon_ici_ilk_taraf_importlari_COZULUYOR():
    """D0Ö.19/20/21 (B-10.57 · B-10.32 · B-9.25 · B-9.27) — betikler F4'ten beri fonksiyon İÇİNDE ölüydü.

    `hasta_anahtari_emanet._sirlari_oku` (`utils`), `vault_emanet.tatbikat` (`database`),
    `xai_batch_rapor` ses kolu (`utils.ses_kalitesi`), `soak_http_ws._veri_koku` (`utils`):
    önsöz sağlam göründü, iş yapan fonksiyon ilk çağrıda `ModuleNotFoundError` verdi — çoğu
    `except` ile yutuldu (emanet ACL'siz yazıldı, soak yanlış kökü ölçtü, rapor exit 0).
    Tüm birinci-taraf import düğümleri betiğin KENDİ kurduğu `sys.path` ile, conftest yolları
    olmadan (alt süreç, daraltılmış yol) çözülmeli ve çözüm deponun KANONİK konumuna (kök ya da
    `apps/backend`) düşmeli.
    """
    from onsoz_kosucu import ilk_taraf_adlari

    # ⚠️ D0Ö.19 ek — VAKUM NÖBETÇİLERİ: birinci-taraf küme `apps/backend` yoluna bağlı; klasör taşınır
    # da koşucu güncellenmezse `utils`/`database` kümeden SESSİZCE düşer ve hiçbir fonksiyon içi
    # import denetlenmez (dosya sayısı yine >30). Hem kümeyi hem gerçekten denetlenen çiftleri ölç.
    kume = ilk_taraf_adlari(KOK)
    assert NOBETCI_KUME <= kume, (
        f"birinci-taraf kümede YOK: {sorted(NOBETCI_KUME - kume)} — klasör (apps/backend, ai_hub, tools…) taşındı mı?"
    )
    dosyalar = _takipli([f"{d}*.py" for d in BETIK_DIZINLERI])
    assert len(dosyalar) > 30, f"VAKUM: yalnız {len(dosyalar)} betik tarandı — tarama bozuk"
    bulgular, denetlenen = _ic_importlar_ve_denetlenenler(dosyalar)
    eksik = NOBETCI_CIFTLER - denetlenen
    assert not eksik, f"VAKUM: F4'te ölen şu (betik, ad) çiftleri DENETLENMEDİ: {sorted(eksik)}"
    olu = [(rel, hata) for rel, hata in bulgular if not _muaf_mi(rel, hata)]
    assert not olu, (
        "FONKSİYON/TRY İÇİNDE ÇÖZÜLEMEYEN BİRİNCİ-TARAF IMPORT:\n  "
        + "\n  ".join(f"{a} -> {b}" for a, b in olu)
        + "\n\nDüzeltme: betiğin önsözünde depo kökünü İŞARET DOSYASIYLA bulup kök + `apps/backend`i "
        "sys.path'e ekleyin (örnek: scripts/stm_firmware_kimligi.py `_depo_koku`)."
    )


# ──────────────────────────────────────────────────────────────────────────
# 1) BETİKLER — açılışta ImportError atmamalı (DAVRANIŞ)
# ──────────────────────────────────────────────────────────────────────────


def test_KRITIK_giris_betikleri_ACILISTA_patlamiyor():
    dosyalar = _takipli([f"{d}*.py" for d in BETIK_DIZINLERI])
    assert len(dosyalar) > 30, f"VAKUM: yalnız {len(dosyalar)} betik tarandı — tarama bozuk"
    olu = [(rel, hata) for rel, hata in _onsozleri_kostur(dosyalar) if not _muaf_mi(rel, hata)]
    assert not olu, (
        "AÇILIŞTA ÖLÜ BETİK:\n  "
        + "\n  ".join(f"{a} -> {b}" for a, b in olu)
        + "\n\nDüzeltme: betiğe depo kökü + `apps/backend` sys.path kurulumu ekleyin. "
        "⚠️ Kökü işaret dosyasıyla YUKARI arayın, sabit derinlikle (`parents[1]`) yazmayın."
    )


def test_KRITIK_D5_33_onsozde_YUTULAN_istisna_YOK():
    """D5.33 (B-10.221): koşucu önsözde import DIŞI istisnayı yutar (ortam / dosya hatası ayrı arıza) — ama yutma önsözün GERİ
    KALANINI koşturmaz, o betiğin sonraki import'ları ölçülmemiş olur. Tam listede yutulan istisna (tür, betik, satır) SIFIR olmalı.
    Ölçülen: üçüncü-taraf C uzantısının (cv2) betikler arası `sys.modules`tan atılıp yeniden yüklenmesi `kabin_marker_a4.py:24`'te
    AttributeError üretiyordu → `:26` (PIL) hiç denenmiyordu."""
    from onsoz_kosucu import YUTULAN_ONEKI

    dosyalar = _takipli([f"{d}*.py" for d in BETIK_DIZINLERI])
    assert len(dosyalar) > 30, f"VAKUM: yalnız {len(dosyalar)} betik"
    satirlar = _kosucu_satirlari(dosyalar, None, False)
    yutulan = [x for s in satirlar if s.startswith(YUTULAN_ONEKI) for x in json.loads(s[len(YUTULAN_ONEKI) :])]
    assert any(s.startswith(YUTULAN_ONEKI) for s in satirlar), "koşucu yutulan-istisna satırını basmadı (sayaç ölü)"
    assert not yutulan, "önsözde YUTULAN istisna (betiğin geri kalan import'ları ölçülmedi):\n  " + "\n  ".join(
        f"{r}:{n} {t}: {m}" for r, t, n, m in yutulan
    )


def test_KARSIT_KANIT_D5_33_kosucu_yutulani_SAYAR(tmp_path):
    """Sayaç ölü değil: önsözde import DIŞI hata (dosya yok) sayılır, satırıyla."""
    from onsoz_kosucu import YUTULAN_ONEKI

    (tmp_path / "yutan.py").write_text(
        "import json\nopen('kesinlikle_yok_d533.cfg').read()\nimport os\n", encoding="utf-8"
    )
    satirlar = _kosucu_satirlari(["yutan.py"], tmp_path, False)
    yutulan = [x for s in satirlar if s.startswith(YUTULAN_ONEKI) for x in json.loads(s[len(YUTULAN_ONEKI) :])]
    assert [(r, t, n) for r, t, n, _ in yutulan] == [("yutan.py", "FileNotFoundError", 2)], yutulan


@pytest.mark.parametrize(
    "rel,beklenen_import",
    [
        ("scripts/stm_firmware_kimligi.py", "utils.stm32_kimlik"),
        ("build_tools/source_crypto.py", "utils.source_crypto"),
        ("build_tools/encrypt_sources.py", "build_tools.source_crypto"),
    ],
)
def test_DUZELTILEN_uc_betik_YASIYOR(rel: str, beklenen_import: str):
    """2026-09-21'de canlandırılan üç betik ölmesin — ve doğru modülü import etsin."""
    metin = (KOK / rel).read_text(encoding="utf-8", errors="replace")
    assert beklenen_import in metin, f"{rel}: {beklenen_import!r} kaybolmuş — çıpa bayat"
    olu = _onsozleri_kostur([rel])
    assert not olu, f"{rel} yeniden ÖLDÜ: {olu[0][1]}"


# ──────────────────────────────────────────────────────────────────────────
# 2) DOCKER — COPY kaynakları GERÇEKTEN var mı (context compose'dan OKUNUR)
# ──────────────────────────────────────────────────────────────────────────


def _compose_contextleri() -> dict[str, Path]:
    """{dockerfile_mutlak: context_dizini} — compose'dan OKUNUR (YAML yapısı, compose-spec çözümü), tahmin edilmez.

    4B-2.14: eskiden satır ayrıştırıcıydı — `context` her `build:`'de sıfırlanmadığından `dockerfile:` `context:`'ten ÖNCE yazılınca
    önceki servisin bağlamıyla eşleniyordu; tırnak / satır sonu yorumu / kısa `build: <yol>` ayrışıyordu; YAML'ı bozuk dosyayı sessizce
    "çözüyordu". Bozuk YAML artık istisna verir (fail-closed).
    """
    import yaml

    out: dict[str, Path] = {}
    for rel in _takipli(["*compose*.yml", "*compose*.yaml"]):
        p = KOK / rel
        belge = yaml.safe_load(p.read_text(encoding="utf-8", errors="replace")) or {}
        for servis in (belge.get("services") or {}).values():
            b = (servis or {}).get("build")
            if b is None:
                continue
            if isinstance(b, str):
                b = {"context": b}
            taban = (p.parent / str(b.get("context", "."))).resolve()
            out[str((taban / str(b.get("dockerfile", "Dockerfile"))).resolve())] = taban
    return out


#: Compose'da servisi OLMAYAN Dockerfile'ların build bağlamı (Dockerfile başlığındaki `docker build` komutuyla aynı).
#: D4.20: bağlamı bilinmeyen Dockerfile artık `continue` ile ATLANMAZ — buraya ya da compose'a eklenmeli.
COMPOSE_DISI_BAGLAM = {"docker/Dockerfile.ai-full": "release_assets"}


def test_KRITIK_dockerfile_COPY_kaynaklari_DISKTE_VAR():
    """`COPY <kaynak> <hedef>` kaynakları build context'inde bulunmalı.

    Ölçülen arıza: `docker/Dockerfile.ai` altı satırda `utils/...` kopyalıyordu; `utils/`
    F4'te `apps/backend/` altına gitti → imaj HİÇ derlenmiyordu, hiçbir kapı görmedi.

    ⚠️ Context TAHMİN EDİLMEZ, compose'dan okunur: `Dockerfile.frontend`in context'i
    `../apps/ui`, `Dockerfile.ai-full`ünki `release_assets`. Kökü varsaymak üç dosyayı
    YANLIŞLIKLA kırık gösteriyordu (ilk ölçümde tam bu oldu).

    ⚠️ D4.20 (B-10.181): bağlamı çözülemeyen Dockerfile eskiden `continue` ile ATLANIYORDU — compose'daki
    `dockerfile:` yolu (bağlama göre) yanlış olunca frontend Dockerfile'ı hiç denetlenmedi, imaj derlenemez
    hâlde kaldı. Artık her Dockerfile ya compose'dan ya `COMPOSE_DISI_BAGLAM`'dan bağlam almalı.
    """
    ctx = _compose_contextleri()
    assert ctx, "VAKUM: hiçbir compose dosyasından context okunamadı"

    kirik: list[str] = []
    baglamsiz: list[str] = []
    bakilan = 0
    for rel in _takipli(["**/Dockerfile*"]):
        if rel.endswith(".dockerignore"):
            continue  # Dockerfile'a özgü ignore dosyası (BuildKit) — Dockerfile değil
        p = KOK / rel
        taban = ctx.get(str(p.resolve()))
        if taban is None and rel in COMPOSE_DISI_BAGLAM:
            taban = KOK / COMPOSE_DISI_BAGLAM[rel]
        if taban is None:
            baglamsiz.append(rel)
            continue
        for satir in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = satir.strip()
            if not s.upper().startswith("COPY "):
                continue
            parcalar = [x for x in s.split()[1:] if not x.startswith("--")]
            if len(parcalar) < 2 or parcalar[0].startswith("<<"):
                continue  # heredoc / eksik
            for kaynak in parcalar[:-1]:
                if kaynak.startswith("/") or "*" in kaynak or "?" in kaynak:
                    continue  # önceki aşamadan / glob → dosya sistemi iddiası yok
                bakilan += 1
                if not (taban / kaynak).exists():
                    kirik.append(f"{rel}  ->  {kaynak}   (context: {taban.name})")
    assert bakilan > 10, f"VAKUM: yalnız {bakilan} COPY kaynağı sınandı"
    assert not baglamsiz, (
        f"build bağlamı ÇÖZÜLEMEYEN Dockerfile (compose'daki dockerfile yolu yanlış ya da servis yok): {baglamsiz} — "
        "COPY kaynakları denetlenemez, imaj sessizce derlenemez kalır"
    )
    assert not kirik, (
        "DOCKERFILE COPY KAYNAĞI YOK:\n  "
        + "\n  ".join(kirik)
        + "\n\nKlasör taşındıysa yolu güncelleyin — imaj sessizce derlenemez hâle gelir."
    )
