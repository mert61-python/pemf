# -*- coding: utf-8 -*-
"""D5-F · ATLAYAN KAPI ZORUNLU KİPTE DÜŞMELİ — eser yokluğuna bağlı HAM atlama meta kapısı (AST, 2026-10-27).

🔴 ÖLÇÜLEN DURUM (K5-F envanteri, HEAD 7f8f57c9): `tests/` içinde 481 atlama yeri; eser yokluğuna bağlı olanların çoğu (dosya / dizin
`.exists()`, `shutil.which`, `find_spec`, `importorskip`, ürünün model çözücüsü) `capraz` kanalının DIŞINDAYDI. Yayın öncesi süit
(`scripts/yayin_oncesi_suit.ps1`) `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1` + `PEMF_GOLDEN_REQUIRED=1` ile koşar; bu bayraklar düz `skipif` /
`pytest.skip` / `importorskip`i GÖREMEZ → eser eksik makinede kapılar sessizce atlanır, süit YEŞİL biter (ölçüldü: ör. `apps/ui/src`
gizli + ZORUNLU=1 → 54 skipped, varsayılanla birebir). D4.04 / D4.09 / D5.48 tek tek dönüştürmüştü; bu kapı SINIFI kilitler.

KAPI: her `tests/**/*.py` AST ile taranır. "Ham eser atlaması" = (a) `skipif(<koşul>)` ya da gövde / fikstür içi `pytest.skip`
(koşul = onu saran `if` testleri) ve koşul — modül düzeyi / aynı işlevdeki atamalar ve modül düzeyi işlevler BİR düzey açılarak —
bir eser sorgusu içerir (`.exists()` / `.is_file()` / `.is_dir()` / `.glob()`, `os.path.isfile|isdir`, `shutil.which`, `find_spec`,
`find_installed_model`, `eser_var_mi`) ya da `except ImportError` içinde atlar; (b) her `pytest.importorskip`.
TUR 2 (çürütücü bulguları, 2026-10-27): `try` gövdesinde içe aktarma varken `except Exception` / `BaseException` / çıplak
`except` içindeki atlama da `except ImportError` gibi HAM; aynı yolda ÖNCEKİ bir `if <eser sorgusu>: return` (döngü içinde de)
ardından gelen KOŞULSUZ atlama HAM (erken dönüş: atlamaya yalnız eser YOKKEN ulaşılır); test parametresi
`@pytest.mark.parametrize` değerlerine açılır (`pytest.param(shutil.which("pwsh"))` → `if kabuk is None: pytest.skip`).
BAĞLI sayılır (ham DEĞİL) — adın VARLIĞI değil YAPI: `skipif` koşulu ZORUNLU doğruyken YAPISAL olarak yanlıştır
(`(…) and not <zorunlu>`, `not (<zorunlu> or …)`; `<zorunlu>` = `capraz.ZORUNLU`, `golden.eser.zorunlu_mu()` …); `pytest.skip`i
saran bir `if` gövdesinde o yapıdadır ya da `if <zorunlu>:` dalının `else`indedir; aynı yolda ÖNCEKİ bir kardeş
`if <zorunlu>: pytest.fail(...)` (koşul ZORUNLU'da yapısal doğru, gövde koşulsuz düşürür) vardır; ya da atlama nedeni `sqlcipher`
taşır (A-46 yerel kapısı o atlamayı HER koşuda kırmızı yapar). KARŞIT: `skipif((X is None) and capraz.ZORUNLU)` (ters yön) ve
`if not ZORUNLU: pytest.fail` (ters dal) HAM.
TUR 3 (çürütücü 2 bulguları c2 · c2b · c4b · c8 · c9 · c11 · c12, 2026-10-27): `<zorunlu>` adın DESENİYLE değil TANIMIYLA bağlıdır —
dosyada bağlanan ad (atama / `def` / parametre / döngü hedefi …) yalnız HER tanımı ZORUNLU'da yapısal doğruysa, `tests/` yardımcısından
içe aktarılan ad oradaki tanımıyla; satır içi ortam denetimi yalnız `os.environ.get` / `os.getenv` + TAM ad listesi
(`PEMF_CAPRAZ_KAYNAK_ZORUNLU`, `PEMF_GOLDEN_REQUIRED`) ile. Geniş `except`te `try` gövdesindeki işlev çağrısı (aynı modül / `self.` /
`tests/` yardımcısı) 3 düzeye kadar açılır ve gövdesinde içe aktarma varsa içe aktarmadır; `except FileNotFoundError` (ikili / dosya yok)
ImportError gibi HAM. Atlama eşdeğerleri de atlamadır: `pytest.skip.Exception` / `pytest.xfail` / `unittest.SkipTest` / `Skipped` /
`self.skipTest` / `pytest.exit` (çağrı ya da çağrısız `raise`), koşullu `pytest.mark.skip`, `pytest.mark.xfail(<koşul>)`,
`skipif(condition=…)` ve ikinci konumsal koşul. Saran koşul varken de erken dönüş koşulları eklenir; saran koşul `if` dışında
`A and skip()` / `A or skip()` kısa devresi, koşullu ifade, `while` ve `for … else` (break koşulları) da sayılır. Atlama istisnası
yükselten `raise` (ve atlamayı yakalayan bloktaki çıplak `raise`) `if <zorunlu>:` dalını düşüren SAYMAZ.
TUR 3b (çürütücü 3 bulguları m1a · m1b · m2b · m3a · m3b, 2026-10-27): çağrılan ad bir düzey takma addan çözülür (`from pytest
import skip as _gec`, `_atla = pytest.skip`, `from unittest import SkipTest as _ST`); pytest işaretinin DİZE koşulu
(`skipif("PWSH is None")` — pytest onu modül globals'ıyla değerlendirir) ifadeye çevrilip aynı kurallarla taranır (unittest
biçimi değerlendirmez — dize hep doğru); geniş `except`te `try` gövdesindeki öznitelik çağrısının tabanı içe aktarılmış modül
DEĞİLSE (`_Y.al()`, `_Y().al()`, `self.f()`) yerel tanım `attr` adıyla açılır. AYRI KRİTİK kapı: ZORUNLU durumuna YAZIM
(`capraz.ZORUNLU = …`, `setattr(…, "ZORUNLU")`, `os.environ["PEMF_GOLDEN_REQUIRED"] = …` — anahtar sabite bağlı ad da —, `pop` /
`setdefault` / `update` / `clear` / `putenv`, `setenv` / `delenv` / `setitem(os.environ, …)`, `patch.dict(os.environ…)`) yalnız
`test_*` işlevinde `monkeypatch.` ile serbest: modül düzeyi (içe aktarmada koşar), fikstür ya da yardımcı işlevdeki yazım META'nın
bağlı saydığı `capraz.ZORUNLU` / satır içi ortam denetimini ZORUNLU kipte boşa çıkarır.
Ham atlama yalnız GEREKÇELİ izin listesindeki dosyada ve listedeki SAYIDA olabilir (cırcır: sayı düşerse liste de düşürülmeli —
bayat liste de KIRMIZI). Doğru yol: `capraz.atla_yoksa(yol, izlenen=…)`, `capraz.atla(sebep)`, `capraz.paket_yoksa_atla(ad)`.

Bilinen sınır (bilinçli): adlar en çok 3 düzey açılır ve başka modülden gelen adlar yalnız `tests/` içindeki modüllerden çözülür;
atlamayı SARMAYAN `continue` (döngüde sessiz geçiş, atlama yok) bu kapının değil dosyanın KARŞIT kolunun işidir
(`test_stm_bobin_sayisi_tek_kaynak.py`). Fikstür `params=` / `request.param` dolaylaması çözülmez. Yardımcı modülün DIŞINDAN
gelen (3. taraf / ürün) `zorunlu` adı desenle kabul edilir; `except OSError` / `PermissionError` (izin / platform yeteneği) eser
yokluğu SAYILMAZ (tek canlı örnek symlink izni — platform). Takma ad yalnız bir düzey çözülür; `getattr(pytest, "skip")`,
`vars(capraz)[…]` / `globals()` / `sys.modules` ile dolaylı atlama ya da durum yazımı taranmaz.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
KOK = TESTS.parent

#: Path yöntemleri / işlev adları — koşulda görülürse atlama ESER YOKLUĞUNA bağlıdır.
_ESER_YONTEMI = frozenset({"exists", "is_file", "is_dir", "glob", "rglob", "isfile", "isdir"})
_ESER_ISLEVI = frozenset({"which", "find_spec", "find_installed_model"})
_ESER_AD_PARCASI = ("eser_var",)
_BAGLI_AD = re.compile(r"zorunlu|required", re.I)
_ITHAL_HATASI = frozenset({"ImportError", "ModuleNotFoundError"})
#: TUR 2: `try` gövdesinde içe aktarma varken bunlar (ve çıplak `except`) da içe aktarma hatasını YAKALAR → ImportError gibi.
_GENIS_HATA = frozenset({"Exception", "BaseException"})
#: `try` gövdesinde bu çağrılar da içe aktarmadır (`import` / `from … import` deyimleri ayrıca).
_ITHAL_ISLEVI = frozenset({"import_module", "__import__", "exec_module", "run_path", "run_module", "load_module"})
#: TUR 3 (c2b): satır içi ortam denetimi YALNIZ yayın süitinin kurduğu bu bayraklarla bağlıdır (desen DEĞİL — `…_YEREL` HAM).
_ZORUNLU_ORTAM = frozenset({"PEMF_CAPRAZ_KAYNAK_ZORUNLU", "PEMF_GOLDEN_REQUIRED"})
#: TUR 3: ortamı GERÇEKTEN okuyan çağrılar (sahte sözlüğün `.get`i DEĞİL).
_ORTAM_OKUYUCU = frozenset({"os.environ.get", "environ.get", "os.getenv", "getenv"})
#: TUR 3 (c8 / c9): ZORUNLU kipte de SESSİZ geçen atlama eşdeğerleri — çağrı / `raise` adı nokta sınırında bunlardan biriyle biter
#: (`pytest.skip`, `pytest.mark.skip`, `pytest.skip.Exception`, `pytest.xfail`, `unittest.SkipTest`, `Skipped`, `self.skipTest` …).
_ATLAMA_SONEKI = (
    "skip",
    "skip.Exception",
    "xfail",
    "xfail.Exception",
    "SkipTest",
    "Skipped",
    "XFailed",
    "skipTest",
    "pytest.exit",
)
#: Bunlar istisna SINIFI — yalnız `raise` edildiğinde atlar (`hata = pytest.skip.Exception(...)` tek başına atlamaz).
_ISTISNA_SONEKI = ("skip.Exception", "xfail.Exception", "SkipTest", "Skipped", "XFailed")
#: TUR 3: eser yokluğunu istisnayla bildiren hata — `except FileNotFoundError: pytest.skip` (ikili / dosya yok) ImportError gibi HAM.
_ESER_HATASI = frozenset({"FileNotFoundError"})


@dataclass(frozen=True)
class Atlama:
    dosya: str
    satir: int
    tur: str
    neden: str


def _cagri_adi(fn: ast.AST) -> str:
    parca = []
    while isinstance(fn, ast.Attribute):
        parca.append(fn.attr)
        fn = fn.value
    if isinstance(fn, ast.Name):
        parca.append(fn.id)
    return ".".join(reversed(parca))


def _eser_sorgusu_var(dugumler) -> bool:
    for d in dugumler:
        for n in ast.walk(d):
            if not isinstance(n, ast.Call):
                continue
            ad = _cagri_adi(n.func)
            son = ad.rsplit(".", 1)[-1]
            if son in _ESER_YONTEMI or son in _ESER_ISLEVI or any(p in son for p in _ESER_AD_PARCASI):
                return True
    return False


def _cozumlu_ad(fn: ast.AST, m) -> str:
    """TUR 3b (m3b): çağrılan ad bir düzey takma addan çözülür — `from pytest import skip as _gec` → `pytest.skip`,
    `_gec = pytest.skip` → `pytest.skip`. Çözülemezse sözdizimsel ad."""
    ad = _cagri_adi(fn)
    if isinstance(fn, ast.Name) and m is not None:
        for b in m.baglama.get(fn.id, []):
            if b[0] == "ithal" and b[2] is not None:
                return f"{b[1]}.{b[2]}"
            if b[0] == "deger" and isinstance(b[1], (ast.Attribute, ast.Name)):
                return _cagri_adi(b[1])
    return ad


def _dize_kosulu(k: ast.AST) -> ast.AST:
    """TUR 3b (m3a): `skipif("PWSH is None")` → `PWSH is None` ifadesi (çözümlenemeyen dize olduğu gibi)."""
    if isinstance(k, ast.Constant) and isinstance(k.value, str):
        try:
            return ast.parse(k.value.strip(), mode="eval").body
        except SyntaxError:
            return k
    return k


def _atlama_adi_mi(ad: str) -> bool:
    """TUR 3 (c8 / c9): çağrı / `raise` adı bir atlama eşdeğeri mi (`_ATLAMA_SONEKI`, nokta sınırında)."""
    return any(ad == s or ad.endswith("." + s) for s in _ATLAMA_SONEKI)


def _atlama_istisnasi_mi(hedef: ast.AST | None, m: _Modul | None) -> bool:
    """`raise <hedef>` bir atlama mı: ad atlama eşdeğeri ya da dosyada atlama istisnasına bağlanmış ad (`hata = pytest.skip.Exception(…)`)."""
    if hedef is None:
        return False
    h = hedef.func if isinstance(hedef, ast.Call) else hedef
    if _atlama_adi_mi(_cagri_adi(h)) or _atlama_adi_mi(_cozumlu_ad(h, m)):
        return True
    if isinstance(h, ast.Name) and m is not None:
        for b in m.baglama.get(h.id, []):
            if b[0] == "deger":
                v = b[1].func if isinstance(b[1], ast.Call) else b[1]
                if _atlama_adi_mi(_cagri_adi(v)):
                    return True
    return False


def _sabit_dizge(n: ast.AST, m: _Modul | None) -> str | None:
    """Dizge sabiti ya da dosyada TEK kez dizge sabitine bağlanan ad (`_BAYRAK = "PEMF_…"`; `os.environ.get(_BAYRAK)`)."""
    if isinstance(n, ast.Constant) and isinstance(n.value, str):
        return n.value
    if isinstance(n, ast.Name) and m is not None:
        bag = m.baglama.get(n.id, [])
        if len(bag) == 1 and bag[0][0] == "deger":
            return _sabit_dizge(bag[0][1], None)
    return None


def _ortam_zorunlu_mu(n: ast.AST, m: _Modul | None) -> bool:
    """Satır içi ortam denetimi `os.environ.get("PEMF_GOLDEN_REQUIRED") == "1"` / `os.getenv(...) == "1"` (yayın süiti iki bayrağı da
    kurar). TUR 3 (c2b): ad TAM listede (`_ZORUNLU_ORTAM`, desen DEĞİL) ve okuyucu gerçek ortam (`_ORTAM_OKUYUCU`)."""
    if not (isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.ops[0], ast.Eq)):
        return False
    sol, sag = n.left, n.comparators[0]
    if isinstance(sol, ast.Constant) and sol.value == "1":
        sol, sag = sag, sol
    return (
        isinstance(sag, ast.Constant)
        and sag.value == "1"
        and isinstance(sol, ast.Call)
        and _cagri_adi(sol.func) in _ORTAM_OKUYUCU
        and bool(sol.args)
        and _sabit_dizge(sol.args[0], m) in _ZORUNLU_ORTAM
    )


def _islev_zorunlu_mu(isl: ast.AST, m: _Modul, gorulen: frozenset) -> bool:
    """TUR 3: yerel / yardımcı `def zorunlu_mu(): return <…>` — son deyimi `return` ve HER `return` değeri ZORUNLU'da yapısal doğru."""
    if not isinstance(isl, (ast.FunctionDef, ast.AsyncFunctionDef)) or not isl.body:
        return False
    if not isinstance(isl.body[-1], ast.Return):
        return False  # düşerek biten yol None (yanlış) döndürür
    donusler = [r for st in isl.body for r in _islev_disi_dolas(st) if isinstance(r, ast.Return)]
    return all(r.value is not None and _zorunluda_dogru(r.value, m, gorulen) for r in donusler)


