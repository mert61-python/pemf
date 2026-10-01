# Author: mertaygn, cglrgrkn
"""D1.12 · B-5.19 — AI Pro'nun dört SÜRÜŞ değişmezine davranış kapısı.

DENETİM-05 (05-2 §2): dört mutant tam süitte YEŞİL kalıyordu; `ai_router.py`'nin seans
döngüsündeki "lokalizasyondan sonra seans hâlâ aktif mi" denetimi ve `/frame`'in süre dalı hiçbir
testte koşmuyordu. Bunlar B-5.3 (E-stop sonrası yeniden enerjileme), B-5.1/B-5.10 (onaysız
`/frame`) ve İG-5.26 düzeltmelerinin KORUYACAĞI değişmezlerdir → o düzeltmelerden ÖNCE kapılanır.

  (a) Lokalizasyon (~1-4 sn) SIRASINDA seans pasifleşirse (E-stop) döngü SÜRMEZ — gerçek `_ai_pro_loop`.
  (b) Süresi dolmuş seansta `/frame` sürmez → `tests/test_ai_pro_frame_suresi_dolmus_SURMEZ.py` (D1.07).
  (c) Güven eşiği İKİ YÖNDE: 0,29 sürülmez, 0,31 sürülür. A-23 (sahip): kedi `_MIN_RELIABILITY` ile
      araştırma `MIN_GUVEN` BAĞIMSIZ kalır; HER BİRİ ayrı değer kapısıyla kilitli, 0,3'ün altı KIRMIZI
      (İG-5.26: 0,2'de kalibrasyonsuz hedef sürülüyordu).
  (d) `:8100` mikroservisi kareyle birlikte GERÇEK `image_w`/`image_h` döndürür (kodlanan kareye ait).

Sahte olan yalnız kamera (cv2), model yükleyicileri, doz tahmini, ağır boru hattı ve donanım
(kayıtçı); eşik kararları, döngü, `/frame` ucu ve kodlama yardımcısı GERÇEKTİR.
"""

from __future__ import annotations

import ast
import base64
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]


def _hedef_tuple(air, guven: float, organ_id: int = 2):
    """Lokalizasyon tuple'ı ÜRETİM fonksiyonundan — eşik kararı GERÇEK `_extract_organ_target`'ta."""
    return air._extract_organ_target({2: {"coord_cabin_cm": [1.0, 2.0, 3.0], "reliability": guven}}, organ_id, None)


# ── (a) gerçek seans döngüsü ─────────────────────────────────────────────────────


class _SahteCv2:
    INTER_AREA = 3
    IMWRITE_JPEG_QUALITY = 1

    class _Cap:
        def isOpened(self):  # noqa: N802
            return True

        def read(self):
            return True, np.zeros((8, 8, 3), dtype=np.uint8)

        def release(self):
            return None

    def VideoCapture(self, *a, **k):  # noqa: N802 — GERÇEK kamera AÇILMAZ
        return self._Cap()

    def imencode(self, *a, **k):
        return True, bytearray(b"jpeg")

    def resize(self, img, *a, **k):
        return img


class _Saat:
    """Duvar saati sabit; `sleep` tur sayar ve bitince döngüyü kapatır (test asılmaz)."""

    def __init__(self, air, tur: int):
        import time as _t

        self._t, self._air, self.kalan = _t, air, int(tur)

    def __getattr__(self, ad):
        return getattr(self._t, ad)

    def time(self):
        return 1_800_000_000.0

    def sleep(self, _sn):
        self.kalan -= 1
        if self.kalan <= 0:
            self._air._ai_loop_active = False


