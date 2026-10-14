# -*- coding: utf-8 -*-
"""AI1.K2 — kedi AI Pro `ood` kapısı KÖR DEĞİL; hocanın sentetik testi (6 organın hepsi em_kedi eğitim aralığı DIŞI) önerilmez.

KAYNAK: hoca kedi organ v2 (`inference_cat_organ_v2.py` `stage_em`, `beklenen_sonuclar/synthetic_aruco_test/organlar.csv`; zip SHA-256
0285b1d969f8): hocanın hattında sentetik karenin 6 organı kabin cm → mm ile em_kedi'ye girer ve 6'sı da `xai_train_ref.npz` aralığı
DIŞINDA (`em_egitim_disi=6`); hoca uyarısı: "Kedi kabin çerçevesi ile EM eğitim çerçevesinin aynı olduğu DOĞRULANMADI".

ÖLÇÜLEN (2026-10-11, `DUZELTME-AI1.md` K2): kusur YOK — kalıcı kapı (önce-kırmızı yerine mutasyon kanıtı).
  * gerçek sentetik kare guii canlı hattında (paketli kabin yapılandırması, perspektif çözümü): 6 organın 6'sı "kabin DIŞI hedef"
    (x ≈ 600–680 mm) diye REDDEDİLİR → `/propose` 409; hocanın kendi koordinatları (y ≈ -350…-480 mm) da kabin dışı → 409.
  * kabin içi ızgarada (25 mm) GERÇEK eğitim referansına göre dışarıdaki 5187 noktanın 5187'si `ood` (KÖR 0); içerideki 6720
    noktanın 2436'sı da `ood` (64 satırlık arka plan aralığı eğitim aralığından dar — fazla işaret; sahibe, değiştirilmedi).
⚠️ Y49: `ood` yalnız GÖSTERİM/İZ — sürüş değişmez (yeni red ya da kıskaç YOK, Ö.4-Y9); bu dosya bunu da kilitler.
"""

from __future__ import annotations

import numpy as np
import pytest

# Hocanın beklenen sonucu: synthetic_aruco_test/organlar.csv — organ: (kabin_x_cm, kabin_y_cm, kabin_z_cm, guvenilirlik)
HOCA_SENTETIK = {
    1: (-21.68, -38.37, -3.55, 0.665),
    2: (-20.62, -46.93, 4.06, 0.583),
    3: (-25.23, -34.85, 1.2, 0.622),
    4: (-4.6, -48.06, 0.83, 0.342),
    5: (-19.51, -39.61, 1.14, 0.675),
    6: (-13.23, -42.84, 0.38, 0.668),
}


@pytest.fixture
def ortam(monkeypatch):
    from kabin_test_geometrisi import kedi_yukleyicisini_sabitle
    from servers import ai_approval
    from servers import ai_pro_hedef as aph
    from servers import ai_router as air

    from ai_hub.em_kedi import inference_em_kedi as iek

    # TD4: senaryo "kabin içi ama eğitim dışı" bölgeyi sabit test kabininde (65×50×50) örnekler.
    kedi_yukleyicisini_sabitle(monkeypatch)
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(air, "_ai_hedef_modeli", "kedi")
    monkeypatch.setattr(air, "_predict_and_drive", lambda x, y, z, oid: ([0.5] * 7, [0.0] * 7, 0.01))
    monkeypatch.setattr(aph.KediSaglayici, "xai_sensitivity", lambda self, *a, **k: None)
    monkeypatch.setattr(ai_approval, "_store", {})
    monkeypatch.setattr(air, "_ai_organ_cache", dict(air._ai_organ_cache))
    er = iek.xai_egitim_ref()
    return air, aph, aph.saglayici_al("kedi"), er["min"][:3], er["max"][:3]


def _lokalize(air, sag, monkeypatch, organs, oid):
    """Gerçek `KediSaglayici.localize` → gerçek `_extract_organ_target` (kabin denetimi + kıskaç) → `_ood_isaretle`; yalnız cat_organ
    çıktısı verilir. Ardından üç lokalizasyon yolunun yazdığı cache alanları yazılır (`/propose` oradan okur)."""
    monkeypatch.setattr(air, "_localize_organ_cpu", lambda frame, o: air._extract_organ_target(organs, o, None))
    r = sag.localize("kare", oid)
    air._ai_organ_cache.update(
        {
            "x_mm": r[1],
            "y_mm": r[2],
            "z_mm": r[3],
            "reliability": r[4],
            "localized": r[0],
            "at": __import__("time").time(),
            "organ_id": oid,
            "kedi_var": True,
            "model": "kedi",
            **air._saglayici_cache_alanlari(),
        }
    )
    return r


