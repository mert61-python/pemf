# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""FANTOM / PETRİ SAĞLAYICILARI — GERÇEK boru hattıyla uçtan uca (Faz 2, 2026-09-09).

Stub kapıları sağlayıcı MANTIĞINI ölçer (tests/test_ai_pro_arastirma_saglayicilari.py); bu dosya
GERÇEK `phantom_cv_v3` / `petri_cv_v2` boru hatlarını (AI-2: hocanın v3 / v2'si; v1 emekli) gerçek örnek fotoğraflarla koşturur:

  · sağlayıcı gerçek sonuç yapısından hedef çıkarabiliyor mu (alan adları sözleşmesi),
  · EM predictor gerçek ağırlıkla D/P/E üretiyor mu ve e_field > 0 mu,
  · KEDİ modeli hiç yüklenmiyor mu (araştırma-yalnız kurulumda em_kedi ağırlığı YOK),
  · ağır modeller kare başına YENİDEN yüklenmiyor mu,
  · bir karenin GERÇEK süresi ne (petri YOLO CPU tahmini "1-3 s"ti — ÖLÇÜM raporlanır).

⚠️ Ağırlıklar (release_assets/ai_models) yoksa `capraz.atla_yoksa` ile ATLANIR ve bu ATLAMA açıkça
raporlanır — CI'da sessizce boş çalışan bir kapı olmasın. Yerel tam süitte
`PEMF_CAPRAZ_KAYNAK_ZORUNLU=1` ile atlama HATAYA döner.
"""

import time

# ⚠️ `tests` bir PAKET DEĞİL (site-packages'ta aynı adlı bir paket var → `from tests import`
# yanlış modülü çeker). Diğer testlerin deseni: doğrudan modül adıyla import.
import capraz
import pytest

pytestmark = pytest.mark.entegrasyon

_TEST_GIRDI = "ai_hub/PEMF_AI_Test_Girdileri"

#: D4.09 (B-10.224): sağlayıcıların GERÇEKTEN yüklediği ağırlıklar (ürün envanteri `_AI_MODUL_ENVANTERI` ile aynı yollar).
#: Ön-koşul eskiden `release_assets/ai_models` DİZİNİYDİ — dizin temiz klonda da var (izlenen küçük dosyalar), ağırlık
#: yokken test atlanmak yerine FileNotFoundError ile KIRMIZI oluyordu.
_AGIRLIK = {
    "fantom": ("ai_hub/inference_em_fantom/BiLSTM_XXL_Raw.onnx",),
    "petri": ("ai_hub/inference_em_petri/BaggingRegressor.onnx", "ai_hub/inference_petri_dish/yolo11m-seg.onnx"),
}


def _agirlik_gerekli(*saglayicilar: str) -> None:
    """Ağırlıklar ÜRÜNÜN çözücüsünde (modül yanı / model kökleri) yoksa ATLA; zorunlu kipte DÜŞ."""
    from golden import eser

    yollar = tuple(y for s in saglayicilar for y in _AGIRLIK[s])
    if eser.eser_var_mi(*yollar):
        return
    sebep = f"model agirligi urun cozucusunde yok: {list(yollar)}"
    if capraz.ZORUNLU:
        pytest.fail(f"PEMF_CAPRAZ_KAYNAK_ZORUNLU=1 ama {sebep}")
    pytest.skip(sebep)


def _kare(gorece: str):
    """Örnek fotoğrafı BGR kare olarak yükle (yoksa testi atla)."""
    import cv2

    # `capraz.oku` METİN döndürür (yaml/py için); görüntü için YOL gerekiyor.
    capraz.atla_yoksa(gorece)
    yol = capraz.kaynak_yolu(gorece)
    img = cv2.imread(str(yol))
    if img is None:
        pytest.skip(f"örnek fotoğraf okunamadı: {gorece}")
    return img


@pytest.fixture()
def kedi_izi(monkeypatch):
    """Kedi modeli çağrılırsa test ÇÖKSÜN: araştırma yolu em_kedi'ye dokunmamalı."""
    import servers.ai_router as air

    def _kedi_yasak(*a, **k):
        raise AssertionError("araştırma sağlayıcısı KEDİ modelini yükledi — araştırma-yalnız kurulumda çalışmaz")

    monkeypatch.setattr(air, "_get_or_load_kedi", _kedi_yasak)
    monkeypatch.setattr(air, "_get_or_load_catorgan", _kedi_yasak)
    return True


def test_ENTEGRASYON_fantom_gercek_kareden_hedef_ve_doz(kedi_izi):
    """Hocanın GERÇEK fantom fotoğrafı (kâhin, tests/kahin) ile: T1–T5 hedef adayları, doz, süre.

    AI-2 (fantom v3): eskiden `05_FantomTumor.jpeg` (eski dağınık-leke fantomu → v3'te piksel kipi, doz YOK) kullanılıyordu
    ve doz adımı hep ATLANIYORDU. Hocanın fotoğrafında ölçek yeşil halkadan gelir (`coil_ring`), kabin işareti YOK → ArUco
    zorunluluğu (karar #4) kareyi kabul etmez (beklenen); doz adımı öngörücüyle CST kutusu merkezinde doğrudan ölçülür."""
    _agirlik_gerekli("fantom")
    from pathlib import Path

    import cv2
    import numpy as np
    import servers.ai_pro_hedef as hedef

    yol = (
        Path(__file__).resolve().parent
        / "kahin"
        / "hoca_cv_2026_10"
        / "fantom"
        / "WhatsApp Image 2026-10-02 at 19.40.11.jpeg"
    )
    kare = cv2.imdecode(np.fromfile(str(yol), dtype=np.uint8), cv2.IMREAD_COLOR)
    sag = hedef.saglayici_al("fantom")

    t0 = time.perf_counter()
    sag.yukle()
    yukleme_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    lz, x, y, z, guven, overlay, ozne, dokum = sag.localize(kare, 0)
    kare1_ms = (time.perf_counter() - t1) * 1000
    t2 = time.perf_counter()
    sag.localize(kare, 0)
    kare2_ms = (time.perf_counter() - t2) * 1000

    meta = sag.son_lokalizasyon_meta()
    print(
        f"\n[OLCUM] fantom: yukleme {yukleme_ms:.0f} ms · kare1 {kare1_ms:.0f} ms · kare2 {kare2_ms:.0f} ms "
        f"· yontem={meta.get('method')!r} · hedef={len(meta.get('targets') or [])}"
    )

    assert ozne is True, f"örnek fotoğrafta fantom bulunamadı (meta={meta})"
    assert meta.get("targets"), "hedef adayı üretilmedi — gerçek sonuç yapısıyla alan adları uyuşmuyor"
    # Kare 2, ağır model yeniden yüklenmediği için kare 1'in katı olmamalı (enjeksiyon kanıtı).
    assert kare2_ms <= max(1500.0, kare1_ms * 3), (
        f"ikinci kare çok yavaş ({kare2_ms:.0f} ms) — ağır model her karede yeniden yükleniyor olabilir"
    )

    assert {t["label"] for t in meta["targets"]} == {f"Tümör T{i}" for i in range(1, 6)}, (
        "v3 kayıtlı kimlik etikete taşınmadı"
    )
    # Hocanın kuralları geçer (pemf_valid CST kutusu VARSAYIMI, reliable) ama kabin işareti yok → ArUco zorunlu: SÜRÜLMEZ.
    assert meta["pemf_kapisi"]["surulebilir"] is True and lz is False and meta.get("method") == "coil_ring"
    assert "kabin işareti" in sag.ipucu(True, "Tümör T1")

    D, P, e = sag.predict(-43.645, 0.215, 3.335, 0)  # CST fantom kutusu merkezi (eğitim aralığı içi)
    print(f"[OLCUM] fantom doz: max(D)={max(D):.3f} · e_field={e:.4f} · ood={meta.get('ood')}")
    assert len(D) == 7 and len(P) == 7
    assert any(d > 0 for d in D), "gerçek ağırlıkla tüm duty 0 — sürülebilir parametre üretilmedi"
    assert e > 0, "e_field 0 — E anahtarı eşlemesi gerçek çıktıda tutmuyor"


def _sentetik_aruco_yapistir(kare, kenar_px: int = 300, konum: tuple = (700, 250), isaret_id: int = 0):
    """⚠️ SENTETİK İŞARET (A-21 · D5.22): kabin işareti (DICT_5X5_50, kenar 10 cm — `cabin_config_v3.yaml` `aruco`) TESTİN İÇİNDE
    `cv2.aruco.generateImageMarker` ile üretilir ve hocanın GERÇEK fantom fotoğrafına (izli kâhin fikstürü) beyaz kenarlıkla, düz
    (kameraya bakan) yapıştırılır. Fiziksel bir ArUco yerleşimi / kabin ölçümü DEĞİLDİR — gerçek yerleşimin doğruluğu TEZGÂH-2'dir
    (A-17). Konum, tümörlerin kabin içine düştüğü bölge (ölçüldü: 300 px @ (700, 250) → 5 hedef, güven 0,95)."""
    import cv2
    import numpy as np

    sozluk = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_50)
    isaret = cv2.aruco.generateImageMarker(sozluk, isaret_id, kenar_px)
    pay = kenar_px // 5
    blok = np.full((kenar_px + 2 * pay, kenar_px + 2 * pay), 255, np.uint8)
    blok[pay : pay + kenar_px, pay : pay + kenar_px] = isaret
    x, y = konum
    out = kare.copy()
    out[y : y + blok.shape[0], x : x + blok.shape[1]] = cv2.cvtColor(blok, cv2.COLOR_GRAY2BGR)
    return out


