# Author: mertaygn, cglrgrkn
r"""DAEMON DÖNGÜSÜ KENDİ HATA BİLDİRİMİYLE ÖLMEZ.

NE BULUNDU (2026-09-19). Backend'in altı sonsuz döngüsünün **altısı da** şu şekildeydi:

    while True:
        try:
            ...
        except Exception:
            logging.exception("...")     # <-- BU fırlatırsa `while`dan ÇIKILIR
        time.sleep(N)

`logging` fırlatabilir: Windows'ta dönen log dosyası kilitliyse `PermissionError`, disk
doluysa `OSError`, handler kapanmışsa `ValueError: I/O operation on closed file`. O anda
thread **sessizce ölür** — üstelik hiçbir yere yazılmaz, çünkü yazmaya çalışan şey zaten
patlamıştır. Ölüm iki hata ister (gövde + bildirim), ama bu depo Windows dosya-kilidi
sınıfını bu oturumda zaten bir kez yaşadı (karantina taşıma arızası).

**En ağır sonucu `session-watchdog`ta:** o döngü seans süresi dolunca DONANIM düzeyinde
STOP üretir ve kendi belgesi *"firmware keep-alive süreyi her sn tazelediğinden tek başına
auto-stop OLMAZ"* diyor. Thread ölürse seans planlanan süreyi **aşar**, hasta o sırada
PEMF maruziyetinde kalır ve hiçbir uyarı çıkmaz.

NASIL FARK EDİLDİ — ve iddianın sınırı: conftest daemon sızıntısını ölçerken tam süit
koşumlarından **birinde** `esp-telemetry-watchdog` süit sonunda yoktu; ikinci koşumda
vardı, izole ölçümde 72 sn canlı kaldı. **Tekrar üretilemedi.** Yani "bu oldu" demiyorum;
AST taraması bu yolun kodda **altı yerde** var olduğunu gösterdi ve kapı onu kapatıyor.

⚠️ BU KAPI "hata yutmayı" ONAYLAMAZ. `dongu_hatasini_bildir` iki kanal dener (logger →
ham `sys.__stderr__`) ve hangisinin çalıştığını DÖNDÜRÜR. Aşağıdaki testler **her iki
düşme dalını da KOŞTURUR** — bu depoda "except dalına hiç uğranmıyor, süit yine yeşil"
arızası yaşandı ([[pemf-suit-yesil-except-dali-bos]]).
"""

from __future__ import annotations

import ast
import io
import logging
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "apps" / "backend"))

from utils.dongu_guvenligi import dongu_hatasini_bildir  # noqa: E402

#: Taranan ağaç — SEVK EDİLEN backend. `tools/` geliştirme aracıdır (simülatör):
#: orada bir döngü ölürse geliştirici anında görür, hasta etkilenmez.
TARANAN = "apps/backend"

#: ⚠️ VAKUM KAPISI: tarama sıfır döngü bulursa sonsuza kadar yeşil kalırdı.
#: 2026-09-19'da ölçülen sayı 6; tavan değil TABAN (yeni döngü eklenebilir).
ASGARI_DONGU = 5


# ═════════════════════════════════════════════════════════════════════════════════════════
# 1. DAVRANIŞ — yardımcı HİÇBİR KOŞULDA fırlatmaz
# ═════════════════════════════════════════════════════════════════════════════════════════


class _PatlayanLogger:
    """`logging` katmanının düştüğü gerçek durumları taklit eder."""

    def __init__(self, hata: Exception):
        self._hata = hata
        self.cagrildi = 0

    def log(self, *a, **k):
        self.cagrildi += 1
        raise self._hata


def _hatayla_cagir(**kw) -> str:
    """Gerçek bir `except` bloğunun İÇİNDEN çağırır — fonksiyon `sys.exc_info()` okur."""
    try:
        raise RuntimeError("DONGU-GOVDE-HATASI-42")
    except RuntimeError:
        return dongu_hatasini_bildir("dongu hatasi", **kw)


def test_KRITIK_normal_yolda_LOGGERA_yazar():
    kayitlar: list[logging.LogRecord] = []

    class _Toplayici(logging.Handler):
        def emit(self, record):
            kayitlar.append(record)

    lg = logging.getLogger("dongu_guvenligi_testi")
    lg.handlers = [_Toplayici()]
    lg.propagate = False
    lg.setLevel(logging.DEBUG)

    assert _hatayla_cagir(logger=lg) == "logger"
    assert len(kayitlar) == 1, "logger çağrılmadı"
    assert kayitlar[0].exc_info is not None, "yığın izi TAŞINMADI — hata bildirilse de teşhis edilemez hâle gelir"
    assert kayitlar[0].exc_info[1].args[0] == "DONGU-GOVDE-HATASI-42", (
        "yanlış istisna bildirildi — `sys.exc_info()` en başta kopyalanmıyor olabilir"
    )


