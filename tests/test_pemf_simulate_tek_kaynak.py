# Author: mertaygn, cglrgrkn
"""D0Ö.11 (B-10.222 = DENETIM-12 P1) KAPISI — `PEMF_SIMULATE` test modüllerinde DEĞİL, conftest'te TEK yerde.

ARIZA (ölçüldü, DENETIM-12 §3.2): 72 test modülü modül gövdesinde `PEMF_SIMULATE` yazıyordu
(16 `setdefault('1')` + 56 `pop`). Değeri TOPLAMA SIRASI belirliyordu: tam süitte toplama
sonunda YOK, tek dosya koşumunda (ör. `tests/test_toplu_silme.py`) '1'. Yani aynı test dosyası
süitte ve tek başına FARKLI ortamda koşuyordu. Ürün bu değişkeni lifespan'de okuyup hw-sim iş
parçacığını başlatıyor (`api_server.py:4132`) ve o iş parçacığı her 0,5 sn `stm='online'`
yazıyor → STM durumuna dayanan kapılar (İG-6.1 / B-1.19) tek dosya koşumunda güvenilmez.

ÇÖZÜM: 72 modül-düzeyi deyim silindi; `tests/conftest.py` süreç başında TEK normalizasyon yapar
(`os.environ.pop("PEMF_SIMULATE", None)`) ve toplama bitince değeri kaydeder.

KAPILAR:
  (1) Davranış: toplama SONUNDA `PEMF_SIMULATE` tanımsız — tek dosya koşumunda da.
  (2) Yapı (AST): `tests/**/*.py` (conftest.py hariç — tek meşru yer) içe aktarma anında koşan
      kodunda (modül gövdesi, üst düzey if/try, sınıf gövdesi, varsayılan argüman) `PEMF_SIMULATE`
      yazımı (setdefault/pop/[]=/del/update) YOK; vakum koruması ≥300 test dosyası.
MUTASYON: herhangi bir test dosyasına modül düzeyinde `os.environ.setdefault("PEMF_SIMULATE", "1")`
eklemek → (2) KIRMIZI; o dosya tek başına toplanınca (1) de KIRMIZI.
"""

import ast
import sys
import warnings
from pathlib import Path

_TESTLER = Path(__file__).resolve().parent


def test_KRITIK_PEMF_SIMULATE_toplama_sonu_TANIMSIZ():
    _c = sys.modules.get("conftest")  # pytest'in YÜKLEDİĞİ conftest (`import` ikinci kopya yaratabilir)
    assert _c is not None and Path(_c.__file__).resolve() == (_TESTLER / "conftest.py").resolve(), (
        "kayıtlı tests/conftest.py bulunamadı (içe aktarma kipi değişmiş olabilir)"
    )
    kayit = getattr(_c, "_PEMF_SIMULATE_TOPLAMA_SONU", None)
    assert kayit, "conftest toplama-sonu değerini KAYDETMİYOR (pytest_collection_finish kancası yok)"
    assert kayit[-1] is None, (
        f"toplama sonunda PEMF_SIMULATE={kayit[-1]!r} — bu koşum tam süitten FARKLI ortamda koşuyor "
        "(bir test modülü modül düzeyinde PEMF_SIMULATE yazıyor YA DA conftest dış ortamdan geleni "
        "normalize etmiyor)"
    )


