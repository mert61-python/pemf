# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SIR KORUMASI (skip-worktree) TAZE KLONDA DA KURULUR (2026-09-16).

OLCULEN ACIK. `firmware/*/Secrets.h` ve `firmware/*/data/config.json` depoda SABLON
olarak takipli; bu makinede GERCEK WiFi + bulut MQTT kimlik bilgileriyle DOLU. Ayrimi
`skip-worktree` bayragi saglar ve o bayrak KLON-YERELDIR — depoya girmez.

Bayragi uygulayan tek yer `build_tools/secrets_backup.py` RESTORE akisiydi. Yani:

    sir yedegini restore eden makine   -> korunur
    TAZE KLON + Secrets.h'i ELLE dolduran makine -> KORUNMAZ

Ikinci senaryoda `git add -A` gercek sirlari PUBLIC depoya stage'ler. Tek guvence
gitleaks (pre-commit + CI) kalir — calisir, ama TEK kemerdir ve bu depo gecmisinde
canli sir bulunmus bir depodur.

⚠️ DENETIM DUZELTMESI: `DEPO-DENETIMI-2026-09-15.md` §1.3 "bayragi kuran bir script/hook
depoda YOK" diyordu. YANLIS — `secrets_backup.py:96` uyguluyor (ve `git exit 128` deligi
de kapatilmis). Gercek acik dardir: RESTORE KOSMAYAN kurulum.

DUZELTME: `bootstrap.ps1` (her yeni makinede zaten kosan kurulum betigi) korumayi
kurar. Bootstrap `pre-commit install`i da tam bu gerekceyle yapiyor — ayni yerde
ikinci kemer baglanir.

⚠️ DOSYA LISTESI KOPYALANMAZ. Bootstrap kendi listesini YAZMAZ; `secrets_backup`in
`_SW_DOSYALAR`ini kullanan bir alt komutu cagirir. Bu depo 2026-09-15'te "ayni kural iki
yerde -> sessizce ayristi" arizasini UC ayri noktada yasadi; ayni tuzagi sir korumasinda
tekrarlamak kabul edilemez.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
_BOOTSTRAP = KOK / "scripts" / "bootstrap.ps1"
_YEDEK = KOK / "build_tools" / "secrets_backup.py"

#: Bootstrap'in cagirdigi alt komut. Tek kaynak: secrets_backup._SW_DOSYALAR.
_ALT_KOMUT = "sir-korumasi"