def _ad_zorunlu_mu(m: _Modul | None, ad: str, gorulen: frozenset) -> bool:
    """TUR 3 (c2): `zorunlu|required` adı yalnız TANIMI ZORUNLU'da yapısal doğruysa bağlıdır. Dosyada bağlanan adın HER bağlaması
    (atama değeri / `def` dönüşü) doğru olmalı; değeri bilinmeyen bağlama (parametre, döngü hedefi, `with … as`, demet açma …)
    BAĞLI DEĞİL. `tests/` yardımcısından içe aktarılan ad oradaki tanımıyla; dosyada hiç bağlanmamış / dışarıdan gelen ad desenle."""
    if not _BAGLI_AD.search(ad):
        return False
    if m is None:
        return True
    anahtar = (id(m), ad)
    if anahtar in gorulen:
        return False  # döngüsel tanım — bağlı SAYILMAZ (fail-closed)
    gorulen = gorulen | {anahtar}
    for b in m.baglama.get(ad, []):
        if b[0] == "deger":
            tamam = _zorunluda_dogru(b[1], m, gorulen)
        elif b[0] == "islev":
            tamam = _islev_zorunlu_mu(b[1], m, gorulen)
        elif b[0] == "ithal":
            ym = _yardimci_modul(b[1]) if b[2] is not None else None
            tamam = True if ym is None else _ad_zorunlu_mu(ym, b[2], gorulen)
        else:
            tamam = False
        if not tamam:
            return False
    return True


def _zorunlu_dugumu(n: ast.AST, m: _Modul | None = None, gorulen: frozenset = frozenset()) -> bool:
    """`ZORUNLU`, `capraz.ZORUNLU`, `zorunlu_mu()`, `golden.eser.zorunlu_mu()` (ad / öznitelik / argümansız çağrı) ya da satır içi
    ortam denetimi (`_ortam_zorunlu_mu`). TUR 3: ad TANIMIYLA çözülür (`_ad_zorunlu_mu`); `tests/` yardımcı modülünün özniteliği
    (`capraz.ZORUNLU`) o modüldeki tanımıyla."""
    if _ortam_zorunlu_mu(n, m):
        return True
    if isinstance(n, ast.Call) and not n.args and not n.keywords:
        n = n.func
    if isinstance(n, ast.Name):
        return _ad_zorunlu_mu(m, n.id, gorulen)
    if isinstance(n, ast.Attribute):
        if not _BAGLI_AD.search(n.attr):
            return False
        if m is not None and isinstance(n.value, ast.Name) and n.value.id in m.ithal:
            modad, oz = m.ithal[n.value.id]
            ym = _yardimci_modul(modad if oz is None else f"{modad}.{oz}")
            if ym is not None:
                return _ad_zorunlu_mu(ym, n.attr, gorulen)
        return True
    return False


def _zorunluda_yanlis(k: ast.AST, m: _Modul | None = None, gorulen: frozenset = frozenset()) -> bool:
    """TUR 2 (lc1 / lc13): ZORUNLU doğruyken koşul YAPISAL olarak YANLIŞ mı — `(…) and not <zorunlu>`, `not (<zorunlu> or …)`.

    Adın koşulda GEÇMESİ yetmez: `(X is None) and capraz.ZORUNLU` ZORUNLU'da atlar (ters yön), `X is None or ZORUNLU` de."""
    if isinstance(k, ast.UnaryOp) and isinstance(k.op, ast.Not):
        return _zorunluda_dogru(k.operand, m, gorulen)
    if isinstance(k, ast.BoolOp):
        alt = [_zorunluda_yanlis(v, m, gorulen) for v in k.values]
        return any(alt) if isinstance(k.op, ast.And) else all(alt)
    return False


def _zorunluda_dogru(k: ast.AST, m: _Modul | None = None, gorulen: frozenset = frozenset()) -> bool:
    """ZORUNLU doğruyken koşul YAPISAL olarak DOĞRU mu — `<zorunlu>`, `<zorunlu> or …`, `not (… and not <zorunlu>)`."""
    if _zorunlu_dugumu(k, m, gorulen):
        return True
    if isinstance(k, ast.UnaryOp) and isinstance(k.op, ast.Not):
        return _zorunluda_yanlis(k.operand, m, gorulen)
    if isinstance(k, ast.BoolOp):
        alt = [_zorunluda_dogru(v, m, gorulen) for v in k.values]
        return any(alt) if isinstance(k.op, ast.Or) else all(alt)
    return False


def _islev_disi_dolas(d: ast.AST):
    """`ast.walk` gibi — iç içe işlev / lambda / sınıf GÖVDELERİNE inmez (onların `return`ü bu yolu kesmez)."""
    yigin = [] if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)) else [d]
    while yigin:
        n = yigin.pop()
        yield n
        yigin.extend(
            c
            for c in ast.iter_child_nodes(n)
            if not isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef))
        )


def _cagri_tanimlari(m: _Modul, fn: ast.AST) -> list[tuple[_Modul, ast.AST]]:
    """TUR 3 (c4b): çağrılan işlevin tanım(lar)ı — aynı modülde `f()` (iç içe tanımlar dahil), `self.f()` / `cls.f()`, ya da `tests/`
    yardımcısından içe aktarılan `f()` / `yardimci.f()`."""
    sonuc = []
    if isinstance(fn, ast.Name):
        for b in m.baglama.get(fn.id, []):
            if b[0] == "islev":
                sonuc.append((m, b[1]))
            elif b[0] == "ithal" and b[2] is not None:
                ym = _yardimci_modul(b[1])
                if ym is not None:
                    sonuc += [(ym, x[1]) for x in ym.baglama.get(b[2], []) if x[0] == "islev"]
    elif isinstance(fn, ast.Attribute) and not (isinstance(fn.value, ast.Name) and fn.value.id in m.ithal):
        # TUR 3b (m2b): taban içe aktarılmış modül DEĞİLSE (self / cls / sınıf adı / örnek / çağrı) yerel tanım
        sonuc += [(m, x[1]) for x in m.baglama.get(fn.attr, []) if x[0] == "islev"]
    elif isinstance(fn, ast.Attribute):
        if fn.value.id in m.ithal:
            modad, oz = m.ithal[fn.value.id]
            ym = _yardimci_modul(modad if oz is None else f"{modad}.{oz}")
            if ym is not None:
                sonuc += [(ym, x[1]) for x in ym.baglama.get(fn.attr, []) if x[0] == "islev"]
    return sonuc


