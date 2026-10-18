# -*- coding: utf-8 -*-
"""SG.G4 — TERMAL OLMAYAN GÖRÜNTÜYE GÜVENLE TEŞHİS (sahip gözlemi 2026-10-13, yanlış klinik sonuç).

Sahip: "termalin canlısında termal görüntü olmamasına rağmen böyle analiz yapıyor." AI Hub "Termal Görüntü Analizi" CANLI kipte
NORMAL web kamerasıyla (insan yüzü, oda) "Termal anormallik · %95 güven … Hasta (Riskli) (Doğruluk: %95.3)" gösterdi.
Kök neden [ÖLÇTÜM `ec5e967c`]: `utils/image_domain.EXPECTED` termali BİLEREK dışarıda bırakıyordu (IR kamera gri ya da renk paletli
çıktı verir) → termal uca giren HER görüntü softmax ile en yakın sınıfa güvenle teşhis alıyordu (2026-08-06 CT → "Grade 4 · %100"
vakasının AYNI sınıfı).
Düzeltme: `image_domain.termal_analiz` — renkli piksellerin TEK bir termal palete (inferno / magma / plasma / hot / jet / turbo /
rainbow / iron) oturma oranı + palet yayılımı (ölçülen dağılım ve eşikler modülün başında). KESİN uyumsuz → 422 + eylem; akromatik /
kararsız GEÇER ama yanıt `girdi_dogrulama` ile "doğrulanamadı" der; iç hata REDDEDER (A-24); `PEMF_AI_DOMAIN_GUARD=0` kaçış aynı.
Sahte YALNIZ en alt katta: tahminci (`_get_or_load_model("thermal")`) — görüntü çözme, kapı ve uç GERÇEK.
⚠️ Sahibin kamera karesi (yüzü var) DEPOYA GİRMEZ: kamera benzeri girdi aşağıda SENTETİK üretilir (sıcak oda ışığı, ten, perde,
beyaz giysi — kişisel veri yok); ayrıca depodaki kişisel olmayan kedi fotoğrafları.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]
SAGLIKLI = KOK / "tests" / "xai_veri" / "termal_saglikli_03a_224.png"
HASTA = KOK / "tests" / "xai_veri" / "termal_hasta_03b_224.png"
KEDI_FOTO = KOK / "ai_hub" / "cat_landmark" / "results" / "00000005_020.jpg"
KEDI_SEG = (
    KOK / "ai_hub" / "cat_segmentation" / "results" / "group0032_jpeg_jpg.rf.66f4458aa732ee0e274b7afd6a766b24.jpg"
)
UYUMSUZ_METNI = (
    "Bu görüntü termal kamera görüntüsüne benzemiyor (renk paleti / sıcaklık eşlemesi yok). Termal kameradan çekin ya da "
    "termal görüntü yükleyin."
)
INFERNO_YON_NOTU = "Paletin kamera yönünde olduğundan emin olun (soğuk = siyah / mor, sıcak = sarı) — ters palette sonuç tersine dönebilir."


def _oku(p: Path) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
    assert img is not None, p
    return img


def _jpg(img: np.ndarray, q: int = 85) -> bytes:
    ok, b = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    assert ok
    return b.tobytes()


def _kamera_benzeri_oda() -> np.ndarray:
    """Normal web kamerası karesine benzeyen SENTETİK oda (kişisel veri yok): bej duvar, pembe-kahve perde, beyaz giysi, ten
    rengi oval, koyu saç; sıcak ışık, gürültü, bulanıklık. G4 / G5 kamera karelerinin ölçülen renk istatistiğine yakın."""
    rng = np.random.default_rng(14)
    h, w = 360, 480
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (155, 170, 190)  # BGR bej duvar
    img[:, : w // 3] = (120, 128, 168)  # pembe-kahve perde
    img[int(h * 0.62) :, w // 4 : int(w * 0.8)] = (212, 218, 222)  # beyaz giysi
    cv2.ellipse(img, (w // 2, int(h * 0.38)), (70, 92), 0, 0, 360, (128, 158, 205), -1)  # ten
    cv2.ellipse(img, (w // 2, int(h * 0.22)), (74, 40), 0, 180, 360, (40, 45, 60), -1)  # saç
    img += rng.normal(0, 6, img.shape)
    img = cv2.GaussianBlur(np.clip(img, 0, 255).astype(np.uint8), (5, 5), 0)
    return img


def _arayuz_benzeri() -> np.ndarray:
    """Koyu lacivert arayüz ekran görüntüsüne benzer sentetik görüntü (paletin yalnız koyu ucuna oturur)."""
    img = np.zeros((300, 400, 3), np.uint8)
    img[:] = (52, 30, 28)  # BGR koyu lacivert
    img[40:120, 30:370] = (70, 44, 38)
    img[200:230, 60:300] = (230, 140, 60)  # mavi düğme
    return img


def _termal_skaler(img: np.ndarray) -> np.ndarray:
    lut = (
        cv2.applyColorMap(np.arange(256, dtype=np.uint8).reshape(-1, 1), cv2.COLORMAP_INFERNO)
        .reshape(256, 3)
        .astype(np.float32)
    )
    p = img.reshape(-1, 3).astype(np.float32)
    d = ((p[:, None, :] - lut[None]) ** 2).sum(-1)
    return np.argmin(d, 1).astype(np.uint8).reshape(img.shape[:2])


class _SahteTahminci:
    """EN ALT kat: termal modelin `predict`i. Kaç kez çağrıldığını ve ona verilen görüntüyü kaydeder."""

    def __init__(self):
        self.cagri = 0

    def predict(self, yol, threshold=0.5):
        self.cagri += 1
        return {"label": "Sick", "confidence": 0.953, "probability": 0.953, "model": "sahte"}


@pytest.fixture()
def uc(monkeypatch):
    from servers import ai_router as air
    from servers import api_server

    sahte = _SahteTahminci()
    gercek = air._get_or_load_model

    def _yukle(ad, yukleyici):
        return sahte if ad == "thermal" else gercek(ad, yukleyici)

    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(air, "_get_or_load_model", _yukle)
    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    return TestClient(api_server.app, client=("127.0.0.1", 51234)), sahte, air


def _gonder(client, veri: bytes):
    return client.post("/api/ai/vision/thermal", files={"file": ("kare.jpg", veri, "image/jpeg")})


# ── ÖNCE-KIRMIZI: termal olmayan görüntü teşhis ALMAMALI ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ad", ["kamera_benzeri_oda", "kedi_fotografi", "kedi_segmentasyon_fotografi"])
def test_KRITIK_termal_OLMAYAN_goruntu_422_ve_model_CAGRILMAZ(uc, ad):
    client, sahte, _ = uc
    img = {
        "kamera_benzeri_oda": _kamera_benzeri_oda,
        "kedi_fotografi": lambda: _oku(KEDI_FOTO),
        "kedi_segmentasyon_fotografi": lambda: _oku(KEDI_SEG),
    }[ad]()
    r = _gonder(client, _jpg(img))
    assert r.status_code == 422, f"{ad}: termal olmayan görüntü TEŞHİS aldı (HTTP {r.status_code}): {r.text[:200]}"
    assert r.json()["detail"] == UYUMSUZ_METNI
    assert sahte.cagri == 0, "kapı reddetmesine rağmen termal model çalıştı"


def test_KRITIK_GERCEK_termal_GECER_DOGRULANDI_ve_goruntuye_DOKUNULMAZ(uc, monkeypatch):
    client, sahte, air = uc
    verilen = []
    gercek_yaz = air._gecici_gorsel_yaz

    def _yaz(yol, img):
        verilen.append(img.copy())
        return gercek_yaz(yol, img)

    monkeypatch.setattr(air, "_gecici_gorsel_yaz", _yaz)
    for p in (SAGLIKLI, HASTA):
        veri = p.read_bytes()
        r = _gonder(client, veri)
        assert r.status_code == 200, f"{p.name}: gerçek termal reddedildi: {r.text[:200]}"
        j = r.json()
        g = j["girdi_dogrulama"]
        assert g["durum"] == "termal_paleti" and g["dogrulandi"] is True and g["uyari"] is None, g
        assert g["olcum"]["palet"] == "inferno" and g["olcum"]["palet_uyumu"] >= 0.95, g
        # S-SGI.4: kapı yönü ölçmez → "doğrulandı" yanıtı da paletin kamera yönü notunu TAŞIR (uç geçirir)
        assert g["yon_notu"] == INFERNO_YON_NOTU, g
        assert j["prediction"]["label"] == "Sick"
        # Kâhin (kapı geçen görüntüye DOKUNMAZ): modele giden piksel dizisi çözülen girdiyle BİREBİR aynı.
        beklenen = cv2.imdecode(np.frombuffer(veri, np.uint8), cv2.IMREAD_COLOR)
        assert np.array_equal(verilen[-1], beklenen), f"{p.name}: kapı görüntüyü değiştirdi"
    assert sahte.cagri == 2


@pytest.mark.parametrize("palet", ["JET", "RAINBOW", "TURBO", "HOT", "MAGMA", "PLASMA"])
def test_KARSIT_KANIT_BASKA_paletli_termal_de_DOGRULANIR(uc, palet):
    """Meşru termal BLOKLANMAZ: aynı sıcaklık alanı başka paletle (FLIR / Seek / InfiRay seçenekleri) — JPEG q60."""
    client, sahte, _ = uc
    sk = _termal_skaler(_oku(HASTA))
    r = _gonder(client, _jpg(cv2.applyColorMap(sk, getattr(cv2, f"COLORMAP_{palet}")), 60))
    assert r.status_code == 200, f"{palet}: meşru termal reddedildi: {r.text[:200]}"
    assert r.json()["girdi_dogrulama"]["dogrulandi"] is True, r.json()["girdi_dogrulama"]


def test_KRITIK_AKROMATIK_white_hot_GECER_ama_DOGRULANAMADI_der(uc):
    client, sahte, _ = uc
    sk = _termal_skaler(_oku(SAGLIKLI))
    r = _gonder(client, _jpg(cv2.cvtColor(sk, cv2.COLOR_GRAY2BGR)))
    assert r.status_code == 200, r.text[:200]
    g = r.json()["girdi_dogrulama"]
    assert g["durum"] == "akromatik" and g["dogrulandi"] is False, g
    assert g["uyari"].startswith("Girdi termal olarak doğrulanamadı: görüntü renksiz"), g
    assert sahte.cagri == 1


def test_KRITIK_KARARSIZ_arayuz_goruntusu_GECER_ama_DOGRULANAMADI_der(uc):
    """Paletin YALNIZ koyu ucuna oturan görüntü (arayüz ekran görüntüsü) KESİN uyumsuz sayılmaz ama doğrulanmış da sayılmaz."""
    client, sahte, _ = uc
    r = _gonder(client, _jpg(_arayuz_benzeri(), 95))
    assert r.status_code == 200, r.text[:200]
    g = r.json()["girdi_dogrulama"]
    assert g["durum"] == "kararsiz" and g["dogrulandi"] is False and "doğrulanamadı" in g["uyari"], g


def test_KRITIK_A24_termal_denetimi_IC_HATADA_REDDEDER(uc, monkeypatch):
    client, sahte, _ = uc
    from utils import image_domain as dom

    def _bozuk(img):
        raise RuntimeError("palet tablosu bozuk")

    monkeypatch.setattr(dom, "termal_analiz", _bozuk)
    r = _gonder(client, SAGLIKLI.read_bytes())
    assert r.status_code == 422, r.text[:200]
    assert r.json()["detail"] == dom.DENETIM_CALISMADI_MESAJI
    assert sahte.cagri == 0


def test_KARSIT_KANIT_kacis_kapagi_PEMF_AI_DOMAIN_GUARD_0(uc, monkeypatch):
    client, sahte, _ = uc
    monkeypatch.setenv("PEMF_AI_DOMAIN_GUARD", "0")
    r = _gonder(client, _jpg(_kamera_benzeri_oda()))
    assert r.status_code == 200, r.text[:200]
    g = r.json()["girdi_dogrulama"]
    assert g["durum"] == "kapali" and g["dogrulandi"] is False and "PEMF_" not in g["uyari"], g


def test_KRITIK_mikroservis_kolunda_da_kapi_DEVRETMEDEN_once(monkeypatch):
    """GPU profili (`ai_service_enabled()`): termal olmayan görüntü GPU servisine HİÇ gitmez (422)."""
    from servers import ai_router as air
    from servers import api_server

    devredilen = []

    async def _devret(name, **kw):
        devredilen.append(name)
        return {"status": "success", "prediction": {"label": "Sick", "confidence": 0.95}}

    monkeypatch.setattr(air, "ai_service_enabled", lambda: True)
    monkeypatch.setattr(air, "delegate_infer", _devret)
    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    client = TestClient(api_server.app, client=("127.0.0.1", 51234))
    r = _gonder(client, _jpg(_kamera_benzeri_oda()))
    assert r.status_code == 422 and r.json()["detail"] == UYUMSUZ_METNI, r.text[:200]
    assert devredilen == []
    r2 = _gonder(client, SAGLIKLI.read_bytes())
    assert r2.status_code == 200 and devredilen == ["thermal"], r2.text[:200]


def test_KRITIK_GPU_servisi_PARITE_ret_ve_girdi_dogrulama(monkeypatch):
    """`ai_service/app.py /infer/thermal` aynı kapıyı (aynı nesne) uygular ve aynı `girdi_dogrulama` alanını döndürür."""
    from ai_service import app as svc

    sahte = _SahteTahminci()
    sahte.session = type("S", (), {"get_providers": lambda self: ["CPUExecutionProvider"]})()
    monkeypatch.setattr(svc.predictors, "get", lambda ad: sahte)
    monkeypatch.delenv("PEMF_AI_DOMAIN_GUARD", raising=False)
    c = TestClient(svc.app)
    r = c.post("/infer/thermal", files={"file": ("k.jpg", _jpg(_kamera_benzeri_oda()), "image/jpeg")})
    assert r.status_code == 422 and r.json()["error"] == UYUMSUZ_METNI, r.text[:200]
    assert sahte.cagri == 0
    r2 = c.post("/infer/thermal", files={"file": ("k.png", HASTA.read_bytes(), "image/png")})
    assert r2.status_code == 200, r2.text[:200]
    assert (
        r2.json()["girdi_dogrulama"]["durum"] == "termal_paleti" and r2.json()["girdi_dogrulama"]["dogrulandi"] is True
    )
    assert r2.json()["girdi_dogrulama"]["yon_notu"] == INFERNO_YON_NOTU  # S-SGI.4 eşliği


def test_olcum_dagilimi_IKI_YONDE_marj():
    """Eşikler ölçümden seçildi (modül başı); burada aparat girdilerinde iki yönde marj korunur mu (kapı sabiti modülden OKUNMAZ)."""
    from utils import image_domain as dom

    for p in (SAGLIKLI, HASTA):
        durum, m = dom.termal_analiz(_oku(p))
        assert durum == "termal_paleti" and m["palet_uyumu"] >= 0.95 and m["palet_yayilimi"] >= 50, (p.name, m)
    for img in (_kamera_benzeri_oda(), _oku(KEDI_FOTO), _oku(KEDI_SEG)):
        durum, m = dom.termal_analiz(img)
        assert durum == "uyumsuz" and m["palet_uyumu"] <= 0.40, m
