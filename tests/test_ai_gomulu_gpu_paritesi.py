# -*- coding: utf-8 -*-
# Author: mertaygn
"""GÖMÜLÜ ↔ GPU MİKROSERVİS PARİTESİ — AI Hub planı, ADIM 2.

Plan: `docs/ai-hub-gorsel-sahne-plani-2026-09-10.md` §4 ADIM 2.

===============================================================================
⚠️ BU DEPONUN BEŞ KEZ ÖLÇÜLEN ARIZA SINIFI
===============================================================================
Aynı AI ucu İKİ yerde uygulanıyor:
  · gömülü  → `apps/backend/servers/ai_router.py`      (CPU, backend'in içinde)
  · GPU     → `ai_service/app.py`         (ayrı servis, :8100)

`apps/backend/servers/ai_client.py` mikroservis JSON'unu **AYNEN** geçirir. Yani `app.py`'ye
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

ROUTER = KOK / "apps" / "backend" / "servers" / "ai_router.py"
SERVIS = KOK / "ai_service" / "app.py"

#: gömülü uç adı → GPU uç adı. ⚠️ Yeni bir görsel uç eklenirse BURAYA da eklenir;
#: `test_eslesme_TAM` eşlemenin eksik kalmasını kırmızı yapar.
UC_ESLEMESI = {
    "analyze_landmark": "infer_landmark",
    "analyze_segmentation": "infer_segmentation",
    # ⚠️ D5 · İG-5.50: burada `None  # GPU tarafında ayrı uç YOK (gömülü-only)` yazıyordu — YANLIŞ ÖNCÜL: `/infer/thermal`
    # 065d607'den beri VAR ve `analyze_thermal` ona `_kapili_devret("thermal")` ile devrediyor. Termal ucu kapı dışındaydı
    # (GPU termal yanıtının görseli + oran alanları olmadığı ölçüldü; bkz. BILINEN_KAYIP). `None` artık YASAK
    # (test_KRITIK_delegasyon_kumesi_ESLEMEYLE_TAM).
    "analyze_thermal": "infer_thermal",
    "analyze_reticulocytes": "infer_reticulocytes",
    "analyze_kidney_ct": "infer_kidney_ct",
    "analyze_em_fantom": "infer_em_fantom",
    "analyze_em_petri": "infer_em_petri",
    "analyze_cat_organ": "infer_cat_organ",
}

#: Oran kilidi sözleşmesi — görsel döndüren HER uç bunları taşımalı.
ORAN_ALANLARI = {"image_w", "image_h"}

#: D5 · İG-5.50 — ÖLÇÜLMÜŞ, AÇIK parite kayıpları (gömülüde VAR, GPU yanıtında YOK). Bu bir İZİN listesi DEĞİL, CIRCIR:
#: `test_KRITIK_alan_paritesi_HER_gecis_delegasyonunda` kaybın bu listeye BİREBİR eşit olmasını ister — yeni kayıp KIRMIZI,
#: ürün düzeltilip kayıp kapanınca da KIRMIZI ("listeden çıkar"). Ürün kalemi: D1.86 / B-5.8 (GPU profili sahada kapalı).
#: `*ad` = gömülü yanıta `**ad(...)` ile yayılan alan grubu (GPU tarafında hiç yayılmıyor).
BILINEN_KAYIP = {
    "infer_thermal": {"image_base64", "image_w", "image_h"},  # B-5.8 "termal görseli": GPU termal panelinde görsel yok
    "infer_landmark": {"hw_status", "hw_params"},  # B-5.8 landmark auto_adjust/hw_status (A-19 ile birlikte)
    "infer_kidney_disease": {"filled_fields", "imputed_fields", "low_evidence", "total_fields"},  # B-5.8 CKD şeffaflık
    "infer_em_fantom": {"*_y51_duty_etiketi"},  # Y51 "eğitim aralığı dışı" etiketi GPU profilinde yok
    "infer_em_petri": {"*_y51_duty_etiketi"},  # Y51 aynı
}

#: GPU yanıtını AYNEN geçirmeyen, içinde TÜKETEN çağıranlar (AI Pro). Yeni bir iç tüketici buraya bilinçli eklenir.
IC_TUKETICILER = {"_localize_organ_gpu": "infer_cat_organ", "_predict_and_drive_gpu": "infer_em_kedi"}

_DELEGE_CAGRILARI = {"_kapili_devret", "delegate_infer", "delegate_json", "delegate_infer_sync", "delegate_json_sync"}


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
        yok = ORAN_ALANLARI - _yanit_alanlari(fn) - BILINEN_KAYIP.get(gpu, set())
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


# ============================================================================
# 4. D5 · İG-5.50 — TÜM DELEGASYONLAR ve ALAN DÜZEYİ (yalnız oran alanları değil)
# ============================================================================
# Eski kapının üç körlüğü (ölçüldü): termal ucu yanlış öncülle muaftı; 16 delegasyon çağrısının (15 GPU ucu) yalnız 7'si
# ölçülüyordu; alan düzeyinde yalnız `image_w`/`image_h` (+ cat_organ) bakılıyordu — GPU `infer_kidney_ct`ten
# `class_counts`, `infer_disease`ten `low_confidence`, `infer_thermal`dan `girdi_dogrulama` silinince kapı YEŞİLDİ.


def _ic_dugumler(fn: ast.AST):
    """`fn` gövdesinin düğümleri — iç içe def / lambda / class GÖVDELERİ hariç (onların `return`ü bu ucun yanıtı değil)."""
    yigin = list(fn.body)
    while yigin:
        d = yigin.pop()
        yield d
        for c in ast.iter_child_nodes(d):
            if not isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                yigin.append(c)


def _hata_yaniti_mi(cagri: ast.Call) -> bool:
    for kw in cagri.keywords:
        if kw.arg == "status_code" and not (isinstance(kw.value, ast.Constant) and int(kw.value.value) < 400):
            return True
    return False


def _donen_anahtar_yollari(fn: ast.AST) -> list[tuple[int, set[str]]]:
    """Ucun HER BAŞARILI `return` yolunun anahtarları (satır, küme) — `return`ten GERİYE çözülür (istek gövdesi / ara
    sözlükler SAYILMAZ).

    `return {...}`, `return JSONResponse({...})` (status_code < 400), `return yanit` (+ `yanit = {...}`, `yanit["k"] = …`,
    `yanit.update({...})`) ve `**ad` yayılımları (ad yerel sözlükse içi; oran üreticisiyse ORAN_ALANLARI; değilse `*ad`).
    Sabit olmayan anahtarla doldurulan yerel sözlük `*ad` (opak) olarak kalır.
    """
    dugumler = list(_ic_dugumler(fn))
    sozlukler: dict[str, list] = {}
    alt_anahtar: dict[str, set] = {}
    for d in dugumler:
        if isinstance(d, ast.Assign):
            for h in d.targets:
                if isinstance(h, ast.Name) and isinstance(d.value, ast.Dict):
                    sozlukler.setdefault(h.id, []).append(d.value)
                elif isinstance(h, ast.Subscript) and isinstance(h.value, ast.Name):
                    k = h.slice
                    alt_anahtar.setdefault(h.value.id, set()).add(
                        k.value if isinstance(k, ast.Constant) and isinstance(k.value, str) else f"*{h.value.id}"
                    )
        elif (
            isinstance(d, ast.Call)
            and isinstance(d.func, ast.Attribute)
            and d.func.attr == "update"
            and isinstance(d.func.value, ast.Name)
            and d.args
            and isinstance(d.args[0], ast.Dict)
        ):
            sozlukler.setdefault(d.func.value.id, []).append(d.args[0])

    def _sozluk(dd: ast.Dict, gorulen: frozenset) -> set:
        s: set = set()
        for k, v in zip(dd.keys, dd.values):
            if k is not None:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    s.add(k.value)
                continue
            if isinstance(v, ast.Name) and v.id in sozlukler and v.id not in gorulen:
                s |= _ad(v.id, gorulen | {v.id})
                continue
            ad = v.id if isinstance(v, ast.Name) else ""
            if isinstance(v, ast.Call):
                ad = v.func.id if isinstance(v.func, ast.Name) else getattr(v.func, "attr", "")
            if ad in ("_kare_boyutu", "_kare_olcusu", "_boyut", "_cat_boyut"):
                s |= ORAN_ALANLARI
            elif ad:
                s.add(f"*{ad}")
        return s

    def _ad(ad: str, gorulen: frozenset) -> set:
        s = set(alt_anahtar.get(ad, set()))
        for dd in sozlukler.get(ad, []):
            s |= _sozluk(dd, gorulen)
        return s

    yollar: list = []
    for d in sorted((x for x in dugumler if isinstance(x, ast.Return) and x.value is not None), key=lambda x: x.lineno):
        v = d.value
        if isinstance(v, ast.Call) and getattr(v.func, "id", "") == "JSONResponse" and not _hata_yaniti_mi(v):
            v = v.args[0] if v.args else next((kw.value for kw in v.keywords if kw.arg == "content"), None)
        if isinstance(v, ast.Dict):
            k = _sozluk(v, frozenset())
        elif isinstance(v, ast.Name):
            k = _ad(v.id, frozenset({v.id}))  # yerel sözlük değilse (ör. `return _red` = kapı reddi) boş küme
        else:
            continue
        if k:
            yollar.append((d.lineno, k))
    return yollar


def _donen_anahtarlar(fn: ast.AST) -> set[str]:
    """Ucun TÜM başarılı `return` yollarının anahtar BİRLEŞİMİ (gömülü taraf)."""
    sonuc: set = set()
    for _, k in _donen_anahtar_yollari(fn):
        sonuc |= k
    return sonuc


def _gpu_infer_uclari() -> dict:
    """ai_service/app.py: `@app.post("/infer/<ad>")` → fonksiyon düğümü (GET /infer/models çıkarım ucu değil)."""
    agac = ast.parse(io.open(SERVIS, encoding="utf-8", errors="replace").read())
    uclar = {}
    for fn in agac.body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dek in fn.decorator_list:
            if (
                isinstance(dek, ast.Call)
                and isinstance(dek.func, ast.Attribute)
                and dek.func.attr == "post"
                and dek.args
                and isinstance(dek.args[0], ast.Constant)
                and str(dek.args[0].value).startswith("/infer/")
            ):
                uclar[str(dek.args[0].value)[len("/infer/") :]] = fn
    return uclar


def _delegasyonlar() -> list[tuple[str, str]]:
    """ai_router.py'deki HER devretme çağrısı: (çağıran fonksiyon, GPU uç adı). İlk argüman sabit olmalı."""
    agac = ast.parse(io.open(ROUTER, encoding="utf-8", errors="replace").read())
    sonuc = []
    for fn in ast.walk(agac):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or fn.name == "_kapili_devret":
            continue
        for d in ast.walk(fn):
            if not isinstance(d, ast.Call):
                continue
            ad = d.func.id if isinstance(d.func, ast.Name) else getattr(d.func, "attr", "")
            if ad in _DELEGE_CAGRILARI:
                assert d.args and isinstance(d.args[0], ast.Constant), (
                    f"{fn.name}:{d.lineno} {ad}(...) uç adı SABİT değil -> parite kapısı hangi GPU ucuna gittiğini bilemez"
                )
                sonuc.append((fn.name, str(d.args[0].value)))
    return sonuc


