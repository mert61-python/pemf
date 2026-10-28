# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.73 · B-10.193 — oto-firmware açılış denetiminin HER dalının sonucu `/api/health` → `firmwareGuncelleme`de görünür.

🔴 ÖLÇÜLEN DURUM (HEAD ebf1c3fe, D67): beyan D1.116 (`a310da87`) ile gerçekleşmiş — `system_router.py` `firmwareGuncelleme =
firmware_manager.durum()` (yerel/LAN istemci). AMA kapı KÖR: D1.116 kapısı durumu `fm._durum_yaz(...)` ile ELLE yazıp sağlık ucunu
okuyor; H-1.2 kapısı `acilis_denetimi`nin DÖNÜŞ değerine bakıyor. Bir dalda dönüşü kurup `_durum_yaz`ı atlayan mutant (dal sonucu
döner ama sağlık ucuna YAZILMAZ) 11 firmware kapı dosyasının HEPSİNDE yeşil kaldı (135 passed): "manifest okunamadı → BEKLE" dalı
ve yakma sonucu dalı (`[kod] özet`).
KAPI (planın yöntemi): `PEMF_FW_AUTO_UPDATE` kapalı (klonda koşucusu 0) + SAHTE yakıcı (`utils.stm_yakma._kos` — EN ALT kat; aparat
`test_firmware_yakma_sonrasi_SURUM_TEYIDI_H11`) ile `acilis_denetimi`nin bir dalı koşulur, ardından GERÇEK `/api/health` (TestClient,
loopback istemci) çağrılır: `firmwareGuncelleme` o dalın eylem / gerekçe / sonuç alanlarını taşımalı. Dallar: manifest yok (BEKLE),
bayrak kapalı karar (yakılmadı), yakma sonrası sürüm teyidi tutmadı, yakma başarılı, yakıcı hatası, aynı SHA ikinci kez (Y80).
⚠️ oto-firmware bayrağı AÇILMAZ — `uygula=True` yalnız sahte yakıcıyla, süreç içinde.
"""

from __future__ import annotations

import pytest
from test_firmware_yakma_sonrasi_SURUM_TEYIDI_H11 import BANNER_FMT, _Kaynak, _kos, zincir  # noqa: F401 — fikstür

ALANLAR = ("kontrol_edildi", "eylem", "gerekce", "uygulandi", "hata", "firmwareSurum", "hedefSurum")


def _saglik_firmware() -> dict:
    from fastapi.testclient import TestClient
    from servers import api_server as api

    r = TestClient(api.app, client=("127.0.0.1", 50173)).get("/api/health")
    assert r.status_code == 200, r.text
    fg = r.json().get("firmwareGuncelleme")
    assert isinstance(fg, dict), f"/api/health firmwareGuncelleme yok: {fg!r}"
    return fg


def _ayni_mi(dal: str, d: dict) -> None:
    fg = _saglik_firmware()
    farkli = {k: (d.get(k), fg.get(k)) for k in ALANLAR if d.get(k) != fg.get(k)}
    assert not farkli, f"[{dal}] açılış denetiminin sonucu /api/health'e YAZILMADI (dal dönüşü ↔ sağlık ucu): {farkli}"


def test_KRITIK_manifest_OKUNAMADI_dali_saglikta_BEKLE(zincir):
    z = zincir
    z["mp"].setattr(z["fm"], "manifest_oku", lambda **_k: None)
    d = dict(z["fm"].acilis_denetimi(firmware_surum="2.3", stm_bagli=True, uygula=False))
    assert d["eylem"] == z["fm"].su.BEKLE and "manifest okunamadı" in d["gerekce"], f"aparat: dal {d}"
    _ayni_mi("manifest yok", d)


def test_KRITIK_bayrak_KAPALI_karari_saglikta(zincir):
    z = zincir
    cagri: list[str] = []
    z["mp"].setattr(z["sy"], "_kos", lambda *a, **k: cagri.append("kos") or (0, ""))
    d = dict(z["fm"].acilis_denetimi(firmware_surum="2.3", stm_bagli=True, uygula=False))
    assert cagri == [] and d["eylem"] == z["fm"].su.FIRMWARE_GUNCELLE, f"aparat: {d} {cagri}"
    _ayni_mi("bayrak kapalı", d)


@pytest.mark.parametrize("banner_surum,uygulandi", [("2.3", False), ("2.4.0", True)])
def test_KRITIK_yakma_sonucu_saglikta(zincir, banner_surum, uygulandi):
    cagri, d = _kos(zincir, _Kaynak(BANNER_FMT.format(banner_surum)))
    assert cagri == ["yedek", "yak"] and d["uygulandi"] is uygulandi, f"aparat: {cagri} {d}"
    _ayni_mi(f"yakma sonrası banner {banner_surum}", d)


def test_KRITIK_yakici_HATASI_saglikta(zincir):
    from pathlib import Path

    from stlink_sahte import listeli

    z = zincir

    def _sahte_kos(cli, argumanlar, timeout=300.0):
        if "-r" in argumanlar:
            Path(argumanlar[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(argumanlar[-1]).write_bytes(b"ESKI-FW")
            return 0, ""
        return 1, "Error: sahte yakici -w basarisiz (D6.73 kapisi)"

    z["mp"].setattr(z["sy"], "_kos", listeli(_sahte_kos))
    z["mp"].setattr(z["sy"], "geri_oku", lambda _c, _i, _h: (True, "geri okuma: (aparat) bayt bayt AYNI"))
    z["mp"].setattr(z["sy"], "baslat", lambda _c: (True, ""))
    d = dict(z["fm"].acilis_denetimi(firmware_surum="2.3", stm_bagli=True, uygula=True, banner_kaynagi=_Kaynak(None)))
    assert d["uygulandi"] is False and d["hata"], f"aparat: yakıcı hatası sonucu yok {d}"
    _ayni_mi("yakıcı hatası", d)


def test_KRITIK_ayni_SHA_IKINCI_kez_Y80_saglikta(zincir):
    _cagri, d1 = _kos(zincir, _Kaynak(BANNER_FMT.format("2.3")))
    assert d1["uygulandi"] is False, f"aparat: ilk deneme {d1}"
    cagri2, d2 = _kos(zincir, _Kaynak(BANNER_FMT.format("2.3")))
    assert cagri2 == [] and d2["uygulandi"] is False and d2["hata"] != d1["hata"], (
        f"aparat: Y80 dalı koşmadı {cagri2} {d2}"
    )
    _ayni_mi("aynı SHA ikinci kez (Y80)", d2)
