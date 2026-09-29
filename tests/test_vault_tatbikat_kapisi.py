# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""VAULT KURTARMA TATBIKATI — aracin kendi kapisi (2026-09-17).

`scripts/vault_emanet.py --tatbikat` calisan Vault + gercek hasta DB'si ister; CI'da ikisi de
YOKTUR, bu yuzden bu dosya tatbikati KOSTURMAZ. Korudugu sey uc degismez:

  1. TATBIKAT CLI'YE BAGLI MI. Fonksiyon yazilip dispatch'e eklenmezse `--tatbikat` diye bir
     sey yokmus gibi davranir; kimse fark etmez cunku `--dogrula` zaten yesil doner.

  2. ⚠️ ANAHTAR ASLA YAZDIRILMAZ. Bu arac hasta veritabanini ACAN anahtari elinde tutar.
     Bir gun tanilama icin `print(anahtar)` eklenirse, sir terminal gecmisine / CI log'una /
     ekran goruntusune duser. Kapi, `anahtar`in `print` icinde YALNIZ `len(...)` sarmalinda
     gecmesine izin verir.

  3. ⚠️ KARSIT KANIT KARARA GIRER. Tatbikat "acildi" demekle yetinemez: YANLIS anahtarin
     REDDEDILDIGINI de olcer. O olcum sonuca baglanmazsa, binding anahtari sessizce yok sayan
     bir surumde tatbikat YESIL doner ve emanetin ise yaradigini SANIRIZ.

Uc kapi da mutasyonla KIRMIZI gorulmustur (2026-09-17).
"""

from __future__ import annotations

import ast
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "vault_emanet.py"


def _agac() -> ast.Module:
    return ast.parse(BETIK.read_text(encoding="utf-8"))


def _fonksiyon(ad: str) -> ast.FunctionDef:
    fn = next((n for n in ast.walk(_agac()) if isinstance(n, ast.FunctionDef) and n.name == ad), None)
    assert fn is not None, f"`{ad}` fonksiyonu YOK — arac degismis, kapi guncellenmeli"
    return fn


def test_KRITIK_tatbikat_CLIye_BAGLI():
    """Fonksiyonun var olmasi yetmez; `main` onu CAGIRMALI."""
    main = _fonksiyon("main")
    metin = BETIK.read_text(encoding="utf-8")
    assert '"--tatbikat"' in metin, "argparse'ta `--tatbikat` secenegi YOK"

    # ⚠️ "main icinde bir yerde `tatbikat()` cagrisi var mi" YETMEZ — MUTASYONLA olculdu
    # (2026-09-17): dispatch kosulunu `if False:` yapmak cagri DUGUMUNU yerinde birakir,
    # kapi yesil kalir ve `--tatbikat` sessizce OLU olur. Capa, cagriyi ULASILABILIR kilan
    # KOSULA pinli: `a.tatbikat` denetlenen dalin icinden cagrilmali.
    baglandi = False
    for n in ast.walk(main):
        if not isinstance(n, ast.If):
            continue
        kosul_alanlari = {d.attr for d in ast.walk(n.test) if isinstance(d, ast.Attribute)}
        if "tatbikat" not in kosul_alanlari:
            continue
        if any(
            isinstance(c, ast.Call) and getattr(c.func, "id", None) == "tatbikat"
            for c in ast.walk(ast.Module(body=n.body, type_ignores=[]))
        ):
            baglandi = True
            break
    assert baglandi, (
        "`--tatbikat` dispatch'e BAGLI DEGIL: `a.tatbikat` kosulunun icinden `tatbikat()` "
        "cagrilmiyor -> secenek sessizce olu. Kurtarma zinciri bir daha olculmez ve "
        "`--dogrula`nin yesili yeterli sanilir."
    )


#: Sirrin tutuldugu ad (tatbikat icinde).
SIR = "anahtar"
#: logging/logger yontemleri — alici ne olursa olsun (logging.x, log.x, logger.x) cikti sayilir.
_LOG_YONTEMLERI = {"debug", "info", "warning", "warn", "error", "exception", "critical", "fatal", "log"}
#: Sirrin AKABILECEGI tek yerler: uzunlugu, veritabanini acan cagri ve bos-mu denetimi.
_IZINLI_CAGRILAR = {"len", "open_encrypted_conn"}


def _ebeveynler(kok: ast.AST) -> dict:
    e = {}
    for n in ast.walk(kok):
        for c in ast.iter_child_nodes(n):
            e[c] = n
    return e


def _cagri_adi(c: ast.Call) -> str | None:
    return getattr(c.func, "id", None) or getattr(c.func, "attr", None)


def _cikti_cagrisi_mi(c: ast.Call) -> bool:
    """print / sys.stdout|stderr(.buffer).write(lines) / logging ve logger yontemleri."""
    if getattr(c.func, "id", None) == "print":
        return True
    if isinstance(c.func, ast.Attribute):
        if c.func.attr in _LOG_YONTEMLERI:
            return True
        if c.func.attr in ("write", "writelines"):
            zincir = {getattr(d, "attr", None) or getattr(d, "id", None) for d in ast.walk(c.func.value)}
            return bool(zincir & {"stdout", "stderr", "__stdout__", "__stderr__"})
    return False


def _sir_gecisleri(fn: ast.AST) -> list:
    """Sirrin OKUNDUGU her gecis (atama hedefi haric) — ebeveyniyle birlikte."""
    e = _ebeveynler(fn)
    return [(d, e) for d in ast.walk(fn) if isinstance(d, ast.Name) and d.id == SIR and isinstance(d.ctx, ast.Load)]


def _len_icinde_mi(d: ast.Name, e: dict) -> bool:
    """⚠️ HER GECIS KENDI EBEVEYNIYLE: `len(anahtar)` ile ayni f-string'deki `{anahtar}` serbest KALMAZ."""
    p = e.get(d)
    return isinstance(p, ast.Call) and getattr(p.func, "id", None) == "len" and d in p.args


