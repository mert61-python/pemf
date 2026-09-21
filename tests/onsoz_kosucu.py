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

Kullanım:  python tests/onsoz_kosucu.py <depo_koku> <json_dosya_listesi>
Çıktı   :  son satırda JSON — [[rel, hata_metni], ...]
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import sys
from pathlib import Path


def onsoz_dugumleri(agac: ast.Module) -> list[ast.stmt]:
    """Üst-düzey gövde — YALNIZ `if __name__ == "__main__"` bloğu atılır.

    ⚠️ İLK YAZIMDA "ilk def/class'a kadar" alıyordum ve KAPI KÖR KALDI: eklediğim
    `sys.path` kurulum bloğu bir `def _depo_koku` tanımlıyor, önsöz orada kesiliyor ve
    ASIL IMPORT satırına hiç ulaşılmıyordu. Mutasyon (yol kurulumunu boşaltmak) bu yüzden
    yeşil kalmıştı — betik gerçekte ölüyken.

    `def`/`class` çalıştırmak zararsızdır (yalnız ad bağlar, gövde koşmaz). Riskli olan
    üst-düzey ÇAĞRILARDIR; onlar da `except Exception: pass` ile yutulur — bu kapının
    konusu YALNIZ import çözümüdür.
    """
    out: list[ast.stmt] = []
    for d in agac.body:
        if isinstance(d, ast.If):
            kosul = ast.dump(d.test)
            if "__name__" in kosul and "__main__" in kosul:
                continue  # giris noktasi — KOSTURULMAZ
        # ⚠️ ÇIPLAK ÇAĞRI ATILIR (bare `Expr`). Tam gövdeyi koşturmak SÜİTİ ASTI: bir
        #    betiğin üst-düzey çağrısı bloke etti. Tek istisna `sys.path` kurulumudur —
        #    ölçmek istediğimiz şey tam olarak odur.
        if isinstance(d, ast.Expr):
            kaynak = ast.dump(d)
            if "sys" not in kaynak or "path" not in kaynak:
                continue
        out.append(d)
    return out


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


def bir_betik(kok: Path, rel: str) -> tuple[str, str] | None:
    p = kok / rel
    try:
        agac = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as e:
        return (rel, f"SyntaxError: {e}")
    kod = compile(ast.Module(body=onsoz_dugumleri(agac), type_ignores=[]), str(p), "exec")
    kapsam = {"__file__": str(p), "__name__": "onsoz_denemesi"}
    eski_yol = list(sys.path)
    sys.path = dar_yol(p, kok)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            exec(kod, kapsam)  # noqa: S102 — ölçüm aracı; yalnız önsöz koşar
    except ModuleNotFoundError as e:
        return (rel, f"ModuleNotFoundError: {e}")
    except ImportError as e:
        return (rel, f"ImportError: {e}")
    except SystemExit:
        pass
    except Exception:
        # ⚠️ BU KAPININ KONUSU YALNIZ IMPORT. Önsözde ortam/dosya hatası olabilir
        # (ör. eksik ayar dosyası) — o ayrı bir arızadır, burada susturulur.
        pass
    finally:
        sys.path = eski_yol
        # Betiğin import ettikleri sonraki betiği etkilemesin.
        for ad in list(sys.modules):
            if ad not in _TEMIZ_MODULLER:
                sys.modules.pop(ad, None)
    return None


def main() -> int:
    kok = Path(sys.argv[1])
    dosyalar = json.loads(sys.argv[2])
    _TEMIZ_MODULLER.update(sys.modules)
    sonuc = [x for x in (bir_betik(kok, rel) for rel in dosyalar) if x]
    print(json.dumps(sonuc, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
