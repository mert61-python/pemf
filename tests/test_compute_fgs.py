"""Kritik yol: FGS skorlama — yetersiz keypoint -> -1 (tespit-yok sinyali, 0 'Ağrı Yok' DEĞİL)."""
import numpy as np

from ai_hub.cat_landmark.inference_cat_landmark import compute_fgs


def test_insufficient_keypoints_returns_negative_not_zero():
    # <48 keypoint -> fgs_total = -1 (endpoint bunu detected:false/null'a çevirir).
    res = compute_fgs(np.zeros((10, 2)))
    assert res.get("fgs_total") == -1
    # KRİTİK: 0 dönmemeli (0 'Ağrı Yok' yanlış-güvencesi demek).
    assert res.get("fgs_total") != 0


def test_full_keypoints_returns_valid_or_invalid_range():
    res = compute_fgs(np.random.rand(48, 2))
    assert "fgs_total" in res
    ft = res["fgs_total"]
    assert ft == -1 or (0 <= ft <= 10)
