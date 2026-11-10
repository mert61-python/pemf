# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KD (istem 44 · sahip Y258–Y259; KD-2 çok konumlu) — SABİT DÜZLEM KALİBRASYONU: plaka kabinin iki yanında (kuyular otomatik + ölçülen
köşeler) + K / D → kamera duruşu KABİN çerçevesinde; her karede piksel → ışın → yatay düzlem → kabin mm; ArUco ARANMAZ. Fail-closed
denetimler bobini HEDEFLETMEZ. KD-2: kalibre etmeden devam, numune tabanı yükseltmesi, kör bölge, kamera kimliği.

KAPI (istem §3): sentetik izdüşüm (bilinen K / R / t → köşe + kuyu pikselleri → kalibrasyon → konum ≤ 1 mm) · kamera 2 cm / 2° oynayınca
denetim KIRMIZI → hedef yok · boş kabinde 0 fantom hedefi (T2B görüntüleriyle) · kalibrasyon bozuk / kamera farklı → konum yok.

ÖLÇÜLEN İKİ KARAR (rapor S-KD.1 / S-KD.2; modül `cv_ortak/sabit_duzlem.py` açıklaması):
  * KD-2 gerçek kareler: tek konum başka yerde 0,8–2,5 cm → iki yana yayılmış ≥ 2 konum, ortak çözüm (S-KD.4);
  * kuyu aralığı yatay 2 cm / 2° kaymayı GÖRMEZ (yalnız yükseklik) → SABİT SAHNE kayması (kalibrasyon karesi referans).
Sahte EN ALT katta: sentetik kare GERÇEK izdüşümle (ürünün M2 K / D'si) çizilir (`tests/sabit_duzlem_sahne.py`); YOLO kapalı (plaka kipinde
yalnız ipucu), doz modeli çağrı sınırında sahte. Gerçek görüntü: `tests/kahin/t2b_2026_10_23/` (KAYNAK.md) ve hocanın fantom kâhini.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
import sabit_duzlem_sahne as sh

T2B = Path(__file__).resolve().parent / "kahin" / "t2b_2026_10_23"
FANTOM_KAHIN = (
    Path(__file__).resolve().parent
    / "kahin"
    / "hoca_cv_2026_10"
    / "fantom"
    / "WhatsApp Image 2026-10-02 at 19.40.11.jpeg"
)
#: Test kendi sabitlerini taşır (mutasyon hedefinden OKUMAZ).
ARALIK = 19.3
PETRI_HEDEF_Y = -172.0  # YAML hedef_duzlem_cm −17,2 (kuyu tabanı)


class _SahteEM:
    """PetriPredictor / PhantomPredictor.predict sözleşmesi — model çağrı sınırında sahte."""

    def predict(self, x, y, z, organ_id, achieved_B, duty_sum):
        d = {f"D{k}": 0.5 for k in range(1, 8)}
        d.update({f"P{k}": 100.0 for k in range(1, 8)})
        d.update(result_E_healthy=0.1, result_E_cancer=0.1, result_E_avg=0.1)
        return d


def _sd():
    from ai_hub.cv_ortak import sabit_duzlem

    return sabit_duzlem


def _undistort(kare, K, D):
    from ai_hub.cv_ortak.coord_transform import CameraIntrinsics, undistort_image

    return undistort_image(kare, CameraIntrinsics(K, D, (kare.shape[1], kare.shape[0]), 0.0))


def _kal(sonuc_ya_da_poz, K, D, boyut, *, duzlem_y, indeks=1, npz_sha=None, fantom=None):
    """Kalibrasyon sözlüğü — `kalibrasyon_coz` sonucundan ya da bilinen (R, t)'den."""
    sd = _sd()
    if isinstance(sonuc_ya_da_poz, dict):
        R, t, izd = sonuc_ya_da_poz["R"], sonuc_ya_da_poz["t_mm"], sonuc_ya_da_poz["izdusum_hatasi_px"]
    else:
        R, t = (np.asarray(v, dtype=np.float64) for v in sonuc_ya_da_poz)
        R, t, izd = R.tolist(), t.ravel().tolist(), 0.0
    kal = {
        "tarih": sd.zaman_damgasi(),
        "kamera": {"indeks": indeks, "genislik": int(boyut[0]), "yukseklik": int(boyut[1])},
        "ic_parametre": {
            "npz": sh.NPZ.name,
            "sha256": npz_sha if npz_sha is not None else sd.dosya_sha256(sh.NPZ),
            "K": np.asarray(K).tolist(),
            "D": np.asarray(D).ravel().tolist(),
        },
        "kabin_ext_cm": list(sh.EXT_CM),
        "duzlem_y_mm": float(duzlem_y),
        "R": R,
        "t_mm": t,
        "izdusum_hatasi_px": float(izd),
        "konumlar": [],
        "plaka": {"tur": 24, "yukseklik_mm": sh.PLAKA_YUK},
    }
    if fantom is not None:
        kal["fantom"] = fantom
    return kal


def _kaydet(kok, kal, ref_und=None, dislanan=()):
    sd = _sd()
    maske = None
    if ref_und is not None:
        maske = sd.cokgen_maskesi((ref_und.shape[1], ref_und.shape[0]), dislanan, genislet_px=40)
        oz = sd.sahne_ozniteligi_say(ref_und, maske)
        kal["referans"] = {"sahne_denetimi": oz >= sd.SAHNE_ASGARI_OZNITELIK, "oznitelik": oz}
    sd.kaydet(kok, kal, referans_bgr=ref_und, referans_maske=maske)
    return sd.yukle(kok)


def _petri(duzlem, tmp_path, *, kamera_indeksi=1, kosulsuz=False):
    from ai_hub.inference_petri_dish.petri_cv_v2 import PetriCvPipeline, load_cabin_config

    yol = tmp_path / "yolo_ipucu_yok.onnx"
    yol.write_bytes(b"")
    pl = PetriCvPipeline(
        load_cabin_config(None),
        yolo_model_path=yol,
        yolo_device="cpu",
        duzlem=duzlem,
        kamera_indeksi=kamera_indeksi,
        kosulsuz=kosulsuz,
    )
    pl.yolo = None  # plaka kipinde YOLO yalnız ipucu → Hough + ECC
    pl._predictor = _SahteEM()
    return pl


def _fantom(duzlem, *, kamera_indeksi=1):
    from ai_hub.inference_em_fantom.phantom_cv_v3 import PhantomCvPipeline, load_cabin_config

    pl = PhantomCvPipeline(load_cabin_config(None), duzlem=duzlem, kamera_indeksi=kamera_indeksi)
    pl._predictor = _SahteEM()
    return pl


