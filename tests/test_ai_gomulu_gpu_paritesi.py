# -*- coding: utf-8 -*-
# Author: mertaygn
"""GÖMÜLÜ ↔ GPU MİKROSERVİS PARİTESİ — AI Hub planı, ADIM 2.

Plan: `docs/ai-hub-gorsel-sahne-plani-2026-09-10.md` §4 ADIM 2.

===============================================================================
⚠️ BU DEPONUN BEŞ KEZ ÖLÇÜLEN ARIZA SINIFI
===============================================================================
Aynı AI ucu İKİ yerde uygulanıyor:
  · gömülü  → `servers/ai_router.py`      (CPU, backend'in içinde)
  · GPU     → `ai_service/app.py`         (ayrı servis, :8100)

`servers/ai_client.py` mikroservis JSON'unu **AYNEN** geçirir. Yani `app.py`'ye
eklenmeyen her alan **GPU dağıtımında sessizce kaybolur** — hata çıkmaz, alan yoktur.

ÖLÇÜLEN SOMUT ZARAR (2026-09-11, ADIM 2 öncesi):
  · `image_w` / `image_h` → `app.py`'de **0 eşleşme**. İstemcinin oran kilidi GPU
    profilinde sessizce yön varsayılanına düşüyor, kare kırpılıyor ve üzerine çizilen
    ORGAN/TÜMÖR İŞARETLERİ canlı görüntüyle KAYIYOR. Bu bir tıbbi karar ekranı.
  · `pnp_residual_px` → router'da var, `app.py`'de yok. Arayüz canlıda
    **"PnP undefinedpx"** yazıyordu (`AiHubScreen.tsx:3879`).

===============================================================================
NEDEN ALAN KÜMESİ KARŞILAŞTIRILIYOR (sayaç DEĞİL)
===============================================================================
"Şu kadar alan var" diyen bir sayaç, alan ADI değişince ya da bir alan başkasıyla
yer değiştirince YEŞİL kalır. Bu kapı uç başına **KÜME** karşılaştırır: gömülüde olup
GPU'da olmayan her alan tek tek raporlanır.
"""

from __future__ import annotations

import ast
import io
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

ROUTER = KOK / "servers" / "ai_router.py"
SERVIS = KOK / "ai_service" / "app.py"

#: gömülü uç adı → GPU uç adı. ⚠️ Yeni bir görsel uç eklenirse BURAYA da eklenir;
#: `test_eslesme_TAM` eşlemenin eksik kalmasını kırmızı yapar.
UC_ESLEMESI = {
    "analyze_landmark": "infer_landmark",
    "analyze_segmentation": "infer_segmentation",
    "analyze_thermal": None,  # GPU tarafında ayrı uç YOK (gömülü-only)
    "analyze_reticulocytes": "infer_reticulocytes",
    "analyze_kidney_ct": "infer_kidney_ct",
    "analyze_em_fantom": "infer_em_fantom",
    "analyze_em_petri": "infer_em_petri",
    "analyze_cat_organ": "infer_cat_organ",
}

#: Oran kilidi sözleşmesi — görsel döndüren HER uç bunları taşımalı.
ORAN_ALANLARI = {"image_w", "image_h"}


