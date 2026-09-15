# -*- coding: utf-8 -*-
# Author: mertaygn
"""[FW-6] S3 WDT PANİĞİ — SAHADA DOĞRULANDI ve KAPATILDI (2026-09-13).

===============================================================================
SAHA BELİRTİSİ (sahip, S3 reflash sonrası)
===============================================================================
    [Warn] statusQueue dolu! Guncel durum datasi atlandi.   (tekrar tekrar)
    E task_wdt: Task watchdog got triggered:
       - NetworkTask (CPU 0) did not reset the watchdog in time
    E task_wdt: Aborting.
    Rebooting...

`statusQueue` doluyor çünkü tüketici (NetworkTask) bir yerde **bloklu**; sonra watchdog
panikliyor ve kart sürekli yeniden başlıyor.

===============================================================================
ÖLÇÜLEN KÖK NEDEN (tahmin DEĞİL — arduino-esp32 3.3.11 kaynağından)
===============================================================================
    NetworkClientSecure.cpp:41   sslclient->handshake_timeout = 120000;   // 120 sn
    NetworkClientSecure.cpp:33   _timeout = 30000;                        // 30 sn
    NetworkClient.cpp:30         WIFI_CLIENT_DEF_CONN_TIMEOUT_MS (3000)   // 3 sn
    SharedDefs.h                 WDT_TIMEOUT_SECONDS 10                   // 10 sn

Yerel broker ulaşılamayınca (klinikte hotspot kapalıydı) kart N denemeden sonra **bulut
TLS**'e düşüyor; tek bir TLS denemesi watchdog bütçesini **12 kata kadar** aşıyor.

⚠️ `_mqtt->setSocketTimeout(2)` BU İŞİ GÖRMEZ — o PubSubClient'in kendi OKUMA zaman aşımıdır,
altındaki TCP connect + TLS el sıkışmasını sınırlamaz. Kod okurken "zaten timeout var" diye
geçilmesi çok kolay; bu kapı tam olarak o yanılgıyı engeller.

===============================================================================
⚠️ DENETİM KAYDI
===============================================================================
`docs/denetim-bulgular-3.md` bu şüpheliyi **[FW-6] "DOĞRULANAMADI"** diye kapatmıştı:
*"PubSubClient/WiFiClientSecure kaynakları depoda OLMADIĞI için ne ispatlanabildi ne
çürütülebildi."* Kaynaklar bu makinede KURULU çıktı ve sayılar ölçüldü → bulgu **gerçek**.

⚠️ ÇIPALAR `c_soy` İLE SOYULUR: düzeltmenin kendi yorumları `setHandshakeTimeout`,
`esp_task_wdt_reset` gibi adları zaten içeriyor; ham metinde arama yapan bir kapı, kod geri
alınsa bile YEŞİL kalırdı ("yorum kapıyı kandırdı" — bu depoda ALTI kez).
"""

