# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.30 · P4 — watchdog ve termal (STM_EVT) dallarının bobin sıfırlama yayını TEK yardımcıda.

ÖLÇÜLEN (DENETİM-12 §3.1-§3.2 P4): `headless_core._handle_stm_line`'da "Watchdog Timeout" ve
"STM_EVT" dalları birebir İKİZ 7-bobin sıfırlama bloğu taşıyordu; watchdog kopyası KAPISIZDI
(bobin 7'yi atlayan mutantta 179/179 yeşil). B-1.18 (D1.73) watchdog sonrası donanım sıfırlamasını
eklerken bir kopyaya yapılan düzeltme diğerinde kalırdı → önce tek yardımcı.

⚠️ A-47 (sahip, KAPALI KARAR): termal kesme YOK — termal dal yalnız firmware'in (bugün kapalı)
NTC satırını AYRIŞTIRIR; bu madde o dalın davranışını DEĞİŞTİRMEZ (aşağıdaki A kolu pinler).

A (davranış): satır gerçek `_handle_stm_line`'a verilir; watchdog satırı FIRMWARE KAYNAĞINDAN okunur
(literal değil). B (yapı): anahtarları sıfırlama şeması VE değerleri sabit-sıfır sözlük modülde TAM
1 yerde kurulur — ACK ayrıştırmasının aynı şemalı CANLI yükü sayılmaz (öz-denetim kolu).
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

import pytest
from event_bus import EventPriority
from headless_core import HeadlessCore
from topoloji import TUM_STM

KOK = Path(__file__).resolve().parents[1]
MAIN_C = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
HEADLESS_CORE = KOK / "apps" / "backend" / "headless_core.py"
SIFIRLAMA_SEMASI = frozenset(
    {"coil_id", "duty", "duty_cycle", "freq", "frequency", "phase", "duration_min", "running", "pwm_active"}
)
#: D1.74 (B-1.19): sıfırlama yayını SENTETİKTİR — kartın bir paketi kabul ettiğinin (STM_OK) kanıtı değil; api_server
#: bununla ne sistematik-NACK kararını siler ne de STM'i "bağlı" sayar. İşaret yükte `True` olarak bulunmalı.
SENTETIK = "sentetik"
#: Termal satır firmware'de `snprintf` biçimi (eşik sayısı çalışma anında basılır) — dal yalnız
#: "STM_EVT" alt dizesine bakar; mevcut M2 kapısıyla aynı dize.
STM_EVT_TERMAL = "-> STM_EVT: TERMAL kesme (>=48C) - bobin(ler) durduruldu, sogumada kilitli."


class _YakalayanBus:
    def __init__(self):
        self.olaylar = []  # (olay, veri, öncelik)

    def publish(self, event_type, data, priority=None, source=None):
        self.olaylar.append((event_type, data, priority))


class _KaydedenLogger:
    """Hata/istisna günlüklerini kaydeder: aparat eksikliği (AttributeError) bir `try/except: logger.exception` ile
    yutulup kol yanlışlıkla YEŞİL kalmasın."""

    def __init__(self):
        self.hatalar = []

    def _hata(self, msg, *a, **k):
        self.hatalar.append(str(msg) % a if a else str(msg))

    error = exception = critical = _hata

    def _sessiz(self, *a, **k):
        pass

    debug = info = warning = log = _sessiz


def _core():
    import queue

    c = HeadlessCore.__new__(HeadlessCore)  # yalnız `_handle_stm_line`'ın ihtiyacı alanlar
    c.logger = _KaydedenLogger()
    c.event_bus = _YakalayanBus()
    # 1-B bağımsız inceleme (i6): GERÇEK HWSender kuyruğu — termal dala donanıma giden bir STOP (A-47'nin yasakladığı
    # termal KESME) eklense kapı olay veriyolunu görüp kuyruğu GÖREMİYORDU (aparatta kuyruk yoktu; AttributeError
    # mutantın kendi try'ı ile yutuldu → 41/41 YEŞİL).
    c._hw_send_queue = queue.Queue()
    return c


def _firmware_watchdog_satiri() -> str:
    metin = MAIN_C.read_text(encoding="utf-8", errors="replace")
    adaylar = re.findall(r'"([^"\n]*Watchdog Timeout[^"\n]*)"', metin)
    assert len(adaylar) == 1, f"firmware watchdog satırı tekil bulunamadı: {adaylar}"
    return adaylar[0].replace("\\r", "").replace("\\n", "").strip()


@pytest.mark.parametrize(
    ("kaynak", "olay"),
    [("watchdog", "hardware.stm.watchdog_timeout"), ("termal", "hardware.stm.thermal_cutoff")],
)
def test_P4_A_satir_TUM_STM_bobinlerinin_sifirlamasini_yayinlar(kaynak, olay):
    satir = _firmware_watchdog_satiri() if kaynak == "watchdog" else STM_EVT_TERMAL
    c = _core()
    c._handle_stm_line(satir)

    # Bağımsız inceleme (r5): olaylar eskiden TÜRE göre süzülüyordu — termal dala ek bir CRITICAL
    # `watchdog_timeout` (api_server onu E-stop'a çevirir = termal KESME, A-47 yasak) eklense yeşil
    # kalıyordu. Tam dizi pinlenir: tek CRITICAL olay + her STM bobini için bir sıfırlama, BAŞKA olay yok.
    dizi = [(t, p) for t, _d, p in c.event_bus.olaylar]
    assert c._hw_send_queue.empty(), (
        f"{kaynak}: donanım kuyruğuna komut verildi ({c._hw_send_queue.qsize()}) — termal/watchdog satırı backend'de "
        "bobin KESMESİNE dönmez (A-47: termal kesme YOK; firmware kendi durdurur)"
    )
    assert c.logger.hatalar == [], f"{kaynak}: işleyici hata günlüğüne düştü (aparat/ürün): {c.logger.hatalar}"
    beklenen = [(olay, EventPriority.CRITICAL)] + [("hardware.stm.coil_update", EventPriority.HIGH)] * len(TUM_STM)
    assert dizi == beklenen, f"{kaynak}: olay dizisi değişti (A-47: termal dal davranışı DEĞİŞMEZ): {dizi}"
    sifirlar = [(d, p) for t, d, p in c.event_bus.olaylar if t == "hardware.stm.coil_update"]
    assert sorted(d["coil_id"] for d, _p in sifirlar) == sorted(TUM_STM), (
        f"{kaynak}: sıfırlanan bobinler {sorted(d['coil_id'] for d, _p in sifirlar)} ≠ STM bobinleri {sorted(TUM_STM)}"
    )
    for d, p in sifirlar:
        assert set(d) == SIFIRLAMA_SEMASI | {SENTETIK}, f"{kaynak}: sıfırlama şeması değişti: {sorted(d)}"
        assert d[SENTETIK] is True, f"{kaynak}: sıfırlama yayını SENTETİK işaretini taşımıyor (D1.74): {d}"
        sifir = {k: v for k, v in d.items() if k not in ("coil_id", SENTETIK)}
        assert all(v == 0 for v in sifir.values()) and d["running"] is False and d["pwm_active"] is False, (
            f"{kaynak}: bobin {d['coil_id']} SIFIRLANMADI: {d}"
        )
        assert p == EventPriority.HIGH


def _sabit_sifir(v: ast.expr) -> bool:
    return isinstance(v, ast.Constant) and not isinstance(v.value, str) and v.value is not None and v.value == 0


def _sifirlama_sozlukleri(kaynak: str) -> list[int]:
    """Anahtarları sıfırlama şeması VE (coil_id dışındaki) değerleri sabit-sıfır sözlük literallerinin satırları."""
    satirlar = []
    for d in ast.walk(ast.parse(kaynak)):
        if not isinstance(d, ast.Dict) or not all(isinstance(k, ast.Constant) for k in d.keys):
            continue
        # D1.74: SENTETİK işareti olan ve olmayan kopya AYNI sayılır (işaretsiz ikinci bir kopya da yakalanır).
        if {k.value for k in d.keys} - {SENTETIK} != SIFIRLAMA_SEMASI:
            continue
        if all(_sabit_sifir(v) for k, v in zip(d.keys, d.values) if k.value not in ("coil_id", SENTETIK)):
            satirlar.append(d.lineno)
    return satirlar


def test_P4_B_sifirlama_yuku_TEK_yerde_kurulur():
    satirlar = _sifirlama_sozlukleri(HEADLESS_CORE.read_text(encoding="utf-8"))
    assert len(satirlar) == 1, (
        f"bobin sıfırlama yükü headless_core'da {len(satirlar)} yerde kuruluyor (satır {satirlar}) — "
        "watchdog ve termal dalları `_tum_bobinleri_sifirla_yayinla`'yı paylaşmalı (bir kopyaya yapılan "
        "düzeltme diğerinde kalır)"
    )


def test_P4_B_ozdenetim_CANLI_yuk_sayilmaz_sifir_yuk_sayilir():
    canli = (
        "d = {'coil_id': c, 'duty': duty, 'duty_cycle': duty, 'freq': f, 'frequency': f, 'phase': ph,"
        " 'duration_min': dk, 'running': r, 'pwm_active': r}\n"
    )
    sifir = (
        "d = {'coil_id': c, 'duty': 0.0, 'duty_cycle': 0.0, 'freq': 0.0, 'frequency': 0.0, 'phase': 0.0,"
        " 'duration_min': 0, 'running': False, 'pwm_active': False}\n"
    )
    assert _sifirlama_sozlukleri(canli) == []
    assert _sifirlama_sozlukleri(sifir) == [1]
    assert _sifirlama_sozlukleri(canli + sifir + sifir) == [2, 3]
    isaretli = sifir.replace("'pwm_active': False}", "'pwm_active': False, 'sentetik': True}")
    assert isaretli != sifir
    assert _sifirlama_sozlukleri(isaretli + sifir) == [1, 2]
