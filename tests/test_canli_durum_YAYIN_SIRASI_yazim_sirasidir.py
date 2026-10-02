# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.81 · İG-5.36 · 1-C bağımsız inceleme i2-F4 — `session_update` yayın SIRASI yazım sırasıdır: E-stop sonrası
istemcinin aldığı SON `session_update` "aktif" OLAMAZ.

ÖLÇÜLEN KUSUR (i2, 30/30): `live_state.update_live_session_state` denetim + yazımı `_live_state_lock` altında yapıyor ama
`session_update` YAYININI kilit bırakıldıktan SONRA planlıyordu. E-stop'tan ÖNCE denetimi geçen bir "aktif" yazımının
(ör. `/frame` AI Pro) yayını, E-stop'un "Acil Durdurma" yayınından SONRAYA kalabiliyordu → sunucu durumu doğru, ama
istemcinin aldığı son ileti `isActive:true` (arayüz E-stop sonrası "AI Pro aktif"; doğal pencere µs → DÜŞÜK).
DÜZELTME: `session_update` yayını yazımla AYNI kilit altında planlanır (`call_soon_threadsafe` FIFO + gönderim kilidi
FIFO → istemci yazım sırasını görür). Tam anlık görüntü yayını kilit dışında kalır (`_build_ws_snapshot` aynı kilidi alır).
Kilit sırası `_live_state_lock` → `_ws_pending_lock` / `_ws_lock`; tersini alan yol yok (yalnız liste/sayaç işlemleri).

KAPI (zorlanmış zamanlama): yayın kancası `/frame`in "aktif" `session_update`ini YAYIN NOKTASINDA tutar ve o sırada
E-stop'u AYRI iş parçacığında başlatır; E-stop ya biter (eski ürün: "Acil Durdurma" önce yayınlanır → ihlal) ya da
canlı durum kilidinde bekler (düzeltilmiş ürün) — en çok `_ESTOP_BEKLEME_S`. Ölçüt: son `session_update` isActive:false.
KARŞIT: sunucunun kendi durumu her iki üründe de "Acil Durdurma" (kusur yalnız yayın sırasında).
"""

from __future__ import annotations

import threading

import ai_pro_aparati as ap
import pytest

DENEME = 10
_ESTOP_BEKLEME_S = 2.0  # eski üründe E-stop (yapay donanımla) bu sürede BİTER; düzeltilmiş üründe kilitte bekler


@pytest.fixture
def o(monkeypatch, tmp_path):
    from kayitci_donanim import gercek_hc

    ns = ap.kur(monkeypatch, tmp_path)
    durum = {"kur": False, "estop": None}

    def _yayin(m):
        veri = m.get("data") or {}
        if (
            m.get("type") == "session_update"
            and veri.get("isActive")
            and str(veri.get("mode", "")).startswith("AI Pro")
            and durum["kur"]
        ):
            durum["kur"] = False
            t = threading.Thread(target=ns.api._emergency_stop_all, args=("manual",), name="kapi-estop", daemon=True)
            durum["estop"] = t
            t.start()
            t.join(_ESTOP_BEKLEME_S)  # eski ürün: E-stop biter (önce yayınlar); düzeltilmiş: kilitte bekler
        ns.ws.append(m)

    monkeypatch.setattr(ns.ls, "_ws_broadcast_sync", _yayin)
    monkeypatch.setattr(ns.api, "_ws_broadcast_sync", _yayin)
    ns.durum = durum
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            yield ns
    finally:
        ns.geri()


def _yeni_tur(o):
    ap.mandali_sifirla(o.c)
    o.c.post("/api/ai/pro/stop")
    ap.mandali_sifirla(o.c)
    _pid, r = ap.onayli_baslat(o)
    assert r.status_code == 200 and r.json().get("status") == "success", r.text[:200]


def test_KRITIK_ESTOP_sonrasi_SON_session_update_isActive_true_OLAMAZ(o):
    ihlal, ornek, sunucu_dogru = 0, None, 0
    for _ in range(DENEME):
        _yeni_tur(o)
        n = len(o.ws)
        o.durum["kur"] = True
        o.durum["estop"] = None
        r = ap.kare(o)  # /frame: "aktif" yazımı → yayın noktasında E-stop başlatılır
        assert r.status_code == 200, r.text[:200]
        t = o.durum["estop"]
        assert t is not None, "aparat: /frame 'aktif' session_update yayınına ulaşmadı"
        t.join(15)
        assert not t.is_alive(), "aparat: E-stop bitmedi"
        su = [(m.get("data") or {}) for m in o.ws[n:] if m.get("type") == "session_update"]
        if su and su[-1].get("isActive"):
            ihlal += 1
            ornek = ornek or [(d.get("isActive"), d.get("mode")) for d in su]
        with o.ls._live_state_lock:
            sunucu_dogru += o.ls._live_state["activeTreatment"].get("mode") == "Acil Durdurma"
    assert sunucu_dogru == DENEME, f"KARŞIT: sunucu durumu 'Acil Durdurma' değil ({sunucu_dogru}/{DENEME})"
    assert ihlal == 0, (
        f"{DENEME} denemenin {ihlal}'inde istemcinin aldığı SON session_update E-stop'tan SONRA 'isActive:true' "
        f"(yayın yazım sırasını izlemiyor). Örnek sıra: {ornek}"
    )
