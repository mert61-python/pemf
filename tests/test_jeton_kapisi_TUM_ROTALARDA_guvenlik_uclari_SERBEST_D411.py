# -*- coding: utf-8 -*-
"""D4.11 · B-2.14 — jeton kapısının GERÇEK karar gövdesi uygulamanın TÜM rotalarında koşulur; tedavi / E-stop SERBEST.

🔴 ÖLÇÜLEN DURUM (4-A, 2026-10-10): `jeton.GUVENLIK_YOLLARI` ({"seans_baslat", "acil_durdur", …}) `JetonYoneticisi.izin()`in
başında kontrol ediliyordu, ama üretimde `izin()`e YALNIZ `_islem_turu`nun çıktısı (bir MALIYET anahtarı ya da None) gelir →
kesişim ∅ (DENETIM-02-2: 96 rotada). Üç test (`test_jeton_yoneticisi` ×2, `test_jeton_bakiye_gorunurlugu`) bu ÖLÜ değeri
koruyordu; "tedavi ve E-stop jetondan bağımsız" değişmezinin ASIL taşıyıcısı `_islem_turu` + `_SERBEST_AI_UCLARI`dır. Kaçan
mutant: `_islem_turu` `/api/hardware/` yollarını "goruntu"ya eşler → mevcut jeton testlerinin HEPSİ YEŞİL (ölçüldü).

KAPI (davranış): `servers.api_server.app`in her HTTP rotası (yol parametreleri doldurulur) gerçek `_jeton_kapisi_karari`ndan
geçirilir; bayrak AÇIK, bakiye 0, ağ çağrıları (bakiye okuma + tüketim gönderimi) SAYILIR:
  · güvenlik uçları (acil durdurma, seans başlat/durdur, bobin kontrolü, AI Pro durdurma, AI Pro kare akışı) uygulamada VAR,
    karar SERBEST, ağ çağrısı 0; asenkron `jeton_gate` de onları ortak iş parçacığı havuzuna sokmadan bırakır (O-1.1);
  · `/api/ai/` DIŞINDAKİ her rota serbest, ağ çağrısı 0 (tedavi/kontrol yolları jetonun işi değildir);
  · KARŞIT: analiz uçları 402 alır (kapı canlı) ve kapılı her rota `/api/ai/` altındadır.
Güvenlik uçları TEST SABİTİDİR — mutasyon hedefinden (jeton.py) OKUNMAZ; yolları `tests/test_route_contract.py` ile aynı.
"""

from __future__ import annotations

import asyncio
import importlib
import re

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

#: Jetondan BAĞIMSIZ olması pazarlık edilemez uçlar (Ö.4-Y8, D4.11 planı). Sabit — üretim kümesinden türetilmez.
_GUVENLIK_UCLARI = frozenset(
    {
        "/api/hardware/emergency_stop",
        "/api/session/start",
        "/api/session/stop",
        "/api/coil/{coil_id}/control",
        "/api/ai/pro/stop",
        "/api/ai/ai_pro/frame",
    }
)
_SIFIR_BAKIYE = {"aylik_hak": 0, "satin_alinan": 0, "odeme_modeli": "on_odemeli", "kullandikca_borc": 0}


class _Istek:
    """`_jeton_kapisi_karari` / `jeton_gate`in kullandığı en küçük Request yüzeyi (kimlikli istek)."""

    def __init__(self, path: str):
        self.url = type("U", (), {"path": path})()
        # 4B-1.5: `sub` taşıyan JWT ({"sub": "test-kullanici"}) — kimliği çözülemeyen jeton zorlama açıkken 402 alır.
        self.headers = {"authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0LWt1bGxhbmljaSJ9.imza"}


def _somut(yol: str) -> str:
    """`/api/coil/{coil_id}/control` → `/api/coil/6/control` (yol parametresi doldurulur)."""
    return re.sub(r"\{[^}]+\}", "6", yol)


@pytest.fixture(scope="module")
def http_rotalari() -> list[str]:
    from servers.api_server import app

    yollar = sorted({r.path for r in app.routes if isinstance(r, APIRoute)})
    assert len(yollar) >= 80, f"VAKUM: yalniz {len(yollar)} HTTP rotasi bulundu"
    return yollar


@pytest.fixture()
def kapi(tmp_path, monkeypatch):
    """Bayrak AÇIK + bakiye 0; ağ çağrıları sayılır. Dönüş: yol → ("serbest" | "kapili:<kod>", [ağ çağrıları])."""
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path))
    j = importlib.import_module("servers.jeton")
    ag: list[str] = []
    monkeypatch.setattr(j, "JETON_ENFORCED", True)
    monkeypatch.setattr(j, "_bakiye_satiri_oku", lambda token: (ag.append("bakiye_oku"), dict(_SIFIR_BAKIYE))[1])
    monkeypatch.setattr(j, "_tuketim_gonder_canli", lambda token, **k: (ag.append("tuketim_gonder"), True)[1])

    def _kos(yol: str) -> tuple[str, list[str]]:
        ag.clear()
        try:
            j._jeton_kapisi_karari(_Istek(_somut(yol)))
            sonuc = "serbest"
        except HTTPException as e:
            sonuc = f"kapili:{e.status_code}"
        return sonuc, list(ag)

    _kos.modul = j
    return _kos


