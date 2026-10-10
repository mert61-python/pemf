# -*- coding: utf-8 -*-
"""LOGLAYAN AMA KÖR handler olmasın — "ele alınmış" görünüp KÖK NEDENİ gizleyenler.

🔴 ÖLÇÜLEN ZARAR (A9, 2026-09-20). `_ai_warmup` içindeki

    except Exception as e:
        logger.info("AI ısıtma atlandı (%s: %s)", type(e).__name__, e)

satırı, `torch`un yarım kalmasının kök nedenini GİZLEDİ. Logda "AI ısıtma atlandı"
yazıyordu; gerçekte o süreçteki **tüm** AI uçları 500 veriyordu (tek koşumda 38 kez).
Kök neden ancak `exc_info=True` açılınca göründü:
`KeyError: 'sympy.assumptions.cnf'` → eşzamanlı `import torch` yarışı.
Aynı gün `_scratch_isit_baslat`ın aynı biçimdeki satırı da YANILTICI teşhis üretti
("model/cell hazır değil" derken gerçek sebep zehirlenmiş torch'tu).

⚠️ BU SINIF `except: pass` DEĞİLDİR ve sessiz-except triyajında "ele alınmış" sayılır.
   Tam da bu yüzden daha sinsidir: bakan kişi "loglanıyor" deyip geçer. Ayrı kapı şart.

ÖLÇÜT (hepsi aynı anda sağlanırsa KÖR):
  1. `try` gövdesi ALT SİSTEM AÇAN bir iş yapıyor (import / connect / Thread / start /
     load / init) → düşmesi tek bir işlemi değil BİR YETENEĞİ kaybettirir
  2. handler logluyor ama `exc_info`/`stack_info`/`logging.exception` YOK
  3. seviye DÜŞÜK (info/debug) → operatör/destek bunu "normal" okur
  4. handler yeniden FIRLATMIYOR

⚠️ Sessiz (`pass`) handler'lar BU KAPININ KONUSU DEĞİL — onların kapısı
   `tests/test_sessiz_yutma_TEHLIKELI_DEGIL.py`. Burada iddia "log var ama KÖR".
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest
from utils.path_utils import kaynak_kokunu_bul

KOK = kaynak_kokunu_bul(__file__)

DUSUK_SEVIYE = {"info", "debug"}
ALT_SISTEM_ISARETLERI = {
    "import_module",
    "find_spec",
    "agir_import",
    "torch_isit",
    "reload",
    "connect",
    "start",
    "Thread",
    "serve",
    "bind",
    "listen",
    "open_port",
    "Serial",
    "load",
    "isit",
    "warmup",
    "initialize",
    "init",
}

#: MUAFİYET — (dosya sonu, fonksiyon adı) + GEREKÇE + muafiyetin HÂLÂ geçerli olduğunu
#: ölçen kanıt dizesi. ⚠️ Kaba yol muafiyeti YASAK: muafiyet, o dosyanın TOPLU sonucu
#: tam zincirle bildirdiğini de DOĞRULAR. Kanıt kaybolursa muafiyet düşer.
MUAFIYETLER = {
    ("database/treatment_history_db.py", "_connect_sqlcipher_if_configured"): (
        "Aday-anahtar döngüsü: her tek deneme BEKLENEN başarısızlıktır (cache → legacy → tam "
        "çözümleme). Tek tek zincir basmak gürültü olurdu; TOPLU sonuç fonksiyon sonunda "
        "tam zincirle bildirilir.",
        "exc_info=last_err",
    ),
}


def _cagri_adi(d: ast.AST) -> str:
    f = getattr(d, "func", None)
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def _govde_agaci(govde):
    return ast.Module(body=govde, type_ignores=[])


_SEVIYE_SABITLERI = {
    "NOTSET": 0,
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "WARN": 30,
    "ERROR": 40,
    "CRITICAL": 50,
    "FATAL": 50,
}


def _log_seviyesi(ad: str, cagri: ast.Call) -> str:
    """Çağrının ETKİN seviyesi. ⚠️ D2.37 (B-10.244): `.log(<seviye>, …)` eskiden "log" adıyla kalıyor ve DÜŞÜK sayılmıyordu —
    `logger.log(logging.INFO, …)` kör handler'ı gizliyordu. Seviye SABİTTEN çözülür (`logging.INFO` / `INFO` / `20`); sabit
    değilse (değişken) bilinmez → düşük SAYILMAZ (kanıt yok)."""
    if ad != "log":
        return ad
    arg = cagri.args[0] if cagri.args else next((k.value for k in cagri.keywords if k.arg == "level"), None)
    deger = None
    if isinstance(arg, ast.Constant) and isinstance(arg.value, int) and not isinstance(arg.value, bool):
        deger = arg.value
    elif isinstance(arg, (ast.Attribute, ast.Name)):
        deger = _SEVIYE_SABITLERI.get(arg.attr if isinstance(arg, ast.Attribute) else arg.id)
    if deger is None:
        return "log?"
    return "debug" if deger <= 10 else "info" if deger <= 20 else "warning"


def _log_cagrilari(govde):
    out = []
    for d in ast.walk(_govde_agaci(govde)):
        if isinstance(d, ast.Call):
            ad = _cagri_adi(d)
            if ad in ("debug", "info", "warning", "error", "critical", "exception", "log"):
                out.append((_log_seviyesi(ad, d), d))
    return out


def _zincir_basar(cagri: ast.Call) -> bool:
    """⚠️ D2.37: `exc_info`/`stack_info` anahtarının VARLIĞI değil DEĞERİ — `False`/`None`/`0` zincir BASMAZ; değişken, çağrı ya da
    doğru sabit (ör. `exc_info=last_err`, `exc_info=True`) basar."""
    # ⚠️ E2-3.13: `stack_info` ÇAĞRI yığınını basar, yakalanan istisnanın zincirini DEĞİL → zincir sayılmaz; `exc_info=(None, None,
    # None)` (hep-None demet) de basmaz.
    for k in cagri.keywords:
        if k.arg == "exc_info":
            if isinstance(k.value, ast.Constant) and not k.value.value:
                continue
            if isinstance(k.value, ast.Tuple) and all(
                isinstance(e, ast.Constant) and e.value is None for e in k.value.elts
            ):
                continue
            return True
    return False


def _olu_test_mu(test: ast.AST) -> bool:
    """E2-3.13: çalışmada hep yanlış koşul — sabit-yanlış, `not <sabit-doğru>`, `TYPE_CHECKING` / `typing.TYPE_CHECKING`."""
    if isinstance(test, ast.Constant):
        return not test.value
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not) and isinstance(test.operand, ast.Constant):
        return bool(test.operand.value)
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _yeniden_firlatir(govde) -> bool:
    """Handler GERÇEKTEN yeniden fırlatıyor mu? ⚠️ D2.37: `if False: raise` / `while False: raise` ÖLÜ daldır — eskiden herhangi bir
    `raise` düğümü "yeniden fırlatıyor" sayılıyor, kör handler kapıdan geçiyordu. Ölü dalın yalnız `else`i erişilebilir."""
    yigin = list(govde)
    while yigin:
        d = yigin.pop()
        if isinstance(d, ast.Raise):
            return True
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue  # E2-3.13: iç tanımın `raise`i handler'ı yeniden fırlatıcı YAPMAZ
        if isinstance(d, (ast.If, ast.While)) and _olu_test_mu(d.test):
            yigin.extend(d.orelse)
            continue
        yigin.extend(ast.iter_child_nodes(d))
    return False


def _alt_sistem_isi(try_govdesi) -> set[str]:
    bulunan = set()
    for d in ast.walk(_govde_agaci(try_govdesi)):
        if isinstance(d, (ast.Import, ast.ImportFrom)):
            bulunan.add("import")
        elif isinstance(d, ast.Call):
            ad = _cagri_adi(d)
            if ad in ALT_SISTEM_ISARETLERI:
                bulunan.add(ad)
    return bulunan


def kor_mu(dugum: ast.Try) -> bool:
    """Tek `try` düğümü KÖR mü? (kapının tek karar noktası — testler bunu sınar)"""
    if not _alt_sistem_isi(dugum.body):
        return False
    for h in dugum.handlers:
        if _yeniden_firlatir(h.body):
            continue
        loglar = _log_cagrilari(h.body)
        if not loglar:
            continue  # sessiz handler → ÖTEKİ kapının konusu
        if not any(s in DUSUK_SEVIYE for s, _ in loglar):
            continue
        if any(s == "exception" for s, _ in loglar):
            continue
        if any(_zincir_basar(c) for _, c in loglar):
            continue
        return True
    return False


def _kapsanan_dosyalar() -> list[Path]:
    ciktilar = subprocess.run(
        ["git", "ls-files", "apps/backend/*.py", "apps/backend/**/*.py"],
        cwd=KOK,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    ).stdout.splitlines()
    return [KOK / r for r in ciktilar if (KOK / r).is_file()]


def _fonksiyon_adi(agac, satir: int) -> str:
    """Satırı içeren EN İÇTEKİ fonksiyonun adı.

    ⚠️ İlk yazımda `ast.walk` sırasındaki SON eşleşme alınıyordu. İç içe fonksiyonlarda
    (ör. `_start_ai_warmup_safe` → `_calistir`) bu DIŞTAKİNİ döndürebiliyordu; o zaman
    aşağıdaki parametreli test aradığı fonksiyonu HİÇ bulamayıp VAKUMDA yeşil kalırdı.
    En küçük aralık = en içteki.
    """
    adaylar = [
        f
        for f in ast.walk(agac)
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.lineno <= satir <= (f.end_lineno or 0)
    ]
    if not adaylar:
        return "?"
    return min(adaylar, key=lambda f: (f.end_lineno or 0) - f.lineno).name


def _muaf_mi(rel: str, fonksiyon: str) -> tuple[bool, str]:
    for (dosya_sonu, fn), (_gerekce, kanit) in MUAFIYETLER.items():
        if rel.replace("\\", "/").endswith(dosya_sonu) and fn == fonksiyon:
            return True, kanit
    return False, ""


# ──────────────────────────────────────────────────────────────────────────
# 0) KARŞIT-KANIT — sınıflandırıcı GERÇEKTEN ayırıyor mu
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kaynak,beklenen,aciklama",
    [
        (
            "try:\n    import torch\nexcept Exception as e:\n    logger.info('atlandi: %s', e)",
            True,
            "A9'un ta kendisi: alt sistem + info + zincir yok",
        ),
        (
            "try:\n    import torch\nexcept Exception as e:\n    logger.warning('x', exc_info=True)",
            False,
            "tam zincir basiliyor",
        ),
        (
            "try:\n    import torch\nexcept Exception:\n    logger.exception('x')",
            False,
            "logging.exception zincir basar",
        ),
        (
            "try:\n    p.unlink()\nexcept Exception as e:\n    logger.info('silinemedi: %s', e)",
            False,
            "alt sistem ACMIYOR — bu kapinin konusu degil",
        ),
        (
            "try:\n    conn = connect(h)\nexcept Exception as e:\n    logger.info('x: %s', e)\n    raise",
            False,
            "yeniden firlatiyor",
        ),
        ("try:\n    import x\nexcept Exception:\n    pass", False, "SESSIZ handler — oteki kapinin konusu"),
        # ⚠️ D2.37 (B-10.244): üç KAÇIŞ biçimi — eski sınıflandırıcı üçünü de "kör değil" sayıyordu.
        (
            "try:\n    import torch\nexcept Exception as e:\n    logger.info('atlandi: %s', e, exc_info=False)",
            True,
            "D2.37: exc_info=False zincir BASMAZ (anahtarın VARLIĞI değil DEĞERİ)",
        ),
        (
            "try:\n    import torch\nexcept Exception as e:\n    logger.log(logging.INFO, 'atlandi: %s', e)",
            True,
            "D2.37: .log(logging.INFO, …) düşük seviyedir",
        ),
        (
            "try:\n    import torch\nexcept Exception as e:\n    logger.info('atlandi: %s', e)\n    if False:\n        raise",
            True,
            "D2.37: ölü `if False: raise` yeniden FIRLATMAZ",
        ),
        (
            "try:\n    import torch\nexcept Exception as e:\n    logger.log(logging.WARNING, 'x: %s', e)",
            False,
            "D2.37 karşıtı: .log(logging.WARNING, …) düşük değil",
        ),
        (
            "try:\n    import torch\nexcept Exception as e:\n    logger.info('x: %s', e, exc_info=e)",
            False,
            "D2.37 karşıtı: exc_info=<istisna> zincir basar",
        ),
        (
            "try:\n    import torch\nexcept Exception as e:\n    logger.info('x: %s', e)\n    if hata_say():\n        raise",
            False,
            "D2.37 karşıtı: koşullu (ölü OLMAYAN) yeniden fırlatma",
        ),
    ],
)
def test_KARSIT_KANIT_siniflandirici_AYIRIYOR(kaynak: str, beklenen: bool, aciklama: str):
    """⚠️ Bu kapı kendi sınıflandırıcısına dayanıyor; önce ONU kanıtla."""
    dugum = [d for d in ast.walk(ast.parse(kaynak)) if isinstance(d, ast.Try)][0]
    assert kor_mu(dugum) is beklenen, f"yanlış sınıflandırma: {aciklama}"


def _a9_try() -> ast.Try:
    """GERÇEK A9 handler'ı: `backend_service._start_ai_warmup_safe` → `_calistir` içindeki `try`."""
    agac = ast.parse((KOK / "apps" / "backend" / "backend_service.py").read_text(encoding="utf-8"))
    dis = next(f for f in ast.walk(agac) if isinstance(f, ast.FunctionDef) and f.name == "_start_ai_warmup_safe")
    ic = next(f for f in ast.walk(dis) if isinstance(f, ast.FunctionDef) and f.name == "_calistir")
    return next(d for d in ast.walk(ic) if isinstance(d, ast.Try))


