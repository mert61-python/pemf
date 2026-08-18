# Author: mertaygn, cglrgrkn
"""ÜRETİM KODUNUN MODÜL-DÜZEYİ İMPORTLARI CI'DA KURULABİLİR OLMALI — "20 test birden kırmızı" sınıfı.

NEDEN VAR: Aynı mekanizma 8 günde ÜÇ kez kırmızı e-posta seli üretti (27 başarısız koşunun
loglarından tek tek doğrulandı, 2026-08-18):
  • `backend_service.py:21` modül düzeyinde `import uvicorn` → paket `requirements-test.txt`te
    yokken onu import eden ~20 test CI'da `ModuleNotFoundError` ile düştü (2026-08-10/12 arası
    15 koşu kırmızı; hattın İLK yeşili bu yüzden gecikti).
  • `ai_service/app.py:23` modül düzeyinde `import onnxruntime` → aynı sınıf, 2026-08-18'de
    yeniden ateşledi (62eaec7, cce00d3); `importorskip` ile kapatıldı.
  • Her seferinde teşhis aynıydı, ama kapı olmadığı için tekrar tekrar REAKTİF yamalandı.

Bu kapı mekanizmayı sınıf olarak kapatır: üretim koduna modül düzeyinde yeni bir üçüncü-parti
import girdiğinde, paket ya `requirements-test.txt`te olacak ya da bilinçli "ağır AI" muafiyeti
alacak — yoksa 20 karışık kırmızı yerine, düzeltmeyi adıyla söyleyen TEK test kırmızı olur.

⚠️ `AGIR_MUAF` bilinçli karardır (requirements-test.txt baş yorumu): torch/onnxruntime sınıfı
paketler CI'ya kurulmaz (~2GB). O sınıf için kural farklı: o modülü import eden HER test dosyası
`pytest.importorskip` ile korunmak ZORUNDA (ikinci test bunu kilitler).
"""

from __future__ import annotations

import ast
import re
import sys
import warnings
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]

#: Üretim kodu: testlerin import ettiği, CI'da modül düzeyinde yüklenen ağaçlar.
_URETIM = ("backend_service.py", "servers", "ai_service", "utils")

#: requirements-test.txt baş yorumundaki BİLİNÇLİ "ağır AI" muafiyeti (lazy yüklenirler).
#: Buraya ekleme yapmak = "bu paket CI'da ASLA kurulmayacak" demek; o zaman ikinci test
#: ilgili modülü import eden her test dosyasında importorskip arar.
AGIR_MUAF = {"onnxruntime", "torch", "ultralytics", "librosa", "numba", "sklearn", "xgboost"}

#: import adı → requirements-test.txt'teki dağıtım adı (farklı olanlar).
_AD_ESLEME = {
    "cv2": {"opencv-python-headless", "opencv-python"},
    "PIL": {"pillow"},
    "imageio_ffmpeg": {"imageio-ffmpeg"},
}


def _bildirilenler() -> set[str]:
    """requirements-test.txt'te sabitlenen dağıtım adları (küçük harf)."""
    adlar = set()
    for satir in (KOK / "requirements-test.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z0-9_.\-]+)\s*==", satir)
        if m:
            adlar.add(m.group(1).lower())
    return adlar


def _modul_duzeyi_importlar(dosya: Path) -> set[str]:
    """Dosyanın modül düzeyindeki, try/except ile KORUNMAYAN üçüncü-parti import kökleri."""
    agac = ast.parse(dosya.read_text(encoding="utf-8"))
    korumali = {
        id(alt)
        for dugum in ast.walk(agac)
        if isinstance(dugum, ast.Try)
        for alt in ast.walk(dugum)
        if isinstance(alt, (ast.Import, ast.ImportFrom))
    }
    stdlib = set(sys.stdlib_module_names)
    yerel = {p.stem for p in KOK.glob("*.py")} | {p.name for p in KOK.iterdir() if p.is_dir()}
    kokler = set()
    for dugum in agac.body:
        if id(dugum) in korumali:
            continue
        if isinstance(dugum, ast.Import):
            kokler.update(a.name.split(".")[0] for a in dugum.names)
        elif isinstance(dugum, ast.ImportFrom) and dugum.level == 0 and dugum.module:
            kokler.add(dugum.module.split(".")[0])
    return {k for k in kokler if k not in stdlib and k not in yerel}


def _uretim_dosyalari() -> list[Path]:
    dosyalar = []
    for ad in _URETIM:
        p = KOK / ad
        if p.is_file():
            dosyalar.append(p)
        elif p.is_dir():
            dosyalar.extend(sorted(p.rglob("*.py")))
    return dosyalar