def _kaynak(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _ps_yorumsuz(p: Path) -> str:
    """PowerShell kaynagi, YORUM satirlari ayiklanmis (dizeler DURUR).

    ⚠️ ZORUNLU: bootstrap.ps1 aciklama yorumlarinda 'Secrets.h' gibi kelimeleri zaten
    aniyor. Ham metinde arayan bir kapi, kod degismeden de kirmizi/yesil olabilirdi —
    bu deponun tekrar eden sinifi ("yorum kapiyi kandirdi").
    """
    out = []
    for satir in _kaynak(p).splitlines():
        s = re.sub(r"(?<!`)#.*$", "", satir)
        if s.strip():
            out.append(s)
    return "\n".join(out)


def _ps_cagri_kodu(p: Path) -> str:
    """Yorumlar VE cift-tirnakli dizeler ayiklanmis PowerShell kaynagi.

    ⚠️ BU AYRIM BIR MUTASYONLA ORTAYA CIKTI (ayni oturum). "Cagri duruyor mu?" testi
    once yalnizca yorumlari soyuyordu; `sir-korumasi` sozcugu, git dustugunde basilan
    ELLE-KOMUT uyarisinda da geciyor:

        Warn "skip-worktree uygulanamadi -> elle: $embPy ...secrets_backup.py sir-korumasi"

    Gercek `& $embPy ... sir-korumasi` satirini silen mutasyon, bu uyari metni yerinde
    kaldigi icin kapiyi YESIL birakti. Cagri arayan iddialar dize-soyulmus kaynakta
    calismali; gercek cagrida alt komut TIRNAKSIZ yazildigi icin hayatta kalir.

    ⚠️ Dosya-adi KOPYASI arayan iddia bunu KULLANAMAZ: kopyalanan liste dizelerin
    ICINDE olur (`@("firmware/.../Secrets.h")`). O iddia `_ps_yorumsuz` ile calisir.
    """
    return re.sub(r'"[^"\n]*"', '""', _ps_yorumsuz(p))


# ═══════════════════════════════════════════════════════════════════════════════════════
# ASIL SOZLESME
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_bootstrap_sir_korumasini_KURAR():
    """⚠️ BU TEST BUGUNKU KODDA KIRMIZIDIR — acigin ta kendisi.

    Taze klonda restore kosmadan Secrets.h elle doldurulursa skip-worktree YOKTUR ve
    `git add -A` gercek sirlari PUBLIC depoya stage'ler.
    """
    kod = _ps_cagri_kodu(_BOOTSTRAP)
    assert _ALT_KOMUT in kod, (
        f"bootstrap.ps1 sir korumasini KURMUYOR (`{_ALT_KOMUT}` alt komutu cagrilmiyor) -> "
        "taze klonda skip-worktree yok; `git add -A` gercek WiFi/MQTT kimlik bilgilerini "
        "PUBLIC depoya stage'ler. Tek guvence gitleaks kalir."
    )


def test_KRITIK_secrets_backup_alt_komutu_SUNAR():
    """Bootstrap'in cagirdigi alt komut gercekten var olmali — yoksa cagri sessizce duser."""
    kod = _kaynak(_YEDEK)
    assert f'"{_ALT_KOMUT}"' in kod or f"'{_ALT_KOMUT}'" in kod, (
        f"secrets_backup.py `{_ALT_KOMUT}` alt komutunu tanimlamiyor -> bootstrap'in cagrisi "
        "bilinmeyen komut hatasiyla duser ve koruma KURULMAZ"
    )


def test_KRITIK_dosya_listesi_TEK_yerde():
    """⚠️ KOPYALAMA YASAK — 2026-09-15 dersi.

    Bootstrap kendi dosya listesini yazarsa iki liste zamanla ayrisir: yeni bir sir dosyasi
    eklendiginde biri guncellenir, digeri UNUTULUR ve o dosya korumasiz kalir. Ayni sinif
    (ayni kural iki yerde) bu depoda UC ayri noktada olculdu.
    """
    kod = _ps_yorumsuz(_BOOTSTRAP)  # dizeler DURUR: kopyalanan liste tirnak icinde olur
    kacaklar = [y for y in ("Secrets.h", "config.json") if y in kod]
    assert not kacaklar, (
        f"bootstrap.ps1 sir dosyasi adlarini KENDI icinde sayiyor: {kacaklar}. Liste TEK "
        "yerde (secrets_backup._SW_DOSYALAR) kalmali; bootstrap yalnizca alt komutu cagirmali."
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# KARSIT-KANITLAR
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_KARSIT_KANIT_restore_yolu_korumayi_KAYBETMEDI():
    """Bootstrap'a eklemek, restore'daki korumayi kaldirmanin bahanesi DEGILDIR.

    Iki giris noktasi da korumali olmali: restore eden makine de, taze klon da.
    """
    agac = ast.parse(_kaynak(_YEDEK))
    restore = next(
        (n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef) and n.name == "cmd_restore"),
        None,
    )
    assert restore is not None, "cmd_restore bulunamadi -> kapi KOR kaldi"
    cagrilar = {
        getattr(c.func, "id", getattr(c.func, "attr", None)) for c in ast.walk(restore) if isinstance(c, ast.Call)
    }
    assert "_git_sir_korumasi" in cagrilar, (
        "restore artik `_git_sir_korumasi`yi cagirmiyor -> sir yedegini geri yukleyen makinede "
        "koruma kayboldu (bootstrap'a tasimak bunu MESRU kilmaz)"
    )


def test_KARSIT_KANIT_alt_komut_KABUK_degil():
    """⚠️ Alt komutu TANIMLAYIP hicbir sey yaptirmamak butun testleri yesil birakirdi.

    `sir-korumasi` kayitli olur, bootstrap onu cagirir, cikis kodu 0 doner — ve
    skip-worktree HIC uygulanmaz. Sessiz bir koruma kaybi olurdu.
    """
    agac = ast.parse(_kaynak(_YEDEK))
    fn = next(
        (n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef) and n.name == "cmd_sir_korumasi"),
        None,
    )
    assert fn is not None, "cmd_sir_korumasi bulunamadi -> alt komut govdesi yok"
    cagrilar = {getattr(c.func, "id", getattr(c.func, "attr", None)) for c in ast.walk(fn) if isinstance(c, ast.Call)}
    assert "_git_sir_korumasi" in cagrilar, (
        "`sir-korumasi` alt komutu `_git_sir_korumasi`yi CAGIRMIYOR -> komut var, korumasi yok; "
        "bootstrap 0 doner ve herkes korunduk sanir"
    )