def test_ENTEGRASYON_fantom_SENTETIK_ArUco_karede_LOKALIZE_ve_doz_A21(kedi_izi):
    """D5.22 (B-10.5 · A-21): doz adımı LOKALİZASYONDAN gelen hedefle koşar (yukarıdaki test kabin işaretsiz fotoğrafta dozu CST
    kutusu merkezinde DOĞRUDAN ölçer — ArUco zorunluluğu kareyi kabul etmez). Sentetik işaretli kare → `aruco_pnp`, sürülebilir,
    hedef KABİN İÇİNDE lokalize, güven ≥ eşik, gerçek ağırlıkla D > 0 ve E > 0.
    MUTASYON: fantom sağlayıcısının duty'lerini 0 döndürmek ya da ArUco dedektörünü boş döndürmek → KIRMIZI."""
    _agirlik_gerekli("fantom")
    from pathlib import Path

    import cv2
    import numpy as np
    import servers.ai_pro_hedef as hedef

    yol = (
        Path(__file__).resolve().parent
        / "kahin"
        / "hoca_cv_2026_10"
        / "fantom"
        / "WhatsApp Image 2026-10-02 at 19.40.11.jpeg"
    )
    kare = _sentetik_aruco_yapistir(cv2.imdecode(np.fromfile(str(yol), dtype=np.uint8), cv2.IMREAD_COLOR))
    sag = hedef.saglayici_al("fantom")
    sag.yukle()
    lz, x, y, z, guven, _overlay, ozne, _dokum = sag.localize(kare, 0)
    meta = sag.son_lokalizasyon_meta()
    print(f"\n[OLCUM] fantom (SENTETİK ArUco): yontem={meta.get('method')!r} lz={lz} xyz=({x}, {y}, {z}) guven={guven}")
    assert meta.get("method") == "aruco_pnp", f"sentetik kabin işareti çözülmedi: yöntem {meta.get('method')!r}"
    assert meta["pemf_kapisi"]["surulebilir"] is True, meta.get("pemf_kapisi")
    assert ozne is True and meta.get("targets"), "işaretli karede tümör hedefi üretilmedi"
    assert lz is True and guven >= hedef.MIN_GUVEN, f"ArUco'lu karede hedef lokalize SAYILMADI (lz={lz}, güven={guven})"
    D, P, e = sag.predict(x, y, z, 0)  # LOKALİZE hedefin kabin koordinatında (sabit nokta DEĞİL)
    print(f"[OLCUM] fantom doz (lokalize hedef): max(D)={max(D):.3f} · e_field={e:.4f}")
    assert len(D) == 7 and any(d > 0 for d in D), (
        "lokalize hedefte gerçek ağırlıkla tüm duty 0 — sürülebilir parametre yok"
    )
    assert e > 0, "lokalize hedefte e_field 0"