def _cikti_atasi(d: ast.Name, e: dict, fn: ast.AST) -> ast.Call | None:
    """Gecisi saran en yakin CIKTI cagrisi (argumanlar VE anahtar sozcukler dahil), yoksa None."""
    ata = e.get(d)
    while ata is not None and ata is not fn:
        if isinstance(ata, ast.Call) and _cikti_cagrisi_mi(ata):
            return ata
        ata = e.get(ata)
    return None


def cikti_ihlalleri(fn: ast.AST) -> list[str]:
    """Bir cikti cagrisinin icinde `len(...)` sarmali DISINDA gecen sir."""
    ihlal = []
    for d, e in _sir_gecisleri(fn):
        cikti = _cikti_atasi(d, e, fn)
        if cikti is not None and not _len_icinde_mi(d, e):
            ihlal.append(f":{d.lineno} {ast.unparse(cikti)[:90]}")
    return ihlal


def akis_ihlalleri(fn: ast.AST) -> list[str]:
    """Sir yalniz `len(...)`, `open_encrypted_conn(...)` ve `not`/kosul icinde gecebilir.

    Cikti cagrisina bakan kapi ARA DEGISKENI goremez (`m = f"{anahtar}"; print(m)`); bu kol her
    yeni kullanimi (kopya, dilim, istisna metni, dosyaya yazma) yakalar.
    """
    ihlal = []
    for d, e in _sir_gecisleri(fn):
        p = e.get(d)
        cagri = e.get(p) if isinstance(p, ast.keyword) else p
        if (
            isinstance(cagri, ast.Call)
            and _cagri_adi(cagri) in _IZINLI_CAGRILAR
            and (d in cagri.args or p is not cagri)
        ):
            continue
        if isinstance(p, ast.UnaryOp) and isinstance(p.op, ast.Not):
            continue
        if isinstance(p, (ast.If, ast.While, ast.IfExp)) and p.test is d:
            continue
        ihlal.append(f":{d.lineno} {ast.unparse(p)[:90]}")
    return ihlal