def _aruco_yasak(monkeypatch):
    """Sabit düzlem kipinde ArUco ARANMAZ — iki hat da çağırırsa test düşer."""
    from ai_hub.inference_em_fantom.phantom_cv_v3 import pipeline as fp
    from ai_hub.inference_petri_dish.petri_cv_v2 import pipeline as pp

    def _yasak(*_a, **_k):
        raise AssertionError("sabit düzlem kipinde ArUco ARANDI")

    for m in (pp, fp):
        monkeypatch.setattr(m, "detect_aruco_marker", _yasak)
        monkeypatch.setattr(m, "solve_cabin_pose", _yasak)


#: KD-2: kalibrasyonun iki konumu (kabinin İKİ YANI — sol halka / sağ halka benzeri) ve doğrulama konumu (mm, plaka merkezi X / Z).
SOL_KONUM, SAG_KONUM, BASKA = (115.0, -32.5), (-110.0, -32.5), (60.0, 20.0)


@pytest.fixture(scope="module")
def sentetik():
    """Bilinen K / D / duruş + plaka iki yanda → `kalibrasyon_coz` (gerçek ürün yolu: kuyu pikselleri izdüşümle, ölçüler cm)."""
    sd = _sd()
    K, D = sh.ic_parametre()
    R, t = sh.poz()
    konumlar = [sh.konum(R, t, K, D, *SOL_KONUM), sh.konum(R, t, K, D, *SAG_KONUM)]
    r = sd.kalibrasyon_coz(konumlar=konumlar, K=K, D=D, boyut=(sh.W, sh.H), ext_cm=sh.EXT_CM, lens_cm=sh.lens_cm())
    px = sh.izdusum(R, t, sh.koseler(*SOL_KONUM), K, D)
    kare1 = sh.ciz(R, t, K, D, plaka=SOL_KONUM)
    return {"K": K, "D": D, "R": R, "t": t, "px": px, "r": r, "kare1": kare1, "konumlar": konumlar}


def _sentetik_kayit(tmp_path, s, *, referans=True, ek=None):
    sd = _sd()
    kal = _kal(s["r"], s["K"], s["D"], (sh.W, sh.H), duzlem_y=s["r"]["duzlem_y_mm"])
    kal.update(ek or {})
    hm = sd.DuzlemHaritasi(kal)
    import cv2

    poly = cv2.undistortPoints(s["px"].reshape(-1, 1, 2), s["K"], s["D"], P=hm.K_yeni).reshape(-1, 2)
    und = _undistort(s["kare1"], s["K"], s["D"])
    return _kaydet(tmp_path, kal, und if referans else None, [poly])


def _coz(s, konumlar, **k):
    return _sd().kalibrasyon_coz(
        konumlar=konumlar,
        K=s["K"],
        D=s["D"],
        boyut=(sh.W, sh.H),
        ext_cm=sh.EXT_CM,
        lens_cm=k.pop("lens_cm", sh.lens_cm()),
        **k,
    )


# ═══ 1. Geometri — sahibin yöntemi, KD-2 çok konumlu (KAPI: konum ≤ 1 mm) ═══════════════════════════════════════════════════════════


def test_KRITIK_sentetik_IKI_KONUM_kalibrasyon_baska_yerde_KONUM_1mm(sentetik):
    sd = _sd()
    r = sentetik["r"]
    assert r["gecerli"] is True and r["nedenler"] == [], r
    assert r["izdusum_hatasi_px"] < 0.5 and r["olcum_uyumu_mm"] < 1.0, r
    assert r["lens_yatay_farki_mm"] < 2.0 and abs(r["lens_dikey_farki_mm"]) < 2.0 and r["lens_uyarisi"] is False, r
    assert r["yayilim_mm"] >= 200.0 and len(r["konumlar"]) == 2
    hm = sd.DuzlemHaritasi(_kal(r, sentetik["K"], sentetik["D"], (sh.W, sh.H), duzlem_y=r["duzlem_y_mm"]))
    import cv2

    gercek = sh.kuyu_merkezleri(*BASKA)  # plaka BAŞKA yerde (yalnız X / Z değişir)
    P = np.array(list(gercek.values()))
    ham = sh.izdusum(sentetik["R"], sentetik["t"], P, sentetik["K"], sentetik["D"])
    duz = cv2.undistortPoints(ham.reshape(-1, 1, 2), sentetik["K"], sentetik["D"], P=hm.K_yeni).reshape(-1, 2)
    for kip, pix in (("ham", ham), ("duzeltilmis", duz)):
        hata = [
            np.linalg.norm(hm.kabin_noktasi(p, P[0][1], duzeltilmis=(kip == "duzeltilmis")) - q) for p, q in zip(pix, P)
        ]
        assert max(hata) <= 1.0, f"{kip}: en büyük konum hatası {max(hata):.3f} mm > 1 mm"


def test_KRITIK_cetvel_gurultusu_IKI_KONUM_baska_yerde_MERKEZ_1cm_icinde(sentetik):
    """S-KD.4 (KD-2, gerçek tezgâh ölçüsü): cetvel σ ≈ 5–8 mm köşe başına. σ 6 mm + 0,5 cm okuma + 0,5 px kuyu gürültüsüyle iki
    yana yayılmış iki konum → başka yerdeki plaka MERKEZİ ≤ 1 cm (her denemede) ve kalibrasyon kabul edilir (eşikler gerçek ölçüme göre)."""
    sd = _sd()
    rng = np.random.default_rng(44)
    gecen, hatalar = 0, []
    gercek = np.array(list(sh.kuyu_merkezleri(*BASKA).values()))
    for _ in range(25):
        konumlar = []
        for cx, cz in (SOL_KONUM, SAG_KONUM):
            k = sh.konum(
                sentetik["R"],
                sentetik["t"],
                sentetik["K"],
                sentetik["D"],
                cx,
                cz,
                piksel_gurultu=lambda s_: rng.normal(0, 0.5, s_),
            )
            k["olcum_cm"] = [
                (round((a + rng.normal(0, 0.6)) * 2) / 2, round((b + rng.normal(0, 0.6)) * 2) / 2)
                for a, b in k["olcum_cm"]
            ]
            konumlar.append(k)
        r = _coz(sentetik, konumlar)
        gecen += bool(r["gecerli"])
        hm = sd.DuzlemHaritasi(_kal(r, sentetik["K"], sentetik["D"], (sh.W, sh.H), duzlem_y=r["duzlem_y_mm"]))
        ham = sh.izdusum(sentetik["R"], sentetik["t"], gercek, sentetik["K"], sentetik["D"])
        tah = np.array([hm.kabin_noktasi(p, gercek[0][1], duzeltilmis=False) for p in ham])
        hatalar.append(float(np.linalg.norm((tah - gercek).mean(axis=0)[[0, 2]])))
    assert gecen >= 23, f"cetvel gürültüsünde {gecen}/25 kalibrasyon geçti"
    assert max(hatalar) <= 10.0 and float(np.median(hatalar)) <= 5.0, (max(hatalar), np.median(hatalar))