def test_ENTEGRASYON_petri_gercek_kareden_hedef_ve_SURE_olcumu(kedi_izi):
    """Hocanın GERÇEK 24'lük plaka fotoğrafı (kâhin, tests/kahin) ile: 24 kuyu adayı (A1–D6 etiketli) + doz; kare süresi
    ÖLÇÜLÜR ve raporlanır (plan Faz 2 bitiş kriteri: `join_timeout_s` bu ölçüme göre sabitlenir).

    AI-2 (petri v2): eskiden `06b_PetriKuyu_aruco.jpg` (tek kap + sentetik işaret) kullanılıyordu; v2'nin plaka kipinde o
    görüntü doğru olarak "plaka değil" sayılır (aşağıdaki karşıt). Gerçek plakada kabin işareti YOK → `pemf_valid=false`
    → tüketim kapısı kareyi lokalize SAYMAZ (beklenen); doz adımı öngörücüyle doğrudan ölçülür."""
    _agirlik_gerekli("petri")
    from pathlib import Path

    import cv2
    import numpy as np
    import servers.ai_pro_hedef as hedef

    yol = (
        Path(__file__).resolve().parent
        / "kahin"
        / "hoca_cv_2026_10"
        / "petri"
        / "WhatsApp Image 2026-10-02 at 19.40.15(2).jpeg"
    )
    kare = cv2.imdecode(np.fromfile(str(yol), dtype=np.uint8), cv2.IMREAD_COLOR)
    sag = hedef.saglayici_al("petri")

    t0 = time.perf_counter()
    sag.yukle()
    yukleme_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    lz, x, y, z, guven, overlay, ozne, dokum = sag.localize(kare, 0)
    kare1_ms = (time.perf_counter() - t1) * 1000
    t2 = time.perf_counter()
    sag.localize(kare, 0)
    kare2_ms = (time.perf_counter() - t2) * 1000

    meta = sag.son_lokalizasyon_meta()
    print(
        f"\n[OLCUM] petri: yukleme {yukleme_ms:.0f} ms · kare1 {kare1_ms:.0f} ms · kare2 {kare2_ms:.0f} ms "
        f"· yontem={meta.get('method')!r} · kuyu={len(meta.get('targets') or [])} · join_timeout_s={sag.join_timeout_s}"
    )

    assert ozne is True, f"örnek fotoğrafta petri plakası bulunamadı (meta={meta})"
    assert meta.get("targets"), "kuyu adayı üretilmedi — gerçek sonuç yapısıyla alan adları uyuşmuyor"
    # Kamera devri (join) bir kare süresini KAPSAMALI; aksi halde çift VideoCapture riski.
    assert sag.join_timeout_s * 1000 > kare2_ms, (
        f"join süresi ({sag.join_timeout_s} s) bir kareyi ({kare2_ms:.0f} ms) kapsamıyor — "
        "hazırlık thread'i turu bitiremeden seans kamerayı açmaya çalışır"
    )

    hedefler = meta.get("targets") or []
    assert len(hedefler) == 24, f"24'lük plakada {len(hedefler)} kuyu adayı"
    assert {t["label"] for t in hedefler} >= {"Kuyu A1", "Kuyu D6"}, "v2 kuyucuk kimliği (A1–D6) etikete taşınmadı"
    # Kabin işareti yok → plaka çerçevesi → pemf_valid=false → kapı kareyi KESER (beklenen; ArUco zorunlu, karar #4).
    assert lz is False and meta.get("method") == "plate_grid", meta.get("method")
    assert "pemf_gecersiz" in meta["pemf_kapisi"]["nedenler"], meta.get("pemf_kapisi")

    # Doz adımı (gerçek ağırlık): kabin merkezinde, öngörücüyle doğrudan.
    D, P, e = sag.predict(0.0, 0.0, 0.0, 0)
    print(f"[OLCUM] petri doz: max(D)={max(D):.3f} · e_field={e:.4f} · sinif={meta.get('secili_organ_id', 1)}")
    assert len(D) == 7 and any(d > 0 for d in D), "gerçek ağırlıkla sürülebilir parametre üretilmedi"
    assert e > 0, "e_field 0 — E anahtarı eşlemesi gerçek çıktıda tutmuyor"

    # KARŞIT: tek kap + sentetik işaret (06b) plaka kipinde "plaka değil" → ÖZNE YOK (ipucu yerleşimi söyler).
    tek = _kare(f"{_TEST_GIRDI}/06b_PetriKuyu_aruco.jpg")
    lz2, *_orta, ozne2, _d = sag.localize(tek, 0)
    assert lz2 is False and ozne2 is False and "petri plakası görünmüyor" in sag.ipucu(False, "Kuyu")


