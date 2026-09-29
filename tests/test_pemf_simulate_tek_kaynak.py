# Author: mertaygn, cglrgrkn
"""D0Ö.11 (B-10.222 = DENETIM-12 P1) KAPISI — `PEMF_SIMULATE` test modüllerinde DEĞİL, conftest'te TEK yerde.

ARIZA (ölçüldü, DENETIM-12 §3.2): 72 test modülü modül gövdesinde `PEMF_SIMULATE` yazıyordu
(16 `setdefault('1')` + 56 `pop`). Değeri TOPLAMA SIRASI belirliyordu: tam süitte toplama
sonunda YOK, tek dosya koşumunda (ör. `tests/test_toplu_silme.py`) '1'. Yani aynı test dosyası
süitte ve tek başına FARKLI ortamda koşuyordu. Ürün bu değişkeni lifespan'de okuyup hw-sim iş
parçacığını başlatıyor (`api_server.py:4132`) ve o iş parçacığı her 0,5 sn `stm='online'`
yazıyor → STM durumuna dayanan kapılar (İG-6.1 / B-1.19) tek dosya koşumunda güvenilmez.

ÇÖZÜM: 72 modül-düzeyi deyim silindi; `tests/conftest.py` süreç başında TEK normalizasyon yapar
(`os.environ.pop("PEMF_SIMULATE", None)`), toplama bitince değeri kaydeder ve her testten sonra
env'de `PEMF_SIMULATE` ya da canlı `hw-sim` kaldıysa o testi KIRMIZI yapar (çalışma-anı sızıntısı).
⚠️ Sanal donanım ENV İLE İSTENMEZ: lifespan hw-sim'i süreç başına BİR KEZ başlatırdı ve o daemon
durdurulamaz (D0Ö.10'dan beri conftest arka plan başlatıcısını zaten engelliyor). Sim davranışı
gereken test döngüyü doğrudan ve sınırlı turla koşturur ya da canlı durumu elle kurar.

KAPILAR:
  (1) Davranış: toplama SONUNDA `PEMF_SIMULATE` tanımsız — tek dosya koşumunda da.
  (2) Yapı (AST): `tests/**/*.py` (yalnız `tests/conftest.py` hariç — tek meşru yer) içe aktarma
      anında koşan kodunda (modül gövdesi, üst düzey if/try, sınıf gövdesi, dekoratör, varsayılan
      argüman) `PEMF_SIMULATE` yazımı YOK: setdefault/pop/[]=/del/update (sözlük, `dict(...)`,
      çift listesi, anahtar sözcük)/`|=`/`__setitem__`/`__delitem__`/putenv/unsetenv/setenv/delenv.
      Vakum koruması ≥300 test dosyası.
  (3) Çalışma anı: env'e yazıp geri almayan test (sonda, alt süreçte) conftest bekçisince KIRMIZI.
MUTASYON: herhangi bir test dosyasına modül düzeyinde `os.environ.setdefault("PEMF_SIMULATE", "1")`
eklemek → (2) KIRMIZI; o dosya tek başına toplanınca (1) de KIRMIZI. Conftest bekçisi silinirse (3).
"""

import ast
import os
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

_TESTLER = Path(__file__).resolve().parent
_BU_DOSYA = "tests/test_pemf_simulate_tek_kaynak.py"
_SONDA_ORTAMI = "D0O11_SIZINTI_SONDASI"
#: Anahtarı ilk argüman (ya da anahtar sözcük değeri) olarak alan env yazıcıları.
_YAZICILAR = ("setdefault", "pop", "__setitem__", "__delitem__", "putenv", "unsetenv", "setenv", "delenv")


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

    def _sozluk_anahtarli_mi(dugum) -> bool:
        return isinstance(dugum, ast.Dict) and any(_anahtar_mi(k) for k in dugum.keys)

    def _update_anahtarli_mi(cagri: ast.Call) -> bool:
        if any(k.arg == "PEMF_SIMULATE" for k in cagri.keywords):
            return True
        for a in cagri.args:
            if _sozluk_anahtarli_mi(a):
                return True
            if isinstance(a, ast.Call) and getattr(a.func, "id", "") == "dict":
                if any(k.arg == "PEMF_SIMULATE" for k in a.keywords) or any(_sozluk_anahtarli_mi(x) for x in a.args):
                    return True
            if isinstance(a, (ast.List, ast.Tuple, ast.Set)) and any(
                isinstance(e, (ast.Tuple, ast.List)) and e.elts and _anahtar_mi(e.elts[0]) for e in a.elts
            ):
                return True
        return False

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
            if ad in _YAZICILAR and (
                any(_anahtar_mi(a) for a in dugum.args) or any(_anahtar_mi(k.value) for k in dugum.keywords)
            ):
                satirlar.append(dugum.lineno)
            if ad == "update" and _update_anahtarli_mi(dugum):
                satirlar.append(dugum.lineno)
        if isinstance(dugum, ast.AugAssign) and _sozluk_anahtarli_mi(dugum.value):  # os.environ |= {...}
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
    return sorted(set(satirlar))