def test_KRITIK_TEK_konum_ve_AYNI_YANDA_iki_konum_REDDEDILIR(sentetik):
    """KD-2 bulgusu (gerçek kareler): tek konum başka yerde 2,5 cm'ye, aynı yandaki iki konum karşı yanda 1,9 cm'ye kaçtı."""
    r1 = _coz(sentetik, sentetik["konumlar"][:1])
    assert r1["gecerli"] is False and r1["nedenler"] == ["konum_az"], r1
    yakin = sh.konum(sentetik["R"], sentetik["t"], sentetik["K"], sentetik["D"], 115.0, 60.0)  # aynı yan, 9 cm arkada
    r2 = _coz(sentetik, [sentetik["konumlar"][0], yakin])
    assert r2["gecerli"] is False and "konum_yayilimi_az" in r2["nedenler"] and r2["yayilim_mm"] < 200.0, r2
    tek_kose = dict(sentetik["konumlar"][1], olcum_cm=[sentetik["konumlar"][1]["olcum_cm"][0], None, None, None])
    r3 = _coz(sentetik, [sentetik["konumlar"][0], tek_kose])
    assert r3["gecerli"] is False and r3["nedenler"] == ["olcum_eksik"], r3


def test_CAPRAZ_kose_IKI_olcu_YETER(sentetik):
    k = [dict(x, olcum_cm=[x["olcum_cm"][0], None, x["olcum_cm"][2], None]) for x in sentetik["konumlar"]]
    r = _coz(sentetik, k)
    assert r["gecerli"] is True and r["izdusum_hatasi_px"] < 0.5, r


@pytest.mark.parametrize(
    "bozma, kod",
    [
        ("kose_5cm", "olcum_tutarsiz"),  # bir köşe ölçüsü 5 cm yanlış yazılmış
        ("numara_karisik", "olcum_tutarsiz"),  # 1 ve 2 numaralı köşelerin ölçüleri yer değiştirmiş
        ("izgara_bozuk", "izdusum_yuksek"),  # bir konumda kuyu tespiti bozuk (σ 6 px) — tek kamera duruşuna uymaz
    ],
)
def test_KRITIK_kaba_hata_REDDEDILIR(sentetik, bozma, kod):
    k = [dict(x) for x in sentetik["konumlar"]]
    olc = list(k[0]["olcum_cm"])
    if bozma == "kose_5cm":
        olc[2] = (olc[2][0] + 5.0, olc[2][1])
    elif bozma == "numara_karisik":
        olc[0], olc[1] = olc[1], olc[0]
    else:
        k[1]["kuyu_px"] = k[1]["kuyu_px"] + np.random.default_rng(7).normal(0, 6.0, k[1]["kuyu_px"].shape)
    k[0]["olcum_cm"] = olc
    r = _coz(sentetik, k)
    assert r["gecerli"] is False and kod in r["nedenler"], r


def test_KRITIK_bir_konumda_plaka_DUZ_DEGIL_izgara_olcekli_LENS_uyarisi_onay_ister(sentetik):
    """Ölçülen sınır: tek konumda ızgara %7 ölçekli (plaka altlıkta / yanlış yükseklik) ortak çözümde EĞİMLE soğurulur — izdüşüm küçük
    kalır, kamera konumu ise ölçülen lensten belirgin ayrılır → `lens_uyarisi` (kayıt AÇIK onay ister). Bu yüzden lens ölçüsü istenir."""
    k = [dict(x) for x in sentetik["konumlar"]]
    m = k[1]["kuyu_px"].mean(axis=0)
    k[1]["kuyu_px"] = m + (k[1]["kuyu_px"] - m) * 1.07
    r = _coz(sentetik, k)
    assert r["lens_uyarisi"] is True, r


def test_KRITIK_lens_YATAY_2cm_ve_YUKSEKLIK_3cm_UYARI_ama_kalibrasyon_gecerli(sentetik):
    sol, on, taban = sh.lens_cm()
    for lens, uyari in (
        ((sol + 3.0, on, taban), True),
        ((sol + 1.0, on, taban), False),
        ((sol, on, taban - 2.5), False),  # cam kalınlığı + optik merkez: yükseklik 3 cm'ye kadar uyarısız
        ((sol, on, taban - 4.0), True),
    ):
        r = _coz(sentetik, sentetik["konumlar"], lens_cm=lens)
        assert r["gecerli"] is True and r["lens_uyarisi"] is uyari, (lens, r)


def test_UC_konumda_CAPRAZ_dogrulama_her_plaka_kalanlarla(sentetik):
    ucuncu = sh.konum(sentetik["R"], sentetik["t"], sentetik["K"], sentetik["D"], *BASKA)
    r = _coz(sentetik, sentetik["konumlar"] + [ucuncu])
    assert r["gecerli"] is True and len(r["capraz_dogrulama_mm"]) == 3, r
    assert max(r["capraz_dogrulama_mm"]) < 1.0, r["capraz_dogrulama_mm"]


def test_GORUS_ALANI_on_kor_serit_bagimsiz_izdusumle_ayni(sentetik):
    """Kör bölge (sahip, KD-1): kalibrasyondan ön camın dibindeki görünmeyen şerit — düzeltilmiş karenin ALT kenarı."""
    import cv2

    sd = _sd()
    r = sentetik["r"]
    hm = sd.DuzlemHaritasi(_kal(r, sentetik["K"], sentetik["D"], (sh.W, sh.H), duzlem_y=r["duzlem_y_mm"]))
    ga = sd.gorus_alani(hm, sh.TABAN_Y)
    # bağımsız: tabanda ön → arka tarama, düzeltilmiş karede görünen en öndeki nokta (kabin genişliği boyunca en kötü)
    rv, _ = cv2.Rodrigues(np.asarray(r["R"]))
    en_kotu = 0.0
    for X in np.linspace(-270.0, 270.0, 19):
        for Z in np.arange(-202.5, 202.5, 1.0):
            p, _ = cv2.projectPoints(np.array([[[X, sh.TABAN_Y, Z]]]), rv, np.asarray(r["t_mm"]), hm.K_yeni, None)
            if 0 <= p[0, 0, 1] <= sh.H - 1:
                en_kotu = max(en_kotu, Z + 202.5)
                break
    assert ga["on"] is not None and abs(ga["on"] - en_kotu / 10.0) <= 0.5, (ga, en_kotu)


