# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""VAULT KURTARMA TATBIKATI — aracin kendi kapisi (2026-09-17).

`scripts/vault_emanet.py --tatbikat` calisan Vault + gercek hasta DB'si ister; CI'da ikisi de
YOKTUR, bu yuzden bu dosya tatbikati KOSTURMAZ. Korudugu sey uc degismez:

  1. TATBIKAT CLI'YE BAGLI MI. Fonksiyon yazilip dispatch'e eklenmezse `--tatbikat` diye bir
     sey yokmus gibi davranir; kimse fark etmez cunku `--dogrula` zaten yesil doner.

  2. ⚠️ ANAHTAR ASLA YAZDIRILMAZ. Bu arac hasta veritabanini ACAN anahtari elinde tutar.
     Bir gun tanilama icin `print(anahtar)` eklenirse, sir terminal gecmisine / CI log'una /
     ekran goruntusune duser. Bes kol: CIKTI (print/write/logging; `anahtar` yalniz dogrudan
     `len(...)`ta), AKIS (sir tasiyan adlar `anahtar`/`d`/`t` yalniz izinli yerlere), IC GOZLEM
     (locals/vars/globals/cerceve, eval/exec/compile, global/nonlocal, capture_locals, izinli adlarin
     atama/parametre/oznitelik/import/def ile golgelenmesi YASAK), SABIT (emanet alani tek
     turetimde), KAYNAK (siri URETEN cagrilar yalniz TEK bilinen baglamda; D0Ö.18 ek-2). Tarayicinin
     kendisi `_OZ_DENETIM`deki butun bicimlerle oz-denetlenir (D0Ö.18 + ek + ek-2 + ek-3; ek-3: oznitelik
     bicimi her alicida sayilir, yalniz `_IC_GOZLEM_ZARARSIZ`daki gerekceli ciftler — `re.compile` — haric).

  3. ⚠️ KARSIT KANIT KARARA GIRER. Tatbikat "acildi" demekle yetinemez: YANLIS anahtarin
     REDDEDILDIGINI de olcer. O olcum sonuca baglanmazsa, binding anahtari sessizce yok sayan
     bir surumde tatbikat YESIL doner ve emanetin ise yaradigini SANIRIZ.

Kapilar mutasyonla KIRMIZI gorulmustur (2026-09-17; D0Ö.18 2026-09-29/30).
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


