"""Shared STM32 serial transport helpers.

Port seçimi:
  1) env PEMF_STM_PORT='COM7' → o portu kullanır (saha override'ı),
  2) PEMF_STM_PORT verilmezse → VARSAYILAN sabit COM10 (LattePanda gibi kartlarda onboard
     STM/co-processor de USB-seri (örn COM3) göründüğü için oto-algılama VARSAYILAN DEĞİL),
  3) PEMF_STM_PORT='auto' → ST-Link VCP'yi ST-Link'e ÖZGÜ USB PID/açıklama ile bulur
     (onboard STM'i eler); bulamazsa COM10'a düşer.
115200 baud. Nucleo-F429ZI ST-Link VCP → USART3 (PD8/PD9). Firmware doğrudan
ST-Link USB için USART3 kullanmalı.
"""

from __future__ import annotations

import os
import struct
import time
import zlib
from dataclasses import dataclass
from typing import Any, Callable, Optional

# VARSAYILAN port (PEMF_STM_PORT verilmediğinde). Sahada sabit COM10; gerekirse env ile
# değiştirin (PEMF_STM_PORT=COMx) veya oto-algılama açın (PEMF_STM_PORT=auto).
FIXED_STM32_PORT = "COM10"       # default/legacy (ST-Link VCP, Nucleo-F429ZI USART3 @ PD8/PD9)
ST_LINK_USB_VID = 0x0483         # STMicroelectronics
# ST-Link VCP USB PID'leri (V1/V2/V2-1/V3). Onboard STM CDC (örn LattePanda, PID 0x5740)
# BU SETTE YOK → oto-algılamada onboard STM'i ELER, yanlış porta (COM3) gitmez.
ST_LINK_USB_PIDS = frozenset({0x3744, 0x3748, 0x374B, 0x374D, 0x374E, 0x374F, 0x3752, 0x3753})
DEFAULT_BAUDRATE = 115200
DEFAULT_HANDSHAKE_TIMEOUT_SEC = 12.0
DEFAULT_NO_PORT_LOG_INTERVAL_SEC = 15.0
DEFAULT_BAD_PORT_COOLDOWN_SEC = 3.0
# Port açıldıktan sonra USB VCP/CDC’nin hazır hale gelmesini bekle (saniye)
VCP_SETTLE_TIME_SEC = 2.0
# Re-opened GUI may attach to an already-running STM that will not emit another
# STM_READY. Listen briefly, then actively probe with a safe zero-duty packet.
HANDSHAKE_PASSIVE_LISTEN_SEC = 1.0
HANDSHAKE_PROBE_INTERVAL_SEC = 1.0

@dataclass(frozen=True)
class Stm32PortCandidate:
    device: str
    description: str = ""

    def label(self) -> str:
        return f"{self.device} | {self.description}" if self.description else self.device


@dataclass
class Stm32OpenResult:
    serial: Any
    candidate: Stm32PortCandidate
    ready_line: str


def build_stm32_zero_duty_packet(freq_hz: float = 100.0) -> bytes:
    """Build the main.c compatible 5-coil zero-duty packet used as ping/stop."""
    fmt = "<BB 5f 5f 5f 5I H"
    ref_ms = int(time.monotonic() * 1000) % 1000
    data = struct.pack(
        fmt,
        0xAA,
        0x55,
        *([0.0] * 5),
        *([0.0] * 5),
        *([float(freq_hz)] * 5),
        *([0] * 5),
        ref_ms,
    )
    return data + struct.pack("<I", zlib.crc32(data) & 0xFFFFFFFF)


