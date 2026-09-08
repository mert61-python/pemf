# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI PRO HEDEF SAĞLAYICI DELEGASYONU — Faz 1 kapıları (2026-09-08).

Kapalı döngünün kediye bağlı beş noktası `servers/ai_pro_hedef.py` arayüzünün arkasına alındı
(plan: docs/arastirma-ai-pro-fantom-petri-plani.md). Bu dosya refaktörün ÜÇ vaadini ölçer:

  1. `_localize_organ` / `_predict_and_drive` gerçekten AKTİF SAĞLAYICIYA gider (isim ve tuple
     sözleşmesi korunur — 9+ test bu adları monkeypatch'liyor).
  2. Duty kırpması TEK YERDE (zarf): sağlayıcı ne döndürürse döndürsün önerilen ve sürülen duty
     `AI_PRO_DUTY_MAX_RATIO`yu aşmaz. Eskiden kırpma kedi `_cpu`/`_gpu` gövdelerinde iki kez
     yazılıydı → yeni bir sağlayıcı kırpmasız kalabilirdi.
  3. Kedi yolu DAVRANIŞ olarak aynı (golden), kod taşınmadı.

Ayrıca yapısal kapı: `ai_pro_hedef` modül seviyesinde `ai_hub` import ETMEZ — ederse frozen EXE
build'i `scripts/build_backend_exe.ps1`in PYZ koruma kapısında durur (ai_hub yalnız .pyd sevk
edilir).
"""

import numpy as np
import pytest


@pytest.fixture()
def air():
    import servers.ai_router as _air

    return _air


@pytest.fixture()
def sahte_model(air, monkeypatch):
    """Kayda sahte bir sağlayıcı ekleyip aktif model yapar; çağrıları izler."""

    izler = {"localize": [], "predict": [], "yukle": 0}

    class _Sahte:
        ad = "sahte"
        title = "Sahte Model"
        subject_label = "sahte özne"
        achieved_B = 0.002
        duty_sum = 2.4
        join_timeout_s = 9.0
        varsayilan_hedef = 0

        def hedef_idleri(self):
            return frozenset({0, 1})

        def yukle(self):
            izler["yukle"] += 1

        def localize(self, frame_bgr, hedef_id):
            izler["localize"].append(hedef_id)
            return (True, 11.0, 22.0, 33.0, 0.77, None, True, {"kaynak": "sahte"})

        def predict(self, x_mm, y_mm, z_mm, hedef_id):
            izler["predict"].append((x_mm, y_mm, z_mm, hedef_id))
            # ⚠️ Kırpma sınırının ÜSTÜNDE ham değer: zarf kırpmazsa test yakalar.
            return [0.9] * 7, [15.0] * 7, 0.123

        def hedef_adi(self, hedef_id):
            return f"Sahte {hedef_id}"

        def ipucu(self, ozne_var, hedef_adi):
            return "sahte ipucu"

        def xai_sensitivity(self, x_mm, y_mm, z_mm, hedef_id):
            return [{"feature": "x", "etki": 1.0}]

    import servers.ai_pro_hedef as hedef

    monkeypatch.setitem(hedef.SAGLAYICILAR, "sahte", _Sahte())
    monkeypatch.setattr(air, "_ai_hedef_modeli", "sahte")
    return izler


def test_KRITIK_lokalizasyon_AKTIF_saglayiciya_gider(air, sahte_model, monkeypatch):
    """MUTASYON: `_localize_organ`ı eski hâline (doğrudan `_localize_organ_cpu`) döndürün →
    KIRMIZI. Kedi kodu çağrılmadığı için sahte sağlayıcının değerleri dönmelidir."""
    kedi_izi = {"cagrildi": False}

    def _kedi_cagrilmamali(*a, **k):
        kedi_izi["cagrildi"] = True
        raise AssertionError("kedi lokalizasyonu çağrıldı — delegasyon çalışmıyor")

    monkeypatch.setattr(air, "_localize_organ_cpu", _kedi_cagrilmamali)
    monkeypatch.setattr(air, "_localize_organ_gpu", _kedi_cagrilmamali)

    sonuc = air._localize_organ("kare", 1)

    assert sahte_model["localize"] == [1], "aktif sağlayıcının localize'ı çağrılmadı"
    assert not kedi_izi["cagrildi"], "kedi yolu çağrıldı"
    assert len(sonuc) == 8, f"8'li tuple sözleşmesi bozuldu: {len(sonuc)} eleman"
    assert sonuc[0] is True and sonuc[1] == 11.0 and sonuc[7] == {"kaynak": "sahte"}


def test_KRITIK_duty_kirpmasi_ZARFTA_tek_yerde(air, sahte_model):
    """Sağlayıcı 0.9 (ham) döndürür; zarf `AI_PRO_DUTY_MAX_RATIO`ya kırpmalı.

    MUTASYON: `_predict_and_drive` içindeki `np.clip(...)` çağrısını kaldırın → KIRMIZI.
    Bu YENİ bir güvenlik sınırı değildir: aynı 0.50 politikası eskiden kedi `_cpu`/`_gpu`
    gövdelerinde yazılıydı; sağlayıcı arayüzünde tek kaynağa alındı."""
    from utils.stm32_protocol_limits import AI_PRO_DUTY_MAX_RATIO

    D, P, e = air._predict_and_drive(1.0, 2.0, 3.0, 1)

    assert sahte_model["predict"] == [(1.0, 2.0, 3.0, 1)], "aktif sağlayıcının predict'i çağrılmadı"
    assert len(D) == 7 and len(P) == 7
    assert max(D) <= AI_PRO_DUTY_MAX_RATIO + 1e-9, (
        f"duty {max(D)} > {AI_PRO_DUTY_MAX_RATIO} — kırpma zarfta uygulanmıyor; onay ekranında "
        "gösterilen değer donanıma gidenden FARKLI olur"
    )
    assert P == [15.0] * 7, "faz değerleri değiştirildi (zarf yalnız duty kırpar)"
    assert e == pytest.approx(0.123), "e_field zarfta bozuldu"


def test_KRITIK_tahmin_hatasi_SIFIR_doner_bobin_SURULMEZ(air, monkeypatch):
    """Güvenli varsayılan korunmalı: sağlayıcı patlarsa (0,0,0) → sürüş yok."""

    class _Patlayan:
        ad = "patlayan"
        title = "Patlayan"
        subject_label = "x"

        def predict(self, *a, **k):
            raise RuntimeError("model yok")

    import servers.ai_pro_hedef as hedef

    monkeypatch.setitem(hedef.SAGLAYICILAR, "patlayan", _Patlayan())
    monkeypatch.setattr(air, "_ai_hedef_modeli", "patlayan")

    D, P, e = air._predict_and_drive(1.0, 2.0, 3.0, 0)
    assert D == [0.0] * 7 and P == [0.0] * 7 and e == 0.0, "tahmin hatasında sıfır dönmüyor — bobin sürülür"


def test_KRITIK_bilinmeyen_model_ValueError_ve_dongu_VARSAYILANA_duser(air, monkeypatch):
    """Uçlar bilinmeyen modeli 422'ye çevirir; döngü ise ölmemeli (varsayılana düşer)."""
    import servers.ai_pro_hedef as hedef

    with pytest.raises(ValueError):
        hedef.saglayici_al("yok-boyle-model")
    assert hedef.saglayici_al(None).ad == hedef.VARSAYILAN_MODEL, "boş model varsayılana düşmüyor"

    monkeypatch.setattr(air, "_ai_hedef_modeli", "yok-boyle-model")
    assert air._aktif_saglayici().ad == hedef.VARSAYILAN_MODEL, "döngü bilinmeyen modelde ölüyor"