#: Sir TASIYAN adlar (tatbikat icinde). ⚠️ D0Ö.18 ek (bagimsiz inceleme tur 4): yalniz ADI izlemek
#: yetmiyordu — `d` (Vault yaniti) IKI hasta anahtarini birden tasir, `t` kok token'dir; `print(d)`
#: ya da `print(locals())` hic `anahtar` gecisi eklemeden sirlari basardi.
SIRLAR = ("anahtar", "d", "t")
#: `d`nin TEK izinli kullanimlari (ast.unparse bicimiyle): hata listesi ve anahtarin turetimi.
_D_HATA = "(d or {}).get('errors')"
_D_TURETIM = "((d.get('data') or {}).get('data') or {}).get('auto.sqlcipher_key') or ''"
#: logging/logger yontemleri — alici ne olursa olsun (logging.x, log.x, logger.x) cikti sayilir.
_LOG_YONTEMLERI = {"debug", "info", "warning", "warn", "error", "exception", "critical", "fatal", "log"}
#: `anahtar`in AKABILECEGI tek yerler: uzunlugu, veritabanini acan cagri ve bos-mu denetimi.
_IZINLI_CAGRILAR = {"len", "open_encrypted_conn"}
#: Yerel ad alanini TOPTAN doken ya da dizeden kod calistiran adlar — siri ADSIZ tasir. D0Ö.18 ek-2:
#: yalniz CAGRI degil her ADI (`f = locals; print(f())`); eval/exec/compile/__import__/setattr da.
_IC_GOZLEM = {
    "locals",
    "vars",
    "globals",
    "_getframe",
    "currentframe",
    "eval",
    "exec",
    "compile",
    "__import__",
    "setattr",
}
#: Oznitelik biciminde ZARARSIZ oldugu bilinen (alici, ad) ciftleri — D0Ö.18 ek-3 (tur 6: `re.compile` sahte
#: KIRMIZI). Varsayilan KATI kalir: her alicida `x.eval`/`x.compile` sayilir (ornegin pandas `df.eval('@yerel')`
#: yereli DIZEYLE okur); yalniz ad alanina dokunmadigi bilinen cift GEREKCEYLE eklenir, kural gevsetilmez.
_IC_GOZLEM_ZARARSIZ = {("re", "compile")}  # desen derler; kod calistirmaz, cerceveye dokunmaz
#: Istisnada YERELLERI basan modul adlari — D0Ö.18 ek-3 (tur 6): yalniz tatbikat ICINDEKI import dugumu
#: yakalaniyordu; olagan yer modul ustu `import cgitb` + tatbikatta `cgitb.enable()` idi (her Load ihlal).
_YEREL_BASANLAR = {"cgitb"}
#: Izinli akislarin dayandigi adlar — golgelenirse (`len = print`) izin listesi kor olur.
_GOLGELENEMEZ = {"len", "open_encrypted_conn", "_istek", "print"}
#: Korunan bir adi BAGLAYABILEN tek import (modul + ad birebir); baska kaynaktan baglamak golgelemedir.
_KANONIK_IMPORT = {"open_encrypted_conn": ("database.sqlcipher_util", "open_encrypted_conn")}
#: Siri URETEN cagrilar ve TEK izinli baglamlari (atama hedef adlari) — D0Ö.18 ek-2 (tur 5, ORTA).
_KAYNAK_BAGLAMLARI = {"_kok_token": ["t"], "_istek": ["kod", "d"]}
#: Tatbikatta HIC cagrilamayan sir kaynaklari (unseal anahtarlari + kok token, cozulmus hasta anahtarlari).
_YASAK_KAYNAKLAR = {"_kurtarma", "_sirlari_oku", "geri_al", "token_uret"}


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
    """Bir sirrin OKUNDUGU her gecis (atama hedefi haric) — ebeveyniyle birlikte."""
    e = _ebeveynler(fn)
    return [(d, e) for d in ast.walk(fn) if isinstance(d, ast.Name) and d.id in SIRLAR and isinstance(d.ctx, ast.Load)]


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


def _d_hata_zinciri_mi(d: ast.Name, e: dict, fn: ast.AST) -> bool:
    ata = e.get(d)
    while ata is not None and ata is not fn and not isinstance(ata, ast.stmt):
        if ast.unparse(ata) == _D_HATA:
            return True
        ata = e.get(ata)
    return False


def _d_turetim_mi(d: ast.Name, e: dict, fn: ast.AST) -> bool:
    ata = e.get(d)
    while ata is not None and ata is not fn and not isinstance(ata, ast.stmt):
        ata = e.get(ata)
    return (
        isinstance(ata, ast.Assign)
        and [getattr(h, "id", None) for h in ata.targets] == ["anahtar"]
        and ast.unparse(ata.value) == _D_TURETIM
    )


def _t_izinli_mi(d: ast.Name, e: dict) -> bool:
    """`t` YALNIZ `_istek(..., token=t)` anahtar sözcüğü olarak. D0Ö.18 ek-2 (tur 5): her konumsal argüman
    serbestti — sıra hatası (`_istek(t, yol)`) kök token'ı URL'ye, oradan izinli hata çıktısına taşıyabilirdi."""
    p = e.get(d)
    if not (isinstance(p, ast.keyword) and p.arg == "token"):
        return False
    cagri = e.get(p)
    return isinstance(cagri, ast.Call) and getattr(cagri.func, "id", None) == "_istek"


def cikti_ihlalleri(fn: ast.AST) -> list[str]:
    """Bir CIKTI cagrisinin icinde gecen sir: `anahtar` yalniz dogrudan `len(...)`ta, `d` yalniz hata
    listesinde (`(d or {}).get('errors')`); `t` HIC."""
    ihlal = []
    for d, e in _sir_gecisleri(fn):
        cikti = _cikti_atasi(d, e, fn)
        if cikti is None:
            continue
        if d.id == "anahtar" and _len_icinde_mi(d, e):
            continue
        if d.id == "d" and _d_hata_zinciri_mi(d, e, fn):
            continue
        ihlal.append(f":{d.lineno} {d.id} → {ast.unparse(cikti)[:90]}")
    return ihlal


