# -*- coding: utf-8 -*-
# Author: mertaygn
"""ÇOK-PANELLİ YANIT (G8) — AI Hub planı, ADIM 3.

Plan: `docs/ai-hub-gorsel-sahne-plani-2026-09-10.md` §4 ADIM 3.

===============================================================================
ÖLÇÜLEN DURUM (düzeltme öncesi)
===============================================================================
fantom/petri boru hatları `render_all_panels` ile **7 panel** üretiyordu; yanıt yalnız
`07_combined` mozaiğini taşıyor, diğer **6 panel AYNI SATIRDA çöpe atılıyordu**.

Sahibin şikâyeti bunun sonucuydu: "sonuç küçük ve yazıları okunmaz geliyor" — çünkü
gösterilen tek şey 2×3 mozaikti ve mozaik, sahne tavanına (330 px) sığdırılınca panel
başına ~81 px kalıyor, gömülü ~12 px metin ~0,35 px'e iniyordu.

⚠️ EK CPU YOK: paneller zaten üretiliyordu. Değişen tek şey, üretilenin çöpe atılmaması.

===============================================================================
BU DOSYA NE ÖLÇER (planın G8 şartı)
===============================================================================
· `render_panels` **7 anahtarı FARKLI SHAPE'li gerçek numpy dizileriyle** döndürür ve
  her panelin `image_w`/`image_h`'i **o panelin kendi shape'iyle** doğrulanır.
  ⚠️ Hepsi aynı boyutta olsaydı, tüm panellere aynı boyutu yazan bir hata YEŞİL kalırdı.
· Kök `image_base64` KALIR (geriye uyum).
· Mutasyon: bir paneli yayından çıkar → KIRMIZI.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from utils.panel_yayin import (  # noqa: E402
    PANEL_ADLARI,
    PETRI_PANEL_ADLARI,
    panelleri_yayina_hazirla,
)


def _panel(w: int, h: int):
    """Gürültülü BGR kare — düz renk JPEG'de aldatıcıdır (her kalitede küçük çıkar)."""
    rng = np.random.default_rng(w * 1000 + h)
    return rng.integers(0, 255, (h, w, 3), dtype=np.uint8)


#: ⚠️ HER PANEL FARKLI SHAPE — planın G8 şartı. Aynı olsalardı "hepsine aynı boyutu yaz"
#: hatası yakalanamazdı.
SAHTE_PANELLER = {
    "01_input": _panel(640, 480),
    "02_phantom_detect": _panel(800, 600),
    "03_phantom_mask": _panel(320, 240),
    "04_tumors": _panel(1024, 768),
    "05_local_coords": _panel(500, 900),  # dikey
    "06_predictions": _panel(1200, 400),  # geniş
    "07_combined": _panel(1920, 2880),  # mozaik — KAPAĞI aşar
}


def _kodlayici(img):
    """Üretimdeki `_kapakli_kodla` — gerçek olan kullanılır, taklit DEĞİL."""
    from servers.ai_router import _kapakli_kodla

    return _kapakli_kodla(img)


# ============================================================================
# 1. ⚠️ ASIL KAPI — her panelin boyutu KENDİ shape'iyle uyuşur
# ============================================================================


def test_KRITIK_her_panelin_boyutu_KENDI_shapeIYLE_uyusur():
    """MUTASYON: `panelleri_yayina_hazirla`da `**boyut`u sabit bir sözlükle değiştir →
    KIRMIZI.

    Sahadaki etki: istemcinin oran kilidi yanlış hesaplar, panel kırpılır/gerilir.
    """
    yayin = panelleri_yayina_hazirla(SAHTE_PANELLER, _kodlayici, PANEL_ADLARI)
    assert len(yayin) == 7, f"7 panel bekleniyordu, {len(yayin)} geldi"

    for p in yayin:
        ham = SAHTE_PANELLER[p["k"]]
        # Kodlanan kareyi GERİ ÇÖZ — bildirilen boyut ONUNLA uyuşmalı (orijinalle değil:
        # kapak mozaiği küçültür).
        geri = cv2.imdecode(np.frombuffer(base64.b64decode(p["image_base64"]), dtype=np.uint8), cv2.IMREAD_COLOR)
        assert geri is not None, f"{p['k']}: kodlanan JPEG cozulemedi"
        assert (p["image_w"], p["image_h"]) == (geri.shape[1], geri.shape[0]), (
            f"{p['k']}: bildirilen {p['image_w']}x{p['image_h']} != kodlanan {geri.shape[1]}x{geri.shape[0]}"
        )
        # Kapağı aşmayan paneller DOKUNULMADAN geçmeli (gereksiz yeniden ölçekleme yok).
        if max(ham.shape[:2]) <= 1600:
            assert (p["image_w"], p["image_h"]) == (ham.shape[1], ham.shape[0]), (
                f"{p['k']}: kapak altindaki panel GEREKSIZ olceklendi"
            )


