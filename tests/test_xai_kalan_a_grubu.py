# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""XAI §KALAN A-GRUBU — backend davranış kilitleri (docs/xai-entegrasyon-plani.md §KALAN-2026-08-26).

A4: landmark yanıtı `fgs_bantlari` taşır (thresholds_calibrated.json p5/p95 — UI
    'ölçülen değer vs popülasyon bandı' paneli buradan çizilir; dosya yoksa boş dict → panel gizli).
A5: em_fantom/em_petri modülleri em_kedi ile AYNI hafif canlı-sensitivity sarmalayıcısını taşır
    (7+1 forward, PNG/SHAP yok) ve router yanıt meta'sına bağlıdır.
A6: termal/ses uçlarında CAM yöntemi dışa açıldı — allowlist DIŞI değer 422 (sessiz düşüş değil).
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]

_BEKLENEN_OLCUMLER = {
    "ear_angle",
    "ear_elev",
    "ear_spread",
    "eye_ratio_avg",
    "mouth_aspect",
    "muzzle_compact",
    "whisker_tension",
    "head_center_y",
}


# ── A4: fgs bantları ─────────────────────────────────────────────────────────
def test_KRITIK_fgs_bantlari_yukleniyor_ve_GECERLI():
    import servers.ai_router as air

    air._FGS_BANTLARI_CACHE = None  # modül-cache'i sıfırla → gerçek dosyadan yüklensin
    bant = air._fgs_bantlari()
    assert set(bant) == _BEKLENEN_OLCUMLER, f"bant anahtarları kalibrasyonla uyuşmuyor: {sorted(bant)}"
    for ad, b in bant.items():
        assert set(b) == {"p5", "p95"}, f"{ad}: fazla/eksik alan sızdı (UI sözleşmesi p5/p95): {b}"
        assert b["p5"] < b["p95"], f"{ad}: p5 >= p95 ({b}) — bant dejenere"
    # cache davranışı: ikinci çağrı AYNI nesneyi döndürür (her istekte disk okunmaz)
    assert air._fgs_bantlari() is bant


def test_KARSIT_KANIT_dosya_yokken_bos_dict_ZARIF(monkeypatch):
    """Kalibrasyon dosyası okunamazsa panel GİZLENİR (boş dict) — landmark yanıtı DÜŞMEZ."""
    import servers.ai_router as air

    monkeypatch.setattr(air, "_FGS_BANTLARI_CACHE", None)
    monkeypatch.setattr(air, "project_root", str(KOK / "OLMAYAN_DIZIN"))
    assert air._fgs_bantlari() == {}
    air._FGS_BANTLARI_CACHE = None  # sonraki testler gerçek dosyayı görsün


# ── D5.57 (B-10.172 · B-10.173) AST yardımcıları: yanıt sözlüğü anahtarları / `**` yayılımları / zarif XAI try'ı ──────────
# Eski yapısal kapılar çıpayı YORUMLAR DAHİL ham metinde arıyordu: yanıt sözlüğündeki alan satırı `# ` ile yoruma alınınca dördü de
# YEŞİL kalıyordu (ölçüldü, HEAD d38b0db5: router landmark `"fgs_bantlari"` satırı yoruma → 219 passed). AST yorumu görmez.
def _sozlukler(dugum) -> list:
    return [d for d in ast.walk(dugum) if isinstance(d, ast.Dict)]


def _anahtarlar(sozluk: ast.Dict) -> dict:
    """Sözlük sabitinin dizge anahtarları → değer düğümü (yalnız KOD; yorumdaki satır sayılmaz)."""
    return {
        k.value: v
        for k, v in zip(sozluk.keys, sozluk.values)
        if isinstance(k, ast.Constant) and isinstance(k.value, str)
    }


def _yayilanlar(sozluk: ast.Dict) -> set:
    """`{**ad, ...}` yayılımlarının adları."""
    return {v.id for k, v in zip(sozluk.keys, sozluk.values) if k is None and isinstance(v, ast.Name)}


def _cagri_adi(dugum) -> str | None:
    if isinstance(dugum, ast.Call):
        f = dugum.func
        return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
    return None


def _fonksiyon_dugumu(src: str, karakter_ofseti: int):
    """`karakter_ofseti`ni İÇEREN en içteki fonksiyonun AST düğümü."""
    satir = src.count("\n", 0, karakter_ofseti) + 1
    en_iyi = None
    for d in ast.walk(ast.parse(src)):
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.lineno <= satir <= d.end_lineno:
            if en_iyi is None or d.lineno > en_iyi.lineno:
                en_iyi = d
    assert en_iyi is not None, f"satır {satir} hiçbir fonksiyonda değil"
    return en_iyi


