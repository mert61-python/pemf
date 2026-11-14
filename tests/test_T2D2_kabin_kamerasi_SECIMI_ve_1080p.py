# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""T2D-2 (Tezgâh-2 #3) — kabin kamerası SEÇİLİR, çözünürlük ilk okumadan ÖNCE istenir, kalibrasyon kenar oranı farklı karede REDDEDİLİR.

ÖLÇÜLEN KUSUR (Tezgâh-2, 2026-10-23): `ai_router.py` hazırlık önizlemesi ve AI Pro döngüsü sabit `cv2.VideoCapture(0)` açıyordu →
dahili kameralı dizüstünde kabin kamerası (Pusat "FHD Camera", OpenCV indeks 1) DEĞİL dahili kamera (indeks 0) açıldı; çözünürlük
istenmediği için kare 640×480 geldi. `olcekli_intrinsics` 1080p kalibrasyonunu 640×480 kareye fx / fy AYRI ölçekleyip yanlış K
veriyordu (görüş alanları farklı). Kedi hattı göreli `intrinsics_npz`'yi YAML DOSYA yoluna ekliyor (hiç bulunmuyordu) ve K'yı
kare boyutuna ölçeklemiyordu.
SÖZLEŞME:
  * seçim cihaz düzeyinde (`<veri kökü>/kabin_kamerasi.json`; Ayarlar ▸ Kabin kamerası); seçim yoksa kamera AÇILMAZ ve eylem
    söyleyen 409 / hazırlık hatası (dahili kameraya sessiz düşüş YOK);
  * açılışta çözünürlük isteği İLK `read()`'den ÖNCE (MSMF akış başladıktan sonra çözünürlük değişimi hata verir) — KD madde 0 (b,
    2026-11-10): sabit 1920×1080 DEĞİL; kalibrasyon yoksa `set(W, 9999)` + `set(H, 9999)` = kameranın EN YÜKSEK kendi modu (sürücü
    desteklediğine indirir; ölçülen Pusat / HP: 1920×1080), sabit düzlem kalibrasyonu varsa onun boyutu (`test_KD_*`);
  * kenar oranı farklı karede K ölçeklemesi REDDİ → yaklaşık K;
  * 1080p kalibrasyonu `ai_hub/cv_ortak/kalibrasyon/` altında; üç YAML aynı dizgeyle ona çözülür;
  * taban işareti (normal "+Y", `up_cabin [0,0,1]`, `qr_to_origin_cm`, `hedef_duzlem_eksen "Y"`) uçtan uca doğru konum verir.
Sahte kamera EN ALT katta (`cv2.VideoCapture` yerine) — gerçek kamera AÇILMAZ.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace

import capraz
import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]
KALIBRASYON = KOK / "ai_hub" / "cv_ortak" / "kalibrasyon" / "pusat_fhd_1920x1080_M2.npz"
YAML_DIZGESI = "cv_ortak/kalibrasyon/pusat_fhd_1920x1080_M2.npz"
PETRI_YAML = KOK / "ai_hub" / "inference_petri_dish" / "petri_cv_v2" / "cabin_config_v2.yaml"
FANTOM_YAML = KOK / "ai_hub" / "inference_em_fantom" / "phantom_cv_v3" / "cabin_config_v3.yaml"
KEDI_YAML = KOK / "ai_hub" / "inference_cat_organ" / "cabin_config_example.yaml"