class Stm32SerialTransport:
    """Serial opener pinned to COM10 (ST-Link VCP, USART3/PD8/PD9) with STM handshake timeout."""

    def __init__(
        self,
        logger: Any,
        settings: Any = None,
        baudrate: int = DEFAULT_BAUDRATE,
        handshake_timeout_sec: float = DEFAULT_HANDSHAKE_TIMEOUT_SEC,
        no_port_log_interval_sec: float = DEFAULT_NO_PORT_LOG_INTERVAL_SEC,
        bad_port_cooldown_sec: float = DEFAULT_BAD_PORT_COOLDOWN_SEC,
    ) -> None:
        self.logger = logger
        self.baudrate = int(baudrate)
        self.handshake_timeout_sec = float(handshake_timeout_sec)
        self.no_port_log_interval_sec = float(no_port_log_interval_sec)
        self.bad_port_cooldown_sec = float(bad_port_cooldown_sec)
        self.settings = settings
        self._last_no_port_log = 0.0
        self._bad_ports_until: dict[str, float] = {}

    def open_and_handshake(
        self,
        stop_event: Any,
        ping_packet: Optional[bytes] = None,
        on_line: Optional[Callable[[str], None]] = None,
    ) -> Optional[Stm32OpenResult]:
        """Open COM10 (ST-Link VCP) and require STM_READY/STM_OK within timeout."""
        candidate = self._select_candidate()
        if candidate is None:
            return None

        serial_obj = None
        try:
            serial_obj = self._open_serial(candidate)
            self._log_info("[STM32] Port açıldı: %s", candidate.label())
            # USB VCP/CDC bağlantısının hazır hale gelmesi için kısa bekleme.
            # ST-Link VCP ilk açılışta DTR/RTS sinyal değişikliği nedeniyle
            # MCU’yu reset'leyebilir; bu süre MCU’nun başlayası ve STM_READY
            # göndermesi için gereklidir.
            self._log_info("[STM32] VCP hazırlanıyor, %.1f sn bekleniyor...", VCP_SETTLE_TIME_SEC)
            time.sleep(VCP_SETTLE_TIME_SEC)
            ready_line = self._wait_for_handshake(
                serial_obj,
                candidate,
                stop_event,
                on_line,
                ping_packet=ping_packet,
            )
            if not ready_line:
                self.close_serial(serial_obj)
                self._mark_bad(candidate.device)
                self._log_warning(
                    "[STM32] Handshake zaman aşımı (%.1f s) → %s; ’STM_READY’ veya ’STM_OK’ "
                    "alınamadı. Port kapatıldı. Firmware USART3 (PD8/PD9) kullanıyor mu? "
                    "COM10 = ST-Link VCP olmalı.",
                    self.handshake_timeout_sec,
                    candidate.label(),
                )
                return None

            self._bad_ports_until.pop(candidate.device.upper(), None)
            self._log_info("[STM32] Handshake OK: %s", candidate.label())
            return Stm32OpenResult(serial=serial_obj, candidate=candidate, ready_line=ready_line)
        except Exception as exc:
            if serial_obj is not None:
                self.close_serial(serial_obj)
            self._mark_bad(candidate.device)
            self._log_warning("[STM32] Bağlantı başarısız → %s: %s", candidate.label(), exc)
            return None

    def close_serial(self, serial_obj: Any) -> None:
        try:
            if serial_obj and getattr(serial_obj, "is_open", False):
                serial_obj.close()
        except Exception:
            pass

    # ── Candidate Seçimi ──────────────────────────────────────────────────────

    def _select_candidate(self) -> Optional[Stm32PortCandidate]:
        configured = (os.environ.get("PEMF_STM_PORT", "") or "").strip()

        # VARSAYILAN = COM10 (sabit). LattePanda gibi platformlarda onboard STM/co-processor
        # de USB-seri (örn COM3) göründüğünden oto-algılama yanlış porta gidebilir → varsayılan
        # sabit COM10. Oto-algılama yalnız PEMF_STM_PORT=auto ile (opt-in) açılır.
        if not configured:
            configured = FIXED_STM32_PORT

        # Oto-algılama (opt-in): ST-Link'e ÖZGÜ eşleştirme (onboard STM'i eler).
        if configured.lower() in ("auto", "otomatik"):
            detected = self._autodetect_stlink()
            if detected is not None:
                return self._candidate_if_ready(detected)
            self._throttled_no_port_log(
                f"[STM32] Oto-algılama: ST-Link VCP bulunamadı → {FIXED_STM32_PORT} denenecek "
                f"(gerekirse PEMF_STM_PORT=COMx ile sabitleyin)."
            )
            return self._candidate_if_ready(
                Stm32PortCandidate(device=FIXED_STM32_PORT, description="auto->COM10 fallback")
            )

        # Açık/varsayılan sabit port (COM10 veya PEMF_STM_PORT=COMx).
        return self._candidate_if_ready(
            Stm32PortCandidate(device=configured, description="sabit (PEMF_STM_PORT/COM10)")
        )

    def _candidate_if_ready(self, candidate: Stm32PortCandidate) -> Optional[Stm32PortCandidate]:
        """Seçilen port cooldown'da değilse aday olarak döndür."""
        bad_until = self._bad_ports_until.get(candidate.device.upper(), 0.0)
        if bad_until > time.monotonic():
            self._throttled_no_port_log(
                f"[STM32] {candidate.device} cooldown dolana kadar bekleniyor."
            )
            return None
        self._log_info("[STM32] Port seçimi: %s @ %d baud", candidate.label(), self.baudrate)
        return candidate

    def _autodetect_stlink(self) -> Optional[Stm32PortCandidate]:
        """Bağlı COM portları arasında ST-Link VCP'yi bul (ST-Link'e ÖZGÜ eşleştirme).

        Yalnız VID 0x0483 YETMEZ: LattePanda gibi kartların onboard STM co-processor'ü de
        VID 0x0483 olabilir (örn COM3) ama ST-Link DEĞİLDİR. Bu yüzden ST-Link'e özgü USB
        PID seti (V1/V2/V2-1/V3) veya açıklamada 'ST-Link' ile eşleştirir; onboard STM CDC'yi
        (farklı PID + açıklamada 'ST-Link' yok) ELER. Birden çok eşleşmede ilkini alır.
        """
        try:
            from serial.tools import list_ports
        except Exception:
            return None
        try:
            ports = list(list_ports.comports())
        except Exception:
            return None
        for p in ports:
            vid = getattr(p, "vid", None)
            pid = getattr(p, "pid", None)
            desc = (getattr(p, "description", "") or "")
            descu = desc.upper().replace("-", "")
            is_stlink = (
                (vid == ST_LINK_USB_VID and pid in ST_LINK_USB_PIDS)
                or "STLINKVIRTUALCOM" in descu
                or "STLINK" in descu
            )
            if is_stlink:
                return Stm32PortCandidate(
                    device=p.device, description=f"oto ST-Link: {desc}".strip()
                )
        return None

    # ── Port Açma ─────────────────────────────────────────────────────────────

    def _open_serial(self, candidate: Stm32PortCandidate) -> Any:
        import serial as serial_lib

        dev = candidate.device
        # socket:// (STM simülatörü / uzak-seri köprü) + rfc2217:// + loop:// → serial_for_url.
        # Gerçek COM (ST-Link VCP) → klasik Serial. Böylece SANAL-STM ile test edilebilir + sahada
        # uzak-seri desteklenir; gerçek-COM yolu ve DTR/RTS davranışı DEĞİŞMEZ (geriye uyumlu).
        if "://" in dev:
            serial_obj = serial_lib.serial_for_url(
                dev, baudrate=self.baudrate, timeout=0.3, write_timeout=1.0
            )
        else:
            serial_obj = serial_lib.Serial(
                candidate.device,
                self.baudrate,
                timeout=0.3,
                write_timeout=1.0,
                dsrdtr=False,   # DTR kapalı: ST-Link VCP’de aynı anda MCU reset'ini önler
                rtscts=False,
            )
        try:
            serial_obj.dtr = False
            serial_obj.rts = False
            serial_obj.reset_input_buffer()
            serial_obj.reset_output_buffer()
        except Exception:
            pass
        return serial_obj

    # ── Handshake ─────────────────────────────────────────────────────────────

    def _wait_for_handshake(
        self,
        serial_obj: Any,
        candidate: Stm32PortCandidate,
        stop_event: Any,
        on_line: Optional[Callable[[str], None]],
        ping_packet: Optional[bytes] = None,
    ) -> str:
        """Wait for STM_READY/STM_OK; probe silent firmware with zero-duty ping.

        Firmware emits STM_READY at boot, but after the first valid packet it may
        keep running silently. A reopened GUI therefore cannot rely on passive
        READY lines only. The active probe is a valid 88-byte zero-duty packet:
        it is safe for outputs and returns STM_OK when the protocol path works.
        """
        start = time.monotonic()
        deadline = start + self.handshake_timeout_sec
        next_probe_at = start + HANDSHAKE_PASSIVE_LISTEN_SEC

        while time.monotonic() < deadline:
            if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
                return ""

            try:
                line = serial_obj.readline()
            except Exception as exc:
                self._log_warning("[STM32] Handshake okuma hatası %s: %s", candidate.device, exc)
                return ""

            if line:
                decoded = line.decode("utf-8", errors="ignore").strip()
                if decoded:
                    if on_line is not None:
                        try:
                            on_line(decoded)
                        except Exception as exc:
                            self._log_warning("[STM32] Handshake callback hatası: %s", exc)

                    if "STM_READY" in decoded or "STM_OK:" in decoded:
                        return decoded

            now = time.monotonic()
            if now < next_probe_at:
                continue

            try:
                packet = ping_packet if ping_packet is not None else build_stm32_zero_duty_packet()
                serial_obj.write(packet)
                self._log_info("[STM32] Handshake probe gönderildi: zero-duty ping → %s", candidate.device)
            except Exception as exc:
                self._log_warning("[STM32] Handshake probe yazma hatası %s: %s", candidate.device, exc)
                return ""
            next_probe_at = now + HANDSHAKE_PROBE_INTERVAL_SEC

        return ""

    # ── Yardımcı Metodlar ─────────────────────────────────────────────────────

    def _mark_bad(self, device: str) -> None:
        if device:
            self._bad_ports_until[device.upper()] = time.monotonic() + self.bad_port_cooldown_sec

    def _throttled_no_port_log(self, message: str) -> None:
        now = time.monotonic()
        if now - self._last_no_port_log >= self.no_port_log_interval_sec:
            self._last_no_port_log = now
            self._log_info(message)

    def _log_info(self, message: str, *args: Any) -> None:
        if self.logger:
            self.logger.info(message, *args)

    def _log_warning(self, message: str, *args: Any) -> None:
        if self.logger:
            self.logger.warning(message, *args)
