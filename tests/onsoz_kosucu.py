# -*- coding: utf-8 -*-
"""BETİK ÖNSÖZÜ KOŞTURUCU — `tests/test_betikler_ACILIYOR.py` alt-süreçte bunu çağırır.

⚠️ NEDEN AYRI DOSYA: kapı, betiğin `sys.path` kurulumunun GERÇEKTEN çalıştığını ölçmeli.
   Kaynakta `sys.path.insert` DİZESİNİ aramak kördü — mutasyon döngüyü boşalttığında
   (`for _yol in ():`) dize yerinde kaldığı için kapı yeşil kalmıştı.

⚠️ YALNIZ ÖNSÖZ koşar: modül gövdesinin ilk `def`/`class`a kadarki kısmı. `sys.path`
   kurulumu ve import'lar oradadır; port açma / dosya yazma gibi asıl iş ilerideki
   fonksiyonlardadır ve KOŞTURULMAZ.

⚠️ `sys.path` BİLEREK daraltılır: yalnız betiğin kendi dizini + site-packages. Test süreci
   `conftest` yüzünden `apps/backend`i zaten taşıyor; onu bırakırsak ölü betikler ÇÖZÜLÜR
   görünür ve kapı hiçbir şey ölçmez.

⚠️ `--ic-importlar` (D0Ö.19, B-10.32): önsöz yalnız ÜST-DÜZEY import'ları ölçer; fonksiyon ya da
   `try` İÇİNDEKİ import'lar (`def _sirlari_oku(): from utils import …`) koşturulmadığı için
   F4 taşımasında ölen betikler (emanet, vault tatbikatı, XAI ses kolu, soak veri kökü) açılışta
   SAĞLAM göründü. Bu kipte, gövde KOŞTURULMADAN, betiğin AST'sindeki TÜM birinci-taraf import
   düğümlerinin üst paketi önsözün kurduğu `sys.path` ile `importlib.util.find_spec`'le çözülür
   ve çözümün deponun KANONİK konumuna (`kok/<ad>` ya da `kok/apps/backend/<ad>`) düştüğü
   denetlenir (site-packages'taki aynı adlı paket, depo içindeki bayat kopya ve düzenli paketin
   ad-alanı parçası sayılmaz).

⚠️ KÖR ALANLAR (tasarım gereği; D0Ö.19 ek'te ölçüldü, bugün hiçbiri gerçekleşmiyor):
   · değişken argümanlı dinamik import (`importlib.import_module(mod_yolu)`, `runpy`, `-c` dizeleri) —
     yalnız SABİT dize argümanlı `import_module`/`__import__` taranır;
   · göreli import'lar; `from modul import ad`daki öznitelik `ad`; `from paket import ad`daki `ad`
     yalnız paketin `__init__`i bir şey BAĞLIYORSA (öznitelik olabilir — karar için `__init__` AST'si
     çözümlenmeli, yapılmadı). `__init__`i yalnız docstring olan ya da hiç olmayan (ad-alanı) pakette
     `ad` YALNIZ alt modül olabilir → D0Ö.19 ek-3'ten beri dosya sisteminde aranır
     (`from utils import secrets_manager`); noktalı adlar (`utils.x`) D0Ö.20 ek'ten beri aranır;
   · modül düzeyinde, yol kurulumundan ÖNCE çağrılan bir fonksiyonun içindeki import;
   · `dar_yol` betik dizinini yola koyar; gömülü `._pth` çalışma anında koymaz (kapı daha hoşgörülü).

Kullanım:  python tests/onsoz_kosucu.py <depo_koku> <json_dosya_listesi> [--ic-importlar]
Çıktı   :  son satırda JSON — [[rel, hata_metni], ...]; `--ic-importlar` kipinde ondan önce
           `DENETLENEN_ONEKI` + JSON [[rel, ad], ...] (gerçekten çözülmeye çalışılan çiftler).
"""

from __future__ import annotations

import ast
import contextlib
import copy
import importlib.util
import io
import json
import os
import sys
import traceback
from pathlib import Path

#: `--ic-importlar` bulgularının öneki — kapı yalnız bunları süzer (önsöz hataları ayrı kapıda).
IC_IMPORT_ONEKI = "COZULEMEYEN_IC_IMPORT"
#: Denetlenen (betik, ad) çiftleri satırının öneki — kapının VAKUM ölçüsü.
DENETLENEN_ONEKI = "DENETLENEN_IC_IMPORTLAR "