class _SahteCv2:
    """En alt kat: `VideoCapture(i)` çağrılarını ve kamera üzerindeki çağrı SIRASINI kaydeder. MSMF gibi: ilk `read()`'den SONRA
    çözünürlük değişimi hata verir. `acik` = açılabilen indeksler.
    KD madde 0 (ölçülen sürücü davranışı, Pusat + dahili HP): istemeden kare 640×480; istenen boyut desteklenen modlardan İSTEĞİ AŞMAYAN
    en büyüğüne iner (9999×9999 → 1920×1080; yükseltme YOK)."""

    MODLAR = ((640, 480), (1280, 720), (1920, 1080))

    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    IMWRITE_JPEG_QUALITY = 1

    def __init__(self, acik=(0, 1)):
        self.acik = set(acik)
        self.acilan: list[int] = []
        self.capler: list = []

    def VideoCapture(self, i):  # noqa: N802 — cv2 API adı
        self.acilan.append(i)
        cv = self

        class _Cap:
            def __init__(self):
                self.indeks, self.sira, self.okundu = i, [], False
                self.boyut = [640, 480]
                self.istek = [10**6, 10**6]  # yalnız bir eksen istenirse diğeri sınırlamaz

            def isOpened(self):  # noqa: N802
                return i in cv.acik

            def set(self, prop, deger):
                if self.okundu:
                    raise RuntimeError("(-215) _step >= minstep — akış başladıktan sonra çözünürlük değişimi")
                self.sira.append(("set", prop, deger))
                self.istek[0 if prop == 3 else 1] = int(deger)
                uygun = [m for m in cv.MODLAR if m[0] <= self.istek[0] and m[1] <= self.istek[1]]
                self.boyut = list(max(uygun) if uygun else cv.MODLAR[0])
                return True

            def get(self, prop):
                return float(self.boyut[0 if prop == 3 else 1])

            def read(self):
                self.okundu = True
                self.sira.append(("read",))
                return True, np.zeros((self.boyut[1], self.boyut[0], 3), dtype=np.uint8)

            def release(self):
                self.sira.append(("release",))

        c = _Cap()
        self.capler.append(c)
        return c

    @staticmethod
    def resize(kare, boyut):
        return np.zeros((boyut[1], boyut[0], 3), dtype=np.uint8)

    @staticmethod
    def imencode(_uz, _kare, _p=None):
        return True, np.frombuffer(b"\xff\xd8sahte", dtype=np.uint8)


@pytest.fixture
def veri(monkeypatch, tmp_path):
    """Seçim yok (conftest'in süit çapı `PEMF_KABIN_KAMERASI=0` değişkeni SİLİNİR), veri kökü testin geçici dizini."""
    from utils import kabin_kamerasi as kk

    monkeypatch.delenv("PEMF_KABIN_KAMERASI", raising=False)
    monkeypatch.setattr(kk, "_veri_koku", lambda: tmp_path)
    return kk, tmp_path


# ── seçim + açılış ───────────────────────────────────────────────────────────────────────────────────────────────────────


def test_KRITIK_secim_YOKSA_kamera_ACILMAZ_dahiliye_dusmez(veri):
    kk, _ = veri
    cv = _SahteCv2()
    with pytest.raises(kk.KameraSecilmedi):
        kk.kamera_ac(cv)
    assert cv.acilan == [], f"seçim yokken kamera açıldı (dahili kameraya sessiz düşüş): {cv.acilan}"


def test_KRITIK_secilen_indeks_acilir_ve_EN_YUKSEK_mod_ILK_okumadan_ONCE_istenir(veri):
    """KD madde 0 (b): kalibrasyon YOKKEN sabit 1920×1080 değil, kameranın en yüksek kendi modu (büyük istek, gelen boyut)."""
    kk, kok = veri
    assert kk.kamera_sec(1) == {"indeks": 1, "kaynak": "ayar"}
    assert json.loads((kok / kk.KAMERA_DOSYASI).read_text(encoding="utf-8")) == {"indeks": 1}
    cv = _SahteCv2()
    cap, indeks = kk.kamera_ac(cv)
    assert (indeks, cv.acilan) == (1, [1]), cv.acilan
    ok, kare = cap.read()
    assert cap.sira[:3] == [("set", 3, 9999.0), ("set", 4, 9999.0), ("read",)], cap.sira
    assert kare.shape[:2] == (1080, 1920), "sürücünün en yüksek modu gelmeli"


def test_KARSIT_ortam_degiskeni_ayarin_ONUNDE(veri, monkeypatch):
    kk, _ = veri
    kk.kamera_sec(2)
    monkeypatch.setenv("PEMF_KABIN_KAMERASI", "1")
    assert kk.secili_kamera() == {"indeks": 1, "kaynak": "ortam"}
    monkeypatch.setenv("PEMF_KABIN_KAMERASI", "bozuk")
    assert kk.secili_kamera() == {"indeks": 2, "kaynak": "ayar"}


