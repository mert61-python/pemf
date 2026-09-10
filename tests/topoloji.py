# -*- coding: utf-8 -*-
# Author: mertaygn
"""BOBİN TOPOLOJİSİ — testler için TEK ÇIPA (literal bobin numarası YAZMA).

⚠️ BU DOSYA BİR TEST DEĞİL, YARDIMCIDIR (`capraz.py` deseni): adı `test_*` olmadığı için
pytest onu TOPLAMAZ. Kapı testleri `tests/test_bobin_topolojisi.py` içindedir — sabitleri
buraya, iddiaları oraya koymanın sebebi tam bu: `topoloji.py` içine yazılan bir
`test_...` fonksiyonu SESSİZCE hiç koşmaz (sahte yeşil).

⚠️ NEDEN BU MODÜL VAR (2026-09-10, faz 4'te ölçüldü):

Bobin 6-7 ESP8266'dan STM32'ye taşındığında **53 test düştü**. Hiçbiri gerçek bir regresyon
değildi: hepsi "ESP bobini" demek için literal **6** yazıyordu (`/api/coil/6/control`,
`pemf/coil/6/status`, `{6, 7, 8}`). Bobin 6 STM'e geçince o çağrılar seri yola düştü ve
fixture'da STM kontrolcüsü olmadığı için **503** döndüler.

Yani testlerin ölçtüğü şey (MQTT NACK görünürlüğü, hayalet koşu kaydı, gözetimsiz süre kapağı)
hâlâ geçerliydi; kırılan yalnızca **çıpaydı**. Bu, deponun tekrar eden en pahalı sınıfı:
zayıf çıpa → alakasız bir değişiklikte kırmızı → "düzeltmek" için birileri iddiayı bozar →
sahte-yeşil. (Aynı gün `test_mt_dose_honesty` tam bunu yaşadı.)

KURAL: bir test "ESP yolundan giden bir bobin" istiyorsa `ESP_BOBIN`, "STM yolundan giden bir
bobin" istiyorsa `STM_BOBIN` kullanır. Topoloji yine değişirse bu dosya dışında hiçbir yer
dokunulmaz.

⚠️ `ESP_COIL_IDS` bir gün BOŞALIRSA (8. slot da kaldırılırsa) `ESP_BOBIN` `None` olur ve
onu kullanan testler ATLANIR — sessizce yeşile dönmezler; `esp_yolu_gerekir()` bunu sağlar.
"""

from __future__ import annotations

import pytest

from servers.live_state import ESP_COIL_IDS, STM_COIL_IDS

#: MQTT/ESP yolundan sürülen bir bobin kimliği (faz 4 sonrası: 8 — cihazı yok, yol canlı).
ESP_BOBIN: int | None = min(ESP_COIL_IDS) if ESP_COIL_IDS else None

#: Seri/STM yolundan sürülen bir bobin kimliği.
STM_BOBIN: int = min(STM_COIL_IDS)

#: `ESP_COIL_IDS`in tamamı — "tüm ESP bobinleri" iddiaları için (E-stop kapsamı gibi).
TUM_ESP: set[int] = set(ESP_COIL_IDS)

#: `STM_COIL_IDS`in tamamı.
TUM_STM: set[int] = set(STM_COIL_IDS)


def esp_yolu_gerekir() -> None:
    """ESP yolu boşsa testi ATLA (sessiz yeşil yerine görünür atlama)."""
    if ESP_BOBIN is None:
        pytest.skip("ESP_COIL_IDS bos — MQTT yolu artik hicbir bobine bagli degil")