def test_KRITIK_KEDI_yolu_davranis_GOLDEN(air, monkeypatch):
    """Kedi sağlayıcısı mevcut fonksiyonlara delege eder; kod TAŞINMADI.

    Golden: aynı sahte cat_organ çıktısı + sahte KediPredictor için lokalizasyon tuple'ı ve
    D/P/E, refaktör öncesiyle AYNI olmalı (cm→mm ×10, güven geçidi, 0.50 kırpma, faz aynen)."""
    import servers.ai_pro_hedef as hedef

    monkeypatch.setattr(air, "_ai_hedef_modeli", "kedi")
    monkeypatch.setattr(air, "ai_service_enabled", lambda: False)

    class _SahteCatOrgan:
        def predict(self, yol, render=False, target_oid=None):
            return {
                "organs": {2: {"coord_cabin_cm": [1.0, -2.0, 3.5], "reliability": 0.9}},
                "_overlay_bgr": None,
            }

    class _SahteKedi:
        def predict(self, x, y, z, organ_id, achieved_B, duty_sum):
            out = {f"D{i}": 0.9 for i in range(1, 8)}  # kırpma sınırının üstünde HAM
            out.update({f"P{i}": 30.0 for i in range(1, 8)})
            out["result_E"] = 0.5
            return out

    monkeypatch.setattr(air, "_get_or_load_catorgan", lambda: _SahteCatOrgan())
    monkeypatch.setattr(air, "_get_or_load_kedi", lambda: _SahteKedi())
    monkeypatch.setattr(air.cv2, "imwrite", lambda *a, **k: True)

    lz, lx, ly, lzz, lrel, _lov, ozne, _dokum = air._localize_organ(np.zeros((4, 4, 3), np.uint8), 2)
    assert (lz, lx, ly, lzz) == (True, 10.0, -20.0, 35.0), "kedi lokalizasyon golden'ı değişti (cm→mm ×10)"
    assert lrel == pytest.approx(0.9) and ozne is True

    D, P, e = air._predict_and_drive(lx, ly, lzz, 2)
    assert D == [0.5] * 7, f"kedi duty golden'ı değişti: {D[:2]}"
    assert P == [30.0] * 7 and e == pytest.approx(0.5)
    assert hedef.saglayici_al("kedi").achieved_B == 0.001, "kedi ekstra girdileri (B) değişti"
    assert hedef.saglayici_al("kedi").duty_sum == 1.5, "kedi ekstra girdileri (duty_sum) değişti"


