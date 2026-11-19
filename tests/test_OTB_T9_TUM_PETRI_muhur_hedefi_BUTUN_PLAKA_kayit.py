# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""OTB T-9 [KRİTİK] (ODM tezgâhı 19-11 12:58, seans 36): sahip onay penceresinde TÜM PETRİ 1,40 seçip "Yeniden hesapla" + "Onayla ve
Başlat" yaptı; geçmiş kartı hedef "Kuyu C2" dedi.

KOD YOLU (ölçüldü): pencere kip değişince `kuyu` GÖNDERMEZ → `/propose` otomatik (0) yolunda lokalizasyonun SEÇTİĞİ kuyuyu (Y143) mühürlüyordu:
`organ_id` = o kuyunun kalıcı kimliği, `target_label` = "Kuyu C2", `otomatik_secim` işareti. Sürülen PLAN mühürdeki `odak.kip`ten gelir
(TUM_PETRI — `oneri.kip_girdisi` hedef etiketini kullanmaz) → doz DOĞRU sürüldü; YANLIŞ olan: kayıt (`/start` `kayit.hedef` = mühür etiketi),
canlı kart / onay penceresinin hedef adı ("yalnız «Kuyu C2» sürülür") ve döngünün TEK kuyuya bağlanması (D1.60: o kuyu karede görülmezse
"hedef yok" → TÜM PETRİ sürüşü kesilir).
SÖZLEŞME: TÜM PETRİ önerisinde mühür hedefi BÜTÜN PLAKA — `organ_id` 0, `target_label` "Tüm petri" (VERİ, TR), otomatik seçim işareti YOK,
kuyu E alanları boş; `kuyu` alanı yok sayılır (tek kuyu KUYUCUK kipindedir). Gösterim iki dilde. KUYUCUK otomatik yolu AYNEN (Y143).
ODAK planı sahtelenir (fizik `test_ODK_*`); `/start`ta seans kaydı ve döngü iş parçacığı EN ALT katta yakalanır.
"""

import time

import pytest
from fastapi.testclient import TestClient

C2 = {"id": 7, "label": "Kuyu C2", "x": 10.0, "y": -150.0, "z": 20.0, "reliability": 0.95, "pxn": [0.3, 0.5]}
C6 = {"id": 11, "label": "Kuyu C6", "x": 60.0, "y": -150.0, "z": 25.0, "reliability": 0.9, "pxn": [0.6, 0.5]}


@pytest.fixture()
def o(monkeypatch):
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air
    import servers.api_server as apis

    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    monkeypatch.setattr(hedef, "duzlem_surus_engeli", lambda _s: None)
    planlar = []

    def _plan(sag, konum, hedef_id, doz, kip="", frek=None):
        planlar.append({"hedef_id": hedef_id, "etiket": konum.get("target_label"), "kip": kip})
        return {
            "kip": kip or "KUYUCUK",
            "doz_mT": float(doz or 0.6),
            "tavan_mT": 1.8,
            "duty": [0.2] * 7,
            "faz": [0.0] * 7,
            "frek_hz": 100.0,
        }

    monkeypatch.setattr(hedef, "odak_plani", _plan)
    snap = dict(air._ai_organ_cache)
    air._ai_organ_cache.update(
        {
            "localized": True,
            "organ_id": 0,  # önizleme OTOMATİK hedefle lokalize etti
            "model": "petri",
            "at": time.time(),
            "x_mm": C2["x"],
            "y_mm": C2["y"],
            "z_mm": C2["z"],
            "reliability": 0.95,
            "kosulsuz": False,
            "targets": [C2, C6],
            "secili_id": 7,
            "target_label": "Kuyu C2",
            "e_cancer": 12.0,
            "e_healthy": 3.0,
        }
    )
    petri = hedef.SAGLAYICILAR["petri"]
    eski_ayar = petri.odak_ayari
    yield TestClient(apis.app), planlar
    petri.odak_ayari = eski_ayar
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap)


def _oner(c, dil="tr", **ek):
    return c.post(
        "/api/ai/pro/propose",
        json={"organ_id": 0, "model": "petri", "duration_minutes": 5, **ek},
        headers={"X-PEMF-Dil": dil},
    )


@pytest.mark.parametrize("dil,gosterim", [("tr", "Tüm petri"), ("en", "Whole well plate")])
def test_KRITIK_T9_TUM_PETRI_onerisi_MUHUR_hedefi_BUTUN_PLAKA_tek_kuyu_DEGIL(o, dil, gosterim):
    c, planlar = o
    r = _oner(c, dil=dil, odak_kip="TUM_PETRI", doz_mT=1.4)
    assert r.status_code == 200, r.text
    j = r.json()
    sp, me = j["specs"], j["meta"]
    assert sp["target_label"] == "Tüm petri", f"TÜM PETRİ mührü tek kuyunun etiketini taşıyor: {sp['target_label']!r}"
    assert sp["organ_id"] == 0, f"TÜM PETRİ döngüsü tek kuyunun kimliğine bağlandı: {sp['organ_id']}"
    assert not me.get("otomatik_secim"), "TÜM PETRİ penceresi 'yalnız bu kuyu sürülür' diyecek (otomatik seçim işareti)"
    assert sp["e_cancer"] is None and sp["e_healthy"] is None, (
        "tek kuyunun E değeri bütün plakanın onay ekranına taşındı"
    )
    assert sp["odak"]["kip"] == "TUM_PETRI" and planlar[-1] == {
        "hedef_id": 0,
        "etiket": "Tüm petri",
        "kip": "TUM_PETRI",
    }
    assert j["hedefGosterim"] == gosterim


def test_KRITIK_T9_TUM_PETRI_kuyu_alani_YOK_SAYILIR_gorulmeyen_kuyu_409_DEGIL(o):
    c, _ = o
    for kuyu in ("C6", "B1"):
        r = _oner(c, odak_kip="TUM_PETRI", doz_mT=1.4, kuyu=kuyu)
        assert r.status_code == 200, (kuyu, r.text)
        assert (r.json()["specs"]["organ_id"], r.json()["specs"]["target_label"]) == (0, "Tüm petri"), kuyu


def test_KRITIK_T9_onizlemede_SECILI_kuyu_varken_TUM_PETRI_yine_BUTUN_PLAKA(o):
    """Önizleme listesinde kuyu seçilmişse istek o kimlikle gelir (`organ_id` 7); TÜM PETRİ mührü yine 0 (döngü tek kuyuya bağlanmaz)."""
    import servers.ai_router as air

    c, planlar = o
    air._ai_organ_cache["organ_id"] = 7
    r = c.post("/api/ai/pro/propose", json={"organ_id": 7, "model": "petri", "odak_kip": "TUM_PETRI", "doz_mT": 1.4})
    assert r.status_code == 200, r.text
    assert (r.json()["specs"]["organ_id"], r.json()["specs"]["target_label"]) == (0, "Tüm petri")
    assert planlar[-1]["hedef_id"] == 0


def test_T9_KUYUCUK_otomatik_yolu_AYNEN_Y143_secili_kuyu_muhurlenir(o):
    c, planlar = o
    r = _oner(c, odak_kip="KUYUCUK", doz_mT=0.6)
    assert r.status_code == 200, r.text
    sp = r.json()["specs"]
    assert (sp["organ_id"], sp["target_label"]) == (7, "Kuyu C2") and r.json()["meta"].get("otomatik_secim")
    assert planlar[-1] == {"hedef_id": 7, "etiket": "Kuyu C2", "kip": "KUYUCUK"}


def test_KRITIK_T9_baslatma_KAYIT_hedefi_Tum_petri_dongu_BUTUN_PLAKAYI_izler(o, monkeypatch):
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air
    import servers.api_server as apis
    from servers import ai_approval
    from utils import kabin_kamerasi

    c, _ = o
    pid = _oner(c, odak_kip="TUM_PETRI", doz_mT=1.4).json()["proposalId"]
    ai_approval.approve(pid, "arastirmaci@test.local")
    kayitlar, donguler = [], []
    monkeypatch.setattr(kabin_kamerasi, "secili_kamera", lambda: 0)
    monkeypatch.setattr(apis, "_kayit_db_hazir", lambda: (True, ""))
    monkeypatch.setattr(apis, "start_ai_session", lambda *a, **k: kayitlar.append(k))
    monkeypatch.setattr(air, "_ai_hazirlik_durdur_ic", lambda: None)
    monkeypatch.setattr(air, "_ai_pro_loop", lambda muhur: donguler.append(dict(muhur)))
    try:
        s = c.post("/api/ai/pro/start", json={"proposal_id": pid})
        assert s.status_code == 200, s.text
        assert kayitlar and kayitlar[-1]["kayit"]["hedef"] == "Tüm petri", kayitlar
        assert kayitlar[-1]["onay_hedefi"] == 0 and s.json()["organId"] == 0
        air._ai_thread.join(timeout=5)
        assert donguler and donguler[-1]["hedef"] == 0, "döngü mührü tek kuyuya bağlı"
        petri = hedef.SAGLAYICILAR["petri"]
        assert petri.odak_ayari["kip"] == "TUM_PETRI" and petri.odak_ayari["doz_mT"] == pytest.approx(1.4)
        # canlı kart / durum: hedef adı bütün plaka (iki dilde), "Kuyu (otomatik)" DEĞİL
        from utils import ceviri

        for dil, beklenen in (("tr", "Tüm petri"), ("en", "Whole well plate")):
            jeton = ceviri.istek_dili_var.set(dil)
            try:
                assert hedef.hedef_gosterim_adi(petri, 0) == beklenen
            finally:
                ceviri.istek_dili_var.reset(jeton)
    finally:
        with air._ai_loop_lock:
            air._ai_loop_active = False
        hedef.odak_ayarla(hedef.SAGLAYICILAR["petri"], None)


@pytest.mark.parametrize(
    "ham,tr,en",
    [
        ("Tüm petri", "Tüm petri", "Whole well plate"),
        ("Kuyu C2", "Kuyu C2", "Well C2"),
        ("Tümör T1", "Tümör T1", "Tumor T1"),
        ("Tümör modeli (DEMO)", "Tümör modeli (DEMO)", "Tümör modeli (DEMO)"),
    ],
)
def test_T9_gecmis_karti_ve_PDF_AI_Pro_hedefi_IKI_DILDE(ham, tr, en):
    from utils import ceviri
    from utils.seans_durum import hedef_etiketi

    for dil, beklenen in (("tr", tr), ("en", en)):
        jeton = ceviri.istek_dili_var.set(dil)
        try:
            assert hedef_etiketi(ham) == beklenen, (dil, ham)
        finally:
            ceviri.istek_dili_var.reset(jeton)