from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
for _p in (str(KOK), str(KOK / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_NM = KOK / "firmware" / "esps3_pemf_coil" / "NetworkManager.cpp"
_SD = KOK / "firmware" / "esps3_pemf_coil" / "SharedDefs.h"


def _kaynak(p: Path) -> str:
    from c_soyucu import c_soy

    return c_soy(p.read_text(encoding="utf-8", errors="replace"))


def _bulut_govdesi(src: str) -> str:
    bas = src.index("_connectToCloudBroker")
    # Gövde sonu: bir sonraki fonksiyon tanımına kadar yeterli bir pencere.
    return src[bas : bas + 4000]


def test_KRITIK_TLS_el_sikismasi_SINIRLANDI():
    """⚠️ ASIL KAPI — 120 sn'lik varsayılan WDT'yi (10 sn) katlayarak aşar.

    MUTASYON: `setHandshakeTimeout` çağrısını sil → KIRMIZI (reboot döngüsü geri gelir).
    """
    govde = _bulut_govdesi(_kaynak(_NM))
    assert "setHandshakeTimeout" in govde, (
        "Bulut TLS yolunda el sikisma zaman asimi AYARLANMIYOR -> kutuphane varsayilani "
        "120 sn; WDT 10 sn -> NetworkTask panikler ve kart surekli yeniden baslar"
    )


def test_KRITIK_TLS_ONCESI_ulasilabilirlik_yoklamasi_VAR():
    """Ulaşılamayan buluta hiç TLS kurulmamalı: düz TCP yoklaması 3 sn'de (ölçülmüş
    kütüphane varsayılanı) kesin cevap verir.

    MUTASYON: `WiFiClient` yoklama bloğunu sil → KIRMIZI.
    """
    govde = _bulut_govdesi(_kaynak(_NM))
    assert "WiFiClient" in govde, (
        "Bulut yolunda TLS ONCESI duz-TCP ulasilabilirlik yoklamasi YOK -> ulasilamayan "
        "adreste dogrudan TLS denenir ve bloklar"
    )


def test_KRITIK_bloklayan_adimlar_ARASINDA_WDT_beslenir():
    """Watchdog süreyi değil BOŞLUĞU ölçer: 10 sn boyunca hiç reset görmezse panikler.
    Her bloklayan çağrının arasında besleme olmalı.

    MUTASYON: `_reconnectMQTT` içindeki yerel↔bulut arası `esp_task_wdt_reset()`i sil
    → KIRMIZI.
    """
    src = _kaynak(_NM)
    # ⚠️ ÇIPA TANIMA pinli, çağrıya DEĞİL. İlk yazımda çıpa yalnız "_reconnectMQTT" idi ve
    # `process()` içindeki ÇAĞRIYI buldu → kapı yanlış pencereyi ölçtü ve kendi kapım
    # kırmızı oldu. Bu depoda tekrar eden ders: "çıpayı gerçek TANIMA/çağrıya pinle".
    bas = src.index("void PemfNetworkManager::_reconnectMQTT")
    govde = src[bas : bas + 2500]
    assert "esp_task_wdt_reset" in govde, (
        "_reconnectMQTT icinde yerel ve bulut denemeleri arasinda WDT BESLENMIYOR -> "
        "iki bloklayan cagri arka arkaya butceyi asabilir"
    )
    # Bulut gövdesinde de en az iki besleme olmalı (deneme ÖNCESİ ve SONRASI).
    assert _bulut_govdesi(src).count("esp_task_wdt_reset") >= 2, (
        "Bulut yolunda WDT beslemesi yetersiz (deneme oncesi VE sonrasi olmali)"
    )


def test_KRITIK_WDT_butcesi_DEGISMEDI():
    """Bu kapı "el sıkışma 4 sn < WDT 10 sn" payına dayanıyor. Bütçe küçültülürse pay biter.

    MUTASYON: `WDT_TIMEOUT_SECONDS`i 3 yap → KIRMIZI (4 sn el sıkışma artık sığmaz).
    """
    import re

    src = _kaynak(_SD)
    m = re.search(r"#define\s+WDT_TIMEOUT_SECONDS\s+(\d+)", src)
    assert m, "WDT_TIMEOUT_SECONDS tanimi bulunamadi"
    butce = int(m.group(1))
    assert butce >= 8, (
        f"WDT butcesi {butce} sn'ye dusmus; TLS el sikismasi (4 sn) + TCP yoklamasi (3 sn) "
        "artik guvenle sigmaz — ya butceyi buyutun ya el sikismayi kisaltin"
    )


def test_socket_timeout_TEK_BASINA_YETERLI_SANILMASIN():
    """⚠️ Karşıt kanıt / kayıt: `setSocketTimeout` hâlâ duruyor ama TLS'i SINIRLAMAZ.

    Bu test onu KALDIRMAYI engellemez; kaldırılırsa PubSubClient okuma zaman aşımı
    15 sn'lik varsayılana döner. İkisi AYRI korumadır ve ikisi de gereklidir.
    """
    src = _kaynak(_NM)
    assert "setSocketTimeout" in src, (
        "setSocketTimeout KALKMIS -> PubSubClient okuma zaman asimi 15 sn varsayilanina doner"
    )
