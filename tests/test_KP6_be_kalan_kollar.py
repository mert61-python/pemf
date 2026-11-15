# -*- coding: utf-8 -*-
"""KP-6 · A (KP6-LISTESI 11): KP-5 kapanışında kapsanmayan 28 backend satırı — KD / ODK / AP / İH sonrası eklenen hata yakalama kolları
ve ODAK gelince gerçek sağlayıcılarda çağrılmayan XAI yolu. Hepsine test yazılabildi (Y242: test yazılabilen satıra etiket YOK); ürün kodu
DEĞİŞMEDİ. Her test bir DAVRANIŞ iddiası, sahte EN ALT katta (çağrılan işlev / seri port baytları / sağlayıcı).

- `headless_core`: izin hatasında veri kökü YOKSA ya da dizin değilse "erişim yok" DENMEZ (eski "açılamadı" iletisi) · MLX bekçisi
  bağlantı geçişini alamazsa geçiş ve bildirimi BOZULMAZ · okuyucunun bekçi tıklaması patlarsa okuyucu SÜRER (bağlantı kopmuş sayılmaz).
- `ai_pro_hedef`: sayıya çevrilemeyen organ koordinatı gövde geometrisine SAYILMAZ · geometri çıkarılamazsa lokalizasyon sürer ve önceki
  karenin gövdesi BAYAT kalmaz · canlı uyarı `ecc_failed` / `plate_cropped` kendi eylemini iki dilde söyler · araştırma sağlayıcısının XAI
  duyarlılığı dozun baz noktasını (karar #9) ve seçili hedefi kullanır.
- `ai_router`: canlı E yazılamazsa sürüş etkilenmez · ODAK DIŞI sağlayıcıda öneri XAI'si onay meta'sına girer, hatası öneriyi düşürmez
  (D5.05: `xai_error` + tam zincir) · boşta tanımsız model seçimi 422 + eylem, etkin model / hedef DEĞİŞMEZ (AP-B5).
"""

from __future__ import annotations

import logging
import time
import types

import numpy as np
import pytest
from test_ai_pro_model_muhru import muhur_env  # noqa: F401  (aparat)
from test_AP_B5_B2_organ_BOSTA_istenen_modelle_dogrulanir import ortam  # noqa: F401  (aparat)
from test_AP_B6_kapi_uyarisi_NEDEN_ve_EYLEM_soyler import dil  # noqa: F401  (aparat)
from test_IH_22_veri_erisimi_yok_saglik_ve_mandal import TR as ERISIM_YOK_TR
from test_IH_22_veri_erisimi_yok_saglik_ve_mandal import _ac_hata_ile, _cekirdek
from test_ODK_kedi_oneri_onay_ODAK import _organlar
from test_TD1_STM_okuyucu_YARIM_satiri_birlestirir_SGI_3_1 import cekirdek  # noqa: F401  (gerçek okuyucu aparatı)
from test_Y285_backend_MLX_BEKCISI_KULLANICIYI_uyarir import TELE_B, yalin  # noqa: F401  (aparat)

_KOK_HATA = "KP6 SIMULE ARIZA"


def _patlayan(sayac: list | None = None):
    def _p(*_a, **_k):
        if sayac is not None:
            sayac.append(1)
        raise RuntimeError(_KOK_HATA)

    return _p


def _zincirli(caplog, parca: str) -> list:
    kayitlar = [r for r in caplog.records if parca in r.getMessage()]
    assert kayitlar, f"'{parca}' kaydı HİÇ yok: {[r.getMessage()[:60] for r in caplog.records]}"
    for r in kayitlar:
        assert r.exc_info and r.exc_info[0] is RuntimeError, f"'{parca}' kaydında kök hata (exc_info) yok"
    return kayitlar


# ── headless_core ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_veri_koku_YOK_ya_da_DOSYA_ise_erisim_yok_DENMEZ(tmp_path):
    from headless_core import veri_koku_erisilemez_mi

    dosya = tmp_path / "PEMF_GUI.txt"
    dosya.write_text("x", encoding="utf-8")
    assert veri_koku_erisilemez_mi(tmp_path / "yok") is False  # FileNotFoundError: dizin yok
    assert veri_koku_erisilemez_mi(dosya) is False  # NotADirectoryError: dizin değil
    assert veri_koku_erisilemez_mi(tmp_path) is False  # listelenebiliyor