def onsoz_dugumleri(agac: ast.Module) -> list[ast.stmt]:
    """SON ÜST-DÜZEY IMPORT'a kadarki gövde — ondan sonrası ASLA koşturulmaz.

    🔴 BU KURAL BİR YAN ETKİDEN DOĞDU (ölçüldü 2026-09-22): `build_tools/make_base_zip.py`
    `main()` KULLANMIYOR — tüm işini üst düzeyde yapıyor ve `_yaz(OUT_APP, …)` bir *Assign*
    olduğu için önceki sürüm onu ÇALIŞTIRIYORDU: her süit koşumunda `base-app.zip`
    yeniden üretiliyor, koşum 61,5 sn sürüyordu. Kapı, ölçtüğü şeyi BOZUYORDU.

    Bu kapının tek iddiası "import'lar çözülüyor mu". O hâlde son import'tan sonrasına
    hiç ihtiyaç yok: prefix alınır. Yol kurulumu (`sys.path`) zaten import'lardan ÖNCE
    olmak zorundadır, dolayısıyla prefix'in içindedir.

    ⚠️ `if __name__ == "__main__"` blokları ayrıca atılır (prefix'e düşerse bile).
    """
    son_import = -1
    for i, d in enumerate(agac.body):
        if isinstance(d, (ast.Import, ast.ImportFrom)):
            son_import = i
    if son_import < 0:
        return []
    return [d for d in agac.body[: son_import + 1] if not _main_blogu_mu(d)]


def _main_blogu_mu(d: ast.stmt) -> bool:
    if not isinstance(d, ast.If):
        return False
    kosul = ast.dump(d.test)
    return "__name__" in kosul and "__main__" in kosul


def _yola_dokunur(d: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Attribute) and n.attr == "path" and isinstance(n.value, ast.Name) and n.value.id == "sys"
        for n in ast.walk(d)
    )


