# -*- coding: utf-8 -*-
"""OTB T-7 / T-8 (ODM tezgâhı 19-11, sahip kuralı): "Sensör seans sırasında petrinin yanına konabilmeli; kamera petriyi gördüğü sürece,
kuyular bulunuyorsa devam."

ÖLÇÜLEN (85 tanı karesi, uygulama KAPALIYKEN, plaka OYNAMADAN — `DENETIM\\odak\\otb\\`): koşulsuz petri seansında her kare ODAK 24'lük
ızgarayla doğrulanıyordu (ODD5 B-5); üst sırası BOŞ plakada hattın ECC inceltmesi ızgarayı sıvılı 3 sıraya SIKIŞTIRIYORDU (satır aralığı
14,3 mm, sütun 19,3 mm) → katı 19,3 mm oturtma 5–11 mm sapıp `plakaUyumsuz`; 30 sn iyi kare gelmezse seans duruyordu. Sensör plakanın
yanındayken bu sıkışma HER karede (15 / 15).
SÖZLEŞME:
  · sabit düzlem kipinde kabin mm'de kuyu aralığı plakanınkinden (19,3 mm) %15'ten çok sapan ızgara varsayımı SEÇİLMEZ (`plate_grid`);
  · seansın İLK doğrulanan ızgarası SABİT NUMUNE REFERANSI olur; sonraki karede görülen kuyular (≥ 3) referansla birkaç mm içinde
    örtüşüyorsa kare kabul edilir ve ODAK planı REFERANSTAN hesaplanır; ızgarası doğrulanan karede etiketle, doğrulanmayan karede en yakın
    referans kuyusuyla karşılaştırılır (etiketi güvenilmez);
  · plaka KAYARSA (etiketli sapma > eşik) ya da kaldırılırsa (< 3 kuyu) kare kabul edilmez → Y300 30 sn son plan + STOP AYNEN;
  · hazırlıkta (seans yok) bugünkü her-kare doğrulaması AYNEN; boş kabin hedef YOK (B-5).
"""

from __future__ import annotations

import numpy as np
import pytest
from test_KD_sabit_duzlem_kalibrasyonu import sentetik  # noqa: F401  sentetik kabin (gerçek kalibrasyon çözümü)

SAT, SUT, A = 4, 6, 19.3


def _izgara(dx=0.0, dz=0.0, satir_araligi=A, bos=(), etiketler=None):
    """Ölçüm çerçevesinde (x, z) → backend P listesi (ODAK adayı biçimi)."""
    from ai_hub.odak.oneri import olcum_to_backend

    out = []
    for r in range(SAT):
        for c in range(SUT):
            e = f"{'ABCD'[r]}{c + 1}"
            if e in bos:
                continue
            x = (c - (SUT - 1) / 2) * A + dx
            z = (r - (SAT - 1) / 2) * satir_araligi + dz
            P = olcum_to_backend(np.array([x, -120.0, z]))
            out.append(
                {
                    "etiket": (etiketler or {}).get(e, e),
                    "P": [float(v) for v in P],
                    "px": [100.0 + 10 * c, 100.0 + 10 * r],
                }
            )
    return out


def test_KRITIK_T8_ayni_yerde_ETIKETLI_kare_ORTUSUR():
    from ai_hub.odak import oneri

    ref = _izgara(bos=("A1", "A2", "A3", "A4", "A5", "A6"))
    k = oneri.sabit_numune_ortusmesi(
        ref, _izgara(dx=1.0, bos=("A1", "A2", "A3", "A4", "A5", "A6", "B3")), etiketli=True
    )
    assert (
        k["ortusuyor"] is True
        and k["gorulen"] == 17
        and k["eslesen"] == 17
        and k["sapma_mm"] == pytest.approx(1.0, abs=0.05)
    )


def test_KRITIK_T8_SIKISMIS_dogrulanmayan_kare_EN_YAKIN_referansla_ORTUSUR():
    """Ölçülen sıkışma: satır aralığı 14,3 mm, ızgara sıvılı sıralara oturmuş (etiketler kayık) — kuyular YİNE plakanın yerinde."""
    from ai_hub.odak import oneri

    ref = _izgara(bos=("A1", "A2", "A3", "A4", "A5", "A6"))
    sikisik = _izgara(satir_araligi=14.3, dz=A / 2)  # 4 sıra 3 sıranın yerine
    k = oneri.sabit_numune_ortusmesi(ref, sikisik, etiketli=False)
    assert k["ortusuyor"] is True and k["eslesen"] == k["gorulen"], k