def _zarif_xai_denemesi(fn, etiket: str) -> None:
    """B-10.173: `xai_hizli_sensitivity` çağrısını saran EN İÇTEKİ try'ın yakalayıcısı `Exception` (daraltılmamış) ve uyarısı
    "analiz etkilenmedi" der. Eskiden ±800 karakterlik pencerede `"except Exception"` aranıyordu — komşu bir uç / blok pencereye
    girince iç except `ValueError`a daraltılsa da YEŞİLDİ (DENETİM-10 ölçümü; HEAD'de konum şans eseri tutuyor)."""
    denemeler = [
        t
        for t in ast.walk(fn)
        if isinstance(t, ast.Try)
        and any(isinstance(n, ast.Attribute) and n.attr == "xai_hizli_sensitivity" for b in t.body for n in ast.walk(b))
    ]
    assert denemeler, f"{etiket}: XAI meta çağrısı bir try İÇİNDE DEĞİL — açıklama hatası analizi düşürür"
    ic = min(denemeler, key=lambda t: t.end_lineno - t.lineno)
    turler = [ast.unparse(h.type) if h.type is not None else "<çıplak>" for h in ic.handlers]
    assert any(isinstance(h.type, ast.Name) and h.type.id == "Exception" for h in ic.handlers), (
        f"{etiket}: XAI meta except'i daraltılmış ({turler}) — başka bir istisna analizi düşürür"
    )
    uyari = [
        c
        for h in ic.handlers
        for c in ast.walk(h)
        if _cagri_adi(c) == "warning"
        and c.args
        and isinstance(c.args[0], ast.Constant)
        and "analiz etkilenmedi" in str(c.args[0].value)
    ]
    assert uyari, f"{etiket}: XAI meta hatası uyarısız ya da 'analiz etkilenmedi' demiyor"
    # TUR 2 (çürütücü ea / eb): `Exception` yakalayıcısının VARLIĞI yetmiyordu — (ea) yakalayıcı uyarı + xai_error yazıp YİNE `raise`
    # ediyor (analiz 500) ve (eb) `Exception`dan ÖNCE `except RuntimeError: raise` geliyor (some ↔ every) → geniş kümede 320 passed.
    # Artık HER yakalayıcı zarif: içinde `raise` / `return` YOK, "analiz etkilenmedi" uyarısı VAR ve `_xai_meta["xai_error"]` yazar.
    for h in ic.handlers:
        tur = ast.unparse(h.type) if h.type is not None else "<çıplak>"
        kacis = sorted({type(n).__name__ for n in ast.walk(h) if isinstance(n, (ast.Raise, ast.Return))})
        assert not kacis, (
            f"{etiket}: XAI meta yakalayıcısı `except {tur}` hatayı ANALİZE taşıyor ({kacis}) — açıklama hatası analizi düşürür"
        )
        assert any(
            _cagri_adi(c) == "warning"
            and c.args
            and isinstance(c.args[0], ast.Constant)
            and "analiz etkilenmedi" in str(c.args[0].value)
            for c in ast.walk(h)
        ), f"{etiket}: `except {tur}` yakalayıcısı uyarısız / 'analiz etkilenmedi' demiyor (sessiz yutma)"
        assert any(
            isinstance(a, ast.Assign)
            and any(
                isinstance(t, ast.Subscript)
                and isinstance(t.value, ast.Name)
                and t.value.id == "_xai_meta"
                and isinstance(t.slice, ast.Constant)
                and t.slice.value == "xai_error"
                for t in a.targets
            )
            for a in ast.walk(h)
        ), f"{etiket}: `except {tur}` yakalayıcısı yanıta `xai_error` yazmıyor (D5.05 sözleşmesi)"


def _donus_sozlukleri(fn) -> list:
    """Ucun YANIT sözlükleri: `return {…}` ya da `return JSONResponse({…})` / `JSONResponse(content={…})` ile DÖNEN ve `"status"`
    anahtarı taşıyan sözlük sabitleri (hata gövdeleri — `{"error": …}` — ve ara sözlükler, ör. `hw_params = {…}`, SAYILMAZ)."""
    sozlukler = []
    for d in ast.walk(fn):
        if not isinstance(d, ast.Return) or d.value is None:
            continue
        v = d.value
        if isinstance(v, ast.Call) and _cagri_adi(v) == "JSONResponse":
            adaylar = list(v.args[:1]) + [k.value for k in v.keywords if k.arg == "content"]
        else:
            adaylar = [v]
        sozlukler += [s for s in adaylar if isinstance(s, ast.Dict) and "status" in _anahtarlar(s)]
    return sozlukler


