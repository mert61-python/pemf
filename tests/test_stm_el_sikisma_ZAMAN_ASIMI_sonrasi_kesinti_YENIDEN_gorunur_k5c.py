# -*- coding: utf-8 -*-
"""2-E incelemesi A-6 (E2-3.12 `k5c`) — D2.10'un KÖR KOLU: port AÇILIP el sıkışma ZAMAN AŞIMINA düşerse sonraki açılış hatası YENİ durumdur
ve yeniden (bir kez) yazılır.

D2.10 sözleşmesi (`utils/stm32_transport.py`): açılış hatası imza (port + tür + metin) DEĞİŞİNCE bir kez WARNING; "port açılıp el sıkışma
zaman aşımına düşerse sonraki açılış hatası yeni durum sayılır" (`self._hata_imzasi = None  # D2.10: port AÇILDI`). Bu satırı kaldıran
mutant (`k5c`) 2-E'nin 5 testinde ve E2-3.12 kapısında YEŞİL kalıyordu: sahada kart takılıp (port açılır) yanıt vermeden çıkarılınca
sonraki kesinti günlükte HİÇ görünmezdi (önceki kesintiyle aynı imza).
ÖLÇÜM: D2.10'un aparatı (GERÇEK `open_and_handshake`, sahte saat, OLMAYAN `COM239`); arada SESSİZ sanal STM (`socket://` loopback —
bağlantıyı kabul eder, `STM_READY` BASMAZ → el sıkışma zaman aşımı).
"""

from __future__ import annotations

import socket
import threading

from test_stm_YOKKEN_gunluk_DURUM_degisiminde_ve_OZETLE_D210 import _YOK_PORT, _dene, _metinler, ortam  # noqa: F401


def test_KRITIK_k5c_el_sikisma_ZAMAN_ASIMI_sonrasi_ayni_acilis_hatasi_YENIDEN_bir_kez_gorunur(ortam, monkeypatch):
    """kesinti (COM239) → kart takılı ama SESSİZ (port açılır, el sıkışma zaman aşımı) → yine COM239 kesintisi: iki kesintinin her biri
    BİR KEZ yazılır. MUTASYON k5c: port açılınca imza sıfırlanmaz → ikinci kesinti yutulur → KIRMIZI."""
    sunucu = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sunucu.bind(("127.0.0.1", 0))
    sunucu.listen(1)
    port = sunucu.getsockname()[1]
    baglantilar: list[socket.socket] = []
    kapat = threading.Event()

    def _sessiz_stm():
        try:
            c, _ = sunucu.accept()
            baglantilar.append(c)
            c.settimeout(0.2)
            while not kapat.is_set():
                try:
                    if not c.recv(1024):
                        break
                except OSError:
                    continue  # yanıt YOK: yoklamaları yut
        except OSError:
            pass

    is_parcacigi = threading.Thread(target=_sessiz_stm, daemon=True)
    is_parcacigi.start()
    t = ortam.st.Stm32SerialTransport(ortam.log)
    try:
        _dene(ortam, t, 5)
        monkeypatch.setenv("PEMF_STM_PORT", f"socket://127.0.0.1:{port}")
        ortam.saat["adim"] = (
            0.25  # el sıkışma döngüsü sahte saatte ilerlesin (dinleme → yoklama → en geç 12 sn zaman aşımı)
        )
        sonuc = _dene(ortam, t, 1)
        ortam.saat["adim"] = 0.0
        assert sonuc is None, "aparat: sessiz sanal STM ile el sıkışma OLMAMALIYDI"
        monkeypatch.setenv("PEMF_STM_PORT", _YOK_PORT)
        _dene(ortam, t, 5)
    finally:
        kapat.set()
        for c in baglantilar:
            c.close()
        sunucu.close()
        is_parcacigi.join(timeout=5)
    m = _metinler(ortam)
    assert baglantilar, "aparat: port hiç açılmadı (el sıkışma denenmedi):\n" + "\n".join(m)
    basarisiz = [x for x in m if "Bağlantı başarısız" in x]
    assert len(basarisiz) == 2, (
        f"el sıkışma zaman aşımından sonraki kesinti BİR KEZ yeniden yazılmalı (bulunan {len(basarisiz)} 'Bağlantı başarısız'):\n"
        + "\n".join(m)
    )