def akis_ihlalleri(fn: ast.AST) -> list[str]:
    """Sir yalniz IZINLI yerlere akar. `anahtar`: `len(...)`, `open_encrypted_conn(...)`, `not`/kosul;
    `d`: hata listesi ya da anahtarin TEK turetimi; `t`: `_istek(..., token=t)`.

    Cikti cagrisina bakan kapi ARA DEGISKENI goremez (`m = f"{anahtar}"; print(m)`); bu kol her
    yeni kullanimi (kopya, dilim, istisna metni, dosyaya yazma) yakalar.
    """
    ihlal = []
    for d, e in _sir_gecisleri(fn):
        p = e.get(d)
        if d.id == "anahtar":
            cagri = e.get(p) if isinstance(p, ast.keyword) else p
            # D0Ö.18 ek-2: izinli çağrı YALNIZ çıplak ad (`len(...)`); öznitelik adlı `x.len(anahtar)` DEĞİL.
            if (
                isinstance(cagri, ast.Call)
                and getattr(cagri.func, "id", None) in _IZINLI_CAGRILAR
                and (d in cagri.args or p is not cagri)
            ):
                continue
            if isinstance(p, ast.UnaryOp) and isinstance(p.op, ast.Not):
                continue
            if isinstance(p, (ast.If, ast.While, ast.IfExp)) and p.test is d:
                continue
        elif d.id == "d":
            if _d_hata_zinciri_mi(d, e, fn) or _d_turetim_mi(d, e, fn):
                continue
        elif _t_izinli_mi(d, e):
            continue
        ihlal.append(f":{d.lineno} {d.id} → {ast.unparse(p)[:90]}")
    return ihlal


def ic_gozlem_ihlalleri(fn: ast.AST) -> list[str]:
    """Ad alanini toptan dokenler (locals/vars/globals/cerceve) ve dizeden kod calistiranlar (eval/exec/
    compile/__import__/setattr) — CAGRI olsun olmasin her ADI; sirri kapsam disina tasiyan `global`/
    `nonlocal`; `capture_locals`/cgitb (yerelleri basan izleme); izinli akislarin dayandigi adlari
    GOLGELEYEN atama, PARAMETRE, OZNITELIK atamasi, import ve def/class (D0Ö.18 ek-2: son uc yeni)."""
    ihlal = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in _IC_GOZLEM:
            ihlal.append(f":{n.lineno} {n.id} (ad alani / dinamik kod)")
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in _YEREL_BASANLAR:
            ihlal.append(f":{n.lineno} {n.id} (istisnada yerelleri basar)")
        elif (
            isinstance(n, ast.Call)
            and _cagri_adi(n) in ("import_module", "__import__")
            and n.args
            and isinstance(n.args[0], ast.Constant)
            and str(n.args[0].value).split(".")[0] in _YEREL_BASANLAR
        ):
            ihlal.append(f":{n.lineno} {ast.unparse(n)[:60]} (istisnada yerelleri basar)")
        elif (
            isinstance(n, ast.Attribute)
            and n.attr in _IC_GOZLEM
            and (getattr(n.value, "id", None), n.attr) not in _IC_GOZLEM_ZARARSIZ
        ):
            ihlal.append(f":{n.lineno} {ast.unparse(n)[:60]} (zararsiz ise _IC_GOZLEM_ZARARSIZ'a GEREKCEYLE)")
        elif isinstance(n, ast.Attribute) and n.attr in ("f_locals", "f_globals"):
            ihlal.append(f":{n.lineno} {ast.unparse(n)[:60]}")
        elif isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store) and n.attr in _GOLGELENEMEZ:
            ihlal.append(f":{n.lineno} {ast.unparse(n)[:60]} = … korunan adi golgeliyor")
        elif isinstance(n, ast.arg) and n.arg in _GOLGELENEMEZ:
            ihlal.append(f":{n.lineno} parametre {n.arg} korunan adi golgeliyor")
        elif isinstance(n, ast.keyword) and n.arg == "capture_locals":
            ihlal.append(f":{getattr(n, 'lineno', '?')} capture_locals (yerelleri basar)")
        elif isinstance(n, (ast.Global, ast.Nonlocal)) and set(n.names) & set(SIRLAR):
            ihlal.append(f":{n.lineno} {type(n).__name__.lower()} {n.names}")
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id in _GOLGELENEMEZ:
            ihlal.append(f":{n.lineno} {n.id} golgelendi")
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                bagli = a.asname or a.name.split(".")[0]
                kanonik = isinstance(n, ast.ImportFrom) and _KANONIK_IMPORT.get(bagli) == (n.module, a.name)
                if bagli in _GOLGELENEMEZ and not kanonik:
                    ihlal.append(f":{n.lineno} {ast.unparse(n)[:60]} korunan adi golgeliyor")
                kaynak_modul = n.module if isinstance(n, ast.ImportFrom) else a.name
                if (kaynak_modul or "").split(".")[0] == "cgitb":
                    ihlal.append(f":{n.lineno} cgitb (istisnada yerelleri basar)")
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n is not fn:
            if n.name in _GOLGELENEMEZ:
                ihlal.append(f":{n.lineno} def {n.name} golgeledi")
    return ihlal