def test_YAPISAL_landmark_yaniti_bantlari_tasir():
    """Çıpa GERÇEK çağrıya pinli (yapısal-çıpa kırılganlığı dersi): landmark JSONResponse
    gövdesi `fgs_bantlari` alanını _fgs_bantlari() ÇAĞRISIYLA doldurur.

    ⚠️ D5.57 (B-10.172): eskiden `'"fgs_bantlari": _fgs_bantlari(),' in src` + 600 karakterlik pencere — satır `# ` ile yoruma alınınca
    YEŞİLDİ. Artık AST: KODDAKİ bir yanıt sözlüğünde `"fgs_bantlari"` anahtarının değeri `_fgs_bantlari()` çağrısı ve AYNI sözlükte
    `"fgs_total"` var.
    ⚠️ TUR 2 (çürütücü dc): "dosyadaki HERHANGİ bir sözlük" kabul ediliyordu — alan yanıttan silinip `hw_params = {"fgs_total": …,
    "fgs_bantlari": _fgs_bantlari()}` iç sözlüğüne taşınınca YEŞİLDİ. Artık YALNIZ `/api/ai/vision/landmark` ucunun DÖNDÜRDÜĞÜ
    (`return JSONResponse(content={…})`) sözlük. Değer akışı: `test_KRITIK_D557_landmark_yaniti_FGS_alanlarini_UST_DUZEYDE_tasir`."""
    src = (KOK / "apps/backend/servers/ai_router.py").read_text(encoding="utf-8")
    donus = _donus_sozlukleri(_uc_dugumu(src, "/api/ai/vision/landmark"))
    assert donus, "aparat: landmark ucunun yanıt sözlüğü bulunamadı (çıpa kaymış)"
    for s in donus:
        a = _anahtarlar(s)
        assert _cagri_adi(a.get("fgs_bantlari")) == "_fgs_bantlari", (
            "landmark YANITI bant alanını kaybetti (A4 regresyonu) — dönen sözlükte `\"fgs_bantlari\": _fgs_bantlari()` yok: "
            f"{sorted(a)}"
        )
        assert "fgs_total" in a, "bant alanı landmark yanıt gövdesinden ayrı düşmüş"


# ── A5: em_fantom/em_petri hafif sensitivity paritesi ────────────────────────
class _Identity:
    def inverse_transform(self, y):
        return np.asarray(y, dtype=np.float64)


def _sahte_em_predictor(n_out=22):
    """test_em_xai_entegrasyon ile aynı sözleşme: duty_sum→D-kanallarına mühendislenmiş güçlü etki."""
    rng = np.random.default_rng(9)
    W = rng.normal(size=(6, n_out)) * 0.001
    W[5, :7] = 5.0

    p = SimpleNamespace(sy=_Identity())
    p._build_input = lambda x, y, z, o, B, d: np.column_stack(
        [np.atleast_1d(x), np.atleast_1d(y), np.atleast_1d(z), np.atleast_1d(o), np.atleast_1d(B), np.atleast_1d(d)]
    ).astype(np.float32)
    p._run_onnx = lambda X: (np.asarray(X, dtype=np.float64) @ W).astype(np.float32)
    return p


@pytest.mark.parametrize(
    "modul_yolu",
    [
        "ai_hub.inference_em_fantom.inference_em_fantom",
        "ai_hub.inference_em_petri.inference_em_petri",
    ],
)
def test_KRITIK_em_modul_hizli_sensitivity_ANLAMLI(modul_yolu):
    import importlib

    m = importlib.import_module(modul_yolu)
    p = _sahte_em_predictor()
    a = m.xai_hizli_sensitivity(p, 10.0, 20.0, 5.0, 1, 0.001, 2.0)
    b = m.xai_hizli_sensitivity(p, 10.0, 20.0, 5.0, 1, 0.001, 2.0)
    assert a == b, f"{modul_yolu}: aynı girdiye farklı açıklama (deterministik değil)"
    # AI1.X6: liste = belirleyenler + (eğitim aralığı dışı / öğrenilmemiş) işaret öğeleri — "belirleyen"ler süzülür
    belirleyen = [t for t in a if not t.get("ogrenilmemis") and t.get("surukleyen", True)]
    assert len(belirleyen) == 3 and all({"feature", "etki"} <= set(t) for t in belirleyen)
    assert belirleyen[0]["feature"] == "duty_sum", f"{modul_yolu}: mühendislenmiş sinyal top-1 değil: {a!r}"
    assert all(t["etki"] > 0 for t in belirleyen), f"{modul_yolu}: sensitivity ~0 (ref-stats bağlanmamış olabilir)"


