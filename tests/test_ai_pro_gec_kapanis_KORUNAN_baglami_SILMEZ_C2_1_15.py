# -*- coding: utf-8 -*-
"""C2-1.15 (2-C inceleme, A1) — O-A2-K.1 ürün yarısı: biten döngünün geç kapanışı, YENİ seansın `seans_basladi`la KORUDUĞU
bağlamı siliyor (nesil sayacı korumada ARTMIYOR).

`efield_live.seans_basladi("ai_pro", m)` aynı modelin (fantom/petri) araştırma AI Pro seansında analiz bağlamını KORUR (D1.61) — ama
nesli artırmaz. Eski döngü (L1) çıkış anında nesil N'yi almış, kapanışının `_ai_loop_lock` bölümünü geçmiş (yeni döngü yok →
atlanmaz) ve ESP STOP yayınındayken (üretimde ~1 sn) operatör yeni bir fantom AI Pro seansı (S2) başlatırsa: S2 bağlamı korur
(nesil hâlâ N) → L1 kapanışı `temizle_degismediyse(N)` → S2'nin bağlamını SİLER (S2'nin E barı boş — O-A2-K.1'in kapattığı
kusurun korunan-bağlam kolu). GERÇEK `_ai_pro_loop` (sahte kamera — gerçek kamera AÇILMAZ); S2'nin bağlam etkisi ürünün kendi
`seans_basladi`sıyla, L1'in ESP STOP yayınının içinde kurulur (yarış penceresi, belirlenimci).
KARŞIT (O-A2-K.1 kapısında da var): S2 yoksa L1 döneminin bağlamı kapanışta temizlenir.
"""

from __future__ import annotations

import numpy as np


def _dongu_kos(monkeypatch, tmp_path, esp_stop_icinde):
    import ai_pro_aparati as ap
    from kayitci_donanim import gercek_hc
    from servers import ai_pro_hedef, efield_live

    gercek_tahmin = __import__("servers.ai_router", fromlist=["x"])._predict_and_drive
    ns = ap.kur(monkeypatch, tmp_path, dongu_noop=False)
    try:
        monkeypatch.setattr(ns.air, "_predict_and_drive", gercek_tahmin)
        ilk = []

        def _tahmin(self, *a, **k):
            if not ilk:  # L1 SÜRERKEN aynı modelin analiz bağlamı (fantom) kurulu
                efield_live.set_context([{"centroid_cabin_mm": [1.0, 2.0, 3.0]}], model="fantom")
                ilk.append(1)
            return [0.3] * 7, [0.0] * 7, 1.0

        monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "predict", _tahmin)
        monkeypatch.setattr(ai_pro_hedef.KediSaglayici, "yukle", lambda self: None)

        class _Kamera:
            def __init__(self, *a, **k):
                pass

            def isOpened(self):  # noqa: N802
                return True

            def read(self):
                return True, np.zeros((8, 8, 3), dtype=np.uint8)

            def release(self):
                pass

        monkeypatch.setattr(ns.air.cv2, "VideoCapture", _Kamera)
        gercek_yayin = ns.api._mqtt_publish

        def _yayin(topic, payload):
            if str((payload or {}).get("command_id", "")).startswith("ai_stop"):
                esp_stop_icinde()
            return gercek_yayin(topic, payload)

        monkeypatch.setattr(ns.api, "_mqtt_publish", _yayin)
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            _pid, r = ap.onayli_baslat(ns, organ=2)
            assert r.status_code == 200, r.text[:200]
            assert ap.bekle(lambda: bool(ap.calisan(ns)), 5), "aparat: döngü sürmedi"
            assert ap.bekle(lambda: bool(ilk), 5), "aparat: L1 döneminde bağlam kurulmadı"
            assert ap.bekle(lambda: ap.dongu_bitir(ns.air, 0.01) == 0 and not ns.air._ai_loop_active, 8.0)
    finally:
        ns.air._ai_loop_active = False
        ns.geri()


def test_KRITIK_C2_1_15_eski_dongunun_gec_kapanisi_YENI_seansin_KORUDUGU_baglami_silmez(monkeypatch, tmp_path):
    from servers import efield_live

    efield_live.set_context([])
    s2 = []

    def _s2_basladi():
        if not s2:  # L1 kapanışı ESP STOP yayınında — S2 (aynı model, araştırma AI Pro) başlar ve bağlamı KORUR
            efield_live.seans_basladi("ai_pro", "fantom")
            s2.append(efield_live.get_context())

    try:
        _dongu_kos(monkeypatch, tmp_path, _s2_basladi)
        assert s2 and s2[0] is not None, "aparat: S2 başlangıcında bağlam korunmalıydı (D1.61)"
        assert efield_live.get_context() is not None, (
            "eski döngünün geç kapanışı YENİ seansın KORUDUĞU E bağlamını sildi"
        )
    finally:
        efield_live.set_context([])


def test_KARSIT_C2_1_15_S2_yoksa_L1_doneminin_baglami_TEMIZLENIR(monkeypatch, tmp_path):
    from servers import efield_live

    efield_live.set_context([])
    try:
        _dongu_kos(monkeypatch, tmp_path, lambda: None)
        assert efield_live.get_context() is None
    finally:
        efield_live.set_context([])