def _ithal_var(govde, m: _Modul | None = None, derinlik: int = 3, _gorulen: set | None = None) -> bool:
    """`try` gövdesinde içe aktarma var mı (deyim ya da `importlib.import_module` / `__import__` / `exec_module` …).

    TUR 3 (c4b): gövdedeki işlev çağrıları (`_cagri_tanimlari`) `derinlik` düzey açılır — `try: yaml = _yaml_al()` (içinde
    `import yaml`) + `except Exception: pytest.skip` da içe aktarma korumasıdır."""
    gorulen = set() if _gorulen is None else _gorulen
    for st in govde:
        for n in _islev_disi_dolas(st):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                return True
            if not isinstance(n, ast.Call):
                continue
            if _cagri_adi(n.func).rsplit(".", 1)[-1] in _ITHAL_ISLEVI:
                return True
            if m is None or derinlik <= 0:
                continue
            for hm, isl in _cagri_tanimlari(m, n.func):
                if id(isl) not in gorulen:
                    gorulen.add(id(isl))
                    if _ithal_var(isl.body, hm, derinlik - 1, gorulen):
                        return True
    return False


def _raise_dusurur(st: ast.Raise, m: _Modul | None) -> bool:
    """TUR 3 (c12): `raise` testi DÜŞÜRÜR mü — atlama / xfail istisnası (`raise pytest.skip.Exception(...)`, `raise unittest.SkipTest`,
    atlama istisnasına bağlanmış ad) DÜŞÜRMEZ; çıplak `raise` yalnız atlama istisnasını da yakalayabilen bloktaysa (`except
    pytest.skip.Exception` / `BaseException` / çıplak `except`) DÜŞÜRMEZ."""
    if st.exc is None:
        p = m.ebeveyn.get(st) if m is not None else None
        while p is not None and not isinstance(
            p, (ast.ExceptHandler, ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)
        ):
            p = m.ebeveyn.get(p)
        if not isinstance(p, ast.ExceptHandler):
            return True  # yakalanan istisna yok → RuntimeError (düşer)
        if p.type is None:
            return False
        adlar = {_cagri_adi(x) for x in (p.type.elts if isinstance(p.type, ast.Tuple) else [p.type])}
        return not any(a == "BaseException" or _atlama_adi_mi(a) or a.endswith("OutcomeException") for a in adlar)
    return not _atlama_istisnasi_mi(st.exc, m)


def _dusurur(govde, m: _Modul | None = None) -> bool:
    """Blok KOŞULSUZ düşürür mü: üst düzey deyimlerinden biri `pytest.fail(...)` / `fail(...)` ya da düşüren `raise` (TUR 3:
    `_raise_dusurur` — atlama istisnası yükselten `raise` SAYILMAZ)."""
    for st in govde:
        if isinstance(st, ast.Raise) and _raise_dusurur(st, m):
            return True
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
            if _cagri_adi(st.value.func).rsplit(".", 1)[-1] == "fail":
                return True
    return False


