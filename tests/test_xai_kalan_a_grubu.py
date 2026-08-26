# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""XAI §KALAN A-GRUBU — backend davranış kilitleri (xai-entegrasyon-plani.md §KALAN-2026-08-26).

A4: landmark yanıtı `fgs_bantlari` taşır (thresholds_calibrated.json p5/p95 — UI
    'ölçülen değer vs popülasyon bandı' paneli buradan çizilir; dosya yoksa boş dict → panel gizli).
A5: em_fantom/em_petri modülleri em_kedi ile AYNI hafif canlı-sensitivity sarmalayıcısını taşır
    (7+1 forward, PNG/SHAP yok) ve router yanıt meta'sına bağlıdır.
A6: termal/ses uçlarında CAM yöntemi dışa açıldı — allowlist DIŞI değer 422 (sessiz düşüş değil).
"""

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


def test_YAPISAL_landmark_yaniti_bantlari_tasir():
    """Çıpa GERÇEK çağrıya pinli (yapısal-çıpa kırılganlığı dersi): landmark JSONResponse
    gövdesi `fgs_bantlari` alanını _fgs_bantlari() ÇAĞRISIYLA doldurur."""
    src = (KOK / "servers/ai_router.py").read_text(encoding="utf-8")
    assert '"fgs_bantlari": _fgs_bantlari(),' in src, "landmark yanıtı bant alanını kaybetti (A4 regresyonu)"
    i = src.index('"fgs_bantlari": _fgs_bantlari(),')
    pencere = src[max(0, i - 600) : i]
    assert '"fgs_total": total,' in pencere, "bant alanı landmark yanıt gövdesinden ayrı düşmüş"


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
    assert len(a) == 3 and all(set(t) == {"feature", "etki"} for t in a)
    assert a[0]["feature"] == "duty_sum", f"{modul_yolu}: mühendislenmiş sinyal top-1 değil: {a!r}"
    assert all(t["etki"] > 0 for t in a), f"{modul_yolu}: sensitivity ~0 (ref-stats bağlanmamış olabilir)"


def test_YAPISAL_router_fantom_ve_petri_meta_bagli():
    """Gerçek çağrıya pinli: iki uç da xaiSensitivity'yi to_thread ile üretir ve
    hata analizi DÜŞÜRMEZ (except + warning)."""
    # ⚠️ çıpa TEK satıra pinli DEĞİL: ruff-format çağrıyı çok-satıra kırabiliyor (ölçüldü)
    # — yapısal-çıpa kırılganlığı dersi. Fonksiyon-adı çıpası + pencere-içi parça kontrolü.
    src = (KOK / "servers/ai_router.py").read_text(encoding="utf-8")
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
        assert "except Exception" in blok and "analiz etkilenmedi" in blok, (
            f"{modul}: XAI meta hatası zarif değil — analiz düşebilir"
        )
        assert "asyncio.to_thread" in blok, f"{modul}: sensitivity event-loop üstünde koşuyor (bloklar)"


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
        blok = src[max(0, i - 500) : i + 500]
        assert "except Exception" in blok and "analiz etkilenmedi" in blok, (
            f"ai_service {modul}: XAI meta hatası zarif değil"
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
