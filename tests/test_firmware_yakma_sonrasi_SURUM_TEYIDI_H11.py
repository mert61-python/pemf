# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""H-1.1 (1-H bağımsız incelemesi) — oto-firmware "uygulandı" ve `firmwareSurum` ÖLÇÜLENİ söyler: kartın yakmadan SONRA
kendi bastığı banner'ın sürümü (D1.120 `stm32_kimlik.firmware_surumu`), planın hedef sürümü DEĞİL.

ÖLÇÜLEN KUSUR (inceleme `kayit/kt_dongu.json`, GERÇEK `backend_service.main()` çocuk süreçte, iki ardışık açılış AYNI veri
köküyle; sahte STM + sahte yakıcı): uyum varlığı `firmware.stm32.version = 2.4` diyor, yakılan ikilinin banner'ı ise `DDS v2.3`
(main.c'deki sürüm dizesi 2026-09'dan beri 5-ch / 7-ch / karma bütün revizyonlarda `v2.3` — hiç artırılmadı). Yakmadan
sonra `durum()` → `uygulandi=True, firmwareSurum='2.4'` (kart 2.3 dedi) ve İKİNCİ açılış AYNI ikiliyi YENİDEN yaktı (her açılış
yedek + yakma). `_firmware_uygula` TAMAM'da `firmwareSurum=plan.hedef_surum` yazıyordu — ölçülmemiş sürüm ölçülmüş gibi.

KAPI (GERÇEK `acilis_denetimi` → `_firmware_uygula` → `yakma_akisi`; SAHTE yakıcı `_kos`, SAHTE banner kaynağı — çekirdek
okuyucusu yerine; gerçek seri port / yakıcı YOK):
  * yakılan ikilinin banner'ı UYUMLU ama sürümü hedeften farklı → `uygulandi=False`, `firmwareSurum` = kartın söylediği,
    `hata` "hedef sürümü bildirmedi" der;
  * KARŞIT: banner hedef sürümü söylüyor → `uygulandi=True`, `firmwareSurum` = kartın söylediği (`2.4.0` ≡ `2.4`).
"""

from __future__ import annotations

import copy
import hashlib
import importlib
from pathlib import Path

import pytest

#: TD1 · Y68: yakılan (yeni) firmware paket boyunu BEYAN eder; beyansız `uni=` banner'ı 120 / 121'i ayırt edemez (None).
BANNER_FMT = "-> STM_READY: DDS v{} (7-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt=121 Waiting for commands..."


class _Kaynak:
    """Çekirdek okuyucusunun yerine: `-w`'den sonra kartın basacağı banner."""

    def __init__(self, banner):
        self.banner = banner
        self.sayac = 0

    def ver(self):
        self.sayac += 1

    def isaret(self):
        return self.sayac

    def bekle(self, isaret, sure):
        return self.banner if self.sayac > isaret else None