# ═══ 2. Hat — petri v2 sabit düzlem kipinde ═════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_petri_SABIT_DUZLEM_24_kuyu_KABIN_mm_ve_SURULEBILIR(sentetik, tmp_path, monkeypatch):
    from ai_hub.cv_ortak import pemf_kapisi

    _aruco_yasak(monkeypatch)
    duz = _sentetik_kayit(tmp_path, sentetik)
    kare = sh.ciz(sentetik["R"], sentetik["t"], sentetik["K"], sentetik["D"], plaka=(60.0, 20.0))
    res, _ = _petri(duz, tmp_path).process_image(kare)
    assert (
        res.success and res.method == "sabit_duzlem" and res.coord_frame == "cabin_plane" and res.pemf_valid is True
    ), res.warnings
    gercek = sh.kuyu_merkezleri(60.0, 20.0)
    hata = [
        math.hypot(w.centroid_cabin_mm[0] - gercek[w.well_id][0], w.centroid_cabin_mm[2] - gercek[w.well_id][2])
        for w in res.wells
    ]
    assert len(hata) == 24, f"{len(hata)} kuyu konumlu"
    # Uçtan uca hata hocanın ızgarasının ECC hizalamasını da içerir (kenar kuyularda ~1,3 mm, ölçüldü) — kalibrasyon zinciri ≤ 1 mm.
    assert max(hata) <= 2.0, f"en büyük kuyu konum hatası {max(hata):.2f} mm"
    assert all(w.centroid_cabin_mm[1] == PETRI_HEDEF_Y for w in res.wells), "hedef Y kuyu tabanı (YAML −17,2 cm) değil"
    ka = res.kalibrasyon["olcum"]["kuyu_araligi"]
    assert (
        ka["gecti"] and abs(ka["sutun_mm"] - ARALIK) / ARALIK <= 0.03 and abs(ka["satir_mm"] - ARALIK) / ARALIK <= 0.03
    ), ka
    assert res.kalibrasyon["olcum"]["sahne"]["gecti"] is True
    kapi = pemf_kapisi.degerlendir(res.to_dict(), model="petri")
    assert kapi["surulebilir"] is True, kapi


@pytest.mark.parametrize(
    "ad, kamera, egim",
    [
        ("yatay_2cm", (47.5, 195.0, -122.5), 15.0),
        ("don_2derece", sh.KAMERA_MM, 17.0),
        ("asagi_2cm", (27.5, 175.0, -122.5), 15.0),
    ],
)
def test_KRITIK_kamera_2cm_2derece_OYNARSA_hedef_YOK_kosulsuzda_da(sentetik, tmp_path, ad, kamera, egim):
    from ai_hub.cv_ortak import pemf_kapisi

    duz = _sentetik_kayit(tmp_path, sentetik)
    R2, t2 = sh.poz(kamera, egim)
    kare = sh.ciz(R2, t2, sentetik["K"], sentetik["D"], plaka=(60.0, 20.0))
    for kosulsuz in (False, True):
        res, _ = _petri(duz, tmp_path, kosulsuz=kosulsuz).process_image(kare)
        assert res.pemf_valid is False and "kamera_oynamis" in res.kalibrasyon["engeller"], (ad, res.kalibrasyon)
        assert all(w.centroid_cabin_mm is None and w.konum_hatasi for w in res.wells), (
            f"{ad}: kamera oynadı ama konum üretildi"
        )
        kapi = pemf_kapisi.degerlendir(res.to_dict(), model="petri", kosulsuz=kosulsuz)
        assert kapi["surulebilir"] is False and "kamera_oynamis" in kapi["nedenler"], kapi
        assert "pemf_gecersiz" not in kapi["nedenler"], "ArUco öneren genel metin fiziksel nedenin yanına eklendi"


def test_KRITIK_kuyu_araligi_TEK_BASINA_yukseklik_degisimini_yakalar(sentetik, tmp_path):
    """Referans karesiz kalibrasyon (sahne denetimi yok): 2 cm yükseklik değişimi YALNIZ kuyu aralığıyla yakalanır."""
    duz = _sentetik_kayit(tmp_path, sentetik, referans=False)
    R2, t2 = sh.poz((27.5, 175.0, -122.5))
    res, _ = _petri(duz, tmp_path).process_image(sh.ciz(R2, t2, sentetik["K"], sentetik["D"], plaka=(60.0, 20.0)))
    ka = res.kalibrasyon["olcum"]["kuyu_araligi"]
    assert ka["gecti"] is False and ka["sapma"] > 0.03 and res.pemf_valid is False, ka
    assert "sahne" not in res.kalibrasyon["olcum"]


def test_KARSIT_kuyu_araligi_YATAY_kaymayi_GORMEZ_bu_yuzden_SAHNE_denetimi(sentetik, tmp_path):
    """S-KD.2 kanıtı: yatay 2 cm kaymada aralık %3 içinde kalır — sahne denetimi olmasaydı kare geçerdi (uyarı `sahne_denetimi_yok`)."""
    duz = _sentetik_kayit(tmp_path, sentetik, referans=False)
    R2, t2 = sh.poz((47.5, 195.0, -122.5))
    res, _ = _petri(duz, tmp_path).process_image(sh.ciz(R2, t2, sentetik["K"], sentetik["D"], plaka=(60.0, 20.0)))
    assert res.kalibrasyon["olcum"]["kuyu_araligi"]["gecti"] is True
    assert any(str(u).startswith("sahne_denetimi_yok") for u in res.warnings), res.warnings


@pytest.mark.parametrize("bozma", ["json", "butunluk", "referans_silindi"])
def test_KRITIK_kalibrasyon_BOZUK_konum_YOK_ArUco_ya_dusmez(sentetik, tmp_path, monkeypatch, bozma):
    sd = _sd()
    _sentetik_kayit(tmp_path, sentetik)
    yol = sd.klasor(tmp_path) / sd.DOSYA_ADI
    if bozma == "json":
        yol.write_text("{bozuk", encoding="utf-8")
    elif bozma == "butunluk":
        d = json.loads(yol.read_text(encoding="utf-8"))
        d["t_mm"][0] += 20.0  # elle "düzeltme" → bütünlük tutmaz
        yol.write_text(json.dumps(d), encoding="utf-8")
    else:
        (sd.klasor(tmp_path) / sd.REFERANS_ADI).unlink()
    duz = sd.yukle(tmp_path)
    assert duz[0] is None and duz[1], duz
    _aruco_yasak(monkeypatch)
    kare = sh.ciz(sentetik["R"], sentetik["t"], sentetik["K"], sentetik["D"], plaka=(60.0, 20.0))
    res, _ = _petri(duz, tmp_path).process_image(kare)
    assert (
        res.method == "sabit_duzlem"
        and res.pemf_valid is False
        and res.kalibrasyon["engeller"] == ["kalibrasyon_bozuk"]
    )
    assert all(w.centroid_cabin_mm is None for w in res.wells)