def test_KRITIK_mozaik_paneli_KAPAGA_indirilir():
    """`07_combined` 1920×2880 → uzun kenar 1600'e inmeli."""
    from servers.ai_router import MOZAIK_AZAMI_KENAR

    yayin = {p["k"]: p for p in panelleri_yayina_hazirla(SAHTE_PANELLER, _kodlayici, PANEL_ADLARI)}
    m = yayin["07_combined"]
    assert max(m["image_w"], m["image_h"]) == MOZAIK_AZAMI_KENAR, f"mozaik kapaga inmedi: {m['image_w']}x{m['image_h']}"


# ============================================================================
# 2. SIRA VE ADLAR — arayüzün ok tuşları bunu izler
# ============================================================================


def test_KRITIK_panel_SIRASI_analiz_akisini_izler():
    """MUTASYON: `sirali` hesabını `panels.keys()`e çevir → KIRMIZI (dict sırasına güvenmek).

    Arayüzdeki ileri/geri okları bu sırada gezer; sıra bozulursa operatör panelleri
    rastgele bir düzende görür.

    ⚠️ GİRDİ BİLEREK TERS SIRADA: panel sözlüğü doğal sırada verilseydi `list(panels)`
    mutasyonu da YEŞİL kalırdı — yani test hiçbir şey ölçmezdi. Ters girdi, sıranın
    `dict` ekleme sırasından DEĞİL tablodan geldiğini kanıtlar.
    """
    ters = {k: SAHTE_PANELLER[k] for k in reversed(list(SAHTE_PANELLER))}
    yayin = panelleri_yayina_hazirla(ters, _kodlayici, PANEL_ADLARI)
    assert [p["k"] for p in yayin] == list(PANEL_ADLARI), "panel SIRASI tanimli sirayla uyusmuyor"


def test_KRITIK_petri_KENDI_ad_tablosunu_kullanir():
    """⚠️ Petri boru hattı FARKLI anahtarlar üretir (`02_yolo_dets`/`03_yolo_masks`).

    Fantom tablosu kullanılırsa o paneller "bilinmeyen" dalına düşer: ham anahtarla
    adlandırılır ve sıraları bozulur.

    MUTASYON: petri ucunda `_PETRI_PANEL_ADLARI` yerine `_PANEL_ADLARI` kullan → KIRMIZI.
    """
    petri = {
        "01_input": _panel(640, 480),
        "02_yolo_dets": _panel(800, 600),
        "03_yolo_masks": _panel(320, 240),
        "04_classify": _panel(400, 400),
        "05_local_coords": _panel(500, 500),
        "06_predictions": _panel(600, 600),
        "07_combined": _panel(1200, 900),
    }
    yayin = panelleri_yayina_hazirla(petri, _kodlayici, PETRI_PANEL_ADLARI)
    assert [p["k"] for p in yayin] == list(PETRI_PANEL_ADLARI)
    adlar = {p["k"]: p["ad"] for p in yayin}
    assert adlar["02_yolo_dets"] == "Tespit" and adlar["03_yolo_masks"] == "Maske", (
        f"petri panelleri HAM anahtarla adlandirilmis: {adlar}"
    )


