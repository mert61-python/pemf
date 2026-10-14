# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.115 · B-4.10 — firmware'in geçici indirme dizini HER yolda silinir; eski firmware yedeği veri kökündeki kalıcı
`firmware_yedek` dizinine, tutma sınırıyla yazılır.

ÖLÇÜLEN KUSURLAR:
  * `firmware_manager.firmware_indir` `um._private_temp_path` ile `%TEMP%\\pemf_upd_*` dizini açıyor, indirme hatasında ve SHA
    uyuşmazlığında yalnız DOSYAYI siliyordu — dizin kalıyordu (1-H D1.110 önce-kırmızısında ölçüldü: her deneme bir dizin,
    10 deneme → 10 yetim dizin). Başarılı akışta da `_firmware_uygula` yalnız dosyayı siliyordu.
  * `yakma_akisi` yedeği `ikili.parent / "firmware_yedek"`e — yani o GEÇİCİ dizinin içine — yazıyordu (1-H D1.108
    önce-kırmızısı: yedek `…\\pemf_upd_*\\firmware_yedek\\`): elle kurtarmada gereken eski firmware'in yeri yalnız INFO
    günlüğünde kalıyor, geçici dizinle birlikte kayboluyordu.

KAPI (GERÇEK `firmware_indir` / `acilis_denetimi` → `_firmware_uygula` → `yakma_akisi`; ağ = yamalı `_pinli_ac`,
yakıcı SAHTE `_kos`; gerçek ağ/yakıcı YOK):
  (a) SHA uyuşmazlığı ve (b) indirme hatası sonrası açılan `pemf_upd_*` dizini YOK;
  (c) başarılı akışta indirme dizini YOK, yedek `<veri kökü>/firmware_yedek/` altında (geçici dizinde DEĞİL);
  (d) tutma sınırı: önceden 7 yedek varken akıştan sonra `FIRMWARE_YEDEK_TUT` kadar kalır, en yenisi (bu akışınki) dahil.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import io
import urllib.error
from pathlib import Path

import pytest

GECERLI = "https://github.com/mert61-python/pemf-update/releases/download/fw-2.4.0/pemf_fw.bin"
GOVDE = b"PEMF-FW-2.4.0" * 80


class _Yanit(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


@pytest.fixture()
def fm(monkeypatch, tmp_path):
    m = importlib.import_module("servers.firmware_manager")
    importlib.reload(m)
    acilan: list[Path] = []
    orj = m.um._private_temp_path

    def _kayitli(ad):
        p = orj(ad)
        acilan.append(p.parent)
        return p

    monkeypatch.setattr(m.um, "_private_temp_path", _kayitli)
    m._test_acilan = acilan
    return m


def test_KRITIK_SHA_tutmazsa_gecici_dizin_SILINIR(fm, monkeypatch):
    monkeypatch.setattr(fm.um, "_pinli_ac", lambda url, timeout, headers=None: _Yanit(GOVDE))
    yol, hata = fm.firmware_indir(GECERLI, "ab" * 32)
    assert yol is None and "SHA256" in hata, hata
    assert fm._test_acilan, "aparat: geçici dizin açılmadı (kapı kör)"
    kalan = [str(d) for d in fm._test_acilan if d.exists()]
    assert not kalan, (
        f"SHA uyuşmazlığından sonra geçici indirme dizini KALDI: {kalan} (her deneme %TEMP%'e yetim bırakır)"
    )


def test_KRITIK_indirme_HATASINDA_gecici_dizin_SILINIR(fm, monkeypatch):
    def _hata(url, timeout, headers=None):
        raise urllib.error.URLError("D1.115 kapisi: ag YOK")

    monkeypatch.setattr(fm.um, "_pinli_ac", _hata)
    yol, hata = fm.firmware_indir(GECERLI, hashlib.sha256(GOVDE).hexdigest())
    assert yol is None, hata
    assert fm._test_acilan, "aparat: geçici dizin açılmadı (kapı kör)"
    kalan = [str(d) for d in fm._test_acilan if d.exists()]
    assert not kalan, f"indirme hatasından sonra geçici indirme dizini KALDI: {kalan}"


@pytest.fixture()
def akis(fm, monkeypatch, tmp_path):
    from servers import api_server as api
    from servers import live_state as ls
    from utils import path_utils

    sy = importlib.import_module("utils.stm_yakma")
    veri = tmp_path / "veri"
    veri.mkdir()
    monkeypatch.setattr(path_utils, "get_app_data_directory", lambda: str(veri))
    ozet = hashlib.sha256(GOVDE).hexdigest()
    manifest = {
        "firmware": {"stm32": {"version": "2.4.0", "url": GECERLI, "sha256": ozet}},
        "uyumluluk": [{"clientMin": "", "firmwareMin": "2.4.0"}],
    }
    monkeypatch.setattr(fm, "manifest_oku", lambda **_k: manifest)
    monkeypatch.setattr(fm.um, "get_current_version", lambda: "1.9.51")
    monkeypatch.setattr(fm.um, "get_status", lambda: {"previousStable": None})
    monkeypatch.setattr(fm.um, "_pinli_ac", lambda url, timeout, headers=None: _Yanit(GOVDE))
    yedekler: list[Path] = []

    def _sahte_kos(cli, argumanlar, timeout=300.0):
        if "-r" in argumanlar:
            p = Path(argumanlar[-1])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"ESKI-FW-2.3.0")
            yedekler.append(p)
        return 0, ""

    monkeypatch.setattr(sy, "programmer_cli", lambda: Path("sahte_cli.exe"))
    monkeypatch.setattr(sy, "_kos", _sahte_kos)
    # TD1-e: yakma sonrası geri okuma + yeniden başlatma BU kapının konusu değil (başarılı — gerçek çıktı uzayından); gerçek akış EN ALT katta: test_TD1_yakma_ve_kimlik_betigi_KANITLA (flash öykünmesi).
    monkeypatch.setattr(sy, "geri_oku", lambda _c, _i, _h: (True, "geri okuma: (aparat) bayt bayt AYNI"))
    monkeypatch.setattr(sy, "baslat", lambda _c: (True, ""))
    monkeypatch.setattr(
        sy,
        "banner_dogrula",
        lambda *a, **k: (
            True,
            "uyumlu",
            "-> STM_READY: DDS v2.4.0 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) Waiting for commands...",
        ),
    )
    monkeypatch.setattr(sy.time, "sleep", lambda _s: None)
    monkeypatch.setitem(api._active_session, "is_active", False)
    monkeypatch.setattr(api.state, "hardware", None)
    with ls._live_state_lock:
        eski_bobin = copy.deepcopy(ls._live_state["coils"])
        for c in ls._live_state["coils"].values():
            c["running"] = False
    try:
        yield {"fm": fm, "sy": sy, "veri": veri, "yedekler": yedekler}
    finally:
        with ls._live_state_lock:
            ls._live_state["coils"].clear()
            ls._live_state["coils"].update(eski_bobin)


