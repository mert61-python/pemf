# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KP-4 · B3 — KD (istem 44) arka uç kodunun KAPSANMAMIŞ hata / kenar kolları (AŞAMA 0: backend %100 → %99,67; 88 satır KD dosyalarında).

SÖZLEŞMELER: kabin kalibrasyonu uçları — kalibrasyon yok / bozuk → 409 (neden metni), seçili kamera kalibrasyon kamerası değil → 409,
plaka bulunamadı / ölçü geçersiz → 422, AI Pro kamerayı tutuyor / seçim yok → 409, kare alınamadı → 503 (indeks söyler), dosyaya
yazılamadı → 503 (neden türü), denetim izi / doğrulama eki yazılamazsa kayıt DURMAZ (günlük), iç parametre okunamazsa 422 (boyut
söyler), sunucuda tutulan kare ÖMRÜ dolunca silinir (404), hesap reddi kodları istek dilinde EYLEM metnine çevrilir · kabin kamerası —
bozuk seçim / kalibrasyon kaydı çözünürlük SEÇMEZ, aygıt yolu değişince ad + VID/PID ile açılır (günlük) · AI Pro hedef — kalibrasyon /
seçim okunamazsa fail-safe None · MSMF kamera listesi — Windows dışı / hata → [] (gerçek Media Foundation sorgusu testte YOK).
Sahte EN ALT katta: KD testinin sentetik kabin karesi (`sabit_duzlem_sahne`), `sabit_duzlem` G/Ç'si, ızgara algılayıcısı, cv2 kodlayıcı.
"""

from __future__ import annotations

import logging
import sys
import time

import i18n_yardimci as iy
import numpy as np
import pytest
from fastapi import HTTPException
from test_KD_kalibrasyon_uclari_ve_surus_kapisi import (  # noqa: F401
    BASKA,
    SAG,
    SOL,
    _govde,
    _iki_kare,
    _kalibre,
    _kare,
    _olcumler,
    env,
)


def _tr(anahtar: str, **p) -> str:
    m = iy.katalog("sunucu", "tr")[anahtar]
    for k, v in p.items():
        m = m.replace("{{" + k + "}}", str(v))
    return m


def _kml(ad: str, yol: str) -> dict:
    from utils.kamera_kimligi import kimlik

    return kimlik(ad, yol)


def _kk():
    from servers import kabin_kalibrasyonu as kk

    return kk


def _sd():
    from ai_hub.cv_ortak import sabit_duzlem as sd

    return sd


# ═══ Saf yardımcılar ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "kod, ek, anahtar, p",
    [
        ("girdi_gecersiz", {}, "ai.kalibrasyon.neden.girdiGecersiz", {}),
        ("olcum_eksik", {}, "ai.kalibrasyon.neden.olcumEksik", {}),
        ("cozum_yok", {}, "ai.kalibrasyon.neden.cozumYok", {}),
        ("kamera_duzlem_altinda", {}, "ai.kalibrasyon.neden.kameraDuzlemAltinda", {}),
        ("izdusum_yuksek", {"px": 12.5}, "ai.kalibrasyon.neden.izdusumYuksek", {"px": "12.5"}),
        ("konum_yayilimi_az", {"cm": 3}, "ai.kalibrasyon.neden.konumYayilimiAz", {"cm": "3"}),
    ],
)
def test_hesap_reddi_KODU_istek_dilinde_EYLEM_metnine_cevrilir(kod, ek, anahtar, p):
    assert _kk().neden_metni(kod, **ek) == _tr(anahtar, **p)


def test_bilinmeyen_red_kodu_AYNEN_doner():
    assert _kk().neden_metni("yeni_bir_kod") == "yeni_bir_kod"


@pytest.mark.parametrize(
    "deger, beklenen", [((1, 2.5), True), (("x",), False), ((None,), False), ((1, float("nan")), False)]
)
def test_sonlu_sayi_denetimi_SAYI_olmayani_reddeder(deger, beklenen):
    assert _kk()._sonlu(*deger) is beklenen


def test_seans_durumu_OKUNAMAZSA_kalibrasyonu_ENGELLEMEZ(monkeypatch):
    import servers

    class _Bozuk:
        def __getattr__(self, ad):
            raise RuntimeError("modül yarım yüklendi")

    monkeypatch.setattr(servers, "ai_router", _Bozuk())
    assert _kk()._seans_suruyor() is False
    _kk()._seans_kapisi()  # istisna YOK — kapı açık


def test_sunucudaki_kare_OMRU_dolunca_silinir_404():
    kk = _kk()
    with kk._kilit:
        kk._kareler["kp4-bayat"] = {"zaman": time.monotonic() - kk.KARE_OMRU_SN - 5.0}
    with pytest.raises(HTTPException) as e:
        kk._kare("kp4-bayat")
    assert e.value.status_code == 404 and e.value.detail == _tr("ai.kalibrasyon.kareYok")
    assert "kp4-bayat" not in kk._kareler, "ömrü dolan kare bellekte kaldı"


def test_plaka_izgarasi_ISTISNA_atarsa_konum_YOK_neden_turu(monkeypatch, caplog):
    from ai_hub.inference_petri_dish.petri_cv_v2 import plate_grid

    def _patlar(*a, **k):
        raise ValueError("ızgara çöktü")

    monkeypatch.setattr(plate_grid, "detect_plate_wells", _patlar)
    with caplog.at_level(logging.WARNING):
        konum, neden = _kk()._plaka_bul(np.zeros((40, 40, 3), np.uint8), _sd())
    assert (konum, neden) == (None, "ValueError")
    assert any("plaka ızgarası istisnası" in r.getMessage() for r in caplog.records)


def test_plaka_bulundu_ama_HOMOGRAFI_yoksa_konum_YOK(monkeypatch):
    from types import SimpleNamespace

    from ai_hub.inference_petri_dish.petri_cv_v2 import plate_grid

    g = SimpleNamespace(success=True, wells_plate_mm=[(0.0, 0.0)], error=None, H_ransac=None, H_img_from_plate=None)
    monkeypatch.setattr(plate_grid, "detect_plate_wells", lambda *a, **k: g)
    assert _kk()._plaka_bul(np.zeros((40, 40, 3), np.uint8), _sd()) == (None, "homografi_yok")


def test_isaretli_kare_KODLANAMAZSA_503(monkeypatch):
    import cv2

    monkeypatch.setattr(cv2, "imencode", lambda *a, **k: (False, None))
    with pytest.raises(HTTPException) as e:
        _kk()._isaretle(np.zeros((20, 30, 3), np.uint8), None, 30)
    assert e.value.status_code == 503 and e.value.detail == _tr("ayarlar.kabinKamerasi.kareAlinamadi", indeks="?")


def test_ic_parametre_OKUNAMAZSA_422_kare_boyutunu_soyler(monkeypatch, caplog):
    from ai_hub.cv_ortak import coord_transform

    def _patlar(*a, **k):
        raise OSError("npz yok")

    monkeypatch.setattr(coord_transform.CameraIntrinsics, "from_npz", staticmethod(_patlar))
    with caplog.at_level(logging.WARNING), pytest.raises(HTTPException) as e:
        _kk()._ic_parametre(1280, 720)
    assert e.value.status_code == 422
    assert e.value.detail == _tr("ai.kalibrasyon.icParametreYok", genislik="1280", yukseklik="720")


# ═══ Kamera karesi (uç: /kare) ═════════════════════════════════════════════════════════════════════════════════════════════════════


def test_kare_AI_PRO_kamerayi_tutuyorsa_409(env, monkeypatch):
    import servers.settings_router as sr

    monkeypatch.setattr(sr, "_ai_kamerasi_mesgul", lambda: True)
    r = env["client"].post("/api/ai/pro/kalibrasyon/kare", json={})
    assert r.status_code == 409 and r.json()["detail"] == _tr("ayarlar.kabinKamerasi.kareMesgul"), r.text


def test_kare_kamera_SECILMEMISSE_409_secim_metni(env, monkeypatch):
    from utils import kabin_kamerasi as kk

    def _secilmedi(*a, **k):
        raise kk.KameraSecilmedi()

    monkeypatch.setattr(kk, "kare_al", _secilmedi)
    r = env["client"].post("/api/ai/pro/kalibrasyon/kare", json={})
    assert r.status_code == 409 and r.json()["detail"] == kk.secim_hatasi_metni(kk.KameraSecilmedi()), r.text


def test_kare_ALINAMAZSA_503_secili_INDEKSI_soyler(env, monkeypatch):
    from utils import kabin_kamerasi as kk

    monkeypatch.setattr(kk, "kare_al", lambda *a, **k: None)
    r = env["client"].post("/api/ai/pro/kalibrasyon/kare", json={})
    assert r.status_code == 503 and r.json()["detail"] == _tr("ayarlar.kabinKamerasi.kareAlinamadi", indeks="1"), r.text


def test_kare_BOYUTU_bildirilenle_UYUSMAZSA_503(env, monkeypatch):
    import base64

    import cv2
    from utils import kabin_kamerasi as kk

    ok, b = cv2.imencode(".jpg", np.zeros((10, 10, 3), np.uint8))
    kare = {
        "indeks": 1,
        "kimlik": None,
        "genislik": 640,
        "yukseklik": 480,
        "image_base64": base64.b64encode(b).decode(),
    }
    monkeypatch.setattr(kk, "kare_al", lambda *a, **k: kare)
    r = env["client"].post("/api/ai/pro/kalibrasyon/kare", json={})
    assert r.status_code == 503 and r.json()["detail"] == _tr("ayarlar.kabinKamerasi.kareAlinamadi", indeks="1"), r.text


# ═══ Hesap / kaydet ════════════════════════════════════════════════════════════════════════════════════════════════════════════════


def test_hesap_konum_kareleri_FARKLI_kameradan_ise_409(env):
    env["secim"]["kimlik"] = _kml("Kamera A", r"\\?\usb#vid_1111&pid_2222&mi_00#a")
    a = _kare(env, SOL)["kareKimligi"]
    env["secim"]["kimlik"] = _kml("Kamera B", r"\\?\usb#vid_3333&pid_4444&mi_00#b")
    b = _kare(env, SAG)["kareKimligi"]
    r = env["client"].post("/api/ai/pro/kalibrasyon/hesapla", json=_govde(env, [(a, SOL), (b, SAG)]))
    assert r.status_code == 409 and r.json()["detail"] == _tr("ai.pemf.kapi.kameraFarkli"), r.text


def test_kaydet_DOSYAYA_yazilamazsa_503_neden_turu_ve_kalibrasyon_YOK(env, monkeypatch):
    sd = _sd()

    def _yazamaz(*a, **k):
        raise PermissionError("salt okunur")

    monkeypatch.setattr(sd, "kaydet", _yazamaz)
    r = env["client"].post("/api/ai/pro/kalibrasyon/kaydet", json=_govde(env, _iki_kare(env)))
    assert r.status_code == 503 and r.json()["detail"] == _tr(
        "ai.kalibrasyon.kaydedilemedi", neden="PermissionError"
    ), r.text
    assert sd.yukle(env["kok"])[0] is None
    assert [o for o, _ in env["izler"]] == [], "yazılamayan kalibrasyon için denetim izi yazıldı"


def test_kaydet_DENETIM_IZI_yazilamazsa_kayit_DURMAZ(env, monkeypatch, caplog):
    import servers.api_server as apis

    class _DB:
        def record_session_event(self, *a, **k):
            raise RuntimeError("DB kilitli")

    monkeypatch.setattr(apis, "_get_treatment_db", lambda: _DB())
    with caplog.at_level(logging.WARNING):
        r = env["client"].post("/api/ai/pro/kalibrasyon/kaydet", json=_govde(env, _iki_kare(env)))
    assert r.status_code == 200 and r.json()["denetimIziYazildi"] is False, r.text
    assert _sd().yukle(env["kok"])[0] is not None, "denetim izi düşünce kalibrasyon kaydedilmedi"
    assert any("denetim izi yazılamadı" in m.getMessage() for m in caplog.records)


# ═══ Doğrula ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════


def test_dogrula_KALIBRASYON_yoksa_409(env):
    k = _kare(env, BASKA)
    r = env["client"].post(
        "/api/ai/pro/kalibrasyon/dogrula", json={"kareKimligi": k["kareKimligi"], "olcumler": _olcumler(BASKA, n=2)}
    )
    assert r.status_code == 409 and r.json()["detail"] == _tr("ai.pemf.kapi.kalibrasyonYok"), r.text


def test_dogrula_KAMERA_farkli_409_PLAKA_yok_422_OLCU_gecersiz_422(env):
    c = env["client"]
    env["secim"]["kimlik"] = _kml("Kamera A", r"\\?\usb#vid_1111&pid_2222&mi_00#a")
    _kalibre(env)
    env["secim"]["kimlik"] = _kml("Kamera B", r"\\?\usb#vid_3333&pid_4444&mi_00#b")
    k = _kare(env, BASKA)
    r = c.post(
        "/api/ai/pro/kalibrasyon/dogrula", json={"kareKimligi": k["kareKimligi"], "olcumler": _olcumler(BASKA, n=2)}
    )
    assert r.status_code == 409 and r.json()["detail"] == _tr("ai.pemf.kapi.kameraFarkli"), r.text
    env["secim"]["kimlik"] = _kml("Kamera A", r"\\?\usb#vid_1111&pid_2222&mi_00#a")
    env["sahne"]["plaka_var"] = False
    yok = c.post("/api/ai/pro/kalibrasyon/kare", json={}).json()
    env["sahne"]["plaka_var"] = True
    r = c.post(
        "/api/ai/pro/kalibrasyon/dogrula", json={"kareKimligi": yok["kareKimligi"], "olcumler": _olcumler(BASKA, n=2)}
    )
    assert r.status_code == 422 and r.json()["detail"] == _tr("ai.kalibrasyon.plakaBulunamadi"), r.text
    k = _kare(env, BASKA)
    # NaN: JSON ayrıştırıcısı kabul eder, pydantic float kabul eder → yalnız ucun KENDİ sonluluk denetimi yakalar
    for olc in ('[null, null, null, null]', '[{"solCm": NaN, "onCm": 1.0}, null, null, null]'):
        govde = '{"kareKimligi": "%s", "olcumler": %s}' % (k["kareKimligi"], olc)
        r = c.post("/api/ai/pro/kalibrasyon/dogrula", content=govde, headers={"content-type": "application/json"})
        assert r.status_code == 422 and r.json()["detail"] == _tr("ai.kalibrasyon.neden.girdiGecersiz"), (olc, r.text)


def test_dogrula_EKI_dosyaya_yazilamazsa_sonuc_yine_DONER(env, monkeypatch, caplog):
    sd = _sd()
    _kalibre(env)

    def _yazamaz(*a, **k):
        raise OSError("disk dolu")

    monkeypatch.setattr(sd, "dogrulama_ekle", _yazamaz)
    k = _kare(env, BASKA)
    with caplog.at_level(logging.WARNING):
        r = env["client"].post(
            "/api/ai/pro/kalibrasyon/dogrula", json={"kareKimligi": k["kareKimligi"], "olcumler": _olcumler(BASKA, n=2)}
        )
    assert r.status_code == 200 and r.json()["gecti"] is True, r.text
    assert [o for o, _ in env["izler"]][-1] == "kabin_kalibrasyonu_dogrulandi"
    assert any("doğrulaması dosyaya eklenemedi" in m.getMessage() for m in caplog.records)


# ═══ Fantom / taban / sahne yenile ════════════════════════════════════════════════════════════════════════════════════════════════


def test_fantom_ve_taban_KALIBRASYON_yoksa_409(env):
    c = env["client"]
    r = c.post("/api/ai/pro/kalibrasyon/fantom", json={"kalinlikCm": 3.0, "tumorDerinligiCm": 0.5})
    assert r.status_code == 409 and r.json()["detail"] == _tr("ai.pemf.kapi.kalibrasyonYok"), r.text
    r = c.post("/api/ai/pro/kalibrasyon/taban", json={"lensUzaklikCm": 30.0})
    assert r.status_code == 409 and r.json()["detail"] == _tr("ai.pemf.kapi.kalibrasyonYok"), r.text


@pytest.mark.parametrize(
    "yol, govde, yazici",
    [
        ("/api/ai/pro/kalibrasyon/fantom", {"kalinlikCm": 3.0, "tumorDerinligiCm": 0.5}, "fantom_ayari_yaz"),
        ("/api/ai/pro/kalibrasyon/taban", {"lensUzaklikCm": None}, "numune_tabani_yaz"),
    ],
)
def test_fantom_ve_taban_DOSYAYA_yazilamazsa_503_ve_iz_YOK(env, monkeypatch, yol, govde, yazici):
    sd = _sd()
    _kalibre(env)
    if govde.get("lensUzaklikCm", 0) is None:
        govde = {"lensUzaklikCm": float(sd.yukle(env["kok"])[0]["olculen_lens_cm"]["taban"]) - 2.0}
    oncesi = len(env["izler"])

    def _yazamaz(*a, **k):
        raise PermissionError("salt okunur")

    monkeypatch.setattr(sd, yazici, _yazamaz)
    r = env["client"].post(yol, json=govde)
    assert r.status_code == 503 and r.json()["detail"] == _tr(
        "ai.kalibrasyon.kaydedilemedi", neden="PermissionError"
    ), r.text
    assert len(env["izler"]) == oncesi, "yazılamayan ayar için denetim izi yazıldı"


def test_taban_kalibrasyonda_LENS_yuksekligi_YOKSA_409(env, monkeypatch):
    sd = _sd()
    _kalibre(env)
    asil = sd.yukle

    def _lenssiz(kok):
        kal, hata = asil(kok)
        kal = dict(kal)
        kal.pop("olculen_lens_cm", None)
        return kal, hata

    monkeypatch.setattr(sd, "yukle", _lenssiz)
    r = env["client"].post("/api/ai/pro/kalibrasyon/taban", json={"lensUzaklikCm": 30.0})
    assert r.status_code == 409 and r.json()["detail"] == _tr("ai.kalibrasyon.lensYuksekligiYok"), r.text


def test_sahne_yenile_KALIBRASYON_yoksa_409_KAMERA_farkliysa_409(env):
    c = env["client"]
    r = c.post("/api/ai/pro/kalibrasyon/sahne-yenile", json={})
    assert r.status_code == 409 and r.json()["detail"] == _tr("ai.pemf.kapi.kalibrasyonYok"), r.text
    env["secim"]["kimlik"] = _kml("Kamera A", r"\\?\usb#vid_1111&pid_2222&mi_00#a")
    _kalibre(env)
    env["secim"]["kimlik"] = _kml("Kamera B", r"\\?\usb#vid_3333&pid_4444&mi_00#b")
    r = c.post("/api/ai/pro/kalibrasyon/sahne-yenile", json={})
    assert r.status_code == 409 and r.json()["detail"] == _tr("ai.pemf.kapi.kameraFarkli"), r.text


def test_sahne_yenile_KUYU_araligi_olculemezse_sahneye_gore_karar_YAZILAMAZSA_503(env, monkeypatch, caplog):
    sd = _sd()
    _kalibre(env)

    def _olculemez(*a, **k):
        raise ValueError("kuyu aralığı yok")

    def _yazamaz(*a, **k):
        raise PermissionError("salt okunur")

    monkeypatch.setattr(sd, "komsu_kuyu_araligi", _olculemez)
    monkeypatch.setattr(sd, "sahne_yenile", _yazamaz)
    with caplog.at_level(logging.INFO):
        r = env["client"].post("/api/ai/pro/kalibrasyon/sahne-yenile", json={})
    assert r.status_code == 503 and r.json()["detail"] == _tr(
        "ai.kalibrasyon.kaydedilemedi", neden="PermissionError"
    ), r.text
    assert any("kuyu aralığı ölçülemedi" in m.getMessage() for m in caplog.records), (
        "ölçülemeyen kuyu aralığı günlüğe düşmedi"
    )


# ═══ Kabin kamerası / kamera kimliği / AI Pro hedef ═══════════════════════════════════════════════════════════════════════════════


def test_kabin_kamerasi_GECERSIZ_indeksli_kayit_SECIM_sayilmaz(monkeypatch, tmp_path):
    import json

    from utils import kabin_kamerasi as kk

    monkeypatch.delenv(kk.ORTAM_DEGISKENI, raising=False)
    monkeypatch.setattr(kk, "_veri_koku", lambda: tmp_path)
    for veri in ({"indeks": -1}, {"indeks": "2"}, {"indeks": True}, ["1"]):
        (tmp_path / kk.KAMERA_DOSYASI).write_text(json.dumps(veri), encoding="utf-8")
        assert kk.secili_kamera() is None, veri


def test_kabin_kamerasi_kalibrasyon_COZUNURLUGU_okunamazsa_ya_da_eksikse_SECMEZ(monkeypatch, tmp_path):
    from utils import kabin_kamerasi as kk

    sd = _sd()
    monkeypatch.setattr(kk, "_veri_koku", lambda: tmp_path)

    def _patlar(_kok):
        raise RuntimeError("okunamadı")

    monkeypatch.setattr(sd, "yukle", _patlar)
    assert kk.istenen_cozunurluk() is None
    for kal in ({"kamera": {}}, {"kamera": {"genislik": "x", "yukseklik": 720}}, {}):
        monkeypatch.setattr(sd, "yukle", lambda _k, kal=kal: (kal, None))
        assert kk.istenen_cozunurluk() is None, kal
    monkeypatch.setattr(sd, "yukle", lambda _k: ({"kamera": {"genislik": 1920, "yukseklik": 1080}}, None))
    assert kk.istenen_cozunurluk() == (1920, 1080)


def test_kabin_kamerasi_AYGIT_YOLU_degisince_AD_VIDPID_ile_acilir_ve_gunluge_yazilir(monkeypatch, caplog):
    from utils import kabin_kamerasi as kk
    from utils import kamera_kimligi

    eski_yol = r"\\?\usb#vid_1bcf&pid_28c4&mi_00#eski"
    yeni_yol = r"\\?\usb#vid_1bcf&pid_28c4&mi_00#yeni"
    monkeypatch.setattr(
        kamera_kimligi, "msmf_kameralar", lambda: [{"indeks": 0, **kamera_kimligi.kimlik("Kabin Kam", yeni_yol)}]
    )
    with caplog.at_level(logging.INFO):
        assert kk.acilacak_indeks({"indeks": 0, "kimlik": kamera_kimligi.kimlik("Kabin Kam", eski_yol)}) == 0
    assert any("aygit yolu degismis" in m.getMessage() for m in caplog.records)


def test_msmf_kamera_listesi_WINDOWS_disinda_ve_HATADA_bos_SORGU_sonucunu_aynen_doner(monkeypatch, caplog):
    # conftest `_kamera_kimligi_kapali` modüldeki `msmf_kameralar`ı boş listeyle DEĞİŞTİRİR → sarmalayıcı, aynı kaynak dosyanın taze
    # bir kopyasında ölçülür (kapsam dosya adına bağlı); gerçek Media Foundation sorgusu (`_msmf_kameralar`) burada da sahte.
    import importlib.util

    from utils import kamera_kimligi

    spec = importlib.util.spec_from_file_location("kp4_kamera_kimligi_taze", kamera_kimligi.__file__)
    kmk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kmk)
    monkeypatch.setattr(kmk, "_msmf_kameralar", lambda: [{"indeks": 0, "ad": "Kam"}])
    monkeypatch.setattr(sys, "platform", "linux")
    assert kmk.msmf_kameralar() == [], "Windows dışında Media Foundation sorgulandı"
    monkeypatch.setattr(sys, "platform", "win32")
    assert kmk.msmf_kameralar() == [{"indeks": 0, "ad": "Kam"}]

    def _patlar():
        raise OSError("MFEnumDeviceSources başarısız")

    monkeypatch.setattr(kmk, "_msmf_kameralar", _patlar)
    with caplog.at_level(logging.WARNING):
        assert kmk.msmf_kameralar() == []
    assert any("MSMF aygit listesi okunamadi" in m.getMessage() for m in caplog.records)


def test_ai_pro_hedef_kalibrasyon_ve_SECIM_okunamazsa_FAIL_SAFE(monkeypatch, caplog):
    from servers import ai_pro_hedef as h
    from utils import kabin_kamerasi as kk

    sd = _sd()

    def _patlar(*a, **k):
        raise RuntimeError("okunamadı")

    monkeypatch.setattr(sd, "yukle", _patlar)
    with caplog.at_level(logging.WARNING):
        assert h.duzlem_durumu() == (None, "okunamadi")
    assert any("Sabit düzlem kalibrasyonu okunamadı" in m.getMessage() for m in caplog.records)
    monkeypatch.setattr(kk, "secili_kamera", _patlar)
    assert h.secili_kamera_kimligi() is None and h.secili_kamera_indeksi() is None
    monkeypatch.setattr(h, "duzlem_durumu", lambda: ({"gorus_alani": {"on": "geniş"}}, None))
    assert h.gorus_alani_on_cm() is None and h.kor_bolge_ipucu() == ""
    assert h.kalibrasyon_eski_metni({"kalibrasyon": ["eski"]}) is None
    for kapi in (None, "metin", 3):
        assert h.kapi_cevir(kapi) == kapi