def _a9_bicimi(ne: str) -> ast.Try:
    """A9 handler'ının günlük çağrısı plan'ın üç KAÇIŞ biçimine çevrilir (AST'de; kaynak dosyaya DOKUNULMAZ)."""
    import copy

    t = copy.deepcopy(_a9_try())
    h = t.handlers[0]
    cagri = next(c for c in ast.walk(_govde_agaci(h.body)) if isinstance(c, ast.Call) and _cagri_adi(c) == "warning")
    if ne == "exc_info_false":
        cagri.func.attr = "info"
        for k in cagri.keywords:
            if k.arg == "exc_info":
                k.value = ast.Constant(False)
    elif ne == "log_info":
        cagri.func.attr = "log"
        cagri.args.insert(0, ast.Attribute(value=ast.Name(id="logging", ctx=ast.Load()), attr="INFO", ctx=ast.Load()))
        cagri.keywords = [k for k in cagri.keywords if k.arg != "exc_info"]
    elif ne == "olu_raise":
        cagri.func.attr = "info"
        cagri.keywords = [k for k in cagri.keywords if k.arg != "exc_info"]
        h.body.append(ast.If(test=ast.Constant(False), body=[ast.Raise(exc=None, cause=None)], orelse=[]))
    return t


@pytest.mark.parametrize("ne", ["exc_info_false", "log_info", "olu_raise"])
def test_KRITIK_D237_A9_handleri_uc_KACIS_bicimine_cevrilince_KOR_sayilir(ne):
    """Plan (B-10.244): A9 handler'ı `exc_info=False` / `logger.log(logging.INFO, …)` / `if False: raise` biçimine çevrilince
    eski `kor_mu` üçünde de "kör değil" diyordu (kapı yeşil kalırdı) — yeni sınıflandırıcı üçünü de KÖR sayar."""
    assert kor_mu(_a9_try()) is False, "aparat: GERÇEK A9 handler'ı (warning + exc_info=True) zaten kör sayıldı"
    assert kor_mu(_a9_bicimi(ne)) is True, f"A9 handler'ının `{ne}` biçimi KÖR sayılmadı — kapı bu kaçışı görmez"