def test_KRITIK_kedi_hedef_kumesi_TEK_KAYNAK_ve_0_6(air):
    """Dört doğrulama noktası bu kümeyi kullanacak (Faz 1 ikinci parça). Kedi kümesi 0-6:
    cat_organ 7-10'u lokalize eder ama em_kedi onları tedavi etmez (Audit P2 sessiz-sıfır)."""
    import servers.ai_pro_hedef as hedef

    assert hedef.saglayici_al("kedi").hedef_idleri() == frozenset(range(0, 7))


def test_YAPISAL_ai_pro_hedef_modul_seviyesinde_ai_hub_IMPORT_ETMEZ():
    """PYZ koruma kapısı (scripts/build_backend_exe.ps1): ai_hub bytecode'u EXE arşivine girerse
    build DURUR — ai_hub yalnız Cython .pyd olarak sevk edilir. ai_router'ın deseni de budur.
    MUTASYON: dosyanın başına `from ai_hub...` ekleyin → KIRMIZI."""
    from pathlib import Path

    import servers.ai_pro_hedef as hedef

    src = Path(hedef.__file__).read_text(encoding="utf-8")
    kacak = [
        s.strip()
        for s in src.splitlines()
        if (s.startswith("import ai_hub") or s.startswith("from ai_hub")) and "#" not in s.split("ai_hub")[0]
    ]
    assert not kacak, (
        f"ai_pro_hedef modül seviyesinde ai_hub import ediyor: {kacak} — frozen build PYZ koruma "
        "kapısında durur. İmportu fonksiyon gövdesine alın (gerekiyorsa TYPE_CHECKING bloğu)."
    )