@pytest.fixture
def dongu(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    anlik = (dict(air._ai_organ_cache), air._ai_organ_id, air._ai_owner_client)
    with apis._session_lock:
        seans_anlik = dict(apis._active_session)
    izler: dict = {"surus": [], "stop": []}
    monkeypatch.setattr(air, "cv2", _SahteCv2())
    monkeypatch.setattr(air, "_get_or_load_kedi", lambda *a, **k: None)
    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda *a, **k: None)
    monkeypatch.setattr(air, "_predict_and_drive", lambda *a, **k: ([0.5] * 7, [0.0] * 7, 1.0))
    monkeypatch.setattr(air, "_drive_coils_ai_pro", lambda D, P: izler["surus"].append((D, P)))
    monkeypatch.setattr(apis, "_stop_session_coils", lambda c=None: izler["stop"].append(list(c or [])))
    monkeypatch.setattr(apis, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(apis, "update_live_session_state", lambda *a, **k: None)
    monkeypatch.setattr(apis, "_mqtt_publish", lambda *a, **k: False)
    monkeypatch.setattr(apis, "state", None)
    monkeypatch.setattr(air, "_ai_started_at", 0.0)
    monkeypatch.setattr(air, "_ai_relocalize", True)
    monkeypatch.setattr(air, "_ai_organ_id", 2)
    air._ai_organ_cache.update({"at": 0.0, "organ_id": -1, "localized": False, "guven_dokumu": None})
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update({"is_active": True, "session_id": "d112", "mode": "AI Pro"})

    def kos(tur: int, lokalize):
        monkeypatch.setattr(air, "_localize_organ", lokalize)
        monkeypatch.setattr(air, "time", _Saat(air, tur))
        air._ai_loop_active = True
        air._ai_pro_loop()

    try:
        yield air, apis, izler, kos
    finally:
        air._ai_loop_active = False
        air._ai_organ_cache.clear()
        air._ai_organ_cache.update(anlik[0])
        air._ai_organ_id, air._ai_owner_client = anlik[1], anlik[2]
        with apis._session_lock:
            apis._active_session.clear()
            apis._active_session.update(seans_anlik)


def test_KRITIK_a_lokalizasyon_SIRASINDA_seans_pasiflesirse_SURUS_YOK(dongu):
    air, apis, izler, kos = dongu

    def _lokalize_ve_estop(*a, **k):
        with apis._session_lock:  # E-stop lokalizasyonun ortasında geldi
            apis._active_session["is_active"] = False
        return _hedef_tuple(air, 0.9)

    kos(3, _lokalize_ve_estop)
    assert izler["surus"] == [], "lokalizasyon sırasında seans pasifleşti ama döngü bobinleri SÜRDÜ"
    assert air._ai_loop_active is False, "seans pasifken döngü durmadı"


def test_KARSIT_a_seans_aktif_kalirsa_dongu_SURER(dongu):
    air, _apis, izler, kos = dongu
    kos(2, lambda *a, **k: _hedef_tuple(air, 0.9))
    assert izler["surus"], "aktif seansta hedef bulunduğu hâlde döngü sürmedi (aparat kör)"


# ── (c) güven eşiği: kedi hattı (gerçek /frame) ─────────────────────────────────


class _KayitciDonanim:
    def __init__(self):
        self.baslat: list[int] = []

    def update_coil(self, coil_id, freq, duty, phase, duration, start=True, duration_seconds=None):
        if start:
            self.baslat.append(int(coil_id))
        return True

    def stop_all_coils(self):
        return True


@pytest.fixture
def kare_ucu(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    anlik = (
        dict(air._ai_organ_cache),
        air._ai_owner_client,
        air._ai_started_at,
        air._ai_duration_min,
        air._ai_organ_id,
        air._ai_relocalize,
    )
    with apis._session_lock:
        seans_anlik = dict(apis._active_session)
    hw = _KayitciDonanim()

    async def _cozum(*a, **k):
        return np.zeros((8, 8, 3), dtype=np.uint8)

    monkeypatch.setattr(air, "_decode_image", _cozum)
    monkeypatch.setattr(air, "_predict_and_drive", lambda x, y, z, o: ([0.3] * 7, [0.0] * 7, 0.05))
    monkeypatch.setattr(apis.state, "hardware", hw)
    monkeypatch.setattr(apis, "_mqtt_publish", lambda *a, **k: False)
    monkeypatch.setattr(apis, "_ws_broadcast_sync", lambda *a, **k: None)
    air._ai_owner_client = ""
    air._ai_started_at = time.monotonic()
    air._ai_duration_min = 20
    air._ai_organ_id = 2
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update({"is_active": True, "mode": "AI Pro", "coil_ids": list(range(1, 8))})

    def kare(guven: float):
        monkeypatch.setattr(air, "_localize_organ", lambda f, o: _hedef_tuple(air, guven))
        air._ai_relocalize = True
        r = TestClient(apis.app).post(
            "/api/ai/ai_pro/frame", data={"image_base64": base64.b64encode(b"\xff\xd8\xff\xd9").decode()}
        )
        assert r.status_code == 200, r.text[:300]
        return r.json()

    try:
        yield kare, hw
    finally:
        air._ai_organ_cache.clear()
        air._ai_organ_cache.update(anlik[0])
        (
            air._ai_owner_client,
            air._ai_started_at,
            air._ai_duration_min,
            air._ai_organ_id,
            air._ai_relocalize,
        ) = anlik[1:]
        with apis._session_lock:
            apis._active_session.clear()
            apis._active_session.update(seans_anlik)


@pytest.mark.parametrize(("guven", "surulur"), [(0.29, False), (0.31, True)])
def test_KRITIK_c_kedi_esigi_IKI_YONDE_gercek_frame_yolunda(kare_ucu, guven, surulur):
    kare, hw = kare_ucu
    j = kare(guven)
    assert j["driven"] is surulur, f"güven {guven}: driven={j['driven']} (eşik 0,3 — İG-5.26)"
    assert bool(hw.baslat) is surulur, f"güven {guven}: STM başlatmaları {hw.baslat}"


@pytest.mark.parametrize(("guven", "bulunur"), [(0.29, False), (0.31, True)])
def test_KRITIK_c_kedi_esigi_TUM_VUCUT_hedefinde_de(guven, bulunur):
    import servers.ai_router as air

    assert _hedef_tuple(air, guven, organ_id=0)[0] is bulunur


# ── (c) güven eşiği: araştırma hattı (gerçek localize; ağır boru hattı sahte) ──────


def _arastirma_saglayici(guven: float):
    from servers import ai_pro_hedef

    class _Sahte(ai_pro_hedef._EmCvSaglayici):
        ad = "d112_sahte"

        def _onbellek(self):
            return {}

        def _pipeline_kur(self, cache):
            sonuc = SimpleNamespace(success=True, error="", method="aruco_pnp", mm_per_px=1.0)
            return SimpleNamespace(process_image=lambda *a, **k: (sonuc, None))

        def _adaylar(self, result):
            return [
                {"reliability": guven, "x": 1.0, "y": 2.0, "z": 3.0, "px": (4.0, 4.0), "bbox": (0, 0, 8, 8)},
            ]

        def _overlay(self, pl, ctx, result):
            return None

        def _egitim_araligi(self):
            return None

    return _Sahte()


@pytest.mark.parametrize(("guven", "bulunur"), [(0.29, False), (0.31, True)])
def test_KRITIK_c_arastirma_esigi_IKI_YONDE_gercek_localize(guven, bulunur):
    sonuc = _arastirma_saglayici(guven).localize(np.zeros((8, 8, 3), dtype=np.uint8), 0)
    assert sonuc[0] is bulunur, f"araştırma hattı güven {guven}: localized={sonuc[0]} (eşik 0,3)"


def test_KRITIK_c_A23_kedi_esigi_DEGER_kapisi():
    import servers.ai_router as air

    assert air._MIN_RELIABILITY >= 0.3, f"kedi eşiği {air._MIN_RELIABILITY} < 0,3 — kalibrasyonsuz hedef sürülür"


def test_KRITIK_c_A23_arastirma_esigi_DEGER_kapisi():
    from servers import ai_pro_hedef

    assert ai_pro_hedef.MIN_GUVEN >= 0.3, f"araştırma eşiği {ai_pro_hedef.MIN_GUVEN} < 0,3"


def test_KRITIK_c_A23_esikler_BAGIMSIZ_birinden_turemez():
    """A-23: biri değişince öteki SESSİZCE değişmesin → ikisi de kendi modülünde SAYI literali."""
    for yol, ad in (
        ("apps/backend/servers/ai_router.py", "_MIN_RELIABILITY"),
        ("apps/backend/servers/ai_pro_hedef.py", "MIN_GUVEN"),
    ):
        agac = ast.parse((KOK / yol).read_text(encoding="utf-8"))
        atamalar = [
            d.value
            for d in agac.body
            if isinstance(d, ast.Assign) and any(isinstance(h, ast.Name) and h.id == ad for h in d.targets)
        ]
        assert len(atamalar) == 1, f"{yol}: {ad} modül düzeyinde TAM 1 kez atanmalı ({len(atamalar)})"
        assert isinstance(atamalar[0], ast.Constant) and isinstance(atamalar[0].value, (int, float)), (
            f"{yol}: {ad} bir SAYI literali değil (başka eşikten türüyor) — A-23 bağımsızlık"
        )


# A-23 bağımsızlığı KARAR YERİNDE (bağımsız inceleme r3): yukarıdaki AST kapısı yalnız ATAMAYA bakıyordu;
# araştırma kararı `from servers.ai_router import _MIN_RELIABILITY` ile kedi eşiğine bağlansa (MIN_GUVEN
# literal kalırken) 237 test YEŞİL kalıyordu. Her kol önce yamanın KENDİ hattında etkili olduğunu ölçer
# (aparat canlı), sonra ÖTEKİ hattın kararının değişmediğini.


def test_KRITIK_c_A23_kedi_esigi_degisince_ARASTIRMA_karari_DEGISMEZ(monkeypatch):
    import servers.ai_router as air

    monkeypatch.setattr(air, "_MIN_RELIABILITY", 0.9)
    assert _hedef_tuple(air, 0.31)[0] is False, "aparat kör: kedi eşiği yaması kedi kararına ulaşmıyor"
    sonuc = _arastirma_saglayici(0.31).localize(np.zeros((8, 8, 3), dtype=np.uint8), 0)
    assert sonuc[0] is True, (
        "kedi eşiği 0,9 yapılınca araştırma hattı güveni 0,31 olan hedefi REDDETTİ — araştırma kararı kedi "
        "eşiğine bağlı (A-23: biri değişince öteki SESSİZCE değişmez)"
    )


def test_KRITIK_c_A23_arastirma_esigi_degisince_KEDI_surusu_DEGISMEZ(kare_ucu, monkeypatch):
    from servers import ai_pro_hedef

    monkeypatch.setattr(ai_pro_hedef, "MIN_GUVEN", 0.9)
    aparat = _arastirma_saglayici(0.31).localize(np.zeros((8, 8, 3), dtype=np.uint8), 0)
    assert aparat[0] is False, "aparat kör: araştırma eşiği yaması araştırma kararına ulaşmıyor"
    kare, hw = kare_ucu
    j = kare(0.31)
    assert j["driven"] is True and hw.baslat, (
        f"araştırma eşiği 0,9 yapılınca kedi /frame güven 0,31'de SÜRMEDİ (driven={j['driven']}, "
        f"STM başlatmaları {hw.baslat}) — kedi kararı araştırma eşiğine bağlı (A-23)"
    )


# ── (d) :8100 kare ölçüsü ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(("h", "w", "bek_w", "bek_h"), [(200, 120, 120, 200), (1000, 2000, 1600, 800)])
def test_KRITIK_d_8100_kodlama_GERCEK_kare_olcusunu_dondurur(h, w, bek_w, bek_h):
    import cv2

    import ai_service.app as svc

    jpeg, olcu = svc._kapakli_kodla_servis(np.zeros((h, w, 3), dtype=np.uint8))
    kod_h, kod_w = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR).shape[:2]
    assert (kod_w, kod_h) == (bek_w, bek_h), f"kodlanan kare {kod_w}x{kod_h}"
    assert olcu == {"image_w": bek_w, "image_h": bek_h}, (
        f":8100 kare ölçüsü {olcu} — kodlanan kare {kod_w}x{kod_h} (oran kilidi / işaret kayması)"
    )
