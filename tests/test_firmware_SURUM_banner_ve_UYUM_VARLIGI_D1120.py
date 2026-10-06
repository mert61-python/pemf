# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D1.120 · B-4.2 · Y17 — açılış, firmware sürümünü banner'dan AYRIŞTIRILABİLİR biçimde verir (`DDS v2.3` → `2.3`); uyum
kuralları `exe/latest.json`'dan DEĞİL, AYRI yayın varlığından okunur (404 = "kural yok", hata değil).

ÖLÇÜLEN KUSUR (1-H (a)0, `kayit/once_acilis_sonda.txt`): `_donanim_guncellemesi_safe` kartın beyan ettiği sürümü HAM
(`stm_kimlik.surum` = `DDS v2.3`) geçiriyordu → `surum_uyumu.surum_demeti('DDS v2.3')` None → kural olsa bile karar HER
açılışta "firmware sürümü ayrıştırılamadı" (EYLEM_YOK). Kurallar da kapalı eski EXE kanalının `exe/latest.json`
taslağından (B-4.25) okunuyordu — sahip Y17: AYRI varlık. ⚠️ Bu madde zinciri UYANDIRIR; Y1 gereği yakma yalnız açık
`PEMF_FW_AUTO_UPDATE=1` ile (karşıt kol: '0' / 'false' / yok → yakma 0).

