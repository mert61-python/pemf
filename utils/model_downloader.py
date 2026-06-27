import os
import sys
from pathlib import Path

# PyQt6 is GUI-only. The headless backend imports this module (through the AI
# router) ONLY for download_model_sync(), which is pure Python. Guard the Qt
# import so the module loads cleanly when PyQt6 is absent (Qt-free service /
# frozen EXE). HFModelDownloader (QThread) below is used solely by the legacy GUI
# and is never instantiated in headless mode.
try:
    from PyQt6.QtCore import QThread, pyqtSignal
except ImportError:  # pragma: no cover - headless backend without PyQt6
    class QThread:  # type: ignore
        """Minimal stub so HFModelDownloader can still be class-defined headless."""

        def __init__(self, *args, **kwargs):
            pass

    def pyqtSignal(*args, **kwargs):  # type: ignore
        return None
import warnings
import socket

# hf_xet vb. uyarilari gizle
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from huggingface_hub import hf_hub_download
from huggingface_hub.errors import HfHubHTTPError

DEFAULT_REPO_ID = "Mertaygn61/PEMF-AI-Models"
HF_TOKEN_ENV_VARS = ("PEMF_HF_TOKEN", "HF_TOKEN", "HUGGINGFACE_HUB_TOKEN")

def check_internet():
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=3)
        return True
    except OSError:
        return False

from utils.path_utils import get_app_data_directory, resource_path


def _get_hf_token():
    """Production'da token kodda durmaz; gerekiyorsa ortam değişkeninden gelir."""
    for env_name in HF_TOKEN_ENV_VARS:
        token = os.environ.get(env_name, "").strip()
        if token:
            return token
    if sys.platform == "win32":
        try:
            import winreg
            wanted = {name.lower() for name in HF_TOKEN_ENV_VARS}
            for hive, subkey in (
                (winreg.HKEY_CURRENT_USER, "Environment"),
                (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            ):
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        value_count = winreg.QueryInfoKey(key)[1]
                        for index in range(value_count):
                            name, value, _ = winreg.EnumValue(key, index)
                            if name.lower() in wanted and str(value).strip():
                                return str(value).strip()
                except OSError:
                    continue
        except Exception:
            pass
    return None


def _format_download_error(repo_id: str, repo_path: str, exc: Exception) -> str:
    status_code = None
    response = getattr(exc, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)

    if isinstance(exc, HfHubHTTPError) and status_code in (401, 403):
        token_hint = (
            "HF token tanımlı değil. "
            "PEMF_HF_TOKEN, HF_TOKEN veya HUGGINGFACE_HUB_TOKEN ortam değişkenlerinden "
            "birine bu repo için yetkili token tanımlayın."
            if _get_hf_token() is None
            else "Tanımlı HF token bu repo/dosya için yetkili değil."
        )
        return (
            f"Hugging Face erişim hatası ({status_code}). "
            f"Repo private/gated olabilir veya dosyaya erişim izni yok. {token_hint} "
            f"Alternatif: modeli release_assets\\ai_models altına ekleyip installer'ın "
            f"'AI Paketlerini Kur' bileşeniyle offline kurun. "
            f"Repo: {repo_id}, Dosya: {repo_path}"
        )

    return f"Model indirme hatası ({repo_id}/{repo_path}): {exc}"


def get_persistent_model_dir() -> Path:
    """Kullanıcıya özel kalıcı model cache klasörü."""
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
    4. PyInstaller bundle içindeki ai_models klasörü (opsiyonel)
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


def find_installed_model(repo_path: str):
    """
    Inno ile kurulan ya da daha once indirilen modeli bulur.
    Paket formatı ideal olarak repo_path ile aynıdır:
    ai_models/ai_hub/cat_landmark/yolo26m-pose.onnx
    """
    normalized = Path(os.path.normpath(repo_path))
    basename = normalized.name

    for root in _candidate_model_roots():
        candidates = [
            root / normalized,
            root / basename,
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return str(candidate)
    return None

class HFModelDownloader(QThread):
    """
    Arka planda Hugging Face üzerinden model indirir.
    GUI'yi dondurmamak için QThread kullanır.
    """
    # Sinyaller
    started_download = pyqtSignal()
    finished = pyqtSignal(str) # İnen dosyanın tam yolu
    error = pyqtSignal(str)

    def __init__(self, repo_id, filename, save_dir_name="ai_models"):
        super().__init__()
        self.repo_id = repo_id or DEFAULT_REPO_ID
        self.filename = filename

        self.local_dir = str(get_persistent_model_dir())
        self.token = _get_hf_token()
        self.final_file_path = os.path.join(self.local_dir, os.path.normpath(filename))

    def run(self):
        try:
            # Eğer model Inno AI paketiyle kurulmuşsa veya daha önce inmişse hızlıca dön
            installed_path = find_installed_model(self.filename)
            if installed_path:
                self.finished.emit(installed_path)
                return

            # Dosya yoksa indirmeyi başlat
            self.started_download.emit()
            
            if not check_internet():
                self.error.emit("İnternet Bağlantısı Yok! Modelleri indirebilmek için lütfen internete bağlanın.")
                return
                
            # Hugging Face üzerinden indir
            downloaded_path = hf_hub_download(
                repo_id=self.repo_id,
                filename=self.filename,
                local_dir=self.local_dir,
                token=self.token
            )
            
            self.finished.emit(downloaded_path)
        
        except Exception as e:
            self.error.emit(_format_download_error(self.repo_id, self.filename, e))

def download_model_sync(repo_path: str):
    """
    Halihazırda bir QThread içerisinde olan işlemler için senkron model indirme fonksiyonu.
    Gerekirse modeli indirir, varsa olan yolu döner.
    repo_path: Örn 'ai_hub/cat_landmark/yolo26m-pose.onnx'
    """
    installed_path = find_installed_model(repo_path)
    if installed_path:
        return installed_path

    if not check_internet():
        raise ConnectionError(
            "İnternet Bağlantısı Yok! Yapay zeka modellerini ilk kullanım için "
            "indirmek veya Inno Setup'ta 'AI Paketlerini Kur' seçeneğiyle kurmak gerekiyor."
        )

    persistent_model_dir = get_persistent_model_dir()
    print(f"Hugging Face'ten model indiriliyor: {repo_path}")

    try:
        downloaded_path = hf_hub_download(
            repo_id=DEFAULT_REPO_ID,
            filename=repo_path,
            local_dir=str(persistent_model_dir),
            token=_get_hf_token()
        )
    except Exception as exc:
        raise RuntimeError(_format_download_error(DEFAULT_REPO_ID, repo_path, exc)) from exc

    return downloaded_path