def test_KRITIK_ANAHTAR_asla_YAZDIRILMAZ():
    """⚠️ Bu kapinin korudugu sey bir SIR.

    `anahtar` degiskeni bir CIKTI cagrisinda (print, sys.stdout/stderr.write, logging) yalniz
    `len(anahtar)` olarak gecebilir. Dogrudan basmak (ya da dilimlemek: `anahtar[:8]`) sirri
    terminal gecmisine ve log'a dusurur.

    ⚠️ D0Ö.18 (B-10.20): eski surum "argumanin HERHANGI bir yerinde `len(anahtar)` var mi" diye
    bakiyordu → `f"... {len(anahtar)} ... {anahtar}"` YESILDI; yalniz `print`in konumsal
    argumanlarini tariyordu → `sys.stdout.write(anahtar)` ve `print(..., sep=anahtar)` YESILDI.
    Artik HER GECIS kendi ebeveyniyle denetlenir.
    """
    fn = _fonksiyon("tatbikat")
    ihlaller = cikti_ihlalleri(fn)
    assert not ihlaller, (
        f"tatbikat ANAHTARI YAZDIRIYOR: {ihlaller}. Bu arac hasta veritabanini acan anahtari "
        "tutar; degeri (kismi bile olsa) ekrana basmak onu terminal gecmisine ve log'a dusurur. "
        "Yalniz `len(anahtar)` serbesttir."
    )


def test_KRITIK_ANAHTAR_yalniz_IZINLI_yerlere_akar():
    fn = _fonksiyon("tatbikat")
    ihlaller = akis_ihlalleri(fn)
    assert not ihlaller, (
        f"tatbikat'ta sir IZINSIZ bir yere akiyor: {ihlaller}. Izinli: len(anahtar), "
        "open_encrypted_conn(..., anahtar, ...), `if not anahtar`. Ara degisken/kopya/dilim/istisna "
        "metni sirri ciktiya tasiyabilir; yeni bir kullanim gerekiyorsa once bu kapiyi gerekcesiyle guncelleyin."
    )


def test_KAPI_TARAYICISI_gercek_gecisleri_GORUYOR():
    """Tarayici bos donerek yesil olamaz: gercek tatbikattaki uc izinli gecis gorulmeli."""
    fn = _fonksiyon("tatbikat")
    gecisler = _sir_gecisleri(fn)
    ebeveyn_turleri = {type(e.get(d)).__name__ for d, e in gecisler}
    assert len(gecisler) >= 3 and {"Call", "UnaryOp"} <= ebeveyn_turleri, (
        f"`{SIR}` gecisleri beklenenden az ({len(gecisler)}; {ebeveyn_turleri}) — ad degismis olabilir, kapi KOR"
    )
    assert any(_len_icinde_mi(d, e) and _cikti_atasi(d, e, fn) is not None for d, e in gecisler), (
        "tatbikat'taki `print(... len(anahtar) ...)` cikti cagrisi olarak GORULMUYOR — tarayici kor"
    )


_OZ_DENETIM = [
    # (kaynak govdesi, cikti kolu ihlal, akis kolu ihlal)
    ('print(f"u {len(anahtar)}")', False, False),
    ("c = open_encrypted_conn(k, anahtar, m)\nif not anahtar:\n    pass", False, False),
    ('print(f"u {len(anahtar)} {anahtar}")', True, True),  # plan mutanti 1
    ("sys.stdout.write(anahtar)", True, True),  # plan mutanti 2
    ('sys.stderr.write(f"{anahtar}")', True, True),
    ('print("x", sep=anahtar)', True, True),
    ('logging.getLogger(__name__).info("k=%s", anahtar)', True, True),
    ('log.warning(f"{anahtar[:4]}")', True, True),
    ('print(f"{len(anahtar[:8])}")', True, True),
    ('m = f"{anahtar}"\nprint(m)', False, True),  # ara degisken: yalniz akis kolu gorur
    ("raise RuntimeError(anahtar)", False, True),
]


