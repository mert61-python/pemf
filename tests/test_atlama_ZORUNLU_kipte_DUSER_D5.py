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
Ham atlama yalnız GEREKÇELİ izin listesindeki dosyada ve listedeki SAYIDA olabilir (cırcır: sayı düşerse liste de düşürülmeli —
bayat liste de KIRMIZI). Doğru yol: `capraz.atla_yoksa(yol, izlenen=…)`, `capraz.atla(sebep)`, `capraz.paket_yoksa_atla(ad)`.

Bilinen sınır (bilinçli): adlar en çok 3 düzey açılır ve başka modülden gelen adlar yalnız `tests/` içindeki modüllerden çözülür;
atlamayı SARMAYAN `continue` (döngüde sessiz geçiş, atlama yok) bu kapının değil dosyanın KARŞIT kolunun işidir
(`test_stm_bobin_sayisi_tek_kaynak.py`). Fikstür `params=` / `request.param` dolaylaması çözülmez.
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


def _zorunlu_dugumu(n: ast.AST) -> bool:
    """`ZORUNLU`, `capraz.ZORUNLU`, `zorunlu_mu()`, `golden.eser.zorunlu_mu()` (ad / öznitelik / argümansız çağrı) ya da satır içi
    ortam denetimi `os.environ.get("PEMF_GOLDEN_REQUIRED") == "1"` / `os.getenv(...) == "1"` (yayın süiti iki bayrağı da kurar)."""
    if isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.ops[0], ast.Eq):
        sol, sag = n.left, n.comparators[0]
        if isinstance(sol, ast.Constant) and sol.value == "1":
            sol, sag = sag, sol
        return (
            isinstance(sag, ast.Constant)
            and sag.value == "1"
            and isinstance(sol, ast.Call)
            and _cagri_adi(sol.func).rsplit(".", 1)[-1] in ("get", "getenv")
            and bool(sol.args)
            and isinstance(sol.args[0], ast.Constant)
            and isinstance(sol.args[0].value, str)
            and bool(_BAGLI_AD.search(sol.args[0].value))
        )
    if isinstance(n, ast.Call) and not n.args and not n.keywords:
        n = n.func
    if isinstance(n, ast.Name):
        return bool(_BAGLI_AD.search(n.id))
    if isinstance(n, ast.Attribute):
        return bool(_BAGLI_AD.search(n.attr))
    return False


def _zorunluda_yanlis(k: ast.AST) -> bool:
    """TUR 2 (lc1 / lc13): ZORUNLU doğruyken koşul YAPISAL olarak YANLIŞ mı — `(…) and not <zorunlu>`, `not (<zorunlu> or …)`.

    Adın koşulda GEÇMESİ yetmez: `(X is None) and capraz.ZORUNLU` ZORUNLU'da atlar (ters yön), `X is None or ZORUNLU` de."""
    if isinstance(k, ast.UnaryOp) and isinstance(k.op, ast.Not):
        return _zorunluda_dogru(k.operand)
    if isinstance(k, ast.BoolOp):
        alt = [_zorunluda_yanlis(v) for v in k.values]
        return any(alt) if isinstance(k.op, ast.And) else all(alt)
    return False


def _zorunluda_dogru(k: ast.AST) -> bool:
    """ZORUNLU doğruyken koşul YAPISAL olarak DOĞRU mu — `<zorunlu>`, `<zorunlu> or …`, `not (… and not <zorunlu>)`."""
    if _zorunlu_dugumu(k):
        return True
    if isinstance(k, ast.UnaryOp) and isinstance(k.op, ast.Not):
        return _zorunluda_yanlis(k.operand)
    if isinstance(k, ast.BoolOp):
        alt = [_zorunluda_dogru(v) for v in k.values]
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


def _ithal_var(govde) -> bool:
    """`try` gövdesinde içe aktarma var mı (deyim ya da `importlib.import_module` / `__import__` / `exec_module` …)."""
    for st in govde:
        for n in _islev_disi_dolas(st):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                return True
            if isinstance(n, ast.Call) and _cagri_adi(n.func).rsplit(".", 1)[-1] in _ITHAL_ISLEVI:
                return True
    return False


