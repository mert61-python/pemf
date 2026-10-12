# -*- coding: utf-8 -*-
"""AII-2.1 (AI incelemesi, A2) — araştırma AI Pro TAKİP KİMLİĞİ kaybolunca BAŞKA hedefe VERİLMEZ (A-16 · D1.60 2. katman).

KUSUR [ÖLÇTÜM K1.5]: `_EmCvSaglayici._kimlik_ata` yeni kimliği `max(önceki karenin kimlikleri) + 1` ile verir. Önceki karede
görünmeyen (tespit düşen, el / pipet altında kalan) hedefin kimliği bu kümede YOKTUR → aynı numara bir SONRAKİ yeni adaya
verilir. Mühür (`onay_hedefi`) ve döngünün 2. katmanı (`_c_oid == muhur["hedef"]`) KİMLİĞİ karşılaştırır → onaylanan tümör
(P3) bir kare kaybolup döndüğünde, onun kimliği komşu tümöre (P2) geçer ve döngü O tümörün koordinatını SÜRER — onaysız hedef.
Tek kare tespit düşmesi + sıra değişimi yeter; sahte pozitif gerekmez.

Kapının iddiası: (1) mühürlü kimlik yalnız AYNI hedefe (son konumunun yarıçapı içinde) geri döner, (2) kaybolan kimlik başka bir
adaya verilmez, (3) eşleşme yarıçapla sınırlı (komşu kuyucuğa / tümöre kilitlenme yok), (4) GERÇEK seans döngüsü mühürlü
kimlikle yalnız onaylanan hedefin koordinatını sürer. Sahte EN ALT katta (`process_image`); sağlayıcı ve döngü gerçek.
Yol: tests/test_ai_pro_arastirma_TAKIP_KIMLIGI_kayip_sonrasi_BASKA_hedefe_verilmez_AII21.py"""

from __future__ import annotations

import numpy as np
import pytest

P1, P2, P3 = (100.0, 100.0), (200.0, 100.0), (300.0, 100.0)
M1, M2, M3 = (-40.0, -60.0, 0.0), (-40.0, 0.0, 0.0), (-40.0, 60.0, 0.0)


class _Bolge:
    def __init__(self, px, mm, r=10):
        self.centroid_px, self.centroid_cabin_mm = px, mm
        self.organ_id, self.area_px, self.bbox_px = 1, 100, (px[0] - r, px[1] - r, 2 * r, 2 * r)
        self.E_cancer, self.E_healthy, self.tumor_id = 0.9, 0.1, ""


class _Sonuc:
    def __init__(self, bolgeler):
        self.success, self.error, self.method, self.mm_per_px = True, None, "aruco_pnp", 0.0
        self.pemf_valid, self.reliable, self.warnings = True, True, []
        self.pemf_source, self.coord_frame, self.layout = "aruco", "cabin_aruco", {}
        self.tumor_regions = [_Bolge(p, m) for p, m in bolgeler]
        self.phantom_detection = {"primary": {"solidity": 0.9, "n_blue_inside": 5}}


class _Hat:
    kuyruk: list = []

    def __init__(self, cfg, **kw):
        self.cfg, self._predictor, self.yolo = cfg, None, None

    def process_image(self, frame, achieved_B=None, duty_sum=None):
        return (_Hat.kuyruk.pop(0) if len(_Hat.kuyruk) > 1 else _Hat.kuyruk[0]), {}

    def render_panels(self, ctx, result, lang="tr"):
        return {"07_combined": None}


class _Cfg:
    class phantom:  # noqa: N801
        achieved_B, duty_sum = 0.001, 2.4


#: Tek kare tespit düşmesi + sıra değişimi: P3 (mühürlü) kaybolur, önce P3 döner (P2 hâlâ yok), sonra P2 döner.
DIZI = [[(P1, M1), (P2, M2), (P3, M3)], [(P1, M1)], [(P1, M1), (P3, M3)], [(P1, M1), (P2, M2), (P3, M3)]]