# ──────────────────────────────────────────────────────────────────────────
# 1) ASIL İDDİA
# ──────────────────────────────────────────────────────────────────────────


def test_KRITIK_alt_sistem_acan_yolda_KOR_handler_YOK():
    """Alt sistem açan hiçbir `try`, kök nedeni gizleyen düşük-seviye logla kapatılmasın."""
    dosyalar = _kapsanan_dosyalar()
    assert len(dosyalar) > 40, f"VAKUM: yalnız {len(dosyalar)} dosya tarandı — tarama bozuk"

    toplam_try = 0
    bulgular = []
    for p in dosyalar:
        rel = str(p.relative_to(KOK)).replace("\\", "/")
        try:
            agac = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as e:
            raise AssertionError(f"AYRIŞTIRILAMADI {rel}: {e} — sessizce DÜŞÜRÜLMEZ") from e
        for d in ast.walk(agac):
            if not isinstance(d, ast.Try):
                continue
            toplam_try += 1
            if not kor_mu(d):
                continue
            fn = _fonksiyon_adi(agac, d.lineno)
            muaf, _kanit = _muaf_mi(rel, fn)
            if muaf:
                continue
            bulgular.append(f"{rel}:{d.lineno}  ({fn})")

    assert toplam_try > 300, f"VAKUM: yalnız {toplam_try} try düğümü görüldü — tarayıcı bozuk"
    assert not bulgular, (
        "LOGLAYAN AMA KÖR handler:\n  "
        + "\n  ".join(bulgular)
        + "\n\nDüzeltme: seviyeyi `warning`e çıkar + `exc_info=True` ekle + mesaj KAYBEDİLEN "
        "YETENEĞİ söylesin. (A9'da bu sınıf kök nedeni saatlerce gizledi.)"
    )


