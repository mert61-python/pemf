# Author: mertaygn, cglrgrkn
"""D3.14 (B-8.9 · Y21 · Ö.4-Y7) — ESP32-S3 MQTT `UPDATE_FIRMWARE` (HTTPS OTA) dalı DERLEME BAYRAĞIYLA VARSAYILAN KAPALI; açılırsa yalnız pinli
ana bilgisayardan; kuyruğa atılan `stopCmd` sıfırla ilklenir. Kod SİLİNMEZ.

ÖLÇÜLEN (HEAD): dal koşulsuz derleniyor — anonim yerel broker'a (A-04) yazabilen herkes `{command:"UPDATE_FIRMWARE", url:"https://…"}` ile
kartın firmware'ini değiştirebiliyordu (üretici YOK: backend / arayüz bu komutu hiç yayınlamıyor; imza yok; yalnız "https://" öneki ve CA).
`ControlCommand stopCmd;` ilklenmemiş — `command_id[36]` + sayılar yığın çöpüyle kuyruğa gidiyordu (08-2: -Os derlemede ACK çıkmıyor).
Y21 (sahip): imaj İMZASI + HOST PİNİ ile korunur — imza sahibin anahtar düzeniyle gelir (TEZGÂH-2 / SAHİBE); o güne dek bayrak KAPALI kalır.
Kapı kaynak düzeyinde (yorum-soyulmuş, string-bilinçli `c_soy`); gerçek xtensa derlemesi (arduino-cli, esp32 3.3.11) rapordadır — ana makine
NetworkManager takımı yok (CoilController takımı var) → davranış kapısı TEZGÂH-2.
"""

from __future__ import annotations

import re
from pathlib import Path

from c_soyucu import c_soy

KOK = Path(__file__).resolve().parents[1]
S3 = KOK / "firmware" / "esps3_pemf_coil"


def _oku(p: Path) -> str:
    return c_soy(p.read_text(encoding="utf-8", errors="replace"))


def _dal() -> str:
    nm = _oku(S3 / "NetworkManager.cpp")
    i = nm.find('cmdStr == "UPDATE_FIRMWARE"')
    assert i != -1, "UPDATE_FIRMWARE dalı SİLİNMİŞ (Ö.4-Y7: ESP kodu silinmez)"
    j = nm.find("Bilinmeyen Komut", i)
    assert j != -1
    return nm[i:j]


def test_KRITIK_D3_14_bayrak_VARSAYILAN_KAPALI_ve_host_pini_BOS():
    sd = _oku(S3 / "SharedDefs.h")
    assert re.search(r"#ifndef\s+PEMF_S3_OTA_ETKIN\s*\n\s*#define\s+PEMF_S3_OTA_ETKIN\s+0\b", sd), (
        "OTA bayrağı varsayılan 0 değil"
    )
    assert re.search(r'#ifndef\s+PEMF_S3_OTA_HOST\s*\n\s*#define\s+PEMF_S3_OTA_HOST\s+""', sd), (
        "pinli host varsayılanı boş değil"
    )


def test_KRITIK_D3_14_httpUpdate_YALNIZ_bayrak_icinde_kapaliyken_REDDEDILIR():
    d = _dal()
    i_if, i_else, i_end = d.find("#if PEMF_S3_OTA_ETKIN"), d.find("#else"), d.find("#endif")
    assert -1 < i_if < i_else < i_end, f"bayrak bloğu yok: if={i_if} else={i_else} endif={i_end}"
    i_up = d.find("httpUpdate.update(")
    assert i_if < i_up < i_else, "httpUpdate.update bayrak bloğunun DIŞINDA (kapalıyken de derlenir)"
    kapali = d[i_else:i_end]
    assert 'publishEvent("ota_rejected"' in kapali, f"bayrak kapalıyken ret OLAYI yok:\n{kapali}"
    assert d.count("httpUpdate.update(") == 1


def test_KRITIK_D3_14_acilirsa_PINLI_hosttan_baska_URL_reddedilir_ve_stopCmd_SIFIR():
    d = _dal()
    i_up = d.find("httpUpdate.update(")
    i_pin = d.find("url.startsWith(PEMF_S3_OTA_HOST)")
    i_bos = d.find("strlen(PEMF_S3_OTA_HOST) == 0")
    assert -1 < i_bos < i_up and -1 < i_pin < i_up, "host pini güncellemeden ÖNCE denetlenmiyor"
    assert re.search(r"ControlCommand\s+stopCmd\s*(=\s*\{\s*\}|\{\s*\})\s*;", d), (
        "stopCmd sıfırla ilklenmiyor (yığın çöpü kuyruğa)"
    )
    assert not re.search(r"ControlCommand\s+stopCmd\s*;", d)


def test_KARSIT_D3_14_URETICI_YOK_backend_ve_arayuz_yayinlamiyor():
    """Ölü-komut envanteri: dalın üreticisi yok (Y21 sahip listesi) — bayrak kapalıyken hiçbir akış kırılmaz."""
    bulgu = []
    for kok in (KOK / "apps" / "backend", KOK / "apps" / "ui" / "src"):
        for p in kok.rglob("*"):
            if p.suffix in {".py", ".ts", ".tsx"} and "__tests__" not in p.parts and "node_modules" not in p.parts:
                try:
                    if "UPDATE_FIRMWARE" in p.read_text(encoding="utf-8", errors="replace"):
                        bulgu.append(str(p.relative_to(KOK)))
                except OSError:
                    pass
    assert bulgu == [], f"UPDATE_FIRMWARE üreticisi bulundu — envanter değişti: {bulgu}"


def test_KARSIT_D3_14_https_ve_CA_denetimi_KORUNDU():
    d = _dal()
    assert 'url.startsWith("https://")' in d and "setCACert(" in d
