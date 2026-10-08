# -*- coding: utf-8 -*-
"""O-A2-K.1 (2-A incelemesi) ürün yarısı — durdurulan/biten AI Pro döngüsünün GEÇ kapanışı yalnız KENDİ döneminin canlı E
bağlamını siler; döngü çıktıktan SONRA kurulan (yeni analizin) bağlamına dokunmaz.

ÖLÇÜLEN (2-A incelemesi, tanı eklentisi): döngünün kapanışı (`_ai_pro_loop` teardown → `efield_live.set_context([])`) süreç
geneli E bağlamını KOŞULSUZ siliyordu; döngü bittikten hemen sonra yapılan fantom/petri analizinin kurduğu bağlam, eski
döngünün geç teardown'ıyla siliniyordu (E barı boş kalır; güvenlik etkisi yok — test sızıntısı `test_KARSIT_E07_em_fantom_
OLCEKLI_kipte_baglam_KURULUR`'u zamanlamaya bağlı kırmızı yapıyordu).
Kapı BELİRLENİMCİ: GERÇEK `_ai_pro_loop` (sahte kamera) kendi kesintisiyle (doz modeli N turda hata) çıkar; kameranın
`release()`'i — döngü çıktıktan SONRA, teardown'ın temizliğinden ÖNCE — yeni bir analiz bağlamı kurar (yarış penceresi).
"""

from __future__ import annotations

import numpy as np


class _BozulanKedi:
    def __init__(self, ilk_tahminde=None):
        self.n = 0
        self.ilk_tahminde = ilk_tahminde

    def __call__(self, saglayici, *a, **k):
        self.n += 1
        if self.n == 1:
            if self.ilk_tahminde:
                self.ilk_tahminde()
            return [0.3] * 7, [0.0] * 7, 1.0
        raise RuntimeError("doz modeli seans ortasında bozuldu (test)")


def _dongu_kos(monkeypatch, tmp_path, release_icinde, ilk_tahminde=None):
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef

    gercek_tahmin = __import__("servers.ai_router", fromlist=["x"])._predict_and_drive
    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    try:
        monkeypatch.setattr(ns.air, "_predict_and_drive", gercek_tahmin)
        monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "predict", _BozulanKedi(ilk_tahminde))
        monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)

        class _Kamera:
            def __init__(self, *a, **k):
                pass

            def isOpened(self):  # noqa: N802
                return True

            def read(self):
                return True, np.zeros((8, 8, 3), dtype=np.uint8)

            def release(self):
                release_icinde()

        monkeypatch.setattr(ns.air.cv2, "VideoCapture", _Kamera)
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns, organ=2)
            assert r.status_code == 200, r.text[:200]
            assert ap.bekle(lambda: bool(ap.calisan(ns)), 5), "aparat: döngü sürmedi"
            assert ap.bekle(lambda: ap.dongu_bitir(ns.air, 0.01) == 0 and not ns.air._ai_loop_active, 8.0)
    finally:
        ns.air._ai_loop_active = False
        ns.geri()


def test_KRITIK_dongu_ciktiktan_SONRA_kurulan_analiz_baglami_teardownda_SILINMEZ(monkeypatch, tmp_path):
    from servers import efield_live

    efield_live.set_context([])
    kuruldu = []

    def _yeni_analiz():
        if not kuruldu:  # release yalnız döngü ÇIKTIKTAN sonra çağrılır → bu bağlam "yeni"dir
            efield_live.set_context([{"centroid_cabin_mm": [10.0, 20.0, 30.0]}], model="fantom")
            kuruldu.append(efield_live.get_context())

    try:
        _dongu_kos(monkeypatch, tmp_path, _yeni_analiz)
        assert kuruldu, "aparat: yarış penceresinde bağlam kurulmadı"
        ctx = efield_live.get_context()
        assert ctx is not None and ctx.get("model") == "fantom", (
            "biten döngünün geç kapanışı YENİ analizin E bağlamını sildi"
        )
    finally:
        efield_live.set_context([])


def test_KARSIT_dongunun_KENDI_doneminin_baglami_teardownda_TEMIZLENIR(monkeypatch, tmp_path):
    """Döngü SÜRERKEN kurulmuş (eski) bağlam kapanışta yine temizlenir — sonraki seansa sızmaz (D1.61). (Seans başlangıcı
    bağlamı zaten temizler — `seans_basladi` — bu yüzden bağlam döngünün ilk tahmininde kurulur.)"""
    from servers import efield_live

    efield_live.set_context([])
    try:
        _dongu_kos(
            monkeypatch,
            tmp_path,
            lambda: None,
            ilk_tahminde=lambda: efield_live.set_context([{"centroid_cabin_mm": [1.0, 2.0, 3.0]}], model="fantom"),
        )
        assert efield_live.get_context() is None, "döngünün kendi döneminin bağlamı kapanışta temizlenmedi"
    finally:
        efield_live.set_context([])