def _ayristir(kaynak: str) -> ast.Module:
    with warnings.catch_warnings():  # eski dosyalardaki geçersiz kaçış dizileri (\P, \s) gürültü yapmasın
        warnings.simplefilter("ignore", (DeprecationWarning, SyntaxWarning))
        return ast.parse(kaynak)


def test_KRITIK_PEMF_SIMULATE_modul_duzeyinde_YAZILMAZ():
    # test_*.py VE testlerin içe aktardığı yardımcılar (tests/**/*.py); TEK meşru yer tests/conftest.py
    tek_mesru = (_TESTLER / "conftest.py").resolve()
    dosyalar = sorted(p for p in _TESTLER.rglob("*.py") if p.resolve() != tek_mesru)
    test_sayisi = sum(p.name.startswith("test_") for p in dosyalar)
    assert test_sayisi >= 300, f"VAKUM: yalnız {test_sayisi} test dosyası tarandı — tarama bozuk"
    ihlal = []
    for p in dosyalar:
        for satir in _modul_duzeyi_yazimlar(_ayristir(p.read_text(encoding="utf-8"))):
            ihlal.append(f"{p.relative_to(_TESTLER).as_posix()}:{satir}")
    assert not ihlal, (
        f"{len(ihlal)} yerde MODÜL DÜZEYİNDE PEMF_SIMULATE yazılıyor: {ihlal[:12]} — değer toplama sırasına "
        "bağlı kalır (tek dosya ≠ tam süit). Sim davranışı gerekiyorsa döngüyü doğrudan ve sınırlı turla "
        "koştur ya da canlı durumu elle kur; env İLE İSTEME (hw-sim süreç başına bir kez başlar, durmaz)."
    )


def test_KARSIT_KANIT_tarayici_ice_aktarma_anini_GORUR_fonksiyon_govdesini_SAYMAZ():
    """Tarayıcının kendisi: içe aktarma anında koşan yazımları SAYAR (üst düzey if/try, sınıf gövdesi,
    dekoratör, varsayılan argüman; tüm yazıcı biçimleri); fonksiyon/lambda gövdesini ve başka anahtarı SAYMAZ."""
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
        "os.environ |= {'PEMF_SIMULATE': '1'}\n"
        "os.environ.update(dict(PEMF_SIMULATE='1'))\n"
        "os.environ.update([('PEMF_SIMULATE', '1')])\n"
        "os.environ.update(PEMF_SIMULATE='1')\n"
        "os.environ.__setitem__('PEMF_SIMULATE', '1')\n"
        "os.environ.__delitem__('PEMF_SIMULATE')\n"
        "os.environ.setdefault(key='PEMF_SIMULATE', default='1')\n"
        "os.putenv('PEMF_SIMULATE', '1')\n"
        "pytest.MonkeyPatch().setenv('PEMF_SIMULATE', '1')\n"
        "@dekor(os.environ.pop('PEMF_SIMULATE', None))\n"
        "def h():\n"
        "    pass\n"
        "g = lambda x=os.environ.pop('PEMF_SIMULATE', None): os.environ.setdefault('PEMF_SIMULATE', '1')\n"
        "os.environ.update({'BASKA': '1'})\n"
    )
    beklenen = [2, 4, 6, 9, 10, 12, 15, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 30]
    assert _modul_duzeyi_yazimlar(ast.parse(kaynak)) == beklenen


def _pytest_alt_sureci(dugum: str, ek_env: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    env.update(ek_env)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-p", "no:xdist", "-q", "-rE", dugum],
        cwd=str(_TESTLER.parent),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


@pytest.mark.skipif(os.environ.get(_SONDA_ORTAMI) != "1", reason="yalnız sızıntı kapısının alt sürecinde koşar")
def test_SONDA_PEMF_SIMULATE_birakir():
    """Kapı (3)'ün sondası: env'e monkeypatch'SİZ yazar ve geri ALMAZ → conftest bu testi ERROR yapmalı."""
    os.environ["PEMF_SIMULATE"] = "1"


def test_KRITIK_calisma_aninda_birakilan_PEMF_SIMULATE_testi_KIRMIZI_yapar():
    r = _pytest_alt_sureci(f"{_BU_DOSYA}::test_SONDA_PEMF_SIMULATE_birakir", {_SONDA_ORTAMI: "1"})
    cikti = (r.stdout or "")[-3000:] + (r.stderr or "")[-1500:]
    assert r.returncode != 0 and "1 error" in (r.stdout or ""), (
        f"env'e PEMF_SIMULATE bırakan sonda testi KIRMIZI olmadı — conftest sızıntı bekçisi kör (rc={r.returncode}):\n"
        f"{cikti}"
    )
    assert "çalışma-anı sızıntısı" in (r.stdout or ""), f"hata sızıntı bekçisinin iletisi değil:\n{cikti}"