def _uc_dugumu(src: str, yol: str):
    """Route dekoratörünün ilk argümanı `yol` olan fonksiyonun AST düğümü.

    ⚠️ `src[i : i + 4000]` karakter penceresinin yerine geçer (ADIM 2 ve ADIM 3'te, 2026-09-11, pencere ucun yanıt sözlüğüne yorum
    eklenince aranan alanı dışarıda bırakıp SAHTE KIRMIZI verdi). ⚠️ D5.57 (B-10.172): eski `_uc_govdesi` / `_fonksiyon_govdesi`
    gövdeyi METİN döndürüyordu → yoruma alınmış alan satırı da "var" sayılıyordu; artık düğüm döner, alanlar `_anahtarlar` /
    `_yayilanlar` ile KODDAN okunur. Dekoratör çağrısının argümanı karşılaştırılır (yorum / docstring'deki yol sayılmaz).
    """
    for d in ast.walk(ast.parse(src)):
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dek in d.decorator_list:
                if isinstance(dek, ast.Call) and dek.args and getattr(dek.args[0], "value", None) == yol:
                    return d
    raise AssertionError(f"{yol} rotasini tasiyan fonksiyon BULUNAMADI (uc silinmis olabilir)")


def test_YAPISAL_router_fantom_ve_petri_meta_bagli():
    """Gerçek çağrıya pinli: iki uç da xaiSensitivity'yi to_thread ile üretir ve
    hata analizi DÜŞÜRMEZ (except + warning)."""
    # ⚠️ çıpa TEK satıra pinli DEĞİL: ruff-format çağrıyı çok-satıra kırabiliyor (ölçüldü)
    # — yapısal-çıpa kırılganlığı dersi. Fonksiyon-adı çıpası + pencere-içi parça kontrolü.
    src = (KOK / "apps/backend/servers/ai_router.py").read_text(encoding="utf-8")
    for modul, cagri in [
        ("em_fantom", "_ief.xai_hizli_sensitivity,"),
        ("em_petri", "_iep.xai_hizli_sensitivity,"),
    ]:
        assert cagri in src, f"{modul}: router meta çağrısı kayıp (A5 regresyonu)"
        i = src.index(cagri)
        # pencere ±800: ruff-format çok-satıra kırınca ±400 "analiz etkilenmedi"yi
        # pencere dışında bırakıyordu (ölçüldü — sahte kırmızı)
        blok = src[max(0, i - 800) : i + 800]
        assert 'cache["predictor"]' in blok, f"{modul}: sensitivity önbellekli predictor'la çağrılmıyor"
        # D5.57 (B-10.173): ±800 penceresinde "except Exception" aramak konuma bağlıydı → AST (en içteki try'ın yakalayıcısı).
        fn = _fonksiyon_dugumu(src, i)
        _zarif_xai_denemesi(fn, modul)
        assert "asyncio.to_thread" in blok, f"{modul}: sensitivity event-loop üstünde koşuyor (bloklar)"
        # WIRING kilidi (düşman-doğrulama 2026-08-27: **_xai_meta silinince eski test yeşil
        # kalıyordu): meta gerçekten YANITA yayılıyor mu?
        #
        # ⚠️ KARAKTER PENCERESİ TERK EDİLDİ (2026-09-11): çıpa `src[i : i + 1600]` idi ve
        # ADIM 2'de yanıt sözlüğüne üç satırlık bir yorum + `**_boyut,` eklenince
        # `**_xai_meta,` pencerenin DIŞINA taştı → SAHTE KIRMIZI. Pencereyi büyütmek aynı
        # kırılmayı yalnız erteler (bu depoda "yapısal çıpa kırılganlığı" olarak kayıtlı).
        # Artık çıpa AST'ye pinli: meta'nın ÜRETİLDİĞİ fonksiyonun KENDİ gövdesinde
        # `**_xai_meta` yayılımı aranır — araya kaç satır girdiği ÖNEMSİZ.
        # ⚠️ D5.57 (B-10.172): fonksiyon gövdesi METİN olarak aranıyordu → `# **_xai_meta,` (yorum) da sayılıyordu. Artık
        # KODDAKİ bir sözlük sabitinde `**_xai_meta` yayılımı (AST).
        assert any("_xai_meta" in _yayilanlar(s) for s in _sozlukler(fn)), (
            f"{modul}: _xai_meta üretiliyor ama YANITA yayılmıyor"
        )
        # Baz-nokta kilidi: açıklama tahminin FİİLEN kullandığı noktada (None → cfg.phantom
        # default'ları; 'or 0.0' yanlış noktada açıklama üretiyordu — 8/8 noktada top-3 farklıydı)
        assert 'cache["cfg"].phantom.achieved_B' in blok, f"{modul}: XAI baz-noktası cfg ikamesiz"
        assert "achieved_B or 0.0" not in blok, f"{modul}: 'or 0.0' baz-nokta hatası geri geldi"


