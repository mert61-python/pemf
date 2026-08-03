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
import socket
import subprocess
import sys
import threading
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
    # Audit P3: bozuk/0-byte cache ASLA yeniden inmiyordu (bin_path.exists()→skip → Popen bozuk binary
    # → watchdog sonsuz relaunch). Cache'i BOYUTLA doğrula; şüpheli-küçükse yeniden indir (self-heal).
    if bin_path.exists() and bin_path.stat().st_size >= 5_000_000:
        logger.info("cloudflared zaten mevcut: %s", bin_path)
        return bin_path

    _BIN_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("cloudflared indiriliyor: %s", url)

    try:
        # Audit P3: ATOMİK indir — temp'e yaz + boyut doğrula + os.replace. Eskiden doğrudan bin_path'e
        # yazılıyordu; indirme kesilirse 0-byte/kesik dosya kalıp bir daha inmiyordu.
        import os as _os
        import tempfile as _tf
        _fd, _tmp = _tf.mkstemp(dir=str(_BIN_DIR), suffix=".part")
        try:
            with urllib.request.urlopen(url, timeout=60) as response, _os.fdopen(_fd, "wb") as f:
                f.write(response.read())
            _sz = _os.path.getsize(_tmp)
            if _sz < 5_000_000:
                raise ValueError(f"cloudflared indirmesi çok küçük ({_sz} bytes) — bozuk/kesik.")
            # DENETIM P3 (macOS): Darwin varliği .tgz ARSIVIDIR. Eskiden arsiv dogrudan
            # "cloudflared-darwin" adiyla kaydedilip CALISTIRILIYORDU → exec basarisiz olur,
            # ustelik dosya 5 MB esigini gectigi icin cache "gecerli" sayilip BIR DAHA
            # INDIRILMEZ; watchdog sonsuz yeniden-baslatma dongusune girer. Arsivi ac ve
            # ICINDEKI gercek ikiliyi yaz.
            if system == "Darwin":
                import tarfile as _tar
                _member_path = None
                with _tar.open(_tmp, "r:gz") as _tf_arch:
                    for _m in _tf_arch.getmembers():
                        if _m.isfile() and _os.path.basename(_m.name) == "cloudflared":
                            _member_path = _m
                            break
                    if _member_path is None:
                        raise ValueError("cloudflared .tgz icinde 'cloudflared' ikilisi bulunamadi.")
                    _extracted = _tf_arch.extractfile(_member_path)
                    with _os.fdopen(_os.open(_tmp + ".bin", _os.O_WRONLY | _os.O_CREAT | _os.O_TRUNC, 0o755), "wb") as _bf:
                        _bf.write(_extracted.read())
                _os.replace(_tmp + ".bin", bin_path)
                try:
                    _os.unlink(_tmp)          # arsivi birakma
                except Exception:
                    pass
            else:
                _os.replace(_tmp, bin_path)
        except Exception:
            try:
                _os.unlink(_tmp)
            except Exception:
                pass
            raise

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
            new_url = match.group(0)
            with _tunnel_lock:
                changed = (new_url != _tunnel_url)
                _tunnel_url = new_url
            if changed:
                logger.info("=" * 60)
                logger.info("🌐 UZAKTAN ERİŞİM LİNKİNİZ: %s", new_url)
                logger.info("=" * 60)
                # Kayıtlı callback'leri çağır (sync_worker → Supabase'e ANINDA yeniden yayın).
                for cb in list(_url_callbacks):
                    try:
                        cb(new_url)
                    except Exception:
                        pass
            # break KALDIRILDI: cloudflared aynı süreçte URL'yi DEĞİŞTİREBİLİR (reconnect) → okumaya
            # DEVAM et; değişince _tunnel_url güncellenir + callback'ler tetiklenir (audit: stale URL yayını).


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
    global _tunnel_process, _tunnel_thread, _tunnel_url

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

    # ÜRETİM (P1): PEMF_CLOUDFLARE_TUNNEL_TOKEN ayarlıysa NAMED tunnel — KALICI hostname +
    # SLA + (istenirse) Cloudflare Access. Yoksa QUICK tunnel (trycloudflare, URL her restart
    # değişir, SLA yok) — geliştirme/yedek. Tıbbi üretimde NAMED + sabit hostname önerilir.
    # TEK-DOSYA: SecretsManager (env → pemf_secrets.json operator bölümü). Boşsa QUICK tunnel.
    try:
        from utils.secrets_manager import get_secret
        token = get_secret("cloudflare_tunnel_token")
        hostname = get_secret("tunnel_hostname")
    except Exception:
        token = os.environ.get("PEMF_CLOUDFLARE_TUNNEL_TOKEN", "").strip()
        hostname = os.environ.get("PEMF_TUNNEL_HOSTNAME", "").strip()
    # GEÇERSİZ/PLACEHOLDER token koruması: GERÇEK cloudflared token uzun base64'tür (eyJ..., ~180+ char).
    # Kısa/bogus token (ör. eski test artığı "1") NAMED tünel'i çökertip tünel URL'sini NULL bırakıyordu →
    # Supabase'e null yazılıyor → UZAKTAN ERİŞİM ÇALIŞMIYORDU. İmplausibly-kısa token'ı YOK SAY → QUICK tünel
    # (gerçek trycloudflare URL üretir, uzaktan erişim çalışır). Geçerli named token etkilenmez.
    token = (token or "").strip()
    if token and len(token) < 40:
        logger.warning("cloudflare_tunnel_token geçersiz/placeholder (uzunluk %d) → YOK SAYILDI, QUICK tünele düşülüyor.", len(token))
        token = ""
    if token:
        cmd = [str(bin_path), "tunnel", "run", "--token", token]
        logger.info("Cloudflare NAMED tunnel başlatılıyor (kalıcı hostname, üretim-grade).")
    else:
        cmd = [str(bin_path), "tunnel", "--url", f"http://localhost:{port}"]
        logger.info("Cloudflare QUICK tunnel başlatılıyor → port %d (URL her restart DEĞİŞİR; üretimde NAMED önerilir).", port)

    try:
        # DEADLOCK fix: NAMED+hostname dalı (aşağıda) stderr-okuma thread'i BAŞLATMADAN döner. O durumda
        # stderr=PIPE hiç boşaltılmaz → ~64KB OS pipe buffer'ı dolunca cloudflared write()'ta BLOKLANIR
        # ve tünel ölür (uzaktan erişim kopar). Okumayacaksak stderr=DEVNULL; okuyacaksak (QUICK veya
        # hostname'siz named → reader thread var) PIPE. stdout zaten hiç okunmuyor → daima DEVNULL.
        _stderr_read = not (token and hostname)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=(subprocess.PIPE if _stderr_read else subprocess.DEVNULL),
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
        with _tunnel_lock:
            _tunnel_process = process

        # NAMED tunnel'da hostname SABİT (config'ten gelir) → stderr'den URL parse etmeye gerek yok.
        if token and hostname:
            url = hostname if hostname.startswith("http") else f"https://{hostname}"
            with _tunnel_lock:
                _tunnel_url = url
            logger.info("🌐 NAMED tunnel kalıcı hostname: %s", url)
            for cb in list(_url_callbacks):
                try:
                    cb(url)
                except Exception:
                    pass
            return True

        # QUICK tunnel: trycloudflare URL'sini stderr'den okuma thread'i ile yakala.
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