@pytest.mark.parametrize("deger", [-1, 64, True, "1", 1.0])
def test_KRITIK_gecersiz_secim_REDDEDILIR(veri, deger):
    kk, kok = veri
    with pytest.raises(ValueError):
        kk.kamera_sec(deger)
    assert not (kok / kk.KAMERA_DOSYASI).exists()


def test_bozuk_secim_dosyasi_SECILMEDI_sayilir(veri):
    kk, kok = veri
    (kok / kk.KAMERA_DOSYASI).write_text("{bozuk", encoding="utf-8")
    assert kk.secili_kamera() is None


def test_tarama_acilanlari_listeler_onizlemeli_ve_EN_YUKSEK_mod_okumadan_ONCE(veri):
    kk, _ = veri
    cv = _SahteCv2(acik=(0, 2))
    liste = kk.kameralari_tara(cv, sayi=4)
    assert [o["indeks"] for o in liste] == [0, 2]
    assert all(o["genislik"] == 1920 and o["yukseklik"] == 1080 and o["onizleme"] for o in liste), liste
    for c in cv.capler:
        assert c.sira[-1] == ("release",), "tarama kamerayı bırakmadı"
        if c.isOpened():
            assert c.sira.index(("read",)) > c.sira.index(("set", 4, 9999.0)), c.sira


# ── ayar uçları ──────────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def ayar_istemcisi(veri):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from servers import settings_router as sr

    app = FastAPI()
    app.include_router(sr.router)
    return TestClient(app), veri[0], sr


def test_uc_secim_yok_null_sonra_POST_ile_hatirlanir(ayar_istemcisi):
    ist, kk, _sr = ayar_istemcisi
    # KD madde 0 (b): kalibrasyon yok → `null` (kameranın en yüksek kendi modu).
    # AP-23: yalnız-ek `bagli` / `guncelIndeks` (seçim yokken None — bilinmiyor; kart "seçilmedi" satırını gösterir)
    assert ist.get("/api/settings/kabin-kamerasi").json() == {
        "secili": None,
        "istenenCozunurluk": None,
        "bagli": None,
        "guncelIndeks": None,
    }
    r = ist.post("/api/settings/kabin-kamerasi", json={"indeks": 1})
    assert r.status_code == 200 and r.json()["secili"]["indeks"] == 1
    assert ist.get("/api/settings/kabin-kamerasi").json()["secili"] == {"indeks": 1, "kaynak": "ayar"}
    assert ist.post("/api/settings/kabin-kamerasi", json={"indeks": 99}).status_code == 400


def test_uc_tarama_AI_kamerayi_tutarken_409_eylem_metni(ayar_istemcisi, monkeypatch):
    import i18n_yardimci as iy

    ist, kk, sr = ayar_istemcisi
    monkeypatch.setattr(sr, "_ai_kamerasi_mesgul", lambda: True)
    monkeypatch.setattr(
        kk, "kameralari_tara", lambda *a, **k: pytest.fail("AI Pro kamerayı tutarken tarama kamera AÇTI")
    )
    r = ist.post("/api/settings/kabin-kamerasi/tara")
    assert (
        r.status_code == 409 and r.json()["detail"] == iy.katalog("sunucu", "tr")["ayarlar.kabinKamerasi.taramaMesgul"]
    )


# ── ai_router: hazırlık + AI Pro ─────────────────────────────────────────────────────────────────────────────────────────


def test_KRITIK_ai_router_SABIT_VideoCapture_0_KALMADI():
    kaynak = (KOK / "apps" / "backend" / "servers" / "ai_router.py").read_text(encoding="utf-8")
    kod = "\n".join(s.split("#", 1)[0] for s in kaynak.splitlines())  # yorum satırları dışında
    assert "VideoCapture(" not in kod, "ai_router kamerayı kabin_kamerasi.kamera_ac dışında açıyor"
    assert kaynak.count("kabin_kamerasi.kamera_ac(cv2)") >= 3, "hazırlık + AI Pro döngüsü seçili kamerayı açmıyor"