def test_BILINMEYEN_panel_atlanmaz_YAYINLANIR():
    """Boru hattı yeni bir panel eklerse arayüzde GÖRÜNMELİ.

    Sessizce düşürmek "üretildi ama kimse görmedi" arızasının ta kendisidir.
    """
    p = dict(SAHTE_PANELLER)
    p["08_yeni_panel"] = _panel(200, 200)
    yayin = panelleri_yayina_hazirla(p, _kodlayici, PANEL_ADLARI)
    anahtarlar = [x["k"] for x in yayin]
    assert "08_yeni_panel" in anahtarlar, "yeni panel SESSIZCE dusuruldu"
    assert anahtarlar[-1] == "08_yeni_panel", "bilinmeyen panel bilinenlerin SONUNA gelmeli"


# ============================================================================
# 3. DAYANIKLILIK
# ============================================================================


def test_KRITIK_tek_BOZUK_panel_tum_yayini_dusurmez():
    """Bir panel kodlanamazsa diğerleri yayınlanmaya devam etmeli.

    MUTASYON: `except Exception: continue` dalını kaldır → KIRMIZI (istisna sızar,
    analiz komple kaybolur).
    """
    sayac = {"n": 0}

    def _ariza_kodlayici(img):
        sayac["n"] += 1
        if sayac["n"] == 3:
            raise RuntimeError("bu panel bozuk")
        return _kodlayici(img)

    yayin = panelleri_yayina_hazirla(SAHTE_PANELLER, _ariza_kodlayici, PANEL_ADLARI)
    assert len(yayin) == 6, f"bozuk panel disindakiler yayinlanmali, {len(yayin)} geldi"


def test_BOS_panel_sozlugu_bos_liste_dondurur():
    assert panelleri_yayina_hazirla({}, _kodlayici, PANEL_ADLARI) == []
    assert panelleri_yayina_hazirla(None, _kodlayici, PANEL_ADLARI) == []


# ============================================================================
# 4. ⚠️ GERİYE UYUM + İKİ DAĞITIM AYNI SÖZLEŞME
# ============================================================================


