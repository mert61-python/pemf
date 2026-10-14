# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.112 · B-4.7 — geri dönüş yakması BAŞARISIZSA ayrı sonuç kodu; geri dönülen firmware'in kimliği DOĞRULANIR.

ÖLÇÜLEN KUSUR: `stm_yakma.yakma_akisi` uyumsuz banner'da `yak(cli, yedek)`'in sonucunu yalnız adım METNİNE yazıyor
("GERİ DÖNÜŞ: BAŞARISIZ") ve HER durumda `UYUMSUZ_GERI_DONULDU` (8) dönüyordu; geri dönüşten sonra kartın kimliği HİÇ
okunmuyordu. Kart ne yeni ne eski firmware'le doğrulanmışken (`firmware_manager.durum()['hata']` iki kolda da "[8] …")
durum "geri dönüldü" ile birebir aynı görünüyordu — destek kartın elle (ST-Link) kurtarılması gerektiğini göremezdi.

KAPI (GERÇEK `acilis_denetimi` → `_firmware_uygula` → `yakma_akisi`; SAHTE yakıcı `_kos`, SAHTE banner kaynağı — çekirdek
okuyucusu yerine; gerçek seri port / yakıcı YOK):
  * geri dönüş rc≠0 → `GERI_DONUS_BASARISIZ`; `durum()['hata']` rc=0 kolundan FARKLI ve elle kurtarmayı söyler;
  * geri dönüş rc=0 ama banner gelmez → `GERI_DONUS_DOGRULANAMADI`;
  * geri dönüş rc=0 + banner → `UYUMSUZ_GERI_DONULDU` ve kimlik İKİ kez okunmuş (yakma sonrası + geri dönüş sonrası).
CLI yolu (`banner_kaynagi` yok → `banner_dogrula`) için de rc≠0 kolu ayrı kodla ölçülür.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
from pathlib import Path

import pytest

YENI_UYUMSUZ = "-> STM_READY: 2.4.0 (5-ch + HW_SYNC@PB1) Waiting for commands..."
ESKI = "-> STM_READY: 2.3.0 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) Waiting for commands..."


class _Kaynak:
    """Çekirdek okuyucusunun yerine: her `-w`'den sonra verilecek banner sırası (None = banner gelmez)."""

    def __init__(self, sira):
        self.sira = list(sira)
        self.sayac = 0
        self.son = None
        self.okuma = 0

    def ver(self):
        b = self.sira.pop(0) if self.sira else None
        if b is not None:
            self.sayac += 1
            self.son = b

    def isaret(self):
        return self.sayac

    def bekle(self, isaret, sure):
        self.okuma += 1
        return self.son if self.sayac > isaret else None


@pytest.fixture()
def zincir(monkeypatch, tmp_path):
    from servers import api_server as api
    from servers import live_state as ls

    fm = importlib.import_module("servers.firmware_manager")
    importlib.reload(fm)
    sy = importlib.import_module("utils.stm_yakma")
    ikili = tmp_path / "pemf_fw.bin"
    ikili.write_bytes(b"PEMF-FW-2.4.0" * 95)
    ozet = hashlib.sha256(ikili.read_bytes()).hexdigest()
    manifest = {
        "firmware": {
            "stm32": {"version": "2.4.0", "url": "https://github.com/mert61-python/pemf-update/x", "sha256": ozet}
        },
        "uyumluluk": [{"clientMin": "", "firmwareMin": "2.4.0"}],
    }
    monkeypatch.setattr(fm, "manifest_oku", lambda **_k: manifest)
    monkeypatch.setattr(fm.um, "get_current_version", lambda: "1.9.51")
    monkeypatch.setattr(fm.um, "get_status", lambda: {"previousStable": None})
    sayac = [0]

    def _indir(url, sha):  # her akış indirilen dosyayı siler (yakmadan sonra) → her çağrıda TAZE kopya
        sayac[0] += 1
        hedef = tmp_path / f"indir{sayac[0]}" / "pemf_fw.bin"
        hedef.parent.mkdir()
        hedef.write_bytes(ikili.read_bytes())
        return hedef, ""

    monkeypatch.setattr(fm, "firmware_indir", _indir)
    monkeypatch.setattr(sy, "programmer_cli", lambda: Path("sahte_cli.exe"))
    monkeypatch.setitem(api._active_session, "is_active", False)
    monkeypatch.setattr(api.state, "hardware", None)
    with ls._live_state_lock:
        eski_bobin = copy.deepcopy(ls._live_state["coils"])
        for c in ls._live_state["coils"].values():
            c["running"] = False
    try:
        yield {"fm": fm, "sy": sy, "ikili": ikili, "mp": monkeypatch}
    finally:
        with ls._live_state_lock:
            ls._live_state["coils"].clear()
            ls._live_state["coils"].update(eski_bobin)


