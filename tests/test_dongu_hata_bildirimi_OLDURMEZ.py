# Author: mertaygn, cglrgrkn
r"""DAEMON DÖNGÜSÜ KENDİ HATA BİLDİRİMİYLE ÖLMEZ.

NE BULUNDU (2026-09-19). Backend'in altı sonsuz döngüsünün **altısı da** şu şekildeydi:

    while True:
        try:
            ...
        except Exception:
            logging.exception("...")     # <-- BU fırlatırsa `while`dan ÇIKILIR
        time.sleep(N)

`logging` NE ZAMAN fırlatır — ÖLÇÜLEN model (DENETİM-01 B-1.36 · DENETİM-04 B-4.17 öncülü D0;
D1.17 ile düzeltildi): ürünün yapılandırmasında (stdlib `RotatingFileHandler`,
`backend_service._configure_logging`) kilitli dosyada devir `PermissionError`'ı, dolu disk
`OSError`'ı, kapalı handler ve `sys.stderr = None` FIRLATMAZ — `Handler.emit` hatayı
`handleError`'a verir, o da `sys.stderr`'e yazıp yutar. Ölçülen tek fırlatma: `sys.stderr`
KAPALI bir akış nesnesiyken `handleError`'ın kendi yazımı (`ValueError: I/O operation on closed
file`); standart dışı bir handler/filtre de fırlatabilir. Yani tetik NADİR — ama olursa thread
**sessizce ölür** ve hiçbir yere yazılmaz (yazmaya çalışan şey zaten patlamıştır). Ölüm iki
hata ister (gövde + bildirim). Aşağıdaki birim testleri bu yüzden yardımcıyı her istisna
türüyle sınar (sahte logger) — üretimde hangi tür gelirse gelsin döngü yaşamalı.

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
#: 2026-09-19'da (yalnız `while True`) ölçülen 6. 2026-10-01 (D1.19, olay + bayrak döngüleri de
#: sayılınca) ölçülen 22 = 9 sabit + 10 olay + 3 bayrak. Tavan değil TABAN; tarayıcı yeniden
#: `while True`'ya daralırsa (9) bu taban da KIRMIZI olur.
ASGARI_DONGU = 20


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
    """Daemon döngüsü biçimleri (D1.19/D1.17 — B-10.121, B-1.36: eskiden YALNIZ `while True`):

    * sabit: `while True` / `while 1`
    * olay: `while not X.is_set()` / `while not X.wait(...)` (keep-alive, HWSender, servisler)
    * bayrak: `while _aktif` / `while self._running` (AI Pro döngüleri, mDNS izleyici)

    Karşılaştırmalı/çağrılı koşullar (`while n < 5`, `while time.monotonic() < son`) sınırlıdır →
    kapsam dışı (orada bildirim düşse akış zaten biter)."""
    t = d.test
    if isinstance(t, ast.Constant) and t.value in (True, 1):
        return True
    if isinstance(t, ast.Name) and t.id == "True":
        return True
    if isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not) and isinstance(t.operand, ast.Call):
        f = t.operand.func
        if isinstance(f, ast.Attribute) and f.attr in ("is_set", "wait"):
            return True
    return isinstance(t, (ast.Name, ast.Attribute))


_LOG_METOTLARI = frozenset({"debug", "info", "warning", "warn", "error", "exception", "critical", "log"})


def _log_cagrisi(c: ast.AST) -> str | None:
    """Günlük çağrısıysa yolunu döndürür. Ölçüt: metot bir logging metodu VE alıcı ifadesinin adında
    'log' geçer — `logging.x`, `log.x`, `logger.x`, `self.logger.x`, `self._log.x`, `_LOG.x`,
    `logging.getLogger(__name__).x` (eskiden yalnız sabit kök adları: `self.logger` GÖRÜNMÜYORDU)."""
    if not isinstance(c, ast.Call) or not isinstance(c.func, ast.Attribute) or c.func.attr not in _LOG_METOTLARI:
        return None
    parcalar: list[str] = []
    f = c.func.value
    while True:
        if isinstance(f, ast.Attribute):
            parcalar.append(f.attr)
            f = f.value
        elif isinstance(f, ast.Call):
            f = f.func
        elif isinstance(f, ast.Name):
            parcalar.append(f.id)
            break
        else:
            return None
    alici = ".".join(reversed(parcalar))
    return f"{alici}.{c.func.attr}" if "log" in alici.lower() else None


def _genis_try(t: ast.Try) -> bool:
    """`Exception`/`BaseException`/çıplak `except` taşıyan try — günlük hatasını (ValueError,
    PermissionError, OSError) yakalar. `except OSError:` gibi DAR bir sarma koruma SAYILMAZ."""
    for h in t.handlers:
        if h.type is None:
            return True
        tipler = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
        if any(isinstance(x, ast.Name) and x.id in ("Exception", "BaseException") for x in tipler):
            return True
    return False


_GOVDE_ALANLARI = ("body", "orelse", "handlers", "finalbody")


def _korumasiz_bildirimler(govde: list[ast.stmt], korunan: bool, isleyicide: bool, bulgu: list) -> None:
    """Döngü gövdesini İÇ İÇE yürür: bir `except` gövdesinde (isleyicide) olup döngü gövdesi içinde
    geniş bir `try` GÖVDESİYLE sarılmamış (korunan değil) her günlük çağrısı bulgudur — fırlarsa
    istisna döngüden çıkar. İç fonksiyon/sınıf ve iç daemon döngüsü atlanır (o kendi başına taranır)."""
    for st in govde:
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(st, ast.While) and _sonsuz_mu(st):
            continue
        if isinstance(st, ast.Try):
            _korumasiz_bildirimler(st.body, korunan or _genis_try(st), isleyicide, bulgu)
            for h in st.handlers:
                _korumasiz_bildirimler(h.body, korunan, True, bulgu)
            _korumasiz_bildirimler(st.orelse, korunan, isleyicide, bulgu)
            _korumasiz_bildirimler(st.finalbody, korunan, isleyicide, bulgu)
            continue
        if isleyicide and not korunan:
            for alan, deger in ast.iter_fields(st):
                if alan in _GOVDE_ALANLARI:
                    continue
                for dugum in deger if isinstance(deger, list) else [deger]:
                    if not isinstance(dugum, ast.AST):
                        continue
                    for c in ast.walk(dugum):
                        yol = _log_cagrisi(c)
                        if yol:
                            bulgu.append((c.lineno, [yol]))
        for alan in ("body", "orelse"):
            alt = getattr(st, alan, None)
            if isinstance(alt, list):
                _korumasiz_bildirimler(alt, korunan, isleyicide, bulgu)


def _tara(kaynak: str) -> tuple[int, list[tuple[int, list[str]]]]:
    """(daemon döngüsü sayısı, [(satır, [korumasız günlük çağrısı])])"""
    try:
        agac = ast.parse(kaynak)
    except SyntaxError:
        return 0, []
    dongu = 0
    bulgu: list[tuple[int, list[str]]] = []
    for d in ast.walk(agac):
        if not isinstance(d, ast.While) or not _sonsuz_mu(d):
            continue
        dongu += 1
        _korumasiz_bildirimler(d.body, False, False, bulgu)
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
        "Daemon döngüsünün bir `except` bloğu KORUMASIZ günlük çağırıyor — bildirim "
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


def test_KARSIT_KANIT_tarayici_OLAY_ve_BAYRAK_dongulerini_ve_self_logger_GORUR():
    """D1.19 (B-10.121): `hardware_controller._keep_alive_loop` biçimi — eski tarayıcı 'bulgu yok' diyordu."""
    olay = (
        "class C:\n"
        "    def d(self):\n"
        "        while not self._stop.is_set():\n"
        "            try:\n"
        "                self._tick()\n"
        "            except Exception:\n"
        '                self.logger.exception("keep-alive tick hatasi")\n'
    )
    assert _tara(olay) == (1, [(7, ["self.logger.exception"])]), _tara(olay)
    bayrak = (
        "import logging\n"
        "def d():\n"
        "    while _aktif:\n"
        "        try:\n"
        "            pass\n"
        "        except Exception:\n"
        '            logging.getLogger(__name__).error("x")\n'
    )
    assert _tara(bayrak) == (1, [(7, ["logging.getLogger.error"])]), _tara(bayrak)


def test_KARSIT_KANIT_tarayici_IC_ICE_handleri_ve_DAR_sarmayi_GORUR():
    """Handler `with`/`if` içinde de olsa bulgudur; `except OSError` gibi DAR sarma koruma değildir
    (kapalı stderr'de `handleError` ValueError atar — D0)."""
    ic_ice = (
        "def d(self):\n"
        "    while True:\n"
        "        with self._kilit:\n"
        "            try:\n"
        "                pass\n"
        "            except Exception as e:\n"
        "                if e:\n"
        '                    self.logger.warning("x %s", e)\n'
    )
    assert _tara(ic_ice)[1] == [(8, ["self.logger.warning"])], _tara(ic_ice)
    dar = (
        "import logging\n"
        "def d():\n"
        "    while True:\n"
        "        try:\n"
        "            pass\n"
        "        except Exception:\n"
        "            try:\n"
        '                logging.exception("x")\n'
        "            except OSError:\n"
        "                pass\n"
    )
    assert _tara(dar)[1] == [(8, ["logging.exception"])], "DAR sarma koruma sayıldı"


def test_KARSIT_KANIT_dis_GENIS_try_ic_handleri_KORUR():
    """Gövde içindeki geniş `try` iç handler'ın bildirimini sarar → istisna döngüden ÇIKMAZ (yanlış kırmızı yok)."""
    korunan = (
        "import logging\n"
        "def d():\n"
        "    while True:\n"
        "        try:\n"
        "            try:\n"
        "                pass\n"
        "            except ValueError as e:\n"
        '                logging.error("ic %s", e)\n'
        "        except Exception:\n"
        '            dongu_hatasini_bildir("dis")\n'
    )
    assert _tara(korunan) == (1, []), _tara(korunan)


def test_KARSIT_KANIT_M1_M2_bicimleri_TEK_BASINA_yakalanir():
    """D1.17 (B-1.36): eski tarayıcı M1 (`while True` + `self.logger`) ve M2 (`is_set` + `logging`) biçimlerine
    TEK BAŞINA kördü (yalnız ikisi birden yakalanıyordu — v-A20)."""
    m1 = (
        "def d(self):\n"
        "    while True:\n"
        "        try:\n"
        "            self._tick()\n"
        "        except Exception:\n"
        '            self.logger.exception("x")\n'
    )
    m2 = (
        "import logging\n"
        "def d(self):\n"
        "    while not self._stop.is_set():\n"
        "        try:\n"
        "            self._tick()\n"
        "        except Exception:\n"
        '            logging.exception("x")\n'
    )
    assert _tara(m1) == (1, [(6, ["self.logger.exception"])]), _tara(m1)
    assert _tara(m2) == (1, [(7, ["logging.exception"])]), _tara(m2)


_YARDIMCI_ADLARI = frozenset({"dongu_hatasini_bildir", "_dongu_hatasini_bildir"})


def _yardimci_cagrisi_sayisi(kaynak: str) -> int:
    """`dongu_hatasini_bildir` için GERÇEK çağrı sayısı (AST). D1.17 (B-1.36): eski sayaç metin araması
    yapıyordu — yoruma eklenen `dongu_hatasini_bildir(` dizesi onu kandırdı (k-K4.6c: 344 passed)."""
    n = 0
    for c in ast.walk(ast.parse(kaynak)):
        if isinstance(c, ast.Call):
            f = c.func
            ad = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if ad in _YARDIMCI_ADLARI:
                n += 1
    return n


def test_KARSIT_KANIT_sayac_YORUM_ve_DIZE_ile_kandirilmaz():
    assert _yardimci_cagrisi_sayisi('# dongu_hatasini_bildir("x")\nX = "dongu_hatasini_bildir("\n') == 0
    assert (
        _yardimci_cagrisi_sayisi('dongu_hatasini_bildir("x")\n_dongu_hatasini_bildir("y")\nm.dongu_hatasini_bildir()\n')
        == 3
    )


#: Yardımcıya bağlı döngü bildirimi sayısı (2026-10-01 ölçüldü: 26). Taban — ekleme serbest.
BAGLI_BILDIRIMLER = {
    "apps/backend/servers/api_server.py": 5,
    "apps/backend/servers/efield_live.py": 1,
    "apps/backend/servers/tunnel_manager.py": 1,
    "apps/backend/servers/sync_worker.py": 2,
    "apps/backend/servers/update_manager.py": 1,
    "apps/backend/services/headless_services.py": 4,
    "apps/backend/services/headless_db_maintenance.py": 1,
    "apps/backend/services/mdns_service.py": 3,
    "apps/backend/controllers/hardware_controller.py": 1,
    "apps/backend/headless_core.py": 3,
    "apps/backend/servers/ai_router.py": 4,
}


def test_KARSIT_KANIT_baglanan_donguler_GERCEKTEN_cagiriyor():
    """Düzeltmenin ÖZNESİ hâlâ orada mı — yoksa kapı boş bir ağacı tarıyor olabilir. Sayım AST ile:
    yorumdaki ya da dizedeki ad sayılmaz."""
    for rel, beklenen in BAGLI_BILDIRIMLER.items():
        n = _yardimci_cagrisi_sayisi((KOK / rel).read_text(encoding="utf-8"))
        assert n >= beklenen, f"{rel}: {n} gerçek çağrı var, beklenen ≥{beklenen} — döngüler yardımcıdan koparılmış"


# ═════════════════════════════════════════════════════════════════════════════════════════
# 4. DAVRANIŞ — GERÇEK keep-alive döngüsü tick + günlük hatasında YAŞAR (D1.19 · B-10.121)
# ═════════════════════════════════════════════════════════════════════════════════════════


class _KosulluLogger:
    """Sağlamken sayar; `patlat` kurulunca her çağrıda fırlatır (kilitli log / kapalı akış)."""

    def __init__(self):
        import threading

        self.patlat = threading.Event()
        self.cagri = 0

    def _cagir(self, *a, **k):
        self.cagri += 1
        if self.patlat.is_set():
            raise PermissionError(13, "log dosyasi kilitli (test)")

    debug = info = warning = error = exception = critical = log = _cagir


@pytest.mark.parametrize("patlak", [False, True], ids=["KONTROL_logger_saglam", "logger_PATLAK"])
def test_KRITIK_GERCEK_keep_alive_dongusu_tick_ve_LOG_hatasinda_YASAR(patlak, monkeypatch):
    """Keep-alive iş parçacığı bobin-başı süre sınırını ve keep-alive'ı taşır. Eskiden `_tick` hatası
    + fırlatan `self.logger.exception` onu SÜREÇ ÖMRÜ BOYUNCA öldürüyordu (firmware ölü-adam devresi
    1,5 sn'de keser — güvenli yön — ama yol cihaz yeniden başlayana dek ölü kalır). GERÇEK
    `HardwareController._keep_alive_loop`; yalnız `_tick` ve aralık test için değiştirilir."""
    import threading
    import time
    import types

    from controllers.hardware_controller import HardwareController

    durum = types.SimpleNamespace(tik=0, hata=threading.Event())

    class _HC(HardwareController):
        KEEP_ALIVE_INTERVAL_S = 0.01

        def _tick(self):
            durum.tik += 1
            if durum.hata.is_set():
                raise RuntimeError("TICK-HATASI (test)")

    def bekle(kosul, sure=5.0):
        son = time.monotonic() + sure
        while time.monotonic() < son and not kosul():
            time.sleep(0.005)
        return kosul()

    monkeypatch.setattr(sys, "__stderr__", io.StringIO())
    hc = _HC(types.SimpleNamespace())
    lg = _KosulluLogger()
    hc.logger = lg
    try:
        assert bekle(lambda: durum.tik >= 1), "keep-alive hiç dönmedi (aparat)"
        if patlak:
            lg.patlat.set()
        durum.hata.set()
        n0 = durum.tik
        dondu = bekle(lambda: durum.tik >= n0 + 3)
        canli = hc._keep_alive_thread.is_alive()
    finally:
        lg.patlat.clear()
        hc._keep_alive_stop.set()
        hc._keep_alive_thread.join(timeout=2)
    assert dondu and canli, f"keep-alive tick{' + LOG' if patlak else ''} hatasında ÖLDÜ ({durum.tik - n0} tur)"
    assert lg.cagri >= 1, "hata yolu günlüğe uğramadı — kapı vakumda"
