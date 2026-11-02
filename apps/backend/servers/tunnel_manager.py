# Author: mertaygn, cglrgrkn
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

import hashlib
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import urllib.request
from pathlib import Path

from utils.dongu_guvenligi import dongu_hatasini_bildir

logger = logging.getLogger(__name__)

# ── Durum ──────────────────────────────────────────────────────────────────────
_tunnel_process: subprocess.Popen | None = None
_tunnel_url: str = ""
_tunnel_lock = threading.Lock()
_tunnel_thread: threading.Thread | None = None
_url_callbacks: list = []  # URL hazır olunca çağrılacak fonksiyonlar

# ── Cloudflared Binary Konumu ──────────────────────────────────────────────────
_BIN_DIR = Path(os.environ.get("APPDATA", Path.home())) / "PEMF_GUI" / "cloudflared"


def _bundled_cloudflared() -> Path | None:
    """Uygulamayla PAKETLENMİŞ cloudflared binary'sini ara (offline kurulum). PyInstaller
    _MEIPASS, EXE yanı ve kaynak bin/ dizinleri. Audit #18: eskiden yalnız runtime'da
    GitHub'dan iniyordu → internetsiz sahada kurulum bozuluyordu."""
    system = platform.system()
    fname = (
        "cloudflared.exe"
        if system == "Windows"
        else ("cloudflared-darwin" if system == "Darwin" else "cloudflared-linux")
    )
    roots = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            roots.append(Path(meipass) / "bin" / "cloudflared")
        roots.append(Path(sys.executable).resolve().parent / "bin" / "cloudflared")
    from utils.path_utils import kaynak_kokunu_bul

    roots.append(kaynak_kokunu_bul(__file__) / "bin" / "cloudflared")
    for r in roots:
        try:
            cand = r / fname
            if cand.exists() and cand.is_file():
                return cand
        except Exception:
            pass
    return None


# D3.35 (B-4.13): indirme SÜRÜM-PİNLİ ve ÖZETLİ. Eskiden `releases/latest` (sürümü belirsiz) gövdesi özet denetimi olmadan
# yerleşip Popen ediliyordu; `response.read()` boyut sınırsızdı. Sürüm = paketlenen ikilinin gömülü `main.Version`ı; Windows özeti
# paketlenen ikilinin SHA-256'sı (18K K6 ölçümü: 54 166 424 B, Authenticode "Cloudflare, Inc."). Özeti BİLİNMEYEN varlık İNDİRİLMEZ
# (fail-closed) — macOS / Linux özetleri resmi sürümden doldurulana kadar o platformlarda tünel yalnız paketli ikiliyle çalışır.
_CLOUDFLARED_SURUM = "2026.6.1"
_CLOUDFLARED_OZET: dict[str, str] = {
    "cloudflared-windows-amd64.exe": "5253e66f1f493c4e13539749f1aa86fd0c61e3072900fec29a44ba046a6d97e2",
}
_ASGARI_BOYUT = 5_000_000  # bundan küçük önbellek / indirme bozuk-kesik sayılır (Audit P3)
_AZAMI_INDIRME = 150 * 1024 * 1024  # gövde (ve arşivden çıkan ikili) boyut tavanı — Windows ikilisi ~52 MB
_PARCA = 1024 * 1024


def _varlik_adi() -> tuple[str, str]:
    """(GitHub sürüm varlığının adı, önbellekteki dosya adı)."""
    system = platform.system()
    arch = "arm64" if "arm" in platform.machine().lower() else "amd64"
    if system == "Windows":
        return "cloudflared-windows-amd64.exe", "cloudflared.exe"
    if system == "Darwin":
        return f"cloudflared-darwin-{arch}.tgz", "cloudflared-darwin"
    return f"cloudflared-linux-{arch}", "cloudflared-linux"