@pytest.mark.parametrize(
    "hata",
    [
        PermissionError(13, "log dosyasi kilitli"),  # Windows: dönen log başka süreçte
        ValueError("I/O operation on closed file"),  # handler kapanmış
        OSError(28, "No space left on device"),  # disk dolu
    ],
    ids=["windows_kilit", "kapali_handler", "disk_dolu"],
)
def test_KRITIK_logger_PATLARSA_firlatmaz_ve_STDERRE_dusr(hata, monkeypatch):
    """🔴 ASIL REGRESYON: bu dal çalışmazsa `while True` biter ve bekçi ÖLÜR."""
    sahte = io.StringIO()
    monkeypatch.setattr(sys, "__stderr__", sahte)
    lg = _PatlayanLogger(hata)

    sonuc = _hatayla_cagir(logger=lg)  # fırlatırsa test zaten kırmızı

    assert lg.cagrildi == 1, "logger denenmedi — ilk kanal atlanıyor"
    assert sonuc == "stderr", f"son çare kanalı çalışmadı: {sonuc}"
    metin = sahte.getvalue()
    assert "logging BASARISIZ" in metin, "son çare uyarısı yazılmadı"
    assert "DONGU-GOVDE-HATASI-42" in metin, (
        "ORİJİNAL hata kayboldu — logging'in hatası orijinalin yerine geçmiş olabilir"
    )


def test_KRITIK_IKISI_DE_patlarsa_yine_firlatmaz(monkeypatch):
    """En kötü durum: logger de stderr de düşüyor. Bekçi YİNE yaşamalı."""

    class _PatlayanAkis:
        def write(self, *a, **k):
            raise OSError("stderr de kapali")

        def flush(self):
            raise OSError("stderr de kapali")

    monkeypatch.setattr(sys, "__stderr__", _PatlayanAkis())
    assert _hatayla_cagir(logger=_PatlayanLogger(OSError("log da kapali"))) == "sessiz"


def test_KRITIK_stderr_YOKSA_firlatmaz(monkeypatch):
    """Donmuş EXE'de `sys.__stderr__` **None** olabilir (pythonw / konsolsuz pencere)."""
    monkeypatch.setattr(sys, "__stderr__", None)
    assert _hatayla_cagir(logger=_PatlayanLogger(OSError("log kapali"))) == "sessiz"


# ═════════════════════════════════════════════════════════════════════════════════════════
# 2. YAPI — sevk edilen hiçbir sonsuz döngü ÇIPLAK logging ile bildirmesin
# ═════════════════════════════════════════════════════════════════════════════════════════


def _sonsuz_mu(d: ast.While) -> bool:
    t = d.test
    return (isinstance(t, ast.Constant) and t.value is True) or (isinstance(t, ast.Name) and t.id == "True")


def _ciplak_logging(govde: list[ast.stmt]) -> list[str]:
    """Handler gövdesindeki KORUMASIZ logging çağrıları.

    "Korumalı" = gövdede bir `try` var (yani bildirimin kendisi sarılmış).
    """
    if any(isinstance(x, ast.Try) for x in govde):
        return []
    bulunan = []
    for st in govde:
        if not isinstance(st, ast.Expr) or not isinstance(st.value, ast.Call):
            continue
        f, parcalar = st.value.func, []
        while isinstance(f, ast.Attribute):
            parcalar.append(f.attr)
            f = f.value
        if isinstance(f, ast.Name):
            parcalar.append(f.id)
        yol = ".".join(reversed(parcalar))
        if yol.split(".")[0] in ("logging", "log", "logger", "_log", "LOG"):
            bulunan.append(yol)
    return bulunan


def _tara(kaynak: str) -> tuple[int, list[tuple[int, list[str]]]]:
    """(sonsuz döngü sayısı, [(satır, çıplak çağrılar)])"""
    try:
        agac = ast.parse(kaynak)
    except SyntaxError:
        return 0, []
    dongu = 0
    bulgu = []
    for d in ast.walk(agac):
        if not isinstance(d, ast.While) or not _sonsuz_mu(d):
            continue
        dongu += 1
        for st in d.body:
            if not isinstance(st, ast.Try):
                continue
            for h in st.handlers:
                c = _ciplak_logging(h.body)
                if c:
                    bulgu.append((h.lineno, c))
    return dongu, bulgu