def test_ENTEGRASYON_analiz_ve_saglayici_AYNI_onbellegi_paylasir():
    """239 MB petri ONNX + 90 MB YOLO iki kez yüklenmesin: analiz ucu ve sağlayıcı aynı
    `_get_or_load_model` anahtarını ve AYNI yükleyiciyi kullanmalı.

    ⚠️ AĞIRLIK GEREKMEZ (4-A kapanış, 2026-10-10): yalnız önbellek anahtarı ve yükleyici KİMLİĞİ ölçülür, model yüklenmez —
    D4.09'da buraya da `_agirlik_gerekli` eklenmişti; temiz klonda GEÇEN test atlanıyor, ZORUNLU kipte YALANCI kırmızı
    veriyordu (kapanış süiti tabanla karşılaştırmasında "passed -> skipped" olarak ölçüldü)."""
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air

    for ad, anahtar, yukleyici in (
        ("fantom", "em_fantom_cv", air._yukle_em_fantom_cv),
        ("petri", "em_petri_cv", air._yukle_em_petri_cv),
    ):
        sag = hedef.saglayici_al(ad)
        assert sag.onbellek_anahtari == anahtar, f"{ad}: önbellek anahtarı analiz ucuyla aynı değil"
        assert sag._yukleyici() is yukleyici, (
            f"{ad}: sağlayıcı KENDİ yükleyicisini kullanıyor — ağır model iki kez yüklenir"
        )