def test_KRITIK_guvenlik_uclari_UYGULAMADA_VAR_ve_jeton_kapisi_SERBEST_ag_SIFIR(http_rotalari, kapi):
    eksik = sorted(_GUVENLIK_UCLARI - set(http_rotalari))
    assert not eksik, f"güvenlik ucu uygulamada YOK (rota adı değişti mi? test_route_contract.py): {eksik}"
    sorunlu = {yol: kapi(yol) for yol in sorted(_GUVENLIK_UCLARI) if kapi(yol) != ("serbest", [])}
    assert not sorunlu, (
        f"jeton kapısı GÜVENLİK ucunu kapılıyor ya da onun için ağa çıkıyor (bayrak açık, bakiye 0): {sorunlu} — "
        "tedavi / acil durdurma jetondan BAĞIMSIZDIR (Ö.4-Y8)"
    )


def test_KRITIK_guvenlik_uclari_ASENKRON_kapida_ortak_havuza_GIRMEZ(kapi, monkeypatch):
    """`jeton_gate` güvenlik uçlarının kararını olay döngüsünde verir — HİÇBİR havuza girmez (O-1.1).

    4A-1.2 (A1 incelemesi, 2026-10-11): eskiden yalnız `asyncio.to_thread` yamalanıyordu; karar `run_in_threadpool`a (anyio
    ORTAK sınırlayıcısı) taşınınca bu test ve O-1.1 havuz testi (bayrak kapalı koşar) YEŞİL kalıyordu (ölçüldü). Ölçüt artık
    kütüphaneden bağımsız: koroutin çalışan döngüde TEK ADIMDA biter (hiçbir `await`te askıya alınmaz). KARŞIT: ücretli uç
    (`kidney_ct`) askıya alınır — ölçücü kör değil. `to_thread` askıya alan sahteyle değiştirilir (gerçek havuz açılmaz)."""

    async def _askiya_alan_havuz(*a, **k):
        await asyncio.sleep(0)

    monkeypatch.setattr(asyncio, "to_thread", _askiya_alan_havuz)

    async def _tek_adimda_biter(yol: str) -> bool:
        coro = kapi.modul.jeton_gate(_Istek(_somut(yol)))
        try:
            coro.send(None)
        except StopIteration:
            return True
        coro.close()
        return False

    assert not asyncio.run(_tek_adimda_biter("/api/ai/vision/kidney_ct")), "KARŞIT: ücretli uç askıya alınmadı"
    askida = [yol for yol in sorted(_GUVENLIK_UCLARI) if not asyncio.run(_tek_adimda_biter(yol))]
    assert not askida, f"güvenlik ucu jeton kararı için askıya alındı (havuz / await): {askida} — O-1.1 · Ö.4-Y8"


def test_KRITIK_ai_DISINDAKI_her_rota_jeton_kapisinda_SERBEST_ag_SIFIR(http_rotalari, kapi):
    ai_disi = [y for y in http_rotalari if not y.startswith("/api/ai/")]
    assert len(ai_disi) >= 50, f"VAKUM: yalniz {len(ai_disi)} ai-disi rota"
    sorunlu = {yol: kapi(yol) for yol in ai_disi if kapi(yol) != ("serbest", [])}
    assert not sorunlu, f"ai_router DIŞI rota(lar) jeton kapısında ücretli sınıfa düşüyor: {sorunlu}"


def test_KARSIT_KANIT_analiz_uclari_402_alir_ve_kapili_her_rota_ai_altinda(http_rotalari, kapi):
    """Ölçücü kör değil: bayrak açık + bakiye 0 iken analiz uçları GERÇEKTEN 402 alır (bakiye okunarak)."""
    kapili = {yol: kapi(yol) for yol in http_rotalari if kapi(yol)[0] != "serbest"}
    assert kapi("/api/ai/vision/kidney_ct") == ("kapili:402", ["bakiye_oku"]), kapi("/api/ai/vision/kidney_ct")
    assert len(kapili) >= 10, f"VAKUM: yalniz {len(kapili)} kapili rota: {sorted(kapili)}"
    assert all(y.startswith("/api/ai/") for y in kapili), f"ai_router disi kapili rota: {sorted(kapili)}"