# ── WATCHDOG (SIFIR-MÜDAHALE uzaktan erişim) ────────────────────────────────────
# Qt NetworkMonitor headless yolda ÖLÜ KOD → saf threading + socket ile internet
# izleyip tüneli (yeniden) başlatan tek daemon. Kapsadığı 3 durum:
#   (1) internetsiz boot → WiFi sonradan bağlanınca tünel OTOMATİK açılır,
#   (2) cloudflared süreci ölürse OTOMATİK yeniden başlar,
#   (3) internet düşüp gelince OTOMATİK toparlar.
# NAMED tünelde cloudflared kendi reconnect'ini yapar; bu watchdog süreç-ölümünü kapsar.
_INTERNET_HOSTS = [("1.1.1.1", 53), ("8.8.8.8", 53)]  # DNS portuna TCP connect = hafif internet kontrolü
_watchdog_thread: threading.Thread | None = None
_watchdog_stop = threading.Event()


def _internet_up(timeout: float = 3.0) -> bool:
    """Herhangi bir DNS host'una (53/tcp) bağlanılabiliyorsa internet VAR kabul edilir."""
    for host, port in _INTERNET_HOSTS:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def _tunnel_alive() -> bool:
    """cloudflared süreci canlı mı?"""
    with _tunnel_lock:
        return _tunnel_process is not None and _tunnel_process.poll() is None