def _sha256(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for parca in iter(lambda: f.read(_PARCA), b""):
            h.update(parca)
    return h.hexdigest()


def _ozet_eki(bin_path: Path) -> Path:
    """Arşivden (macOS .tgz) çıkan ikilinin özeti: pinli özet ARŞİVİNdir, ikilinin değil — doğrulanmış kurulum bu dosyayı yazar."""
    return bin_path.with_name(bin_path.name + ".sha256")


def _onbellek_dogrulandi(bin_path: Path, varlik: str) -> bool:
    """D3.35: önbellek yalnız BOYUTU ve SHA-256'sı tutuyorsa kullanılır (eskiden ≥ 5 MB her dosya — eski sürümlerin pinsiz,
    özetsiz indirdiği ikili dahil — doğrudan çalıştırılıyordu). Ham ikili varlıkta beklenen özet pinli özettir; arşivde ek dosya."""
    try:
        if not bin_path.is_file() or bin_path.stat().st_size < _ASGARI_BOYUT:
            return False
        if varlik.endswith(".tgz"):
            beklenen = _ozet_eki(bin_path).read_text(encoding="ascii").strip().lower()
        else:
            beklenen = _CLOUDFLARED_OZET.get(varlik, "")
        return bool(beklenen) and _sha256(bin_path) == beklenen
    except Exception:
        return False


def _download_cloudflared() -> Path | None:
    """cloudflared ikilisi — sıra: (1) PAKET → (2) boyutu ve SHA-256'sı doğrulanmış önbellek → (3) sürüm-pinli, boyut tavanlı,
    özetli indirme. Doğrulanamayan gövde önbelleğe YERLEŞMEZ ve çalıştırılmaz."""
    bundled = _bundled_cloudflared()
    if bundled is not None:
        logger.info("cloudflared paketlenmiş binary kullanılıyor (offline): %s", bundled)
        return bundled

    varlik, filename = _varlik_adi()
    bin_path = _BIN_DIR / filename
    if _onbellek_dogrulandi(bin_path, varlik):
        logger.info("cloudflared önbellekte (özet doğrulandı): %s", bin_path)
        return bin_path

    beklenen = _CLOUDFLARED_OZET.get(varlik)
    if not beklenen:
        logger.error(
            "cloudflared %s için pinli özet yok — doğrulanamayan ikili İNDİRİLMEZ (paketli ikili gerekir).", varlik
        )
        return None
    url = f"https://github.com/cloudflare/cloudflared/releases/download/{_CLOUDFLARED_SURUM}/{varlik}"
    try:
        _BIN_DIR.mkdir(parents=True, exist_ok=True)
        # Audit P3: ATOMİK — geçici dosyaya yaz, doğrula, os.replace (kesik indirme önbellekte kalmaz).
        fd, tmp = tempfile.mkstemp(dir=str(_BIN_DIR), suffix=".part")
    except Exception as e:
        logger.error("cloudflared indirilemedi: %s", e)
        return None
    gecici = [tmp, tmp + ".bin"]
    logger.info("cloudflared indiriliyor: %s", url)
    try:
        h = hashlib.sha256()
        toplam = 0
        with os.fdopen(fd, "wb") as f, urllib.request.urlopen(url, timeout=60) as response:
            while True:
                parca = response.read(_PARCA)
                if not parca:
                    break
                toplam += len(parca)
                if toplam > _AZAMI_INDIRME:
                    raise ValueError(f"cloudflared indirmesi boyut tavanını aştı (> {_AZAMI_INDIRME} bayt).")
                h.update(parca)
                f.write(parca)
        if toplam < _ASGARI_BOYUT:
            raise ValueError(f"cloudflared indirmesi çok küçük ({toplam} bytes) — bozuk/kesik.")
        if h.hexdigest() != beklenen:
            raise ValueError(
                f"cloudflared {_CLOUDFLARED_SURUM} indirmesinin SHA-256 özeti pinli özetle UYUŞMUYOR — kullanılmaz."
            )
        if varlik.endswith(".tgz"):
            # B-4.14: macOS varlığı .tgz ARŞİVİDİR — BİR KEZ açılır, içindeki ikili yerleşir. Eskiden çıkarılmış ikili ikinci kez
            # `tarfile.open` ile açılmaya çalışılıyor, hata → None dönüyordu (geçerli arşivle bile tünel yok).
            with tarfile.open(tmp, "r:gz") as arsiv:
                uye = next(
                    (m for m in arsiv.getmembers() if m.isfile() and os.path.basename(m.name) == "cloudflared"), None
                )
                if uye is None:
                    raise ValueError("cloudflared .tgz icinde 'cloudflared' ikilisi bulunamadi.")
                if uye.size > _AZAMI_INDIRME:
                    raise ValueError("cloudflared .tgz içindeki ikili boyut tavanını aştı.")
                kaynak = arsiv.extractfile(uye)
                with os.fdopen(os.open(tmp + ".bin", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o755), "wb") as bf:
                    shutil.copyfileobj(kaynak, bf, _PARCA)
            os.replace(tmp + ".bin", bin_path)
            _ozet_eki(bin_path).write_text(_sha256(bin_path), encoding="ascii")
        else:
            os.replace(tmp, bin_path)
        if platform.system() != "Windows":
            bin_path.chmod(0o755)
        logger.info("cloudflared %s indirildi ve özeti doğrulandı: %s", _CLOUDFLARED_SURUM, bin_path)
        return bin_path
    except Exception as e:
        logger.error("cloudflared indirilemedi: %s", e)
        return None
    finally:
        for g in gecici:
            try:
                os.unlink(g)  # yerleştiyse zaten yok
            except OSError:
                pass


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
                changed = new_url != _tunnel_url
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

    # 18K K6 · D3.35 (B-4.12): PAKETTEKİ ikili ÖNCE — `_download_cloudflared` sırası: paket → boyutu doğrulanmış önbellek →
    # indirme. Eskiden önbellek dosyası (%APPDATA%\PEMF_GUI\cloudflared) VARSA — 0 bayt / bozuk / eski sürümlerin sürüm-pinsiz,
    # özetsiz indirdiği ikili dahil — doğrulanmadan çalıştırılıyor, paketli ikili hiç denenmiyordu (uzaktan erişim kalıcı ölü).
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
        logger.warning(
            "cloudflare_tunnel_token geçersiz/placeholder (uzunluk %d) → YOK SAYILDI, QUICK tünele düşülüyor.",
            len(token),
        )
        token = ""
    if token:
        cmd = [str(bin_path), "tunnel", "run", "--token", token]
        logger.info("Cloudflare NAMED tunnel başlatılıyor (kalıcı hostname, üretim-grade).")
    else:
        cmd = [str(bin_path), "tunnel", "--url", f"http://localhost:{port}"]
        logger.info(
            "Cloudflare QUICK tunnel başlatılıyor → port %d (URL her restart DEĞİŞİR; üretimde NAMED önerilir).", port
        )

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
    except urllib.error.HTTPError as e:
        # Y241 (KP1 T-1): urlopen 4xx'te HTTPError fırlatır; edge 4xx (Access 403 / 404 / 429) forward ediyor = CANLI, 5xx ölü.
        return 200 <= int(e.code) < 500
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
                    _watchdog_stop.wait(check_interval)  # çevrimdışı → sadece bekle (yerel etkilenmez)
                    continue
                if _tunnel_alive():
                    # Süreç canlı; ama quick tünel edge'i ölmüş olabilir (forward yok). DIŞ URL'yi probe et;
                    # 2 ardışık ölüde yeniden başlat (audit P0: ölü-URL Supabase'e yayınlanmaya devam ediyordu).
                    if _tunnel_url_alive():
                        dead_url_strikes = 0
                        backoff = check_interval  # sağlıklı → normal aralıkta tekrar bak
                        _watchdog_stop.wait(check_interval)
                        continue
                    dead_url_strikes += 1
                    if dead_url_strikes < 2:
                        logger.info(
                            "Tünel watchdog: dış URL probe başarısız (%d/2) → bir tur daha bekleniyor.",
                            dead_url_strikes,
                        )
                        _watchdog_stop.wait(check_interval)
                        continue
                    logger.warning("Tünel watchdog: süreç canlı ama DIŞ URL ölü → tünel yeniden başlatılıyor.")
                    dead_url_strikes = 0
                    # düş → aşağıda stop_tunnel + start_tunnel (yeni URL alınır + yayınlanır)
                stop_tunnel()  # yarı-ölü süreç varsa temizle (None ise zararsız)
                logger.info("Tünel watchdog: internet VAR, tünel yok/ölü → (yeniden) başlatılıyor.")
                if start_tunnel(port=port):
                    backoff = check_interval
                    _watchdog_stop.wait(check_interval)  # QUICK tünel URL'yi yakalasın diye bekle
                else:
                    logger.warning("Tünel watchdog: başlatma başarısız, %ds sonra tekrar.", backoff)
                    _watchdog_stop.wait(backoff)
                    backoff = min(backoff * 2, max_backoff)
            except Exception:
                # D1.18 (B-4.17): bildirim fırlatırsa uzaktan erişim tüneli süreç ömrü boyunca ölürdü.
                dongu_hatasini_bildir("Tünel watchdog döngü hatası (devam ediliyor).", logger=logger)
                _watchdog_stop.wait(check_interval)

    _watchdog_thread = threading.Thread(target=_loop, daemon=True, name="CloudflareTunnelWatchdog")
    _watchdog_thread.start()
    logger.info("Cloudflare tünel watchdog başlatıldı (internet geldikçe/gittikçe uzaktan erişim otomatik).")