@pytest.fixture()
def sag(monkeypatch):
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air

    cache = {"cls": _Hat, "cfg": _Cfg(), "predictor": None, "yolo": None, "yolo_path": "y.onnx"}
    monkeypatch.setattr(air, "_get_or_load_model", lambda ad, y: cache)
    monkeypatch.setattr(hedef, "hedef_kabin_disi_nedeni", lambda *a: "")
    tekil = hedef.SAGLAYICILAR["fantom"]
    snap = {
        a: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v) for a, v in vars(tekil).items()
    }
    # Orkestratör (AI inceleme): tekil sağlayıcı önceki testlerin takip durumunu taşır (ör. AI2_C4 döngüleri `_son_kimlik`'i
    # büyütür) → seans testinde "kimlik 3" P3 olmaz ve kapı SIRAYA bağlı düşerdi (ölçüldü: AI2_C4 + bu dosya → 1 failed).
    # Seans testi TAZE tekille başlar; bitince TÜM öznitelikler (sayıllar dahil) geri yüklenir.
    for a, v in vars(hedef.FantomSaglayici()).items():
        setattr(tekil, a, v)
    _Hat.kuyruk = []
    yield hedef, hedef.FantomSaglayici()
    for a in [a for a in vars(tekil) if a not in snap]:
        delattr(tekil, a)
    for a, v in snap.items():
        setattr(tekil, a, v)


def _lokalize(s, bolgeler, hedef_id):
    _Hat.kuyruk = [_Sonuc(bolgeler)]
    return s.localize(np.zeros((400, 400, 3), np.uint8), hedef_id)


def test_KRITIK_muhurlu_kimlik_kayip_sonrasi_BASKA_tumorun_koordinatini_vermez(sag):
    hedef, s = sag
    ilk = _lokalize(s, DIZI[0], 3)
    assert ilk[0] is True and tuple(ilk[1:4]) == M3, "düzenek: ilk karede kimlik 3 = P3 olmalı"
    for adim, bolgeler in enumerate(DIZI[1:], 1):
        r = _lokalize(s, bolgeler, 3)
        if r[0]:
            assert tuple(r[1:4]) == M3, (
                f"adım {adim}: mühürlü kimlik 3 (onaylanan P3) BAŞKA hedefin koordinatını verdi {tuple(r[1:4])} — "
                "kaybolan kimlik yeni adaya verildi (onaysız hedef, A-16)"
            )


def test_KRITIK_kaybolan_kimlik_YENI_adaya_verilmez(sag):
    hedef, s = sag
    _lokalize(s, DIZI[0], 0)
    ilk = {t["id"]: t["px"] for t in s.son_lokalizasyon_meta()["targets"]}
    for bolgeler in DIZI[1:]:
        _lokalize(s, bolgeler, 0)
        for t in s.son_lokalizasyon_meta()["targets"]:
            if t["id"] in ilk:
                assert tuple(t["px"]) == tuple(ilk[t["id"]]), (
                    f"kimlik {t['id']} ilk karede {ilk[t['id']]} idi, şimdi {t['px']} — kimlik başka hedefe geçti"
                )


def test_KRITIK_kaybolan_kimlik_UZAK_yeni_adaya_verilmez(sag):
    """Mühürlü P3 kayıp kalırken UZAKTA yeni bir aday (P4: sahte pozitif / bölünen tümör) belirir → P3'ün kimliğini ALMAZ."""
    hedef, s = sag
    P4, M4 = (300.0, 300.0), (-40.0, 60.0, 80.0)
    _lokalize(s, DIZI[0], 3)
    _lokalize(s, [(P1, M1), (P2, M2)], 3)
    r = _lokalize(s, [(P1, M1), (P2, M2), (P4, M4)], 3)
    assert not (r[0] and tuple(r[1:4]) == M4), "kayıp mühürlü kimlik 3, uzaktaki YENİ adaya (P4) verildi"


def test_KRITIK_takip_eslesmesi_YARICAPLA_sinirli(sag):
    """Komşu kuyucuk / tümör merkezleri yarıçaptan uzaktadır; eşleşme yarıçap dışına taşarsa (ör. `TAKIP_YARICAP_KATI` büyürse)
    mühürlü kimlik komşuya kayar. Yarıçap 10 px: 15 px öteye kayan aday AYNI kimliği ALMAZ."""
    hedef, s = sag
    _lokalize(s, [(P1, M1)], 0)
    kimlik = s.son_lokalizasyon_meta()["targets"][0]["id"]
    _lokalize(s, [((P1[0] + 15.0, P1[1]), M2)], 0)
    yeni = s.son_lokalizasyon_meta()["targets"][0]["id"]
    assert yeni != kimlik, "yarıçap (10 px) dışındaki aday önceki kimliği aldı — eşleşme yarıçapla sınırlı değil"
    _lokalize(s, [((P1[0] + 15.0 + 4.0, P1[1]), M2)], 0)
    assert s.son_lokalizasyon_meta()["targets"][0]["id"] == yeni, (
        "karşıt: yarıçap içindeki küçük kayma kimliği korumalı"
    )