def test_KRITIK_basarili_akista_indirme_dizini_YOK_yedek_VERI_KOKUNDE(akis):
    a = akis
    d = a["fm"].acilis_denetimi(firmware_surum="2.3.0", stm_bagli=True, uygula=True)
    assert d["uygulandi"] is True, d
    kalan = [str(p) for p in a["fm"]._test_acilan if p.exists()]
    assert not kalan, f"başarılı akıştan sonra geçici indirme dizini KALDI: {kalan}"
    assert len(a["yedekler"]) == 1, a["yedekler"]
    hedef = a["veri"] / "firmware_yedek"
    assert a["yedekler"][0].parent == hedef, (
        f"yedek {a['yedekler'][0]} — veri kökündeki kalıcı {hedef} altında DEĞİL (geçici dizinle birlikte kaybolur; elle "
        "kurtarmada gereken eski firmware bulunamaz)"
    )
    assert a["yedekler"][0].exists(), "yedek dosyası akıştan sonra silinmiş"


def test_KRITIK_yedek_TUTMA_siniri_en_yenisi_dahil(akis):
    a = akis
    kok = a["veri"] / "firmware_yedek"
    kok.mkdir()
    for i in range(7):
        (kok / f"pemf_yedek_2026010{i}_000000.bin").write_bytes(b"ESKI")
    a["fm"].acilis_denetimi(firmware_surum="2.3.0", stm_bagli=True, uygula=True)
    tut = getattr(a["fm"], "FIRMWARE_YEDEK_TUT", None)
    assert isinstance(tut, int) and 1 <= tut <= 10, f"tutma sınırı tanımsız/anlamsız: {tut!r}"
    kalan = sorted(p.name for p in kok.glob("pemf_yedek_*.bin"))
    assert len(kalan) == tut, f"tutma sınırı uygulanmadı: {len(kalan)} yedek ({kalan})"
    assert a["yedekler"][0].name in kalan, "en YENİ yedek (bu akışınki) silindi — geri dönüş/elle kurtarma onu ister"


def test_KRITIK_H51_yakma_akisi_ISTISNA_firlatirsa_gecici_dizin_YINE_silinir(akis, monkeypatch):
    """H-5.1 (1-H incelemesi): "HER yolda silinir" iddiasının İSTİSNA kolu kapısızdı — `_firmware_uygula`'da `_gecici_sil`
    `finally` dışına alınınca firmware zincirinin 93 testi yeşil kaldı. Yakma akışı fırlatırsa (ör. `firmware_yedek` dizini
    yazılamıyor) indirilen ikilinin `pemf_upd_*` dizini kalmamalı."""
    a = akis

    def _yedek_yazilamaz(cli, hedef, boyut):
        raise PermissionError(13, "firmware_yedek dizini yazılamıyor (sahte)")

    monkeypatch.setattr(a["sy"], "yedek_al", _yedek_yazilamaz)
    with pytest.raises(PermissionError):
        a["fm"].acilis_denetimi(firmware_surum="2.3.0", stm_bagli=True, uygula=True)
    assert a["fm"]._test_acilan, "aparat: geçici dizin açılmadı (kapı kör)"
    kalan = [str(d) for d in a["fm"]._test_acilan if d.exists()]
    assert not kalan, f"yakma akışı istisnayla bitti ama geçici indirme dizini KALDI: {kalan}"
