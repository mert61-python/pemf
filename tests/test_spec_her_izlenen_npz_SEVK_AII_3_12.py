# -*- coding: utf-8 -*-
"""AII-3.12 — git'te izlenen HER `ai_hub/**/*.npz` (XAI referansları) gerçek spec'in datas'ına doğru hedefle girer.

Bu boşluk BİR KEZ ISIRDI (`test_ai_hazirlik_envanteri.py` başlığı: `.npz` spec'te yoktu → EM XAI 1.9.25'ten beri üretimde sessiz ölü).
ÖLÇÜLDÜ (A3, 2026-10-12): spec'in ai_hub kuralından `.npz` çıkarılınca (mutant K5_spec_npz_yok) mevcut paketleme / hazırlık / X4 / X6 /
4B24 / D427 / kurulum / base-zip kapılarının HİÇBİRİ kırmızı olmuyor (41 geçti / 18 atlandı + 39 geçti) — 4B24'ün deseni yalnız kodda
`"ai_hub/…npz"` DİZESİ arıyor; AI-1'in yeni npz'leri (`xai_train_ref.npz` ×3, `xai_train_ref_v2.npz`) `THIS_DIR / "…npz"` ile çözülüyor.
Hazırlık probu ancak SAHADA (frozen EXE açılınca) "eksik" der. Kapı derleme ÖNCESİ ölçer: D4.27'nin PyInstaller'sız spec sürücüsü.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "tests"))
from test_her_model_agirligi_bir_PAKETE_duser_D427 import spec_datas  # noqa: E402,F401  (fikstür: GERÇEK spec)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="spec yalnız Windows derlemesinde koşar")


def _izlenen_npz() -> list[str]:
    ham = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files", "-z", "--", "ai_hub/*.npz", "ai_hub/**/*.npz"],
        cwd=KOK,
        capture_output=True,
        timeout=120,
    ).stdout
    return sorted(
        {
            x.decode("utf-8")
            for x in ham.split(b"\x00")
            if x and (KOK / x.decode("utf-8")).stat().st_size < 5 * 1024 * 1024
        }
    )


def test_KRITIK_izlenen_her_ai_hub_npz_spec_datasinda(spec_datas):
    npzler = _izlenen_npz()
    assert len(npzler) >= 7, f"senaryo: izlenen ai_hub npz sayısı beklenenden az ({npzler})"
    eksik, yanlis = [], []
    for rel in npzler:
        eslesen = [(s, d) for s, d in spec_datas if s.replace("\\", "/").endswith(rel)]
        if not eslesen:
            eksik.append(rel)
        elif any(d != str(Path(rel).parent).replace("\\", "/") for _, d in eslesen):
            yanlis.append((rel, eslesen))
    assert not eksik, f"frozen EXE'ye GİRMEYEN XAI referansları (sahada XAI sessiz ölü): {eksik}"
    assert not yanlis, f"yanlış hedef dizin: {yanlis}"


def test_KARSIT_AI1_yeni_npzleri_listede():
    npzler = set(_izlenen_npz())
    for rel in (
        "ai_hub/em_kedi/xai_train_ref.npz",
        "ai_hub/inference_em_fantom/xai_train_ref.npz",
        "ai_hub/inference_em_petri/xai_train_ref.npz",
        "ai_hub/inference_human_kidney_disease/xai_train_ref_v2.npz",
    ):
        assert rel in npzler, rel
