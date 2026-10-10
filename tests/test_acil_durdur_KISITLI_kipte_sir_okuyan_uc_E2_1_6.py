# -*- coding: utf-8 -*-
"""E2-1.6 (2-E incelemesi, A1) — DB'siz KISITLI kipte (sır dosyası okunamıyor — D2.80 / Y9) kimliksiz, tünelden de erişilen
`POST /api/auth/exchange` ve `POST /api/auth/reset` `get_secret`'i OLAY DÖNGÜSÜNDE eşzamanlı çağırır; önbellek dolmadığı için
çağrı diske iner ve (60 sn geri çekilme dolmuşsa) `_ensure_dir_hardened` → `icacls`'i (10 sn zaman aşımı) döngüde koşturur.
`icacls` asılırsa (AV / kilitli tutamak — E-3 zaman aşımının nedeni) döngü donar: o sırada gelen ACİL DURDUR'un STOP'u porta
ancak döngü çözülünce gider (Ö.4-Y8: gecikme de kapılanmadır).

Ölçüm TEK olay döngüsünde (httpx ASGITransport + asyncio.run), O-1.1 aparatı (GERÇEK HeadlessCore/HWSender/HardwareController,
porta yazılan baytlar firmware aynasıyla çözülür). Kısıtlı kip GERÇEK ACL (sır dosyası yalnız LOCAL SERVICE'e açık). Arıza EN ALT
katta: `subprocess.run(["icacls", …], timeout=10)` ASILI_S sn bekleyip `TimeoutExpired` yükseltir. ACİL DURDUR, eşleştirme/sıfırlama
işleyicisi döngüyü dondurduktan SONRA gönderilir (istemci niyeti t_niyet; TCP'de bekleyen istek gibi).
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import time

import pytest
from test_O11_STOP_yollari_ORTAK_HAVUZA_bagli_DEGIL import _bobin1_sur, _ilk_stop_stm, _seanssiz, aparat  # noqa: F401

ASILI_S = 3.0  # üretimde en çok 10 sn (file_acl timeout); gecikme bu süreyle orantılı
SINIR_S = 1.0
_GERCEK_RUN = subprocess.run

_UCLAR = {
    "eslestirme": ("/api/auth/exchange", {"code": "YANLIS1"}),
    "sifre_sifirlama": (
        "/api/auth/reset",
        {"email": "x@ornek.com", "admin_code": "YANLIS-KOD", "new_password": "Abcdefg1"},
    ),
}


@pytest.fixture
def kisitli(tmp_path, monkeypatch):
    from utils import secrets_manager as sm

    veri = tmp_path / "kisitli" / "PEMF_GUI"
    veri.mkdir(parents=True)
    p = veri / "pemf_secrets.json"
    p.write_text(json.dumps({"auto": {"pairing_code": "SAHTE1"}, "operator": {}, "embedded": {}}), encoding="utf-8")
    r = _GERCEK_RUN(["icacls", str(p), "/inheritance:r", "/grant:r", "*S-1-5-19:(F)"], capture_output=True, timeout=60)
    assert r.returncode == 0, r
    monkeypatch.setattr(sm, "_data_dir", lambda: veri)
    monkeypatch.setattr(sm, "_cache", None)
    monkeypatch.setattr(sm, "_dir_hardened", False)
    monkeypatch.setattr(sm, "_sertlestirme_sonraki", 0.0)
    monkeypatch.setattr(sm, "_tekrar_gunluk", {})
    try:
        with pytest.raises(PermissionError):
            p.read_bytes()  # aparat kanıtı: gerçek erişim reddi
        yield sm
    finally:
        _GERCEK_RUN(["icacls", str(tmp_path / "kisitli"), "/reset", "/T", "/C", "/Q"], capture_output=True, timeout=60)
        assert p.read_bytes(), "aparat: erişim geri gelmedi"


def _asili_icacls(monkeypatch, sayac):
    import utils.file_acl as fa

    def _run(args, *a, **k):
        if isinstance(args, (list, tuple)) and args and str(args[0]).lower() == "icacls":
            sayac["n"] += 1
            time.sleep(ASILI_S)
            raise subprocess.TimeoutExpired(args, k.get("timeout", 10))
        return _GERCEK_RUN(args, *a, **k)

    monkeypatch.setattr(fa.subprocess, "run", _run)


def _deneme(o, sm, uc):
    import httpx

    _bobin1_sur(o)
    _seanssiz(o, 0)
    sm._sertlestirme_sonraki = 0.0  # geri çekilme süresi DOLMUŞ (60 sn'de bir olan an)

    async def _kos():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=o.api.app), base_url="http://cihaz") as c:
            await asyncio.sleep(0.03)
            t_niyet = time.perf_counter() + 0.05

            async def _estop_niyette():
                await asyncio.sleep(max(0.0, t_niyet - time.perf_counter()))
                while time.perf_counter() < t_niyet:  # Windows zamanlayıcısı ~15 ms erken uyandırabilir
                    await asyncio.sleep(0)
                return await c.post("/api/hardware/emergency_stop")

            gorev = None
            if uc:
                yol, govde = _UCLAR[uc]
                gorev = asyncio.ensure_future(c.post(yol, json=govde))
            es = asyncio.ensure_future(_estop_niyette())
            r = await asyncio.wait_for(es, timeout=ASILI_S + 10)
            yanit_s = time.perf_counter() - t_niyet
            ts = None
            son = time.perf_counter() + ASILI_S + 2
            while time.perf_counter() < son and (ts := _ilk_stop_stm(o, t_niyet)) is None:
                await asyncio.sleep(0.01)
            if gorev is not None:
                await gorev
            return r.status_code, round(yanit_s, 3), (None if ts is None else round(ts - t_niyet, 3))

    return asyncio.run(_kos())


@pytest.mark.parametrize("uc", list(_UCLAR))
def test_KRITIK_kisitli_kipte_sir_okuyan_kimliksiz_uc_ACIL_DURDURU_BEKLETMEZ_E2_1_6(aparat, kisitli, monkeypatch, uc):
    sayac = {"n": 0}
    _asili_icacls(monkeypatch, sayac)
    sonuc = [_deneme(aparat, kisitli, uc) for _ in range(3)]
    print(f"OLCUM E2-1.6 uc={uc} icacls={sayac['n']} (kod, yanit_s, ilk_STOP_s)={sonuc}")
    assert sayac["n"] >= 1, "aparat: asılı icacls hiç çağrılmadı (kısıtlı kip / geri çekilme kurulmadı)"
    kotu = [s for s in sonuc if s[0] != 200 or s[1] >= SINIR_S or s[2] is None or s[2] >= SINIR_S]
    assert not kotu, (
        f"[{uc}] sır dosyası okunamazken asılı icacls (≤10 sn) olay döngüsünü dondurdu: ACİL DURDUR STOP'u {SINIR_S} sn içinde "
        f"porta gitmedi / yanıt dönmedi (kod, yanit_s, ilk_STOP_s): {kotu}"
    )


def test_KARSIT_kisitli_kip_ASILI_icacls_ama_sir_okuyan_istek_YOK_ACIL_DURDUR_hizli_E2_1_6(
    aparat, kisitli, monkeypatch
):
    """Aparat kanıtı: aynı kısıtlı kip + asılı icacls, eşzamanlı sır okuyan istek yokken ACİL DURDUR < 1 sn."""
    sayac = {"n": 0}
    _asili_icacls(monkeypatch, sayac)
    sonuc = [_deneme(aparat, kisitli, None) for _ in range(3)]
    assert all(s[0] == 200 and s[1] < SINIR_S and s[2] is not None and s[2] < SINIR_S for s in sonuc), sonuc