@pytest.fixture
def hazirlik(veri, monkeypatch):
    import servers.ai_router as air

    cv = _SahteCv2()
    monkeypatch.setattr(air.cv2, "VideoCapture", cv.VideoCapture)
    sag = SimpleNamespace(ad="sahte", yukle=lambda: None)
    monkeypatch.setattr(air, "_aktif_saglayici", lambda: sag)
    onceki = (
        air._ai_hazirlik_active,
        air._ai_hazirlik_hata,
        air._ai_hazirlik_hata_kodu,
        air._ai_hazirlik_hata_saglayici,
    )
    yield air, cv, veri[0]
    air._ai_hazirlik_active, air._ai_hazirlik_hata, air._ai_hazirlik_hata_kodu, air._ai_hazirlik_hata_saglayici = onceki


def test_KRITIK_hazirlik_dongusu_secim_YOKSA_kamera_acmaz_EYLEM_hatasi(hazirlik):
    import i18n_yardimci as iy

    air, cv, _kk = hazirlik
    air._ai_hazirlik_active = True
    air._ai_hazirlik_loop()
    assert cv.acilan == [], cv.acilan
    assert air._ai_hazirlik_hata_kodu == "kamera_secilmedi" and air._ai_hazirlik_active is False
    assert air._ai_hazirlik_hata == iy.katalog("sunucu", "tr")["ai.pro.hazirlik.kameraSecilmedi"]
    assert (
        air._hazirlik_hata_metni("kamera_secilmedi", "", "en")
        == iy.katalog("sunucu", "en")["ai.pro.hazirlik.kameraSecilmedi"]
    )


def test_KRITIK_hazirlik_dongusu_SECILI_kamerayi_EN_YUKSEK_mod_ile_acar(hazirlik, monkeypatch):
    air, cv, kk = hazirlik
    kk.kamera_sec(1)
    monkeypatch.setattr(air, "_AI_HAZIRLIK_TAVAN_S", 0.0)  # ilk turda tavan → döngü çıkar, kamera bırakılır
    air._ai_hazirlik_started_at = time.monotonic() - 1.0
    air._ai_hazirlik_active = True
    air._ai_hazirlik_loop()
    assert cv.acilan == [1], cv.acilan
    assert cv.capler[0].sira[:2] == [("set", 3, 9999.0), ("set", 4, 9999.0)], cv.capler[0].sira
    assert cv.capler[0].sira[-1] == ("release",)


@pytest.mark.parametrize("uc", ["/api/ai/pro/hazirlik/baslat", "/api/ai/pro/start"])
def test_KRITIK_uclar_secim_YOKSA_409_eylem_metni_ve_onay_TUKETILMEZ(veri, monkeypatch, uc):
    import i18n_yardimci as iy
    import servers.ai_router as air
    import servers.api_server as apis
    from fastapi.testclient import TestClient
    from servers import ai_approval

    monkeypatch.setattr(air, "_ai_kare_yabanci", lambda *_a, **_k: False)
    monkeypatch.setattr(
        ai_approval, "dogrula", lambda *_a, **_k: pytest.fail("kamera seçilmeden onay doğrulandı / tüketildi")
    )
    onceki = (air._ai_hazirlik_active, air._ai_loop_active, air._ai_hazirlik_thread, air._ai_thread)
    r = TestClient(apis.app).post(uc, json={})
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == iy.katalog("sunucu", "tr")["ai.pro.hazirlik.kameraSecilmedi"], r.json()
    assert (air._ai_hazirlik_active, air._ai_loop_active, air._ai_hazirlik_thread, air._ai_thread) == onceki, (
        "döngü başladı"
    )


# ── K ölçeklemesi + kalibrasyon dosyası ──────────────────────────────────────────────────────────────────────────────────


def _intr_1080():
    from ai_hub.cv_ortak.coord_transform import CameraIntrinsics

    K = np.array([[1279.83, 0, 960.0], [0, 1279.83, 540.0], [0, 0, 1.0]])
    return CameraIntrinsics(K=K, D=np.zeros(5), image_size=(1920, 1080), rms=0.885)


def test_KRITIK_olcekli_intrinsics_KENAR_ORANI_farkliysa_REDDEDER():
    from ai_hub.cv_ortak.coord_transform import olcekli_intrinsics

    assert olcekli_intrinsics(_intr_1080(), 640, 480) is None, (
        "16:9 kalibrasyonu 4:3 kareye ölçeklendi (anizotrop yanlış K)"
    )
    k720 = olcekli_intrinsics(_intr_1080(), 1280, 720)
    assert k720 is not None and k720.image_size == (1280, 720)
    assert np.allclose(
        [k720.K[0, 0], k720.K[1, 1], k720.K[0, 2], k720.K[1, 2]], [853.22, 853.22, 640.0, 360.0], atol=0.01
    )
    assert olcekli_intrinsics(_intr_1080(), 1920, 1080) is not None