def test_muafiyetler_GERCEKTEN_gerekli_ve_KANITLI():
    """Muafiyet kaba yol değil: gerekçesi VAR ve kanıtı hâlâ kaynakta.

    ⚠️ Muafiyet listesi çürüyen bir şeydir. Muaf tutulan yer artık kör DEĞİLSE muafiyet
    KALDIRILMALI — yoksa gelecekte gerçek bir körlüğü sessizce örter.
    """
    for (dosya_sonu, fn), (gerekce, kanit) in MUAFIYETLER.items():
        assert len(gerekce) > 40, f"{dosya_sonu}:{fn} muafiyeti gerekçesiz"
        eslesen = [p for p in _kapsanan_dosyalar() if str(p).replace("\\", "/").endswith(dosya_sonu)]
        assert eslesen, f"muaf dosya YOK: {dosya_sonu} — muafiyet bayat, kaldırın"
        metin = eslesen[0].read_text(encoding="utf-8", errors="replace")
        assert kanit in metin, (
            f"{dosya_sonu}: muafiyetin dayandığı kanıt {kanit!r} kaynakta YOK. Toplu sonuç "
            "artık tam zincirle bildirilmiyorsa muafiyet geçersizdir."
        )
        agac = ast.parse(metin)
        hedef = [
            d for d in ast.walk(agac) if isinstance(d, ast.Try) and _fonksiyon_adi(agac, d.lineno) == fn and kor_mu(d)
        ]
        assert hedef, (
            f"{dosya_sonu}:{fn} artık KÖR DEĞİL → muafiyet gereksiz, listeden KALDIRIN "
            "(gereksiz muafiyet gelecekte gerçek bir körlüğü örter)."
        )