def _yakici(z, kaynak, geri_rc: int):
    kos: list[str] = []

    def _sahte_kos(cli, argumanlar, timeout=300.0):
        if "-r" in argumanlar:
            kos.append("yedek")
            Path(argumanlar[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(argumanlar[-1]).write_bytes(b"ESKI-FW-2.3.0")
            return 0, ""
        hedef = Path(argumanlar[argumanlar.index("-w") + 1])
        if hedef.read_bytes() == z["ikili"].read_bytes():
            kos.append("yak:yeni")
            if kaynak is not None:
                kaynak.ver()
            return 0, ""
        kos.append("yak:yedek")
        if geri_rc != 0:
            return geri_rc, "Error: target not found (sahte)"
        if kaynak is not None:
            kaynak.ver()
        return 0, ""

    z["mp"].setattr(z["sy"], "_kos", _sahte_kos)
    # TD1-e: yakma sonrası geri okuma + yeniden başlatma BU kapının konusu değil (başarılı — gerçek çıktı uzayından); gerçek akış EN ALT katta: test_TD1_yakma_ve_kimlik_betigi_KANITLA (flash öykünmesi).
    z["mp"].setattr(z["sy"], "geri_oku", lambda _c, _i, _h: (True, "geri okuma: (aparat) bayt bayt AYNI"))
    z["mp"].setattr(z["sy"], "baslat", lambda _c: (True, ""))
    return kos


def _calistir(z, kaynak):
    return z["fm"].acilis_denetimi(firmware_surum="2.3.0", stm_bagli=True, uygula=True, banner_kaynagi=kaynak)


def test_KRITIK_geri_donus_YAKILAMAZSA_ayri_kod_ve_hata_FARKLI(zincir):
    z = zincir
    kaynak_ok = _Kaynak([YENI_UYUMSUZ, ESKI])
    kos_ok = _yakici(z, kaynak_ok, geri_rc=0)
    d_ok = dict(_calistir(z, kaynak_ok))
    assert kos_ok == ["yedek", "yak:yeni", "yak:yedek"], kos_ok

    kaynak_kotu = _Kaynak([YENI_UYUMSUZ])  # `acilis_denetimi` durumu her çağrıda yeniden yazar
    kos_kotu = _yakici(z, kaynak_kotu, geri_rc=1)
    d_kotu = dict(_calistir(z, kaynak_kotu))
    assert kos_kotu == ["yedek", "yak:yeni", "yak:yedek"], kos_kotu
    assert f"[{z['sy'].UYUMSUZ_GERI_DONULDU}]" not in d_kotu["hata"], (
        f"geri dönüş YAKILAMADI ama durum 'geri dönüldü' ile AYNI: {d_kotu['hata']!r} (rc=0 kolu: {d_ok['hata']!r})"
    )
    assert f"[{getattr(z['sy'], 'GERI_DONUS_BASARISIZ', -1)}]" in d_kotu["hata"], d_kotu
    assert d_kotu["hata"] != d_ok["hata"]
    assert "ST-Link" in d_kotu["hata"], f"elle kurtarma söylenmiyor: {d_kotu['hata']!r}"


def test_KRITIK_geri_donus_sonrasi_banner_GELMEZSE_dogrulanamadi(zincir):
    z = zincir
    kaynak = _Kaynak([YENI_UYUMSUZ, None])
    _yakici(z, kaynak, geri_rc=0)
    z["mp"].setattr(z["sy"], "BANNER_SURESI", 0.2)
    d = _calistir(z, kaynak)
    assert f"[{getattr(z['sy'], 'GERI_DONUS_DOGRULANAMADI', -1)}]" in d["hata"], (
        f"geri dönüşten sonra kart kimliği okunmadı ama durum: {d['hata']!r}"
    )


def test_KRITIK_geri_donulen_firmware_KIMLIGI_okunur(zincir):
    z = zincir
    kaynak = _Kaynak([YENI_UYUMSUZ, ESKI])
    _yakici(z, kaynak, geri_rc=0)
    d = _calistir(z, kaynak)
    assert f"[{z['sy'].UYUMSUZ_GERI_DONULDU}]" in d["hata"], d
    assert kaynak.okuma == 2, f"kart kimliği yakma + geri dönüş sonrası İKİ kez okunmalıydı, {kaynak.okuma} kez okundu"


def test_KRITIK_CLI_yolunda_da_geri_donus_YAKILAMAZSA_ayri_kod(zincir, tmp_path):
    z = zincir
    sy = z["sy"]
    _yakici(z, None, geri_rc=1)
    z["mp"].setattr(sy, "banner_dogrula", lambda *a, **k: (False, "kart 5 kanalli", YENI_UYUMSUZ))
    z["mp"].setattr(sy.time, "sleep", lambda _s: None)
    s = sy.yakma_akisi(z["ikili"], guvenlik_kontrolu=lambda: (True, "t"), yedek_dizin=tmp_path / "y")
    assert s.kod == getattr(sy, "GERI_DONUS_BASARISIZ", -1), s