def _parametre_degerleri(isl, ad: str) -> list[ast.AST]:
    """TUR 2 (DEV_C3:141): `@pytest.mark.parametrize("ad, …", <değerler>)` ile test parametresine gelen değer düğümleri."""
    if not isinstance(isl, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    if ad not in {a.arg for a in (*isl.args.posonlyargs, *isl.args.args, *isl.args.kwonlyargs)}:
        return []
    sonuc = []
    for dek in isl.decorator_list:
        if not (isinstance(dek, ast.Call) and _cagri_adi(dek.func).rsplit(".", 1)[-1] == "parametrize"):
            continue
        adlar_d = dek.args[0] if dek.args else next((k.value for k in dek.keywords if k.arg == "argnames"), None)
        degerler = (
            dek.args[1] if len(dek.args) > 1 else next((k.value for k in dek.keywords if k.arg == "argvalues"), None)
        )
        if isinstance(adlar_d, ast.Constant) and isinstance(adlar_d.value, str):
            adlar = {s.strip() for s in adlar_d.value.split(",")}
        elif isinstance(adlar_d, (ast.List, ast.Tuple)):
            adlar = {e.value for e in adlar_d.elts if isinstance(e, ast.Constant)}
        else:
            adlar = set()
        if ad in adlar and degerler is not None:
            sonuc.append(degerler)
    return sonuc


def _metin(n: ast.AST | None) -> str:
    if n is None:
        return ""
    if isinstance(n, ast.Constant) and isinstance(n.value, str):
        return n.value
    try:
        return ast.unparse(n)
    except Exception:  # noqa: BLE001 — yalnız neden METNİ; çözümlenemezse boş (karar koşula dayanır)
        return ""


class _Modul:
    """Bir kaynağın AST'si + modül düzeyi atamalar / işlevler / içe aktarmalar (işlev ve sınıf GÖVDELERİ hariç her düzey)."""

    def __init__(self, kaynak: str):
        self.agac = ast.parse(kaynak)
        self.ebeveyn: dict[ast.AST, ast.AST] = {}
        for n in ast.walk(self.agac):
            for c in ast.iter_child_nodes(n):
                self.ebeveyn[c] = n
        #: TUR 3: dosyanın HER düzeyindeki ad bağlamaları — ("deger", <değer>) · ("islev", <def>) · ("ithal", <modül>, <ad|None>) ·
        #: ("bilinmez",) (parametre, döngü / `with` hedefi, demet açma, artırımlı atama, sınıf, `except … as`).
        self.baglama: dict[str, list[tuple]] = {}

        def bag(ad: str, *v) -> None:
            self.baglama.setdefault(ad, []).append(v)

        for n in ast.walk(self.agac):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                if not isinstance(n, ast.Lambda):
                    bag(n.name, "islev", n)
                a = n.args
                for x in (*a.posonlyargs, *a.args, *a.kwonlyargs, a.vararg, a.kwarg):
                    if x is not None:
                        bag(x.arg, "bilinmez")
            elif isinstance(n, ast.ClassDef):
                bag(n.name, "bilinmez")
            elif isinstance(n, ast.Import):
                for a in n.names:
                    bag(a.asname or a.name.split(".")[0], "ithal", a.name if a.asname else a.name.split(".")[0], None)
            elif isinstance(n, ast.ImportFrom):
                for a in n.names:
                    if n.module and not n.level:
                        bag(a.asname or a.name, "ithal", n.module, a.name)
                    else:
                        bag(a.asname or a.name, "bilinmez")
            elif isinstance(n, ast.ExceptHandler) and n.name:
                bag(n.name, "bilinmez")
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                p = self.ebeveyn.get(n)
                if isinstance(p, ast.Assign) and any(t is n for t in p.targets):
                    bag(n.id, "deger", p.value)
                elif isinstance(p, (ast.AnnAssign, ast.NamedExpr)) and p.target is n:
                    if p.value is not None:
                        bag(n.id, "deger", p.value)
                else:
                    bag(n.id, "bilinmez")
        self.atama: dict[str, list[ast.AST]] = {}
        self.islev: dict[str, ast.AST] = {}
        self.ithal: dict[str, tuple[str, str | None]] = {}
        yigin = list(self.agac.body)
        while yigin:
            st = yigin.pop()
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.islev.setdefault(st.name, st)
                continue
            if isinstance(st, ast.ClassDef):
                continue
            if isinstance(st, (ast.Assign, ast.AnnAssign)) and st.value is not None:
                for h in st.targets if isinstance(st, ast.Assign) else [st.target]:
                    if isinstance(h, ast.Name):
                        self.atama.setdefault(h.id, []).append(st.value)
            elif isinstance(st, ast.Import):
                for a in st.names:
                    self.ithal[a.asname or a.name.split(".")[0]] = (a.name if a.asname else a.name.split(".")[0], None)
            elif isinstance(st, ast.ImportFrom) and st.module and not st.level:
                for a in st.names:
                    self.ithal[a.asname or a.name] = (st.module, a.name)
            yigin.extend(c for c in ast.iter_child_nodes(st) if isinstance(c, ast.stmt))


_MODULLER: dict[str, _Modul | None] = {}


def _yardimci_modul(ad: str) -> _Modul | None:
    """`tests/` içindeki yardımcı / test modülü (`ad` → `tests/<ad>.py`); 3. taraf ya da ürün paketi → None."""
    if ad not in _MODULLER:
        yol = TESTS / (ad.replace(".", "/") + ".py")
        try:
            _MODULLER[ad] = _Modul(yol.read_text(encoding="utf-8")) if yol.is_file() else None
        except SyntaxError:
            _MODULLER[ad] = None
    return _MODULLER[ad]


def _yerel_atamalar(isl: ast.AST | None) -> dict[str, list[ast.AST]]:
    yerel: dict[str, list[ast.AST]] = {}
    if isl is not None:
        for n in ast.walk(isl):
            if isinstance(n, (ast.Assign, ast.AnnAssign)) and getattr(n, "value", None) is not None:
                for h in n.targets if isinstance(n, ast.Assign) else [n.target]:
                    if isinstance(h, ast.Name):
                        yerel.setdefault(h.id, []).append(n.value)
    return yerel


def _ac(m: _Modul, dugumler, isl, derinlik: int = 3) -> list[ast.AST]:
    """Koşuldaki adları `derinlik` düzey açar: işlev içi / modül düzeyi atamalar, modül işlevlerinin gövdesi, `tests/`
    içindeki modüllerden içe aktarılan adlar (`from aparat import PWSH`, `import mosquitto_aparat as ma` → `ma.ikili()`) ve
    `parametrize` ile gelen test parametreleri (TUR 2)."""
    sonuc = list(dugumler)
    gorulen = {id(d) for d in dugumler}
    sinir = [(m, d, isl) for d in dugumler]

    def modulden(ym: _Modul | None, oz: str):
        if ym is None:
            return []
        h = [(ym, x, None) for x in ym.atama.get(oz, [])]
        if oz in ym.islev:
            h.append((ym, ym.islev[oz], ym.islev[oz]))
        return h

    for _ in range(derinlik):
        yeni = []
        for mm, d, il in sinir:
            yerel = _yerel_atamalar(il)
            for n in ast.walk(d):
                hedef = []
                if isinstance(n, ast.Name):
                    hedef += [(mm, x, il) for x in yerel.get(n.id, [])]
                    hedef += [(mm, x, None) for x in mm.atama.get(n.id, [])]
                    if n.id in mm.islev and mm.islev[n.id] is not il:
                        hedef.append((mm, mm.islev[n.id], mm.islev[n.id]))
                    if n.id in mm.ithal and mm.ithal[n.id][1] is not None:
                        modad, oz = mm.ithal[n.id]
                        hedef += modulden(_yardimci_modul(modad), oz)
                    hedef += [(mm, x, None) for x in _parametre_degerleri(il, n.id)]
                elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in mm.ithal:
                    modad, oz = mm.ithal[n.value.id]
                    hedef += modulden(_yardimci_modul(modad if oz is None else f"{modad}.{oz}"), n.attr)
                for hm, hx, hi in hedef:
                    if id(hx) not in gorulen:
                        gorulen.add(id(hx))
                        sonuc.append(hx)
                        yeni.append((hm, hx, hi))
        sinir = yeni
    return sonuc


def tara(kaynak: str, dosya: str) -> list[Atlama]:
    """Bir kaynak metindeki HAM eser atlamalarını döndürür (bağlı olanlar ve eser dışı atlamalar hariç)."""
    m = _Modul(kaynak)

    def islevi(n):
        p = m.ebeveyn.get(n)
        while p is not None and not isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
            p = m.ebeveyn.get(p)
        return p

    def hata_adlari(tur) -> set[str]:
        """`except` türünün adları; dosyada demete / ada bağlanmış ad bir düzey açılır (`_HATALAR = (ImportError, OSError)`)."""
        if tur is None:
            return set()
        adlar = set()
        for x in tur.elts if isinstance(tur, ast.Tuple) else [tur]:
            adlar.add(_cagri_adi(x))
            if isinstance(x, ast.Name):
                for b in m.baglama.get(x.id, []):
                    if b[0] == "deger":
                        v = b[1]
                        adlar.update(_cagri_adi(y) for y in (v.elts if isinstance(v, (ast.Tuple, ast.List)) else [v]))
        return adlar

    def saran_kosullar(n):
        """Saran `if` testleri + dal yönü (True = gövde, False = `else`) + içe aktarma hatasını yakalayan `except` içinde mi.

        TUR 3: `A and skip()` / `A or skip()` kısa devresi (önceki değerler; `or`da yön False), koşullu ifade, `while` ve
        `for` / `while` … `else` (gövdedeki `if X: break` koşulları, yön False) de saran koşuldur."""
        kosul, yon, ithal = [], [], False
        cur, p = n, m.ebeveyn.get(n)
        while p is not None and not isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module, ast.ClassDef)):
            if isinstance(p, (ast.If, ast.IfExp, ast.While)) and cur is not p.test:
                ic_govde = cur is p.body if isinstance(p, ast.IfExp) else any(x is cur for x in p.body)
                kosul.append(p.test)
                yon.append(ic_govde)
            if isinstance(p, (ast.For, ast.AsyncFor, ast.While)) and any(x is cur for x in p.orelse):
                for st in p.body:
                    for x in _islev_disi_dolas(st):
                        if isinstance(x, ast.If) and any(isinstance(r, ast.Break) for r in _islev_disi_dolas(x)):
                            kosul.append(x.test)
                            yon.append(False)
            elif isinstance(p, ast.BoolOp):
                i = next((i for i, v in enumerate(p.values) if v is cur), 0)
                for v in p.values[:i]:
                    kosul.append(v)
                    yon.append(isinstance(p.op, ast.And))
            elif isinstance(p, ast.ExceptHandler):
                tur = p.type
                adlar = hata_adlari(tur)
                if adlar & (_ITHAL_HATASI | _ESER_HATASI):
                    ithal = True
                elif (tur is None or adlar & _GENIS_HATA) and _ithal_var(m.ebeveyn[p].body, m):
                    ithal = True  # TUR 2 (lc5 / lc6) + TUR 3 (c4b): `try: import …` / `try: _yaml_al()` + geniş `except` = ImportError gibi
            cur, p = p, m.ebeveyn.get(p)
        return kosul, yon, ithal

    def onceki_kardesler(n):
        """n'ye giden yolda, işlev / modül gövdesine kadar her blokta n'den ÖNCE koşan deyimler (yakından uzağa)."""
        cur, p = n, m.ebeveyn.get(n)
        while p is not None:
            for alan in ("body", "orelse", "finalbody"):
                blok = getattr(p, alan, None)
                if isinstance(blok, list):
                    i = next((i for i, x in enumerate(blok) if x is cur), None)
                    if i is not None:
                        yield from reversed(blok[:i])
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module, ast.ClassDef)):
                return
            cur, p = p, m.ebeveyn.get(p)

    def skip_bagli(n, kosul, yon) -> bool:
        """`pytest.skip` ZORUNLU kipte YAPISAL olarak ulaşılamaz mı (saran dal ya da önceki `if <zorunlu>: fail`)."""
        if any(_zorunluda_yanlis(k, m) if govde else _zorunluda_dogru(k, m) for k, govde in zip(kosul, yon)):
            return True
        return any(
            isinstance(st, ast.If) and _zorunluda_dogru(st.test, m) and _dusurur(st.body, m)
            for st in onceki_kardesler(n)
        )

    def erken_donus_kosullari(n) -> list[ast.AST]:
        """TUR 2 (lc2 / NSIS A3_3): önceki deyimlerdeki `if <…>: return` testleri — koşulsuz atlamaya yalnız onlar YANLIŞKEN ulaşılır."""
        k = []
        for st in onceki_kardesler(n):
            for x in _islev_disi_dolas(st):
                if isinstance(x, ast.If) and any(isinstance(r, ast.Return) for r in _islev_disi_dolas(x)):
                    k.append(x.test)
        return k

    sonuc = []
    for n in ast.walk(m.agac):
        if isinstance(n, ast.Call):
            ad, argl, anahtar = _cozumlu_ad(n.func, m), n.args, n.keywords
            if any(ad == s or ad.endswith("." + s) for s in _ISTISNA_SONEKI) and not isinstance(
                m.ebeveyn.get(n), ast.Raise
            ):
                continue  # istisna nesnesi kuruldu ama yükseltilmedi — atlama değil (yükselten `raise` aşağıda)
        elif isinstance(n, ast.Raise) and n.exc is not None and not isinstance(n.exc, ast.Call):
            # TUR 3: çağrısız `raise unittest.SkipTest` ya da atlama istisnasına bağlanmış ad (`raise hata`)
            if not _atlama_istisnasi_mi(n.exc, m):
                continue
            ad, argl, anahtar = _cagri_adi(n.exc), [], []
            if not _atlama_adi_mi(ad):
                ad = "skip.Exception"  # ada bağlı atlama istisnası — tür adı için
        else:
            continue
        son = ad.rsplit(".", 1)[-1]
        neden_d = next((k.value for k in anahtar if k.arg == "reason"), None)
        isl = islevi(n)
        isaret_xfail = ad == "mark.xfail" or ad.endswith(".mark.xfail")
        kosullar = []
        if son in ("skipif", "skipIf", "skipUnless") or isaret_xfail:
            # TUR 3: pytest işaretinde HER konumsal argüman ve `condition=` bir koşuldur (biri doğruysa atlar); unittest biçiminde
            # yalnız ilki (ikincisi neden). Koşulsuz işaret (`skipif(reason=…)`, `mark.xfail(reason=…)`) koşulsuz atlama gibi.
            unittest_bicimi = son in ("skipIf", "skipUnless")
            kosullar = list(argl[:1] if unittest_bicimi else argl) + [k.value for k in anahtar if k.arg == "condition"]
            if not unittest_bicimi:  # TUR 3b (m3a): pytest dize koşulunu modül globals'ıyla DEĞERLENDİRİR
                kosullar = [_dize_kosulu(k) for k in kosullar]
            if unittest_bicimi and neden_d is None and len(argl) > 1:
                neden_d = argl[1]
        if kosullar:
            ithal = False
            if son == "skipUnless":
                kosul = [k for k in kosullar if not _zorunluda_dogru(k, m)]
            else:
                kosul = [k for k in kosullar if not _zorunluda_yanlis(k, m)]
            bagli = not kosul
            tur = "mark.xfail" if isaret_xfail else son
        elif _atlama_adi_mi(ad) or son in ("skipif", "skipIf", "skipUnless") or isaret_xfail:
            kosul, yon, ithal = saran_kosullar(n)
            if neden_d is None and argl:
                neden_d = argl[0]
            bagli = skip_bagli(n, kosul, yon)
            if not bagli and not ithal:
                # TUR 3 (c11): saran (eser DIŞI) koşul varken de erken dönüş koşulları eklenir
                kosul = kosul + erken_donus_kosullari(n)
            tur = next((s for s in _ATLAMA_SONEKI if ad == s or ad.endswith("." + s)), son)
        elif son == "importorskip":
            paket = _metin(argl[0]) if argl else ""
            neden = _metin(neden_d)
            if not ("sqlcipher" in paket.lower() or "sqlcipher" in neden.lower()):
                sonuc.append(Atlama(dosya, n.lineno, "importorskip", f"{paket} {neden}".strip()))
            continue
        else:
            continue
        neden = _metin(neden_d)
        if "sqlcipher" in neden.lower():
            continue  # A-46 yerel kapısı: nedeninde "sqlcipher" geçen atlama her koşuda KIRMIZI
        if bagli:
            continue
        if _eser_sorgusu_var(_ac(m, kosul, isl)) or ithal:
            sonuc.append(Atlama(dosya, n.lineno, tur, neden))
    return sonuc


def tara_hepsi() -> list[Atlama]:
    tum = []
    for yol in sorted(TESTS.rglob("*.py")):
        if "__pycache__" in yol.parts:
            continue
        gorece = yol.relative_to(KOK).as_posix()
        tum += tara(yol.read_text(encoding="utf-8"), gorece)
    return tum