KAPI: banner GERÇEK firmware biçim dizesinden (`main.c` `STM_READY` snprintf'i, yorumsuz kaynak) üretilir → GERÇEK
`stm32_kimlik.banner_ayristir` → GERÇEK `backend_service._donanim_guncellemesi_safe` (çekirdek taslağı: bağlı + kimlik) →
GERÇEK `firmware_manager.acilis_denetimi` → `_firmware_uygula`; manifest yamalı (ağ yok), indirme kayıtçı, yakıcı SAHTE. Y17:
GERÇEK `manifest_oku` yamalı pinli açıcıyla — istenen adres beklenen varlık (burada yazılı), 404 → kural yok.
"""

from __future__ import annotations

import io
import json
import logging
import re
import urllib.error
from pathlib import Path

import pytest
from c_soyucu import c_soy

KOK = Path(__file__).resolve().parents[1]
MAIN_C = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"
#: Y17 varlığı — beklenen adres BURADA yazılı (mutasyon hedefinden okunmaz).
VARLIK_YOLU = "/mert61-python/pemf-update/releases/download/firmware-uyum/firmware_uyum.json"
KURALLI = {
    "firmware": {
        "stm32": {
            "version": "2.4",
            "url": "https://github.com/mert61-python/pemf-update/releases/download/fw-2.4/pemf_fw.bin",
            "sha256": "ab" * 32,
        }
    },
    "uyumluluk": [{"clientMin": "", "clientMax": "", "firmwareMin": "2.4", "firmwareMax": ""}],
}


def saha_banneri() -> str:
    """Firmware'in GERÇEK biçim dizesinden (yorumsuz main.c) 7 kanal · KARMA · 0x60 banner'ı (sahadaki kart, Y7)."""
    soy = c_soy(MAIN_C.read_text(encoding="utf-8"))
    m = re.search(r'"(-> STM_READY: DDS v[^"]*)"', soy)
    assert m, "main.c'de (yorum dışı) STM_READY biçim dizesi yok"
    return (m.group(1).replace("\\r\\n", "") % (7, "KARMA", 0x60)).strip()


class _Cekirdek:
    def __init__(self, kimlik):
        self.stm_is_connected = True
        self.stm_kimlik = kimlik


@pytest.fixture
def zincir(monkeypatch, tmp_path):
    import utils.stm_yakma as sy
    from servers import firmware_manager as fm

    monkeypatch.setattr(fm, "manifest_oku", lambda timeout=15.0: json.loads(json.dumps(KURALLI)))
    monkeypatch.setattr(fm.um, "get_current_version", lambda: "1.9.51")
    ikili = tmp_path / "pemf_fw.bin"
    ikili.write_bytes(b"\x00" * 64)
    kayit = {"indir": [], "yak": []}
    monkeypatch.setattr(fm, "firmware_indir", lambda url, sha: kayit["indir"].append(url) or (ikili, ""))
    monkeypatch.setattr(fm, "_yedek_dizini", lambda: tmp_path / "yedek")
    monkeypatch.setattr(fm, "_gecici_sil", lambda yol: None)

    def _sahte_yak(yol, **k):
        kayit["yak"].append(str(yol))
        return sy.Sonuc(sy.TAMAM, "sahte yakıcı", adimlar=["sahte"])

    monkeypatch.setattr(sy, "yakma_akisi", _sahte_yak)
    monkeypatch.setattr(sy, "programmer_cli", lambda: None)
    monkeypatch.setattr(sy, "_kos", lambda *a, **k: (_ for _ in ()).throw(AssertionError("GERÇEK yakıcı çağrıldı")))
    fm._durum_yaz(kontrol_edildi=False, eylem="yok", gerekce="", uygulandi=False, hata="")
    return fm, kayit


def _kos(monkeypatch, bayrak):
    import backend_service as bs
    from servers import firmware_manager as fm
    from utils import stm32_kimlik

    kimlik = stm32_kimlik.banner_ayristir(saha_banneri())
    assert kimlik is not None and kimlik.surum == "DDS v2.3", f"aparat: banner ayrıştırılamadı: {kimlik}"
    if bayrak is None:
        monkeypatch.delenv("PEMF_FW_AUTO_UPDATE", raising=False)
    else:
        monkeypatch.setenv("PEMF_FW_AUTO_UPDATE", bayrak)
    bs._donanim_guncellemesi_safe(_Cekirdek(kimlik), logging.getLogger("d1120"))
    return fm.durum()


def test_KRITIK_banner_surumu_AYRISTIRILIR_karar_FIRMWARE_GUNCELLE_ve_bayrak_1de_YAKAR(zincir, monkeypatch):
    fm, kayit = zincir
    from utils import surum_uyumu as su

    d = _kos(monkeypatch, "1")
    assert d["eylem"] == su.FIRMWARE_GUNCELLE, (
        f"saha banner'ı (DDS v2.3) + firmwareMin 2.4 kuralı → eylem {d['eylem']!r}: {d['gerekce']} — sürüm "
        "ayrıştırılamıyor (karar hep 'yok')"
    )
    assert d.get("firmwareSurum") in ("2.3", "2.4") and kayit["yak"], f"bayrak '1' + kural + STM → yakma YOK: {d}"


@pytest.mark.parametrize("bayrak", [None, "0", "false"])
def test_KARSIT_bayrak_1_DEGILSE_karar_olculur_YAKMA_0(zincir, monkeypatch, bayrak):
    fm, kayit = zincir
    from utils import surum_uyumu as su

    d = _kos(monkeypatch, bayrak)
    assert d["eylem"] == su.FIRMWARE_GUNCELLE, f"aparat: karar ölçülemedi ({d['gerekce']})"
    assert kayit["yak"] == [] and kayit["indir"] == [] and d["uygulandi"] is False, (
        f"PEMF_FW_AUTO_UPDATE={bayrak!r} iken indirme/yakma denendi (Y1): {kayit}"
    )


@pytest.mark.parametrize(
    "ham,beklenen",
    [("DDS v2.3", "2.3"), ("DDS v2.2", "2.2"), ("DDS v10.12.1", "10.12.1"), ("v2.3-rc1", "2.3"), ("DDS", ""), ("", "")],
)
def test_KRITIK_firmware_surumu_SAYIYI_cikarir_bilinmeyende_BOS(ham, beklenen):
    from utils import stm32_kimlik

    assert stm32_kimlik.firmware_surumu(ham) == beklenen


# ── Y17: ayrı yayın varlığı ─────────────────────────────────────────────────────────────────────────────────────────
class _Yanit(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


@pytest.fixture
def acici(monkeypatch):
    from servers import firmware_manager as fm

    istekler: list = []
    davranis = {"yanit": None}

    def _ac(url, timeout, headers=None):
        istekler.append(url)
        y = davranis["yanit"]
        if isinstance(y, BaseException):
            raise y
        return _Yanit(y)

    monkeypatch.setattr(fm.um, "_pinli_ac", _ac)
    return fm, istekler, davranis


def test_KRITIK_Y17_kurallar_AYRI_varliktan_okunur_exe_latest_json_DEGIL(acici):
    fm, istekler, davranis = acici
    davranis["yanit"] = json.dumps(KURALLI).encode("utf-8")
    m = fm.manifest_oku()
    assert len(istekler) == 1, f"uyum varlığı pinli açıcıdan istenmedi: {istekler}"
    from urllib.parse import urlparse

    u = urlparse(istekler[0])
    assert (u.scheme, u.netloc, u.path) == ("https", "github.com", VARLIK_YOLU), (
        f"kurallar beklenen ayrı varlıktan değil: {istekler[0]} (exe/latest.json'a bağlı kalmamalı — Y17)"
    )
    assert "latest.json" not in istekler[0]
    assert m == KURALLI


def test_KRITIK_Y17_varlik_YAYINLANMAMISSA_404_kural_YOK_hata_DEGIL(acici):
    fm, istekler, davranis = acici
    from utils import surum_uyumu as su

    davranis["yanit"] = urllib.error.HTTPError(istekler and istekler[-1] or "u", 404, "Not Found", {}, None)
    assert fm.manifest_oku() == {}, "yayınlanmamış varlık (404) 'okunamadı' sınıfına düştü"
    d = fm.acilis_denetimi(firmware_surum="2.3", stm_bagli=True, uygula=False)
    assert d["eylem"] == su.EYLEM_YOK and "kural" in d["gerekce"].lower(), d


@pytest.mark.parametrize(
    "yanit",
    [
        urllib.error.HTTPError("u", 500, "x", {}, None),
        urllib.error.URLError("ag yok"),
        b"[1, 2]",
        b"{bozuk",
    ],
    ids=["http500", "ag_yok", "nesne_degil", "bozuk_json"],
)
def test_KRITIK_Y17_varlik_OKUNAMAZSA_None_BEKLE(acici, yanit):
    fm, _istekler, davranis = acici
    davranis["yanit"] = yanit
    assert fm.manifest_oku() is None