def _modul_duzeyi_yazimlar(agac: ast.Module) -> list[int]:
    """İÇE AKTARMA ANINDA koşan PEMF_SIMULATE yazımlarının satırları: modül gövdesi (üst düzey
    if/try/with dahil), SINIF gövdeleri, dekoratörler ve varsayılan argümanlar. Fonksiyon ve
    lambda GÖVDELERİ koşmaz → sayılmaz."""
    satirlar = []

    def _anahtar_mi(dugum) -> bool:
        return isinstance(dugum, ast.Constant) and dugum.value == "PEMF_SIMULATE"

    def _tara(dugum):
        if isinstance(dugum, (ast.FunctionDef, ast.AsyncFunctionDef)):
            tanim_aninda = [*dugum.decorator_list, *dugum.args.defaults, *dugum.args.kw_defaults]
            for alt in tanim_aninda:
                if alt is not None:
                    _tara(alt)
            return
        if isinstance(dugum, ast.Lambda):
            for alt in [*dugum.args.defaults, *dugum.args.kw_defaults]:
                if alt is not None:
                    _tara(alt)
            return
        if isinstance(dugum, ast.Call) and isinstance(dugum.func, ast.Attribute):
            ad = dugum.func.attr
            if ad in ("setdefault", "pop", "__setitem__", "__delitem__") and dugum.args and _anahtar_mi(dugum.args[0]):
                satirlar.append(dugum.lineno)
            if ad == "update":
                for a in dugum.args:
                    if isinstance(a, ast.Dict) and any(_anahtar_mi(k) for k in a.keys):
                        satirlar.append(dugum.lineno)
                if any(k.arg == "PEMF_SIMULATE" for k in dugum.keywords):
                    satirlar.append(dugum.lineno)
        if isinstance(dugum, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
            hedefler = dugum.targets if isinstance(dugum, (ast.Assign, ast.Delete)) else [dugum.target]
            for h in hedefler:
                if isinstance(h, ast.Subscript) and _anahtar_mi(h.slice):
                    satirlar.append(dugum.lineno)
        for alt in ast.iter_child_nodes(dugum):
            _tara(alt)

    for d in agac.body:
        _tara(d)
    return satirlar


def _ayristir(kaynak: str) -> ast.Module:
    with warnings.catch_warnings():  # eski dosyalardaki geçersiz kaçış dizileri (\P, \s) gürültü yapmasın
        warnings.simplefilter("ignore", (DeprecationWarning, SyntaxWarning))
        return ast.parse(kaynak)


def test_KRITIK_PEMF_SIMULATE_modul_duzeyinde_YAZILMAZ():
    # test_*.py VE testlerin içe aktardığı yardımcılar (tests/**/*.py); TEK meşru yer conftest.py
    dosyalar = sorted(p for p in _TESTLER.rglob("*.py") if p.name != "conftest.py")
    assert sum(p.name.startswith("test_") for p in dosyalar) >= 300, (
        f"VAKUM: yalnız {len(dosyalar)} dosya tarandı — tarama bozuk"
    )
    ihlal = []
    for p in dosyalar:
        for satir in _modul_duzeyi_yazimlar(_ayristir(p.read_text(encoding="utf-8"))):
            ihlal.append(f"{p.relative_to(_TESTLER).as_posix()}:{satir}")
    assert not ihlal, (
        f"{len(ihlal)} test modülü MODÜL DÜZEYİNDE PEMF_SIMULATE yazıyor: {ihlal[:12]} — değer toplama "
        "sırasına bağlı kalır (tek dosya ≠ tam süit). Gerekiyorsa testin KENDİ fixture'ında monkeypatch ile iste."
    )


def test_KARSIT_KANIT_tarayici_ice_aktarma_anini_GORUR_fonksiyon_govdesini_SAYMAZ():
    """Tarayıcının kendisi: içe aktarma anında koşan yazımları SAYAR (üst düzey if/try, sınıf gövdesi,
    varsayılan argüman); fonksiyon gövdesini ve başka anahtarı SAYMAZ."""
    kaynak = (
        "import os\n"
        "os.environ.setdefault('PEMF_SIMULATE', '1')\n"
        "if True:\n"
        "    os.environ['PEMF_SIMULATE'] = '1'\n"
        "try:\n"
        "    os.environ.pop('PEMF_SIMULATE', None)\n"
        "except Exception:\n"
        "    pass\n"
        "os.environ.update({'PEMF_SIMULATE': '1'})\n"
        "del os.environ['PEMF_SIMULATE']\n"
        "os.environ.setdefault('BASKA', '1')\n"
        "def f(x=os.environ.pop('PEMF_SIMULATE', None)):\n"
        "    os.environ.setdefault('PEMF_SIMULATE', '1')\n"
        "class K:\n"
        "    os.environ.pop('PEMF_SIMULATE', None)\n"
        "    def g(self):\n"
        "        os.environ.pop('PEMF_SIMULATE', None)\n"
    )
    assert _modul_duzeyi_yazimlar(ast.parse(kaynak)) == [2, 4, 6, 9, 10, 12, 15]