# ═══ GEREKÇELİ İZİN LİSTESİ (cırcır) ═════════════════════════════════════════════════════════════════════════════════
#: Etiketler — gerekçe bunlardan biriyle BAŞLAR ve etiket sonrası en az 30 karakter neden taşır.
ETIKETLER = ("ARAC:", "PAKET:", "PLATFORM:", "TASARIM:", "DIS-KAYNAK:", "ORTAM:", "SEMA:", "BEKLEYEN YAMA:")
#: dosya → (ham atlama SAYISI, gerekçe). `None` sayı YALNIZ "BEKLEYEN YAMA:" için: orkestratörün bekleyen yaması dosyayı
#: değiştiriyor; sayı entegrasyondan sonra pinlenir (≥ 1 olmalı — 0'a düşerse satır BAYAT).
_BEKLEYEN = "BEKLEYEN YAMA: orkestratörün bekleyen yaması bu dosyayı değiştiriyor (K5-F DOKUNMA listesi) — entegrasyondan sonra capraz'a dönüştürülüp sayı pinlenir"
IZIN: dict[str, tuple[int | None, str]] = {
    'tests/test_18K_K3_dis_ag_kullanim_verisi_yok.py': (
        1,
        "PAKET: albumentations requirements*.txt'te doğrudan bildirili DEĞİL (yalnız geçişli — yorum satırı); ultralytics ile aynı find_spec döngüsünde → ZORUNLU yapılmadı",
    ),
    'tests/test_D3_04_ai_gecmisi_liste_ve_PDF_AYNI_erisim_sinifi_A02.py': (
        1,
        'PAKET: PyMuPDF (fitz) HİÇBİR requirements*.txt / build betiğinde yok (yalnız testte — K5-F ölçtü); yayın makinesi taşıdığını BEYAN etmiyor → K5_F gereği ZORUNLU yapılmadı',
    ),
    'tests/test_D3_41_kurtarma_kilidi_SEVK_AGACIYLA_ayni.py': (
        1,
        "ORTAM: gömülü derleme Python'u kimliği (python3XX.zip) — CI / venv'de bilinçli atlar; statik + sentetik kollar her ortamda koşar (eser değil yorumlayıcı kimliği)",
    ),
    'tests/test_I18NI_pdf_csv_ai_pro_modu_en.py': (
        1,
        'PAKET: PyMuPDF (fitz) HİÇBİR requirements*.txt / build betiğinde yok (yalnız testte — K5-F ölçtü); yayın makinesi taşıdığını BEYAN etmiyor → K5_F gereği ZORUNLU yapılmadı',
    ),
    'tests/test_YH_D2_bagimlilik_sabitleri_kurulu_surumle_ayni.py': (
        1,
        "ORTAM: gömülü derleme Python'u kimliği — geçişli bağımlılık sürümleri yalnız yayın yorumlayıcısında anlamlı (CI / venv başka sürüm taşır)",
    ),
    'tests/test_ai_analiz_pdf.py': (
        1,
        'PAKET: PyMuPDF (fitz) HİÇBİR requirements*.txt / build betiğinde yok (yalnız testte — K5-F ölçtü); yayın makinesi taşıdığını BEYAN etmiyor → K5_F gereği ZORUNLU yapılmadı',
    ),
    'tests/test_ai_analiz_pdf_OKUNUR_TURKCE.py': (
        1,
        'PAKET: PyMuPDF (fitz) HİÇBİR requirements*.txt / build betiğinde yok (yalnız testte — K5-F ölçtü); yayın makinesi taşıdığını BEYAN etmiyor → K5_F gereği ZORUNLU yapılmadı',
    ),
    'tests/test_capraz_atla_ve_paket_ZORUNLU_kipte_DUSER_D5.py': (
        1,
        "TASARIM: KARŞIT kol — düz `pytest.importorskip`in ZORUNLU=1'de de ATLADIĞINI ölçer (ölçücünün ayırt ettiği kanıt); istisna `_yakala` içinde yakalanır, test atlanmaz",
    ),
    'tests/test_compose_cozum_kolu_KIRIK_compose_ta_DURUR_4B214.py': (
        1,
        'ARAC: Docker CLI — yayın zincirinin aracı DEĞİL (publish_release / build betikleri istemez); yayın makinesinde zorunlu tutulmaz (K5_F: taşımıyorsa zorunlu yapma)',
    ),
    'tests/test_docker_DOCKERFILE_ve_IGNORE_yollari_GUNCEL_D420.py': (
        2,
        'ARAC: Docker CLI — yayın zincirinin aracı DEĞİL (publish_release / build betikleri istemez); yayın makinesinde zorunlu tutulmaz (K5_F: taşımıyorsa zorunlu yapma)',
    ),
    'tests/test_docker_KALICI_makine_kimligi_D412.py': (
        4,
        'ARAC: Docker CLI — yayın zincirinin aracı DEĞİL (publish_release / build betikleri istemez); yayın makinesinde zorunlu tutulmaz (K5_F: taşımıyorsa zorunlu yapma)',
    ),
    'tests/test_i18n_launcher_altyapi.py': (
        1,
        "TASARIM: asgari NSIS betiğinin Tauri şablonuna özgü sembol sınırı (makensis ÇIKTISINA bağlı); eser yokluğu değil — dönüştürmek ZORUNLU'da sahte kırmızı üretirdi (K5-F P9 --haric)",
    ),
    'tests/test_i18n_tr_taban.py': (
        1,
        "DIS-KAYNAK: TR tabanı depo DIŞINDA (`PEMF_I18N_TABAN`, sahibin denetim dizini); capraz.atla_yoksa depo-göreli yol alır — [SAHİBE] tabanı depoya alma ya da ZORUNLU'ya bağlama kararı",
    ),
    'tests/test_inno_kod_derlenir.py': (
        1,
        "ARAC: ISCC (Inno Setup) — 'eser var' kolu gerçek Inno derlemesi ister (ORTAK §1 yasak); dönüşüm + ölçüm ORKESTRATÖRDE",
    ),
    'tests/test_kasa_yalitimi.py': (
        3,
        "PLATFORM: keyring.backends.Windows — Windows'a özgü kasa arka ucu (Linux CI'da modül içi pywin32-ctypes yok); paket değil platform yeteneği",
    ),
    'tests/test_manifest_consistency.py': (
        1,
        'TASARIM: manifestte `launcher` bloğu opsiyonel (şema); eser yokluğu değil — tarayıcı koşulu manifest okuyan yolu çözerken sayıyor',
    ),
    'tests/test_pdf_turkce_karakter_ATLAMA_D5_17.py': (
        1,
        'PAKET: PyMuPDF (fitz) HİÇBİR requirements*.txt / build betiğinde yok (yalnız testte — K5-F ölçtü); D5.17 kolu fitz KURULUYKEN `_fitz()`in atlamadığını ölçer, fitz yoksa ölçecek şey yok',
    ),
    'tests/test_pdf_TOPLAM_SEANS_bulunan_seanslarla_TUTARLI_D234.py': (
        1,
        'PAKET: PyMuPDF (fitz) HİÇBİR requirements*.txt / build betiğinde yok (yalnız testte — K5-F ölçtü); yayın makinesi taşıdığını BEYAN etmiyor → K5_F gereği ZORUNLU yapılmadı',
    ),
    'tests/test_pdf_secili_seans_SQL_suzgeci_D228.py': (
        1,
        'PAKET: PyMuPDF (fitz) HİÇBİR requirements*.txt / build betiğinde yok (yalnız testte — K5-F ölçtü); yayın makinesi taşıdığını BEYAN etmiyor → K5_F gereği ZORUNLU yapılmadı',
    ),
    'tests/test_seans_mod_hedef_etiketi_P1.py': (
        1,
        'PAKET: PyMuPDF (fitz) HİÇBİR requirements*.txt / build betiğinde yok (yalnız testte — K5-F ölçtü); yayın makinesi taşıdığını BEYAN etmiyor → K5_F gereği ZORUNLU yapılmadı',
    ),
    'tests/test_sunucu_pdf_yedek_durum_istek_dilinde_P1.py': (
        1,
        'PAKET: PyMuPDF (fitz) HİÇBİR requirements*.txt / build betiğinde yok (yalnız testte — K5-F ölçtü); yayın makinesi taşıdığını BEYAN etmiyor → K5_F gereği ZORUNLU yapılmadı',
    ),
    'tests/test_tedavi_db_YOL_YAZIMI_suren_seansi_MUHURLEMEZ_D157.py': (
        1,
        'ORTAM: aparat önkoşulu — dizin bağlantısı (junction) kurulamazsa senaryo kurulamaz; koşul `bag.exists()` aparatın sonucunu sınar, eser yokluğunu değil',
    ),
}


def _say() -> Counter:
    return Counter(a.dosya for a in tara_hepsi())


def test_KRITIK_izin_listesi_DISINDA_ham_eser_atlamasi_YOK():
    sayim = _say()
    disarida = {d: n for d, n in sayim.items() if d not in IZIN}
    asan = {d: (n, IZIN[d][0]) for d, n in sayim.items() if d in IZIN and IZIN[d][0] is not None and n > IZIN[d][0]}
    if disarida or asan:
        ayrinti = [a for a in tara_hepsi() if a.dosya in disarida or a.dosya in asan]
        pytest.fail(
            "eser yokluğuna bağlı HAM atlama (ZORUNLU kipte de ATLAR): capraz.atla_yoksa / capraz.atla / capraz.paket_yoksa_atla "
            f"kullanın.\nlistede olmayan: {disarida}\nsayısı aşan: {asan}\n"
            + "\n".join(f"  {a.dosya}:{a.satir} {a.tur} {a.neden[:90]}" for a in ayrinti[:40])
        )


def test_KRITIK_izin_listesi_BAYAT_degil_cirt_cirt():
    """Sayı düştüyse (dönüştürüldü) liste de düşürülmeli; tamamen temizlenen dosya listeden çıkmalı."""
    sayim = _say()
    bayat = {}
    for d, (n, _g) in IZIN.items():
        gercek = sayim.get(d, 0)
        if n is None:
            if gercek == 0:
                bayat[d] = (gercek, "BEKLEYEN ama ham atlama kalmadı")
        elif gercek < n:
            bayat[d] = (gercek, n)
    assert not bayat, (
        f"izin listesi BAYAT (cırcır geri döndü / dosya temizlendi — sayıyı düşürün, satırı silin): {bayat}"
    )


def test_KRITIK_izin_listesi_GEREKCELI():
    kusur = []
    for d, (n, g) in IZIN.items():
        etiket = next((e for e in ETIKETLER if g.startswith(e)), None)
        if etiket is None or len(g[len(etiket) :].strip()) < 30:
            kusur.append(f"{d}: gerekçe etiketsiz ya da kısa: {g!r}")
        if n is None and etiket != "BEKLEYEN YAMA:":
            kusur.append(f"{d}: sayısız (None) satır yalnız BEKLEYEN YAMA için")
        if n is not None and n < 1:
            kusur.append(f"{d}: sayı {n} — sıfır / negatif satır olmaz (silin)")
        if not (KOK / d).is_file():
            kusur.append(f"{d}: dosya YOK")
    assert not kusur, "\n".join(kusur)


# ═══ ARAÇ KANITI — sentetik karşıt kollar (tarayıcı kör değil) ═══════════════════════════════════════════════════════
_HAM = '''
import shutil, os, importlib.util
from pathlib import Path
import pytest
KOK = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
pytestmark = pytest.mark.skipif(not (KOK / "apps" / "ui").exists(), reason="ui yok")
def _var():
    return (KOK / "x").is_file()
@pytest.mark.skipif(PWSH is None, reason="pwsh yok")
def test_a():
    pass
@pytest.mark.skipif(not _var(), reason="x yok")
def test_b():
    pass
def test_c():
    p = KOK / "y"
    if not p.exists():
        pytest.skip("y yok")
def test_d():
    yol = shutil.which("node")
    if yol is None:
        pytest.skip("node yok")
def test_e():
    try:
        import olmayan_paket  # noqa: F401
    except ImportError:
        pytest.skip("paket yok")
def test_f():
    if importlib.util.find_spec("x") is None:
        pytest.skip("x yok")
cv2 = pytest.importorskip("cv2")
'''

_BAGLI = '''
import os
from pathlib import Path
import capraz
import pytest
from golden.eser import eser_var_mi, zorunlu_mu
KOK = Path(__file__).resolve().parents[1]
ZORUNLU = os.environ.get("PEMF_CAPRAZ_KAYNAK_ZORUNLU") == "1"
isaret = pytest.mark.skipif(not eser_var_mi("a.pt") and not zorunlu_mu(), reason="pt yok")
def test_a():
    capraz.atla_yoksa("apps/ui/src", izlenen=True)
def test_b():
    if not (KOK / "y").exists():
        if ZORUNLU:
            pytest.fail("zorunlu")
        pytest.skip("y yok")
def test_c():
    if not (KOK / "z").exists():
        pytest.skip("sqlcipher3 yok — A-46")
sq = pytest.importorskip("sqlcipher3")
cv2 = capraz.paket_yoksa_atla("cv2")
@pytest.mark.skipif(os.name != "nt", reason="yalniz Windows")
def test_platform():
    pass
@pytest.mark.skipif(os.environ.get("X") != "1", reason="tasarim")
def test_tasarim():
    pass
'''