def test_KARSIT_ayni_hedef_geri_donunce_kimligini_GERI_alir(sag):
    """Düzeltme kimliği SONSUZ büyütmemeli (fantom `hedef_idleri` 0–8): kaybolup AYNI yere dönen hedef aynı kimliği alır."""
    hedef, s = sag
    for bolgeler in DIZI:
        _lokalize(s, bolgeler, 0)
    son = {tuple(t["px"]): t["id"] for t in s.son_lokalizasyon_meta()["targets"]}
    assert son[P3] == 3 and son[P1] == 1, son
    # AIK: `hedef_idleri` artık VERİLMİŞ kimlikleri kapsar → "sonsuz büyümez" iddiası STATİK tavana pinlenir.
    assert max(son.values()) <= s.azami_hedef, son


# ── GERÇEK SEANS DÖNGÜSÜ: mühürlü hedef 3 iken yalnız P3'ün koordinatı sürülür ─────────────────────────────────────
class _Cv2:
    INTER_AREA, IMWRITE_JPEG_QUALITY = 3, 1

    class _Cap:
        def isOpened(self):  # noqa: N802
            return True

        def read(self):
            return True, np.zeros((400, 400, 3), np.uint8)

        def release(self):
            return None

    def VideoCapture(self, *a, **k):  # noqa: N802
        return self._Cap()

    def imencode(self, *a, **k):
        return True, bytearray(b"jpeg")

    def resize(self, img, *a, **k):
        return img


class _Saat:
    def __init__(self, air, tur):
        import time as _t

        self._t, self._air, self.kalan = _t, air, tur

    def __getattr__(self, ad):
        return getattr(self._t, ad)

    def time(self):
        return 1_800_000_000.0

    def sleep(self, _sn):
        self.kalan -= 1
        if self.kalan <= 0:
            self._air._ai_loop_active = False


def test_KRITIK_seans_dongusu_MUHURLU_hedef_disinda_SURMEZ(sag, monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis
    from utils import estop_mandali

    hedef, _s = sag
    tahmin = []
    snap = (dict(air._ai_organ_cache), air._ai_organ_id, air._ai_hedef_modeli)
    with apis._session_lock:
        sess = dict(apis._active_session)
    monkeypatch.setattr(air, "cv2", _Cv2())
    monkeypatch.setattr(
        air, "_predict_and_drive", lambda x, y, z, o: tahmin.append((x, y, z)) or ([0.5] * 7, [0.0] * 7, 1.0)
    )
    monkeypatch.setattr(air, "_drive_coils_ai_pro", lambda D, P: [1])
    monkeypatch.setattr(apis, "_stop_session_coils", lambda *a, **k: None)
    monkeypatch.setattr(apis, "_bildir_teyitsiz_stop", lambda *a, **k: None)
    monkeypatch.setattr(apis, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(apis, "update_live_session_state", lambda *a, **k: None)
    monkeypatch.setattr(apis, "state", None)
    monkeypatch.setattr(air, "_ai_started_at", 0.0)
    monkeypatch.setattr(air, "_ai_relocalize", True)
    monkeypatch.setattr(air, "_ORGAN_LOCALIZE_INTERVAL_S", 0.0)
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    monkeypatch.setattr(air, "_ai_hedef_modeli", "fantom")
    # Onay anı (hazırlık): 3 tümör, kimlik 3 = P3 mühürlenir.
    _lokalize(hedef.SAGLAYICILAR["fantom"], DIZI[0], 3)
    monkeypatch.setattr(air, "_ai_organ_id", 3)
    air._ai_organ_cache.update({"at": 0.0, "organ_id": -1, "localized": False, "guven_dokumu": None})
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update({"is_active": True, "session_id": "ai_1", "mode": "AI Pro · Fantom Tümör"})
    _Hat.kuyruk = [_Sonuc(b) for b in DIZI[1:]]
    saat = _Saat(air, 4)
    monkeypatch.setattr(air, "time", saat)
    muhur = {"nesil": estop_mandali.nesil(), "onay": "t", "dongu": air._ai_dongu_no, "hedef": 3}
    try:
        air._ai_loop_active = True
        air._ai_pro_loop(muhur)
    finally:
        air._ai_loop_active = False
        air._ai_organ_cache.clear()
        air._ai_organ_cache.update(snap[0])
        with apis._session_lock:
            apis._active_session.clear()
            apis._active_session.update(sess)
    assert saat.kalan <= 0, "döngü dönmedi — düzenek kör"
    yanlis = [t for t in tahmin if tuple(t) != M3]
    assert not yanlis, f"mühürlü hedef 3 (P3 {M3}) iken BAŞKA tümörün koordinatı sürüldü: {yanlis}"