@pytest.mark.parametrize("fark", ["cozunurluk", "kamera_indeksi", "ic_parametre"])
def test_KRITIK_kamera_ya_da_cozunurluk_FARKLI_konum_YOK(sentetik, tmp_path, fark):
    import cv2

    sd = _sd()
    if fark == "ic_parametre":
        kal = _kal(
            sentetik["r"],
            sentetik["K"],
            sentetik["D"],
            (sh.W, sh.H),
            duzlem_y=sentetik["r"]["duzlem_y_mm"],
            npz_sha="0" * 64,
        )
        duz = _kaydet(tmp_path, kal)
    else:
        duz = _sentetik_kayit(tmp_path, sentetik)
    kare = sh.ciz(sentetik["R"], sentetik["t"], sentetik["K"], sentetik["D"], plaka=(60.0, 20.0))
    if fark == "cozunurluk":
        kare = cv2.resize(kare, (1280, 720))
    res, _ = _petri(duz, tmp_path, kamera_indeksi=0 if fark == "kamera_indeksi" else 1).process_image(kare)
    assert res.pemf_valid is False and res.kalibrasyon["engeller"] == ["kalibrasyon_kamera_farkli"], res.kalibrasyon
    assert all(w.centroid_cabin_mm is None for w in res.wells)
    assert sd.kare_hazirla(duz, kare_boyutu=(sh.W, sh.H), kamera_indeksi=None).engeller == [] or fark == "ic_parametre"


def test_KARSIT_dosya_YOKSA_bugunku_ArUco_kipi(tmp_path, sentetik):
    sd = _sd()
    duz = sd.yukle(tmp_path)  # klasör yok
    assert duz == (None, None)
    kare = sh.ciz(sentetik["R"], sentetik["t"], sentetik["K"], sentetik["D"], plaka=(60.0, 20.0))
    res, _ = _petri(duz, tmp_path).process_image(kare)
    assert res.method != "sabit_duzlem" and res.kalibrasyon == {} and res.coord_frame != "cabin_plane", res.method


def test_kaydet_yukle_ATOMIK_ve_onbellek_DOSYA_degisince_tazelenir(sentetik, tmp_path):
    sd = _sd()
    duz = _sentetik_kayit(tmp_path, sentetik)
    assert duz[1] is None and duz[0]["referans"]["sahne_denetimi"] is True and "_referans_gri" in duz[0]
    assert "_referans_gri" not in json.loads((sd.klasor(tmp_path) / sd.DOSYA_ADI).read_text(encoding="utf-8"))
    assert not list(sd.klasor(tmp_path).glob("*.tmp")), "geçici dosya kaldı"
    kal = {k: v for k, v in duz[0].items() if not k.startswith("_")}
    kal["fantom"] = {"kalinlik_mm": 30.0, "tumor_derinligi_mm": 5.0}
    sd.kaydet(tmp_path, kal)
    assert sd.yukle(tmp_path)[0]["fantom"]["kalinlik_mm"] == 30.0, "önbellek eski dosyayı döndürdü"


# ═══ 3. Gerçek T2B kareleri (tezgâh 2026-10-23): sahne denetimi + boş kabinde fantom ═══════════════════════════════════════════════


def _t2b(ad):
    import cv2

    img = cv2.imdecode(np.fromfile(str(T2B / f"{ad}.jpg"), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert img is not None, ad
    return img


def _t2b_kalibrasyon(tmp_path, fantom=None):
    """T2B son_01: tabandaki ArUco'dan (şeritle ölçülen merkez (−8,25; −17,5; −0,75) cm, 10 cm kare, üst kenar arkaya) kabin duruşu."""
    import cv2

    K, D = sh.ic_parametre()
    kare = _t2b("son_01")
    det = cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50), cv2.aruco.DetectorParameters()
    )
    c, ids, _ = det.detectMarkers(kare)
    assert ids is not None and len(ids) == 1, "T2B karesinde işaret bulunamadı"
    m = np.array([-82.5, -175.0, -7.5])
    obj = np.array([m + [50, 0, 50], m + [-50, 0, 50], m + [-50, 0, -50], m + [50, 0, -50]], dtype=np.float64)
    ok, rv, tv = cv2.solvePnP(
        obj.reshape(-1, 1, 3), c[0].reshape(-1, 1, 2).astype(np.float64), K, D, flags=cv2.SOLVEPNP_IPPE
    )
    R, _ = cv2.Rodrigues(rv)
    kal = _kal((R, tv), K, D, (1920, 1080), duzlem_y=-175.0, fantom=fantom)
    und = _undistort(kare, K, D)
    hm = _sd().DuzlemHaritasi(kal)
    isaret = cv2.undistortPoints(c[0].reshape(-1, 1, 2).astype(np.float64), K, D, P=hm.K_yeni).reshape(-1, 2)
    return _kaydet(tmp_path, kal, und, [isaret])


def test_KRITIK_T2B_gercek_kare_sahne_AYNI_kamera_gecer_EGIM_degisince_kamera_oynamis(tmp_path):
    sd = _sd()
    duz = _t2b_kalibrasyon(tmp_path)
    kd_ayni = sd.kare_hazirla(duz, kare_boyutu=(1920, 1080), kamera_indeksi=1)
    K, D = sh.ic_parametre()
    sd.sahne_denetle(kd_ayni, _undistort(_t2b("son_02"), K, D))
    assert kd_ayni.engeller == [] and kd_ayni.olcum["sahne"]["kayma_px"] < 2.0, kd_ayni.olcum
    kd_egik = sd.kare_hazirla(duz, kare_boyutu=(1920, 1080), kamera_indeksi=1)
    sd.sahne_denetle(kd_egik, _undistort(_t2b("k2_01"), K, D))  # T2B: kamera eğimi 12,8° (k2) → 15,3° (son)
    assert [e.split(":")[0] for e in kd_egik.engeller] == ["kamera_oynamis"] and kd_egik.olcum["sahne"][
        "kayma_px"
    ] > 20.0