def test_KARSIT_KANIT_tarayici_HAM_bicimlerin_HEPSINI_yakalar():
    bulunan = tara(_HAM, "sentetik_ham.py")
    satirlar = sorted(a.satir for a in bulunan)
    turler = Counter(a.tur for a in bulunan)
    # modül skipif (exists) + PWSH (which, modül ataması) + _var() (işlev gövdesi) + skip/exists + skip/yerel which +
    # skip/except ImportError + skip/find_spec + importorskip
    assert len(bulunan) == 8, f"tarayıcı ham biçimleri kaçırıyor: {bulunan}"
    assert turler == {"skipif": 3, "skip": 4, "importorskip": 1}, turler
    assert satirlar == sorted(set(satirlar))


def test_KARSIT_KANIT_tarayici_BAGLI_ve_eser_DISI_atlamalari_saymaz():
    bulunan = tara(_BAGLI, "sentetik_bagli.py")
    assert bulunan == [], f"bağlı / eser dışı atlama ham sayıldı (sahte kırmızı): {bulunan}"


# ═══ TUR 2 — çürütücünün yaşayan mutantları (lc1 · lc2 · lc5 · lc6 · lc13) ve canlı kaçakları (DEV_C3:141 · A3_3:72) ═══════════
#: `# HAM` ile biten satırlar tarayıcının bulması GEREKEN satırlardır (fazlası da eksiği de kırmızı).
_HAM_TUR2 = """
import importlib
import os
import shutil
from pathlib import Path
import capraz
import pytest
from capraz import ZORUNLU
KOK = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
_KABUKLAR = [pytest.param(shutil.which("pwsh"), id="pwsh7"), pytest.param(None, id="yok")]
@pytest.mark.skipif((PWSH is None) and capraz.ZORUNLU, reason="lc1 ters yon")  # HAM
def test_lc1_ters_yon():
    pass
@pytest.mark.skipif(PWSH is None or ZORUNLU, reason="ad var yapi yok")  # HAM
def test_ad_var_yapi_yok():
    pass
@pytest.mark.skipif(not (KOK / "x").exists() and not os.name, reason="not var ama zorunlu degil")  # HAM
def test_not_var_zorunlu_degil():
    pass
def test_lc13_skip_ters_yon():
    if not (KOK / "y").exists() and capraz.ZORUNLU:
        pytest.skip("y yok")  # HAM
def test_zorunlu_dali_TERS():
    if not (KOK / "y").exists():
        if not ZORUNLU:
            pytest.fail("ters dal")
        pytest.skip("y yok")  # HAM
def test_zorunlu_dali_KOSULLU():
    if not (KOK / "y").exists():
        if ZORUNLU and os.name == "nt":
            pytest.fail("yalniz Windows'ta duser")
        pytest.skip("y yok")  # HAM
def test_zorunlu_dali_DUSURMEZ():
    if not (KOK / "y").exists():
        if ZORUNLU:
            print("uyari")
        pytest.skip("y yok")  # HAM
def test_zorunlu_dali_SONRA():
    if not (KOK / "y").exists():
        pytest.skip("y yok")  # HAM
    if ZORUNLU:
        pytest.fail("gec kalan dal")
def _ortam_dali_TERS():
    if (KOK / "c.onnx").exists():
        return
    if os.environ.get("PEMF_GOLDEN_REQUIRED") != "1":
        pytest.fail("ters ortam dali")
    pytest.skip("onnx yok")  # HAM
def test_lc5_genis_except():
    try:
        import yaml  # noqa: F401
    except Exception:
        pytest.skip("yaml yok")  # HAM
def test_lc6_ciplak_except_import_module():
    try:
        importlib.import_module("make_model_zip")
    except:  # noqa: E722
        pytest.skip("arac ice aktarilamadi")  # HAM
def test_base_exception_dunder_import():
    try:
        __import__("make_model_zip")
    except (OSError, BaseException) as e:
        pytest.skip(f"arac ice aktarilamadi ({e})")  # HAM
def _ps_A3_3():
    for p in (KOK / "a.exe", KOK / "b.exe"):
        if p.is_file():
            return str(p)
    pytest.skip("powershell yok")  # HAM
def _fikstur_lc2():
    if (KOK / "s.c").exists() and (KOK / "m.c").exists():
        return
    pytest.skip("firmware yok")  # HAM
@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_DEV_C3_parametre(tmp_path, kabuk):
    if kabuk is None:
        pytest.skip("kabuk yok")  # HAM
@pytest.mark.parametrize(["ad", "yol"], [("a", shutil.which("node"))])
def test_parametre_liste_adli(ad, yol):
    if not yol:
        pytest.skip("node yok")  # HAM
"""

_BAGLI_TUR2 = """
import os
import shutil
import unittest
from pathlib import Path
import capraz
import pytest
from golden.eser import zorunlu_mu
KOK = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
_KABUKLAR = [pytest.param(shutil.which("pwsh"), id="pwsh7")]
@pytest.mark.skipif(not (capraz.ZORUNLU or (KOK / "x").exists()), reason="not (zorunlu or ...)")
def test_not_or():
    pass
@pytest.mark.skipif((PWSH is None) and not zorunlu_mu(), reason="cagri bicimi")
def test_cagri():
    pass
@unittest.skipUnless(capraz.ZORUNLU or (KOK / "x").exists(), reason="skipUnless dogru yon")
def test_skip_unless():
    pass
def test_else_dali():
    if not (KOK / "y").exists():
        if capraz.ZORUNLU:
            pytest.fail("zorunlu")
        else:
            pytest.skip("y yok")
def test_ic_ice_bagli():
    if not (KOK / "y").exists():
        if not capraz.ZORUNLU:
            pytest.skip("y yok")
def test_genis_except_zorunlu_dalli():
    try:
        import yaml  # noqa: F401
    except Exception:
        if capraz.ZORUNLU:
            pytest.fail("zorunlu")
        pytest.skip("yaml yok")
def test_except_ithalsiz():
    try:
        int("x")
    except Exception:
        pytest.skip("ice aktarma degil, eser degil")
def _ps():
    for p in (KOK / "a.exe",):
        if p.is_file():
            return str(p)
    if zorunlu_mu():
        pytest.fail("zorunlu")
    pytest.skip("powershell yok")
def _platform():
    if os.name == "nt":
        return
    pytest.skip("yalniz Windows")
def _ortam_dali_ckd():
    if (KOK / "c.onnx").exists():
        return
    if os.environ.get("PEMF_GOLDEN_REQUIRED") == "1":
        pytest.fail("PEMF_GOLDEN_REQUIRED=1 ama onnx yok")
    pytest.skip("onnx yok")
def _ic_islev_donusu():
    def _bul():
        if (KOK / "a").exists():
            return 1
    pytest.skip("tasarim: ic islevin return'u bu yolu kesmez")
@pytest.mark.parametrize("kabuk", _KABUKLAR)
def test_parametre_bagli(kabuk):
    if kabuk is None and not capraz.ZORUNLU:
        pytest.skip("kabuk yok")
@pytest.mark.parametrize("sayi", [1, 2])
def test_parametre_eser_disi(sayi):
    if sayi is None:
        pytest.skip("eser degil")
"""


def _isaretli(kaynak: str) -> dict[int, str]:
    return {i: s.strip() for i, s in enumerate(kaynak.splitlines(), 1) if s.rstrip().endswith("# HAM")}


def test_KARSIT_KANIT_TUR2_ters_yon_genis_except_erken_donus_parametre_HAM_sayilir():
    """lc1 / lc13 (bağlı ad VAR ama yapı TERS), lc5 / lc6 (`except Exception` / çıplak `except` içe aktarma koruması), lc2 / A3_3:72
    (erken dönüş + koşulsuz skip), DEV_C3:141 (parametrize dolaylaması) — ZORUNLU kipte ATLAYAN biçimlerin HER biri HAM."""
    beklenen = _isaretli(_HAM_TUR2)
    bulunan = {a.satir for a in tara(_HAM_TUR2, "sentetik_ham_tur2.py")}
    kacan = {s: beklenen[s] for s in sorted(set(beklenen) - bulunan)}
    fazla = sorted(bulunan - set(beklenen))
    assert not kacan and not fazla, (
        f"tarayıcı ZORUNLU kipte ATLAYAN biçimi BAĞLI sanıyor (kaçırılan): {kacan} · fazladan ham sayılan satır: {fazla}"
    )


def test_KARSIT_KANIT_TUR2_yapisal_BAGLI_ve_eser_DISI_bicimleri_saymaz():
    """`not (<zorunlu> or …)`, `and not zorunlu_mu()`, `skipUnless(<zorunlu> or …)`, `if <zorunlu>: fail` + `else: skip`, iç içe bağlı
    dal, geniş except + zorunlu dalı, içe aktarmasız `try`, zorunlu dallı erken dönüş, eser dışı erken dönüş / parametre → HAM DEĞİL."""
    bulunan = tara(_BAGLI_TUR2, "sentetik_bagli_tur2.py")
    assert bulunan == [], (
        f"ZORUNLU kipte DÜŞEN (yapısal bağlı) / eser dışı atlama ham sayıldı (sahte kırmızı): {bulunan}"
    )