def _backend_dosyalari() -> list[str]:
    ch = subprocess.run(
        ["git", "ls-files", f"{TARANAN}/*.py"],
        cwd=KOK,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    if ch.returncode != 0:
        pytest.skip("git deposu değil")
    return [a for a in ch.stdout.splitlines() if a]


def test_KRITIK_sevk_edilen_donguler_CIPLAK_logging_KULLANMAZ():
    """🔴 Her çıplak bildirim, o daemon'ı öldürebilecek bir yoldur."""
    dosyalar = _backend_dosyalari()
    assert len(dosyalar) > 50, f"tarama çok dar ({len(dosyalar)}) — kapı boş dönüyor olabilir"

    toplam_dongu = 0
    bulgu: dict[str, list[str]] = {}
    for rel in dosyalar:
        try:
            kaynak = (KOK / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n, b = _tara(kaynak)
        toplam_dongu += n
        for satir, cagrilar in b:
            bulgu.setdefault(rel, []).append(f"{satir}: {cagrilar}")

    assert not bulgu, (
        "Sonsuz döngünün en-dış `except` bloğu ÇIPLAK logging çağırıyor — bildirim "
        "fırlatırsa döngü ölür:\n"
        + "\n".join(f"  {k}\n    " + "\n    ".join(v) for k, v in sorted(bulgu.items()))
        + "\nÇözüm: `utils.dongu_guvenligi.dongu_hatasini_bildir(...)`"
    )
    # ⚠️ VAKUM KAPISI: sıfır döngü bulan bir tarama sonsuza kadar yeşil kalır.
    assert toplam_dongu >= ASGARI_DONGU, (
        f"taramada yalnız {toplam_dongu} sonsuz döngü bulundu (beklenen ≥{ASGARI_DONGU}) — "
        "AST çözümleyici kapsamı kaybetmiş olabilir; kapı vakum"
    )


# ═════════════════════════════════════════════════════════════════════════════════════════
# 3. KARŞIT-KANITLAR
# ═════════════════════════════════════════════════════════════════════════════════════════


def test_KARSIT_KANIT_tarayici_BOZUK_sekli_yakaliyor():
    """Kapı boş geçmiyor: düzeltmeden önceki gerçek şekil YAKALANMALI."""
    bozuk = (
        "import logging, time\n"
        "def d():\n"
        "    while True:\n"
        "        try:\n"
        "            pass\n"
        "        except Exception:\n"
        '            logging.exception("x")\n'
        "        time.sleep(1)\n"
    )
    dongu, bulgu = _tara(bozuk)
    assert dongu == 1 and bulgu, "tarayıcı BOZUK şekli kaçırıyor"
    assert bulgu[0][1] == ["logging.exception"], bulgu

    # `log.warning(..., exc_info=True)` biçimi de aynı sınıf (daily-maintenance böyleydi).
    bozuk2 = bozuk.replace('logging.exception("x")', 'log.warning("x", exc_info=True)')
    assert _tara(bozuk2)[1], "alternatif logger adı kaçırılıyor"


def test_KARSIT_KANIT_DUZELTILMIS_sekil_yanlis_kirmizi_vermiyor():
    """Yardımcıya bağlanmış şekil temiz sayılmalı; `try` ile sarılmış olan da."""
    iyi = (
        "import time\n"
        "def d():\n"
        "    while True:\n"
        "        try:\n"
        "            pass\n"
        "        except Exception:\n"
        '            dongu_hatasini_bildir("x")\n'
        "        time.sleep(1)\n"
    )
    assert _tara(iyi) == (1, []), "düzeltilmiş şekil YANLIŞ KIRMIZI veriyor"

    sarili = (
        "import logging, time\n"
        "def d():\n"
        "    while True:\n"
        "        try:\n"
        "            pass\n"
        "        except Exception:\n"
        "            try:\n"
        '                logging.exception("x")\n'
        "            except Exception:\n"
        "                pass\n"
        "        time.sleep(1)\n"
    )
    assert _tara(sarili)[1] == [], "kendi `try`ıyla sarılmış bildirim ihlal sayılıyor"


def test_KARSIT_KANIT_SINIRLI_dongu_yanlis_kirmizi_vermiyor():
    """Sonsuz OLMAYAN döngü kapsam dışı — orada bildirim düşse akış zaten biter."""
    sinirli = (
        "import logging\n"
        "def d():\n"
        "    for _ in range(3):\n"
        "        try:\n"
        "            pass\n"
        "        except Exception:\n"
        '            logging.exception("x")\n'
        "    while n < 5:\n"
        "        try:\n"
        "            pass\n"
        "        except Exception:\n"
        '            logging.exception("y")\n'
    )
    assert _tara(sinirli) == (0, []), "sınırlı döngü sonsuz sayılıyor"


def test_KARSIT_KANIT_ALTI_dongu_GERCEKTEN_baglandi():
    """Düzeltmenin ÖZNESİ hâlâ orada mı — yoksa kapı boş bir ağacı tarıyor olabilir."""
    hedefler = {
        "apps/backend/servers/api_server.py": 5,
        "apps/backend/servers/efield_live.py": 1,
    }
    for rel, beklenen in hedefler.items():
        metin = (KOK / rel).read_text(encoding="utf-8")
        n = metin.count("dongu_hatasini_bildir(")
        assert n >= beklenen, f"{rel}: {n} bağlanma var, beklenen ≥{beklenen} — döngüler yardımcıdan koparılmış"