def test_YAPISAL_ai_service_fantom_ve_petri_meta_PARITESI():
    """Kapı-paritesi: :8100 devrindeyken de aynı meta dönmeli — app.py iki EM ucu da
    xai_hizli_sensitivity'yi zarif (except + warning) bağlar."""
    src = (KOK / "ai_service/app.py").read_text(encoding="utf-8")
    for modul, cagri in [
        ("em_fantom", "_ief.xai_hizli_sensitivity("),
        ("em_petri", "_iep.xai_hizli_sensitivity("),
    ]:
        assert cagri in src, f"ai_service {modul}: xaiSensitivity paritesi kayıp (router dönerken :8100 dönmez)"
        i = src.index(cagri)
        blok = src[max(0, i - 800) : i + 800]
        # D5.57 (B-10.173): pencere yerine AST — en içteki try'ın yakalayıcısı `Exception` + "analiz etkilenmedi" uyarısı.
        fn = _fonksiyon_dugumu(src, i)
        _zarif_xai_denemesi(fn, f"ai_service {modul}")
        # ⚠️ KARAKTER PENCERESİ TERK EDİLDİ (2026-09-12): çıpa `src[i : i + 1600]` idi ve
        # ADIM 3'te yanıt sözlüğüne `"paneller"` + dört satırlık gerekçe yorumu eklenince
        # `**_xai_meta,` pencerenin DIŞINA taştı → SAHTE KIRMIZI. (Aynı kırılma ADIM 2'de
        # router tarafında yaşanmış ve orada AST'ye pinlenmişti; bu ikizi atlanmış.)
        # ⚠️ D5.57 (B-10.172): gövde METNİ yerine KODDAKİ sözlükte `**_xai_meta` yayılımı (yorum sayılmaz).
        assert any("_xai_meta" in _yayilanlar(s) for s in _sozlukler(fn)), (
            f"ai_service {modul}: _xai_meta üretiliyor ama YANITA yayılmıyor"
        )
        assert 'c["cfg"].phantom.achieved_B' in blok, f"ai_service {modul}: XAI baz-noktası cfg ikamesiz"
        assert "achieved_B or 0.0" not in blok, f"ai_service {modul}: 'or 0.0' baz-nokta hatası geri geldi"


# ── Kapı-paritesi (düşman-doğrulama 2026-08-27): landmark + cat_organ GPU yolu ──
def test_KRITIK_fgs_bantlari_TEK_KAYNAK_paritesi():
    """Kanonik modül fonksiyonu (ai_service bunu kullanır) router'ın döndürdüğüyle BİREBİR
    aynı olmalı — ayrışırsa GPU ve gömülü profil farklı bant gösterir."""
    import servers.ai_router as air

    from ai_hub.cat_landmark.inference_cat_landmark import fgs_bantlari

    air._FGS_BANTLARI_CACHE = None
    assert fgs_bantlari() == air._fgs_bantlari(), "modül bantları ile router bantları ayrıştı"
    assert set(fgs_bantlari()) == _BEKLENEN_OLCUMLER


