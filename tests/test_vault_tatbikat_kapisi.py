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


def test_KRITIK_ANAHTAR_asla_YAZDIRILMAZ():
    """⚠️ Bu kapinin korudugu sey bir SIR.

    `anahtar` degiskeni `print(...)` icinde yalniz `len(anahtar)` olarak gecebilir. Dogrudan
    basmak (ya da dilimlemek: `anahtar[:8]`) sirri terminal gecmisine ve log'a dusurur.
    """
    fn = _fonksiyon("tatbikat")
    ihlaller = []
    for c in ast.walk(fn):
        if not isinstance(c, ast.Call):
            continue
        if getattr(c.func, "id", None) != "print":
            continue
        for arg in c.args:
            # f-string dahil TUM alt dugumleri tara
            for d in ast.walk(arg):
                if not (isinstance(d, ast.Name) and d.id == "anahtar"):
                    continue
                # `len(anahtar)` sarmali serbest; baska her kullanim ihlal.
                sarmalli = any(
                    isinstance(u, ast.Call)
                    and getattr(u.func, "id", None) == "len"
                    and any(isinstance(x, ast.Name) and x.id == "anahtar" for x in u.args)
                    for u in ast.walk(arg)
                )
                dilim = any(
                    isinstance(u, ast.Subscript) and isinstance(u.value, ast.Name) and u.value.id == "anahtar"
                    for u in ast.walk(arg)
                )
                if dilim or not sarmalli:
                    ihlaller.append(ast.unparse(arg)[:90])
    assert not ihlaller, (
        f"tatbikat ANAHTARI YAZDIRIYOR: {ihlaller}. Bu arac hasta veritabanini acan anahtari "
        "tutar; degeri (kismi bile olsa) ekrana basmak onu terminal gecmisine ve log'a dusurur. "
        "Yalniz `len(anahtar)` serbesttir."
    )


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
