"""SON-A1.55 (22 · A1b) — kurulum betiği aparatları ürün metnine girmiş DOSYA YAZAN / izin dışı yükü KOŞTURMAMALI.

D5 §5 "ölçülmüş AÇIK aparat açığı" (Y44 aparatı sürücü nitelikli değişken yükünü koşturuyordu) ve ÖLÇÜLMEMİŞ kardeşleri. Her aile için
`scripts/setup_services.ps1`'in GEÇİCİ bir kopyasına (tmp_path) dört tür zararsız yük eklenir — hepsi YALNIZ bu testin geçici dizinine bir
işaret dosyası yazar: (1) .NET statik yöntemi `[IO.File]::WriteAllText`, (2) dosyaya yönlendirme `'x' > dosya`, (3) sürücü nitelikli
değişken `${C:\\…} = 'x'`, (4) gölgelenmemiş cmdlet `Set-Content` (yalnız izin listesi OLMAYAN aileler; komut-adı listeli Y44 / D274
aparatı onu zaten reddeder). Aparat, modül sabiti kopyaya yönlendirilerek GERÇEK sürücüsüyle koşturulur. Ölçüt: aparat yükü reddedebilir
(AssertionError) ya da koşabilir — ama HİÇBİR işaret dosyası yazılmamalı (yazıldıysa aparat ürün metnini denetimsiz koşturuyor demektir:
aynı yer `Stop-Service` / `Remove-Item` / `[IO.File]::Delete` olsaydı geliştirici makinesinde GERÇEKTEN koşardı).
Ürün KOŞMAZ, gerçek dosya sistemine yalnız tmp_path'e yazılır; gerçek güvenlik duvarı / servis aparatların kendi gölgeleriyle kapalıdır.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import capraz
import pytest

KOK = Path(__file__).resolve().parents[1]
SETUP = KOK / "scripts" / "setup_services.ps1"

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="pwsh aparatı Windows betik anlamını ölçer"),
    pytest.mark.skipif((shutil.which("pwsh") is None) and not capraz.ZORUNLU, reason="pwsh (PowerShell 7) bulunamadı"),
]


def _yuk(isaret: Path, tur: str) -> str:
    p = str(isaret)
    return {
        "yontem": f"[IO.File]::WriteAllText('{p}_yontem.txt', 'x')",
        "yonlendirme": f"'x' > '{p}_yonlendirme.txt'",
        "surucu": "${" + p + "_surucu.txt} = 'x'",
        "komut": f"Set-Content -LiteralPath '{p}_komut.txt' -Value 'x'",
    }[tur]


# Her yük türü AYRI koşar (bir denetimi zayıflatan değişiklik ötekinin ilk ihlaliyle maskelenmesin).
TUM = ["yontem", "yonlendirme", "surucu", "komut"]
KOMUTSUZ = ["yontem", "yonlendirme", "surucu"]


def _kopya(tmp_path: Path, capa: str, yuk: str) -> Path:
    metin = SETUP.read_text(encoding="utf-8-sig")
    assert metin.count(capa) == 1, f"çapa betikte tek değil ({metin.count(capa)}): {capa}"
    hedef = tmp_path / "kopya" / "scripts" / "setup_services.ps1"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(
        metin.replace(capa, capa + " " + yuk + ";" if capa.endswith("{") else capa + "; " + yuk), encoding="utf-8-sig"
    )
    return hedef


def _yazilan(tmp_path: Path) -> list[str]:
    return sorted(p.name for p in (tmp_path / "isaret").glob("*.txt"))


def _kos_yutarak(fn) -> None:
    try:
        fn()
    except AssertionError:
        pass  # aparat yükü REDDETTİ (izin dışı) — beklenen düzeltilmiş davranış; ölçüt işaret dosyasının YOKLUĞU


@pytest.fixture
def isaret(tmp_path: Path) -> Path:
    (tmp_path / "isaret").mkdir()
    return tmp_path / "isaret" / "yazildi"


@pytest.mark.parametrize("tur", TUM)
def test_KRITIK_firewall_kaniti_ve_DEV_C4_aparati_mosquitto_islevindeki_YUKU_KOSTURMAZ(
    tmp_path, isaret, monkeypatch, tur
):
    import test_setup_services_firewall_kaniti as fk
    import test_setup_services_MOSQ_FW_kurali_ICERIKLE_DEV_C4 as dc4

    kopya = _kopya(tmp_path, "function Ensure-PemfMosquittoFirewallRule([bool]$EspEtkin = $false) {", _yuk(isaret, tur))
    monkeypatch.setattr(fk, "PS1", kopya)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _kos_yutarak(lambda: fk._run_firewall_func(tmp_path / "a", rule_exists=True, new_rule_fails=False))
    _kos_yutarak(lambda: dc4._kos(tmp_path / "b", []))
    assert not _yazilan(tmp_path), (
        f"Ensure-PemfMosquittoFirewallRule aparatları (firewall_kaniti / DEV-C4 — `_extract_function` + gölge, İZİN LİSTESİ YOK) ürün metnindeki "
        f"yükü GERÇEKTEN koşturdu: {_yazilan(tmp_path)}"
    )


@pytest.mark.parametrize("tur", TUM)
def test_KRITIK_D3_07_aparati_at_rest_islevindeki_YUKU_KOSTURMAZ(tmp_path, isaret, monkeypatch, tur):
    import test_D3_07_setup_services_AT_REST_profilden_BAGIMSIZ as d307
    import test_setup_services_firewall_kaniti as fk

    kopya = _kopya(
        tmp_path,
        "function Test-PemfAtRestDurumu([int]$Port, [int]$Deneme = 6, [int]$BeklemeSn = 2) {",
        _yuk(isaret, tur),
    )
    monkeypatch.setattr(fk, "PS1", kopya)
    (tmp_path / "a").mkdir()
    _kos_yutarak(
        lambda: d307.test_KRITIK_D3_07_durum_ucu_DOGRU_siniflanir(
            tmp_path / "a", "throw 'baglanti reddedildi'", "dogrulanamadi"
        )
    )
    assert not _yazilan(tmp_path), (
        f"D3_07 aparatı (`_extract_function` + yalnız Invoke-RestMethod / Start-Sleep gölgesi, modül otomatik yükleme AÇIK, izin listesi YOK) "
        f"ürün metnindeki yükü GERÇEKTEN koşturdu: {_yazilan(tmp_path)}"
    )


@pytest.mark.parametrize("tur", KOMUTSUZ)
def test_KRITIK_Y44_aparati_on_dogrulama_dilimindeki_KOMUTSUZ_yuku_KOSTURMAZ(tmp_path, isaret, monkeypatch, tur):
    import test_setup_services_API_PORT_Y44 as y44

    kopya = _kopya(tmp_path, "$OnProfil = Read-PemfProfilEnv $OnEnvFile", _yuk(isaret, tur))
    monkeypatch.setattr(y44, "SETUP", kopya)
    y44._profil(tmp_path, "PEMF_API_PORT=8010")
    _kos_yutarak(lambda: y44._kos(tmp_path, "kurulum"))
    assert not _yazilan(tmp_path), (
        f"Y44 aparatı (izin listesi YALNIZ komut adına bakıyor — D5 §5 AÇIK) komutsuz yükü GERÇEKTEN koşturdu: {_yazilan(tmp_path)}"
    )


@pytest.mark.parametrize("tur", KOMUTSUZ)
def test_KRITIK_D274_aparati_ust_duzey_KOMUTSUZ_yuku_KOSTURMAZ(tmp_path, isaret, monkeypatch, tur):
    import test_setup_services_STAGING_klinige_DOKUNMAZ_D274 as d274

    kopya = _kopya(
        tmp_path,
        "$OnEnvFile = Get-PemfProfilEnvDosyasi $AppDir $Mode (Split-Path -Parent $MyInvocation.MyCommand.Path)",
        _yuk(isaret, tur),
    )
    monkeypatch.setattr(d274, "SETUP", kopya)
    (tmp_path / "a").mkdir()
    _kos_yutarak(lambda: d274._kos(tmp_path / "a", "kurulum_device"))
    assert not _yazilan(tmp_path), (
        f"D274 aparatı (`Saf` yönlendirme + sürücü değişkenini reddediyor ama .NET YÖNTEMİNİ denetlemiyor) yükü GERÇEKTEN koşturdu: "
        f"{_yazilan(tmp_path)}"
    )