def test_KRITIK_kok_image_base64_KALDI_ve_paneller_EK_alan():
    """Eski istemci `paneller`i görmez; kök `image_base64` onun tek kaynağıdır.

    MUTASYON: fantom yanıtından `"image_base64": b64_image` satırını kaldırıp yerine
    yalnız `paneller` bırak → KIRMIZI.
    """
    import ast
    import io as _io

    kaynak = _io.open(KOK / "apps" / "backend" / "servers" / "ai_router.py", encoding="utf-8").read()
    agac = ast.parse(kaynak)
    for ad in ("analyze_em_fantom", "analyze_em_petri"):
        fn = next(d for d in ast.walk(agac) if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.name == ad)
        alanlar = set()
        for d in ast.walk(fn):
            if isinstance(d, ast.Dict):
                alanlar |= {k.value for k in d.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        assert "image_base64" in alanlar, f"{ad}: kok image_base64 KALDIRILDI -> eski istemci BOS ekran"
        assert "paneller" in alanlar, f"{ad}: paneller yayinlanmiyor"


def test_KRITIK_GPU_tarafi_da_panelleri_yayinliyor():
    """Plan: "AYNI COMMIT'te `ai_service/app.py`". Aksi halde GPU profilinde galeri BOŞ.

    MUTASYON: `app.py`den `"paneller": _paneller,` satırını sil → KIRMIZI.
    """
    import ast
    import io as _io

    kaynak = _io.open(KOK / "ai_service" / "app.py", encoding="utf-8").read()
    agac = ast.parse(kaynak)
    for ad in ("infer_em_fantom", "infer_em_petri"):
        fn = next(d for d in ast.walk(agac) if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.name == ad)
        alanlar = set()
        for d in ast.walk(fn):
            if isinstance(d, ast.Dict):
                alanlar |= {k.value for k in d.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        assert "paneller" in alanlar, f"GPU {ad}: paneller YOK -> GPU profilinde galeri BOS"


def test_KRITIK_GPU_kok_gorseli_de_KAPAKLI_kodlanir():
    """⚠️ ÖLÇÜLEN AÇIK (ADIM 3 sırasında bulundu): GPU fantom/petri kök görseli `_jpg_b64` ile
    HAM mozaiği gönderiyordu — ADIM 1'in ölçtüğü 6048×12256'lık dev kare GPU profilinde
    yaşamaya devam ediyordu. Gömülü yol aynı kareyi 1600 px'e indiriyordu.

    Sahadaki etki: aynı analiz, GPU profilinde megabaytlarca kök görsel; tünel üzerinden
    kullanan makinede gözle görülür gecikme. Üstelik kök görsel `07_combined` panelinden
    FARKLI çözünürlükte oluyordu (aynı kare, iki ayrı kodlama).

    MUTASYON: `"image_base64": base64...(_kok_bayt)`ı `_jpg_b64(overlay)`a geri çevir → KIRMIZI.
    """
    import ast
    import io as _io

    kaynak = _io.open(KOK / "ai_service" / "app.py", encoding="utf-8").read()
    agac = ast.parse(kaynak)
    for ad in ("infer_em_fantom", "infer_em_petri"):
        fn = next(d for d in ast.walk(agac) if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.name == ad)
        # ⚠️ ÇAĞRI DEĞİL AD taranıyor: kodlayıcı artık `_kok_gorseli_sec(...)`e ARGÜMAN olarak
        # geçiyor (mozaiği iki kez kodlamamak için). Yalnız `ast.Call`a bakan bir çıpa bu
        # yeniden-kullanım refaktöründe sahte kırmızı verirdi.
        adlar = {d.id for d in ast.walk(fn) if isinstance(d, ast.Name)}
        assert "_kapakli_kodla_servis" in adlar, f"GPU {ad}: kapakli kodlayici KULLANILMIYOR"
        assert "_jpg_b64" not in adlar, (
            f"GPU {ad}: HAM `_jpg_b64` hala kullaniliyor -> kok gorsel KAPAKSIZ (dev mozaik)"
        )


def test_KRITIK_iki_dagitim_AYNI_kapagi_kullanir():
    """Kapak ayrışırsa aynı analiz dağıtıma göre farklı çözünürlükte döner.

    MUTASYON: `app.py`deki `MOZAIK_AZAMI_KENAR`ı 1200 yap → KIRMIZI.
    """
    import io as _io
    import re

    from servers.ai_router import MOZAIK_AZAMI_KENAR as GOMULU

    servis = _io.open(KOK / "ai_service" / "app.py", encoding="utf-8").read()
    m = re.search(r"^MOZAIK_AZAMI_KENAR\s*=\s*(\d+)", servis, re.M)
    assert m, "ai_service/app.py MOZAIK_AZAMI_KENAR tanimlamiyor"
    assert int(m.group(1)) == GOMULU, (
        f"kapak AYRISTI: gomulu {GOMULU}, GPU {m.group(1)} -> ayni analiz farkli cozunurlukte doner"
    )


# ============================================================================
# 5. ⚠️ TEL SEVİYESİ (planın G8 şartı) — UÇ NOKTA GERÇEKTEN 7 PANEL DÖNÜYOR MU
# ============================================================================
# Yukarıdaki birim kapıları `panelleri_yayina_hazirla`yı ölçer; bu bölüm UCU ölçer.
# ⚠️ İkisi AYNI ŞEY DEĞİL: modül kusursuz çalışırken uçtaki `_paneller = []` satırı ya da
# yanıttan düşen bir anahtar arayüze hiçbir panel ulaştırmaz ve birim testleri YEŞİL kalır.
#
# Modeller CI'da yüklü olmadığı için boru hattı `_get_no_or_load_model` casusuyla taklit edilir
# (`test_petri_ayar_parametreleri.py::yakala` deseni).

_OLCULER = [(640, 480), (800, 600), (320, 240), (1024, 768), (500, 900), (1200, 400), (1920, 2880)]


def _sahte_panel_seti(anahtarlar) -> dict:
    """⚠️ HER PANEL FARKLI SHAPE — aynı olsalardı "hepsine aynı boyutu yaz" hatası geçerdi.

    ⚠️ EKLEME SIRASI DA TERS: boru hattı sözlüğü doğal sırada verseydi, sırayı `dict`ten okuyan
    bir gerileme telde de fark edilmezdi.
    """
    esli = list(zip(list(anahtarlar), _OLCULER))
    return {k: _panel(w, h) for k, (w, h) in reversed(esli)}


def _jpeg(w: int = 256, h: int = 192, renkli: bool = False) -> bytes:
    """Yükleme için küçük gerçek JPEG — test varlığına bağımlılık YOK (CI'da hep koşar).

    ⚠️ ALAN KAPISI (`utils.image_domain`) GİRDİYİ DENETLİYOR — rastgele renk gürültüsü
    "boyalı patoloji preparatı (H&E)" sayılıp 422 ile reddediliyor (ölçüldü: stain_ratio 0,23 ·
    sat_mean 0,30). Bu yüzden kare modüle göre üretilir:
      · `em_petri`  → {COLOR, GRAYSCALE}: üç kanalı eşit gradyan `grayscale` olarak geçer.
      · `em_fantom` → {COLOR} YALNIZ: gri reddedilir, bu yüzden YEŞİL gradyan (OpenCV H≈60,
        boyama aralığı 125-178 mor→pembe'nin UZAĞINDA) → `color`.
    """
    g = np.tile(np.linspace(0, 255, w, dtype=np.uint8), (h, 1))
    sifir = np.zeros_like(g)
    ok, buf = cv2.imencode(".jpg", cv2.merge([sifir, g, sifir] if renkli else [g, g, g]))
    assert ok
    return buf.tobytes()


class _SahtePetriSonuc:
    def __init__(self):
        self.success = True
        self.error = None
        self.n_wells = 2
        self.n_cancer = 1
        self.n_healthy = 1
        self.method = "sahte"
        self.mm_per_px = 0.5
        self.wells = []
        self.timing_ms = {}
        self.plausibility = {}
        self.yolo_ayar = {}
        self.resize = {}


class _SahteFantomSonuc:
    def __init__(self):
        self.success = True
        self.error = None
        self.n_tumor = 1
        self.n_healthy = 1
        self.method = "sahte"
        self.mm_per_px = 0.5
        self.timing_ms = {}

    def to_dict(self):
        return {"tumor_regions": [], "healthy_regions": []}


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from servers import api_server

    return TestClient(api_server.app, client=("127.0.0.1", 51239))


@pytest.fixture()
def sahte_boru(monkeypatch):
    """Boru hattını taklit et; `render_panels` 7 anahtarı FARKLI shape'lerle döndürsün."""
    from servers import ai_router

    uretilen: dict = {}

    def _kur(anahtarlar, sonuc_sinifi):
        class _SahtePipeline:
            def __init__(self, cfg, **kw):
                pass

            def process_image(self, img, **kw):
                return sonuc_sinifi(), {}

            def render_panels(self, ctx, result, lang="tr"):
                uretilen.clear()
                uretilen.update(_sahte_panel_seti(anahtarlar))
                return dict(uretilen)

        monkeypatch.setattr(
            ai_router,
            "_get_or_load_model",
            lambda key, loader: {
                "cls": _SahtePipeline,
                "cfg": object(),
                "yolo_path": "x.onnx",
                "yolo": object(),
                "predictor": object(),
            },
        )
        # GPU profiline devretmesin — bu test GÖMÜLÜ yolu ölçüyor.
        monkeypatch.setattr(ai_router, "ai_service_enabled", lambda: False)
        return uretilen

    return _kur


def _panelleri_dogrula(yanit: dict, uretilen: dict, adlar: dict, uc: str):
    """Her panelin boyutu KENDİ shape'iyle mi uyuşuyor + kök alan yerinde mi."""
    paneller = yanit.get("paneller")
    assert isinstance(paneller, list), f"{uc}: 'paneller' alani YOK -> arayuzde galeri BOS"
    assert len(paneller) == 7, f"{uc}: 7 panel bekleniyordu, {len(paneller)} yayinlandi"
    assert [p["k"] for p in paneller] == list(adlar), f"{uc}: panel SIRASI bozuk"

    for p in paneller:
        geri = cv2.imdecode(np.frombuffer(base64.b64decode(p["image_base64"]), dtype=np.uint8), cv2.IMREAD_COLOR)
        assert geri is not None, f"{uc}/{p['k']}: JPEG cozulemedi"
        assert (p["image_w"], p["image_h"]) == (geri.shape[1], geri.shape[0]), (
            f"{uc}/{p['k']}: bildirilen {p['image_w']}x{p['image_h']} != kodlanan {geri.shape[1]}x{geri.shape[0]}"
        )
        ham = uretilen[p["k"]]
        if max(ham.shape[:2]) <= 1600:
            assert (p["image_w"], p["image_h"]) == (ham.shape[1], ham.shape[0]), (
                f"{uc}/{p['k']}: panel boyutu KENDI shape'iyle uyusmuyor"
            )
        assert p["ad"] == adlar[p["k"]], f"{uc}/{p['k']}: gosterim adi yanlis ({p['ad']})"

    # ⚠️ GERİYE UYUM: kök `image_base64` (07_combined) KALMALI ve panelle AYNI olmalı.
    birlesik = next(p for p in paneller if p["k"] == "07_combined")
    assert yanit.get("image_base64"), f"{uc}: kok image_base64 KAYBOLDU -> eski istemci BOS ekran"
    assert yanit["image_base64"] == birlesik["image_base64"], (
        f"{uc}: kok gorsel 07_combined panelinden FARKLI -> iki ayri kodlama"
    )
    assert (yanit["image_w"], yanit["image_h"]) == (birlesik["image_w"], birlesik["image_h"])


def test_KRITIK_UC_petri_YEDI_paneli_TELDE_yayinliyor(client, sahte_boru):
    """MUTASYON: uçtaki `_paneller = _panelleri_hazirla(...)`ı `_paneller = []` yap → KIRMIZI.

    Sahadaki etki: 7 panel üretilir, 6'sı çöpe gider, operatör yalnız okunmaz mozaiği görür —
    yani düzeltilmeye çalışılan arızanın ta kendisi geri gelir.
    """
    uretilen = sahte_boru(PETRI_PANEL_ADLARI, _SahtePetriSonuc)
    r = client.post("/api/ai/vision/em_petri", files={"file": ("t.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text
    _panelleri_dogrula(r.json(), uretilen, PETRI_PANEL_ADLARI, "petri")


def test_KRITIK_UC_fantom_YEDI_paneli_TELDE_yayinliyor(client, sahte_boru):
    """MUTASYON: fantom ucunda `_PANEL_ADLARI`yı `{}` yap → KIRMIZI (adlar ham anahtara düşer)."""
    uretilen = sahte_boru(PANEL_ADLARI, _SahteFantomSonuc)
    r = client.post("/api/ai/vision/em_fantom", files={"file": ("t.jpg", _jpeg(renkli=True), "image/jpeg")})
    assert r.status_code == 200, r.text
    _panelleri_dogrula(r.json(), uretilen, PANEL_ADLARI, "fantom")


def test_KRITIK_mozaik_IKI_KEZ_kodlanmaz(client, sahte_boru, monkeypatch):
    """⚠️ Kök görsel ile `07_combined` paneli AYNI karedir — tek kodlama yetmeli.

    ÖLÇÜLDÜ (2026-09-12): 6048×12256'lık dikey telefon mozaiğinde `_kapakli_kodla` çağrısı
    **38 ms**. İlk yazımda uç, kareyi bir kez kök görsel bir kez panel için kodluyordu → istek
    başına 38 ms saf israf, üstelik iki dağıtımda da. Planın "ek CPU YOK" iddiası ancak bu
    yeniden kullanımla doğru.

    ⚠️ İKİNCİ KAZANÇ: kök görsel artık panelle BİT-BİT aynı; ayrı kodlansalardı ileride biri
    kapak/kalite değiştirdiğinde sessizce ayrışırlardı.

    MUTASYON: uçta `b64_image, _boyut = _kok_gorseli_sec(...)`ı
    `_bayt, _boyut = _kapakli_kodla(panels["07_combined"])`a geri çevir → KIRMIZI (8 çağrı).
    """
    from servers import ai_router

    uretilen = sahte_boru(PETRI_PANEL_ADLARI, _SahtePetriSonuc)
    sayac = {"n": 0}
    gercek = ai_router._kapakli_kodla

    def _sayan(img, *a, **k):
        sayac["n"] += 1
        return gercek(img, *a, **k)

    monkeypatch.setattr(ai_router, "_kapakli_kodla", _sayan)
    r = client.post("/api/ai/vision/em_petri", files={"file": ("t.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text

    assert sayac["n"] == len(uretilen), (
        f"panel basina TEK kodlama bekleniyordu ({len(uretilen)}), {sayac['n']} kodlama yapildi "
        "-> mozaik iki kez kodlaniyor (olculen 38 ms/kodlama bosa gidiyor)"
    )
    y = r.json()
    birlesik = next(p for p in y["paneller"] if p["k"] == "07_combined")
    assert y["image_base64"] == birlesik["image_base64"], "kok gorsel panelden AYRI kodlanmis"


def test_KRITIK_PANEL_KODLANAMAZSA_kok_gorsel_YINE_doner(client, sahte_boru, monkeypatch):
    """⚠️ YEDEK YOL: `07_combined` paneli kodlanamazsa kök görsel YİNE dönmeli.

    Kök görselin kaybolması eski istemcide BOŞ EKRAN demektir — panel yayını bir iyileştirme,
    bir tek-nokta arızası değil.

    ⚠️ BU TEST BİR TASARIM HATASI YAKALADI (2026-09-12): yedek yol önce `panels["07_combined"]`i
    YENİDEN kodluyordu. Oysa panel listede yoksa sebebi zaten o karenin KODLANAMAMASIDIR —
    aynı kare yeniden kodlanınca aynı hata geliyor ve analizin TAMAMI 500'e dönüyordu.
    Yedek artık ORİJİNAL GİRDİ karesi.

    MUTASYON: `kok_gorseli_sec`teki yedek kodlama satırını sil → KIRMIZI (boş görsel).
    """
    from servers import ai_router

    sahte_boru(PETRI_PANEL_ADLARI, _SahtePetriSonuc)
    gercek = ai_router._kapakli_kodla

    def _birlesigi_bozan(img, *a, **k):
        # 07_combined en BÜYÜK kare (1920×2880) — onu ayırt etmek için boyutuna bak.
        if img.shape[0] == 2880:
            raise RuntimeError("mozaik kodlanamadi")
        return gercek(img, *a, **k)

    monkeypatch.setattr(ai_router, "_kapakli_kodla", _birlesigi_bozan)
    r = client.post("/api/ai/vision/em_petri", files={"file": ("t.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text
    y = r.json()
    assert not any(p["k"] == "07_combined" for p in y["paneller"]), "bozuk panel yayindan dusmeliydi"
    assert y["image_base64"], "panel kodlanamayinca kok gorsel de KAYBOLDU -> eski istemcide BOS EKRAN"
    assert y["image_w"] and y["image_h"], "yedek yolda boyut alanlari kayip"


def test_KRITIK_TESPIT_YOKken_paneller_BOS_ama_gorsel_VAR(client, monkeypatch):
    """`success=False` dalı: panel yok ama kök görsel (orijinal) dönmeli.

    ⚠️ Bu dalda `paneller` alanının TAMAMEN kaybolması istemcide `undefined.map` ile çökerdi;
    alan var ama boş olmalı.
    """
    from servers import ai_router

    class _Bos(_SahtePetriSonuc):
        def __init__(self):
            super().__init__()
            self.success = False
            self.error = None

    class _SahtePipeline:
        def __init__(self, cfg, **kw):
            pass

        def process_image(self, img, **kw):
            return _Bos(), {}

    monkeypatch.setattr(ai_router, "ai_service_enabled", lambda: False)
    monkeypatch.setattr(
        ai_router,
        "_get_or_load_model",
        lambda key, loader: {
            "cls": _SahtePipeline,
            "cfg": object(),
            "yolo_path": "x.onnx",
            "yolo": object(),
            "predictor": object(),
        },
    )
    r = client.post("/api/ai/vision/em_petri", files={"file": ("t.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text
    y = r.json()
    assert y["status"] == "no_detection"
    assert y["paneller"] == [], "tespit yokken panel yayinlanmamali"
    assert y["image_base64"], "tespit yokken bile ORIJINAL gorsel donmeli"