def _tunnel_url_alive(timeout: float = 6.0) -> bool:
    """Quick tünel URL'si DIŞARIDAN gerçekten forward ediyor mu? cloudflared süreci canlı olsa da
    edge ölebilir (idle-reap/rate-limit) → process.poll() yetmez. Cihaz→Cloudflare→cihaz round-trip
    ile /api/health erişilebilir mi diye bakar. URL henüz yoksa True döner (process kontrolüne bırak)."""
    with _tunnel_lock:
        url = _tunnel_url
    if not url:
        return True
    try:
        with urllib.request.urlopen(url + "/api/health", timeout=timeout) as r:
            code = getattr(r, "status", None) or r.getcode()
            return 200 <= int(code) < 500
    except Exception:
        return False


def start_tunnel_watchdog(port: int = 8000, check_interval: int = 20) -> None:
    """Tünel watchdog daemon'ını başlatır (tek-seferlik start_tunnel yerine).

    İnternet VARSA ve tünel YOKSA/ÖLÜYSE (yeniden) başlatır; çevrimdışıyken denemez
    (doomed subprocess açmaz, yerel çalışmaya dokunmaz). Başarısızlıkta exp backoff.
    """
    global _watchdog_thread
    if _watchdog_thread and _watchdog_thread.is_alive():
        return
    _watchdog_stop.clear()

    def _loop():
        backoff = check_interval
        max_backoff = 300
        dead_url_strikes = 0
        while not _watchdog_stop.is_set():
            try:
                if not _internet_up():
                    _watchdog_stop.wait(check_interval)   # çevrimdışı → sadece bekle (yerel etkilenmez)
                    continue
                if _tunnel_alive():
                    # Süreç canlı; ama quick tünel edge'i ölmüş olabilir (forward yok). DIŞ URL'yi probe et;
                    # 2 ardışık ölüde yeniden başlat (audit P0: ölü-URL Supabase'e yayınlanmaya devam ediyordu).
                    if _tunnel_url_alive():
                        dead_url_strikes = 0
                        backoff = check_interval           # sağlıklı → normal aralıkta tekrar bak
                        _watchdog_stop.wait(check_interval)
                        continue
                    dead_url_strikes += 1
                    if dead_url_strikes < 2:
                        logger.info("Tünel watchdog: dış URL probe başarısız (%d/2) → bir tur daha bekleniyor.", dead_url_strikes)
                        _watchdog_stop.wait(check_interval)
                        continue
                    logger.warning("Tünel watchdog: süreç canlı ama DIŞ URL ölü → tünel yeniden başlatılıyor.")
                    dead_url_strikes = 0
                    # düş → aşağıda stop_tunnel + start_tunnel (yeni URL alınır + yayınlanır)
                stop_tunnel()                              # yarı-ölü süreç varsa temizle (None ise zararsız)
                logger.info("Tünel watchdog: internet VAR, tünel yok/ölü → (yeniden) başlatılıyor.")
                if start_tunnel(port=port):
                    backoff = check_interval
                    _watchdog_stop.wait(check_interval)    # QUICK tünel URL'yi yakalasın diye bekle
                else:
                    logger.warning("Tünel watchdog: başlatma başarısız, %ds sonra tekrar.", backoff)
                    _watchdog_stop.wait(backoff)
                    backoff = min(backoff * 2, max_backoff)
            except Exception:
                logger.exception("Tünel watchdog döngü hatası (devam ediliyor).")
                _watchdog_stop.wait(check_interval)

    _watchdog_thread = threading.Thread(target=_loop, daemon=True, name="CloudflareTunnelWatchdog")
    _watchdog_thread.start()
    logger.info("Cloudflare tünel watchdog başlatıldı (internet geldikçe/gittikçe uzaktan erişim otomatik).")
