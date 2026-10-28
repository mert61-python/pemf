# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D5 M-4 (TUR 2 kapsam dışı gözlemi → ürün kararı [ÖNERİLEN UYGULANDI]) — dağıtım profili (`deploy\\<Mode>.env`) Windows PowerShell 5.1'de
de UTF-8 okunur: `setup_services.ps1` ve `install_backend_service.ps1` `Read-PemfProfilEnv` aynı profilden PS 7 ile AYNI haritayı ve AYNI
Y44 kararını üretir.

ÖLÇÜLEN (TUR 2 durumu, D5M3 kapısı Windows PowerShell 5.1 ile): `Read-PemfProfilEnv` profili `Get-Content $Dosya` ile (kodlamasız) okuyordu.
PS 7 kodlamasız okumada UTF-8 varsayar; Windows PowerShell 5.1 (kurulum betikleri "Yönetici PowerShell"de çoğunlukla 5.1 ile koşar) ANSI
(Türkçe Windows'ta cp1254) varsayar → BOM'suz UTF-8 profilde ASCII dışı her değer BOZULUR: `PEMF_API_PORT=٨٠١٠` (backend `int()` → 8010)
5.1'de kurulumu Y44 ile DURDURUYORDU, Türkçe karakterli değerler (yol, ad) servise bozuk gidiyordu; HATA iletisi bozuk değeri gösteriyordu.
PROFİLİ YAZAN YOLLAR (kodu okunarak, 2026-10-27): hiçbir kod yolu profil YAZMAZ — `deploy\\*.env` depodan AYNEN paketlenir (UTF-8, BOM'suz,
CRLF; PyInstaller `datas` → `_internal\\deploy`, Inno `{app}`); launcher (Rust) profili yalnız bir TESTTE okur; NSIS kancası profile dokunmaz;
kurulum betikleri yalnız OKUR. Tümü UTF-8 → `Get-Content -Encoding UTF8` iki yorumlayıcıda AYNI sonucu verir (BOM'lu UTF-8 de okunur).
SÖZLEŞME: iki betikte `Read-PemfProfilEnv` BİREBİR ve profili UTF-8 okur; aynı (BOM'lu / BOM'suz UTF-8) profil PS 7 ve 5.1'de AYNI haritaya
ayrışır (Python ayrıştırmasıyla eşit); Y44 kararı iki yorumlayıcıda AYNI ve backend `int()` anlamında (Arap-Hint rakamlı geçerli port SÜRER,
bozuk değer DURUR ve HATA değeri AYNEN söyler).
TUR 3b (çürütücü 3 m4f): profil değerinde '=' (base64 jetonu `…==`, DSN sorgusu `?a=b&c=d`) iki betikte, iki yorumlayıcıda AYNEN okunur
(ilk '='den bölünür) — eşlik kolu iki betik aynı bozulursa yakalamaz, harita kolu Python ayrıştırmasıyla karşılaştırır.
⛔ Betik GERÇEKTEN koşmaz: yalnız `Read-PemfProfilEnv` (izinli komut yalnız `Get-Content`) ve D5 M-3 aparatıyla Y44 ifadesi parser ile çekilir,
izin listesine karşı denetlenir; gölgeli sürücüde (modül otomatik yükleme KAPALI, Get-Command İŞLEV kanıtlı) gerçek `powershell.exe` (5.1)
ve `pwsh` (7) ile koşar. 5.1 alt süreci PS 7'nin `PSModulePath`ini miras ALMAZ (değişken ortamdan çıkarılır — hafıza: 5.1 aksi hâlde PS 7
modülünü yüklemeye çalışıp yalancı kırmızı verir). Profil dosyası test geçici dizinindedir.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
SETUP = KOK / "scripts" / "setup_services.ps1"
BETIK = KOK / "scripts" / "install_backend_service.ps1"
MOSQ = KOK / "scripts" / "install_mosquitto_service.ps1"  # Y205 · S-D5.16: üçüncü okuyucu
PWSH = shutil.which("pwsh")
PS51 = shutil.which("powershell")

if sys.platform != "win32":
    capraz.atla("Windows PowerShell 5.1 / pwsh aparatı Windows betik anlamını ölçer")
if PWSH is None:
    capraz.atla("pwsh (PowerShell 7) bulunamadı")
if PS51 is None:
    capraz.atla("Windows PowerShell 5.1 (powershell.exe) bulunamadı")

import test_install_backend_service_BOZUK_API_PORT_DURDURUR_Y44_D5M3 as D5M3  # noqa: E402
from test_install_backend_service_FW_kurali_ICERIKLE_D5H1 import betik_fonksiyonu  # noqa: E402
from test_setup_services_firewall_kaniti import _ps_lit  # noqa: E402

YORUMLAYICI = {"PS7": PWSH, "PS51": PS51}
BETIKLER = {"setup": SETUP, "install": BETIK}
# Profil: Türkçe yorum + Türkçe karakterli değerler + Arap-Hint rakamlı (backend int() → 8010) port. Satır sonu CRLF (depodaki profiller gibi).
PROFIL_SATIRLARI = [
    "# Türkçe yorum — şğüöçıİ ŞĞÜÖÇ",
    "PEMF_KLINIK_ADI=Şişli Veteriner Kliniği — İğdır Şubesi",
    "PEMF_DATA_DIR=C:\\ProgramData\\PEMF Çalışma Kökü",
    "PEMF_API_PORT=\u0668\u0660\u0661\u0660",
    "PEMF_ALLOWED_NAMES=Ayşe,Gülşen,Ömer",
    "PEMF_HEADLESS=1",
    # D5 M-4 TUR 3b (çürütücü 3 m4f — sınır): DEĞERİNDE '=' taşıyan satırlar (base64 dolgusu, DSN sorgusu; sahte değerler) — ayrıştırma
    # İLK '='den bölmeli (`Split("=", 2)`); sınırsız bölme değeri keser ve boşlukla birleştirir, servise BOZUK değer gider.
    "PEMF_API_TOKEN=YWJjZA==",
    "PEMF_DB_DSN=postgres://u@h/db?sslmode=require&x=1",
]


def _ps_kos(yorumlayici: str, d: Path, ad: str, govde: str) -> subprocess.CompletedProcess:
    """Geçici .ps1'i UTF-8-BOM ile yaz, `yorumlayici` (PS7 | PS51) ile koştur. 5.1 alt sürecine PSModulePath AKTARILMAZ."""
    p = d / ad
    p.write_text(govde, encoding="utf-8-sig", newline="\n")
    env = dict(os.environ)
    if yorumlayici == "PS51":
        env = {k: v for k, v in os.environ.items() if k.upper() != "PSMODULEPATH"}
    return subprocess.run(
        [YORUMLAYICI[yorumlayici], "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(p)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env=env,
    )


def _profil_yaz(yol: Path, satirlar: list[str], bom: bool) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_bytes(("\ufeff" if bom else "").encode("utf-8") + "\r\n".join([*satirlar, ""]).encode("utf-8"))


def _python_ayristir(satirlar: list[str]) -> dict[str, str]:
    """`Read-PemfProfilEnv` anlamı (kırp · boş / # satır atla · `=` yoksa atla · ilk `=`den böl · aynı anahtarda sonuncu kazanır)."""
    d: dict[str, str] = {}
    for ln in satirlar:
        t = ln.strip()
        if t and not t.startswith("#") and "=" in t:
            k, v = t.split("=", 1)
            d[k.strip()] = v.strip()
    return d


_HARITA = r"""
Import-Module Microsoft.PowerShell.Management, Microsoft.PowerShell.Utility
$PSModuleAutoLoadingPreference = 'None'
$ErrorActionPreference = 'Stop'
@@ISLEV@@
$m = Read-PemfProfilEnv @@PROFIL@@
$satir = @("SURUM=" + $PSVersionTable.PSVersion.Major) + @(foreach ($k in $m.Keys) { "$k=$($m[$k])" })
[System.IO.File]::WriteAllText(@@CIKTI@@, ($satir -join "`n"), (New-Object System.Text.UTF8Encoding($false)))
"""


def _harita(tmp_path: Path, betik: str, yorumlayici: str, bom: bool) -> tuple[int, dict[str, str]]:
    d = tmp_path / f"{betik}_{yorumlayici}_{'bom' if bom else 'bomsuz'}"
    d.mkdir()
    profil = d / "deploy" / "device.env"
    _profil_yaz(profil, PROFIL_SATIRLARI, bom)
    islev = betik_fonksiyonu(
        d, "Read-PemfProfilEnv", BETIKLER[betik], ("Get-Content",), ("Trim", "StartsWith", "Contains", "Split")
    )
    cikti = d / "harita.txt"
    govde = (
        _HARITA.replace("@@ISLEV@@", islev).replace("@@PROFIL@@", _ps_lit(profil)).replace("@@CIKTI@@", _ps_lit(cikti))
    )
    r = _ps_kos(yorumlayici, d, "harita.ps1", govde)
    assert r.returncode == 0 and cikti.exists(), (
        f"[{betik}/{yorumlayici}] sürücü düştü (rc={r.returncode}):\n{r.stdout}\n{r.stderr}"
    )
    satirlar = cikti.read_text(encoding="utf-8").split("\n")
    surum = int(satirlar[0].split("=", 1)[1])
    return surum, dict(s.split("=", 1) for s in satirlar[1:] if s)


@pytest.mark.parametrize("bom", [False, True], ids=["utf8_bomsuz", "utf8_bomlu"])
@pytest.mark.parametrize("yorumlayici", ["PS7", "PS51"])
@pytest.mark.parametrize("betik", ["setup", "install"])
def test_KRITIK_profil_ASCII_DISI_degerler_PS51_ve_PS7_AYNI_ayristirilir(tmp_path, betik, yorumlayici, bom):
    surum, harita = _harita(tmp_path, betik, yorumlayici, bom)
    assert surum == (7 if yorumlayici == "PS7" else 5), (
        f"aparat: {yorumlayici} yerine PowerShell {surum} koştu (kör ölçüm)"
    )
    beklenen = _python_ayristir(PROFIL_SATIRLARI)
    bozuk = {k: (harita.get(k), v) for k, v in beklenen.items() if harita.get(k) != v}
    assert not bozuk and set(harita) == set(beklenen), (
        f"[{BETIKLER[betik].name} / {yorumlayici} / {'BOM' if bom else 'BOM YOK'}] UTF-8 profil BOZUK / EKSİK okundu (Read-PemfProfilEnv "
        f"profili UTF-8 ve TAMAMEN okumalı — kodlamasız Get-Content 5.1'de ANSI varsayar): {{anahtar: (okunan, profil)}} = {bozuk}; "
        f"fazla / eksik anahtar: {set(harita) ^ set(beklenen)}"
    )


def _y44(tmp_path: Path, kip: str, satir: str, yorumlayici: str) -> tuple[int, list[str], Path]:
    """D5 M-3 aparatı (izin listeli Y44 + Read-PemfProfilEnv + Test-PemfApiPortDegeri, kayıtçı gölgeler) `yorumlayici` ile; profil BOM'suz
    UTF-8 + Türkçe değerler. → (çıkış kodu, olaylar, profil)."""
    d = tmp_path / f"y44_{kip}_{yorumlayici}"
    d.mkdir()
    profil = d / "deploy" / "device.env"
    _profil_yaz(profil, [s for s in PROFIL_SATIRLARI if not s.startswith("PEMF_API_PORT=")] + [satir], bom=False)
    olay = d / "olay.txt"
    olay.write_text("", encoding="utf-8")
    betik = BETIK if kip == "install" else SETUP
    on = "$Mode = 'device'\n" + (
        f"$ProfilDosyasi = {_ps_lit(profil)}\n" if kip == "install" else f"$OnEnvFile = {_ps_lit(profil)}\n"
    )
    eap = "'Stop'" if kip == "install" else "'Continue'"
    govde = (
        D5M3._SURUCU.replace("@@OLAY@@", _ps_lit(olay))
        .replace("@@EAP@@", eap)
        .replace("@@KOD@@", on + D5M3._cek(d, betik))
    )
    r = _ps_kos(yorumlayici, d, "surucu.ps1", govde)
    olaylar = [s for s in olay.read_text(encoding="utf-8-sig").splitlines() if s.strip()]
    assert r.returncode in (0, 1), (
        f"[{kip}/{yorumlayici}] sürücü düştü (rc={r.returncode}; 99 gölge yok):\n{olaylar}\n{r.stdout}\n{r.stderr}"
    )
    assert ("DEVAM" in olaylar) == (r.returncode == 0), f"aparat: çıkış kodu / DEVAM tutarsız:\n{olaylar}"
    return r.returncode, olaylar, profil


@pytest.mark.parametrize(
    ("deger", "gecerli"),
    [("\u0668\u0660\u0661\u0660", True), ("\u0668\u0660O\u0660", False)],
    ids=["arap_hint_8010_gecerli", "arap_hint_harfli_bozuk"],
)
@pytest.mark.parametrize("kip", ["install", "setup"])
def test_KRITIK_Y44_ASCII_DISI_port_PS51_ve_PS7_AYNI_karar_backend_int_anlaminda(tmp_path, kip, deger, gecerli):
    assert D5M3._gecerli(deger) is gecerli, "aparat: değer beklentisi backend int() anlamıyla tutarsız"
    sonuc = {}
    for yorumlayici in ("PS7", "PS51"):
        rc, olaylar, profil = _y44(tmp_path, kip, f"PEMF_API_PORT={deger}", yorumlayici)
        hata = [s.replace(str(profil), "<PROFIL>") for s in olaylar if s.startswith("LOG HATA")]
        sonuc[yorumlayici] = (rc, hata)
        if gecerli:
            assert rc == 0 and not hata, (
                f"[{kip}/{yorumlayici}] PEMF_API_PORT={deger!r} backend için GEÇERLİ (int() → {int(deger)}) ama kurulum durdu — profil "
                f"UTF-8 okunmadı (5.1 ANSI):\n{olaylar}"
            )
        else:
            assert rc == 1 and [s for s in hata if f"PEMF_API_PORT geçersiz: '{deger}'" in s], (
                f"[{kip}/{yorumlayici}] PEMF_API_PORT={deger!r} bozuk: kurulum durmadı ya da HATA değeri AYNEN söylemiyor (bozuk okundu):\n"
                f"{olaylar}"
            )
    assert sonuc["PS7"] == sonuc["PS51"], (
        f"[{kip}] PS 7 ile Windows PowerShell 5.1 Y44 kararında / metninde AYRIŞTI: {sonuc}"
    )


def test_KRITIK_ESLIK_Read_PemfProfilEnv_iki_betikte_BIREBIR(tmp_path):
    izin = ("Get-Content",)
    uye = ("Trim", "StartsWith", "Contains", "Split")
    (tmp_path / "s").mkdir()
    (tmp_path / "i").mkdir()
    kurulum = betik_fonksiyonu(tmp_path / "s", "Read-PemfProfilEnv", SETUP, izin, uye)
    servis = betik_fonksiyonu(tmp_path / "i", "Read-PemfProfilEnv", BETIK, izin, uye)
    assert kurulum == servis, (
        "Read-PemfProfilEnv iki kurulum yolunda AYRIŞTI — birini düzelttiyseniz (ör. kodlama) ötekini de düzeltin:\n"
        f"setup:\n{kurulum}\ninstall:\n{servis}"
    )


def test_KRITIK_ESLIK_Read_PemfProfilEnv_mosquitto_servis_betiginde_de_BIREBIR_Y205(tmp_path):
    """Y205 · S-D5.16: `install_mosquitto_service.ps1` ESP kipini aynı profilden okur — ayrıştırıcısı backend servisininkiyle BİREBİR."""
    izin = ("Get-Content",)
    uye = ("Trim", "StartsWith", "Contains", "Split")
    (tmp_path / "i").mkdir()
    (tmp_path / "m").mkdir()
    servis = betik_fonksiyonu(tmp_path / "i", "Read-PemfProfilEnv", BETIK, izin, uye)
    mosq = betik_fonksiyonu(tmp_path / "m", "Read-PemfProfilEnv", MOSQ, izin, uye)
    assert mosq == servis, (
        f"Read-PemfProfilEnv mosquitto servis betiğinde AYRIŞTI:\ninstall:\n{servis}\nmosquitto:\n{mosq}"
    )