def test_YAPISAL_ai_service_landmark_ve_cat_organ_PARITESI():
    """GPU mikroservis yanıtları A2/A4 alanlarını taşımalı (düşman-doğrulama: taşımıyordu —
    rozetler + ölçüm-band paneli GPU dağıtımında sessizce ölüydü)."""
    src = (KOK / "ai_service/app.py").read_text(encoding="utf-8")

    # ⚠️ Çıpa AST'ye pinli: `src[i : i + 4000]` karakter penceresi, ucun gövdesine yorum ya da
    # yeni alan girdiğinde aranan alanı dışarıda bırakır (ADIM 2 ve ADIM 3'te iki kez ölçüldü).
    # ⚠️ D5.57 (B-10.172): uç gövdesi METİN olarak aranıyordu → yoruma alınmış `# "fgs_bantlari": …` satırı da sayılıyordu.
    # Artık ucun KODUNDAKİ sözlük sabitlerinin anahtarları (AST; yorum görünmez).
    # ⚠️ TUR 2 (çürütücü de): ucun TÜM sözlüklerinin anahtarları BİRLEŞTİRİLİYORDU — `raw_fgs` ana yanıttan silinip 400 hata
    # gövdesine taşınınca YEŞİLDİ. Artık ucun DÖNDÜRDÜĞÜ her YANIT sözlüğü (`"status"` taşıyan `return {…}`) alanları TEK TEK taşır.
    def _yanit_sozlukleri(yol: str) -> list:
        donus = [_anahtarlar(s) for s in _donus_sozlukleri(_uc_dugumu(src, yol))]
        assert donus, f"aparat: ai_service {yol} yanıt sözlüğü bulunamadı (çıpa kaymış)"
        return donus

    for anahtar in _yanit_sozlukleri("/infer/landmark"):
        for alan in ("fgs_bantlari", "raw_fgs", "action_units"):
            assert alan in anahtar, f"ai_service landmark yanıtı {alan!r} taşımıyor (A4 GPU'da ölü): {sorted(anahtar)}"
        assert _cagri_adi(anahtar["fgs_bantlari"]) == "_fgs_bantlari_tek", (
            "ai_service landmark bantları TEK-KAYNAK modülden değil"
        )
    for anahtar in _yanit_sozlukleri("/infer/cat_organ"):
        for alan in ("mirror_warning", "anatomic_consistency"):
            assert alan in anahtar, f"ai_service cat_organ yanıtı {alan!r} taşımıyor (A2 GPU'da ölü): {sorted(anahtar)}"


class _Dizi:
    """torch tensörü taklidi — landmark uçlarının okuduğu yüzey: `[i]`, `len()`, `.cpu()`, `.numpy()`."""

    def __init__(self, a):
        self._a = np.asarray(a, dtype=np.float32)

    def __getitem__(self, i):
        return _Dizi(self._a[i])

    def __len__(self):
        return len(self._a)

    def cpu(self):
        return self

    def numpy(self):
        return self._a


def _sahte_poz_modeli(kp_piksel: np.ndarray, kutu: list):
    """YOLO-pose sonucu taklidi: tek kedi yüzü, 48 nokta (piksel), nokta güveni YOK (sevk edilen modelle aynı)."""
    sonuc = SimpleNamespace(
        keypoints=SimpleNamespace(xy=_Dizi([kp_piksel]), conf=None),
        boxes=[SimpleNamespace(xyxy=_Dizi([kutu]))],
    )
    return SimpleNamespace(predict=lambda *a, **k: [sonuc])


def _renkli_jpg() -> bytes:
    import cv2

    ok, buf = cv2.imencode(".jpg", (np.random.default_rng(57).random((96, 96, 3)) * 255).astype(np.uint8))
    assert ok, "aparat: JPEG kodlanamadı"
    return buf.tobytes()


