"""GPU tespiti — TEK NOKTA (app.py + predictors.py ortak kullanır).

torch.cuda.is_available() yeni kartlarda (RTX 5090 / Blackwell) True döner AMA torch kernel'i o
mimariyi desteklemiyorsa çalışma anında ÇÖKER ("no kernel image..."). Bu yüzden küçük bir test op
ile GERÇEKTEN dene; başarısızsa GPU hatası fırlatma → uyar + CPU'ya düş. Sonuç önbelleğe alınır.

Not: RTX 5090/Blackwell için CUDA 12.8 + PyTorch 2.7 (cu128) gerekir; cu128 build eski kartları
(RTX 30/40) da kapsar. Sürüm doğruysa GPU çalışır; değilse burası otomatik CPU'ya düşer.
"""
import logging

_lg = logging.getLogger("pemf-ai")
_GPU_OK = None
_YOLO_DEVICE = None


def gpu_ok() -> bool:
    """CUDA GERÇEKTEN çalışıyor mu (test op ile)? Başarısız → uyar + False (CPU). Bir kez, önbellekli."""
    global _GPU_OK
    if _GPU_OK is None:
        try:
            import torch
            if hasattr(torch, "cuda") and torch.cuda.is_available():
                x = torch.zeros(8, device="cuda")          # gerçek çalışma testi (kernel-mismatch'i yakalar)
                _ = (x + 1).sum().item()
                torch.cuda.synchronize()
                _GPU_OK = True
                _lg.info("GPU aktif: %s", torch.cuda.get_device_name(0))
            else:
                _GPU_OK = False
                _lg.info("GPU bulunamadı → CPU modunda çalışılıyor.")
        except Exception as e:
            _GPU_OK = False
            _lg.warning("GPU tespit edildi ama çalıştırılamadı (%s: %s) → CPU'ya düşülüyor. "
                        "Yeni kartlar (RTX 5090/Blackwell) için CUDA 12.8 + PyTorch cu128 gerekir.",
                        type(e).__name__, e)
    return _GPU_OK


def torch_device() -> str:
    """'cuda' (GPU gerçekten çalışıyorsa) | 'cpu'."""
    return "cuda" if gpu_ok() else "cpu"


def yolo_device():
    """ultralytics device: 0 (GPU) | 'cpu' (yoksa/başarısızsa)."""
    global _YOLO_DEVICE
    if _YOLO_DEVICE is None:
        _YOLO_DEVICE = 0 if gpu_ok() else "cpu"
    return _YOLO_DEVICE


def onnx_providers(want_cuda: bool = True):
    """onnxruntime provider listesi. CUDA yalnız GERÇEKTEN çalışıyorsa; CPU her zaman sonda (oto-fallback)."""
    import onnxruntime as ort
    avail = ort.get_available_providers()
    use_cuda = want_cuda and "CUDAExecutionProvider" in avail and gpu_ok()
    return (["CUDAExecutionProvider"] if use_cuda else []) + ["CPUExecutionProvider"]