# ═══ TUR 3 — çürütücü 2'nin yaşayan mutantları (c2 · c2b · c4b · c8 · c9 · c11 · c12) + aynı sınıfın komşu biçimleri ═════════════
_HAM_TUR3 = """
import os
import shutil
import sys
import unittest
from pathlib import Path
import pytest
KOK = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
ZORUNLU = os.environ.get("PEMF_ZORUNLU") == "1"
def zorunlu_mu():
    return False
@pytest.mark.skipif((PWSH is None) and not ZORUNLU, reason="c2 yerel ZORUNLU yanlis ortam adi")  # HAM
def test_c2_yerel_ad():
    pass
@pytest.mark.skipif((PWSH is None) and not zorunlu_mu(), reason="yerel tanimli zorunlu_mu hep False")  # HAM
def test_yerel_islev():
    pass
def test_parametre_golgesi(required=False):
    if not (KOK / "y").exists():
        if required:
            pytest.fail("parametre degeri bilinmez")
        pytest.skip("y yok")  # HAM
def _c2b_ortam_adi():
    if (KOK / "c.onnx").exists():
        return
    if os.environ.get("PEMF_GOLDEN_REQUIRED_YEREL") == "1":
        pytest.fail("yanlis ortam adi")
    pytest.skip("onnx yok")  # HAM
def _sahte_okuyucu():
    if (KOK / "c.onnx").exists():
        return
    if {}.get("PEMF_GOLDEN_REQUIRED") == "1":
        pytest.fail("sahte sozluk")
    pytest.skip("onnx yok")  # HAM
def _yaml_al():
    import yaml
    return yaml
def _yaml_al_2():
    return _yaml_al()
def test_c4b_dolayli():
    try:
        _yaml_al()
    except Exception:
        pytest.skip("yaml yok")  # HAM
def test_c4b_iki_duzey():
    try:
        _yaml_al_2()
    except BaseException:
        pytest.skip("yaml yok")  # HAM
def test_ikili_yok():
    try:
        open(KOK / "a.bin")
    except FileNotFoundError:
        pytest.skip("ikili yok")  # HAM
def _c8_ps():
    for p in (KOK / "a.exe",):
        if p.is_file():
            return str(p)
    raise pytest.skip.Exception("powershell yok")  # HAM
def test_c9_xfail():
    if PWSH is None:
        pytest.xfail("kabuk yok")  # HAM
def test_skiptest_cagrisiz():
    if not (KOK / "y").exists():
        raise unittest.SkipTest  # HAM
class T(unittest.TestCase):
    def test_skip_test(self):
        if shutil.which("node") is None:
            self.skipTest("node yok")  # HAM
@pytest.mark.xfail(PWSH is None, reason="isaret xfail", run=False)  # HAM
def test_isaret_xfail():
    pass
@pytest.mark.skipif(condition=PWSH is None, reason="anahtar sozcuklu kosul")  # HAM
def test_kosul_anahtar():
    pass
@pytest.mark.skipif(os.name != "nt", PWSH is None, reason="ikinci konumsal kosul")  # HAM
def test_ikinci_kosul():
    pass
if not (KOK / "z").exists():
    pytestmark = pytest.mark.skip(reason="modul duzeyi kosullu isaret")  # HAM
def _c11_platform():
    for p in (KOK / "a.exe",):
        if p.is_file():
            return str(p)
    if sys.platform == "win32":
        pytest.skip("powershell yok")  # HAM
def test_kisa_devre():
    (KOK / "y").exists() or pytest.skip("y yok")  # HAM
def test_kosullu_ifade():
    _ = pytest.skip("y yok") if not (KOK / "y").exists() else None  # HAM
def _for_else():
    for p in (KOK / "a.exe",):
        if p.is_file():
            break
    else:
        pytest.skip("aday yok")  # HAM
def _c12_raise_skip():
    if (KOK / "c.onnx").exists():
        return
    if os.environ.get("PEMF_GOLDEN_REQUIRED") == "1":
        raise pytest.skip.Exception("zorunlu ama yine atlar")  # HAM
    pytest.skip("onnx yok")  # HAM
def _c12_degisken():
    if (KOK / "c.onnx").exists():
        return
    hata = pytest.skip.Exception("zorunlu ama atlar")
    if os.environ.get("PEMF_GOLDEN_REQUIRED") == "1":
        raise hata  # HAM
    pytest.skip("onnx yok")  # HAM
def test_c12_ciplak_raise_atlamayi_yakalar():
    try:
        int("0")
    except pytest.skip.Exception:
        if not (KOK / "y").exists():
            if os.environ.get("PEMF_CAPRAZ_KAYNAK_ZORUNLU") == "1":
                raise
            pytest.skip("y yok")  # HAM
"""

_BAGLI_TUR3 = """
import os
import shutil
import unittest
from pathlib import Path
import capraz
import pytest
from capraz import ZORUNLU as ZORUNLU_KIP
from golden.eser import zorunlu_mu
KOK = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
ZORUNLU = os.environ.get("PEMF_CAPRAZ_KAYNAK_ZORUNLU") == "1"
GOLDEN_REQUIRED = os.getenv("PEMF_GOLDEN_REQUIRED") == "1" or capraz.ZORUNLU
_BAYRAK = "PEMF_CAPRAZ_KAYNAK_ZORUNLU"
def kip_zorunlu():
    return capraz.ZORUNLU or zorunlu_mu()
@pytest.mark.skipif((PWSH is None) and not ZORUNLU, reason="yerel ZORUNLU dogru ortam adiyla")
def test_yerel_dogru():
    pass
@pytest.mark.skipif((PWSH is None) and not ZORUNLU_KIP, reason="capraz'dan ice aktarilan ad")
def test_ice_aktarilan():
    pass
@pytest.mark.skipif((PWSH is None) and not kip_zorunlu(), reason="yerel islev zorunlu doner")
def test_yerel_islev():
    pass
@pytest.mark.skipif((PWSH is None) and not GOLDEN_REQUIRED, reason="getenv okuyucu")
def test_getenv():
    pass
@pytest.mark.skipif(not (os.environ.get(_BAYRAK) == "1" or PWSH is not None), reason="sabite bagli ortam adi")
def test_sabit_ad():
    pass
@pytest.mark.skipif(os.name != "nt", (PWSH is None) and not capraz.ZORUNLU, reason="eserli kosul bagli")
def test_iki_kosul_bagli():
    pass
@pytest.mark.xfail(PWSH is None and not capraz.ZORUNLU, reason="isaret xfail bagli")
def test_isaret_xfail_bagli():
    pass
@pytest.mark.xfail(reason="bilinen urun hatasi - eser degil")
def test_isaret_xfail_kosulsuz():
    pass
@pytest.mark.skip(reason="tasarim")
def test_kosulsuz_isaret():
    pass
if os.name != "nt":
    pytestmark = pytest.mark.skip(reason="yalniz Windows")
def test_skip_exception_zorunlu_dalli():
    if not (KOK / "y").exists():
        if ZORUNLU:
            raise AssertionError("zorunlu kipte eser yok")
        raise pytest.skip.Exception("y yok")
def test_xfail_bagli():
    if PWSH is None and not capraz.ZORUNLU:
        pytest.xfail("pwsh yok")
def test_cagrisiz_raise_bagli():
    if not (KOK / "y").exists():
        if capraz.ZORUNLU:
            pytest.fail("zorunlu")
        raise unittest.SkipTest
def test_ciplak_raise_dusurur():
    try:
        import yaml  # noqa: F401
    except ImportError:
        if capraz.ZORUNLU:
            raise
        pytest.skip("yaml yok")
def test_kisa_devre_bagli():
    capraz.ZORUNLU or (KOK / "y").exists() or pytest.skip("y yok")
def test_for_else_bagli():
    for p in (KOK / "a.exe",):
        if p.is_file():
            break
    else:
        if capraz.ZORUNLU:
            pytest.fail("aday yok")
        pytest.skip("aday yok")
def _hesapla():
    return int("x")
def test_genis_except_dolayli_ithalsiz():
    try:
        _hesapla()
    except Exception:
        pytest.skip("ice aktarma degil, eser degil")
def test_izin_hatasi_platform():
    try:
        (KOK / "l").symlink_to(KOK)
    except OSError:
        pytest.skip("symlink izni yok - platform")
"""


def test_KARSIT_KANIT_TUR3_tanim_dolayli_ithal_atlama_esdegeri_ve_saran_bicimler_HAM_sayilir():
    """c2 / c2b (ad ya da ortam adı TANIMIYLA yanlış), c4b (yardımcıda içe aktarma, 2 düzey), c8 / c9 (`skip.Exception` / `xfail` /
    `SkipTest` / `skipTest` / işaret xfail / `condition=` / ikinci koşul / koşullu `mark.skip`), c11 (saran eser dışı koşul + erken
    dönüş; kısa devre, koşullu ifade, `for … else`), c12 (atlama istisnası yükselten `raise` düşürme sayılmaz) — HER biri HAM."""
    beklenen = _isaretli(_HAM_TUR3)
    bulunan = {a.satir for a in tara(_HAM_TUR3, "sentetik_ham_tur3.py")}
    kacan = {s: beklenen[s] for s in sorted(set(beklenen) - bulunan)}
    fazla = sorted(bulunan - set(beklenen))
    assert not kacan and not fazla, (
        f"tarayıcı ZORUNLU kipte ATLAYAN biçimi BAĞLI / eser dışı sanıyor (kaçırılan): {kacan} · fazladan ham sayılan satır: {fazla}"
    )


def test_KARSIT_KANIT_TUR3_dogru_tanimli_BAGLI_ve_eser_DISI_bicimleri_saymaz():
    """Doğru ortam adlı yerel `ZORUNLU`, `capraz`tan içe aktarılan ad, `zorunlu` döndüren yerel işlev, `getenv` + `or capraz.ZORUNLU`,
    sabite bağlı ortam adı, eserli koşulu bağlı iki koşullu işaret, bağlı / koşulsuz xfail, `if ZORUNLU: raise AssertionError` +
    `raise skip.Exception`, ImportError'ı yeniden yükselten çıplak `raise`, bağlı kısa devre / `for … else`, içe aktarmasız dolaylı
    `try`, `OSError` (izin / platform) → HAM DEĞİL."""
    bulunan = tara(_BAGLI_TUR3, "sentetik_bagli_tur3.py")
    assert bulunan == [], (
        f"ZORUNLU kipte DÜŞEN (tanımıyla bağlı) / eser dışı atlama ham sayıldı (sahte kırmızı): {bulunan}"
    )


# ═══ TUR 3b — çürütücü 3'ün yaşayanları: takma ad (m3b) · DİZE koşulu (m3a) · sınıf adıyla dolaylı içe aktarma (m2b) ════════════
_HAM_TUR3B = """
import shutil
import sys
from pathlib import Path
import pytest
from pytest import skip as _gec
from unittest import SkipTest as _ST
_atla = pytest.skip
KOK = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
@pytest.mark.skipif("PWSH is None", reason="m3a dize kosulu")  # HAM
def test_m3a_dize():
    pass
@pytest.mark.xfail("not (KOK / 'x').exists()", reason="dize xfail kosulu")  # HAM
def test_dize_xfail():
    pass
pytestmark = pytest.mark.skipif(condition="not (KOK / 'z').is_dir()", reason="anahtar sozcuklu dize")  # HAM
@pytest.mark.skipif(sys.platform != "win32", "not (KOK / 'w').exists()", reason="ikinci konumsal dize")  # HAM
def test_ikinci_dize():
    pass
def test_m3b_takma_ad():
    if PWSH is None:
        _gec("pwsh yok")  # HAM
def test_takma_deger():
    if not (KOK / "y").exists():
        _atla("y yok")  # HAM
def test_takma_istisna():
    if not (KOK / "y").exists():
        raise _ST("y yok")  # HAM
def test_takma_istisna_cagrisiz():
    if shutil.which("node") is None:
        raise _ST  # HAM
class _Y:
    @staticmethod
    def al():
        import yaml
        return yaml
def test_m2b_sinif_adi():
    try:
        _Y.al()
    except Exception:
        pytest.skip("yaml yok")  # HAM
def test_ornek_cagrisi():
    try:
        _Y().al()
    except BaseException:
        pytest.skip("yaml yok")  # HAM
"""

_BAGLI_TUR3B = """
import shutil
import unittest
from pathlib import Path
import capraz
import pytest
from capraz import atla as _gec
KOK = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh")
@pytest.mark.skipif("PWSH is None and not capraz.ZORUNLU", reason="dize kosulu bagli")
def test_dize_bagli():
    pass
@pytest.mark.skipif("sys.platform != 'win32'", reason="dize platform kosulu")
def test_dize_platform():
    pass
@pytest.mark.xfail("bilinen urun hatasi", reason="cozumlenemeyen dize - eser degil")
def test_dize_cozulemez():
    pass
@unittest.skipIf("PWSH is None", "unittest bicimi dizeyi degerlendirmez - eser degil")
def test_unittest_dize():
    pass
def test_takma_capraz():
    if PWSH is None:
        _gec("pwsh yok")
class _Z:
    @staticmethod
    def hesapla():
        return int("1")
def test_sinif_ithalsiz():
    try:
        _Z.hesapla()
    except Exception:
        pytest.skip("ice aktarma degil, eser degil")
"""