def test_KRITIK_delegasyon_kumesi_ESLEMEYLE_TAM():
    """GPU'nun HER çıkarım ucu devrediliyor ve HER devretme ya geçiş eşlemesinde ya iç tüketicilerde; `None` eşleme YOK.

    MUTASYON: eşlemede termali yeniden `None` yapmak / app.py'ye yeni `/infer/x` eklemek / router'a eşlenmemiş yeni
    `_kapili_devret("x")` eklemek → KIRMIZI.
    """
    gpu = _gpu_infer_uclari()
    dl = _delegasyonlar()
    assert len(dl) >= 16, f"kurulum: {len(dl)} devretme çağrısı bulundu (HEAD 5bc99be1: 16) — çıpa kaymış olabilir"
    bos = sorted(k for k, v in UC_ESLEMESI.items() if v is None)
    assert not bos, f"eşlemede GPU karşılığı None olan uç(lar): {bos} -> kapı onları ÖLÇMÜYOR (İG-5.50 yanlış öncül)"
    devredilen = {ad for _, ad in dl}
    assert devredilen == set(gpu), (
        f"devredilen uçlar ↔ GPU /infer uçları AYRIŞIYOR: yalnız router'da {sorted(devredilen - set(gpu))}, "
        f"yalnız GPU'da {sorted(set(gpu) - devredilen)}"
    )
    eslenmemis = sorted(
        (cagiran, ad)
        for cagiran, ad in dl
        if not (cagiran.startswith("analyze_") or IC_TUKETICILER.get(cagiran) == f"infer_{ad}")
    )
    assert not eslenmemis, (
        f"geçiş ucu da iç tüketici de olmayan devretme(ler): {eslenmemis} -> IC_TUKETICILER'e bilinçli ekle"
    )
    for gomulu, gpu_ad in UC_ESLEMESI.items():
        assert (gomulu, gpu_ad[len("infer_") :]) in set(dl), (
            f"eşleme {gomulu}->{gpu_ad} router'daki devretmeyle UYUŞMUYOR"
        )


