# Author: mertaygn, cglrgrkn
"""D1.22 · B-10.29 — ürün STM paket kurucusunda ALAN SIRASI davranışla: her bobin kendi duty/faz/frekans/süresini taşır.

ÖLÇÜLEN (plan): `hardware_controller._send_stm_manual_update`'te `*stm32_duties` ile `*stm32_phases` yer değiştirince
25 dosyanın 244 testi YEŞİL kalıyordu — çözümleme testi paketi kendi içinde STM_PAKET_FMT ile yeniden kuruyordu.
Firmware duty üst sınırını denetlemediğinden faz değeri duty olarak gider: bobin tavan duty ile sürülür ya da hiç
sürülmez (kategori 1).

Kapı: GERÇEK `HardwareController` (kayıtçı donanım kuyruğu); 7 STM bobinine BİRBİRİNDEN FARKLI duty/faz/frekans/süre
verilir; kuyruğa giden SON paket firmware doğrulamasının aynası (`tools/stm32_simulator.decode_packet`) ile çözülür ve
bobin başına dört alan beklenen değerle eşlenir. Değerler alanlar arası takası ayırt edecek biçimde seçildi (bir
alanın değeri başka bir alanın geçerli aralığında bile olsa bobin/alan eşleşmesi tutmaz).
"""

from __future__ import annotations

import pytest
from kayitci_donanim import gercek_hc, paket_coz
from topoloji import TUM_STM

_BOBINLER = sorted(TUM_STM)
# bobin → (frekans Hz, duty %, faz °, süre dk) — her alan bobinden bobine ve alandan alana farklı
_DEGER = {b: (10.0 * b + 3.0, 5.0 * b + 7.0, 11.0 * b + 13.0, b + 1) for b in _BOBINLER}


def test_KRITIK_paket_her_bobinin_dort_alanini_KENDI_yerinde_tasir():
    with gercek_hc() as hc:
        for b in _BOBINLER:
            f, d, p, dk = _DEGER[b]
            assert hc.update_coil(b, f, d, p, duration=dk) is True, f"aparat: bobin {b} başlatılamadı"
        duty, faz, frek, sure, _ref, _kip = paket_coz(hc.core._hw_send_queue.paketler[-1])
    for b in _BOBINLER:
        f, d, p, dk = _DEGER[b]
        i = b - 1
        assert (duty[i], faz[i], frek[i]) == (pytest.approx(d / 100.0), pytest.approx(p), pytest.approx(f)), (
            f"bobin {b}: pakette duty={duty[i]} faz={faz[i]} frekans={frek[i]} — beklenen {d / 100.0}/{p}/{f} "
            "(alan sırası kaydı: faz duty yerine giderse bobin tavan duty ile sürülür)"
        )
        assert sure[i] == dk, f"bobin {b}: pakette süre {sure[i]} dk (beklenen {dk})"


def test_KARSIT_bos_bobinler_paket_varsayilanlarini_tasir():
    """Hiç sürülmeyen bobinler sıfır duty/faz ve 100 Hz taşır (alan sırası başka bir yolla da sabit)."""
    with gercek_hc() as hc:
        b = _BOBINLER[0]
        assert hc.update_coil(b, 77.0, 33.0, 21.0, duration=2) is True
        duty, faz, frek, _sure, _ref, _kip = paket_coz(hc.core._hw_send_queue.paketler[-1])
    for diger in _BOBINLER[1:]:
        assert (duty[diger - 1], faz[diger - 1]) == (0.0, 0.0), f"boş bobin {diger}: duty/faz sıfır değil"