def test_KRITIK_T2B_BOS_kabin_fantomsuz_kare_SIFIR_fantom_hedefi(tmp_path):
    """T2B B1: fantomsuz kabinde v1 HSV yedeği kadrajın tamamını "fantom" sayıp 7–25 "sürülebilir" tümör veriyordu."""
    from ai_hub.cv_ortak import pemf_kapisi

    duz = _t2b_kalibrasyon(tmp_path, fantom={"kalinlik_mm": 30.0, "tumor_derinligi_mm": 5.0, "boy_mm": [104.1, 65.0]})
    res, _ = _fantom(duz).process_image(_t2b("son_02"))
    d = res.to_dict()
    assert res.n_tumor == 0 and res.tumor_regions == [] and res.success is False, (res.n_tumor, res.error)
    kod = str(res.error).split(":")[0]
    assert kod in ("fantom_degil", "fantom_boyu_farkli"), res.error
    kapi = pemf_kapisi.degerlendir(d, model="fantom", kosulsuz=True)
    assert kapi["surulebilir"] is False and kod in kapi["nedenler"] and "basarisiz" not in kapi["nedenler"], kapi


def test_KRITIK_fantom_KOYULUK_orani_gercek_fantomu_ISIK_yansimasindan_ayirir():
    """§1d: boy denetimi tek başına yetmedi (T2B `son_02` yansıması 86 × 71 mm — ayara %17 yakın). Tümör / gövde parlaklık oranı:
    hocanın 9 fantomu ≤ 0,71, T2B yansımaları ≥ 1,01 (ölçüldü) — test kendi eşiğini taşır."""
    import cv2

    from ai_hub.inference_em_fantom.phantom_cv_v3 import load_cabin_config
    from ai_hub.inference_em_fantom.phantom_cv_v3.tumor_detect import TumorDetectCfg, detect_phantom_tumors

    sd = _sd()
    v2 = load_cabin_config(None).phantom_v2
    cfg = TumorDetectCfg(
        navy_s_min=v2.navy_s_min, navy_v_min=v2.navy_v_min, navy_a_max=v2.navy_a_max, core_v_max=v2.core_v_max
    )

    def _oran(img):
        det = detect_phantom_tumors(img, cfg)
        assert det.success, det.error
        return sd.fantom_koyuluk_orani(img, det.phantom.mask, [t.mask for t in det.tumors])

    gercek = [
        _oran(cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR))
        for p in sorted(FANTOM_KAHIN.parent.glob("*.jpeg"))
    ]
    yansima = [_oran(_t2b(a)) for a in ("son_01", "son_02", "k2_01")]
    assert len(gercek) == 9 and all(o is not None and o <= 0.80 for o in gercek), gercek
    assert all(o is not None and o >= 0.95 for o in yansima), yansima
    assert max(gercek) < sd.FANTOM_KOYULUK_ORANI < min(yansima)


# ═══ 4. Fantom olumlu yol — hocanın kâhin fantomu + tepeden sentetik duruş ═══════════════════════════════════════════════════════════