def test_KRITIK_fantom_hatti_red_sonrasi_YAKLASIK_K_ya_duser(monkeypatch):
    import ai_hub.inference_em_fantom.phantom_cv_v3.pipeline as fp

    yaklasik = object()
    monkeypatch.setattr(fp, "approx_intrinsics_from_marker", lambda *_a, **_k: yaklasik)
    hat = SimpleNamespace(intrinsics=_intr_1080(), cfg=None, _approx_intrinsics=False)
    fp.PhantomCvPipeline._ensure_intrinsics(hat, np.zeros((480, 640, 3), dtype=np.uint8))
    assert hat.intrinsics is yaklasik and hat._approx_intrinsics is True


def test_KRITIK_petri_hatti_red_sonrasi_YAKLASIK_K_ya_duser(monkeypatch):
    import ai_hub.inference_petri_dish.petri_cv_v2.pipeline as pp

    yaklasik = object()
    monkeypatch.setattr(pp, "approx_intrinsics_from_marker", lambda *_a, **_k: yaklasik)
    hat = SimpleNamespace(intrinsics=_intr_1080(), cfg=None, _approx_intrinsics=False)
    hat._olcekli_intrinsics = lambda w, h: pp.PetriCvPipeline._olcekli_intrinsics(hat, w, h)
    assert pp.PetriCvPipeline._ensure_intrinsics(hat, np.zeros((480, 640, 3), dtype=np.uint8)) is True
    assert hat.intrinsics is yaklasik and hat._approx_intrinsics is True


def test_KRITIK_kalibrasyon_dosyasi_COMMITLI_ve_tezgah_olcumuyle_AYNI():
    assert KALIBRASYON.exists(), KALIBRASYON
    assert hashlib.sha256(KALIBRASYON.read_bytes()).hexdigest().startswith("b6c085a9"), "Tezgâh-2 M2 dosyası değil"
    d = np.load(str(KALIBRASYON), allow_pickle=False)
    assert tuple(int(v) for v in d["image_size"]) == (1920, 1080)
    assert abs(float(d["K"][0, 0]) - 1279.8) < 0.1


def test_KRITIK_uc_YAML_ayni_dizgeyle_kalibrasyona_COZULUR():
    yaml = capraz.paket_yoksa_atla("yaml")
    from ai_hub.cv_ortak.cabin_config import load_cabin_config
    from ai_hub.inference_cat_organ.lib.cabin_config import has_perspective_data
    from ai_hub.inference_cat_organ.lib.cabin_config import load_cabin_config as kedi_yukle
    from ai_hub.inference_cat_organ.lib.camera import load_intrinsics

    for p in (PETRI_YAML, FANTOM_YAML, KEDI_YAML):
        assert yaml.safe_load(p.read_text(encoding="utf-8"))["camera"]["intrinsics_npz"] == YAML_DIZGESI, p
    for p in (PETRI_YAML, FANTOM_YAML):
        assert load_cabin_config(p).intrinsics_path().resolve() == KALIBRASYON.resolve(), p
    kedi = kedi_yukle(str(KEDI_YAML))
    assert has_perspective_data(kedi)
    intr = load_intrinsics(kedi["camera"]["intrinsics_npz"], yaml_dir=kedi["_yaml_path"])
    assert intr is not None and intr["image_size"] == (1920, 1080), "kedi hattı göreli kalibrasyonu bulamadı"


def test_KRITIK_kedi_hatti_K_yi_kare_boyutuna_OLCEKLER_kenar_orani_farkliysa_REDDEDER():
    from ai_hub.inference_cat_organ.lib.camera import olcekli_ic_parametre

    intr = {"K": _intr_1080().K, "D": np.zeros(5), "image_size": (1920, 1080)}
    assert olcekli_ic_parametre(intr, (1080, 1920, 3)) is intr
    k720 = olcekli_ic_parametre(intr, (720, 1280, 3))
    assert k720 is not None and abs(k720["K"][0, 0] - 853.22) < 0.01 and k720["image_size"] == (1280, 720)
    assert olcekli_ic_parametre(intr, (480, 640, 3)) is None