def test_izin_hatasi_ama_veri_koku_YOKSA_eski_acilamadi_iletisi_kalir(tmp_path):
    """İzin biçimli hata (errno 13, winerror YOK — `open()` kilidi de böyle) + veri kökü bu makinede YOK → "paylaşım kartıyla erişim verin"
    demek yanlış eylem olurdu (kart yok olan dizine erişim veremez)."""
    from headless_core import HeadlessCore

    try:
        raise RuntimeError("SQLCipher anahtari okunamadi") from PermissionError(13, "Permission denied")
    except RuntimeError as r:
        zincir = r
    cekirdek_ = _cekirdek(tmp_path / "PEMF_GUI_yok")
    assert HeadlessCore._db_ac(cekirdek_, "hasta", _ac_hata_ile(zincir)) is None
    assert cekirdek_.db_acilis_ayrintilari["hasta"][0] == "acilamadi", cekirdek_.db_acilis_ayrintilari
    assert cekirdek_.db_acilis_hatalari["hasta"] != ERISIM_YOK_TR


def test_MLX_bekcisi_PATLASA_da_baglanti_gecisi_ve_bildirimi_BOZULMAZ(yalin, caplog):  # noqa: F811
    c = yalin
    alinan: list = []
    c.stm_connected_signal.connect(alinan.append)
    sayac: list = []
    c._mlx_bekci = _patlayan(sayac)
    with caplog.at_level(logging.DEBUG, logger=c.logger.name):
        c._set_stm_connected(True)
        c._set_stm_connected(False)
    assert len(sayac) == 2, "aparat: bekçi geçişlere HİÇ çağrılmadı"
    assert alinan == [True, False], f"bekçi hatası bağlantı bildirimini bozdu: {alinan}"
    assert c.stm_is_connected is False
    assert len(_zincirli(caplog, "MLX bekcisi baglanti gecisini alamadi")) == 2


def test_okuyucu_MLX_tiklamasi_PATLASA_da_SURER_baglanti_KOPMUS_sayilmaz(cekirdek, caplog):  # noqa: F811
    core, kart = cekirdek
    sayac: list = []
    core._mlx_bekci_tikla = _patlayan(sayac)
    once = list(core.baglanti)

    def _telemetri() -> int:
        return sum(1 for t, v in core.olaylar if t == "hardware.stm.telemetry" and v and v.get("coil_id") == 6)

    with caplog.at_level(logging.DEBUG, logger=core.logger.name):
        for beklenen in (1, 2):  # tıklama patladıktan SONRA da satırlar işlenir
            kart.q.put((TELE_B + "\r\n").encode())
            bitis = time.monotonic() + 5.0
            while time.monotonic() < bitis and (_telemetri() < beklenen or len(sayac) < 2 * beklenen):
                time.sleep(0.02)
            assert _telemetri() >= beklenen, f"tıklama hatasından sonra satır işlenmedi ({_telemetri()} < {beklenen})"
    assert len(sayac) >= 2, "aparat: okuyucu bekçiyi HİÇ tıklamadı"
    assert core.baglanti == once, (
        f"bekçi tıklaması okuyucuyu düşürdü — bağlantı kopmuş sayıldı: {core.baglanti[len(once) :]}"
    )
    assert core._hw_sender_thread.is_alive()
    _zincirli(caplog, "MLX bekcisi tiklanamadi (okuyucu SURUYOR)")


# ── ai_pro_hedef ──────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bozuk", [["x", "y", "z"], None, 5], ids=["metin", "yok", "skaler"])
def test_govde_geometrisi_SAYI_OLMAYAN_koordinatli_organi_SAYMAZ(bozuk):
    from servers.ai_pro_hedef import kedi_govde_geometrisi

    tam = kedi_govde_geometrisi(_organlar())
    bozuk_org = _organlar()
    bozuk_org[7] = {"coord_cabin_cm": bozuk, "reliability": 0.9}  # kalp: güvenilir ama koordinatı sayı değil
    g = kedi_govde_geometrisi(bozuk_org)
    assert g is not None and g["organ_sayisi"] == tam["organ_sayisi"] - 1, g
    assert g == kedi_govde_geometrisi({k: v for k, v in _organlar().items() if k != 7}), (
        "bozuk koordinatlı organ gövde merkezine / yönüne katıldı"
    )


