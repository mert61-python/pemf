"""model_downloader.py — YEREL model çözümü (Hugging Face KALDIRILDI).

NOT (2026-07, kullanıcı kararı): Hugging Face indirme tamamen kaldırıldı. Tüm AI
modelleri artık offline paketlenir — EXE'ye gömülü ya da ProgramData\\PEMF_GUI\\ai_models
/ release_assets altında staged. Bu modül yalnızca YEREL arama yapar; ağ erişimi,
HF token'ı veya huggingface_hub bağımlılığı YOKTUR. Public API (download_model_sync,
find_installed_model) korunur.
"""
import os
import sys
import hashlib
from pathlib import Path

from utils.path_utils import get_app_data_directory, resource_path


def get_persistent_model_dir() -> Path:
    """Kullanıcıya özel kalıcı model klasörü (yerel arama köklerinden biri)."""
    model_dir = get_app_data_directory() / ".ai_models"
    model_dir.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        try:
            import ctypes
            FILE_ATTRIBUTE_HIDDEN = 0x02
            ctypes.windll.kernel32.SetFileAttributesW(str(model_dir), FILE_ATTRIBUTE_HIDDEN)
        except Exception:
            pass

    return model_dir


def _candidate_model_roots():
    """
    Model arama önceliği:
    1. PEMF_AI_MODELS_DIR ile verilen klasör
    2. Inno Setup ile kurulabilecek ortak ProgramData klasörü
    3. Kullanıcı AppData cache klasörü
    4. proje-yanı release_assets\\ai_models
    5. PyInstaller bundle içindeki ai_models klasörü (EXE'ye gömülü modeller)
    """
    roots = []

    env_dir = os.environ.get("PEMF_AI_MODELS_DIR", "").strip()
    if env_dir:
        roots.append(Path(env_dir))

    program_data = os.environ.get("PROGRAMDATA")
    if program_data:
        roots.append(Path(program_data) / "PEMF_GUI" / "ai_models")

    roots.append(get_persistent_model_dir())

    try:
        roots.append(Path(__file__).resolve().parent.parent / "release_assets" / "ai_models")
    except Exception:
        pass

    try:
        roots.append(Path(resource_path("ai_models")))
    except Exception:
        pass

    seen = set()
    unique_roots = []
    for root in roots:
        key = str(root).lower()
        if key not in seen:
            seen.add(key)
            unique_roots.append(root)
    return unique_roots


_MODEL_MIN_BYTES = {".onnx": 100_000, ".pt": 100_000, ".pth": 100_000, ".pkl": 200, ".bin": 1000}


def _model_integrity_ok(path: Path) -> bool:
    """Yarım/bozuk modeli 'kurulu' saymamak için bütünlük sağlaması (audit P2).
    (1) Asgari-boyut → truncated/0-byte ONNX tespiti. (2) Yanında <model>.sha256 varsa SHA256."""
    try:
        size = path.stat().st_size
        min_bytes = _MODEL_MIN_BYTES.get(path.suffix.lower(), 1)
        if size < min_bytes:
            print(f"Model butunluk UYARISI: {path.name} beklenenden kucuk ({size}B < {min_bytes}B).")
            return False
        sha_file = path.with_name(path.name + ".sha256")
        if sha_file.exists():
            expected = sha_file.read_text(encoding="utf-8").split()[0].strip().lower()
            if expected:
                h = hashlib.sha256()
                with open(path, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                if h.hexdigest().lower() != expected:
                    print(f"Model butunluk UYARISI: {path.name} SHA256 uyusmuyor.")
                    return False
        return True
    except Exception:
        return True  # şüpheli durumda engelleme yapma — mevcut davranışı koru


def find_installed_model(repo_path: str):
    """
    EXE'ye gömülü ya da ProgramData/release_assets altında kurulu modeli bulur.
    Paket formatı repo_path ile aynıdır: ai_models/ai_hub/<model>/<file>.onnx
    Bulamazsa None döner.
    """
    normalized = Path(os.path.normpath(repo_path))
    basename = normalized.name

    for root in _candidate_model_roots():
        candidates = [
            root / normalized,
            root / basename,
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file() and _model_integrity_ok(candidate):
                return str(candidate)
    return None


def download_model_sync(repo_path: str):
    """
    Modeli YEREL kaynaklardan çöz (EXE bundle / ProgramData / release_assets).
    Hugging Face indirme KALDIRILDI — internet erişimi yoktur.
    repo_path: örn 'ai_hub/inference_renal_histopath_kmc/v22_kmc_classictrio_kmc.onnx'
    """
    installed_path = find_installed_model(repo_path)
    if installed_path:
        return installed_path

    raise FileNotFoundError(
        f"Model bulunamadı: {repo_path}. Modeller EXE'ye gömülü ya da "
        f"ProgramData\\PEMF_GUI\\ai_models / release_assets altında olmalı "
        f"(Hugging Face indirme kaldırıldı)."
    )
