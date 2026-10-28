# -*- coding: utf-8 -*-
"""Y212 · S-D67.13 (sahip, 2026-10-28) — seans sırasında Canlı E-Alanı WS bağlıyken de istemciye AKAR.

ÖLÇÜLEN KUSUR (D6.25 ürün bulgusu, HEAD 8b002fc0): `efield_live` 2 Hz döngüsü değeri yalnız önbelleğe yazıyordu; istemciye yalnız tam snapshot
(WS bağlanınca) taşıyordu. WS ayaktayken arayüz HTTP yoklamasını atladığı için seans boyunca E-Alanı çubuğu 5 sn sonra "duraklandı" diyordu.
SÖZLEŞME: döngü her YENİ hesabı `yayinla`ya verir; hesap bitince (seans / bağlam yok) BİR KEZ None, sonra susar (boşta yayın yok). Backend
bunu `efield_update` WS iletisiyle yayar; tür periyodiktir (geri basınçta ilk o düşer — ACİL DURDUR / geçiş iletileri düşürülemez kalır).
Arayüz tarafı: `apps/ui/src/components/domain/__tests__/EFieldBar.Y212.wsCanliAkis.test.tsx`.
Sahte YALNIZ en altta: vekil model hesabı (`compute`) ve analiz bağlamı (ONNX / kamera yok); döngü, durum geçişi ve yayın kararı GERÇEK.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def _dongu(monkeypatch, aktif: dict, yayinlar: list):
    from servers import efield_live

    sayac = {"n": 0}

    def _hesap(_coils):
        sayac["n"] += 1
        return {"cancer": 0.05, "healthy": 0.02, "ts": 1000.0 + sayac["n"]}

    def _aktif_mi():
        if aktif.get("dur"):
            raise SystemExit  # döngü iş parçacığını bitirir (except Exception yakalamaz)
        return aktif["seans"]

    monkeypatch.setattr(efield_live, "TICK_S", 0.01)
    monkeypatch.setattr(efield_live, "compute", _hesap)
    monkeypatch.setattr(efield_live, "get_context", lambda: {"regions": [1]})
    t = efield_live.start_loop(read_coils=lambda: [], is_session_active=_aktif_mi, yayinla=yayinlar.append)
    return efield_live, t


def _bekle(kosul, sure=3.0):
    son = time.monotonic() + sure
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.01)
    return False


def test_KRITIK_seans_suresince_HER_yeni_hesap_yayinlanir_bitince_TEK_None_sonra_SUSAR(monkeypatch):
    aktif = {"seans": True}
    yayinlar: list = []
    ef, t = _dongu(monkeypatch, aktif, yayinlar)
    try:
        assert _bekle(lambda: len([y for y in yayinlar if y]) >= 5), (
            f"seans sürerken yeni hesap yayınlanmadı: {yayinlar[:5]}"
        )
        damgalar = [y["ts"] for y in yayinlar if y]
        assert damgalar == sorted(set(damgalar)), f"her yayın YENİ hesap olmalı (damga artar): {damgalar[:10]}"
        aktif["seans"] = False
        assert _bekle(lambda: yayinlar and yayinlar[-1] is None), "seans bitti ama 'hesap yok' (None) yayınlanmadı"
        n = len(yayinlar)
        time.sleep(0.2)  # ~20 tik boşta
        assert len(yayinlar) == n, f"boştayken yayın SÜRÜYOR (her tikte None): {yayinlar[n:][:5]}"
        assert [y for y in yayinlar if y is None] == [None], f"bitişte TEK None beklenirdi: {yayinlar.count(None)}"
        assert ef.get_live() is None
    finally:
        aktif["dur"] = True
        t.join(timeout=3)
        ef._set_live(None)
    assert not t.is_alive(), "aparat: döngü iş parçacığı kapanmadı"


def test_KARSIT_yayinla_VERILMEZSE_davranis_eskisi_gibi_yalniz_onbellek(monkeypatch):
    """Eski çağıranlar (`yayinla` yok) bozulmaz: döngü yalnız önbelleği yazar. (Önbellek değil YAZIM kaydedilir: süreçte daha önce
    başlamış gerçek döngü boşta önbelleğe None yazar — dolu değeri yalnız bu testin döngüsü üretir.)"""
    aktif = {"seans": True}
    from servers import efield_live

    yazilan: list = []
    asil = efield_live._set_live
    monkeypatch.setattr(efield_live, "_set_live", lambda v: (yazilan.append(v) if v else None, asil(v)))
    monkeypatch.setattr(efield_live, "TICK_S", 0.01)
    monkeypatch.setattr(efield_live, "compute", lambda _c: {"cancer": 0.05, "ts": time.time()})
    monkeypatch.setattr(efield_live, "get_context", lambda: {"regions": [1]})

    def _aktif_mi():
        if aktif.get("dur"):
            raise SystemExit
        return aktif["seans"]

    t = efield_live.start_loop(read_coils=lambda: [], is_session_active=_aktif_mi)
    try:
        assert _bekle(lambda: len(yazilan) >= 3), "yayinla'sız döngü önbelleğe hesap yazmadı"
    finally:
        aktif["dur"] = True
        t.join(timeout=3)
        asil(None)


def test_KRITIK_backend_dongusu_efield_update_iletisiyle_ve_PERIYODIK_turle_yayar():
    from servers import live_state

    assert "efield_update" in live_state._WS_PERIYODIK_TURLER, (
        "efield_update periyodik değil — 2 Hz akış geri basınçta düşürülemez kalır"
    )
    agac = ast.parse((KOK / "apps" / "backend" / "servers" / "api_server.py").read_text(encoding="utf-8"))
    cagrilar = [
        c
        for c in ast.walk(agac)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "start_loop"
    ]
    assert len(cagrilar) == 1, f"aparat: efield_live.start_loop çağrısı bulunamadı ({len(cagrilar)})"
    yay = {k.arg: k.value for k in cagrilar[0].keywords}.get("yayinla")
    assert isinstance(yay, ast.Lambda), "start_loop'a yayinla verilmiyor — değer WS'de yalnız ilk snapshot'la gider"
    govde = yay.body
    assert isinstance(govde, ast.Call) and getattr(govde.func, "id", "") == "_ws_broadcast_sync", ast.unparse(yay)
    ileti = govde.args[0]
    assert isinstance(ileti, ast.Dict), ast.unparse(yay)
    alanlar = {ast.literal_eval(k): v for k, v in zip(ileti.keys, ileti.values)}
    assert ast.literal_eval(alanlar["type"]) == "efield_update", ast.unparse(yay)
    assert isinstance(alanlar["data"], ast.Name) and alanlar["data"].id == yay.args.args[0].arg, (
        f"yayınlanan veri döngünün verdiği değer değil: {ast.unparse(yay)}"
    )
