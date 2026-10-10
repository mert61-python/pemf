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
        self.headers = {"authorization": "Bearer d411-jwt"}


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
    """`jeton_gate` güvenlik uçlarının kararını olay döngüsünde verir — `to_thread`e (ortak havuz) hiç girmez (O-1.1)."""

    async def _havuz(*a, **k):
        raise AssertionError("güvenlik ucu jeton kararı için ortak iş parçacığı havuzuna girdi")

    monkeypatch.setattr(asyncio, "to_thread", _havuz)
    for yol in sorted(_GUVENLIK_UCLARI):
        asyncio.run(kapi.modul.jeton_gate(_Istek(_somut(yol))))


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