def _hedef_adlari(hedef: ast.AST) -> list[str]:
    if isinstance(hedef, ast.Name):
        return [hedef.id]
    if isinstance(hedef, (ast.Tuple, ast.List)):
        return [getattr(x, "id", "?") for x in hedef.elts]
    return ["?"]


def kaynak_ihlalleri(fn: ast.AST) -> list[str]:
    """Siri URETEN cagrilar: `_kok_token()` yalniz `t = _kok_token()`, `_istek(...)` yalniz
    `kod, d = _istek(...)` — TAM BIR KEZ; `_kurtarma`/`_sirlari_oku`/`geri_al`/`token_uret` HIC.

    ⚠️ D0Ö.18 ek-2 (bagimsiz inceleme tur 5, ORTA): adlari izleyen kollar siri ureten CAGRININ kendisini
    gormuyordu — `print(_kok_token())`, `print(_sirlari_oku())` ya da `_istek` donusunu yeni bir ada
    baglamak dort kolu da atlatiyor, kok token'i ya da iki hasta anahtarini basiyordu.
    """
    e = _ebeveynler(fn)
    ihlal: list[str] = []
    sayim = dict.fromkeys(_KAYNAK_BAGLAMLARI, 0)
    for n in ast.walk(fn):
        if not isinstance(n, ast.Call):
            continue
        ad = _cagri_adi(n)
        if ad in _YASAK_KAYNAKLAR:
            ihlal.append(f":{n.lineno} {ad}() tatbikatta CAGRILAMAZ")
        elif ad in _KAYNAK_BAGLAMLARI:
            sayim[ad] += 1
            p = e.get(n)
            beklenen = _KAYNAK_BAGLAMLARI[ad]
            if not (
                isinstance(p, ast.Assign)
                and p.value is n
                and len(p.targets) == 1
                and _hedef_adlari(p.targets[0]) == beklenen
            ):
                ihlal.append(f":{n.lineno} {ad}() yalniz `{', '.join(beklenen)} = {ad}(...)` biciminde")
    ihlal += [f"{ad}() {k} kez (tam 1 bekleniyor)" for ad, k in sayim.items() if k != 1]
    return ihlal


