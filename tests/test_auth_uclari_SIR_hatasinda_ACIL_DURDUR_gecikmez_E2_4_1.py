# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""E2-4.1 (2-E incelemesi · Ö.4-Y8) — sır deposu okunamazken async kimlik uçları olay döngüsünü DONDURMAZ; ACİL DURDUR gecikmez.

Kusur [ölçüldü, 2-E incelemesi O3]: `/api/auth/token`, `/api/auth/exchange` ve `/api/auth/reset` async uçlardır ve sır deposunu
(`get_api_token` / `get_secret`) SATIR İÇİ okur. Sır önbelleği soğukken ya da sır dosyası okunamazken (ikinci hesap / bozulmuş ACL)
`secrets_manager._load` → `_ensure_dir_hardened` → `icacls` (alt süreç, 10 sn zaman aşımı) ve `get_api_token`'ın yedek yolu
(`api_token.txt` + `lock_down_file` → `icacls`) OLAY DÖNGÜSÜNDE koşuyordu. `icacls` yavaşken (antivirüs, büyük veri kökü — 20 000 dosyada
1,9 sn ölçüldü) döngü saniyelerce donuyor ve o sürede gelen ACİL DURDUR isteği DAĞITILAMIYORDU (3 sn'lik `icacls` ile 6,1 sn ölçüldü).

Kapı tek PAYLAŞILAN olay döngüsünden ölçer (httpx ASGITransport — üretimdeki uvicorn gibi; TestClient her istekte yeni döngü açar).
Arıza EN ALT katta ve GERÇEK: sır dosyası GERÇEK ACL ile okunamaz (yalnız LOCAL SERVICE), `icacls` `file_acl.subprocess.run` düzeyinde
3 sn yavaşlatılır (gerçek komut yine koşar). Ölçüt: 10 ms'lik kalp atışının en büyük boşluğu (döngü donması) + ACİL DURDUR yanıtı.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="GERÇEK NTFS ACL + icacls")

_YAVAS_SN = 3.0
_DONMA_TAVANI_SN = 1.0


@pytest.fixture
def o(monkeypatch, tmp_path):
    import ai_pro_aparati as apa
    from kayitci_donanim import gercek_hc

    o = apa.kur(monkeypatch, tmp_path)
    o.mp = monkeypatch
    try:
        with gercek_hc() as hc:
            monkeypatch.setattr(o.api.state, "hardware", hc)
            o.hc = hc
            yield o
    finally:
        o.air._ai_loop_active = False
        o.geri()


@pytest.fixture
def sir_okunamaz_icacls_yavas(o):
    """Sır dosyası GERÇEK ACL ile okunamaz + soğuk önbellek + sertleştirme yeniden denenir + `icacls` 3 sn yavaş (gerçek komut koşar)."""
    from servers import auth
    from utils import file_acl
    from utils import secrets_manager as sm

    sm.get_secret("api_token")  # sır dosyası VAR olsun (conftest veri kökü)
    sir = sm.secrets_path()
    o.mp.setattr(sm, "_cache", None)
    o.mp.setattr(sm, "_dir_hardened", False)
    o.mp.setattr(sm, "_sertlestirme_sonraki", 0.0)
    o.mp.setattr(auth, "_token", None)
    o.mp.delenv("PEMF_API_TOKEN", raising=False)
    _gercek = file_acl.subprocess.run
    cagri = []

    def _yavas(arg, *a, **k):
        if arg and "icacls" in str(arg[0]).lower():
            cagri.append(time.monotonic())
            time.sleep(_YAVAS_SN)
        return _gercek(arg, *a, **k)

    o.mp.setattr(file_acl.subprocess, "run", _yavas)
    subprocess.run(["icacls", str(sir), "/reset"], capture_output=True)
    k = subprocess.run(
        ["icacls", str(sir), "/inheritance:r", "/grant:r", "*S-1-5-19:F"], capture_output=True, text=True
    )
    assert k.returncode == 0, k.stdout + k.stderr
    try:
        try:
            sir.read_bytes()
            okunamaz = False
        except PermissionError:
            okunamaz = True
        assert okunamaz, "ARAÇ: sır dosyası okunamaz kurulamadı — kol geçersiz"
        yield cagri
    finally:
        subprocess.run(["icacls", str(sir), "/reset"], capture_output=True)
        sir.read_bytes()  # erişim geri geldi (TEMİZLİK; düşerse test ERROR)


async def _olc(o, istek):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=o.api.app, client=("127.0.0.1", 50124)), base_url="http://cihaz", timeout=60
    ) as c:
        bitti = asyncio.Event()
        bosluk = []

        async def _kalp():
            son = time.monotonic()
            while not bitti.is_set():
                await asyncio.sleep(0.01)
                t = time.monotonic()
                bosluk.append(t - son)
                son = t

        k = asyncio.create_task(_kalp())
        g = asyncio.create_task(istek(c))
        await asyncio.sleep(0.15)
        estop = []
        while not g.done() or len(estop) < 2:
            t0 = time.monotonic()
            r = await c.post("/api/hardware/emergency_stop")
            estop.append((r.status_code, time.monotonic() - t0))
            await asyncio.sleep(0.3)
        yanit = await g
        bitti.set()
        await k
        return yanit, max(bosluk), estop


_UCLAR = {
    "token": lambda c: c.get("/api/auth/token"),
    "exchange": lambda c: c.post("/api/auth/exchange", json={"code": "YANLIS1"}),
    "reset": lambda c: c.post(
        "/api/auth/reset", json={"email": "yok@ornek.test", "admin_code": "YANLIS-KOD", "new_password": "x"}
    ),
}


@pytest.mark.parametrize("uc", sorted(_UCLAR))
def test_KRITIK_sir_okunamazken_kimlik_ucu_DONGUYU_dondurmaz_ACIL_DURDUR_gecikmez_E2_4_1(
    o, sir_okunamaz_icacls_yavas, uc
):
    yanit, donma, estop = asyncio.run(_olc(o, _UCLAR[uc]))
    assert sir_okunamaz_icacls_yavas, "ARAÇ: yavaş icacls hiç çağrılmadı — sır yükleme yolu koşmadı, kol geçersiz"
    assert donma < _DONMA_TAVANI_SN, (
        f"/api/auth/{uc}: sır deposu okunamazken olay döngüsü {donma:.2f} sn DONDU (icacls satır içi) — bu sürede ACİL DURDUR "
        f"dağıtılamadı; ACİL DURDUR ölçümleri {estop}"
    )
    assert all(k == 200 for k, _ in estop), estop
    assert yanit.status_code in (200, 403, 429, 400), yanit.text


def test_KARSIT_sir_okunurken_token_ucu_AYNI_tokeni_verir_ve_LAN_disina_403_E2_4_1(o):
    """Davranış değişmez: yerel istemci cihaz token'ını alır (iki çağrıda aynı), tünelden gelen istek 403."""
    import httpx
    from servers import auth

    o.mp.setattr(auth, "_token", None)

    async def _kos():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=o.api.app, client=("127.0.0.1", 50125)), base_url="http://cihaz"
        ) as c:
            r1 = await c.get("/api/auth/token")
            r2 = await c.get("/api/auth/token")
            r3 = await c.get("/api/auth/token", headers={"cf-ray": "x", "cf-connecting-ip": "203.0.113.9"})
            return r1, r2, r3

    r1, r2, r3 = asyncio.run(_kos())
    assert r1.status_code == 200 and r1.json()["token"], r1.text
    assert r2.json()["token"] == r1.json()["token"]
    assert r3.status_code == 403