# ──────────────────────────────────────────────────────────────────────────
# 2) DÜZELTİLENLER GERİ DÖNMESİN — ölçülen dört yer
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rel,fonksiyon,kayip_yetenek",
    [
        ("apps/backend/backend_service.py", "_calistir", "AI ısıtma"),
        ("apps/backend/servers/api_server.py", "_scratch_isit_baslat", "Yara-kapanma ısıtması"),
        ("apps/backend/servers/sync_worker.py", "_ensure_client", "BULUT SENKRONU KAPALI"),
        ("apps/backend/utils/zeroconf_singleton.py", "_real_lan_ipv4s", "InterfaceChoice.All"),
    ],
)
def test_DUZELTILEN_dort_yer_artik_KOR_DEGIL(rel: str, fonksiyon: str, kayip_yetenek: str):
    """A9 turunda düzeltilen dört yer geri dönmesin; mesaj KAYBEDİLEN YETENEĞİ söylesin."""
    p = KOK / rel
    metin = p.read_text(encoding="utf-8")
    agac = ast.parse(metin)
    # ⚠️ VAKUM KORUMASI: fonksiyon adı eşleşmezse liste boş çıkar ve test hiçbir şey
    # ölçmeden yeşil olur. Önce fonksiyonun VAR olduğunu ve içinde try bulunduğunu kanıtla.
    bu_fonksiyondaki_try = [
        d for d in ast.walk(agac) if isinstance(d, ast.Try) and _fonksiyon_adi(agac, d.lineno) == fonksiyon
    ]
    assert bu_fonksiyondaki_try, (
        f"VAKUM: {rel} içinde {fonksiyon!r} fonksiyonunda hiç try bulunamadı — "
        "fonksiyon yeniden adlandırılmış ya da çıpa bayat; bu test hiçbir şey ölçmüyor."
    )
    korler = [d for d in bu_fonksiyondaki_try if kor_mu(d)]
    assert not korler, f"{rel}:{fonksiyon} yeniden KÖR oldu (satır {[d.lineno for d in korler]})"
    assert kayip_yetenek in metin, (
        f"{rel}: hata mesajı artık {kayip_yetenek!r} demiyor — operatör NE KAYBETTİĞİNİ "
        "okuyamaz (bkz. 'Hata Mesajı EYLEM Söylesin')."
    )


