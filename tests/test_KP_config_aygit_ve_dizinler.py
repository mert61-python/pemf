# -*- coding: utf-8 -*-
"""KP-1 · ai/config.py · sözleşmeler: aygıt seçimi (CUDA → mps → cpu; torch yoksa 'cpu' dizgesi), torch kurulu değilken
içe aktarma çökmez, çalışma dizinleri APPDATA altında kurulur ve kurulamazsa içe aktarma çökmez, `__main__` özeti.

Sahte EN ALT katta: `torch` (modülün kendi `torch` adı; CUDA / MPS durumu), içe aktarma (`__import__` — yalnız 'torch' için
ModuleNotFoundError), ortam (`APPDATA` → tmp_path). İçe aktarma zamanı davranışı, modül kaynağı AYNI dosya yolundan ayrı bir ad
alanında derlenip yürütülerek ölçülür (sys.modules'a dokunulmaz; gerçek `ai.config` değişmez).
"""

from __future__ import annotations

import builtins
import logging
import types
from pathlib import Path

import pytest

from ai import config as cfg


class _SahteTorch:
    """CUDA / MPS durumu verilen sahte torch; `device(ad)` → ('cihaz', ad)."""

    def __init__(self, cuda=False, mps=None):
        self.cuda = types.SimpleNamespace(is_available=lambda: cuda, get_device_name=lambda i: f"Sahte GPU {i}")
        if mps is not None:
            self.backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: mps))

    @staticmethod
    def device(ad):
        return ("cihaz", ad)


def test_aygit_CUDA_varsa_cuda_ve_GPU_adi_gunlukte(monkeypatch, caplog):
    """torch.cuda.is_available() True → torch.device('cuda') döner; günlükte 'Using GPU: Sahte GPU 0' (0. aygıtın adı)."""
    monkeypatch.setattr(cfg, "torch", _SahteTorch(cuda=True, mps=True))
    with caplog.at_level(logging.INFO, logger=cfg.logger.name):
        assert cfg.get_device() == ("cihaz", "cuda")
    assert "Using GPU: Sahte GPU 0" in [r.getMessage() for r in caplog.records]


def test_aygit_CUDA_yok_MPS_varsa_mps(monkeypatch, caplog):
    """CUDA yok + backends.mps.is_available() True → torch.device('mps') + 'Using Apple Silicon GPU'."""
    monkeypatch.setattr(cfg, "torch", _SahteTorch(cuda=False, mps=True))
    with caplog.at_level(logging.INFO, logger=cfg.logger.name):
        assert cfg.get_device() == ("cihaz", "mps")
    assert "Using Apple Silicon GPU" in [r.getMessage() for r in caplog.records]


@pytest.mark.parametrize("mps", [False, None], ids=["mps_kapali", "mps_yok"])
def test_aygit_CUDA_ve_MPS_yoksa_cpu(monkeypatch, mps):
    """CUDA yok; MPS kapalı ya da backends.mps hiç yok → torch.device('cpu')."""
    monkeypatch.setattr(cfg, "torch", _SahteTorch(cuda=False, mps=mps))
    assert cfg.get_device() == ("cihaz", "cpu")


def test_aygit_TORCH_YOKSA_cpu_dizgesi(monkeypatch, caplog):
    """torch None (ONNX/GUI derlemesi) → 'cpu' DİZGESİ (torch.device değil) + 'Torch not available' günlüğü."""
    monkeypatch.setattr(cfg, "torch", None)
    with caplog.at_level(logging.INFO, logger=cfg.logger.name):
        assert cfg.get_device() == "cpu"
    assert any("Torch not available" in r.getMessage() for r in caplog.records)


# ───────────────────────────── içe aktarma zamanı (ikiz yürütme) ─────────────────────────────


def _torchsuz_yerlesikler():
    gercek = builtins.__import__

    def _ice_aktar(ad, globals=None, locals=None, fromlist=(), level=0):
        if ad == "torch" or ad.startswith("torch."):
            raise ModuleNotFoundError("No module named 'torch'", name="torch")
        return gercek(ad, globals, locals, fromlist, level)

    yerlesik = dict(vars(builtins))
    yerlesik["__import__"] = _ice_aktar
    return yerlesik


def _ikiz_yurut(ad):
    kaynak = Path(cfg.__file__).read_text(encoding="utf-8")
    ns = {"__name__": ad, "__file__": cfg.__file__, "__builtins__": _torchsuz_yerlesikler()}
    exec(compile(kaynak, cfg.__file__, "exec"), ns)
    return ns


def test_ice_aktarma_TORCH_KURULU_DEGIL_ve_APPDATA_DOSYA_iken_COKMEZ(monkeypatch, tmp_path):
    """torch içe aktarılamaz + APPDATA bir DOSYAyı gösterir (dizin kurulamaz) → modül yine yüklenir: torch None, DEVICE 'cpu',
    DATA_DIR / MODELS_DIR APPDATA/PEMF_GUI/ai altını gösterir, hiçbir dizin oluşmaz."""
    alan = tmp_path / "kp_alan"  # conftest tmp_path'e kendi izole dizinlerini koyar → ayrı alt alan
    alan.mkdir()
    dosya = alan / "appdata_dosya"
    dosya.write_text("dizin degil", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(dosya))
    ns = _ikiz_yurut("kp_ai_config_ikiz")
    assert ns["torch"] is None
    assert ns["DEVICE"] == "cpu"
    assert ns["DATA_DIR"] == dosya / "PEMF_GUI" / "ai" / "data" / "datasets"
    assert ns["MODELS_DIR"] == dosya / "PEMF_GUI" / "ai" / "models" / "saved_models"
    assert dosya.is_file() and dosya.read_text(encoding="utf-8") == "dizin degil"
    assert sorted(p.name for p in alan.iterdir()) == ["appdata_dosya"]


def test_main_OZETI_dizinleri_cihazi_ve_katalogu_yazar_dizinler_APPDATA_altinda_kurulur(monkeypatch, tmp_path, capsys):
    """`__main__` olarak (torch yok, APPDATA = tmp) → dört çalışma dizini tmp altında KURULUR; çıktı: yükleme satırı, temel /
    veri / model dizinleri, 'Device: cpu', veri kümesi ve model adları (modülün kendi sözlüklerinden)."""
    alan = tmp_path / "kp_alan"
    alan.mkdir()
    monkeypatch.setenv("APPDATA", str(alan))
    ns = _ikiz_yurut("__main__")
    kok = alan / "PEMF_GUI" / "ai"
    for alt in (("data", "datasets"), ("models", "saved_models"), ("logs",), ("results",)):
        assert kok.joinpath(*alt).is_dir(), alt
    satirlar = capsys.readouterr().out.splitlines()
    assert satirlar[0] == "AI Configuration Loaded Successfully"
    assert satirlar[1] == f"Base Directory: {Path(cfg.__file__).parent}"
    assert satirlar[2] == f"Data Directory: {kok / 'data' / 'datasets'}"
    assert satirlar[3] == f"Models Directory: {kok / 'models' / 'saved_models'}"
    assert satirlar[4] == "Device: cpu"
    assert f"Available Datasets: {list(cfg.DATASETS.keys())}" in satirlar
    assert f"Available Models: {list(cfg.MODELS.keys())}" in satirlar
    assert list(ns["DATASETS"]) == list(cfg.DATASETS) and list(ns["MODELS"]) == list(cfg.MODELS)
