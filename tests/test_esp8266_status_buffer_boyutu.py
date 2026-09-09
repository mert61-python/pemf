# -*- coding: utf-8 -*-
# Author: mertaygn
"""8266 STATUS JSON BUFFER'I — sahada telemetri DÜŞÜYORDU (2026-09-09, ölçüldü).

BELİRTİ (sahibin seri çıktı kaydı, bobin yönü ölçümü sırasında):

    [MQTT] Status mesaji sigmadi! Req: 505

Status telemetrisi komple atılıyor → panel bayat değer gösteriyor. `snprintf` taşmayı kırpar
ama kod kırpılmış JSON'u göndermek yerine mesajı ATAR (doğru karar — yarım JSON parse
edilemez); kullanıcı tarafında bu "veri gelmiyor" olarak görünür, HATA olarak görünmez.

KÖK NEDEN SÜRÜKLENME: `_setupMQTT()` taşıma buffer'ını 768'e çıkarmış ve yorumunda
"Status mesajı (640)" diyor — ama `publishStatus` içindeki yerel `jsonBuffer` 480'de KALMIŞ.
Taşıma 640 için hazırlanmış, üretici hâlâ 480'lik kaba yazıyordu.

BU KAPI NE YAPAR — SABİT KARŞILAŞTIRMASI DEĞİL, YENİDEN HESAPLAMA: biçim dizesini kaynaktan
okur, statik metni ölçer, her dönüşüm belirteci için EN KÖTÜ uzunluğu ekler ve bildirilen
buffer'ın bunu kapsadığını doğrular. Böylece JSON'a YENİ ALAN eklenirse kapı kendiliğinden
kırmızı olur — asıl arıza tam olarak "alan eklendi, boyut güncellenmedi" sınıfındaydı.

C bu makinede DERLENEMEZ → doğrulanabilir = YAPISAL. Gerçek doğrulama (seri portta artık
"sigmadi" satırı YOK, panel canlı) tezgâh-ONLY.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
NM = KOK / "firmware" / "esp8266_pemf_coil" / "NetworkManager.cpp"

pytestmark = pytest.mark.skipif(not NM.exists(), reason="firmware/ kaynak agaci yok")

_SPES = re.compile(r"%[-+ #0-9.]*(?:ll|l|h)?[a-zA-Z]")

#: Dönüşüm belirteci → EN KÖTÜ üretilen karakter sayısı (işaret dahil).
_EN_KOTU = {"%d": 11, "%u": 10, "%lu": 10, "%llu": 20, "%.2f": 12, "%.3f": 12, "%f": 20}

#: `%s` argümanlarının biçim dizesindeki SIRAYLA en kötü uzunlukları.
#: bool → "false" (5), SSID → 32 (802.11 üst sınırı), IPv4 metni → 15 ("255.255.255.255").
#: Sıra kaynaktan ÖLÇÜLDÜ: wifi_connected, wifi_ssid, wifi_ip, portal_active, portal_ip,
#: portal_ssid, mqtt_connected, pwm_active, sensors_ok, temp_ok, magnetic_ok, current_ok.
#: ⚠️ SIRA ÖNEMLİ: ilk yazımda wifi_ip ile portal_active yer değiştirmişti. Toplam tesadüfen
#: aynı çıkıyordu (aynı sayı kümesi) ama bir alan eklenince/çıkınca eşleme kayardı.
_S_MAKS = [5, 32, 15, 5, 15, 32, 5, 5, 5, 5, 5, 5]


def _literalleri_birlestir(ham: str) -> str:
    """Bitişik C string literallerini tek dizeye indirger (kaçışlı tırnak korunur)."""
    yer = "\x00"
    ham = ham.replace(chr(92) + '"', yer)  # \" → yer tutucu
    return "".join(ham.split('"')[1::2]).replace(yer, '"')


def _bicim_ve_buffer() -> tuple[str, int]:
    satirlar = io.open(NM, encoding="utf-8", errors="replace").read().splitlines()
    i = next(n for n, s in enumerate(satirlar) if "void NetworkManager::publishStatus" in s)

    m = None
    for n in range(i, min(i + 20, len(satirlar))):
        m = re.search(r"static char jsonBuffer\[([A-Za-z0-9_]+)\]", satirlar[n]) or m
    assert m, "publishStatus icinde jsonBuffer bildirimi bulunamadi -> kapi BAYAT"
    boyut_ifade = m.group(1)
    if boyut_ifade.isdigit():
        buffer = int(boyut_ifade)
    else:
        d = re.search(rf"#define\s+{re.escape(boyut_ifade)}\s+(\d+)", "\n".join(satirlar))
        assert d, f"{boyut_ifade} sabiti tanimli degil"
        buffer = int(d.group(1))

    bas = next(n for n in range(i, i + 30) if 'PSTR("{' in satirlar[n])
    son = next(n for n in range(bas, bas + 20) if "uptime" in satirlar[n])
    return _literalleri_birlestir("".join(satirlar[bas : son + 1])), buffer


def _en_kotu_boyut(bicim: str) -> int:
    spesler = _SPES.findall(bicim)
    statik = _SPES.sub("", bicim)
    si, degisken = 0, 0
    for sp in spesler:
        if sp == "%s":
            degisken += _S_MAKS[si] if si < len(_S_MAKS) else 32
            si += 1
        else:
            assert sp in _EN_KOTU, f"bilinmeyen donusum belirteci {sp} -> kapiyi guncelle"
            degisken += _EN_KOTU[sp]
    return len(statik) + degisken + 1  # + NUL


def test_KRITIK_status_buffer_EN_KOTU_JSONU_kapsiyor():
    """Bildirilen buffer, biçim dizesinden hesaplanan en kötü boyutu KAPSAMALI.

    ⚠️ Yeniden hesaplama şart: sabit bir sayıyla karşılaştırmak, JSON'a alan eklendiğinde
    sessiz kalırdı — arıza tam olarak böyle oluştu (480 kaldı, alanlar büyüdü).
    """
    bicim, buffer = _bicim_ve_buffer()
    gerek = _en_kotu_boyut(bicim)
    assert buffer >= gerek, (
        f"status JSON buffer YETERSIZ: bildirilen {buffer}, en kotu {gerek} bayt "
        f"(statik {len(_SPES.sub('', bicim))} + degisken + NUL). Sahada olculen belirti: "
        "'[MQTT] Status mesaji sigmadi! Req: 505' -> telemetri KOMPLE dusuyor."
    )


def test_KRITIK_MQTT_tavani_PAYLOAD_topic_ve_EKI_kapsiyor():
    """PubSubClient paket tavanı payload + topic + protokol ekini kapsamalı.

    ⚠️ Yalnız `jsonBuffer`ı büyütmek yetmez: taşıma tavanı küçük kalırsa `publish()` sessizce
    başarısız olur ve mesaj yine gitmez (aynı belirti, farklı katman). Kaynakta bunu ayrıca
    `static_assert` kilitler; bu test o `static_assert`ın VARLIĞINI ve sayıların tutarlılığını
    ölçer (derleyici burada koşmadığı için).
    """
    kaynak = io.open(NM, encoding="utf-8", errors="replace").read()
    sabitler = {
        ad: int(d)
        for ad, d in re.findall(
            r"#define\s+(STATUS_JSON_BUF|MQTT_BUFFER_BYTES|MQTT_TOPIC_MAKS|MQTT_PROTOKOL_EK)\s+(\d+)", kaynak
        )
    }
    eksik = {"STATUS_JSON_BUF", "MQTT_BUFFER_BYTES", "MQTT_TOPIC_MAKS", "MQTT_PROTOKOL_EK"} - set(sabitler)
    assert not eksik, f"bu sabitler tanimli degil: {sorted(eksik)}"
    assert "static_assert(" in kaynak, "derleme-ani tutarlilik kontrolu (static_assert) YOK"
    toplam = sabitler["STATUS_JSON_BUF"] + sabitler["MQTT_TOPIC_MAKS"] + sabitler["MQTT_PROTOKOL_EK"]
    assert toplam <= sabitler["MQTT_BUFFER_BYTES"], (
        f"MQTT tavani ({sabitler['MQTT_BUFFER_BYTES']}) payload+topic+ek ({toplam}) icin YETERSIZ"
    )


def test_MQTT_tavani_SABITTEN_okunuyor():
    """`setBufferSize` çıplak sayı DEĞİL, sabiti kullanmalı — sürüklenmenin doğduğu yer.

    Eski kod `setBufferSize(768)` yazıyor ve yorumunda status'u 640 sanıyordu; iki sayı ayrı
    yerlerde durduğu için biri güncellenip diğeri unutuldu.
    """
    kaynak = io.open(NM, encoding="utf-8", errors="replace").read()
    m = re.search(r"setBufferSize\(\s*([A-Za-z0-9_]+)\s*\)", kaynak)
    assert m, "setBufferSize cagrisi bulunamadi -> kapi BAYAT"
    assert not m.group(1).isdigit(), (
        f"setBufferSize ciplak sayi kullaniyor ({m.group(1)}) -> static_assert anlamsizlasir; "
        "MQTT_BUFFER_BYTES sabitini kullanin"
    )


def test_TASMA_mesaji_ATIYOR_kirpmiyor():
    """Taşma hâlinde kırpılmış JSON GÖNDERİLMEMELİ (yarım JSON parse edilemez).

    Karşıt kanıt: mevcut davranış doğru; buffer büyütülürken bu koruma kaldırılmasın.
    """
    kaynak = io.open(NM, encoding="utf-8", errors="replace").read()
    i = kaynak.index("void NetworkManager::publishStatus")
    blok = kaynak[i : i + 2600]
    assert "jsonLen >= (int)sizeof(jsonBuffer)" in blok, "tasma kontrolu YOK/degismis"
    assert "return" in blok.split("jsonLen >= (int)sizeof(jsonBuffer)")[1][:200], (
        "tasmada erken donus YOK -> kirpilmis JSON yayinlanir"
    )