@pytest.mark.parametrize("dx", [12.0, 19.3, -19.3])
def test_KRITIK_T8_plaka_KAYARSA_dogrulanan_karede_ORTUSMEZ(dx):
    """Bir kuyu aralığı kayma dahil (etiketsiz eşleşme komşu kuyuya kanardı) — doğrulanan karede etiketle yakalanır."""
    from ai_hub.odak import oneri

    ref = _izgara()
    k = oneri.sabit_numune_ortusmesi(ref, _izgara(dx=dx), etiketli=True)
    assert k["ortusuyor"] is False and k["sapma_mm"] >= 11.9, k


def test_KRITIK_T8_plaka_KALDIRILINCA_ya_da_UC_kuyudan_AZ_ORTUSMEZ():
    from ai_hub.odak import oneri

    ref = _izgara()
    assert oneri.sabit_numune_ortusmesi(ref, [], etiketli=False)["ortusuyor"] is False
    assert oneri.sabit_numune_ortusmesi(ref, _izgara()[:2], etiketli=False)["ortusuyor"] is False
    uzak = _izgara(dx=60.0, dz=40.0)
    # referans oturtulamazsa (bozuk / < 3 kuyu) örtüşme YOK (fail-closed)
    assert oneri.sabit_numune_ortusmesi(ref[:2], ref, etiketli=True) == {
        "ortusuyor": False,
        "gorulen": 0,
        "eslesen": 0,
        "sapma_mm": None,
    }
    assert oneri.sabit_numune_ortusmesi(ref, uzak, etiketli=False)["ortusuyor"] is False


def test_T8_esik_ve_en_az_kuyu_SABIT():
    from ai_hub.odak import oneri

    assert oneri.SABIT_NUMUNE_ESIGI_MM == 10.0 and oneri.SABIT_NUMUNE_KABA_ESIK_MM == 10.0 and oneri.IZGARA_EN_AZ == 3


# ── sağlayıcı: seans içi sabit numune (gerçek `localize` + gerçek ODAK ızgarası; sahte: CV hattı sonucu ve adaylar) ─────────────────
def _saglayici(kareler):
    """`kareler`: her `localize` çağrısında sıradaki aday listesi (B-5 düzeneği)."""
    import types

    from servers import ai_pro_hedef as hedef

    sira = list(kareler)

    class _Hat:
        def process_image(self, frame, **k):
            return types.SimpleNamespace(
                success=True,
                error="",
                method="sabit_duzlem",
                mm_per_px=0.5,
                warnings=[],
                pemf_valid=True,
                reliable=False,
                coord_frame="cabin_plane",
                layout={},
            ), {}

    class _S(hedef.PetriSaglayici):
        def _onbellek(self):
            return {"cfg": None}

        def _pipeline_kur(self, cache):
            self.son_pl_kuyu_araligi_uyari = self._sabit_izgara is not None
            return _Hat()

        def _overlay(self, pl, ctx, result):
            return None

        def _egitim_araligi(self):
            raise RuntimeError("aralık yok")

        def _adaylar(self, result):
            return [dict(a) for a in sira.pop(0)]

    s = _S()
    s.kosulsuz = True
    return s


def _kayik(adaylar, dx=0.0, dz=0.0, px_kay=0.0):
    return [{**a, "x": a["x"] + dx, "z": a["z"] + dz, "px": (a["px"][0] + px_kay, a["px"][1])} for a in adaylar]


