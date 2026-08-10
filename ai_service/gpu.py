"""GPU tespiti — TEK NOKTA (app.py + predictors.py ortak kullanır).

torch.cuda.is_available() yeni kartlarda (RTX 5090 / Blackwell) True döner AMA torch kernel'i o
mimariyi desteklemiyorsa çalışma anında ÇÖKER ("no kernel image..."). Bu yüzden küçük bir test op
ile GERÇEKTEN dene; başarısızsa GPU hatası fırlatma → uyar + CPU'ya düş. Sonuç önbelleğe alınır.

onnxruntime AYRI bir CUDA stack'idir (#12): torch cu128 geçse bile resmi onnxruntime-gpu build'i
sm_120 (Blackwell) kernel'i içermeyebilir → ONNX seansları CUDA'da çöker. Bu yüzden ONNX için
torch prob'unu proxy ALMA; ayrı bir gerçek ORT CUDA prob'u koş.

Not: RTX 5090/Blackwell için CUDA 12.8 + PyTorch 2.7 (cu128) gerekir; cu128 build eski kartları
(RTX 30/40) da kapsar. Sürüm doğruysa GPU çalışır; değilse burası otomatik CPU'ya düşer.
"""

import logging

_lg = logging.getLogger("pemf-ai")
_GPU_OK = None
_ORT_GPU_OK = None
_YOLO_DEVICE = None


def gpu_ok() -> bool:
    """torch CUDA GERÇEKTEN çalışıyor mu (test op ile)? Başarısız → uyar + False (CPU). Bir kez, önbellekli."""
    global _GPU_OK
    if _GPU_OK is None:
        try:
            import torch
        except ImportError:
            # torch KURULU DEĞİL → saf-ONNX/CPU dağıtımı için NORMAL senaryo. Yanıltıcı "RTX 5090
            # cu128 gerekir" uyarısı BASMA (eskiden ImportError da o dala düşüyordu, #12).
            _GPU_OK = False
            _lg.info("torch kurulu degil → CPU modunda calisiliyor (saf-ONNX dagitimi icin normaldir).")
            return _GPU_OK
        try:
            if hasattr(torch, "cuda") and torch.cuda.is_available():
                x = torch.zeros(8, device="cuda")  # gerçek çalışma testi (kernel-mismatch'i yakalar)
                _ = (x + 1).sum().item()
                torch.cuda.synchronize()
                _GPU_OK = True
                _lg.info("GPU aktif (torch): %s", torch.cuda.get_device_name(0))
            else:
                _GPU_OK = False
                _lg.info("GPU bulunamadı → CPU modunda çalışılıyor.")
        except Exception as e:
            _GPU_OK = False
            _lg.warning(
                "GPU tespit edildi ama torch ile çalıştırılamadı (%s: %s) → CPU'ya düşülüyor. "
                "Yeni kartlar (RTX 5090/Blackwell) için CUDA 12.8 + PyTorch cu128 gerekir.",
                type(e).__name__,
                e,
            )
    return _GPU_OK


def ort_gpu_ok() -> bool:
    """onnxruntime CUDA GERÇEKTEN çalışıyor mu (torch'tan AYRI stack)? Minik Identity ONNX + tek CUDA
    run ile dene. Başarısız (ör. sm_120 kernel yok) → uyar + CPU. Bir kez, önbellekli. onnx paketi
    yoksa/prob patlarsa güvenli tarafta kal (CPU) — 'GPU hatası yerine CPU uyarısı' tercihi."""
    global _ORT_GPU_OK
    if _ORT_GPU_OK is None:
        _ORT_GPU_OK = False
        try:
            import onnxruntime as ort
        except ImportError:
            return _ORT_GPU_OK
        if "CUDAExecutionProvider" not in ort.get_available_providers():
            return _ORT_GPU_OK  # ORT CPU-only build → sessizce CPU
        try:
            import numpy as np
            from onnx import TensorProto, helper

            node = helper.make_node("Identity", ["x"], ["y"])
            graph = helper.make_graph(
                [node],
                "probe",
                [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 4])],
                [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 4])],
            )
            model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
            sess = ort.InferenceSession(
                model.SerializeToString(),
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            if "CUDAExecutionProvider" not in sess.get_providers():
                return _ORT_GPU_OK  # ORT CUDA'yı reddetti → CPU'ya düştü
            sess.run(None, {"x": np.zeros((1, 4), dtype=np.float32)})  # gerçek CUDA çalıştırma
            _ORT_GPU_OK = True
            _lg.info("onnxruntime CUDA aktif.")
        except Exception as e:
            _lg.warning(
                "onnxruntime CUDA doğrulanamadı (%s: %s) → ONNX CPU'da çalışacak. Resmi "
                "onnxruntime-gpu RTX 5090/Blackwell (sm_120) kernel'i içermeyebilir.",
                type(e).__name__,
                e,
            )
    return _ORT_GPU_OK


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
    """onnxruntime provider listesi. CUDA yalnız AYRI ORT prob'u GERÇEKTEN geçerse; CPU her zaman
    sonda (oto-fallback). torch prob'una (gpu_ok) DEĞİL, ORT prob'una (ort_gpu_ok) bağlı (#12)."""
    use_cuda = want_cuda and ort_gpu_ok()
    return (["CUDAExecutionProvider"] if use_cuda else []) + ["CPUExecutionProvider"]