def test_KRITIK_alan_paritesi_HER_gecis_delegasyonunda():
    """Gömülü yanıttaki her alan GPU yanıtında da var — tek istisna ÖLÇÜLMÜŞ `BILINEN_KAYIP` (BİREBİR, iki yönlü cırcır).

    MUTASYON: GPU `infer_kidney_ct`ten `class_counts`, `infer_disease`ten `low_confidence`, `infer_thermal`dan
    `girdi_dogrulama` silmek → KIRMIZI; GPU termaline görsel eklemek (kayıp kapanır) → KIRMIZI ("listeden çıkar").
    """
    gpu = _gpu_infer_uclari()
    rfn = _fonksiyonlar(ROUTER)
    sapma = {}
    olculen = 0
    for cagiran, ad in _delegasyonlar():
        if not cagiran.startswith("analyze_"):
            continue
        gomulu = _donen_anahtarlar(rfn[cagiran])
        assert len(gomulu) >= 2, f"kurulum: {cagiran} başarılı yanıt anahtarları çözülemedi ({sorted(gomulu)})"
        yollar = _donen_anahtar_yollari(gpu[ad])
        assert yollar, f"kurulum: GPU infer_{ad} başarılı return yolu çözülemedi"
        beklenen = BILINEN_KAYIP.get(f"infer_{ad}", set())
        # GPU'nun HER başarılı yolu ayrı ölçülür (birleşim, alanı yalnız erken-dönüş yolunda taşıyan kaybı gizlerdi).
        for satir, gpu_alan in yollar:
            kayip = gomulu - gpu_alan
            if kayip != beklenen:
                sapma[f"{cagiran}->infer_{ad}@app.py:{satir}"] = {
                    "YENI_KAYIP": sorted(kayip - beklenen),
                    "KAPANDI_listeden_cikar": sorted(beklenen - kayip),
                }
        olculen += 1
    assert olculen >= 14, f"kurulum: yalnız {olculen} geçiş delegasyonu ölçüldü (HEAD: 14)"
    assert not sapma, (
        f"gömülü ↔ GPU alan paritesi SAPTI: {sapma} -> ai_client JSON'u aynen geçirdiği için YENI_KAYIP alanlar GPU "
        "dağıtımında SESSİZCE kaybolur; KAPANDI olanı BILINEN_KAYIP'tan sil"
    )