def _sikisik(adaylar):
    """Ölçülen sıkışma (tezgâh 19-11): 24'lük ızgara üst sırası BOŞ plakanın 3 sıvılı sırasına oturtulmuş — satır aralığı 19,3 → 14,3 mm,
    ızgara merkezi yarım aralık sıvılı sıralara kaymış. Kuyular plakanın yerinde ama katı 19,3 mm ızgaraya OTURMAZ (> 5 mm)."""
    from petri_plaka_aparati import plaka_adaylari

    tum = {a["label"].split()[-1]: a for a in plaka_adaylari()}
    a1, d1 = np.array([tum["A1"]["x"], tum["A1"]["z"]]), np.array([tum["D1"]["x"], tum["D1"]["z"]])
    u = (d1 - a1) / np.linalg.norm(d1 - a1)  # satır ekseni (A → D)
    m = np.mean([[a["x"], a["z"]] for a in tum.values()], axis=0)
    out = []
    for e, a in tum.items():
        if e == "A1":  # tezgâhta da 23 kuyu görülüyordu (24'ün hepsi görülünce ızgara oturtulmaz, ölçülen AYNEN)
            continue
        q = np.array([a["x"], a["z"]])
        t = float((q - m) @ u)
        q2 = q + (0.74 * t - t + 0.5 * 19.3) * u
        out.append({**a, "x": float(q2[0]), "z": float(q2[1])})
    return out


KARE = np.zeros((8, 8, 3), dtype=np.uint8)


def test_KRITIK_T8_seansta_SIKISIK_kare_REFERANSLA_surer_plan_REFERANSTAN():
    from petri_plaka_aparati import plaka_adaylari
    from servers import ai_pro_hedef as hedef

    ref = plaka_adaylari(eksik=("A1", "A2", "A3", "A4", "A5", "A6"))  # üst sıra BOŞ (tezgâhtaki plaka)
    s = _saglayici([ref, _sikisik(ref), _sikisik(ref)])
    hedef.odak_ayarla(s, {"doz_mT": 1.4, "kip": "TUM_PETRI"}, "Tüm petri")
    assert s.localize(KARE, 0)[0] is True  # seansın ilk doğrulanan karesi → referans
    ref_odak = [dict(a) for a in s.son_lokalizasyon_meta()["odak_adaylar"]]
    sonuc = s.localize(KARE, 0)
    meta = s.son_lokalizasyon_meta()
    assert sonuc[0] is True, (
        f"sıkışık kare (plaka yerinde) seansı kesti: {meta.get('plaka_dogrulanmadi')} {meta.get('sabit_numune')}"
    )
    assert meta["odak_adaylar"] == ref_odak, "ODAK planı sabit numune REFERANSINDAN hesaplanmadı"
    assert meta["sabit_numune"]["ortusuyor"] is True and "plaka_dogrulanmadi" not in meta
    assert s.son_pl_kuyu_araligi_uyari is True, "referans varken gürültülü kuyu aralığı hâlâ ENGEL (T-7)"


def test_KRITIK_T8_HAZIRLIKTA_sikisik_kare_bugunku_gibi_REDDEDILIR():
    from petri_plaka_aparati import plaka_adaylari

    ref = plaka_adaylari(eksik=("A1", "A2", "A3", "A4", "A5", "A6"))
    s = _saglayici([ref, _sikisik(ref)])
    assert s.localize(KARE, 0)[0] is True
    assert s.localize(KARE, 0)[0] is False and s.son_lokalizasyon_meta()["plaka_dogrulanmadi"] == "plakaUyumsuz"
    assert s.son_pl_kuyu_araligi_uyari is False


@pytest.mark.parametrize("ad,kare", [("kayma_bir_kuyu", "kuyu"), ("kayma_12mm", "12mm"), ("bos_kabin", "bos")])
def test_KRITIK_T8_plaka_KAYINCA_ya_da_KALKINCA_kare_REDDEDILIR_Y300(ad, kare):
    from petri_plaka_aparati import plaka_adaylari
    from servers import ai_pro_hedef as hedef

    ref = plaka_adaylari()
    sonraki = {"kuyu": _kayik(ref, dx=19.3), "12mm": _kayik(ref, dz=12.0), "bos": []}[kare]
    s = _saglayici([ref, sonraki])
    hedef.odak_ayarla(s, {"doz_mT": 1.4, "kip": "TUM_PETRI"}, "Tüm petri")
    assert s.localize(KARE, 0)[0] is True
    assert s.localize(KARE, 0)[0] is False, ad
    meta = s.son_lokalizasyon_meta()
    assert meta["targets"] == [] and meta["odak_adaylar"] == [] and meta.get("plaka_dogrulanmadi"), meta.get(
        "plaka_dogrulanmadi"
    )
    if kare != "bos":
        assert meta["plaka_dogrulanmadi"] == "plakaKaydi" and meta["sabit_numune"]["sapma_mm"] >= 11.9, meta[
            "sabit_numune"
        ]


