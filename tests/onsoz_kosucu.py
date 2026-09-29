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
   ve çözümün DEPO İÇİNE düştüğü denetlenir (site-packages'taki aynı adlı bir paket sayılmaz).

Kullanım:  python tests/onsoz_kosucu.py <depo_koku> <json_dosya_listesi> [--ic-importlar]
Çıktı   :  son satırda JSON — [[rel, hata_metni], ...]
"""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path

#: `--ic-importlar` bulgularının öneki — kapı yalnız bunları süzer (önsöz hataları ayrı kapıda).
IC_IMPORT_ONEKI = "COZULEMEYEN_IC_IMPORT"


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


def yol_kurulumu_dugumleri(agac: ast.Module) -> list[ast.stmt]:
    """ÖNSÖZDEN SONRA gelen üst-düzey `sys.path` kurulumu + YALNIZ onun dayandığı tanımlar.

    ⚠️ Betik yolu son import'tan SONRA kurabilir (`KOK = …; sys.path.insert(0, str(KOK))`, ardından
    import yalnız fonksiyonlarda): önsöz o satırı koşturmaz ve fonksiyon içi import'lar SAHTE kırmızı
    olur (ölçüldü: `xai_batch_rapor` → `ai_hub`). Kalan gövdenin TAMAMI KOŞTURULMAZ (make_base_zip
    dersi): yalnız `sys.path`e dokunan deyimler ve onların (geçişli) kullandığı atama/fonksiyonlar.
    """
    govde = [d for d in agac.body if not _main_blogu_mu(d)]
    son_import = max((i for i, d in enumerate(govde) if isinstance(d, (ast.Import, ast.ImportFrom))), default=-1)
    kalan = govde[son_import + 1 :]
    secili = {
        id(d)
        for d in kalan
        if not isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and _yola_dokunur(d)
    }
    if not secili:
        return []
    gereken: set[str] = set()
    for d in kalan:
        if id(d) in secili:
            gereken |= _kullandigi_adlar(d)
    degisti = True
    while degisti:
        degisti = False
        for d in kalan:
            if id(d) not in secili and _tanimladigi_adlar(d) & gereken:
                secili.add(id(d))
                gereken |= _kullandigi_adlar(d)
                degisti = True
    return [d for d in kalan if id(d) in secili]


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


def _depoda_cozuluyor(ad: str, kok: Path) -> bool:
    """`ad` ŞU ANKİ `sys.path` ile çözülüyor VE çözüm depo içinde mi? (modül KOŞTURULMAZ)"""
    mod = sys.modules.get(ad)
    try:
        spec = mod.__spec__ if mod is not None else importlib.util.find_spec(ad)
    except (ImportError, ValueError):
        return False
    if spec is None:
        return False
    konumlar = list(spec.submodule_search_locations or [])
    if spec.origin and spec.origin not in ("namespace", "built-in", "frozen"):
        konumlar.append(spec.origin)
    depo = kok.resolve()
    for x in konumlar:
        try:
            if Path(x).resolve().is_relative_to(depo):
                return True
        except (OSError, ValueError):
            continue
    return False


def ic_import_hatalari(agac: ast.Module, kok: Path, ilk_taraf: set[str]) -> list[str]:
    """GÖVDE KOŞTURULMADAN: fonksiyon/`try` içi dahil TÜM birinci-taraf import'lar çözülüyor mu?"""
    hatalar: list[str] = []
    bakilan: set[str] = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            adlar = [a.name.split(".")[0] for a in d.names]
        elif isinstance(d, ast.ImportFrom) and d.level == 0 and d.module:
            adlar = [d.module.split(".")[0]]
        else:
            continue  # göreli import: betik paket değil, önsöz kapısının konusu
        for ad in adlar:
            if ad not in ilk_taraf or ad in bakilan:
                continue
            bakilan.add(ad)
            if not _depoda_cozuluyor(ad, kok):
                hatalar.append(f"{IC_IMPORT_ONEKI}: No module named '{ad}' (satir {d.lineno})")
    return hatalar


def bir_betik(kok: Path, rel: str, ic_importlar: bool = False) -> list[tuple[str, str]]:
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
        except Exception:
            # ⚠️ BU KAPININ KONUSU YALNIZ IMPORT. Önsözde ortam/dosya hatası olabilir
            # (ör. eksik ayar dosyası) — o ayrı bir arızadır, burada susturulur.
            pass
        if ic_importlar:
            # Önsözden sonra kurulan yol (yalnız sys.path dilimi — kalan gövde KOŞMAZ).
            dilim = yol_kurulumu_dugumleri(agac)
            if dilim:
                try:
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        exec(compile(ast.Module(body=dilim, type_ignores=[]), str(p), "exec"), kapsam)  # noqa: S102
                except Exception:  # noqa: S110 — yol kurulamadıysa import'lar aşağıda KIRMIZI olur
                    pass
            # ⚠️ `sys.path` HÂLÂ betiğin kurduğu hâlde: betiğin KENDİ yol kurulumu ölçülür.
            sonuc += [(rel, h) for h in ic_import_hatalari(agac, kok, ilk_taraf_adlari(kok))]
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
    sonuc = [x for rel in dosyalar for x in bir_betik(kok, rel, ic_importlar)]
    print(json.dumps(sonuc, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