# ── taban işareti (ölçüm: kod destekliyor mu) ───────────────────────────────────────────────────────────────────────────


def _taban_cfg(tmp_path):
    yaml = capraz.paket_yoksa_atla("yaml")
    from ai_hub.cv_ortak.cabin_config import load_cabin_config

    d = yaml.safe_load(PETRI_YAML.read_text(encoding="utf-8"))
    d["aruco"]["normal_axis_in_cabin"] = "+Y"  # işaret TABANDA, yüzü yukarı
    d["aruco"]["plane_offset_cm"] = 0.0
    d["camera"]["up_cabin"] = [0.0, 0.0, 1.0]  # işaretin ÜST kenarı arka duvara
    d["geometry"]["qr_to_origin_cm"] = [0.5, 17.0, 2.0]  # işaret merkezi (-0,5; -17; -2) cm
    d["phantom_plate"]["hedef_duzlem_eksen"] = "Y"
    d["phantom_plate"]["hedef_duzlem_cm"] = -16.0  # plaka yüzeyi tabandan 1 cm yukarıda
    p = tmp_path / "taban.yaml"
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return load_cabin_config(p)


def test_OLCUM_taban_isareti_uctan_uca_konum_DOGRU(tmp_path):
    """Tavandaki kamera (3,5; 15; −4) cm tabana bakar; işaretin 4 köşesi izdüşürülüp GERÇEK `solvePnP` ile poz çözülür; plaka
    düzlemindeki hedefin pikseli GERÇEK `pixel_to_cabin_mm` ile kabine döner → ≤ 1 mm. İşaret doğru yönde: `isaret_ters_mi` False."""
    import cv2

    from ai_hub.cv_ortak import coord_transform as ct

    cfg = _taban_cfg(tmp_path)
    intr = _intr_1080()
    R_axis = ct._marker_to_cabin_R(cfg)
    assert np.allclose(R_axis @ [0, 0, 1], [0, 1, 0]) and np.allclose(R_axis @ [0, 1, 0], [0, 0, 1])
    assert abs(np.linalg.det(R_axis) - 1.0) < 1e-9
    C = np.array([35.0, 150.0, -40.0])  # mm
    M = -cfg.geometry.qr_to_origin_mm
    z_c, y_c = np.array([0.0, -1.0, 0.0]), np.array([0.0, 0.0, -1.0])  # optik eksen aşağı; görüntü "aşağısı" = ön cam
    R_cc = np.vstack([np.cross(y_c, z_c), y_c, z_c])  # kabin → kamera
    R_cm, t = R_cc @ R_axis, R_cc @ (M - C)
    obj = ct._marker_object_points(cfg.aruco.real_mm)
    rvec0, _ = cv2.Rodrigues(R_cm)
    img, _ = cv2.projectPoints(obj, rvec0, t.reshape(3, 1), intr.K, intr.D)
    ok, rvec, tvec = cv2.solvePnP(obj, img.reshape(-1, 2), intr.K, intr.D, flags=cv2.SOLVEPNP_IPPE_SQUARE)
    assert ok
    R, _ = cv2.Rodrigues(rvec)
    poz = ct.CabinPose(marker_id=0, rvec=rvec, tvec=tvec, R=R, reproj_error_px=0.0, marker_pos_cabin_mm=M)
    assert not ct.isaret_ters_mi(poz, cfg), "doğru yerleştirilmiş taban işareti TERS sayıldı"
    for hedef in ([150.0, -160.0, 50.0], [-80.0, -160.0, -60.0], [212.0, -160.0, 153.0]):
        P = np.array(hedef)
        pc = R_cc @ (P - C)
        px = (intr.K @ (pc / pc[2]))[:2]
        sonuc = ct.pixel_to_cabin_mm((float(px[0]), float(px[1])), poz, intr, cfg)
        assert np.allclose(sonuc, P, atol=1.0), f"taban işaretiyle hedef {hedef} → {sonuc}"