def test_KRITIK_T8_YENI_seans_YENI_referans_durdurma_TEMIZLER():
    from petri_plaka_aparati import plaka_adaylari
    from servers import ai_pro_hedef as hedef

    ref = plaka_adaylari()
    yeni_yer = _kayik(ref, dx=40.0)
    s = _saglayici([ref, yeni_yer])
    hedef.odak_ayarla(s, {"doz_mT": 1.4, "kip": "TUM_PETRI"}, "Tüm petri")
    assert s.localize(KARE, 0)[0] is True and s._sabit_izgara is not None
    hedef.odak_ayarla(s, None)  # durdurma
    assert s._sabit_izgara is None
    hedef.odak_ayarla(s, {"doz_mT": 1.4, "kip": "TUM_PETRI"}, "Tüm petri")  # plaka başka yerde, YENİ seans
    assert s.localize(KARE, 0)[0] is True, "yeni seans eski referansla kıyaslandı"


# ── ızgara varsayımı seçimi: sabit düzlem kipinde FİZİKSEL ölçek denetimi (plate_grid + pipeline) ─────────────────────────────────
def _sentetik_H(s, cx=115.0, cz=-32.5, satir_olcek=1.0):
    """Sentetik kabinde plakanın GERÇEK ızgara homografisi (plaka mm → düzeltilmiş px); `satir_olcek` < 1 = satırları sıkıştırılmış varsayım."""
    import cv2
    import sabit_duzlem_sahne as sh

    from ai_hub.cv_ortak import sabit_duzlem as sd

    P = np.array(list(sh.kuyu_merkezleri(cx, cz).values()))
    pl = np.array([[j * sh.ARALIK, i * sh.ARALIK] for i in range(4) for j in range(6)], dtype=np.float64)
    duz = cv2.undistortPoints(
        sh.izdusum(s["R"], s["t"], P, s["K"], s["D"]).reshape(-1, 1, 2),
        s["K"],
        s["D"],
        P=sd._yeni_K(s["K"], s["D"], (sh.W, sh.H)),
    ).reshape(-1, 2)
    Hm, _ = cv2.findHomography(pl.reshape(-1, 1, 2), duz.reshape(-1, 1, 2))
    return Hm @ np.diag([1.0, satir_olcek, 1.0])


def test_KRITIK_T8_pipeline_izgara_OLCEK_denetimi_SIKISIK_varsayimi_REDDEDER(sentetik, tmp_path):
    """Ölçülen sıkışma: satır aralığı 19,3 → 14,3 mm (×0,74). Doğru ızgara GEÇER, sıkışık REDDEDİLİR; kalibrasyon yoksa denetim YOK."""
    import types

    import sabit_duzlem_sahne as sh
    from test_KD_sabit_duzlem_kalibrasyonu import _sd, _sentetik_kayit

    from ai_hub.inference_petri_dish.petri_cv_v2.pipeline import PetriCvPipeline

    s = sentetik
    sd = _sd()
    _sentetik_kayit(tmp_path, s)
    kd = sd.kare_hazirla(sd.yukle(tmp_path), kare_boyutu=(sh.W, sh.H), kamera_indeksi=1)
    sahte = types.SimpleNamespace(plate_type=24)
    denetle = PetriCvPipeline._izgara_olcek_denetimi(sahte, kd, 1.0)
    assert denetle(_sentetik_H(s)) is True
    assert denetle(_sentetik_H(s, satir_olcek=0.74)) is False, (
        "sıkışık (×0,74) ızgara varsayımı fiziksel ölçek denetiminden geçti"
    )
    assert denetle(_sentetik_H(s, satir_olcek=1.25)) is False
    assert PetriCvPipeline._izgara_olcek_denetimi(sahte, None, 1.0) is None
    from ai_hub.inference_petri_dish.petri_cv_v2.coord_transform import KesisimGecersiz

    def _kesisimsiz(*a, **k):
        raise KesisimGecersiz("ışın düzleme paralel")

    kd.harita.kabin_noktasi = _kesisimsiz  # izdüşümü hesaplanamayan varsayım FİZİKSEL sayılmaz (fail-closed)
    assert denetle(_sentetik_H(s)) is False


