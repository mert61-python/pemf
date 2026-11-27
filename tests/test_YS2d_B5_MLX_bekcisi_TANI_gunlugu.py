# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""YS2 d · B5 (YG0 25-11, İZLE): "Alan sensörü (MLX, kanal 6) veri göndermiyor" uyarısı -O2 kartla 2 kez çıktı ve kendiliğinden düzeldi;
doğrudan COM ölçümünde (uygulama kapalı, 60 sn) kesinti YOK. Kök neden kanıtlanamadı (uygulama içi günlük veri kökünde). Bu kapı
yalnız TANIYI kilitler: uyarı anında backend günlüğü "son B= kaç sn önce" ve "okuyucu döngüsü bu sürede en uzun kaç sn duraksadı"
yazar → sonraki tezgâhta (a) kart gerçekten sustu (duraksama küçük) mu, (b) okuyucu duraksadı (≈ boşluk) mı ayrılır.
UYARI KARARI DEĞİŞMEZ (eşik, tek sefer, yeniden izleme — Y285 kapıları aynen).
"""

from __future__ import annotations

import logging

from test_Y285_backend_MLX_BEKCISI_KULLANICIYI_uyarir import TELE_B, _bekci, _Saat, yalin  # noqa: F401


def test_tani_SON_B_ve_OKUYUCU_DURAKSAMASI_olculur():
    s = _Saat()
    b = _bekci(s)
    b.baglandi()
    b.veri(6)
    for _ in range(3):  # okuyucu 0,3 sn'de bir tıklar
        s.t += 0.3
        assert b.tikla() == []
    s.t += 8.0  # okuyucu 8 sn duraksadı (ağır iş)
    assert b.tikla() == []
    s.t += 1.2
    assert b.tikla() == [6]
    gecen, ara = b.tani(6)
    assert round(gecen, 1) == 10.1 and round(ara, 1) == 8.0, (gecen, ara)
    b.veri(6)
    assert b.tani(6) == (0.0, 0.0), "B= gelince tanı sıfırlanmadı"
    assert b.tani(99) == (0.0, 0.0), "hiç izlenmeyen bobin"


def test_tani_KOPUKKEN_gecen_sure_DURAKSAMA_sayilmaz():
    s = _Saat()
    b = _bekci(s)
    b.baglandi()
    b.veri(6)
    s.t += 0.3
    b.tikla()
    b.koptu()
    s.t += 50.0
    assert b.tikla() == []  # kopuk: süre işlemez
    b.baglandi()
    s.t += 0.3
    b.tikla()
    assert b.tani(6)[1] < 1.0, "kopukluk okuyucu duraksaması sayıldı"


def test_KRITIK_uyari_GUNLUGU_tani_degerlerini_TASIR(yalin, caplog):
    c = yalin
    c._set_stm_connected(True)
    c._handle_stm_line(TELE_B, retry_last_payload=lambda: None)
    c.saat.t += 0.3
    c._mlx_bekci_tikla()
    c.saat.t += 9.7
    caplog.set_level(logging.WARNING)
    c._mlx_bekci_tikla()
    satir = [r.getMessage() for r in caplog.records if "veri gondermiyor" in r.getMessage()]
    assert len(satir) == 1 and "son B= 10.0 sn once" in satir[0] and "en uzun 9.7 sn duraksadi" in satir[0], satir
