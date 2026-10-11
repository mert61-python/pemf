# -*- coding: utf-8 -*-
"""4B-3.7 (A3 inceleme, D4.14 `799bb71e` ailesi · A-41) — ESP32-S3 firmware'inin NVS yapılandırma SÜRÜMÜ de izlenen başlıkta olmalı.

D4.14 yalnız 8266'yı düzeltti (`EEPROM_CONFIG_VERSION` → izlenen `SharedDefs.h`). S3'te aynı sınıf duruyor: `NetworkManager.cpp:123-136`
NVS'teki `cfg_ver`'i `CONFIG_VERSION` ile karşılaştırır, uyuşmazsa WiFi/MQTT ayarlarını SİLER (fabrika ayarı); `BLEProvisioning.cpp:343` aynı
makroyu yazar — makro YALNIZ skip-worktree'li `firmware/esps3_pemf_coil/Secrets.h`'de tanımlı [ÖLÇTÜM: HEAD blobunda hedefli sayım, tanım 1,
izlenen dosyalarda 0]. A-41 (cevaplı): sır OLMAYAN değerler (yapılandırma sürümü) git'te izlenir. HEAD'den derlenen S3 firmware'i sahibin yerel
değerini taşımaz → değerler ayrışırsa her dönüşümlü yakmada NVS WiFi silinir (8266'nın B-8.1'i).

Ölçüm D4.14 kapısının GERÇEK yardımcılarıyla (`_sir_dosyalari`, `_tanimlar`: sır dosyaları YALNIZ `git show HEAD:` ile; içerik basılmaz).
"""

from __future__ import annotations

import re

import test_esp8266_CONFIG_SURUMU_izlenen_baslikta_D414 as d414
from c_soyucu import c_soy

S3 = "firmware/esps3_pemf_coil"
BIRIMLER = (f"{S3}/NetworkManager.cpp", f"{S3}/BLEProvisioning.cpp")
#: HEAD'de derlenen S3'ün bugünkü NVS sürümü (git show HEAD: + hedefli sayım). Değiştirmek sahadaki kartların NVS WiFi'sini BİR KEZ siler.
BEKLENEN = 2


def _surum_makrosu() -> str:
    metin = {b: c_soy((d414.KOK / b).read_text(encoding="utf-8", errors="replace")) for b in BIRIMLER}
    karsi = re.findall(r"storedVersion\s*!=\s*([A-Za-z_]\w*)", metin[BIRIMLER[0]])
    yaz = [
        m
        for b in BIRIMLER
        for m in re.findall(r"putInt\(\s*PREF_KEY_CONFIG_VERSION\s*,\s*([A-Za-z_]\w*)\s*\)", metin[b])
    ]
    assert len(karsi) == 1 and len(yaz) == 2, f"çıpa: S3 sürüm denetimi bulunamadı (karşılaştırma {karsi}, yazım {yaz})"
    assert set(yaz) == set(karsi), (
        f"karşılaştırılan ({karsi[0]}) ile NVS'e yazılan ({yaz}) FARKLI makro → her açılışta fabrika ayarı"
    )
    return karsi[0]


def test_KRITIK_S3_NVS_surum_makrosu_IZLENEN_baslikta_A41():
    sirlar = d414._sir_dosyalari()
    assert f"{S3}/Secrets.h" in sirlar, "VAKUM: S3 sır dosyası listede yok"
    ad = _surum_makrosu()
    for birim in BIRIMLER:
        tanimlar = [(d, r) for (n, d, r) in d414._tanimlar(birim, sirlar, {birim}) if n == ad]
        assert len(tanimlar) == 1, f"{birim}: {ad} include kapanışında {len(tanimlar)} kez tanımlı: {tanimlar}"
        deger, dosya = tanimlar[0]
        assert dosya not in sirlar, (
            f"{birim}: {ad} YALNIZ skip-worktree/sır dosyasında ({dosya}) — HEAD'den derlenen S3 firmware'i sahibin yerel değerini "
            "TAŞIMAZ (A-41: sır olmayan değer git'te izlenir)"
        )
        assert int(deger.strip("()")) == BEKLENEN, (
            f"{birim}: {ad}={deger} ({dosya}) — bugünkü HEAD değeri {BEKLENEN} değil"
        )
