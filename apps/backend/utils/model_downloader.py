# Author: mertaygn, cglrgrkn
"""model_downloader.py — YEREL model çözümü (Hugging Face KALDIRILDI).

NOT (2026-07, kullanıcı kararı): Hugging Face indirme tamamen kaldırıldı. Tüm AI
modelleri artık offline paketlenir — EXE'ye gömülü ya da ProgramData\\PEMF_GUI\\ai_models
/ release_assets altında staged. Bu modül yalnızca YEREL arama yapar; ağ erişimi,
HF token'ı veya huggingface_hub bağımlılığı YOKTUR. Public API (download_model_sync,
find_installed_model) korunur.
"""

import hashlib
import json
import logging
import os
import sys
from pathlib import Path

from utils.path_utils import get_app_data_directory, kaynak_kokunu_bul, resource_path

logger = logging.getLogger(__name__)

#: D3.48 (B-5.14 · Y18): takipli ağırlık özetleri — D3.45 `release_assets/ai_models_sha256.json` (göreli yol → SHA-256);
#: donmuş pakette `_internal/ai_hub/` altında (APP katmanı — her uygulama sürümüyle tazelenir; spec ekler, yoksa derleme DURUR).
_MANIFEST_ADI = "ai_models_sha256.json"
#: Aday manifest yolları → özetler (kök yeri değişirse — ör. testte `__file__` yönlendirilirse — yeniden okunur).
_manifest_onbellegi: dict[tuple[str, ...], dict[str, str]] = {}
_ozet_onbellegi: dict[tuple[str, int, int], str] = {}


class ModelButunlukHatasi(RuntimeError):
    """D3.48 · Y18 (sahip): model / yan dosya beklenen SHA-256 ile AYNI DEĞİL (ya da özet okunamadı) — YÜKLENMEZ, başka model
    köküne DÜŞÜLMEZ; AI ucu 503 + açık uyarı (`ai_router._ai_fail`). Manuel seans ve ACİL DURDUR etkilenmez."""

    def __init__(self, dosya, sebep: str):
        super().__init__(f"model butunluk denetimi gecmedi: {dosya} ({sebep})")
        self.dosya = str(dosya)
        self.sebep = sebep


def _goreli_anahtar(goreli) -> str:
    return str(goreli).replace(chr(92), "/")


def _manifest_ozetleri() -> dict[str, str]:
    """Göreli yol → beklenen SHA-256 (takipli manifest; donmuşta paketteki kopya). Bulunamazsa {} — denetim yalnız `.sha256`
    yan dosyasıyla yapılır (manifestsiz eski paket: davranış ESKİSİ GİBİ, ama günlükte görünür)."""
    adaylar = []
    try:
        adaylar.append(Path(resource_path(os.path.join("ai_hub", _MANIFEST_ADI))))
    except Exception:
        logger.debug("model manifesti: paket yolu çözülemedi", exc_info=True)
    try:
        adaylar.append(kaynak_kokunu_bul(__file__) / "release_assets" / _MANIFEST_ADI)
    except Exception:
        logger.debug("model manifesti: kaynak kökü çözülemedi", exc_info=True)
    anahtar = tuple(str(a) for a in adaylar)
    if anahtar not in _manifest_onbellegi:
        ozetler: dict[str, str] = {}
        for aday in adaylar:
            try:
                if aday.is_file():
                    veri = json.loads(aday.read_text(encoding="utf-8"))
                    ozetler = {_goreli_anahtar(k): str(v["sha256"]).lower() for k, v in veri["dosyalar"].items()}
                    break
            except Exception:
                logger.error(
                    "Model bütünlük manifesti OKUNAMADI: %s — denetim yalnız yan dosyalarla yapılır",
                    aday,
                    exc_info=True,
                )
        if not ozetler:
            logger.warning(
                "Model bütünlük manifesti YOK (%s) — ağırlıklar yalnız asgari boyut / yan dosya ile denetlenir", adaylar
            )
        _manifest_onbellegi[anahtar] = ozetler
    return _manifest_onbellegi[anahtar]