# ──────────────────────────────────────────────────────────────────────────
# 3) ÇALIŞMA-ANI — `exc_info=True` YAZILMASI ile ZİNCİRİN BASILMASI ayrı şeyler
# ──────────────────────────────────────────────────────────────────────────


def test_DAVRANIS_zincir_GERCEKTEN_log_kaydina_giriyor(monkeypatch, caplog):
    """Gerçek bir arızayı tetikle ve log kaydında TRACEBACK olduğunu doğrula.

    ⚠️ Yapısal iddia yalnızca "`exc_info=True` kaynakta yazıyor" der. Formatter/handler
    yapılandırması ya da yanlış çağrı biçimi yüzünden zincir yine de kaybolabilir —
    bu yüzden çıpa gerçek `LogRecord`a pinli.
    """
    import logging
    import sys
    import types

    from utils import zeroconf_singleton as zs

    class _PatlayanIfaddr(types.ModuleType):
        def get_adapters(self):
            raise OSError("ifaddr SIMULE ARIZA (kapı testi)")

    monkeypatch.setitem(sys.modules, "ifaddr", _PatlayanIfaddr("ifaddr"))

    with caplog.at_level(logging.DEBUG):
        zs._real_lan_ipv4s()  # düşmeli ama SERVİSİ düşürmemeli

    ilgili = [r for r in caplog.records if "InterfaceChoice.All" in r.getMessage()]
    assert ilgili, (
        "arıza tetiklendi ama ilgili uyarı HİÇ basılmadı — handler sessizleşmiş olabilir. "
        f"görülen kayıtlar: {[r.getMessage()[:60] for r in caplog.records]}"
    )
    kayit = ilgili[0]
    assert kayit.levelno >= logging.WARNING, (
        f"seviye {kayit.levelname}: normal log seviyesinde görünmez → sessizce kaybolur"
    )
    assert kayit.exc_info is not None, "kayıtta exc_info YOK — tam zincir basılmıyor"
    metin = logging.Formatter().format(kayit)
    assert "Traceback" in metin and "SIMULE ARIZA" in metin, (
        "biçimlendirilmiş kayıtta traceback ya da kök hata mesajı yok:\n" + metin[:400]
    )