# ── 4A-1.1 (A1 incelemesi, 2026-10-11): `/api/ai/` altına YARIN eklenecek bir durdurma ucu ───────────────────────────
# ÖLÇÜLDÜ: `@ai_router.post("/api/ai/pro/acil_durdur")` eklenip route contract güncellenince yukarıdaki dört test YEŞİL
# kalıyordu (güvenlik uçları SABİT 6 yol; `/api/ai/` altındaki yeni rota varsayılan "goruntu" sınıfına düşer ve KARŞIT
# testi onu doğru sayar), oysa uç bayrak açık + bakiye 0 iken GERÇEK `jeton_gate`le 402 alıp bakiye için ağa çıkıyordu.
#: Adında durdurma / acil anlamı taşıyan yol parçaları (TEST SABİTİ — jeton.py'den okunmaz).
_DURDURMA_PARCALARI = frozenset(
    {"stop", "estop", "durdur", "acil", "emergency", "iptal", "cancel", "abort", "halt", "kill", "bitir", "sonlandir"}
)
#: `jeton_gate` taşıyan HER rotanın BİLİNÇLİ sınıfı (None = serbest). Yeni bir ai_router rotası "durdurma mı, analiz mi?"
#: kararı verilip buraya eklenmeden bu kapı KIRMIZI — karar varsayılan "goruntu" sınıfına bırakılmaz.
_JETONLU_ROTA_SINIFI = {
    "/api/ai/ai_pro/frame": None,
    "/api/ai/hazirlik": None,
    "/api/ai/pro/approve": None,
    "/api/ai/pro/calibrate": None,
    "/api/ai/pro/hazirlik/baslat": None,
    "/api/ai/pro/hazirlik/durdur": None,
    "/api/ai/pro/organ": None,
    "/api/ai/pro/reject": None,
    "/api/ai/pro/status": None,
    "/api/ai/pro/stop": None,
    "/api/ai/pro/start": "ai_pro_seans",
    "/api/ai/pro/propose": "sensor",
    "/api/ai/rna/kidney": "agir_arastirma",
    "/api/ai/vision/histopath": "agir_arastirma",
    "/api/ai/vision/kidney_ct": "agir_arastirma",
    "/api/ai/vision/scratch": "agir_arastirma",
    "/api/ai/sound/cat": "ses",
    "/api/ai/disease": "goruntu",
    "/api/ai/disease/kidney": "goruntu",
    "/api/ai/vision/cat_organ": "goruntu",
    "/api/ai/vision/em_fantom": "goruntu",
    "/api/ai/vision/em_petri": "goruntu",
    "/api/ai/vision/landmark": "goruntu",
    "/api/ai/vision/reticulocytes": "goruntu",
    "/api/ai/vision/segmentation": "goruntu",
    "/api/ai/vision/thermal": "goruntu",
}


def _durdurma_anlamli(yol: str) -> bool:
    return bool(set(re.split(r"[/_\-{}.]+", yol.lower())) & _DURDURMA_PARCALARI)


def test_KRITIK_adinda_DURDURMA_anlami_olan_HER_rota_SERBEST_ag_SIFIR(http_rotalari, kapi):
    durdurma = [y for y in http_rotalari if _durdurma_anlamli(y)]
    assert {"/api/hardware/emergency_stop", "/api/session/stop", "/api/ai/pro/stop"} <= set(durdurma), durdurma
    sorunlu = {yol: kapi(yol) for yol in durdurma if kapi(yol) != ("serbest", [])}
    assert not sorunlu, (
        f"adında durdurma/acil anlamı olan rota(lar) jeton kapısında ücretli ya da ağa çıkıyor: {sorunlu} — "
        "`_SERBEST_AI_UCLARI`na ekleyin (Ö.4-Y8: ACİL DURDUR / STOP jetona kapılanmaz)"
    )


def test_KRITIK_jeton_gate_tasiyan_HER_rota_BILINCLI_siniflandirilmis(kapi):
    from servers.api_server import app

    jetonlu = {
        r.path
        for r in app.routes
        if isinstance(r, APIRoute)
        and "jeton_gate" in [getattr(d.call, "__name__", "") for d in r.dependant.dependencies]
    }
    assert len(jetonlu) >= 20, f"VAKUM: yalniz {len(jetonlu)} jeton_gate'li rota"
    yeni = sorted(jetonlu - set(_JETONLU_ROTA_SINIFI))
    assert not yeni, (
        f"sınıflandırılmamış jeton_gate'li rota(lar): {yeni} — durdurma/tedavi ise `_SERBEST_AI_UCLARI`na, analiz ise "
        "MALIYET sınıfına BİLİNÇLİ olarak koyun ve `_JETONLU_ROTA_SINIFI`na ekleyin (varsayılan 'goruntu' ücretlidir)"
    )
    farkli = {
        y: (kapi.modul._islem_turu(y), s) for y, s in _JETONLU_ROTA_SINIFI.items() if kapi.modul._islem_turu(y) != s
    }
    assert not farkli, f"jeton sınıfı değişti (gerçek, beklenen): {farkli}"