def _dusurur(govde) -> bool:
    """Blok KOŞULSUZ düşürür mü: üst düzey deyimlerinden biri `pytest.fail(...)` / `fail(...)` ya da `raise`."""
    for st in govde:
        if isinstance(st, ast.Raise):
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

    def saran_kosullar(n):
        """Saran `if` testleri + dal yönü (True = gövde, False = `else`) + içe aktarma hatasını yakalayan `except` içinde mi."""
        kosul, yon, ithal = [], [], False
        cur, p = n, m.ebeveyn.get(n)
        while p is not None and not isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module, ast.ClassDef)):
            if isinstance(p, ast.If) and cur is not p.test:
                kosul.append(p.test)
                yon.append(not any(x is cur for x in p.orelse))
            elif isinstance(p, ast.ExceptHandler):
                tur = p.type
                adlar = (
                    set()
                    if tur is None
                    else {_cagri_adi(x) for x in (tur.elts if isinstance(tur, ast.Tuple) else [tur])}
                )
                if adlar & _ITHAL_HATASI:
                    ithal = True
                elif (tur is None or adlar & _GENIS_HATA) and _ithal_var(m.ebeveyn[p].body):
                    ithal = True  # TUR 2 (lc5 / lc6): `try: import …` + `except Exception` / çıplak `except` = ImportError gibi
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
        if any(_zorunluda_yanlis(k) if govde else _zorunluda_dogru(k) for k, govde in zip(kosul, yon)):
            return True
        return any(
            isinstance(st, ast.If) and _zorunluda_dogru(st.test) and _dusurur(st.body) for st in onceki_kardesler(n)
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
        if not isinstance(n, ast.Call):
            continue
        ad = _cagri_adi(n.func)
        son = ad.rsplit(".", 1)[-1]
        neden_d = next((k.value for k in n.keywords if k.arg == "reason"), None)
        isl = islevi(n)
        if son in ("skipif", "skipIf", "skipUnless"):
            if not n.args:
                continue
            kosul, ithal = [n.args[0]], False
            if neden_d is None and len(n.args) > 1:
                neden_d = n.args[1]
            bagli = _zorunluda_dogru(n.args[0]) if son == "skipUnless" else _zorunluda_yanlis(n.args[0])
        elif ad in ("pytest.skip", "skip") and son == "skip":
            kosul, yon, ithal = saran_kosullar(n)
            if neden_d is None and n.args:
                neden_d = n.args[0]
            bagli = skip_bagli(n, kosul, yon)
            if not bagli and not kosul and not ithal:
                kosul = erken_donus_kosullari(n)
        elif son == "importorskip":
            paket = _metin(n.args[0]) if n.args else ""
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
            sonuc.append(Atlama(dosya, n.lineno, son, neden))
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
    'tests/test_18K_K1_nsis_estop_VARSAYILAN_port.py': (
        1,
        "ARAC: makensis — kapı NSIS kancasını derleyip loopback'teki sahte E-stop sunucusuyla KOŞTURUR; K5-F ölçümü loopback'e istek gönderemez (ORTAK §1) — dönüşüm + üçlü ölçüm ORKESTRATÖRDE",
    ),
    'tests/test_18K_K3_dis_ag_kullanim_verisi_yok.py': (
        1,
        "PAKET: albumentations requirements*.txt'te doğrudan bildirili DEĞİL (yalnız geçişli — yorum satırı); ultralytics ile aynı find_spec döngüsünde → ZORUNLU yapılmadı",
    ),
    'tests/test_A11_mosquitto_servisi_BOS_conf_d_ile_ACILIR_G33.py': (
        1,
        'ARAC: mosquitto ikilisi (`mosquitto_aparat.ikili()`) — K5 kafesi mosquitto alt sürecini reddeder (ORTAK §2), ZORUNLU kolu bu ortamda ölçülemez; Windows CI paketteki 2.0.18 ile koşar — dönüşüm + ölçüm ORKESTRATÖRDE',
    ),
    'tests/test_D1104_broker_KIMLIKLI_sahte_ack_TEYIT_SAYILMAZ.py': (
        1,
        'ARAC: mosquitto ikilisi (`mosquitto_aparat.ikili()`) — K5 kafesi mosquitto alt sürecini reddeder (ORTAK §2), ZORUNLU kolu bu ortamda ölçülemez; Windows CI paketteki 2.0.18 ile koşar — dönüşüm + ölçüm ORKESTRATÖRDE',
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
    'tests/test_ag_gecidi_mosquitto_BOS_conf_d_ile_ACILIR_G8_11.py': (
        1,
        'ARAC: mosquitto ikilisi (`mosquitto_aparat.ikili()`) — K5 kafesi mosquitto alt sürecini reddeder (ORTAK §2), ZORUNLU kolu bu ortamda ölçülemez; Windows CI paketteki 2.0.18 ile koşar — dönüşüm + ölçüm ORKESTRATÖRDE',
    ),
    'tests/test_ai_analiz_pdf.py': (
        1,
        'PAKET: PyMuPDF (fitz) HİÇBİR requirements*.txt / build betiğinde yok (yalnız testte — K5-F ölçtü); yayın makinesi taşıdığını BEYAN etmiyor → K5_F gereği ZORUNLU yapılmadı',
    ),
    'tests/test_ai_analiz_pdf_OKUNUR_TURKCE.py': (
        1,
        'PAKET: PyMuPDF (fitz) HİÇBİR requirements*.txt / build betiğinde yok (yalnız testte — K5-F ölçtü); yayın makinesi taşıdığını BEYAN etmiyor → K5_F gereği ZORUNLU yapılmadı',
    ),
    'tests/test_ai_servis_8100_kapisi.py': (
        1,
        "ARAC: ffmpeg ikilisi (PATH + imageio_ffmpeg) — dosya P6b'de importorskip için dönüştürüldü; aynı dosyaya ikinci parti çakışmasın diye bırakıldı (imageio-ffmpeg requirements'ta — sonraki partide dönüştürülebilir)",
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
    'tests/test_kabin_CV_mqtt_kimligi_pemf_cv_Y73.py': (
        1,
        'ARAC: mosquitto ikilisi (`mosquitto_aparat.ikili()`) — K5 kafesi mosquitto alt sürecini reddeder (ORTAK §2), ZORUNLU kolu bu ortamda ölçülemez; Windows CI paketteki 2.0.18 ile koşar — dönüşüm + ölçüm ORKESTRATÖRDE',
    ),
    'tests/test_kaldirma_yetim_surec_temizligi.py': (
        6,
        'ARAC: makensis / PowerShell — kapı yetim süreç temizliğini gerçek alt süreçlerle koşturur; K5-F klonunda koşturulmadı — dönüşüm (arac_donustur.py) + ölçüm ORKESTRATÖRDE',
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
