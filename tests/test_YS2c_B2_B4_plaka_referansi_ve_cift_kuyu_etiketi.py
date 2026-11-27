# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""YS2 c · B2 + YS2 d · B4 (YG0 25-11, `DENETIM\\YAYIN-GUNU.md` YG0 b).

B2 (DÜŞÜK, kullanılabilirlik): T-8 seansından sonra plaka yeni yere konunca yeni hazırlık "Plaka seansın başındaki yerinden kaydı
(38,3 mm) — sürülmedi" deyip 2 dk sonra "Konumlandırma tamamlanamadı" ile duruyordu: süresi dolan seansın mühürlü ODAK ayarı ve sabit
numune referansı (seans başı plaka konumu) TEMİZLENMİYORDU (yalnız `/ai/pro/stop` ve "Hazırlığı durdur" temizliyordu) → hazırlık
"seans" gibi eski referansla kıyaslıyordu; "Yeniden Konumla" da sıfırlamıyordu. GÜVENLİ YÖN KORUNUR: seans sürerken referans KALIR —
gerçek kayma hâlâ STOP (T-8), "Yeniden Konumla" onu aşamaz.
B4 (DÜŞÜK): hedef listesinde aynı kuyu etiketi iki kez (C2 ×2 …) — takip önceki karenin etiketini taşıyıp CV'nin bu karede başka kuyuya
verdiği etiketle çakışıyordu.
APARAT: gerçek onay akışı + gerçek döngü + gerçek HC (YS2 a düzeneği); hazırlık / kalibrasyon uçları TestClient.
"""

from __future__ import annotations

import time

import ai_pro_aparati as ap
import pytest
from test_YS2a_B1_ai_pro_seans_KAYDI_gercek_surus import _dongu_bitmesini_bekle, _ortam

REFERANS = [{"etiket": "D3", "x": 1.0, "y": 2.0}]
ODAK = {"doz_mT": 1.43, "kip": "KUYUCUK", "frek_hz": 100.0}


def _referansli(sag) -> None:
    sag.odak_ayari = {"doz_mT": 1.43, "kip": "KUYUCUK", "hedef_etiket": "Kuyu D3", "frek_hz": 100.0}
    sag._sabit_izgara = [dict(k) for k in REFERANS]


@pytest.fixture
def petri(monkeypatch):
    from servers import ai_pro_hedef

    s = ai_pro_hedef.saglayici_al("petri")
    monkeypatch.setattr(s, "odak_ayari", None, raising=False)
    monkeypatch.setattr(s, "_sabit_izgara", None, raising=False)
    return s


def test_KRITIK_B2_SURESI_DOLAN_seans_odak_ayarini_ve_PLAKA_REFERANSINI_birakir(monkeypatch, tmp_path, petri):
    from kayitci_donanim import gercek_hc
    from servers import ai_approval

    ns, _durum = _ortam(monkeypatch, tmp_path, pencere_s=30.0, mod="bulundu")
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(ns.api.state, "hardware", hc)
            ns.hc = hc
            rec = ai_approval.create(
                "ai_pro",
                {"organ_id": 1, "duration_minutes": 1, "model": "petri", "odak": dict(ODAK), "target_label": "Kuyu D3"},
            )
            ai_approval.approve(rec["id"], "hekim@test.local")
            r = ns.c.post("/api/ai/pro/start", json={"proposal_id": rec["id"], "client_id": ""})
            assert r.status_code == 200, r.text[:300]
            assert ap.bekle(lambda: bool(ap.calisan(ns)), 6), "aparat: döngü sürmedi"
            assert petri.odak_ayari is not None, "aparat: mühürlü ODAK ayarı kurulmadı"
            petri._sabit_izgara = [dict(k) for k in REFERANS]  # seansın ilk doğrulanan ızgarası (T-8 referansı)
            ns.air._ai_started_at = time.monotonic() - 60.0  # süre doldu (döngünün kendi sayacı)
            assert _dongu_bitmesini_bekle(8.0), "döngü süre dolumunda bitmedi"
        assert petri.odak_ayari is None, "süresi dolan seansın mühürlü ODAK ayarı kaldı (yeni hazırlık 'seans' sanılır)"
        assert petri._sabit_izgara is None, "süresi dolan seansın plaka referansı yeni hazırlığa TAŞINDI (B2)"
    finally:
        ap.dongu_bitir(ns.air)
        ns.air._ai_loop_active = False
        ns.geri()


@pytest.fixture
def ns(monkeypatch, tmp_path):
    o = ap.kur(monkeypatch, tmp_path)
    try:
        yield o
    finally:
        ap.dongu_bitir(o.air)
        o.geri()
        o.c.close()


def test_KRITIK_B2_yeni_HAZIRLIK_onceki_referansi_TASIMAZ(ns, monkeypatch, petri):
    _referansli(petri)
    monkeypatch.setattr(ns.air, "_ai_hazirlik_active", True)  # önizleme çalışıyor → iş parçacığı açılmaz (yalnız ayar)
    monkeypatch.setattr(ns.air, "_ai_hazirlik_thread", None)
    r = ns.c.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 11, "model": "petri"})
    assert r.status_code == 200, r.text[:300]
    assert petri._sabit_izgara is None and petri.odak_ayari is None, "yeni hazırlık önceki seansın referansını taşıdı"


def test_KRITIK_B2_seans_YOKKEN_YENIDEN_KONUMLA_referansi_sifirlar(ns, petri):
    _referansli(petri)
    r = ns.c.post("/api/ai/pro/calibrate", json={})
    assert r.status_code == 200, r.text[:300]
    assert petri._sabit_izgara is None and petri.odak_ayari is None
    assert ns.air._ai_relocalize is True


def test_KARSIT_B2_seans_SURERKEN_YENIDEN_KONUMLA_referansa_DOKUNMAZ_T8_korunur(ns, petri):
    """Mühürlü seans sürerken "Yeniden Konumla" referansı SIFIRLAMAZ — sıfırlasaydı kaydırılan plaka yeni yerinde referans olur,
    T-8 (gerçek kayma STOP) düğmeyle aşılırdı."""
    _referansli(petri)
    ap.muhurlu_seans_yaz(ns.api, model="petri")
    r = ns.c.post("/api/ai/pro/calibrate", json={})
    assert r.status_code == 200, r.text[:300]
    assert petri._sabit_izgara == REFERANS and petri.odak_ayari is not None, (
        "seans sürerken plaka referansı sıfırlandı (T-8 aşıldı)"
    )


def test_KARSIT_B2_dongu_SURERKEN_YENIDEN_KONUMLA_referansa_DOKUNMAZ(ns, monkeypatch, petri):
    _referansli(petri)
    monkeypatch.setattr(ns.air, "_ai_loop_active", True)
    r = ns.c.post("/api/ai/pro/calibrate", json={})
    assert r.status_code == 200, r.text[:300]
    assert petri._sabit_izgara == REFERANS


# ── B4 ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _aday(px, label):
    x, y = px
    return {
        "px": (float(x), float(y)),
        "bbox": [x - 10, y - 10, 20, 20],
        "label": label,
        "reliability": 0.9,
    }  # (x, y, w, h)


def test_KRITIK_B4_takip_etiketi_CV_etiketiyle_CAKISINCA_ayni_kuyu_IKI_KEZ_listelenmez():
    from servers import ai_pro_hedef

    sag = type(ai_pro_hedef.saglayici_al("petri"))()
    bir = sag._kimlik_ata([_aday((100, 100), "C2"), _aday((200, 100), "C3")])
    assert [a["label"] for a in bir] == ["C2", "C3"]
    kimlik_c2 = next(a["id"] for a in bir if a["label"] == "C2")
    # Izgara kaydı: (102,100)'deki kuyu (takipte C2) bu karede CV'ce "C1"; (300,100)'deki YENİ kuyu CV'ce "C2".
    iki = sag._kimlik_ata([_aday((102, 100), "C1"), _aday((300, 100), "C2")])
    etiketler = [a["label"] for a in iki]
    assert len(etiketler) == len(set(etiketler)), f"aynı karede yinelenen kuyu etiketi: {etiketler}"
    takipli = next(a for a in iki if a["px"] == (102.0, 100.0))
    assert takipli["id"] == kimlik_c2, "kimlik (onay mührü) değişti — yalnız etiket düzelmeli"
    assert takipli["label"] == "C1" and takipli["etiketGosterim"], takipli


def test_KARSIT_B4_cakisma_YOKSA_takip_etiketi_KORUNUR():
    from servers import ai_pro_hedef

    sag = type(ai_pro_hedef.saglayici_al("petri"))()
    sag._kimlik_ata([_aday((100, 100), "C2")])
    iki = sag._kimlik_ata([_aday((102, 100), "C1"), _aday((300, 100), "D5")])
    assert sorted(a["label"] for a in iki) == ["C2", "D5"], "çakışma yokken mühürlü takip etiketi değişti"


def test_B4_CV_etiketi_de_kullaniliyorsa_DOKUNULMAZ():
    from servers import ai_pro_hedef

    adaylar = [
        {"label": "C2", "cv_label": "C3"},
        {"label": "C2"},
        {"label": "C3"},
    ]
    ai_pro_hedef.PetriSaglayici._yinelenen_etiketleri_coz(adaylar)
    assert [a["label"] for a in adaylar] == ["C2", "C2", "C3"]
