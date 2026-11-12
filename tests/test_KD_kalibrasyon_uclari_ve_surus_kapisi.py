# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KD · Y259 / Y260 — kabin kalibrasyonu UÇLARI ve araştırma SÜRÜŞ KAPISI (arka uç, gerçek uçlar, TestClient).

SÖZLEŞME (istem 44 §2–§3): araştırma modeli (petri / fantom) AI Pro önerisi, BAŞLATMASI ve sürüş-anı mühür denetimi GEÇERLİ sabit
düzlem kalibrasyonu ister — yok / bozuk / seçili kamera kalibrasyon kamerası değil / fantomda kalınlık girilmemiş → 409 (neden + eylem,
istek dilinde) ve onay TÜKETİLMEZ. Kedi bu kapıya tabi değil. Kalibrasyon ekranının uçları (KD-2 çok konumlu): kare (kuyular otomatik,
sunucuda saklanır) → ≥ 2 konum hesapla → kaydet (lens uyarısı AÇIK onay; denetim izi) → doğrula (merkez ≤ 1 cm) → fantom ayarı ·
numune tabanı · kalibre etmeden devam; seans sürerken değişiklik 409. Kamera kimliği (ad + VID/PID) indeks yerine karşılaştırılır.
Sahte EN ALT katta: kabin kamerası karesi gerçek izdüşümle çizilen sentetik kabin (`sabit_duzlem_sahne.py`); sağlayıcı sahte; veri kökü
testin geçici dizini; denetim izi DB çağrı sınırında kaydedici.
"""

from __future__ import annotations

import base64
import time

import i18n_yardimci as iy
import numpy as np
import pytest
import sabit_duzlem_sahne as sh
from fastapi.testclient import TestClient
from kd_kalibrasyon_yardimci import (
    odak_tahminci,  # noqa: F401  ODAK sahtesi (bu dosya DÜZLEM kapısını ölçer; ODAK test_ODK_*)
)


def _sag(ad: str):
    class _Sag:
        title = f"Sahte {ad}"
        subject_label = "sahte özne"
        achieved_B = 0.001
        duty_sum = 2.4
        join_timeout_s = 6.0
        varsayilan_hedef = 0

        def hedef_idleri(self):
            return frozenset({0, 1})

        def yukle(self):
            return None

        def localize(self, frame_bgr, hedef_id):
            return (True, 1.0, 2.0, 3.0, 0.9, None, True, None)

        def predict(self, x, y, z, hedef_id):
            return [0.2] * 7, [0.0] * 7, 0.3

        def hedef_adi(self, hedef_id):
            return f"{ad} {hedef_id}"

        def ipucu(self, ozne_var, hedef_adi):
            return "sahte ipucu"

        def xai_sensitivity(self, *a, **k):
            return None

    s = _Sag()
    s.ad = ad
    return s


def _jpeg(bgr) -> str:
    import cv2

    ok, b = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert ok
    return base64.b64encode(b.tobytes()).decode("ascii")


@pytest.fixture()
def env(monkeypatch, tmp_path):
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air
    import servers.api_server as apis
    import servers.settings_router as sr
    from utils import kabin_kamerasi as kk

    monkeypatch.setitem(hedef.SAGLAYICILAR, "fantom", _sag("fantom"))
    monkeypatch.setitem(hedef.SAGLAYICILAR, "petri", _sag("petri"))
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO", "1")
    monkeypatch.setenv("PEMF_ARASTIRMA_AIPRO_FANTOM", "1")
    monkeypatch.setattr(hedef, "duzlem_veri_koku", lambda: tmp_path)
    secim = {"indeks": 1, "kimlik": None}
    monkeypatch.setattr(kk, "secili_kamera", lambda: dict(secim, kaynak="ayar"))
    monkeypatch.setattr(sr, "_ai_kamerasi_mesgul", lambda: False)
    izler: list = []

    class _DB:
        def record_session_event(self, sid, olay, payload=None, severity="info"):
            izler.append((olay, payload))

    monkeypatch.setattr(apis, "_get_treatment_db", lambda: _DB())
    # kabin kamerası: sentetik kabin (kamera üst kapakta; plaka `plaka` konumunda; duruş `R` / `t` — "kamera oynadı" için değişir)
    K, D = sh.ic_parametre()
    R, t = sh.poz()
    sahne = {"plaka": SOL, "plaka_var": True, "R": R, "t": t}
    monkeypatch.setattr(
        kk,
        "kare_al",
        lambda *a, **k: {
            "indeks": secim["indeks"],
            "kimlik": secim.get("kimlik"),
            "genislik": sh.W,
            "yukseklik": sh.H,
            "image_base64": _jpeg(
                sh.ciz(sahne["R"], sahne["t"], K, D, plaka=sahne["plaka"], plaka_var=sahne["plaka_var"])
            ),
        },
    )
    snap_cache = dict(air._ai_organ_cache)
    snap = (air._ai_hedef_modeli, air._ai_organ_id, air._ai_owner_client)
    air._ai_loop_active = False
    air._ai_hazirlik_active = False

    def taze(model: str, hedef_id: int = 1):
        air._ai_hedef_modeli = model
        air._ai_organ_id = hedef_id
        with air._ai_cache_lock:
            air._ai_organ_cache.update(
                {
                    "x_mm": 1.0,
                    "y_mm": 2.0,
                    "z_mm": 3.0,
                    "reliability": 0.9,
                    "localized": True,
                    "overlay_bgr": None,
                    "at": time.time(),
                    "organ_id": hedef_id,
                    "kedi_var": True,
                    "guven_dokumu": None,
                    "model": model,
                }
            )

    yield {
        "air": air,
        "hedef": hedef,
        "client": TestClient(apis.app),
        "taze": taze,
        "izler": izler,
        "kok": tmp_path,
        "secim": secim,
        "sahne": sahne,
        "K": K,
        "D": D,
        "R": R,
        "t": t,
    }
    air._ai_loop_active = False
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap_cache)
    air._ai_hedef_modeli, air._ai_organ_id, air._ai_owner_client = snap


#: KD-2: kalibrasyon kabinin İKİ YANINDA (sol / sağ) iki konumla; doğrulama başka yerde.
SOL, SAG, BASKA = (115.0, -32.5), (-110.0, -32.5), (40.0, 30.0)


def _kare(e, plaka) -> dict:
    e["sahne"]["plaka"] = plaka
    k = e["client"].post("/api/ai/pro/kalibrasyon/kare", json={}).json()
    assert k["plaka"]["bulundu"] is True, k["plaka"]
    return k


def _olcumler(plaka, *, bozuk_kose=False, n=4):
    """Numaralı köşelerin (1 ön-sol, 2 ön-sağ, 3 arka-sağ, 4 arka-sol — görüntünün üstü arka) GERÇEK cetvel ölçüsü."""
    olc = sh.olcum_cm(sh.koseler(*plaka))
    if bozuk_kose:
        olc[2] = (olc[2][0] + 5.0, olc[2][1])
    sec = [0, 2] if n == 2 else list(range(4))
    return [{"solCm": o[0], "onCm": o[1]} if i in sec else None for i, o in enumerate(olc)]


def _govde(e, kareler, *, lens_fark_cm=0.0, bozuk_kose=False, n=4):
    """`kareler`: [(kare kimliği, plaka)]."""
    sol, on, taban = sh.lens_cm()
    return {
        "konumlar": [
            {"kareKimligi": kim, "olcumler": _olcumler(pl, bozuk_kose=bozuk_kose and i == 0, n=n)}
            for i, (kim, pl) in enumerate(kareler)
        ],
        "lens": {"solCm": sol + lens_fark_cm, "onCm": on, "tabanCm": taban},
        "plakaYuksekligiCm": 2.0,
    }


def _iki_kare(e):
    return [(_kare(e, SOL)["kareKimligi"], SOL), (_kare(e, SAG)["kareKimligi"], SAG)]


def _kalibre(e) -> dict:
    r = e["client"].post("/api/ai/pro/kalibrasyon/kaydet", json=_govde(e, _iki_kare(e)))
    assert r.status_code == 200, r.text
    return r.json()


def _kapi_tr(anahtar: str, dil: str = "tr") -> str:
    return iy.katalog("sunucu", dil)[anahtar]


# ═══ Sürüş kapısı ══════════════════════════════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_oneri_KALIBRASYON_YOKSA_409_eylem_metni_TR_ve_EN(env):
    env["taze"]("petri")
    c = env["client"]
    r = c.post("/api/ai/pro/propose", json={"organ_id": 1, "model": "petri"})
    assert r.status_code == 409 and r.json()["detail"] == _kapi_tr("ai.pemf.kapi.kalibrasyonYok"), r.text
    r = c.post("/api/ai/pro/propose", json={"organ_id": 1, "model": "petri"}, headers={"X-PEMF-Dil": "en"})
    assert r.status_code == 409 and r.json()["detail"] == _kapi_tr("ai.pemf.kapi.kalibrasyonYok", "en"), r.text


def test_KARSIT_gecerli_kalibrasyonla_oneri_KALIBRASYON_kapisindan_gecer(env):
    _kalibre(env)
    env["taze"]("petri")
    r = env["client"].post("/api/ai/pro/propose", json={"organ_id": 1, "model": "petri"})
    assert r.status_code == 200, r.text


def test_KRITIK_secili_kamera_KALIBRASYON_kamerasi_degilse_409(env):
    _kalibre(env)
    env["secim"]["indeks"] = 0
    env["taze"]("petri")
    r = env["client"].post("/api/ai/pro/propose", json={"organ_id": 1, "model": "petri"})
    assert r.status_code == 409 and r.json()["detail"] == _kapi_tr("ai.pemf.kapi.kameraFarkli"), r.text


def test_KRITIK_BOZUK_kalibrasyon_409(env):
    from ai_hub.cv_ortak import sabit_duzlem as sd

    _kalibre(env)
    (sd.klasor(env["kok"]) / sd.DOSYA_ADI).write_text("{bozuk", encoding="utf-8")
    env["taze"]("petri")
    r = env["client"].post("/api/ai/pro/propose", json={"organ_id": 1, "model": "petri"})
    assert r.status_code == 409 and r.json()["detail"] == _kapi_tr("ai.pemf.kapi.kalibrasyonBozuk"), r.text


def test_KRITIK_fantom_KALINLIK_girilmeden_409_girilince_gecer(env):
    _kalibre(env)
    env["taze"]("fantom")
    c = env["client"]
    r = c.post("/api/ai/pro/propose", json={"organ_id": 1, "model": "fantom"})
    assert r.status_code == 409 and r.json()["detail"] == _kapi_tr("ai.pemf.kapi.fantomAyariYok"), r.text
    assert (
        c.post("/api/ai/pro/kalibrasyon/fantom", json={"kalinlikCm": 3.0, "tumorDerinligiCm": 0.5}).status_code == 200
    )
    env["taze"]("fantom")
    assert c.post("/api/ai/pro/propose", json={"organ_id": 1, "model": "fantom"}).status_code == 200


def test_KRITIK_baslatma_KALIBRASYON_YOKSA_409_ve_onay_TUKETILMEZ(env, monkeypatch):
    from servers import ai_approval

    tuketilen: list = []
    monkeypatch.setattr(
        ai_approval, "dogrula", lambda pid: {"specs": {"model": "petri", "organ_id": 1, "duration_minutes": 1}}
    )
    monkeypatch.setattr(ai_approval, "consume", lambda pid: tuketilen.append(pid) or {})
    r = env["client"].post("/api/ai/pro/start", json={"proposal_id": "p-kd"})
    assert r.status_code == 409 and r.json()["detail"] == _kapi_tr("ai.pemf.kapi.kalibrasyonYok"), r.text
    assert tuketilen == [], "başlamayan seans hekimin onayını tüketti"


def test_KRITIK_SURUS_ANINDA_kalibrasyon_denetlenir_kedi_TABI_DEGIL(env):
    from ai_hub.cv_ortak import sabit_duzlem as sd

    air = env["air"]
    hedef = env["hedef"]
    air._ai_hedef_modeli = "petri"
    orj = hedef.saglayici_al
    try:
        hedef.saglayici_al = lambda m=None: hedef.SAGLAYICILAR["petri"]
        air_aktif = getattr(air, "_aktif_saglayici")
        assert air_aktif().ad == "petri"
        assert air._muhur_surulebilir_mi({"model": "petri"}) is False, "kalibrasyon yokken mühür sürülebilir sayıldı"
        _kalibre(env)
        assert air._muhur_surulebilir_mi({"model": "petri"}) is True
        (sd.klasor(env["kok"]) / sd.DOSYA_ADI).unlink()  # seans sürerken kalibrasyon silindi
        assert air._muhur_surulebilir_mi({"model": "petri"}) is False
    finally:
        hedef.saglayici_al = orj
    air._duzlem_kalibrasyonu_kapisi(hedef.SAGLAYICILAR["kedi"])  # kedi: kalibrasyonsuz da 409 YOK (Y142 kendi kapısı)


def test_KRITIK_ACIL_DURDUR_kalibrasyon_kapisina_BAGLI_DEGIL():
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1]
    api = (kok / "apps" / "backend" / "servers" / "api_server.py").read_text(encoding="utf-8")
    assert "_duzlem_kalibrasyonu_kapisi" not in api and "duzlem_surus_engeli" not in api
    router = (kok / "apps" / "backend" / "servers" / "ai_router.py").read_text(encoding="utf-8")
    bas = router.index('@ai_router.post("/api/ai/pro/stop")')
    son = router.index("@ai_router.post", bas + 10)
    assert "_duzlem_kalibrasyonu_kapisi" not in router[bas:son], "AI Pro STOP kalibrasyon kapısına bağlandı"


# ═══ Kalibrasyon uçları ════════════════════════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_kare_KUYULAR_otomatik_hesapla_kaydet_IKI_konum_ve_DENETIM_izi(env):
    from ai_hub.cv_ortak import sabit_duzlem as sd

    c = env["client"]
    assert c.get("/api/ai/pro/kalibrasyon").json()["gecerli"] is False
    k = _kare(env, SOL)
    assert (k["genislik"], k["yukseklik"]) == (sh.W, sh.H) and k["kareKimligi"] and k["image_base64"]
    assert k["plaka"]["kuyuSayisi"] == 24 and len(k["plaka"]["kosePx"]) == 4, k["plaka"]
    kareler = [(k["kareKimligi"], SOL), (_kare(env, SAG)["kareKimligi"], SAG)]
    h = c.post("/api/ai/pro/kalibrasyon/hesapla", json=_govde(env, kareler)).json()
    # Çizilmiş kare (JPEG + Hough) tespit gürültüsü eğime yansır: lens yatayda ~1 cm (eşik 2 cm); ölçüm uyumu < 1 mm adlandırmayı kanıtlar.
    assert (
        h["gecerli"] is True
        and h["izdusumHatasiPx"] < 1.5
        and h["lensYatayFarkiCm"] < 1.5
        and h["lensUyarisi"] is False
    ), h
    assert h["olcumUyumuMm"] < 1.5, h
    assert h["yayilimCm"] >= 20.0 and len(h["konumlar"]) == 2 and h["gorusAlani"]["onCm"] is not None, h
    assert not (sd.klasor(env["kok"]) / sd.DOSYA_ADI).exists(), "hesapla KAYDETMEMELİ"
    r = c.post("/api/ai/pro/kalibrasyon/kaydet", json=_govde(env, kareler))
    assert r.status_code == 200 and r.json()["durum"]["gecerli"] is True and r.json()["durum"]["konumSayisi"] == 2, (
        r.text
    )
    kal, hata = sd.yukle(env["kok"])
    assert hata is None and kal["kamera"]["indeks"] == 1 and kal["referans"]["sahne_denetimi"] is True
    assert len(kal["konumlar"]) == 2 and kal["ic_parametre"]["sha256"] and kal["olculen_lens_mm"] and kal["gorus_alani"]
    assert [o for o, _ in env["izler"]] == ["kabin_kalibrasyonu_kaydedildi"] and r.json()["denetimIziYazildi"] is True


def test_KRITIK_TEK_konum_422_EYLEM_metni(env):
    k = _kare(env, SOL)
    r = env["client"].post("/api/ai/pro/kalibrasyon/kaydet", json=_govde(env, [(k["kareKimligi"], SOL)]))
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["sonuc"]["nedenler"] == [
        {"kod": "konum_az", "metin": _kapi_tr("ai.kalibrasyon.neden.konumAz")}
    ]


def test_KRITIK_plaka_BULUNAMAYAN_kare_EYLEM_soyler_hesaba_GIRMEZ(env):
    env["sahne"]["plaka_var"] = False
    k = env["client"].post("/api/ai/pro/kalibrasyon/kare", json={}).json()
    assert k["plaka"]["bulundu"] is False and k["plaka"]["metin"] == _kapi_tr("ai.kalibrasyon.plakaBulunamadi"), k[
        "plaka"
    ]
    env["sahne"]["plaka_var"] = True
    g = _govde(env, [(k["kareKimligi"], SOL), (_kare(env, SAG)["kareKimligi"], SAG)])
    r = env["client"].post("/api/ai/pro/kalibrasyon/hesapla", json=g)
    assert r.status_code == 422 and r.json()["detail"] == _kapi_tr("ai.kalibrasyon.plakaBulunamadi"), r.text


def test_KRITIK_lens_farki_2cm_ACIK_onay_olmadan_KAYDEDILMEZ(env):
    c = env["client"]
    g = _govde(env, _iki_kare(env), lens_fark_cm=3.0)
    r = c.post("/api/ai/pro/kalibrasyon/kaydet", json=g)
    assert r.status_code == 409 and r.json()["detail"]["sonuc"]["lensUyarisi"] is True, r.text
    assert "cm" in r.json()["detail"]["mesaj"]
    g["lensUyarisiniOnayla"] = True
    assert c.post("/api/ai/pro/kalibrasyon/kaydet", json=g).status_code == 200


def test_KRITIK_tutarsiz_kose_olcusu_422_EYLEM_metni(env):
    r = env["client"].post("/api/ai/pro/kalibrasyon/kaydet", json=_govde(env, _iki_kare(env), bozuk_kose=True))
    assert r.status_code == 422, r.text
    neden = r.json()["detail"]["sonuc"]["nedenler"]
    assert {"kod": "olcum_tutarsiz", "metin": _kapi_tr("ai.kalibrasyon.neden.olcumTutarsiz")} in neden, neden
    assert env["izler"] == []


def test_KRITIK_dogrula_plaka_BASKA_yerde_MERKEZ_1cm_icinde(env):
    _kalibre(env)
    c = env["client"]
    k = _kare(env, BASKA)
    olc = _olcumler(BASKA, n=2)
    r = c.post("/api/ai/pro/kalibrasyon/dogrula", json={"kareKimligi": k["kareKimligi"], "olcumler": olc})
    assert r.status_code == 200 and r.json()["gecti"] is True and r.json()["merkezFarkCm"] <= 1.0, r.text
    assert r.json()["farkCm"][1] is None and r.json()["farkCm"][0] <= 1.0
    assert [o for o, _ in env["izler"]][-1] == "kabin_kalibrasyonu_dogrulandi"
    yanlis = [None if q is None else dict(q, solCm=q["solCm"] + 3.0) for q in olc]  # ölçü 3 cm yanlış → KALIR
    r2 = c.post("/api/ai/pro/kalibrasyon/dogrula", json={"kareKimligi": k["kareKimligi"], "olcumler": yanlis})
    assert r2.json()["gecti"] is False and r2.json()["merkezFarkCm"] > 2.5


def test_KRITIK_seans_SURERKEN_kalibrasyon_fantom_taban_sahne_DEGISMEZ(env):
    _kalibre(env)
    c = env["client"]
    env["air"]._ai_loop_active = True
    try:
        for yol, govde in (
            ("/api/ai/pro/kalibrasyon/fantom", {"kalinlikCm": 3.0}),
            ("/api/ai/pro/kalibrasyon/taban", {"lensUzaklikCm": 30.0}),
            ("/api/ai/pro/kalibrasyon/sahne-yenile", {}),
        ):
            r = c.post(yol, json=govde)
            assert r.status_code == 409 and r.json()["detail"] == _kapi_tr("ai.kalibrasyon.seansSuruyor"), (yol, r.text)
    finally:
        env["air"]._ai_loop_active = False


@pytest.mark.parametrize(
    "govde",
    [{"kalinlikCm": 0}, {"kalinlikCm": 25}, {"kalinlikCm": 3, "tumorDerinligiCm": 3}, {"kalinlikCm": 3, "boyCm": 10}],
)
def test_fantom_ayari_GECERSIZ_422(env, govde):
    _kalibre(env)
    r = env["client"].post("/api/ai/pro/kalibrasyon/fantom", json=govde)
    assert r.status_code == 422 and r.json()["detail"] == _kapi_tr("ai.kalibrasyon.fantomGecersiz"), r.text


def test_yeniden_kalibrasyon_FANTOM_ve_TABAN_ayarini_KORUR(env):
    _kalibre(env)
    c = env["client"]
    c.post(
        "/api/ai/pro/kalibrasyon/fantom", json={"kalinlikCm": 3.0, "tumorDerinligiCm": 0.5, "boyCm": 10.4, "enCm": 6.5}
    )
    taban = sh.lens_cm()[2]
    assert c.post("/api/ai/pro/kalibrasyon/taban", json={"lensUzaklikCm": taban - 4.0}).status_code == 200
    d = _kalibre(env)["durum"]
    assert d["fantom"] == {"kalinlikCm": 3.0, "tumorDerinligiCm": 0.5, "boyCm": [10.4, 6.5]}, d
    assert d["tabanYukseltmesiCm"] == 4.0, d


def test_kare_KIMLIGI_yoksa_404_eylem_metni(env):
    r = env["client"].post("/api/ai/pro/kalibrasyon/hesapla", json=_govde(env, [("yok", SOL), ("yok2", SAG)]))
    assert r.status_code == 404 and r.json()["detail"] == _kapi_tr("ai.kalibrasyon.kareYok")


# ═══ KD-2 sahip kararları: numune tabanı · kalibre etmeden devam · kamera kimliği ═══════════════════════════════════════════════════


def test_KRITIK_numune_TABANI_lens_uzakligindan_yukseltme_DENETIM_izi_ve_SINIRLAR(env):
    _kalibre(env)
    c = env["client"]
    taban = sh.lens_cm()[2]
    r = c.post("/api/ai/pro/kalibrasyon/taban", json={"lensUzaklikCm": taban - 5.0})
    assert r.status_code == 200 and r.json()["durum"]["tabanYukseltmesiCm"] == 5.0, r.text
    assert r.json()["durum"]["olculenLensTabanCm"] == taban
    assert [o for o, _ in env["izler"]][-1] == "kabin_kalibrasyonu_numune_tabani"
    for yanlis in (taban - 25.0, taban + 3.0):  # 25 cm yükseltme (> 20) · tabanın altı
        r = c.post("/api/ai/pro/kalibrasyon/taban", json={"lensUzaklikCm": yanlis})
        assert r.status_code == 422 and r.json()["detail"].startswith(
            _kapi_tr("ai.kalibrasyon.tabanGecersiz").split("{{")[0]
        ), r.text
    assert (
        c.post("/api/ai/pro/kalibrasyon/taban", json={"lensUzaklikCm": taban}).json()["durum"]["tabanYukseltmesiCm"]
        == 0.0
    )


@pytest.mark.parametrize("kamera, gecer", [((37.5, 195.0, -122.5), True), ((77.5, 195.0, -122.5), False)])
def test_KRITIK_kalibre_etmeden_DEVAM_yalniz_KUCUK_kaymada(env, kamera, gecer):
    """Sahip (KD-1): kamera ~1 cm oynadı → devam edilebilir (yeni sahne referansı, kalıcı "eski" uyarısı, denetim izi);
    5 cm oynadı → 409 (yeniden kalibrasyon)."""
    _kalibre(env)
    env["sahne"]["R"], env["sahne"]["t"] = sh.poz(kamera)
    env["sahne"]["plaka"] = BASKA
    r = env["client"].post("/api/ai/pro/kalibrasyon/sahne-yenile", json={})
    if gecer:
        assert r.status_code == 200 and r.json()["durum"]["eski"] is True and r.json()["kaymaPx"] > 12.0, r.text
        assert [o for o, _ in env["izler"]][-1] == "kabin_kalibrasyonu_sahne_yenilendi"
    else:
        assert (
            r.status_code == 409 and _kapi_tr("ai.kalibrasyon.sahneYenilemeBuyuk").split("(")[0] in r.json()["detail"]
        ), r.text
        assert [o for o, _ in env["izler"]][-1] == "kabin_kalibrasyonu_sahne_yenileme_reddedildi"
        assert env["client"].get("/api/ai/pro/kalibrasyon").json()["eski"] is False


def test_KRITIK_KAMERA_KIMLIGI_farkliysa_409_ayniysa_INDEKS_degisse_de_gecer(env):
    pusat = {"ad": "FHD Camera", "vidpid": "VID_1BCF&PID_28C4", "aygit_yolu": "yol-1"}
    env["secim"]["kimlik"] = dict(pusat)
    _kalibre(env)
    env["secim"]["indeks"] = 0  # MSMF sırası değişti, kamera AYNI
    env["taze"]("petri")
    assert env["client"].post("/api/ai/pro/propose", json={"organ_id": 1, "model": "petri"}).status_code == 200
    env["secim"]["kimlik"] = {"ad": "HP True Vision FHD Camera", "vidpid": "VID_30C9&PID_0069", "aygit_yolu": "yol-2"}
    env["taze"]("petri")
    r = env["client"].post("/api/ai/pro/propose", json={"organ_id": 1, "model": "petri"})
    assert r.status_code == 409 and r.json()["detail"] == _kapi_tr("ai.pemf.kapi.kameraFarkli"), r.text


# ═══ PEMF kapısı metni istek dilinde ═══════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_KRITIK_analiz_yanitinda_FIZIKSEL_neden_ISTEK_dilinde(dil):
    from servers import ai_router as air
    from utils import ceviri

    jeton = ceviri.istek_dili_var.set(dil)
    try:
        d = air._pemf_alanlari(
            {"success": True, "pemf_valid": False, "warnings": ["kamera_oynamis: sahne 40 px"]}, "petri"
        )
    finally:
        ceviri.istek_dili_var.reset(jeton)
    k = d["pemf_kapisi"]
    beklenen = _kapi_tr("ai.pemf.kapi.kameraOynamis", dil)
    assert (
        k["surulebilir"] is False
        and k["eylem"] == beklenen
        and k["mesajlar"] == [{"kod": "kamera_oynamis", "metin": beklenen}]
    ), k


def test_kapi_metni_HER_fiziksel_kod_icin_katalogda():
    from servers import ai_pro_hedef

    from ai_hub.cv_ortak import pemf_kapisi

    for kod in pemf_kapisi.FIZIKSEL:
        m = ai_pro_hedef.kapi_metni(kod)
        assert m and m != kod and not m.startswith("ai."), (kod, m)
    assert ai_pro_hedef.kapi_metni("layout_mismatch") is None
    _ = np  # numpy aparat için içe aktarıldı (sh)


# ═══ Sağlayıcı (AI Pro döngüsü) — denetimi düşen kare LOKALİZE SAYILMAZ ═════════════════════════════════════════════════════════════


class _SahteEM:
    def predict(self, x, y, z, organ_id, achieved_B, duty_sum):
        d = {f"D{k}": 0.5 for k in range(1, 8)}
        d.update({f"P{k}": 100.0 for k in range(1, 8)})
        d.update(result_E_healthy=0.1, result_E_cancer=0.1, result_E_avg=0.1)
        return d


@pytest.mark.parametrize("kamera, gecer", [(sh.KAMERA_MM, True), ((47.5, 195.0, -122.5), False)])
def test_KRITIK_PetriSaglayici_GERCEK_hat_kamera_OYNAYINCA_lokalize_YOK_ipucu_NEDEN(
    env, monkeypatch, tmp_path, kamera, gecer
):
    from servers import ai_pro_hedef

    from ai_hub.inference_petri_dish.petri_cv_v2 import PetriCvPipeline, load_cabin_config

    _kalibre(env)
    yol = tmp_path / "yolo_yok.onnx"
    yol.write_bytes(b"")
    onbellek = {
        "cls": PetriCvPipeline,
        "cfg": load_cabin_config(None),
        "yolo": None,
        "predictor": _SahteEM(),
        "yolo_path": yol,
    }
    sag = ai_pro_hedef.PetriSaglayici()
    monkeypatch.setattr(sag, "_onbellek", lambda: onbellek)
    R2, t2 = sh.poz(kamera)
    kare = sh.ciz(R2, t2, env["K"], env["D"], plaka=(60.0, 20.0))
    lok, x, y, z, guven, _ov, ozne, _dokum = sag.localize(kare, 0)
    meta = sag.son_lokalizasyon_meta()
    if gecer:
        assert lok is True and meta["method"] == "sabit_duzlem" and y == -172.0, (lok, meta.get("pemf_kapisi"))
        assert meta["pemf_kapisi"]["surulebilir"] is True
    else:
        assert lok is False and ozne is True, "kamera oynadı ama kare lokalize sayıldı"
        assert "kamera_oynamis" in meta["pemf_kapisi"]["nedenler"]
        assert sag.ipucu(True, "Kuyu") == _kapi_tr("ai.pemf.kapi.kameraOynamis"), sag.ipucu(True, "Kuyu")


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_KRITIK_KOR_BOLGE_kapi_metni_YON_ve_on_SERIT_cm_istek_dilinde(env, dil):
    from servers import ai_pro_hedef
    from utils import ceviri

    _kalibre(env)
    on = env["client"].get("/api/ai/pro/kalibrasyon").json()["gorusAlani"]["on"]
    jeton = ceviri.istek_dili_var.set(dil)
    try:
        m = ai_pro_hedef.kapi_metni("kor_bolge_on")
        ipucu = ai_pro_hedef.SAGLAYICILAR["kedi"] and ai_pro_hedef.kor_bolge_ipucu()
    finally:
        ceviri.istek_dili_var.reset(jeton)
    assert m.startswith(_kapi_tr("ai.pemf.kapi.korBolgeOn", dil)) and f"{on:g}" in m, (m, on)
    assert f"{on:g}" in ipucu and ipucu.strip().startswith(_kapi_tr("ai.pro.ipucu.korBolge", dil).split("{{")[0]), ipucu


def test_KRITIK_kalibre_etmeden_devam_edildiyse_ANALIZ_yanitinda_KALICI_uyari():
    from servers import ai_router as air

    d = air._pemf_alanlari(
        {"success": True, "pemf_valid": True, "warnings": [], "kalibrasyon": {"eski": True}}, "petri"
    )
    assert d["kalibrasyon_uyarisi"] == _kapi_tr("ai.pemf.kapi.kalibrasyonEski"), d
    d2 = air._pemf_alanlari(
        {"success": True, "pemf_valid": True, "warnings": [], "kalibrasyon": {"eski": False}}, "petri"
    )
    assert "kalibrasyon_uyarisi" not in d2


@pytest.mark.parametrize("yol", ["/api/ai/pro/kalibrasyon/kare", "/api/ai/pro/kalibrasyon/sahne-yenile"])
def test_KRITIK_govdesiz_KAMERA_ve_DURUM_uclari_HAM_POSTu_reddeder_D5(env, yol):
    """D5 · Y204: kamera açan / kalibrasyonu değiştiren uç ön-uçuşsuz (ham) POST'la ÇALIŞMAZ — JSON gövde zorunlu (arayüz `{}` gönderir)."""
    r = env["client"].post(yol, content=b"x", headers={"Content-Type": "text/plain"})
    assert r.status_code == 422, r.text
    assert env["izler"] == []