def _fonksiyonlar(dosya: Path) -> dict:
    agac = ast.parse(io.open(dosya, encoding="utf-8", errors="replace").read())
    return {d.name: d for d in ast.walk(agac) if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _yanit_alanlari(fn: ast.AST) -> set[str]:
    """Fonksiyonun DÖNDÜĞÜ sözlüklerdeki anahtarlar + `**` ile yayılan yardımcı adları.

    ⚠️ `**_kare_boyutu(img)` gibi yayılımlar ANAHTAR ÜRETİR ama AST'de sabit değildir;
    bu yüzden yayılan çağrının ADI da küme ye eklenir (ör. `*_kare_boyutu`). Kapı
    gömülü/GPU tarafında farklı yardımcı adları kullanıldığı için ADI değil, o adın
    ÜRETTİĞİ sözleşme alanlarını (aşağıda) çözer.
    """
    alanlar: set[str] = set()
    for d in ast.walk(fn):
        if not isinstance(d, ast.Dict):
            continue
        for k, v in zip(d.keys, d.values):
            if k is None:  # `**yayilim`
                ad = ""
                if isinstance(v, ast.Call):
                    ad = v.func.id if isinstance(v.func, ast.Name) else getattr(v.func, "attr", "")
                elif isinstance(v, ast.Name):
                    ad = v.id
                # Boyut sözleşmesini ÜRETEN yardımcılar/değişkenler → alanlarını ekle.
                if ad in ("_kare_boyutu", "_kare_olcusu", "_boyut", "_cat_boyut"):
                    alanlar |= ORAN_ALANLARI
                elif ad:
                    alanlar.add(f"*{ad}")
            elif isinstance(k, ast.Constant) and isinstance(k.value, str):
                alanlar.add(k.value)
    return alanlar


# ============================================================================
# 1. ⚠️ ASIL KAPI — ORAN KİLİDİ HER İKİ DAĞITIMDA DA VAR
# ============================================================================


def test_KRITIK_gomulu_gorsel_uclari_ORAN_alanlarini_tasiyor():
    """MUTASYON: `analyze_em_fantom`dan `**_boyut`u sil → KIRMIZI.

    Sahadaki etki: istemci kutunun oranını bilemez, kareyi kırpar, işaretler kayar.
    """
    fonlar = _fonksiyonlar(ROUTER)
    eksik = {}
    for gomulu in UC_ESLEMESI:
        fn = fonlar.get(gomulu)
        assert fn is not None, f"{gomulu} ai_router.py'de YOK -> capa BAYAT"
        yok = ORAN_ALANLARI - _yanit_alanlari(fn)
        if yok:
            eksik[gomulu] = sorted(yok)
    assert not eksik, f"GOMULU uclarda oran alanlari EKSIK: {eksik}"


def test_KRITIK_GPU_gorsel_uclari_ORAN_alanlarini_tasiyor():
    """⚠️ 2026-09-11 öncesi `app.py`'de `image_w` HİÇ YOKTU (grep 0).

    MUTASYON: `infer_cat_organ`dan `**_cat_boyut`u sil → KIRMIZI.
    """
    fonlar = _fonksiyonlar(SERVIS)
    eksik = {}
    for gomulu, gpu in UC_ESLEMESI.items():
        if gpu is None:
            continue
        fn = fonlar.get(gpu)
        assert fn is not None, f"{gpu} ai_service/app.py'de YOK -> capa BAYAT"
        yok = ORAN_ALANLARI - _yanit_alanlari(fn)
        if yok:
            eksik[gpu] = sorted(yok)
    assert not eksik, (
        f"GPU uclarinda oran alanlari EKSIK: {eksik} -> ai_client JSON'u AYNEN gecirdigi icin "
        "bu alanlar GPU dagitiminda SESSIZCE kaybolur (istemci orani bilemez, isaretler kayar)"
    )


# ============================================================================
# 2. pnp_residual_px — "PnP undefinedpx"
# ============================================================================


def test_KRITIK_pnp_residual_px_HER_IKI_tarafta():
    """Arayüz (`AiHubScreen.tsx:3879`) bunu koşulsuz basıyor; yoksa "undefinedpx" yazar.

    MUTASYON: `app.py`'deki `pnp_residual_px` satırını sil → KIRMIZI.
    """
    gomulu = _yanit_alanlari(_fonksiyonlar(ROUTER)["analyze_cat_organ"])
    gpu = _yanit_alanlari(_fonksiyonlar(SERVIS)["infer_cat_organ"])
    assert "pnp_residual_px" in gomulu, "gomulu cat_organ pnp_residual_px TASIMIYOR"
    assert "pnp_residual_px" in gpu, "GPU cat_organ pnp_residual_px TASIMIYOR -> arayuz 'PnP undefinedpx' yazar"


# ============================================================================
# 3. GENEL PARİTE — gömülüde olup GPU'da olmayan alanlar
# ============================================================================


def test_KRITIK_cat_organ_alan_kumeleri_AYRISMIYOR():
    """⚠️ Sayaç değil KÜME: alan adı değişse ya da biri diğeriyle yer değiştirse
    bir sayaç YEŞİL kalırdı.

    ⚠️ DÜRÜST SINIR: yalnız `cat_organ` karşılaştırılır. Diğer uçlarda iki taraf
    bilinçli olarak farklı alanlar taşıyor (ör. GPU `device`/`inference_ms` ekler,
    gömülü XAI meta ekler) — hepsini eşitlemeye çalışmak yanlış-kırmızı üretirdi.
    `cat_organ` en zengin sözleşmedir ve parite açıkları hep orada ölçüldü.
    """
    gomulu = {a for a in _yanit_alanlari(_fonksiyonlar(ROUTER)["analyze_cat_organ"]) if not a.startswith("*")}
    gpu = {a for a in _yanit_alanlari(_fonksiyonlar(SERVIS)["infer_cat_organ"]) if not a.startswith("*")}
    # GPU'ya özgü alanlar (gömülüde karşılığı YOK, olmasına da gerek yok).
    GPU_OZEL = {"device", "inference_ms", "status"}
    kayip = gomulu - gpu - {"status"}
    # Gömülüye özgü, GPU'da anlamsız olanlar (dağıtım farkı — bilerek hariç).
    GOMULU_OZEL = {"xaiHeatmapB64", "xaiMethod", "xaiNote", "xaiSensitivity"}
    kayip -= GOMULU_OZEL
    assert not kayip, (
        f"gomuluDE VAR, GPU'da YOK: {sorted(kayip)} -> ai_client JSON'u aynen gecirdigi icin "
        "bu alanlar GPU dagitiminda kaybolur"
    )
    assert GPU_OZEL & gpu, "GPU ucu kendi alanlarini da tasimali (capa BAYAT olabilir)"


def test_esleme_TAM_yeni_uc_sessizce_eklenemez():
    """Yeni bir görsel uç eklenip eşlemeye yazılmazsa bu kapı onu GÖRMEZ.

    Bu test, gömülüdeki görsel uç kümesinin eşleme ile aynı olduğunu doğrular.
    """
    fonlar = _fonksiyonlar(ROUTER)
    gorsel = {ad for ad, fn in fonlar.items() if ad.startswith("analyze_") and "image_base64" in _yanit_alanlari(fn)}
    eksik = gorsel - set(UC_ESLEMESI)
    assert not eksik, f"gorsel donen ama ESLEMEDE OLMAYAN uc(lar): {sorted(eksik)} -> parite kapisi onlari OLCMUYOR"
