# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""FANTOM / PETRİ SAĞLAYICILARI — GERÇEK boru hattıyla uçtan uca (Faz 2, 2026-09-09).

Stub kapıları sağlayıcı MANTIĞINI ölçer (tests/test_ai_pro_arastirma_saglayicilari.py); bu dosya
GERÇEK `phantom_cv` / `petri_cv` boru hatlarını gerçek örnek fotoğraflarla koşturur:

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
    """05_FantomTumor.jpeg ile: hedef adayları çıkar, doz üret, süreyi raporla."""
    capraz.atla_yoksa("release_assets/ai_models")
    import servers.ai_pro_hedef as hedef

    kare = _kare(f"{_TEST_GIRDI}/05_FantomTumor.jpeg")
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

    if not lz:
        # ArUco yoksa (karar #4) hedef yapısal olarak reddedilir; bu BEKLENEN bir sonuçtur.
        assert meta.get("method") != "aruco_pnp", f"ArUco varken hedef reddedildi: {meta}"
        pytest.skip(f"örnek fotoğrafta kabin işareti yok (yöntem={meta.get('method')}) — doz adımı atlandı")

    D, P, e = sag.predict(x, y, z, 0)
    print(f"[OLCUM] fantom doz: max(D)={max(D):.3f} · e_field={e:.4f} · ood={meta.get('ood')}")
    assert len(D) == 7 and len(P) == 7
    assert any(d > 0 for d in D), "gerçek ağırlıkla tüm duty 0 — sürülebilir parametre üretilmedi"
    assert e > 0, "e_field 0 — E anahtarı eşlemesi gerçek çıktıda tutmuyor"


def test_ENTEGRASYON_petri_gercek_kareden_hedef_ve_SURE_olcumu(kedi_izi):
    """06b_PetriKuyu_aruco.jpg ile: kuyu adayları + doz; YOLO CPU süresi ÖLÇÜLÜR ve raporlanır
    (plan Faz 2 bitiş kriteri: `join_timeout_s` bu ölçüme göre sabitlenir)."""
    capraz.atla_yoksa("release_assets/ai_models")
    import servers.ai_pro_hedef as hedef

    kare = _kare(f"{_TEST_GIRDI}/06b_PetriKuyu_aruco.jpg")
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

    if not lz:
        assert meta.get("method") != "aruco_pnp", f"ArUco varken hedef reddedildi: {meta}"
        pytest.skip(f"örnek fotoğrafta kabin işareti çözülemedi (yöntem={meta.get('method')})")

    D, P, e = sag.predict(x, y, z, 0)
    print(f"[OLCUM] petri doz: max(D)={max(D):.3f} · e_field={e:.4f} · sinif={meta.get('secili_organ_id')}")
    assert len(D) == 7 and any(d > 0 for d in D), "gerçek ağırlıkla sürülebilir parametre üretilmedi"
    assert e > 0, "e_field 0 — E anahtarı eşlemesi gerçek çıktıda tutmuyor"


def test_ENTEGRASYON_analiz_ve_saglayici_AYNI_onbellegi_paylasir():
    """239 MB petri ONNX + 90 MB YOLO iki kez yüklenmesin: analiz ucu ve sağlayıcı aynı
    `_get_or_load_model` anahtarını ve AYNI yükleyiciyi kullanmalı."""
    capraz.atla_yoksa("release_assets/ai_models")
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