def _fantom_kalibrasyonu(tmp_path, kalinlik_mm=30.0, derinlik_mm=5.0, *, referans=True):
    """Kâhin fotoğrafı (1200×1600) için tepeden bakan duruş: üst yüzeyde 0,315 mm/px (hocanın halka ölçeği ≈ 0,3147)."""
    import cv2

    img = cv2.imdecode(np.fromfile(str(FANTOM_KAHIN), dtype=np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    f = 1000.0
    K = np.array([[f, 0, w / 2.0], [0, f, h / 2.0], [0, 0, 1.0]])
    D = np.zeros(5)
    ust_y = -175.0 + kalinlik_mm
    C = np.array([0.0, ust_y + 315.0, 0.0])
    R = np.array([[-1.0, 0, 0], [0, 0, -1.0], [0, -1.0, 0]])  # görüntü sağı −X, aşağısı −Z (ön), bakış aşağı
    from ai_hub.inference_em_fantom.phantom_cv_v3 import load_cabin_config

    sha = _sd().npz_sha256(load_cabin_config(None).intrinsics_path())
    kal = _kal(
        (R, -R @ C),
        K,
        D,
        (w, h),
        duzlem_y=-155.0,
        npz_sha=sha,
        fantom={"kalinlik_mm": kalinlik_mm, "tumor_derinligi_mm": derinlik_mm, "boy_mm": [104.1, 65.0]},
    )
    return img, _kaydet(
        tmp_path, kal, img if referans else None, [np.array([[300, 500], [900, 500], [900, 1150], [300, 1150]])]
    )


def test_KRITIK_fantom_SABIT_DUZLEM_hedef_Y_ust_yuzey_eksi_DERINLIK_ve_surulebilir(tmp_path, monkeypatch):
    from ai_hub.cv_ortak import pemf_kapisi

    _aruco_yasak(monkeypatch)
    img, duz = _fantom_kalibrasyonu(tmp_path)
    res, _ = _fantom(duz).process_image(img)
    assert res.success and res.method == "sabit_duzlem" and res.pemf_valid is True, (res.error, res.warnings)
    assert res.n_tumor >= 3 and all(r.centroid_cabin_mm is not None for r in res.tumor_regions)
    assert all(r.centroid_cabin_mm[1] == -175.0 + 30.0 - 5.0 for r in res.tumor_regions), (
        "hedef Y = taban + kalınlık − derinlik değil"
    )
    boy = res.kalibrasyon["olcum"]["fantom_boyu"]
    assert boy["sapma"] <= 0.20, boy
    kapi = pemf_kapisi.degerlendir(res.to_dict(), model="fantom")
    assert "kalibrasyon" in pemf_kapisi.yanit_alanlari(res.to_dict(), model="fantom")
    assert not any(k in kapi["nedenler"] for k in pemf_kapisi.FIZIKSEL), kapi


def test_KRITIK_fantom_AYARI_yoksa_ve_KALINLIK_yanlissa_hedef_YOK(tmp_path):
    sd = _sd()
    img, duz = _fantom_kalibrasyonu(tmp_path)
    kal = {k: v for k, v in duz[0].items() if not k.startswith("_")}
    kal.pop("fantom")
    sd.kaydet(tmp_path, kal)
    res, _ = _fantom(sd.yukle(tmp_path)).process_image(img)
    assert res.pemf_valid is False and "fantom_ayari_yok" in res.kalibrasyon["engeller"]
    assert all(r.centroid_cabin_mm is None for r in res.tumor_regions)
    # Kalınlık 15 cm yazılmış: üst yüzey kameraya çok yakın sanılır → bulunan boy küçülür → hedef YOK
    img2, duz2 = _fantom_kalibrasyonu(tmp_path / "b", kalinlik_mm=30.0)
    kal2 = {k: v for k, v in duz2[0].items() if not k.startswith("_")}
    kal2["fantom"] = dict(kal2["fantom"], kalinlik_mm=150.0, tumor_derinligi_mm=5.0)
    sd.kaydet(tmp_path / "b", kal2)
    res2, _ = _fantom(sd.yukle(tmp_path / "b")).process_image(img2)
    assert res2.n_tumor == 0 and str(res2.error).startswith("fantom_boyu_farkli"), (res2.n_tumor, res2.error)


def test_KRITIK_fantomda_SAHNE_olculemezse_kamera_DOGRULANAMAZ_hedef_yok(tmp_path):
    img, duz = _fantom_kalibrasyonu(tmp_path, referans=False)
    res, _ = _fantom(duz).process_image(img)
    assert res.pemf_valid is False and "kamera_oynamis" in res.kalibrasyon["engeller"], res.kalibrasyon


# ═══ 5. PEMF kapısı — fiziksel kodlar ═════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "kod", ["kalibrasyon_bozuk", "kalibrasyon_kamera_farkli", "kamera_oynamis", "fantom_ayari_yok"]
)
@pytest.mark.parametrize("model", ["petri", "fantom"])
def test_KRITIK_FIZIKSEL_kod_KOSULSUZDA_da_keser_ve_EYLEM_soyler(kod, model):
    from ai_hub.cv_ortak import pemf_kapisi

    sonuc = {"success": True, "pemf_valid": False, "reliable": True, "warnings": [f"{kod}: ayrinti"]}
    for kosulsuz in (False, True):
        k = pemf_kapisi.degerlendir(sonuc, model=model, kosulsuz=kosulsuz)
        assert k["surulebilir"] is False and kod in k["nedenler"] and kod not in k["atlanan"], k
        assert "pemf_gecersiz" not in k["nedenler"]
        assert k["mesajlar"][[m["kod"] for m in k["mesajlar"]].index(kod)]["metin"].strip()


def test_KARSIT_FIZIKSEL_kod_YOKKEN_genel_pemf_gecersiz_aynen():
    from ai_hub.cv_ortak import pemf_kapisi

    k = pemf_kapisi.degerlendir({"success": True, "pemf_valid": False, "warnings": []}, model="petri")
    assert k["nedenler"] == ["pemf_gecersiz"], k


# ═══ 5. KD-2 sahip kararları: kalibre etmeden devam · numune tabanı · kör bölge · kamera kimliği ═══════════════════════════════════


def test_KRITIK_kalibre_etmeden_DEVAM_kaydi_KALICI_uyari_ve_tolerans_yuzde_10(sentetik, tmp_path):
    sd = _sd()
    duz = _sentetik_kayit(tmp_path, sentetik)
    kd = sd.kare_hazirla(duz, kare_boyutu=(sh.W, sh.H), kamera_indeksi=1)
    assert kd.eski is False and kd.kuyu_araligi_toleransi == 0.03 and not kd.uyarilar
    import cv2

    und = _undistort(sentetik["kare1"], sentetik["K"], sentetik["D"])
    maske = sd.cokgen_maskesi((sh.W, sh.H), [], genislet_px=0)
    kal = sd.sahne_yenile(
        tmp_path, und, maske, {"tarih": "2026-11-10T22:00:00+0300", "kayma_px": 30.0, "kuyu_sapma": 0.04}
    )
    assert kal is not None and kal["sahne_yenileme"]["kayma_px"] == 30.0
    kd = sd.kare_hazirla(sd.yukle(tmp_path), kare_boyutu=(sh.W, sh.H), kamera_indeksi=1)
    assert kd.eski is True and kd.kuyu_araligi_toleransi == 0.10 and kd.gecerli
    assert any(u.startswith("kalibrasyon_eski") for u in kd.uyarilar), kd.uyarilar
    assert kd.ozet()["eski"] is True
    _ = cv2


def test_KRITIK_numune_TABANI_yukseltmesi_petri_konum_ve_HEDEF_Y_yukari(sentetik, tmp_path):
    """Sahip (KD-1): plaka 5 cm altlık üstünde. Ayar doğruysa kuyular ≤ 2 mm ve hedef Y +50 mm; ayar YOKSA kuyu aralığı tutmaz
    (kamera_oynamis — metin "ya da taban yüksekliği ayarı yanlış" der) ve konum ÜRETİLMEZ."""
    sd = _sd()
    kare = sh.ciz(sentetik["R"], sentetik["t"], sentetik["K"], sentetik["D"], plaka=BASKA, yukseltme=50.0)
    gercek = sh.kuyu_merkezleri(*BASKA, yukseltme=50.0)
    duz = _sentetik_kayit(tmp_path / "ayarli", sentetik, ek={"numune_tabani": {"yukseltme_mm": 50.0}})
    res, _ = _petri(duz, tmp_path).process_image(kare)
    assert res.pemf_valid is True and res.kalibrasyon["engeller"] == [], res.kalibrasyon
    hata = [
        math.hypot(w.centroid_cabin_mm[0] - gercek[w.well_id][0], w.centroid_cabin_mm[2] - gercek[w.well_id][2])
        for w in res.wells
    ]
    assert len(hata) == 24 and max(hata) <= 2.0, max(hata)
    assert all(w.centroid_cabin_mm[1] == PETRI_HEDEF_Y + 50.0 for w in res.wells)
    duz0 = _sentetik_kayit(tmp_path / "ayarsiz", sentetik)
    res0, _ = _petri(duz0, tmp_path).process_image(kare)
    assert res0.pemf_valid is False and "kamera_oynamis" in res0.kalibrasyon["engeller"], res0.kalibrasyon
    assert all(w.centroid_cabin_mm is None for w in res0.wells)
    assert sd.taban_yukseltmesi_mm({"numune_tabani": {"yukseltme_mm": 250.0}}) == 0.0  # sınır dışı değer YOK sayılır


@pytest.mark.parametrize(
    "dortgen, yon",
    [
        ([[600, 700], [1300, 700], [1300, 1079], [600, 1079]], "on"),
        ([[600, 0], [1300, 0], [1300, 400], [600, 400]], "arka"),
        ([[0, 300], [700, 300], [700, 700], [0, 700]], "sol"),
        ([[1300, 300], [1919, 300], [1919, 700], [1300, 700]], "sag"),
    ],
)
def test_KRITIK_KOR_BOLGE_plaka_kare_kenarina_degerse_ENGEL_ve_YON(sentetik, tmp_path, dortgen, yon):
    """Sahip (KD-1): numune kısmen kör bölgede → hedef YOK + hangi yöne kaydırılacağı (kod `kor_bolge_<yön>`, PEMF kapısı FİZİKSEL)."""
    from types import SimpleNamespace

    from ai_hub.cv_ortak import pemf_kapisi

    sd = _sd()
    duz = _sentetik_kayit(tmp_path, sentetik)
    kd = sd.kare_hazirla(duz, kare_boyutu=(sh.W, sh.H), kamera_indeksi=1)
    und = _undistort(sentetik["kare1"], sentetik["K"], sentetik["D"])
    grid = SimpleNamespace(plate_quad_px=dortgen, spec=None, H_ransac=None)
    _petri(duz, tmp_path)._duzlem_denetle(kd, und, grid, [], 1.0)
    kodlar = [e.split(":", 1)[0] for e in kd.engeller]
    assert kodlar.count(f"kor_bolge_{yon}") == 1 and not kd.gecerli, kd.engeller
    assert f"kor_bolge_{yon}" in pemf_kapisi.FIZIKSEL and f"kor_bolge_{yon}" in sd.ENGEL_KODLARI


def test_KARSIT_KOR_BOLGE_kadraj_icindeki_plakada_YOK(sentetik, tmp_path):
    from types import SimpleNamespace

    sd = _sd()
    duz = _sentetik_kayit(tmp_path, sentetik)
    kd = sd.kare_hazirla(duz, kare_boyutu=(sh.W, sh.H), kamera_indeksi=1)
    und = _undistort(sentetik["kare1"], sentetik["K"], sentetik["D"])
    grid = SimpleNamespace(plate_quad_px=[[600, 300], [1300, 300], [1300, 700], [600, 700]], spec=None, H_ransac=None)
    _petri(duz, tmp_path)._duzlem_denetle(kd, und, grid, [], 1.0)
    assert not any(e.startswith("kor_bolge") for e in kd.engeller), kd.engeller


@pytest.mark.parametrize(
    "secili, beklenen",
    [
        (
            {"ad": "FHD Camera", "vidpid": "VID_1BCF&PID_28C4", "aygit_yolu": "baska-giris"},
            [],
        ),  # aynı kamera başka USB girişinde
        ({"ad": "HP True Vision FHD Camera", "vidpid": "VID_30C9&PID_0069"}, ["kalibrasyon_kamera_farkli"]),
        ({"ad": "FHD Camera", "vidpid": "VID_046D&PID_0825"}, ["kalibrasyon_kamera_farkli"]),
    ],
)
def test_KRITIK_KAMERA_KIMLIGI_ad_VIDPID_karsilastirilir_INDEKS_degil(sentetik, tmp_path, secili, beklenen):
    """KD-2 (sahip): MSMF sırası değişebilir (KD-1: Pusat 1 → 0) — kimlik biliniyorsa indeks farkı ENGEL DEĞİL; ad / VID/PID farkı ENGEL."""
    sd = _sd()
    kimlik = {"ad": "FHD Camera", "vidpid": "VID_1BCF&PID_28C4", "aygit_yolu": r"\\?\usb#vid_1bcf&pid_28c4&mi_00#7&1"}
    kal = _kal(sentetik["r"], sentetik["K"], sentetik["D"], (sh.W, sh.H), duzlem_y=sentetik["r"]["duzlem_y_mm"])
    kal["kamera"]["kimlik"] = kimlik
    duz = _kaydet(tmp_path, kal)
    kd = sd.kare_hazirla(duz, kare_boyutu=(sh.W, sh.H), kamera_indeksi=0, kamera_kimligi=secili)
    assert [e.split(":", 1)[0] for e in kd.engeller] == beklenen, kd.engeller


def test_komsu_kuyu_araligi_yonelimden_bagimsiz_19_3(sentetik):
    sd = _sd()
    r = sentetik["r"]
    hm = sd.DuzlemHaritasi(_kal(r, sentetik["K"], sentetik["D"], (sh.W, sh.H), duzlem_y=r["duzlem_y_mm"]))
    k = sh.konum(sentetik["R"], sentetik["t"], sentetik["K"], sentetik["D"], *BASKA)
    ka = sd.komsu_kuyu_araligi(hm, k, ARALIK, hm.numune_y_mm, sd.KUYU_ARALIGI_TOLERANSI)
    assert ka["gecti"] and abs(ka["sutun_mm"] - ARALIK) < 0.1, ka
    k90 = dict(k, kuyu_plaka_mm=k["kuyu_plaka_mm"][:, ::-1])  # dikey plaka (eksenler yer değiştirmiş) — aynı komşuluk
    assert sd.komsu_kuyu_araligi(hm, k90, ARALIK, hm.numune_y_mm, 0.03)["gecti"]


def test_KRITIK_A1_kosesi_KALIBRASYONDAN_kamera_TERS_takili_kuyu_kimlikleri_DOGRU(tmp_path):
    """KD-2: kamera 180° ters takılı (görüntünün üstü ÖN cam). A1 plakanın arka-solunda (kılavuz). Sabit "tl" varsayımı kuyu
    kimliklerini aynalardı (A1 ↔ D6, ~11 cm); kalibrasyondan A1 köşesi "br" → her kuyu kendi fiziksel konumunda (≤ 2 mm)."""
    sd = _sd()
    K, D = sh.ic_parametre()
    kamera = (27.5, 195.0, 122.5)
    R, t = sh.poz(kamera, sapma_deg=180.0)
    konumlar = [sh.konum(R, t, K, D, *SOL_KONUM), sh.konum(R, t, K, D, *SAG_KONUM)]
    r = sd.kalibrasyon_coz(
        konumlar=konumlar, K=K, D=D, boyut=(sh.W, sh.H), ext_cm=sh.EXT_CM, lens_cm=sh.lens_cm(kamera)
    )
    assert r["gecerli"] is True, r
    kal = _kal(r, K, D, (sh.W, sh.H), duzlem_y=r["duzlem_y_mm"])
    assert sd.a1_kosesi(sd.DuzlemHaritasi(kal), r["duzlem_y_mm"]) == "br"
    duz = _kaydet(tmp_path, kal)
    res, _ = _petri(duz, tmp_path).process_image(sh.ciz(R, t, K, D, plaka=BASKA))
    gercek = sh.kuyu_merkezleri(*BASKA)
    assert res.pemf_valid is True and len(res.wells) == 24, (res.warnings, res.kalibrasyon)
    hata = {
        w.well_id: math.hypot(
            w.centroid_cabin_mm[0] - gercek[w.well_id][0], w.centroid_cabin_mm[2] - gercek[w.well_id][2]
        )
        for w in res.wells
    }
    assert max(hata.values()) <= 2.0, sorted(hata.items(), key=lambda a: -a[1])[:3]
