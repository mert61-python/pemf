# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""EM ÜÇLÜSÜ XAI ENTEGRASYONU — Faz 1 kalem 4 (docs/xai-entegrasyon-plani.md §4/1.2).

ÖLÇÜLEN DURUM: em_kedi CANLI AI Pro'nun doz modelidir; öneri-onay ekranı parametreleri
NEDENSİZ gösterir. Tek-örnek XAI dejenere olduğundan (std/background X'ten türetilirse ~0)
eğitim-dağılımı referansları ZORUNLU — build_tools/make_em_xai_ref_stats.py bunları
scaler.scale_ + eğitim CSV'sinden ÇAPRAZ-KONTROLLE üretti (ai_hub/<modül>/xai_ref_stats.npz;
petri organ_id sabit-0 tuzağı 0.5 ile elle geçildi).

DÜZELTME: ai_hub.xai_tabular.em_runtime TEK-KAYNAK yapıştırıcı (ham-girdi→ham-çıktı
predict_fn + ref-stats yükleyici + hafif canlı sensitivity [7 ONNX forward, D-kanalları,
PNG'siz JSON] + Mod-2 batch); üç EM modülü ince sarmalayıcı taşır; /api/ai/pro/propose
meta'sına 'xaiSensitivity' eklenir — XAI hatası ÖNERİYİ ASLA düşürmez.
"""

import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]

_MODUL_DIZINLERI = {
    "em_kedi": ("ai_hub/em_kedi", {0, 1, 2, 3, 4, 5, 6}),
    "em_fantom": ("ai_hub/inference_em_fantom", {0, 1}),
    "em_petri": ("ai_hub/inference_em_petri", {0, 1}),
}


# ── 1) Referans varlıkları geçerli mi ────────────────────────────────────────
def test_KRITIK_ref_stats_varliklari_GECERLI():
    for ad, (dizin, organ_kume) in _MODUL_DIZINLERI.items():
        p = KOK / dizin / "xai_ref_stats.npz"
        assert p.exists(), (
            f"{ad}: xai_ref_stats.npz YOK — canlı XAI dejenere kalır (üret: build_tools/make_em_xai_ref_stats.py)"
        )
        d = np.load(p, allow_pickle=False)
        std, bg = d["std"], d["background"]
        assert std.shape == (6,) and (std > 0).all(), f"{ad}: std dejenere/eksik: {std!r}"
        assert bg.shape == (64, 6), f"{ad}: background beklenen (64,6) değil: {bg.shape}"
        assert set(np.unique(bg[:, 3]).astype(int)).issubset(organ_kume), (
            f"{ad}: background organ_id geçersiz küme: {np.unique(bg[:, 3])!r}"
        )
        assert 1e-6 < std[4] < 1e-2, f"{ad}: achieved_B std fiziksel aralık dışı: {std[4]}"


def test_KARSIT_KANIT_petri_organ_std_sifir_DEGIL():
    """Keşif bulgusu: petri eğitim CSV'sinde organ_id sabit 0 (std=0) — varlıkta 0.5 override
    uygulanmış olmalı; yoksa sensitivity organ_id için sessizce ~0 raporlar."""
    d = np.load(KOK / "ai_hub/inference_em_petri/xai_ref_stats.npz", allow_pickle=False)
    assert d["std"][3] == pytest.approx(0.5), f"petri organ_id std {d['std'][3]} — override kayıp"


# ── sahte predictor (üç modülün ortak iç zinciri) ────────────────────────────
class _Identity:
    def inverse_transform(self, y):
        return np.asarray(y, dtype=np.float64)


def _sahte_em_predictor(n_out=22):
    """Gerçek zincirle aynı sözleşme: _build_input(6 kolon)->float32, _run_onnx->(N,n_out), sy.inverse."""
    rng = np.random.default_rng(9)
    # ⚠️ Kalibrasyon GERÇEK ref_std ölçeklerine göre (ilk sürüm bunu kaçırdı ve test
    # kendi zayıflığını yakaladı): etki ≈ 0.1·std·|W|; kedi std'leri y≈125, duty≈0.37.
    # W_koord=0.001 → y etkisi ≈ 0.0125; W_duty=5 → duty etkisi ≈ 0.183 ⇒ net ayrım.
    W = rng.normal(size=(6, n_out)) * 0.001
    W[5, :7] = 5.0  # duty_sum → D-kanallarına GÜÇLÜ etki (mühendislenmiş sinyal)

    p = SimpleNamespace(sy=_Identity())
    p._build_input = lambda x, y, z, o, B, d: np.column_stack(
        [np.atleast_1d(x), np.atleast_1d(y), np.atleast_1d(z), np.atleast_1d(o), np.atleast_1d(B), np.atleast_1d(d)]
    ).astype(np.float32)
    p._run_onnx = lambda X: (np.asarray(X, dtype=np.float64) @ W).astype(np.float32)
    return p


# ── 2) hafif canlı sensitivity (em_kedi) ─────────────────────────────────────
def test_KRITIK_em_kedi_hizli_sensitivity_ANLAMLI_ve_DETERMINISTIK():
    from ai_hub.em_kedi.inference_em_kedi import xai_hizli_sensitivity

    p = _sahte_em_predictor()
    a = xai_hizli_sensitivity(p, 78.0, 210.0, -57.85, 3, 0.001, 2.0)
    b = xai_hizli_sensitivity(p, 78.0, 210.0, -57.85, 3, 0.001, 2.0)
    assert a == b, "aynı girdiye farklı canlı açıklama"
    assert len(a) == 3 and all(set(t) == {"feature", "etki"} for t in a)
    assert a[0]["feature"] == "duty_sum", (
        f"mühendislenmiş sinyal (duty_sum→D güçlü) top-1 değil: {a!r} — D-kanal hedefli ölçüm bozuk"
    )
    assert all(t["etki"] > 0 for t in a), "referanslı tek-örnek sensitivity ~0 (dejenerasyon sürüyor)"


# ── 3) propose meta'sı xaiSensitivity taşır; hatası öneriyi düşürmez ─────────
@pytest.fixture()
def propose_env(monkeypatch):
    import servers.ai_router as air
    import servers.api_server as apis

    snap = dict(air._ai_organ_cache)
    with air._ai_cache_lock:
        air._ai_organ_cache.update(
            {
                "localized": True,
                "organ_id": 3,
                "at": time.time(),
                "x_mm": 10.0,
                "y_mm": 20.0,
                "z_mm": 30.0,
                "reliability": 0.8,
                "kedi_var": True,
            }
        )
    monkeypatch.setattr(air, "_predict_and_drive", lambda x, y, z, o: ([0.5] * 7, [0.0] * 7, 0.07))
    monkeypatch.setattr(air, "_get_or_load_kedi", lambda: object())
    yield air, TestClient(apis.app)
    air._ai_organ_cache.clear()
    air._ai_organ_cache.update(snap)


_SENTINEL = [{"feature": "duty_sum", "etki": 0.15}]


def test_KRITIK_propose_meta_xai_sensitivity_TASIR(propose_env, monkeypatch):
    air, client = propose_env
    import ai_hub.em_kedi.inference_em_kedi as iek

    monkeypatch.setattr(iek, "xai_hizli_sensitivity", lambda *a, **k: _SENTINEL)
    r = client.post("/api/ai/pro/propose", json={"organ_id": 3, "duration_minutes": 20})
    assert r.status_code == 200, r.text
    meta = r.json().get("meta") or {}
    assert meta.get("xaiSensitivity") == _SENTINEL, (
        "öneri meta'sı xaiSensitivity taşımıyor — hekim onay ekranı 'dozu ne belirledi' gösteremez"
    )


def test_KARSIT_KANIT_xai_hatasi_ONERIYI_dusurmez(propose_env, monkeypatch):
    air, client = propose_env
    import ai_hub.em_kedi.inference_em_kedi as iek

    def _patla(*a, **k):
        raise RuntimeError("xai patladı (test)")

    monkeypatch.setattr(iek, "xai_hizli_sensitivity", _patla)
    r = client.post("/api/ai/pro/propose", json={"organ_id": 3, "duration_minutes": 20})
    assert r.status_code == 200, f"XAI hatası ÖNERİYİ düşürdü (klinik akış kırıldı): {r.text}"
    body = r.json()
    assert body.get("proposalId") and "xaiSensitivity" not in (body.get("meta") or {})


# ── 4) yapısal: üç modül de batch XAI + ref-stats bağlı ──────────────────────
def test_YAPISAL_uc_modul_de_xai_bagli():
    for ad, (dizin, _k) in _MODUL_DIZINLERI.items():
        src_dosyalar = list((KOK / dizin).glob("inference_em_*.py"))
        assert src_dosyalar, f"{ad}: inference dosyası bulunamadı"
        src = src_dosyalar[0].read_text(encoding="utf-8", errors="replace")
        assert "xai_ref_stats" in src and "_run_xai_em" in src, (
            f"{ad}: batch XAI (_run_xai_em) veya ref-stats yükleyici bağlanmamış"
        )