def test_KRITIK_T8_plate_grid_DENETIMDEN_gecmeyen_varsayimi_SECMEZ_hepsi_gecmezse_AYNEN(sentetik):
    import sabit_duzlem_sahne as sh
    from test_KD_sabit_duzlem_kalibrasyonu import SOL_KONUM, _undistort

    from ai_hub.inference_petri_dish.petri_cv_v2.plate_grid import detect_plate_wells

    s = sentetik
    img = _undistort(sh.ciz(s["R"], s["t"], s["K"], s["D"], plaka=SOL_KONUM), s["K"], s["D"])
    r0 = detect_plate_wells(img, 24)
    assert r0.success and r0.olcek_elenen == []
    r_hepsi = detect_plate_wells(img, 24, izgara_denetimi=lambda H: False)
    assert r_hepsi.chosen == r0.chosen and r_hepsi.olcek_elenen == [], "hiçbiri geçmezken seçim DEĞİŞTİ"
    if len(r0.hypotheses) < 2:
        pytest.skip(f"tek varsayım: {r0.hypotheses}")
    secilen = np.asarray(r0.H_img_from_plate, float)
    r1 = detect_plate_wells(img, 24, izgara_denetimi=lambda H: not np.allclose(np.asarray(H, float), secilen))
    assert r1.chosen != r0.chosen and r0.chosen in r1.olcek_elenen, (r0.chosen, r1.chosen, r1.olcek_elenen)


def test_KRITIK_T7_seansta_kuyu_araligi_sapmasi_ENGEL_degil_UYARI_hazirlikta_ENGEL_AYNEN(sentetik, tmp_path):
    """Gerçek pipeline + sentetik kabin: 2 cm yükseklik değişimi kuyu aralığını saptırır. Bayrak yokken (hazırlık) `kamera_oynamis`
    ENGEL; seansta sabit numune referansı varken (sağlayıcı bayrağı açar) UYARI — konumlar hesaplanır, referans örtüşmesi denetler."""
    import sabit_duzlem_sahne as sh
    from test_KD_sabit_duzlem_kalibrasyonu import _petri, _sentetik_kayit

    duz = _sentetik_kayit(tmp_path, sentetik, referans=False)
    R2, t2 = sh.poz((27.5, 175.0, -122.5))
    kare = sh.ciz(R2, t2, sentetik["K"], sentetik["D"], plaka=(60.0, 20.0))
    res, _ = _petri(duz, tmp_path).process_image(kare)
    assert (
        res.kalibrasyon["olcum"]["kuyu_araligi"]["gecti"] is False and "kamera_oynamis" in res.kalibrasyon["engeller"]
    )
    pl = _petri(duz, tmp_path)
    pl.kuyu_araligi_uyari = True
    res2, _ = pl.process_image(kare)
    assert "kamera_oynamis" not in res2.kalibrasyon["engeller"], res2.kalibrasyon["engeller"]
    assert any(str(w).startswith("kuyu_araligi_sapti") for w in res2.warnings), res2.warnings


def test_KRITIK_T7_saglayici_bayragi_YALNIZ_referans_VARKEN_acar():
    from servers import ai_pro_hedef as hedef

    class _Hat:
        def __init__(self, cfg, **k):
            self.kuyu_araligi_uyari = False

    s = hedef.PetriSaglayici()
    onbellek = {"cls": _Hat, "cfg": None, "yolo_path": "y.onnx", "yolo": None, "predictor": None}
    assert s._pipeline_kur(onbellek).kuyu_araligi_uyari is False
    s._sabit_izgara = [{"etiket": "A1", "P": [0.0, 0.0, 0.0]}]
    assert s._pipeline_kur(onbellek).kuyu_araligi_uyari is True