def test_KAPI_TARAYICISI_oz_denetim():
    """Tarayicinin kendisi mutantlarla olculur (plan mutantlari + print disi cikti yollari)."""
    yanlis = []
    for govde, cikti_beklenen, akis_beklenen in _OZ_DENETIM:
        girintili = "\n".join("    " + s for s in govde.splitlines())
        fn = ast.parse(f"def tatbikat():\n    anahtar = oku()\n{girintili}\n").body[0]
        if bool(cikti_ihlalleri(fn)) != cikti_beklenen or bool(akis_ihlalleri(fn)) != akis_beklenen:
            yanlis.append((govde, cikti_ihlalleri(fn), akis_ihlalleri(fn)))
    assert not yanlis, f"tarayici oz-denetimi TUTMADI: {yanlis}"


def test_KRITIK_KARSIT_KANIT_sonuca_BAGLI():
    """⚠️ "Acildi" tek basina hicbir sey kanitlamaz.

    Tatbikat YANLIS anahtarin reddedildigini de olcer (`red`). O olcum nihai karara
    (`tamam`) girmezse, sifrelemeyi sessizce yok sayan bir binding surumunde tatbikat
    YESIL doner.
    """
    fn = _fonksiyon("tatbikat")
    atama = None
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "tamam" for t in n.targets):
            atama = n
            break
    assert atama is not None, "tatbikatta `tamam` karari YOK — sonuc nasil hesaplaniyor?"
    kaynak = ast.unparse(atama.value)
    assert "red" in {d.id for d in ast.walk(atama.value) if isinstance(d, ast.Name)}, (
        f"karsit kanit (`red`) nihai karara girmiyor: `{kaynak}`. Yanlis anahtar kabul edilse "
        "bile tatbikat BASARILI derdi."
    )


def test_KARSIT_KANIT_gercek_DBye_DOKUNULMUYOR():
    """Tatbikat gercek dosyayi acmamali — KOPYA uzerinde calismali."""
    fn = _fonksiyon("tatbikat")
    # ⚠️ "en az bir copy2 var mi" YETMEZ — MUTASYONLA olculdu (2026-09-17): tatbikatta IKI
    # copy2 var (ana dongu + yanlis-anahtar testi); birini kaldirmak otekini kapiya YETERLI
    # gosteriyordu. Bu, ayni oturumda ikinci "capa KARDES ornege takildi" vakasi.
    # Degismez SAYIYLA yazildi: her acma isleminden ONCE bir kopya alinmali.
    kopyalar = [c for c in ast.walk(fn) if isinstance(c, ast.Call) and getattr(c.func, "attr", None) == "copy2"]
    acmalar = [
        c for c in ast.walk(fn) if isinstance(c, ast.Call) and getattr(c.func, "id", None) == "open_encrypted_conn"
    ]
    assert acmalar, "tatbikat artik DB acmiyor — olcum anlamsiz"
    assert len(kopyalar) >= len(acmalar), (
        f"kopya sayisi ({len(kopyalar)}) acma sayisindan ({len(acmalar)}) AZ -> en az bir acma "
        "GERCEK hasta veritabani uzerinde yapiliyor. Acma denemesi (ozellikle yanlis anahtarla) "
        "uretim dosyasina dokunmamali."
    )
    temizlik = [c for c in ast.walk(fn) if isinstance(c, ast.Call) and getattr(c.func, "attr", None) == "rmtree"]
    assert temizlik, "tatbikat gecici kopyalari SILMIYOR -> duz-metin cozulebilir kopya diskte kalir"