@pytest.mark.parametrize("profil", ["gomulu", "servis"])
def test_KRITIK_D557_landmark_yaniti_FGS_alanlarini_UST_DUZEYDE_tasir(profil, monkeypatch):
    """TUR 2 (çürütücü dc / de) — DAVRANIŞ: GERÇEK landmark ucu (gömülü `/api/ai/vision/landmark` ve :8100 `/infer/landmark`;
    süreç içi TestClient, port YOK) + sahte YOLO-pose sonucu (48 nokta, tohumlu). Yanıtın ÜST DÜZEYİNDE: `detected` true,
    `fgs_total` = Σ eylem birimi = `raw_fgs.fgs_total` (ürünün `compute_fgs`i ile AYNI girdi → aynı sonuç), `action_units` =
    `raw_fgs.action_units`, `fgs_bantlari` TEK-KAYNAK bantlar (8 ölçüm, p5/p95). MUTASYON: bantlar `hw_params` iç sözlüğüne (dc) /
    `raw_fgs` hata gövdesine (de) taşınır, değer `{}` olur → KIRMIZI."""
    from ai_hub.cat_landmark.inference_cat_landmark import compute_fgs, fgs_bantlari

    kutu = [10.0, 20.0, 110.0, 120.0]
    kp_norm = np.random.default_rng(557).random((48, 2)).astype(np.float32)
    kp_piksel = kp_norm * np.array([100.0, 100.0], dtype=np.float32) + np.array([10.0, 20.0], dtype=np.float32)
    beklenen = compute_fgs((kp_piksel - np.array([10.0, 20.0], dtype=np.float32)) / 100.0)
    assert beklenen["fgs_total"] >= 0, (
        "48 noktalı tohumlu girdide compute_fgs skor üretmiyor (-1) — landmark ucu hiçbir yüzü tespit edemez"
    )
    model = _sahte_poz_modeli(kp_piksel, kutu)
    jpg = _renkli_jpg()
    if profil == "gomulu":
        import servers.ai_router as air
        import servers.api_server as apis
        from utils import image_domain

        monkeypatch.setattr(air, "ai_service_enabled", lambda: False)
        monkeypatch.setattr(air, "_get_or_load_model", lambda ad, yukleyici: model)
        monkeypatch.setattr(image_domain, "check", lambda *a, **k: None)  # modalite kapısı bu kapının konusu değil
        import base64

        r = TestClient(apis.app).post("/api/ai/vision/landmark", data={"image_base64": base64.b64encode(jpg).decode()})
        bant_beklenen = air._fgs_bantlari()
    else:
        import ai_service.app as sapp

        monkeypatch.setattr(sapp, "_kapi", lambda *a, **k: None)
        monkeypatch.setattr(sapp.predictors, "get", lambda ad: model)
        r = TestClient(sapp.app).post("/infer/landmark", files={"file": ("y.jpg", jpg, "image/jpeg")})
        bant_beklenen = fgs_bantlari()
    assert r.status_code == 200, f"{profil}: landmark ucu {r.status_code}: {r.text[:200]}"
    j = r.json()
    assert j.get("detected") is True, f"{profil}: aparat — sahte yüz tespit sayılmadı: {sorted(j)}"
    eksik = [a for a in ("fgs_total", "raw_fgs", "action_units", "fgs_bantlari") if a not in j]
    assert not eksik, f"{profil}: landmark YANITI üst düzeyde {eksik} taşımıyor (A2 / A4 alanı düştü): {sorted(j)}"
    assert set(bant_beklenen) == _BEKLENEN_OLCUMLER and j["fgs_bantlari"] == bant_beklenen, (
        f"{profil}: yanıttaki bantlar TEK-KAYNAK bantlar değil: {sorted(j['fgs_bantlari'] or {})}"
    )
    puanlar = [au["score"] for au in (j["action_units"] or {}).values()]
    assert j["fgs_total"] == beklenen["fgs_total"] == sum(puanlar), (
        f"{profil}: fgs_total {j['fgs_total']!r} ≠ compute_fgs {beklenen['fgs_total']!r} / Σ AU {sum(puanlar)}"
    )
    assert (j["raw_fgs"] or {}).get("fgs_total") == j["fgs_total"], (
        f"{profil}: raw_fgs yanıtla çelişiyor: {j['raw_fgs']!r}"
    )
    assert j["action_units"] == (j["raw_fgs"] or {}).get("action_units"), (
        f"{profil}: action_units raw_fgs ile çelişiyor"
    )


def test_KRITIK_ai_service_termal_ses_allowlist_422():
    """A6 GERÇEK paritesi: :8100'e doğrudan geçersiz CAM yöntemi 422 almalı (eskiden zarif
    düşüşe yutuluyordu — çağıran yazım hatasını asla öğrenemiyordu)."""
    from ai_service.app import app as svc_app

    svc = TestClient(svc_app)
    for uc in ("/infer/thermal", "/infer/sound"):
        r = svc.post(uc, files={"file": ("x.bin", b"0" * 400)}, data={"xai_method": "grad-cam"})
        assert r.status_code == 422 and "xai_method" in r.text, f"{uc}: {r.status_code} {r.text[:120]}"
        # KARŞIT: geçerli yöntem allowlist'e TAKILMAZ (girdi-kapısı vs. farklı hata dönebilir)
        r = svc.post(uc, files={"file": ("x.bin", b"0" * 400)}, data={"xai_method": "eigencam"})
        assert not (r.status_code == 422 and "xai_method" in r.text), f"{uc}: geçerli yöntem reddedildi"


