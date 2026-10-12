# -*- coding: utf-8 -*-
"""AII-2.2 (AI incelemesi, A2) — PEMF tüketim kapısı BOZUK / beklenmeyen `warnings` biçiminde de engelleyici kodu TANIR.

KUSUR [ÖLÇTÜM K1.1]: `pemf_kapisi.uyari_kodlari` (i) `warnings` bir DİZE gelirse onu karakter karakter gezer (kodlar
"l", "a", "y"… olur) → `layout_mismatch` tanınmaz ve sonuç SÜRÜLEBİLİR; (ii) büyük harfli kod (`LAYOUT_MISMATCH: …`)
tanınmaz; (iii) ilk parça kodsuz serbest metinse (`"bir sey oldu: layout_mismatch: …"`) `break` iç içe kodu hiç okumaz;
(iv) bytes uyarı tanınmaz. Modülün kendi iddiası: "FAIL-CLOSED: alan YOKSA (… bozuk yanıt) geçerli SAYILMAZ". Bugünkü
üreticiler (hocanın v2/v3 dataclass'ı) liste + küçük harf verdiği için canlıda tetiklenmedi [ÖLÇTÜM K1.2: 24 biçimin 24'ü
tanındı]; bu kapı GPU servisi / gelecekteki üretici / JSON yolundaki biçim kaymasına karşıdır.
Yol: tests/test_pemf_kapisi_BOZUK_uyari_bicimi_FAIL_CLOSED_AII22.py"""

from __future__ import annotations

import numpy as np
import pytest


class _Sonuc:
    def __init__(self, **k):
        self.success, self.error, self.method = True, None, "aruco_pnp"
        self.pemf_valid, self.reliable, self.warnings = True, True, []
        for a, v in k.items():
            setattr(self, a, v)


BOZUK = {
    "dize": "layout_mismatch: referans yerlesime kayit hatasi 9.1 mm",
    "dize_yeniden_cekim": "oblique_view: olcek degisimi x1.34",
    "buyuk_harf": ["LAYOUT_MISMATCH: referans yerlesime kayit hatasi"],
    "serbest_metin_oneki": ["kayit denetimi: layout_mismatch: referans yerlesime kayit hatasi"],
    "bytes": [b"control_cancer_missed: B2 (blue=0.001)"],
}


@pytest.mark.parametrize("model", ["fantom", "petri"])
@pytest.mark.parametrize("ad", sorted(BOZUK))
def test_KRITIK_bozuk_uyari_biciminde_SURULEMEZ(ad, model):
    from ai_hub.cv_ortak import pemf_kapisi as pk

    k = pk.degerlendir(_Sonuc(warnings=BOZUK[ad]), model=model)
    assert k["surulebilir"] is False, (
        f"{ad}: engelleyici / yeniden-çekim kodu tanınmadı, sonuç SÜRÜLEBİLİR: {k['uyari_kodlari']}"
    )
    assert set(k["nedenler"]) & {"layout_mismatch", "oblique_view", "control_cancer_missed"}, k["nedenler"]


def test_KRITIK_saglayici_DIZE_uyarili_kareyi_LOKALIZE_saymaz(monkeypatch):
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air

    class _Hat:
        def __init__(self, cfg, **kw):
            self._predictor = None

        def process_image(self, frame, achieved_B=None, duty_sum=None):
            r = _Sonuc(warnings=BOZUK["dize"], pemf_source="aruco", coord_frame="cabin_aruco", layout={}, mm_per_px=0.0)
            b = type("B", (), {})()
            b.centroid_px, b.centroid_cabin_mm, b.organ_id, b.area_px = (10.0, 10.0), (-40.0, 0.0, 0.0), 1, 100
            b.bbox_px, b.E_cancer, b.E_healthy, b.tumor_id = (0, 0, 20, 20), 0.9, 0.1, ""
            r.tumor_regions, r.phantom_detection = [b], {"primary": {"solidity": 0.9, "n_blue_inside": 5}}
            return r, {}

        def render_panels(self, *a, **k):
            return {}

    class _Cfg:
        class phantom:  # noqa: N801
            achieved_B, duty_sum = 0.001, 2.4

    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, y: {"cls": _Hat, "cfg": _Cfg(), "predictor": None})
    monkeypatch.setattr(hedef, "hedef_kabin_disi_nedeni", lambda *a: "")
    lz = hedef.FantomSaglayici().localize(np.zeros((8, 8, 3), np.uint8), 0)[0]
    assert lz is False, "warnings DİZE geldi (layout_mismatch) — kare LOKALİZE sayıldı, kapı fail-open"


def test_KARSIT_gecerli_bicim_ve_aciklama_parcalari():
    from ai_hub.cv_ortak import pemf_kapisi as pk

    gecerli = _Sonuc(
        warnings=["pemf_axis_sign_assumed: fantom merkezi: u->+y", "layout_unregistered: kimlikler KONUM SIRALI"]
    )
    assert pk.degerlendir(gecerli, model="fantom")["surulebilir"] is True
    assert pk.uyari_kodlari(["ring_unavailable: ring_partial: halkanin %31'i"]) == ["ring_unavailable", "ring_partial"]
    assert pk.uyari_kodlari(None) == [] and pk.uyari_kodlari([]) == []
    # yanıt alanı da DİZEYİ karakterlere bölmez (AI Hub kutusu)
    assert pk.yanit_alanlari(_Sonuc(warnings=BOZUK["dize"]), model="fantom")["warnings"] == [BOZUK["dize"]]