def _tanimladigi_adlar(d: ast.stmt) -> set[str]:
    if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {d.name}
    if isinstance(d, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        hedefler = d.targets if isinstance(d, ast.Assign) else [d.target]
        return {n.id for h in hedefler for n in ast.walk(h) if isinstance(n, ast.Name)}
    return set()


def _kullandigi_adlar(d: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(d) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


#: Yol diliminin dayanabileceği tanım türleri. ⚠️ Sınıf gövdesi ve bileşik deyim KOŞTURULMAZ.
_DILIM_TANIMLARI = (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.FunctionDef, ast.AsyncFunctionDef)


def _yola_budanmis(d: ast.stmt) -> ast.stmt:
    """Bileşik deyimin (for/if/while/try/with) gövdelerinde YALNIZ `sys.path`e dokunan alt deyimler kalır.

    ⚠️ D0Ö.19 ek: dilim bileşik deyimi BÜTÜNÜYLE koşturuyordu — `for`un içindeki yan etki (dosya
    yazma) de koşuyordu. Başlık (koşul, döngü değişkeni) korunur; boşalan gövdeye `pass` konur.
    """
    d = copy.deepcopy(d)
    for sahip in [d, *getattr(d, "handlers", [])]:
        for alan in ("body", "orelse", "finalbody"):
            govde = getattr(sahip, alan, None)
            if not isinstance(govde, list) or not govde or not isinstance(govde[0], ast.stmt):
                continue
            kalan = [_yola_budanmis(x) for x in govde if _yola_dokunur(x)]
            setattr(sahip, alan, kalan or ([] if alan == "orelse" else [ast.Pass()]))
    return d


def yol_kurulumu_dugumleri(agac: ast.Module) -> list[ast.stmt]:
    """ÖNSÖZDEN SONRA gelen üst-düzey `sys.path` kurulumu + YALNIZ onun dayandığı tanımlar.

    ⚠️ Betik yolu son import'tan SONRA kurabilir (`KOK = …; sys.path.insert(0, str(KOK))`, ardından
    import yalnız fonksiyonlarda): önsöz o satırı koşturmaz ve fonksiyon içi import'lar SAHTE kırmızı
    olur (ölçüldü: `xai_batch_rapor` → `ai_hub`). Kalan gövdenin TAMAMI KOŞTURULMAZ (make_base_zip
    dersi): yalnız `sys.path`e dokunan deyimler (bileşikse budanmış) ve onların (geçişli) kullandığı,
    SON `sys.path` deyiminden ÖNCE gelen atama/fonksiyon tanımları (sonradan yeniden atama koşmaz).
    """
    govde = [d for d in agac.body if not _main_blogu_mu(d)]
    son_import = max((i for i, d in enumerate(govde) if isinstance(d, (ast.Import, ast.ImportFrom))), default=-1)
    kalan = govde[son_import + 1 :]
    yol_sira = [
        i
        for i, d in enumerate(kalan)
        if not isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and _yola_dokunur(d)
    ]
    if not yol_sira:
        return []
    secili = {i: _yola_budanmis(kalan[i]) for i in yol_sira}
    gereken: set[str] = set().union(*(_kullandigi_adlar(d) for d in secili.values()))
    adaylar = [(i, d) for i, d in enumerate(kalan[: yol_sira[-1]]) if isinstance(d, _DILIM_TANIMLARI)]
    degisti = True
    while degisti:
        degisti = False
        for i, d in adaylar:
            if i not in secili and _tanimladigi_adlar(d) & gereken:
                secili[i] = d
                gereken |= _kullandigi_adlar(d)
                degisti = True
    return [secili[i] for i in sorted(secili)]


def dar_yol(betik: Path, depo_koku: Path) -> list[str]:
    """Betiğin GERÇEK açılış yolu: kendi dizini + yorumlayıcının kendi yolları.

    ⚠️ DEPO yolları ATILIR (conftest `apps/backend`i ekliyor; bırakılırsa ölü betikler
    çözülür görünür ve kapı hiçbir şey ölçmez).
    ⚠️ AMA stdlib/DLL dizinleri KALIR. İlk yazımda yalnız `site-packages` bırakmıştım ve
    gömülü Python'un DLL dizini düştüğü için 9 betik `No module named '_socket'` verdi —
    ürün hatası değil, ARAÇ hatasıydı.
    """
    kok = str(depo_koku).replace("\\", "/").rstrip("/").lower()
    disarida = []
    for x in sys.path:
        if not x:
            continue
        n = str(Path(x).resolve()).replace("\\", "/").rstrip("/").lower()
        if n == kok or n.startswith(kok + "/"):
            continue  # depo yolu — DUSER
        disarida.append(x)
    return [str(betik.parent)] + disarida


#: Ilk betik kosmadan ONCEKI modul kumesi. ⚠️ Her betikten sonra BUNA donulur; yoksa
#: birinci betigin import ettigi `utils` sonrakilerin `sys.modules`unda kalir ve OLU
#: betik CANLI gorunur (mutasyon bunu yakaladi).
_TEMIZ_MODULLER: dict = {}


def ilk_taraf_adlari(kok: Path) -> set[str]:
    """Deponun KENDİ üst-düzey Python adları: kökteki ve `apps/backend` altındaki modül/paketler.

    ⚠️ Yalnız bunlar denetlenir: üçüncü-taraf isteğe bağlı bağımlılıklar `try` içinde BİLEREK
    eksik olabilir (`sqlcipher3` yoksa `pysqlcipher3`); birinci-taraf bir ad ise asla eksik olamaz.
    """
    adlar: set[str] = set()
    for taban in (kok, kok / "apps" / "backend"):
        if not taban.is_dir():
            continue
        for p in taban.iterdir():
            if p.name.startswith(".") or p.name == "__pycache__":
                continue
            if p.is_dir():
                if any(p.glob("*.py")):
                    adlar.add(p.name)
            elif p.suffix == ".py":
                adlar.add(p.stem)
    return adlar


def _kanonik_konumlar(ad: str, kok: Path) -> list[Path] | None:
    """`ad` ŞU ANKİ `sys.path` ile deponun KANONİK konumuna mı çözülüyor? (modül KOŞTURULMAZ)

    Dönüş: paketse arama dizinleri, düz modülse `[]`, çözülmüyor / kanonik değilse `None`.

    ⚠️ D0Ö.19 ek: "depo içinde HERHANGİ bir yer" yetmiyordu — betik dizini yolda olduğu için depo
    içindeki bayat bir kopya (`scripts/utils/`) çözüm sayılıyordu. Kanonik: `kok/<ad>` ya da
    `kok/apps/backend/<ad>` (paket dizini ya da `<ad>.py`). Depoda DÜZENLİ paket olan bir ad için
    ad-alanı spec'i de reddedilir: düzenli paket yoldaysa Python ad-alanı döndürmez; dönmesi
    gerçek paketin yolda OLMADIĞI demektir.
    """
    mod = sys.modules.get(ad)
    try:
        spec = mod.__spec__ if mod is not None else importlib.util.find_spec(ad)
    except (ImportError, ValueError):
        return None
    if spec is None:
        return None
    tabanlar = (kok.resolve(), kok.resolve() / "apps" / "backend")
    try:
        if spec.submodule_search_locations is not None:
            konumlar = {Path(x).resolve() for x in spec.submodule_search_locations}
            if not konumlar or not konumlar <= {(t / ad).resolve() for t in tabanlar}:
                return None
            duzenli = any((t / ad / "__init__.py").is_file() for t in tabanlar)
            return None if duzenli and spec.origin in (None, "namespace") else sorted(konumlar)
        dosya = bool(spec.origin) and Path(spec.origin).resolve() in {(t / f"{ad}.py").resolve() for t in tabanlar}
        return [] if dosya else None
    except (OSError, ValueError):
        return None


def _depoda_cozuluyor(ad: str, kok: Path) -> bool:
    return _kanonik_konumlar(ad, kok) is not None


def _depo_ici_mi(dosya: str, kok: Path) -> bool:
    try:
        return Path(dosya).resolve().is_relative_to(kok.resolve())
    except (OSError, ValueError):
        return False


def _alt_modul_var(tam_ad: str, konumlar: list[Path]) -> bool:
    """`a.b.c`: üst paketin kanonik dizinlerinden başlayarak her parça dosya sisteminde var mı?

    ⚠️ D0Ö.20 ek (tur 4): yalnız üst paket çözülüyordu — `utils.file_acl` taşınsa kapı YEŞİL kalırdı.
    Modül KOŞTURULMAZ: alt paket dizini (`__init__`li ya da ad-alanı) ya da SON parça için `<parça>.py`.
    """
    parcalar = tam_ad.split(".")[1:]
    for i, parca in enumerate(parcalar):
        dizinler = [k / parca for k in konumlar if _girdi_birebir(k, parca) and (k / parca).is_dir()]
        if dizinler:
            konumlar = dizinler
            continue
        return i == len(parcalar) - 1 and any(
            _girdi_birebir(k, f"{parca}.py") and (k / f"{parca}.py").is_file() for k in konumlar
        )
    return True


def _paket_dizinleri(tam_ad: str, konumlar: list[Path]) -> list[Path]:
    """`a.b` bir PAKETSE (dizin) arama dizinleri; düz modül ya da yoksa `[]`."""
    for parca in tam_ad.split(".")[1:]:
        konumlar = [k / parca for k in konumlar if _girdi_birebir(k, parca) and (k / parca).is_dir()]
    return konumlar


def _init_ad_baglamaz(dizin: Path) -> bool:
    """Paket dizininin `__init__`i HİÇBİR ad bağlayamaz mı? (yok = ad-alanı parçası; yalnız docstring)

    ⚠️ Temkinli: docstring dışında TEK deyim (`from __future__` bile — `annotations` adını bağlar) varsa
    hayır → çağıran karar vermez (ad öznitelik olabilir). Yorumlar AST'de yoktur.
    """
    ini = dizin / "__init__.py"
    if not ini.is_file():
        return True
    try:
        govde = ast.parse(ini.read_text(encoding="utf-8", errors="replace")).body
    except (OSError, SyntaxError, ValueError):
        return False
    return all(isinstance(d, ast.Expr) and isinstance(d.value, ast.Constant) for d in govde)


def _from_ad_hatalari(d: ast.ImportFrom, konumlar: list[Path], bakilan: set[str]) -> list[str]:
    """`from paket import ad`: `__init__`i ad bağlamayan pakette `ad` YALNIZ alt modül olabilir.

    ⚠️ D0Ö.19 ek-3 (tur 6): `ad` hiç denetlenmiyordu — `utils/secrets_manager.py` taşınsa
    `from utils import secrets_manager` (emanet, kurtarma) kapıda YEŞİL kalırdı. `__init__` bir şey
    bağlıyorsa `ad` öznitelik olabilir: karar VERİLMEZ (kör alan, modül başlığında yazılı).
    """
    dizinler = _paket_dizinleri(d.module, konumlar)
    hatalar: list[str] = []
    for a in d.names:
        tam = f"{d.module}.{a.name}"
        if a.name == "*" or not dizinler or tam in bakilan:
            continue
        if _alt_modul_var(tam, konumlar):
            bakilan.add(tam)
        elif all(_init_ad_baglamaz(k) for k in dizinler):
            bakilan.add(tam)
            hatalar.append(
                f"{IC_IMPORT_ONEKI}: No module named '{tam}' (satir {d.lineno}; `{d.module}` __init__'i ad "
                "baglamiyor — `ad` yalniz alt modul olabilir)"
            )
    return hatalar


def _girdi_birebir(dizin: Path, ad: str) -> bool:
    """`ad` dizinde HARFİ HARFİNE var mı? D0Ö.19 ek-2 (tur 5): import harfe DUYARLI (Windows'ta da;
    FileFinder dizin listesini birebir karşılaştırır), `Path.is_file()` NTFS'te DUYARSIZ — harfi yanlış
    alt modül Windows'ta çözülmüş sayılıyordu."""
    try:
        return ad in os.listdir(dizin)
    except OSError:
        return False


def _import_adlari(d: ast.AST) -> list[str]:
    """Düğümün import ettiği TAM (noktalı) adlar (göreli import ve değişken argümanlı dinamik import: yok)."""
    if isinstance(d, ast.Import):
        return [a.name for a in d.names]
    if isinstance(d, ast.ImportFrom) and d.level == 0 and d.module:
        return [d.module]
    if (
        isinstance(d, ast.Call)
        and (getattr(d.func, "id", None) or getattr(d.func, "attr", None)) in ("import_module", "__import__")
        and d.args
        and isinstance(d.args[0], ast.Constant)
        and isinstance(d.args[0].value, str)
    ):
        return [d.args[0].value]
    return []


def ic_import_hatalari(
    agac: ast.Module, kok: Path, ilk_taraf: set[str], denetlenen: set[str] | None = None
) -> list[str]:
    """GÖVDE KOŞTURULMADAN: fonksiyon/`try` içi dahil TÜM birinci-taraf import'lar çözülüyor mu?

    Üst paket `sys.path` ile (kanonik konum), noktalı alt modül dosya sisteminde aranır.
    `denetlenen`: çözülmeye çalışılan adlar (üst ve noktalı) buraya eklenir (kapının vakum ölçüsü).
    ⚠️ `from paket import ad`daki `ad`: alt modülse ya da `__init__`i ad bağlamayan pakette aranır
    (`_from_ad_hatalari`); `__init__` bir şey bağlıyorsa öznitelik olabilir → denetlenmez.
    """
    hatalar: list[str] = []
    bakilan: set[str] = set() if denetlenen is None else denetlenen
    konumlar: dict[str, list[Path] | None] = {}
    for d in ast.walk(agac):
        for tam in _import_adlari(d):
            ad = tam.split(".")[0]
            if ad not in ilk_taraf or tam in bakilan:
                continue
            bakilan.add(tam)
            if ad not in konumlar:
                bakilan.add(ad)
                konumlar[ad] = _kanonik_konumlar(ad, kok)
                if konumlar[ad] is None:
                    hatalar.append(f"{IC_IMPORT_ONEKI}: No module named '{ad}' (satir {d.lineno})")
            if konumlar[ad] is not None and tam != ad and not _alt_modul_var(tam, konumlar[ad]):
                hatalar.append(f"{IC_IMPORT_ONEKI}: No module named '{tam}' (satir {d.lineno})")
        if isinstance(d, ast.ImportFrom) and d.level == 0 and d.module and konumlar.get(d.module.split(".")[0]):
            hatalar += _from_ad_hatalari(d, konumlar[d.module.split(".")[0]], bakilan)
    return hatalar


def bir_betik(
    kok: Path, rel: str, ic_importlar: bool = False, denetlenen: list[tuple[str, str]] | None = None
) -> list[tuple[str, str]]:
    p = kok / rel
    try:
        agac = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as e:
        return [(rel, f"SyntaxError: {e}")]
    kod = compile(ast.Module(body=onsoz_dugumleri(agac), type_ignores=[]), str(p), "exec")
    kapsam = {"__file__": str(p), "__name__": "onsoz_denemesi"}
    eski_yol = list(sys.path)
    sys.path = dar_yol(p, kok)
    sonuc: list[tuple[str, str]] = []
    try:
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                exec(kod, kapsam)  # noqa: S102 — ölçüm aracı; yalnız önsöz koşar
        except ModuleNotFoundError as e:
            sonuc.append((rel, f"ModuleNotFoundError: {e}"))
        except ImportError as e:
            sonuc.append((rel, f"ImportError: {e}"))
        except SystemExit:
            pass
        except RuntimeError as e:
            # ⚠️ D0Ö.19 ek: `_depo_koku` işaret bulamayınca RuntimeError atar → betik AÇILIŞTA ölür
            # ve önsözde ondan sonraki import'lar HİÇ denenmez. Yutulursa kapı YEŞİL kalırdı.
            # D0Ö.19 ek-2 (tur 5): yalnız DEPO kodundan (betik ya da birinci-taraf modül) gelen sayılır —
            # üçüncü-taraf içinden gelen (bu koşucu modülleri silip yeniden import ettiği için bir C uzantısının
            # ikinci yüklenişi gibi) ortam/koşucu artefaktıdır; sıraya bağlı sahte KIRMIZI üretmesin.
            cerceveler = traceback.extract_tb(e.__traceback__)
            if cerceveler and _depo_ici_mi(cerceveler[-1].filename, kok):
                sonuc.append((rel, f"RuntimeError: {e}"))
        except Exception:
            # ⚠️ BU KAPININ KONUSU YALNIZ IMPORT. Önsözde ortam/dosya hatası olabilir
            # (ör. eksik ayar dosyası) — o ayrı bir arızadır, burada susturulur.
            pass
        if ic_importlar:
            # Önsözden sonra kurulan yol (yalnız sys.path dilimi — kalan gövde KOŞMAZ).
            dilim = yol_kurulumu_dugumleri(agac)
            if dilim:
                modul = ast.fix_missing_locations(ast.Module(body=dilim, type_ignores=[]))
                try:
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        exec(compile(modul, str(p), "exec"), kapsam)  # noqa: S102
                except Exception as e:
                    # ⚠️ D0Ö.19 ek: YUTULMAZ — yol kurulamayan betik açılışta ÖLÜR; fonksiyon içi
                    # import'lar başka bir yoldan (betik dizini) çözülse bile.
                    sonuc.append((rel, f"{IC_IMPORT_ONEKI}: yol kurulumu DUSTU — {type(e).__name__}: {e}"))
            # ⚠️ `sys.path` HÂLÂ betiğin kurduğu hâlde: betiğin KENDİ yol kurulumu ölçülür.
            bakilan: set[str] = set()
            sonuc += [(rel, h) for h in ic_import_hatalari(agac, kok, ilk_taraf_adlari(kok), bakilan)]
            if denetlenen is not None:
                denetlenen += [(rel, ad) for ad in sorted(bakilan)]
    finally:
        sys.path = eski_yol
        # Betiğin import ettikleri sonraki betiği etkilemesin.
        for ad in list(sys.modules):
            if ad not in _TEMIZ_MODULLER:
                sys.modules.pop(ad, None)
    return sonuc


def main() -> int:
    kok = Path(sys.argv[1])
    dosyalar = json.loads(sys.argv[2])
    ic_importlar = "--ic-importlar" in sys.argv[3:]
    _TEMIZ_MODULLER.update(sys.modules)
    denetlenen: list[tuple[str, str]] = []
    sonuc = [x for rel in dosyalar for x in bir_betik(kok, rel, ic_importlar, denetlenen)]
    if ic_importlar:
        print(DENETLENEN_ONEKI + json.dumps(denetlenen, ensure_ascii=False))
    print(json.dumps(sonuc, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