def test_localize_govde_geometrisi_PATLARSA_lokalizasyon_SURER_odak_kedi_BAYAT_kalmaz(monkeypatch, caplog):
    from servers import ai_pro_hedef as hedef
    from servers import ai_router as air

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(air, "_localize_organ_cpu", lambda f, oid: air._extract_organ_target(_organlar(), oid, None))
    sag = hedef.KediSaglayici()
    kare = np.zeros((4, 4, 3), np.uint8)
    sag.localize(kare, 2)
    assert sag.odak_kedi_girdisi() is not None, "aparat: ilk karede gövde bulunmadı"
    monkeypatch.setattr(hedef, "kedi_govde_geometrisi", _patlayan())
    with caplog.at_level(logging.WARNING, logger=air.logger.name):
        sonuc = sag.localize(kare, 2)
    assert sonuc[0] is True and len(sonuc) == 8, f"geometri hatası lokalizasyonu düşürdü: {sonuc[:2]}"
    assert sag.odak_kedi_girdisi() is None, "önceki karenin gövdesi bayat kaldı (öneri yanlış gövdeyle sürerdi)"
    _zincirli(caplog, "ODAK kedi gövde geometrisi çıkarılamadı")


@pytest.mark.parametrize(
    "neden, tr_bas, en_bas",
    [
        ("ecc_failed", "Plaka ızgarası ince hizalanamadı", "The plate grid could not be fine-aligned"),
        ("plate_cropped", "Plakanın bir kısmı görüntünün dışında", "Part of the plate is outside the image"),
    ],
)
def test_canli_uyari_ECC_ve_KIRPIK_plaka_KENDI_eylemini_iki_dilde_soyler(dil, neden, tr_bas, en_bas):  # noqa: F811
    from servers import ai_pro_hedef as h

    kapi = {"surulebilir": False, "nedenler": [neden, "oblique_view"]}  # ilk fiziksel olmayan neden söylenir
    dil("tr")
    assert h.kapi_uyari_metni(kapi).startswith(tr_bas)
    dil("en")
    assert h.kapi_uyari_metni(kapi).startswith(en_bas)


def test_arastirma_XAI_dozun_BAZ_noktasini_ve_SECILI_hedefi_kullanir(monkeypatch):
    """Karar #9 (2026-09-09): açıklama dozun FİİLEN üretildiği ekstra girdilerle (kabin yapılandırmasının achieved_B / duty_sum) ve
    mühürlenen SEÇİLİ hedefle üretilir. Petri modülü gerçek `inference_em_petri`."""
    from servers import ai_pro_hedef as aph

    from ai_hub.inference_em_petri import inference_em_petri as iep

    s = aph.PetriSaglayici()
    assert s._xai_modulu() is iep
    ongorucu = object()
    cfg = types.SimpleNamespace(phantom=types.SimpleNamespace(achieved_B=0.0031, duty_sum=1.7))
    s._onbellek = lambda: {"predictor": ongorucu, "cfg": cfg}
    s._meta = {"secili_organ_id": 4}
    cagri: list = []
    monkeypatch.setattr(iep, "xai_hizli_sensitivity", lambda *a, **k: cagri.append((a, k)) or [{"feature": "D3"}])
    assert s.xai_sensitivity(1.0, 2.0, 3.0, 9) == [{"feature": "D3"}]
    assert cagri == [((ongorucu, 1.0, 2.0, 3.0, 4), {"achieved_B": 0.0031, "duty_sum": 1.7})], cagri


# ── ai_router ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_canli_E_yazilamazsa_SURUS_etkilenmez(monkeypatch, caplog):
    from servers import ai_router as air
    from servers import efield_live as ef

    sag = types.SimpleNamespace(son_odak_e={"cancer": 0.04, "healthy": 0.02, "ortam": None})
    monkeypatch.setattr(air, "_aktif_saglayici", lambda: sag)
    yazilan: list = []
    monkeypatch.setattr(ef, "odak_guncelle", yazilan.append)
    air._canli_e_odak()
    assert yazilan == [sag.son_odak_e], "aparat: ODAK E'si canlı çubuğa yazılmadı"
    monkeypatch.setattr(ef, "odak_guncelle", _patlayan())
    with caplog.at_level(logging.DEBUG, logger=air.logger.name):
        assert air._canli_e_odak() is None  # fırlatmaz: gösterim hatası sürüş döngüsünü kesmez
    _zincirli(caplog, "ODAK canlı E yazılamadı")