def _karsilanmayanlar(bildirilen: set[str]) -> dict[str, list[str]]:
    """{import_koku: [dosyalar]} — ne bildirilmiş ne muaf olanlar."""
    sorunlu: dict[str, list[str]] = {}
    for f in _uretim_dosyalari():
        for kok in _modul_duzeyi_importlar(f):
            if kok in AGIR_MUAF:
                continue
            dagitimlar = _AD_ESLEME.get(kok, {kok})
            if not {d.lower() for d in dagitimlar} & bildirilen:
                sorunlu.setdefault(kok, []).append(f.relative_to(KOK).as_posix())
    return sorunlu


def test_KRITIK_modul_duzeyi_importlar_CI_da_kurulabilir():
    sorunlu = _karsilanmayanlar(_bildirilenler())
    assert not sorunlu, (
        f"Üretim kodunda modül düzeyinde import edilen ama requirements-test.txt'te OLMAYAN "
        f"paket(ler) var: {sorunlu}. Bu, o modülü import eden TÜM testleri CI'da "
        f"`ModuleNotFoundError` ile düşürür (uvicorn bunu 15 koşuda yaptı). Ya paketi "
        f"requirements-test.txt'e sabitleyin (sürüm shipped requirements.txt ile birebir) "
        f"ya da bilinçli ağır-AI kararıysa AGIR_MUAF'a ekleyip import'u fonksiyon içine "
        f"taşıyın / testleri importorskip ile koruyun."
    )


def test_KRITIK_agir_muaf_modulleri_import_eden_testler_KORUMALI():
    """AGIR_MUAF paketi modül düzeyinde çeken üretim modülünü import eden her test dosyası
    `pytest.importorskip("<paket>")` içermeli — yoksa CI'da ModuleNotFoundError seli."""
    # Hangi üretim modülü hangi ağır paketi çekiyor?
    agir_ceken: dict[str, set[str]] = {}  # "ai_service" -> {"onnxruntime"}
    for f in _uretim_dosyalari():
        agirlar = _modul_duzeyi_importlar(f) & AGIR_MUAF
        if agirlar:
            ust = f.relative_to(KOK).parts[0].removesuffix(".py")
            agir_ceken.setdefault(ust, set()).update(agirlar)
    assert agir_ceken, "hiçbir üretim modülü AGIR_MUAF çekmiyor — muafiyet listesi bayatladı mı?"

    ihlaller = []
    for test_dosyasi in sorted((KOK / "tests").glob("*.py")):
        metin = test_dosyasi.read_text(encoding="utf-8")
        with warnings.catch_warnings():
            # Başka dosyanın kaynağını derliyoruz; ondaki kaçış-dizisi uyarıları BU kapının
            # konusu değil (kendi uyarısı kendi koşusunda görünür).
            warnings.simplefilter("ignore")
            agac = ast.parse(metin)
        importlar = set()
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.Import):
                importlar.update(a.name.split(".")[0] for a in dugum.names)
            elif isinstance(dugum, ast.ImportFrom) and dugum.level == 0 and dugum.module:
                importlar.add(dugum.module.split(".")[0])
        for modul, paketler in agir_ceken.items():
            if modul in importlar:
                for paket in paketler:
                    if f'importorskip("{paket}"' not in metin and f"importorskip('{paket}'" not in metin:
                        ihlaller.append(f"{test_dosyasi.name} -> {modul} ({paket} korumasız)")
    assert not ihlaller, (
        f"Şu test dosyaları AGIR_MUAF paketi çeken üretim modülünü importorskip KORUMASI OLMADAN "
        f"import ediyor: {ihlaller}. CI'da (paket kurulmaz) ModuleNotFoundError ile düşerler — "
        f"2026-08-18'de test_ai_servis_8100_kapisi tam böyle kırmızıydı."
    )


def test_KARSIT_KANIT_kapi_bos_gecmiyor():
    """Sınıflandırıcının gerçekten ölçtüğünü kanıtla — boş kümelerle 'geçti' demesin."""
    bildirilen = _bildirilenler()
    assert "uvicorn" in bildirilen, "uvicorn requirements-test.txt'ten düşmüş — 15 koşuluk sel geri gelir"
    assert "imageio-ffmpeg" in bildirilen, (
        "imageio-ffmpeg düşmüş — hasta-görünür sessizlik kapısı (3 test) CI'da yine atlanır"
    )
    # backend_service.py'nin uvicorn'u gerçekten görülüyor (AST yolu çalışıyor).
    assert "uvicorn" in _modul_duzeyi_importlar(KOK / "backend_service.py")
    # ai_service ağır paket çekiyor ve yakalanıyor.
    assert "onnxruntime" in _modul_duzeyi_importlar(KOK / "ai_service" / "app.py")
    # Sahte bir bildirilen kümesiyle sorun ÜRETİLİYOR (mutasyon simülasyonu).
    sahte = _karsilanmayanlar(bildirilen - {"uvicorn"})
    assert "uvicorn" in sahte, "uvicorn requirements'tan düşünce kapı YAKALAMIYOR — kapı bozuk"
