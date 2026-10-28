# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.01 · B-1.35 — `start_all_coils` / `stop_all_coils` günlüğü GERÇEKTEN işlenen bobin aralığını yazar.

ÖLÇÜLEN KUSUR (HEAD ebf1c3fe): iki metot da `range(1, STM_BOBIN_SAYISI + 1)` üzerinde döner (faz 4'ten beri 1-7) ama
günlük sabit "Tüm bobinler (1-5) başlatıldı / durduruldu" yazıyordu. Saha günlüğünü okuyan geliştirici bobin 6-7'nin
sürülmediğini sanır (E-stop yolu da `stop_all_coils`'i çağırır → acil durdurma günlüğü de yanlış aralık söylüyordu).

Ölçüt: günlükteki aralık, çağrının `is_running`'ini DEĞİŞTİRDİĞİ bobin kümesiyle aynı; `STM_BOBIN_SAYISI` yamalanınca
(6) metin de "1-6" olur (sabit metin bu kolda yakalanır). STOP davranışı aynı: tek paket, dönüş True, tüm bobinler durur.
Günlük iletisi Türkçe kalır (i18n/KURALLAR.md §0.5 — geliştirici günlüğü, katalog dışı).
"""

from __future__ import annotations

import logging

import pytest

_LOGGER = "HardwareController"


def _iletiler(caplog, parca: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == _LOGGER and parca in r.getMessage()]


def _calisan(hc) -> list[int]:
    return sorted(i for i, s in hc.coils_state.items() if s["is_running"])


@pytest.mark.parametrize("bobin_sayisi", [None, 6])
def test_start_all_gunlugu_SURULEN_bobin_araligini_yazar(caplog, monkeypatch, bobin_sayisi):
    import controllers.hardware_controller as hcm
    from kayitci_donanim import gercek_hc

    with gercek_hc() as hc:
        if bobin_sayisi is not None:
            monkeypatch.setattr(hcm, "STM_BOBIN_SAYISI", bobin_sayisi)
        beklenen_ust = 7 if bobin_sayisi is None else bobin_sayisi  # değer testte pinli (hedeften okunmaz)
        once = _calisan(hc)
        assert once == [], f"başlangıçta çalışan bobin var: {once}"
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            assert hc.start_all_coils(50.0, 25.0, 0.0, 10) is True
        calisan = _calisan(hc)
        assert calisan == list(range(1, beklenen_ust + 1)), f"start_all {calisan} bobinini sürdü"
        satirlar = _iletiler(caplog, "başlatıldı")
        assert len(satirlar) == 1, f"tek 'başlatıldı' satırı bekleniyordu: {satirlar}"
        assert f"Tüm bobinler (1-{beklenen_ust}) başlatıldı" in satirlar[0], (
            f"günlük aralığı sürülen kümeyle ({calisan[0]}-{calisan[-1]}) uyuşmuyor: {satirlar[0]!r}"
        )


@pytest.mark.parametrize("bobin_sayisi", [None, 6])
def test_stop_all_gunlugu_DURDURULAN_bobin_araligini_yazar_STOP_davranisi_ayni(caplog, monkeypatch, bobin_sayisi):
    import controllers.hardware_controller as hcm
    from kayitci_donanim import gercek_hc, paket_coz

    with gercek_hc() as hc:
        assert hc.start_all_coils(50.0, 25.0, 0.0, 10) is True
        if bobin_sayisi is not None:
            monkeypatch.setattr(hcm, "STM_BOBIN_SAYISI", bobin_sayisi)
        beklenen_ust = 7 if bobin_sayisi is None else bobin_sayisi
        n_once = len(hc.core._hw_send_queue.paketler)
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            assert hc.stop_all_coils() is True
        # STOP davranışı: TEK çağrı → TEK paket; durdurulan bobinlerin duty'si sıfır gider.
        assert hc.stop_all_cagri == 1
        yeni = hc.core._hw_send_queue.paketler[n_once:]
        assert len(yeni) == 1, f"stop_all {len(yeni)} paket kuyruğa verdi (1 bekleniyordu)"
        duty = list(paket_coz(yeni[0])[0])
        assert all(d == 0 for d in duty[:beklenen_ust]), f"STOP paketinde duty>0 kaldı: {duty}"
        durdurulan = [i for i in range(1, 8) if not hc.coils_state[i]["is_running"]]
        assert durdurulan == list(range(1, beklenen_ust + 1)), f"stop_all {durdurulan} bobinini durdurdu"
        satirlar = _iletiler(caplog, "durduruldu")
        assert len(satirlar) == 1, f"tek 'durduruldu' satırı bekleniyordu: {satirlar}"
        assert f"Tüm bobinler (1-{beklenen_ust}) durduruldu" in satirlar[0], (
            f"günlük aralığı durdurulan kümeyle uyuşmuyor: {satirlar[0]!r}"
        )
        # temizlik: yamalanmış kolda kalan bobini de durdur (sızıntı olmasın)
        monkeypatch.setattr(hcm, "STM_BOBIN_SAYISI", 7)
        hc.stop_all_coils()
