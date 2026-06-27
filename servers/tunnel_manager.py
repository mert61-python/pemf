"""
PEMF Cloudflare Tunnel Manager
===============================
`cloudflared` binary'yi otomatik olarak indirip arka planda başlatır.
Oluşturulan geçici public URL'yi kayıt defterine/ekrana yazar.

Kullanım:
    from servers.tunnel_manager import start_tunnel, get_tunnel_url, stop_tunnel
    start_tunnel(port=8000)
    url = get_tunnel_url()   # Örn: "https://abcd-xyz.trycloudflare.com"
"""
from __future__ import annotations

import logging
import os
import platform
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Durum ──────────────────────────────────────────────────────────────────────
_tunnel_process: subprocess.Popen | None = None
_tunnel_url: str = ""
_tunnel_lock = threading.Lock()
_tunnel_thread: threading.Thread | None = None
_url_callbacks: list = []  # URL hazır olunca çağrılacak fonksiyonlar

# ── Cloudflared Binary Konumu ──────────────────────────────────────────────────
_BIN_DIR = Path(os.environ.get("APPDATA", Path.home())) / "PEMF_GUI" / "cloudflared"

def _get_binary_path() -> Path:
    """OS'a göre cloudflared binary yolunu döndürür."""
    system = platform.system()
    if system == "Windows":
        return _BIN_DIR / "cloudflared.exe"
    elif system == "Darwin":
        return _BIN_DIR / "cloudflared-darwin"
    else:
        return _BIN_DIR / "cloudflared-linux"


def _bundled_cloudflared() -> Path | None:
    """Uygulamayla PAKETLENMİŞ cloudflared binary'sini ara (offline kurulum). PyInstaller
    _MEIPASS, EXE yanı ve kaynak bin/ dizinleri. Audit #18: eskiden yalnız runtime'da
    GitHub'dan iniyordu → internetsiz sahada kurulum bozuluyordu."""
    system = platform.system()
    fname = "cloudflared.exe" if system == "Windows" else (
        "cloudflared-darwin" if system == "Darwin" else "cloudflared-linux")
    roots = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            roots.append(Path(meipass) / "bin" / "cloudflared")
        roots.append(Path(sys.executable).resolve().parent / "bin" / "cloudflared")
    roots.append(Path(__file__).resolve().parent.parent / "bin" / "cloudflared")
    for r in roots:
        try:
            cand = r / fname
            if cand.exists() and cand.is_file():
                return cand
        except Exception:
            pass
    return None


def _download_cloudflared() -> Path | None:
    """cloudflared binary'yi (varsa) PAKETTEN kullanır, yoksa resmi GitHub release'den indirir."""
    bundled = _bundled_cloudflared()
    if bundled is not None:
        logger.info("cloudflared paketlenmiş binary kullanılıyor (offline): %s", bundled)
        return bundled

    system = platform.system()
    machine = platform.machine().lower()

    if system == "Windows":
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
        filename = "cloudflared.exe"
    elif system == "Darwin":
        arch = "arm64" if "arm" in machine else "amd64"
        url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-{arch}.tgz"
        filename = "cloudflared-darwin"
    else:
        arch = "arm64" if "arm" in machine else "amd64"
        url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{arch}"
        filename = "cloudflared-linux"

    bin_path = _BIN_DIR / filename
    if bin_path.exists():
        logger.info("cloudflared zaten mevcut: %s", bin_path)
        return bin_path

    _BIN_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("cloudflared indiriliyor: %s", url)

    try:
        with urllib.request.urlopen(url, timeout=60) as response, open(bin_path, "wb") as f:
            f.write(response.read())

        # Linux/macOS: çalıştırma izni ver
        if system != "Windows":
            bin_path.chmod(0o755)
            # Eğer tgz ise çıkart
            if str(url).endswith(".tgz"):
                import tarfile
                with tarfile.open(bin_path, "r:gz") as tar:
                    tar.extractall(_BIN_DIR)

        logger.info("cloudflared indirildi: %s", bin_path)
        return bin_path
    except Exception as e:
        logger.error("cloudflared indirilemedi: %s", e)
        return None


def _read_url_from_output(process: subprocess.Popen, port: int) -> None:
    """cloudflared'in stderr çıktısından public URL'yi okur."""
    global _tunnel_url
    url_pattern = re.compile(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com")

    for line in iter(process.stderr.readline, b""):
        try:
            decoded = line.decode("utf-8", errors="replace").strip()
        except Exception:
            continue

        if decoded:
            logger.debug("[cloudflared] %s", decoded)

        match = url_pattern.search(decoded)
        if match:
            with _tunnel_lock:
                _tunnel_url = match.group(0)
            logger.info("=" * 60)
            logger.info("🌐 UZAKTAN ERİŞİM LİNKİNİZ: %s", _tunnel_url)
            logger.info("   Mobil uygulamada Ayarlar > Sunucu IP kısmına")
            logger.info("   bu adresi yapıştırın.")
            logger.info("=" * 60)

            # Kayıtlı callback'leri çağır (GUI'ye link iletmek için)
            for cb in list(_url_callbacks):
                try:
                    cb(_tunnel_url)
                except Exception:
                    pass
            break  # URL bulunduktan sonra okumaya devam etmeye gerek yok


def get_tunnel_url() -> str:
    """Aktif tünel URL'sini döndürür. Hazır değilse boş string."""
    with _tunnel_lock:
        return _tunnel_url


def register_url_callback(callback) -> None:
    """URL hazır olunca çağrılacak bir fonksiyon kaydet (GUI güncellemesi için)."""
    _url_callbacks.append(callback)


def start_tunnel(port: int = 8000) -> bool:
    """
    Cloudflare Tünelini başlatır.
    Returns True if started successfully, False otherwise.
    """
    global _tunnel_process, _tunnel_thread

    with _tunnel_lock:
        if _tunnel_process and _tunnel_process.poll() is None:
            logger.info("Tünel zaten çalışıyor: %s", _tunnel_url)
            return True

    # Binary'yi bul veya indir
    bin_path = _get_binary_path()
    if not bin_path.exists():
        logger.info("cloudflared binary bulunamadı, indiriliyor...")
        bin_path = _download_cloudflared()
        if not bin_path:
            logger.error("cloudflared binary hazırlanamadı, tünel başlatılamıyor.")
            return False

    cmd = [str(bin_path), "tunnel", "--url", f"http://localhost:{port}"]
    logger.info("Cloudflare tüneli başlatılıyor → port %d", port)

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
        with _tunnel_lock:
            _tunnel_process = process

        # URL okuma thread'ini başlat
        _tunnel_thread = threading.Thread(
            target=_read_url_from_output,
            args=(process, port),
            daemon=True,
            name="CloudflareTunnelReader",
        )
        _tunnel_thread.start()
        return True
    except Exception as e:
        logger.error("Tünel başlatma hatası: %s", e)
        return False


def stop_tunnel() -> None:
    """Cloudflare tünelini durdurur."""
    global _tunnel_process, _tunnel_url
    with _tunnel_lock:
        proc = _tunnel_process
        _tunnel_process = None
        _tunnel_url = ""

    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        logger.info("Cloudflare tüneli durduruldu.")