def test_KRITIK_batch_xai_SHAP_duty_agregasyonuyla():
    """A7 wiring (düşman-doğrulama: varyant hiçbir üretim yolunda çağrılmıyordu): Mod-2
    batch_xai SHAP'ı D1-D7 duty-agregasyonuyla istemeli."""
    import ai_hub.xai_tabular.em_runtime as rt

    yakalanan = {}

    def _sahte_run(*a, **k):
        yakalanan.update(k)
        return {"sensitivity": None, "shap_values": None, "out_dir": "x"}

    orijinal = rt.run_em_xai
    rt.run_em_xai = _sahte_run
    try:
        rt.batch_xai(object(), {"std": np.ones(6), "background": np.zeros((4, 6))}, np.zeros((2, 6)), "cikti")
    finally:
        rt.run_em_xai = orijinal
    assert yakalanan.get("shap_output_agg") == "duty", (
        f"batch_xai SHAP agregasyonu duty değil: {yakalanan.get('shap_output_agg')!r}"
    )


# ── A7: shap_kernel_em output_agg='duty' ─────────────────────────────────────
def test_KRITIK_shap_duty_agregasyonu_D_kanallarina_ODAKLANIR():
    """Mühendislenmiş model: duty_sum YALNIZ D(7) kanallarını, y YALNIZ faz/E (16) kanallarını
    sürer. 'duty' agregasyonu duty_sum'u top-1 yapmalı; 'mean' ise faz-sürücü y'yi öne çıkarır
    (karşıt-kanıt: varyant gerçekten farklı soruyu yanıtlıyor)."""
    from ai_hub.xai_tabular.em_sensitivity import shap_kernel_em

    W = np.zeros((6, 23))  # EM çıktı yerleşimi: D(7)+sinP(7)+cosP(7)+E(2)
    W[5, :7] = 5.0  # duty_sum → yalnız D-kanalları
    W[1, 7:] = 5.0  # y → yalnız faz+E kanalları
    fn = lambda X: np.asarray(X, dtype=np.float64) @ W  # noqa: E731

    rng = np.random.default_rng(3)
    bg = rng.normal(size=(24, 6))
    X = np.array([[0.5, 1.5, -0.3, 1.0, 0.8, 2.0]])

    sv_duty = np.abs(shap_kernel_em(fn, X, n_kernel_samples=64, output_agg="duty", background=bg))[0]
    sv_mean = np.abs(shap_kernel_em(fn, X, n_kernel_samples=64, output_agg="mean", background=bg))[0]

    assert int(np.argmax(sv_duty)) == 5, f"'duty' agregasyonu duty_sum'u top-1 yapmadı: {sv_duty}"
    assert sv_duty[1] < 0.05 * sv_duty[5], "faz-sürücü y 'duty' görünümüne sızdı"
    assert int(np.argmax(sv_mean)) == 1, f"karşıt-kanıt bozuldu: 'mean' görünümü y'yi öne çıkarmalıydı: {sv_mean}"


def test_KARSIT_KANIT_gecersiz_output_agg_ACIK_hata():
    from ai_hub.xai_tabular.em_sensitivity import shap_kernel_em

    with pytest.raises(ValueError, match="output_agg"):
        shap_kernel_em(lambda X: X, np.zeros((1, 6)), output_agg="hepsi", background=np.zeros((4, 6)))


# ── A6: termal/ses xai_method allowlist ──────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    import servers.api_server as apis

    return TestClient(apis.app)


@pytest.mark.parametrize("uc", ["/api/ai/vision/thermal", "/api/ai/sound/cat"])
def test_KRITIK_gecersiz_xai_method_422(client, uc):
    r = client.post(uc, data={"xai_method": "shap_deep"})  # allowlist dışı
    assert r.status_code == 422, f"{uc}: geçersiz CAM yöntemi sessizce yutuldu ({r.status_code})"
    assert "xai_method" in r.text, r.text


@pytest.mark.parametrize("uc", ["/api/ai/vision/thermal", "/api/ai/sound/cat"])
@pytest.mark.parametrize("yontem", ["gradcam++", "gradcam", "eigencam", "hirescam"])
def test_KARSIT_KANIT_gecerli_yontem_allowliste_TAKILMAZ(client, uc, yontem):
    """Geçerli yöntem, girdi eksik olsa bile allowlist 422'sine TAKILMAMALI —
    dönen hata (girdi-yok) xai_method'dan bahsetmez."""
    r = client.post(uc, data={"xai_method": yontem})
    assert not (r.status_code == 422 and "xai_method" in r.text), (
        f"{uc}/{yontem}: allowlist geçerli yöntemi reddetti — UI seçenekleri kilitlenir"
    )