def _oner(client, dil_: str):
    return client.post(
        "/api/ai/pro/propose",
        json={"organ_id": 1, "duration_minutes": 5, "model": "sahte"},
        headers={"X-PEMF-Dil": dil_},
    )


def test_ODAK_DISI_saglayicida_XAI_duyarliligi_onay_meta_sina_GIRER(muhur_env, monkeypatch):  # noqa: F811
    import servers.ai_pro_hedef as hedef

    air, _apis, client, taze_cache, _izler = muhur_env
    assert not hedef.odak_destekli(hedef.SAGLAYICILAR["sahte"]), "aparat: sahte sağlayıcı ODAK'lı — XAI yolu denenmez"
    monkeypatch.setattr(
        hedef.SAGLAYICILAR["sahte"], "xai_sensitivity", lambda *a, **k: [{"feature": "D3", "etki": 0.7}]
    )
    monkeypatch.setattr(
        hedef, "duzlem_surus_engeli", lambda _s: None
    )  # KD · Y259 ön koşulu sağlanmış (başka kural ölçülür)
    taze_cache("sahte")
    r = _oner(client, "tr")
    assert r.status_code == 200, r.text[:200]
    meta = r.json()["meta"]
    assert meta.get("xaiSensitivity") == [{"feature": "D3", "etki": 0.7}], meta
    assert "xai_error" not in meta


@pytest.mark.parametrize(
    "dil_, beklenen", [("tr", "Açıklama üretilemedi"), ("en", "Explanation could not be generated")]
)
def test_ODAK_DISI_saglayicida_XAI_hatasi_ONERIYI_dusurmez_xai_error_ve_TAM_ZINCIR(
    muhur_env,  # noqa: F811
    monkeypatch,
    caplog,
    dil_,
    beklenen,
):
    import servers.ai_pro_hedef as hedef

    air, _apis, client, taze_cache, izler = muhur_env
    sayac: list = []
    monkeypatch.setattr(hedef.SAGLAYICILAR["sahte"], "xai_sensitivity", _patlayan(sayac))
    monkeypatch.setattr(
        hedef, "duzlem_surus_engeli", lambda _s: None
    )  # KD · Y259 ön koşulu sağlanmış (başka kural ölçülür)
    taze_cache("sahte")
    with caplog.at_level(logging.WARNING, logger=air.logger.name):
        r = _oner(client, dil_)
    assert r.status_code == 200, f"XAI hatası ÖNERİYİ düşürdü: {r.text[:200]}"
    assert sayac == [1] and izler["predict"] == [1], "aparat: XAI / doz yoluna girilmedi"
    meta = r.json()["meta"]
    assert "xaiSensitivity" not in meta
    assert meta.get("xai_error") == beklenen, meta.get("xai_error")
    _zincirli(caplog, "AI Pro öneri XAI üretilemedi")


@pytest.mark.parametrize(
    "dil_, kalip",
    [("tr", "Model 'yok-boyle' tanınmıyor (geçerli: {})"), ("en", "Model 'yok-boyle' is not recognized (valid: {})")],
)
def test_bosta_TANIMSIZ_model_secimi_422_EYLEM_etkin_model_ve_hedef_DEGISMEZ(ortam, dil_, kalip):  # noqa: F811
    import servers.ai_pro_hedef as hedef

    air, c = ortam
    r = c.post(
        "/api/ai/pro/organ",
        json={"organ_id": 1, "model": "yok-boyle", "client_id": "panel"},
        headers={"X-PEMF-Dil": dil_},
    )
    assert r.status_code == 422, r.text[:200]
    assert r.json()["detail"] == kalip.format("|".join(sorted(hedef.SAGLAYICILAR))), r.json()
    assert air._ai_hedef_modeli == "kedi" and air._ai_organ_id == 0, "reddedilen seçim etkin modeli / hedefi değiştirdi"