def test_KARSIT_KANIT_alt_komut_argparse_e_BAGLI():
    """Fonksiyonu yazip alt komuta BAGLAMAMAK da testleri yesil birakirdi."""
    kod = _kaynak(_YEDEK)
    assert re.search(r'add_parser\(\s*\n?\s*["\']sir-korumasi["\']', kod), (
        "`sir-korumasi` argparse'a kayitli degil -> bootstrap'in cagrisi 'invalid choice' ile duser"
    )
    assert re.search(r"set_defaults\(fn=cmd_sir_korumasi\)", kod), (
        "alt komut `cmd_sir_korumasi`ye baglanmamis -> cagri baska bir seyi calistirir ya da duser"
    )


def test_KARSIT_KANIT_koruma_GERCEKTEN_skip_worktree_calistirir():
    """`_git_sir_korumasi` bos bir kabuga donerse her iki giris noktasi da anlamsizlasir.

    ⚠️ BU KAPININ ILK HALI DELIKTI (ayni oturumda mutasyonla yakalandi). Once fonksiyon
    govdesinde `"--skip-worktree" in govde` araniyordu. O dize govdede IKI kez geciyor:
    (1) gercek `subprocess.run` argumaninda, (2) git dustugunde basilan ELLE-KOMUT
    yardim metninde. Gercek cagriyi `--refresh` yapan mutasyon, yardim metni yerinde
    kaldigi icin kapiyi YESIL birakti — "dize kapiyi kandirdi" sinifi.

    Cozum: capa CAGRININ ARGUMAN LISTESINE pinli. Yardim metinleri artik sayilmaz.
    """
    agac = ast.parse(_kaynak(_YEDEK))
    fn = next(
        (n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef) and n.name == "_git_sir_korumasi"),
        None,
    )
    assert fn is not None, "_git_sir_korumasi bulunamadi -> kapi KOR kaldi"

    uygulayan = []
    for n in ast.walk(fn):
        if not (isinstance(n, ast.Call) and n.args):
            continue
        ilk = n.args[0]
        if not isinstance(ilk, (ast.List, ast.Tuple)):
            continue
        sabitler = [e.value for e in ilk.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if "update-index" in sabitler:
            uygulayan.append(sabitler)

    assert uygulayan, (
        "`git update-index` CAGRISI yok -> koruma adi var, kendisi yok (yalnizca yardim metninde geciyor olabilir)"
    )
    assert any("--skip-worktree" in s for s in uygulayan), (
        f"`update-index` cagrilari `--skip-worktree` bayragini TASIMIYOR: {uygulayan} -> "
        "dosyalar git'in gozunden dusurulmuyor; `git add -A` gercek sirlari stage'ler"
    )
    # Ve listeyi TEK kaynaktan almali (cagrida `*izlenenler` acilimi).
    kod_fn = ast.unparse(fn)
    assert "_SW_DOSYALAR" in kod_fn, "koruma artik tek-kaynak dosya listesini kullanmiyor"


@pytest.mark.parametrize("yol", ["firmware/esps3_pemf_coil/Secrets.h", "firmware/esp8266_pemf_coil/Secrets.h"])
def test_KARSIT_KANIT_korunan_dosyalar_HALA_takipli(yol: str):
    """Koruma yalnizca IZLENEN dosyalar icin anlamlidir.

    Dosya takipten cikarilirsa `skip-worktree` konusu kapanir ama o zaman da sablonun
    depodan silinmis olmasi gerekir; sessizce yarim bir durum olusmamali.
    """
    assert (KOK / yol).exists(), f"{yol} agacta yok -> koruma listesi bayatlamis olabilir"
    liste = _kaynak(_YEDEK)
    assert yol in liste, f"{yol} `_SW_DOSYALAR`da yok -> o dosya korumasiz"