@pytest.fixture()
def zincir(monkeypatch, tmp_path):
    from servers import api_server as api
    from servers import live_state as ls

    fm = importlib.import_module("servers.firmware_manager")
    importlib.reload(fm)
    sy = importlib.import_module("utils.stm_yakma")
    ikili = tmp_path / "pemf_fw.bin"
    ikili.write_bytes(b"PEMF-FW-2.4" * 97)
    ozet = hashlib.sha256(ikili.read_bytes()).hexdigest()
    manifest = {
        "firmware": {
            "stm32": {
                "version": "2.4",
                "url": "https://github.com/mert61-python/pemf-update/releases/download/fw-2.4/pemf_fw.bin",
                "sha256": ozet,
            }
        },
        "uyumluluk": [{"clientMin": "", "clientMax": "", "firmwareMin": "2.4", "firmwareMax": ""}],
    }
    monkeypatch.setattr(fm, "manifest_oku", lambda **_k: copy.deepcopy(manifest))
    monkeypatch.setattr(fm.um, "get_current_version", lambda: "1.9.51")
    sayac = [0]

    def _indir(url, sha):  # akış indirilen dosyayı yakmadan sonra siler → her çağrıda TAZE kopya
        sayac[0] += 1
        hedef = tmp_path / f"indir{sayac[0]}" / "pemf_fw.bin"
        hedef.parent.mkdir()
        hedef.write_bytes(ikili.read_bytes())
        return hedef, ""

    monkeypatch.setattr(fm, "firmware_indir", _indir)
    monkeypatch.setattr(fm, "_yedek_dizini", lambda: tmp_path / "firmware_yedek")
    monkeypatch.setattr(sy, "programmer_cli", lambda: Path("sahte_yakici.exe"))
    monkeypatch.setitem(api._active_session, "is_active", False)
    monkeypatch.setattr(api.state, "hardware", None)
    with ls._live_state_lock:
        eski_bobin = copy.deepcopy(ls._live_state["coils"])
        for c in ls._live_state["coils"].values():
            c["running"] = False
    try:
        yield {"fm": fm, "sy": sy, "mp": monkeypatch}
    finally:
        with ls._live_state_lock:
            ls._live_state["coils"].clear()
            ls._live_state["coils"].update(eski_bobin)


def _kos(z, kaynak):
    cagri: list[str] = []

    def _sahte_kos(cli, argumanlar, timeout=300.0):
        if "-r" in argumanlar:
            cagri.append("yedek")
            Path(argumanlar[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(argumanlar[-1]).write_bytes(b"ESKI-FW")
            return 0, ""
        cagri.append("yak")
        kaynak.ver()
        return 0, ""

    z["mp"].setattr(z["sy"], "_kos", _sahte_kos)
    # TD1-e: yakma sonrası geri okuma + yeniden başlatma BU kapının konusu değil (başarılı — gerçek çıktı uzayından); gerçek akış EN ALT katta: test_TD1_yakma_ve_kimlik_betigi_KANITLA (flash öykünmesi).
    z["mp"].setattr(z["sy"], "geri_oku", lambda _c, _i, _h: (True, "geri okuma: (aparat) bayt bayt AYNI"))
    z["mp"].setattr(z["sy"], "baslat", lambda _c: (True, ""))
    d = dict(z["fm"].acilis_denetimi(firmware_surum="2.3", stm_bagli=True, uygula=True, banner_kaynagi=kaynak))
    return cagri, d


def test_KRITIK_H11_yakilan_ikili_HEDEF_SURUMU_soylemezse_UYGULANDI_denmez_olculen_surum_yazilir(zincir):
    cagri, d = _kos(zincir, _Kaynak(BANNER_FMT.format("2.3")))
    assert cagri == ["yedek", "yak"], f"aparat: yakma akışı koşmadı ({cagri})"
    assert d["eylem"] == zincir["fm"].su.FIRMWARE_GUNCELLE and d["hedefSurum"] == "2.4", f"aparat: plan {d}"
    assert d["uygulandi"] is False, (
        f"kart yakmadan sonra 'DDS v2.3' dedi (hedef 2.4) ama durum 'UYGULANDI' diyor — ölçülmemiş başarı: {d}"
    )
    assert d["firmwareSurum"] == "2.3", f"firmwareSurum kartın SÖYLEDİĞİ değil (planın hedefi yazılmış): {d}"
    assert "hedef sürümü bildirmedi" in d["hata"] and "2.4" in d["hata"] and "2.3" in d["hata"], d["hata"]


def test_KARSIT_H11_banner_HEDEF_surumu_soylerse_uygulandi_ve_olculen_surum(zincir):
    cagri, d = _kos(zincir, _Kaynak(BANNER_FMT.format("2.4.0")))
    assert cagri == ["yedek", "yak"], cagri
    assert d["uygulandi"] is True and d["hata"] == "", d
    assert d["firmwareSurum"] == "2.4.0", f"firmwareSurum kartın söylediği olmalı: {d}"