def test_KARSIT_KANIT_TUR3B_takma_ad_DIZE_kosulu_ve_sinif_adli_dolayli_ithal_HAM_sayilir():
    """m3b (`from pytest import skip as _gec`, `_atla = pytest.skip`, `from unittest import SkipTest as _ST` — çağrılı ve çağrısız),
    m3a (pytest işaretinin DİZE koşulu — konumsal skipif / xfail, `condition=`, ikinci konumsal), m2b (`_Y.al()` / `_Y().al()` gövdesinde içe aktarma +
    geniş `except`) — ZORUNLU kipte ATLAYAN biçimlerin HER biri HAM."""
    beklenen = _isaretli(_HAM_TUR3B)
    bulunan = {a.satir for a in tara(_HAM_TUR3B, "sentetik_ham_tur3b.py")}
    kacan = {s: beklenen[s] for s in sorted(set(beklenen) - bulunan)}
    fazla = sorted(bulunan - set(beklenen))
    assert not kacan and not fazla, (
        f"tarayıcı takma ad / dize koşulu / sınıf adıyla çağrıyı GÖRMÜYOR (kaçırılan): {kacan} · fazladan ham sayılan satır: {fazla}"
    )


def test_KARSIT_KANIT_TUR3B_bagli_dize_capraz_takma_adi_ve_ithalsiz_sinif_cagrisi_saymaz():
    """Bağlı dize koşulu (`'… and not capraz.ZORUNLU'`), eser dışı / çözümlenemeyen dize, unittest dize biçimi (değerlendirilmez),
    `capraz.atla` takma adı, içe aktarmasız sınıf yöntemi → HAM DEĞİL (takma ad / dize çözümü sahte kırmızı üretmez)."""
    bulunan = tara(_BAGLI_TUR3B, "sentetik_bagli_tur3b.py")
    assert bulunan == [], f"bağlı / eser dışı biçim ham sayıldı (takma ad / dize çözümü sahte kırmızı): {bulunan}"


# ═══ TUR 3b — ZORUNLU durumuna YAZIM (m1a · m1b): yalnız test işlevinde monkeypatch ═════════════════════════════════════════
#: TUR 3b (m1a / m1b): ZORUNLU durumunu taşıyan ortam bayrakları (yayın süiti kurar).
_DURUM_BAYRAK = _ZORUNLU_ORTAM


def durum_yazimi_ihlalleri(kaynak: str, dosya: str, serbest_dahil: bool = False) -> list[Atlama]:
    """ZORUNLU durumuna yazım (`capraz.ZORUNLU = …`, `setattr(…, "ZORUNLU", …)`, `os.environ["PEMF_GOLDEN_REQUIRED"] = …` — anahtar
    sabite bağlı ad da —, `pop` / `setdefault` / `update` / `clear` / `putenv`, `setitem(os.environ, …)`, `patch.dict(os.environ…)`,
    `patch.object(…, "ZORUNLU")`) YALNIZ `test_*` işlevinde `monkeypatch.setattr|setenv|delenv|setitem` ile serbest (geri alınır;
    capraz'ın kendi testleri). Modül düzeyi (içe aktarmada koşar), fikstür,
    yardımcı işlev ya da ham yazım = ihlal: META'nın "bağlı" saydığı `capraz.ZORUNLU` / satır içi ortam denetimini ZORUNLU kipte boşa çıkarır.
    `serbest_dahil`: serbest yazımlar da (`tur` = "durum-serbest") döner — KRİTİK kapının kör tarama bekçisi için."""
    try:
        m = _Modul(kaynak)
    except SyntaxError:
        return []
    agac, eb = m.agac, m.ebeveyn

    def sabit(x):
        # TUR 3b: dizge sabiti ya da dosyada TEK kez dizge sabitine bağlanan ad (`_BAYRAK = "PEMF_…"`; `os.environ[_BAYRAK] = "0"`)
        return _sabit_dizge(x, m)

    def bayrak_mi(x):
        v = sabit(x)
        return v is not None and (v in _DURUM_BAYRAK or bool(_BAGLI_AD.search(v)))

    def islev(x):
        p = eb.get(x)
        while p is not None and not isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
            p = eb.get(p)
        return p

    sonuc = []
    for n in ast.walk(agac):
        yazim, mp = None, False
        if isinstance(n, ast.Attribute) and isinstance(n.ctx, (ast.Store, ast.Del)) and _BAGLI_AD.search(n.attr):
            yazim = f"öznitelik {_cagri_adi(n)}"
        elif (
            isinstance(n, ast.Subscript)
            and isinstance(n.ctx, (ast.Store, ast.Del))
            and _cagri_adi(n.value).endswith("environ")
        ):
            if bayrak_mi(n.slice):
                yazim = f"ortam {_cagri_adi(n.value)}[{sabit(n.slice)}]"
        elif isinstance(n, ast.Call):
            a = _cagri_adi(n.func)
            son = a.rsplit(".", 1)[-1]
            mp = a.startswith("monkeypatch.")
            if son in ("setattr", "delattr", "object") and any(
                sabit(x) and _BAGLI_AD.search(sabit(x)) for x in n.args[:2]
            ):
                yazim = f"{a}(…)"
            elif son in ("setenv", "delenv", "putenv", "unsetenv") and n.args and bayrak_mi(n.args[0]):
                yazim = f"{a}({sabit(n.args[0])})"
            elif (
                son in ("setitem", "delitem")
                and len(n.args) >= 2
                and _cagri_adi(n.args[0]).endswith("environ")
                and bayrak_mi(n.args[1])
            ):
                yazim = f"{a}(environ, {sabit(n.args[1])})"  # TUR 3b: `monkeypatch.setitem(os.environ, …)` ikiz biçimi
            elif (
                "environ." in a
                and son in ("pop", "setdefault", "__setitem__", "__delitem__")
                and n.args
                and bayrak_mi(n.args[0])
            ):
                yazim = f"{a}({sabit(n.args[0])})"
            elif a.endswith("environ.update") or a.endswith("environ.clear"):
                yazim = f"{a}(…)"
            elif son == "dict" and "patch" in a and n.args and _cagri_adi(n.args[0]).endswith("environ"):
                yazim = f"{a}(os.environ, …)"
        if yazim is None:
            continue
        isl = islev(n)
        fikstur = isl is not None and any(
            "fixture" in _cagri_adi(d.func if isinstance(d, ast.Call) else d) for d in isl.decorator_list
        )
        if mp and isl is not None and isl.name.startswith("test") and not fikstur:
            if serbest_dahil:
                sonuc.append(Atlama(dosya, n.lineno, "durum-serbest", f"{yazim} — test {isl.name} (monkeypatch)"))
            continue
        yer = "modül düzeyi" if isl is None else (f"fikstür {isl.name}" if fikstur else f"işlev {isl.name}")
        sonuc.append(Atlama(dosya, n.lineno, "durum-yazimi", f"{yazim} — {yer}"))
    return sonuc


def durum_yazimi_hepsi(serbest_dahil: bool = False) -> list[Atlama]:
    tum = []
    for yol in sorted(TESTS.rglob("*.py")):
        if "__pycache__" in yol.parts:
            continue
        tum += durum_yazimi_ihlalleri(yol.read_text(encoding="utf-8"), yol.relative_to(KOK).as_posix(), serbest_dahil)
    return tum


def test_KRITIK_ZORUNLU_durumuna_YAZIM_yalniz_test_icinde_monkeypatch():
    tum = durum_yazimi_hepsi(serbest_dahil=True)
    ihlal = [a for a in tum if a.tur == "durum-yazimi"]
    # TUR 3b (n14): KÖR TARAMA bekçisi — capraz'ın kendi testleri ZORUNLU'yu test içinde monkeypatch ile yazar; tarayıcı onları
    # (serbest olarak) GÖRMÜYORSA ağaç taraması boşalmıştır ve "ihlal yok" kanıt değildir.
    assert any(a.tur == "durum-serbest" for a in tum), (
        "KÖR TARAMA: tests/ içinde hiç ZORUNLU durum yazımı görülmedi (capraz'ın kendi testlerindeki monkeypatch yazımları da yok) — "
        "durum_yazimi_hepsi ağacı taramıyor"
    )
    assert not ihlal, (
        "ZORUNLU durumuna test DIŞINDA / ham yazım (META'nın bağlı saydığı denetimi boşa çıkarır):\n"
        + "\n".join(f"  {a.dosya}:{a.satir} {a.neden}" for a in ihlal[:40])
    )


_DURUM_KARSIT = '''
import os, capraz, pytest
capraz.ZORUNLU = False  # HAM
os.environ["PEMF_GOLDEN_REQUIRED"] = "0"  # HAM
_BAYRAK = "PEMF_CAPRAZ_KAYNAK_ZORUNLU"
os.environ[_BAYRAK] = "0"  # HAM

@pytest.fixture(autouse=True)
def _f(monkeypatch):
    monkeypatch.setattr(capraz, "ZORUNLU", False)  # HAM
    monkeypatch.setitem(os.environ, "PEMF_GOLDEN_REQUIRED", "0")  # HAM

def _yardimci():
    os.environ.pop("PEMF_CAPRAZ_KAYNAK_ZORUNLU", None)  # HAM

def test_ham_setattr():
    setattr(capraz, "ZORUNLU", False)  # HAM

def test_capraz_kendi_testi(monkeypatch):
    monkeypatch.setattr(capraz, "ZORUNLU", True)
    monkeypatch.setenv("PEMF_GOLDEN_REQUIRED", "1")
    monkeypatch.delenv("PEMF_GOLDEN_REQUIRED", raising=False)
    monkeypatch.setitem(os.environ, _BAYRAK, "1")
    os.environ.get("PEMF_GOLDEN_REQUIRED")
    yerel = {}
    yerel["PEMF_GOLDEN_REQUIRED"] = "0"
'''


def test_KARSIT_KANIT_C3_durum_yazimi_HAM_bicimleri_yakalar_monkeypatch_test_icinde_serbest():
    """m1a / m1b ailesi: modül düzeyi öznitelik / ortam yazımı (anahtar sabite bağlı ad da), fikstürde monkeypatch (setattr / setitem),
    yardımcı işlevde `environ.pop`, test içinde ham `setattr` → İHLAL; test işlevinde `monkeypatch.` ve ortam dışı sözlük → serbest."""
    beklenen = _isaretli(_DURUM_KARSIT)
    bulunan = {a.satir for a in durum_yazimi_ihlalleri(_DURUM_KARSIT, "sentetik_durum.py")}
    serbest = {
        a.satir for a in durum_yazimi_ihlalleri(_DURUM_KARSIT, "sentetik_durum.py", serbest_dahil=True)
    } - bulunan
    assert len(serbest) == 4, f"serbest (test içinde monkeypatch) yazım sayısı 4 değil: {sorted(serbest)}"
    kacan = {s: beklenen[s] for s in sorted(set(beklenen) - bulunan)}
    fazla = sorted(bulunan - set(beklenen))
    assert not kacan and not fazla, (
        f"durum yazımı tarayıcısı ZORUNLU'yu boşa çıkaran yazımı GÖRMÜYOR (kaçırılan): {kacan} · fazladan ihlal sayılan satır: {fazla}"
    )