def _dosya_ozeti(yol: Path) -> str:
    """SHA-256 (yol + boyut + değişiklik zamanı ile önbellekli — her yüklemede büyük ağırlık yeniden özetlenmez)."""
    st = yol.stat()
    anahtar = (os.path.normcase(os.path.abspath(str(yol))), st.st_size, st.st_mtime_ns)
    ozet = _ozet_onbellegi.get(anahtar)
    if ozet is None:
        h = hashlib.sha256()
        with open(yol, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        ozet = _ozet_onbellegi[anahtar] = h.hexdigest()
    return ozet


def butunluk_sebebi(path, goreli=None) -> str | None:
    """D3.48: ağırlığın bütünlük kararı — None (geçer) · `kucuk` (asgari boyutun altında: kesik / yarım) · `ozet` (beklenen SHA-256
    tutmuyor) · `dogrulanamadi` (beklenen özet VAR ama dosya / özet okunamadı). Beklenen özet: `<dosya>.sha256` yan dosyası, yoksa
    takipli manifestte `goreli` (`ai_hub/<modül>/<dosya>`). Hiçbiri yoksa yalnız asgari boyut."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError:
        return "dogrulanamadi"
    min_bytes = _MODEL_MIN_BYTES.get(path.suffix.lower(), 1)
    if size < min_bytes:
        logger.error(
            "Model bütünlük UYARISI: %s beklenenden küçük (%d B < %d B) — kesik / yarım.", path, size, min_bytes
        )
        return "kucuk"
    sha_file = path.with_name(path.name + ".sha256")
    try:
        if sha_file.exists():
            beklenen = sha_file.read_text(encoding="utf-8").split()[0].strip().lower()
        else:
            beklenen = _manifest_ozetleri().get(_goreli_anahtar(goreli)) if goreli else None
        if not beklenen:
            return None
        if _dosya_ozeti(path).lower() != beklenen:
            logger.error(
                "Model bütünlük REDDİ: %s SHA-256 beklenenle AYNI DEĞİL (%s) — yüklenmez.",
                path,
                goreli or sha_file.name,
            )
            return "ozet"
        return None
    except Exception:
        logger.error("Model bütünlük DOĞRULANAMADI: %s — reddedildi (fail-closed).", path, exc_info=True)
        return "dogrulanamadi"


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
        roots.append(kaynak_kokunu_bul(__file__) / "release_assets" / "ai_models")
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


def _model_integrity_ok(path: Path, goreli: str | None = None) -> bool:
    """Yarım/bozuk modeli 'kurulu' saymamak için bütünlük sağlaması (audit P2): asgari boyut + beklenen SHA-256 (yan dosya ya da
    D3.48 takipli manifest). ⚠️ İG-5.40: ret eskiden yalnız `print` ile yazılıyordu (donmuş EXE'de stdout NUL) → artık günlükte."""
    return butunluk_sebebi(path, goreli) is None


def find_installed_model(repo_path: str):
    """
    EXE'ye gömülü ya da ProgramData/release_assets altında kurulu modeli bulur.
    Paket formatı repo_path ile aynıdır: ai_models/ai_hub/<model>/<file>.onnx
    Bulamazsa None döner.
    """
    normalized = Path(os.path.normpath(repo_path))
    basename = normalized.name
    goreli = normalized.as_posix()

    for root in _candidate_model_roots():
        candidates = [
            root / normalized,
            root / basename,
        ]
        for candidate in candidates:
            if not (candidate.exists() and candidate.is_file()):
                continue
            sebep = butunluk_sebebi(candidate, goreli)
            if sebep is None:
                return str(candidate)
            # ⚠️ D3.48 · İG-5.40: özeti TUTMAYAN (kurcalanmış / başka sürüm) ağırlık sonraki köke SESSİZCE ikame edilmez — HATA.
            # Kesik (asgari boyut altı) kopyada eski davranış: sonraki köke bakılır (yarım kurulum), ret günlükte.
            if sebep != "kucuk":
                raise ModelButunlukHatasi(candidate, sebep)
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


def yan_dosya_coz(yerel_yol, repo_yolu: str) -> str:
    """Modelin YANINDAKİ dosyayı (scaler / encoder / preprocessor) çöz.

    ⚠️ DENETİM 2026-08-28 #09 — ÖLÇÜLEN ARIZA. AI modülleri ANA modeli
    `download_model_sync` ile `/models` mount'undan çözüyor ama yanındaki scaler/encoder
    dosyaları modül dizinine (`_DIR`) SABİT kalıyordu. Docker imajında
    `docker/Dockerfile.backend.dockerignore` `ai_hub/**/*.pkl|*.onnx|*.pt` desenini eliyor →
    imajda o dosyalar YOK. Ölçüldü (imaj düzeni birebir kurulup koşuldu):

        cat_disease      MODEL_PATH var: True   SCALER_PATH var: False  → FileNotFoundError
        em_kedi          ONNX var: True         3 scaler var: False
        kidney_disease   (hiç fallback yok)                              → FileNotFoundError

    Yani monolit Docker profilinde kedi-hastalık, böbrek-hastalık ve AI Pro doz uçları
    ölüydü. Gerekli dosyaların hepsi `/models` ağacında MEVCUT — sadece oraya bakılmıyordu.

    ⚠️ KLİNİK (frozen EXE) YOLU ETKİLENMEZ: `PEMF_Backend_onedir.spec` 5 MB altı
    `.pkl/.onnx/.npy/.npz` dosyalarını modülün YANINA gömer, dolayısıyla ilk koşul tutar ve
    fonksiyon hemen döner — çözücüye hiç girilmez.

    Args:
        yerel_yol: modül dizinindeki varsayılan yol (str | Path)
        repo_yolu: `ai_hub/<modül>/<dosya>` biçiminde paket-göreli yol
    Returns:
        Var olan bir yol (bulunamazsa `yerel_yol` — çağıran kendi hatasını üretsin).
    """
    try:
        if os.path.exists(str(yerel_yol)):
            # D3.48 (B-5.14): modül YANINDAKİ dosya (donmuşta `_internal/ai_hub/…`, <5 MB) da yüklemeden ÖNCE özetle denetlenir —
            # eskiden doğrudan dönüyordu: ×1,10 kurcalanmış doz ölçekleyicisi uyarısız yükleniyordu (plan B-5.14).
            sebep = butunluk_sebebi(Path(yerel_yol), repo_yolu)
            if sebep in ("ozet", "dogrulanamadi"):
                raise ModelButunlukHatasi(yerel_yol, sebep)
            return str(yerel_yol)
        bulunan = find_installed_model(repo_yolu)
        return bulunan or str(yerel_yol)
    except ModelButunlukHatasi:
        raise
    except Exception:
        return str(yerel_yol)
