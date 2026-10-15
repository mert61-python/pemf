# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AKIM ÖLÇÜMÜ — TEK BAYRAK, TEK KAYNAK (CH4 · Y154, sahip 2026-10-15). Yaprak modül (yalnız `os`).

SAHİP KARARI (Y154): "Akım sensörü (ACS712) TÜMDEN KAPALI: akım hiç gösterilmez ve kaydedilmez; 'Anlık Güç' kalıcı gizli
(A-64). Firmware'e dokunulmaz (satırlar gelir, backend yok sayar); ACİL DURDUR / güvenlik yolları akıma bağlı değil."
Tezgâh (Oturum 13, TD5): takılı olmayan ACS712 girişleri gürültüyü 10–115 A diye basıyordu; sensörün takılı olduğu bilinmiyor.

KAPALIYKEN (VARSAYILAN): akım alanları backend'in GİRİŞİNDE atılır — STM ayrıştırıcısı (`STM_TELE … I= / X=`), STM telemetri olay
işleyicisi (ayrıştırıcıyı atlayan üretici), ESP `sensors` / `status` yükü, sim kipi ve sensör CSV kaydedicisi. Böylece canlı durum
(`currentA`, `measuredFields`), WS, sensör CSV'si, dakika ortalaması (doz kaydı) ve bildirimler (güvenilmez / aralık dışı akım) akım
TAŞIMAZ; seans geçmişi çıktıları (`/details`, `coil_runs.csv`) eski kayıtlardaki akımı vermez (veri SİLİNMEZ — bayrak açılınca geri
görünür); arayüz `akimOlcumu: false` görüp akım satırlarını çizmez.

AÇIKKEN (`PEMF_AKIM_OLCUMU=1` — ileride sensör takılır ve tezgâhta doğrulanırsa): TD5 yolu AYNEN (X=1 / ACS712-30A aralığı dışı akım
güvenilmez → yazılmaz, bobin başına tek uyarı). ⚠️ Launcher backend ortamını AÇIKÇA kurar ("LAUNCHER ENV" sınıfı): sahada açmak için
launcher'ın bu değişkeni geçirmesi gerekir.

⚠️ GÜVENLİK YOLLARI AKIMA BAĞLI DEĞİL (ölçüldü — `tests/test_CH4_akim_sensoru_TUMDEN_KAPALI_Y154.py`): ACİL DURDUR, STOP, mandal,
watchdog, keep-alive ve E-stop teyidi akım okumaz. ESP'nin "overcurrent" ALARM türü (`_Y53_DIGER_ALARM`) TAM acil durdurmaya gider —
bu bayrak alarmları SÜZMEZ (Ö.4-Y8: durdurma daralmaz).
"""

from __future__ import annotations

import os

#: Bayrağın ortam değişkeni. YALNIZ "1" açar (yanlışlıkla "true" / "evet" açmasın — tek, açık değer).
ORTAM_DEGISKENI = "PEMF_AKIM_OLCUMU"

#: Akım taşıyan telemetri anahtarları: STM ayrıştırıcısının olay gövdesi (`current`, `current_saturated`, `akim_guvenilmez`) +
#: ESP yükü / sensör CSV sütunları (`max_current`, `current_sensor_ok`).
AKIM_ANAHTARLARI = ("current", "current_saturated", "max_current", "current_sensor_ok", "akim_guvenilmez")


def akim_olcumu_acik() -> bool:
    """Akım ölçümü AÇIK mı? Varsayılan KAPALI (Y154). Her çağrıda okunur (test / tanı için ortamı izler; maliyeti ihmal)."""
    return os.environ.get(ORTAM_DEGISKENI, "").strip() == "1"


def akimsiz(yuk):
    """Bayrak KAPALIYSA akım anahtarları atılmış bir KOPYA döner; açıksa (ya da yük sözlük değilse / akım taşımıyorsa) yükün KENDİSİ.
    Girdi sözlüğü değiştirilmez (çağıran onu başka yere de verebilir)."""
    if not isinstance(yuk, dict) or akim_olcumu_acik():
        return yuk
    if not any(k in yuk for k in AKIM_ANAHTARLARI):
        return yuk
    return {k: v for k, v in yuk.items() if k not in AKIM_ANAHTARLARI}