def test_KRITIK_ic_tuketici_okudugu_alanlar_GPU_yanitinda():
    """`_localize_organ_gpu` GPU cat_organ yanıtından SABİT adla okuduğu her alanı orada bulmalı (yoksa `.get` None → sessiz
    "organ yok"). MUTASYON: GPU `infer_cat_organ`dan `pose_type` / `kabin_uyarisi` silmek → KIRMIZI.
    ⚠️ DÜRÜST SINIR: `_predict_and_drive_gpu` `D{i}`/`P{i}`/`result_E`yi GPU'nun OPAK `**out` yayılımından okur (model çıktısı);
    alan adları AST'den doğrulanamaz — davranış kapısı `tests/test_ai_servis_8100_kapisi.py`.
    """
    rfn = _fonksiyonlar(ROUTER)
    okunan = set()
    for d in ast.walk(rfn["_localize_organ_gpu"]):
        if (
            isinstance(d, ast.Call)
            and isinstance(d.func, ast.Attribute)
            and d.func.attr == "get"
            and isinstance(d.func.value, ast.Name)
            and d.func.value.id == "resp"
            and d.args
            and isinstance(d.args[0], ast.Constant)
        ):
            okunan.add(d.args[0].value)
    assert {"organs", "image_base64", "kabin_uyarisi", "pose_type"} <= okunan, (
        f"kurulum: okunan alanlar çözülemedi {okunan}"
    )
    eksik = okunan - _donen_anahtarlar(_gpu_infer_uclari()["cat_organ"])
    assert not eksik, f"AI Pro GPU yolu cat_organ yanıtından {sorted(eksik)} okuyor ama GPU ucu DÖNMÜYOR (sessiz None)"