def _propose(air, oid):
    from fastapi import HTTPException

    try:
        return 200, air.propose_ai_pro(None, air.AiProProposePayload(organ_id=oid, model="kedi"))
    except HTTPException as e:
        return e.status_code, str(e.detail)


def test_KRITIK_K2_kabin_ici_EGITIM_DISI_her_hedef_ood_ve_surus_DEGISMEZ(ortam, monkeypatch):
    air, aph, sag, lo, hi = ortam
    yari = aph.kabin_yari_boyut_mm()
    kor, n_dis = [], 0
    for x in np.arange(-yari[0], yari[0] + 0.1, 50.0):
        for y in np.arange(-yari[1], yari[1] + 0.1, 50.0):
            for z in np.arange(-yari[2], yari[2] + 0.1, 50.0):
                p = np.array([x, y, z])
                if not np.any((p < lo) | (p > hi)):
                    continue
                n_dis += 1
                r = _lokalize(air, sag, monkeypatch, {2: {"coord_cabin_cm": list(p / 10.0), "reliability": 0.6}}, 2)
                beklenen = tuple(float(np.clip(v, -300.0, 300.0)) for v in p)
                assert r[0] is True and tuple(r[1:4]) == pytest.approx(beklenen), (
                    f"Y49: işaret sürüşü DEĞİŞTİRMEMELİ ({p} → {r[:4]})"
                )
                if not sag.son_lokalizasyon_meta().get("ood"):
                    kor.append(tuple(p))
    assert n_dis > 100, "ızgara eğitim dışı bölgeyi örneklemiyor"
    assert not kor, (
        f"kabin İÇİNDE ama em_kedi GERÇEK eğitim aralığı ({lo}..{hi} mm) DIŞINDAKİ {len(kor)}/{n_dis} hedef `ood` işaretlenmedi "
        f"(ilk: {kor[:4]}) — onay ekranı 'eğitim aralığı dışı' uyarısını göstermez"
    )


def test_KRITIK_K2_hoca_sentetik_6_organ_ONERILMEZ_surulmez(ortam, monkeypatch):
    air, aph, sag, lo, hi = ortam
    for oid, (x, y, z, guven) in HOCA_SENTETIK.items():
        mm = np.array([x, y, z]) * 10.0
        assert np.any((mm < lo) | (mm > hi)), f"organ {oid}: hocanın noktası eğitim aralığında — test verisi bayat"
        r = _lokalize(air, sag, monkeypatch, {oid: {"coord_cabin_cm": [x, y, z], "reliability": guven}}, oid)
        assert r[0] is False, (
            f"organ {oid}: hocanın eğitim dışı (ve kabin dışı) hedefi {mm} mm lokalize sayıldı → sürülür"
        )
        assert not sag.son_lokalizasyon_meta().get("ood"), "lokalize edilmeyen hedefte bayat `ood` kaldı"
        durum, yanit = _propose(air, oid)
        assert durum == 409, f"organ {oid}: kabin dışı hedef için öneri ÜRETİLDİ: {yanit}"


def test_KRITIK_K2_propose_EGITIM_DISI_hedefte_ood_TRUE_tasir(ortam, monkeypatch):
    """Kabin İÇİ, eğitim DIŞI (z = 200 mm > eğitim üst sınırı) hedef önerilir ve `/propose` `meta.ood` TRUE; konum aynen."""
    air, aph, sag, lo, hi = ortam
    p = (0.0, 0.0, 200.0)
    assert p[2] > hi[2] and abs(p[2]) <= aph.kabin_yari_boyut_mm()[2], (
        "senaryo varsayımı bozuldu (eğitim/kabin sınırı değişti)"
    )
    _lokalize(air, sag, monkeypatch, {2: {"coord_cabin_cm": [v / 10.0 for v in p], "reliability": 0.6}}, 2)
    durum, yanit = _propose(air, 2)
    assert durum == 200, yanit
    assert yanit["meta"]["ood"] is True, f"eğitim dışı hedefin önerisinde `ood` false: {yanit['meta']}"
    assert (yanit["meta"]["x_mm"], yanit["meta"]["y_mm"], yanit["meta"]["z_mm"]) == pytest.approx(p), (
        "Y49: konum değişti"
    )