def sabit_ihlalleri(fn: ast.AST) -> list[str]:
    """`auto.sqlcipher_key` alani tatbikatta YALNIZ bir kez (turetimde) gecer; Fernet anahtari hic."""
    sabitler = [n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    ihlal = []
    if sabitler.count("auto.sqlcipher_key") != 1:
        ihlal.append(f"'auto.sqlcipher_key' {sabitler.count('auto.sqlcipher_key')} kez (yalniz turetimde 1 kez)")
    if "auto.patient_fernet_key" in sabitler:
        ihlal.append("'auto.patient_fernet_key' tatbikatta KULLANILAMAZ")
    return ihlal


def tum_ihlaller(fn: ast.AST) -> dict[str, list[str]]:
    return {
        "cikti": cikti_ihlalleri(fn),
        "akis": akis_ihlalleri(fn),
        "icgozlem": ic_gozlem_ihlalleri(fn),
        "sabit": sabit_ihlalleri(fn),
        "kaynak": kaynak_ihlalleri(fn),
    }


def test_KRITIK_ANAHTAR_asla_YAZDIRILMAZ():
    """⚠️ Bu kapinin korudugu sey bir SIR.

    Sir tasiyan adlar (`anahtar`, Vault yaniti `d`, kok token `t`) bir CIKTI cagrisinda (print,
    sys.stdout/stderr(.buffer).write(lines), logging) yalniz izinli bicimde gecebilir: `anahtar`
    dogrudan `len(...)` icinde, `d` yalniz hata listesi olarak, `t` HIC.

    ⚠️ D0Ö.18 (B-10.20): eski surum "argumanin HERHANGI bir yerinde `len(anahtar)` var mi" diye
    bakiyordu → `f"... {len(anahtar)} ... {anahtar}"` YESILDI; yalniz `print`in konumsal
    argumanlarini tariyordu → `sys.stdout.write(anahtar)` ve `print(..., sep=anahtar)` YESILDI.
    Artik HER GECIS kendi ebeveyniyle denetlenir.
    """
    fn = _fonksiyon("tatbikat")
    ihlaller = cikti_ihlalleri(fn)
    assert not ihlaller, (
        f"tatbikat SIRRI YAZDIRIYOR: {ihlaller}. Bu arac hasta veritabanini acan anahtari "
        "tutar; degeri (kismi bile olsa) ekrana basmak onu terminal gecmisine ve log'a dusurur. "
        "Yalniz `len(anahtar)` ve `(d or {}).get('errors')` serbesttir."
    )


def test_KRITIK_ANAHTAR_yalniz_IZINLI_yerlere_akar():
    fn = _fonksiyon("tatbikat")
    ihlaller = akis_ihlalleri(fn)
    assert not ihlaller, (
        f"tatbikat'ta sir IZINSIZ bir yere akiyor: {ihlaller}. Izinli: `len(anahtar)`, "
        "`open_encrypted_conn(..., anahtar | key=anahtar, ...)` (ciplak adla), `not anahtar`, "
        "`if/while anahtar`, `x if anahtar else y`, `(d or {}).get('errors')`, anahtarin TEK turetimi, "
        "`_istek(..., token=t)` (yalniz anahtar sozcugu). Yeni bir kullanim gerekiyorsa once bu kapiyi "
        "gerekcesiyle guncelleyin."
    )


def test_KRITIK_ad_alani_DOKULMEZ_ve_izinli_adlar_GOLGELENMEZ():
    fn = _fonksiyon("tatbikat")
    ihlaller = ic_gozlem_ihlalleri(fn)
    assert not ihlaller, (
        f"tatbikat'ta ad alanini doken / dizeden kod calistiran / izinli adi golgeleyen yapi: {ihlaller} — "
        "mesru ve ZARARSIZ bir oznitelik cagrisiysa (alici, ad) ciftini _IC_GOZLEM_ZARARSIZ'a gerekceyle "
        "ekleyin; kurali gevsetmeyin (D0Ö.18 ek-3)"
    )


def test_KRITIK_anahtar_ALANI_yalniz_TEK_turetimde():
    fn = _fonksiyon("tatbikat")
    ihlaller = sabit_ihlalleri(fn)
    assert not ihlaller, f"tatbikat emanetten anahtari birden cok yoldan okuyor: {ihlaller}"


def test_KRITIK_sir_KAYNAKLARI_yalniz_TEK_baglamda():
    """D0Ö.18 ek-2 (tur 5, ORTA): siri URETEN cagrilar (`_kok_token`, `_istek`) yalniz bilinen TEK atamada;
    kurtarma/hasta-anahtari kaynaklari tatbikatta HIC. Sayim 0 donerse de KIRMIZI (tarayici kor olamaz)."""
    fn = _fonksiyon("tatbikat")
    ihlaller = kaynak_ihlalleri(fn)
    assert not ihlaller, f"tatbikat'ta sir KAYNAGI izinsiz baglamda: {ihlaller}"


def test_KAPI_TARAYICISI_gercek_gecisleri_GORUYOR():
    """Tarayici bos donerek yesil olamaz: gercek tatbikattaki izinli gecislerin HEPSI gorulmeli."""
    fn = _fonksiyon("tatbikat")
    gecisler = _sir_gecisleri(fn)
    anahtar = [(d, e) for d, e in gecisler if d.id == "anahtar"]
    ebeveyn_turleri = {type(e.get(d)).__name__ for d, e in anahtar}
    assert len(anahtar) >= 3 and {"Call", "UnaryOp"} <= ebeveyn_turleri, (
        f"`anahtar` gecisleri beklenenden az ({len(anahtar)}; {ebeveyn_turleri}) — ad degismis olabilir, kapi KOR"
    )
    assert any(_len_icinde_mi(d, e) and _cikti_atasi(d, e, fn) is not None for d, e in anahtar), (
        "tatbikat'taki `print(... len(anahtar) ...)` cikti cagrisi olarak GORULMUYOR — tarayici kor"
    )
    d_gecisleri = [(d, e) for d, e in gecisler if d.id == "d"]
    assert any(_d_hata_zinciri_mi(d, e, fn) for d, e in d_gecisleri), "`d` hata listesi kullanimi gorulmuyor"
    assert any(_d_turetim_mi(d, e, fn) for d, e in d_gecisleri), "`anahtar` turetimi gorulmuyor — kapi KOR"
    assert any(_t_izinli_mi(d, e) for d, e in gecisler if d.id == "t"), "`_istek(..., token=t)` gorulmuyor"


#: Oz-denetimin sentetik tatbikati: GERCEK tatbikatin sir akisinin iskeleti (izinli kullanimlar).
_TABAN = (
    "def tatbikat():\n"
    "    from database.sqlcipher_util import open_encrypted_conn\n"
    "    t = _kok_token()\n"
    "    kod, d = _istek('/v1/x', token=t)\n"
    "    if kod != 200:\n"
    "        print(f\"  HATA {kod}: ({(d or {}).get('errors')})\")\n"
    "    anahtar = ((d.get('data') or {}).get('data') or {}).get('auto.sqlcipher_key') or ''\n"
)

_OZ_DENETIM = [
    # (tabana eklenen govde, KIRMIZI olmasi beklenen kollar)
    ('print(f"u {len(anahtar)}")', set()),
    ("c = open_encrypted_conn(k, anahtar, m)\nif not anahtar:\n    pass", set()),
    ("if anahtar:\n    pass", set()),
    ("c = open_encrypted_conn(k, key=anahtar)", set()),
    # D0Ö.18 ek-2: ikinci `_istek` KAYNAK ihlalidir (t'nin token= izni tabandaki çağrıyla ölçülür).
    ("_istek('/v1/y', token=t)", {"kaynak"}),
    ('print(f"u {len(anahtar)} {anahtar}")', {"cikti", "akis"}),  # plan mutanti 1
    ("sys.stdout.write(anahtar)", {"cikti", "akis"}),  # plan mutanti 2
    ("sys.stdout.buffer.write(anahtar.encode())", {"cikti", "akis"}),
    ("sys.stderr.writelines([anahtar])", {"cikti", "akis"}),
    ('sys.stderr.write(f"{anahtar}")', {"cikti", "akis"}),
    ('print("x", sep=anahtar)', {"cikti", "akis"}),
    ("print(repr(anahtar))", {"cikti", "akis"}),
    ('print("%s" % anahtar)', {"cikti", "akis"}),
    ('print("{}".format(anahtar))', {"cikti", "akis"}),
    ('print(f"{anahtar!r}")', {"cikti", "akis"}),
    ("print((lambda: anahtar)())", {"cikti", "akis"}),
    ('logging.getLogger(__name__).info("k=%s", anahtar)', {"cikti", "akis"}),
    ('log.warning(f"{anahtar[:4]}")', {"cikti", "akis"}),
    ('print(f"{len(anahtar[:8])}")', {"cikti", "akis"}),
    ('m = f"{anahtar}"\nprint(m)', {"akis"}),  # ara degisken: yalniz akis kolu gorur
    ("raise RuntimeError(anahtar)", {"akis"}),
    ("sys.exit(anahtar)", {"akis"}),
    ("print(d)", {"cikti", "akis"}),  # Vault yaniti IKI anahtari birden tasir
    ('print(f"emanet: {d}")', {"cikti", "akis"}),
    ("print(d.get('data'))", {"cikti", "akis"}),
    ("v = (d.get('data') or {}).get('data') or {}\nprint(v)", {"akis"}),
    ("print(t)", {"cikti", "akis"}),  # kok token
    ("print(locals())", {"icgozlem"}),
    ("print(vars())", {"icgozlem"}),
    ("print(sys._getframe().f_locals)", {"icgozlem"}),
    ("len = print\nlen(anahtar)", {"icgozlem"}),  # izinli adin golgelenmesi
    ("from sahte_modul import open_encrypted_conn", {"icgozlem"}),  # korunan ad YANLIS kaynaktan
    ("from os import path as len", {"icgozlem"}),
    ("import print", {"icgozlem"}),
    ("x = 'auto.sqlcipher_key'", {"sabit"}),
    ("y = 'auto.patient_fernet_key'", {"sabit"}),
    # ── D0Ö.18 ek-2 (bağımsız inceleme tur 5) ──
    ("print(_kok_token())", {"kaynak"}),  # ORTA: kaynak çağrısı ada bağlanmadan basılır
    ("print(_sirlari_oku())", {"kaynak"}),
    ("y = _istek('/v1/x', token=t)[1]\nprint(y)", {"kaynak"}),
    ("x = _kurtarma()", {"kaynak"}),
    ("_istek(t)", {"akis", "kaynak"}),  # t konumsal: sıra hatası token'ı URL'ye taşır
    ("_istek(t, '/v1/x')", {"akis", "kaynak"}),
    ("types.SimpleNamespace(len=print).len(anahtar)", {"akis"}),  # öznitelik adlı "izinli" çağrı
    ("def len(x):\n    return x", {"icgozlem"}),
    ("class print:\n    pass", {"icgozlem"}),
    ("g = globals()", {"icgozlem"}),
    ("f = inspect.currentframe()", {"icgozlem"}),
    ("x = inspect.stack()[0].frame.f_locals", {"icgozlem"}),
    ("x = fr.f_globals", {"icgozlem"}),
    ("def _ic():\n    nonlocal anahtar", {"icgozlem"}),
    ("def _yaz(len=print):\n    len(anahtar)", {"icgozlem"}),  # parametre gölgelemesi
    ("(lambda len: len(anahtar))(print)", {"icgozlem"}),
    ("import builtins\nbuiltins.len = print", {"icgozlem"}),  # öznitelik yaması
    ("setattr(builtins, 'len', print)", {"icgozlem"}),
    ("print(eval('anahtar'))", {"icgozlem"}),
    ("exec('print(anahtar)')", {"icgozlem"}),
    ("f = locals\nprint(f())", {"icgozlem"}),  # çağrısız referans
    ("traceback.TracebackException.from_exception(e, capture_locals=True)", {"icgozlem"}),
    ("import cgitb\ncgitb.enable()", {"icgozlem"}),
    # ── D0Ö.18 ek-3 (tur 6 sonrası): alıcıya bakan öznitelik kuralı — dar muafiyet, katı varsayılan ──
    ("p = re.compile('x')", set()),  # sahte KIRMIZI idi: desen derler, ad alanına dokunmaz
    ("m = __import__('os')", {"icgozlem"}),
    ("x = compile('1', 's', 'eval')", {"icgozlem"}),
    ("x = builtins.eval('anahtar')", {"icgozlem"}),
    ("x = df.eval('@anahtar')", {"icgozlem"}),  # pandas: yereli DİZEYLE okur — varsayılan katı kalmalı
    ("cgitb.enable()", {"icgozlem"}),  # modül üstünde import edilmiş cgitb (olağan yer) — import düğümü yok
    ("importlib.import_module('cgitb').enable()", {"icgozlem"}),
    ("m = importlib.import_module('json')", set()),  # karşıt: sabit adlı başka modül temiz
]


def test_KAPI_TARAYICISI_oz_denetim():
    """Tarayicinin kendisi mutantlarla olculur (plan mutantlari + print disi cikti yollari + deger izi)."""
    yanlis = []
    for govde, beklenen in _OZ_DENETIM:
        girintili = "\n".join("    " + s for s in govde.splitlines())
        fn = ast.parse(_TABAN + girintili + "\n").body[0]
        gelen = {kol for kol, ihlal in tum_ihlaller(fn).items() if ihlal}
        if gelen != beklenen:
            yanlis.append((govde, sorted(beklenen), sorted(gelen)))
    global_fn = ast.parse("def tatbikat():\n    global anahtar\n    anahtar = oku()\n").body[0]
    if not ic_gozlem_ihlalleri(global_fn):
        yanlis.append(("global anahtar", ["icgozlem"], []))
    assert not yanlis, f"tarayici oz-denetimi TUTMADI (govde, beklenen, gelen): {yanlis}"


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
