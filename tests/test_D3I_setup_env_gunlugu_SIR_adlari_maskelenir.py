# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D3I-A2.8 (D3.08 / D3.29) — `setup_services.ps1` `Format-PemfEnvGunluk` SIR TAŞIYAN ortam değerlerini günlüğe DÜZ YAZMAZ.

ÖLÇÜLEN KUSUR: maske deseni `PASS|TOKEN|SECRET|KEY|CREDENTIAL|PRIVATE|_PAT$` backend'in okuduğu iki sır taşıyan adı kapsamıyordu →
`deploy\\<Mode>.env`e konursa `setup_services.log`a DÜZ düşer: `PEMF_BACKUP_RECOVERY_CODE` (kurtarma zarfını açan kod — zarf + yedek =
sqlcipher_key + patient_fernet_key → tüm hasta verisi) ve `PEMF_SENTRY_DSN` (DSN açık anahtarı olay gönderme hakkı verir).
SÖZLEŞME: backend'in okuduğu SIR adlarının hepsi maskelenir (ad görünür, değer `***`); sır OLMAYAN ayar değerleri görünür kalır (tanı).
Gerçek sır KULLANILMAZ (rastgele nöbetçi); işlev PowerShell parser'ıyla çekilir (D3.08 kapısının aparatı).
"""

from __future__ import annotations

import secrets

import pytest
from test_setup_services_firewall_kaniti import PWSH, _extract_function, _ps_lit, _pwsh_file

pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh (PowerShell 7) yok — PS fonksiyonu koşturulamaz")

#: backend `os.getenv` taramasından (D3I-A2.8 ölçümü) SIR taşıyan adlar — hepsi maskelenmeli
SIR_ADLARI = (
    "PEMF_BACKUP_RECOVERY_CODE",
    "PEMF_SENTRY_DSN",
    "PEMF_API_TOKEN",
    "PEMF_CLOUDFLARE_TUNNEL_TOKEN",
    "PEMF_DEVICE_REGISTRY_SECRET",
    "PEMF_MASTER_SECRET",
    "PEMF_MQTT_PASS",
    "PEMF_MQTT_CLOUD_PASS",
    "PEMF_SOURCE_KEY",
    "PEMF_SQLCIPHER_KEY",
    "SUPABASE_KEY",
)
#: sır OLMAYAN ayarlar — değer görünür kalmalı (tanı)
ACIK_ADLAR = ("PEMF_HEADLESS", "PEMF_API_PORT", "PEMF_DATA_DIR", "SUPABASE_URL", "PEMF_ENCRYPT_AT_REST")


@pytest.fixture(scope="module")
def gunluk(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("d3i_a28")
    func = _extract_function(tmp, "Format-PemfEnvGunluk")
    nobetci = {k: "NOBETCI_" + secrets.token_hex(8) for k in SIR_ADLARI + ACIK_ADLAR}
    satirlar = "; ".join(f'"{k}" = {_ps_lit(v)}' for k, v in nobetci.items())
    body = f"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
{func}
$m = [ordered]@{{ {satirlar} }}
Write-Output ("GUNLUK=" + (Format-PemfEnvGunluk $m))
"""
    r = _pwsh_file(tmp, "a28.ps1", body)
    assert r.returncode == 0, r.stdout + r.stderr
    return nobetci, next(s for s in r.stdout.splitlines() if s.startswith("GUNLUK="))


@pytest.mark.parametrize("ad", SIR_ADLARI)
def test_KRITIK_D3I_A2_8_sir_tasiyan_ortam_DEGERI_gunluge_DUZ_dusmez(gunluk, ad):
    """MUTASYON: desenden `_CODE$` / `_DSN$` çıkarılır (= HEAD) → kurtarma kodu / DSN KIRMIZI."""
    nobetci, satir = gunluk
    assert nobetci[ad] not in satir, f"{ad} DEĞERİ günlüğe düz düştü"
    assert f"{ad}=***" in satir, f"{ad} adı maskeli görünmüyor"


@pytest.mark.parametrize("ad", ACIK_ADLAR)
def test_KARSIT_D3I_A2_8_sir_olmayan_ayar_GORUNUR_kalir(gunluk, ad):
    """Her şeyi maskeleyen desen tanıyı öldürür. MUTASYON: desen `.` (her ad) → KIRMIZI."""
    nobetci, satir = gunluk
    assert f"{ad}={nobetci[ad]}" in satir, f"{ad} sır değil ama maskelendi"
