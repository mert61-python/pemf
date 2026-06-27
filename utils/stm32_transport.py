"""Shared STM32 serial transport helpers.

STM32 connection is pinned to COM10 (ST-Link Virtual COM Port) at 115200 baud.
Nucleo-F429ZI board uses ST-Link VCP which maps to USART3 (PD8/PD9) on the MCU.
Firmware must use USART3 for direct ST-Link USB cable communication.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
import time
from typing import Any, Callable, Optional
import zlib


FIXED_STM32_PORT = "COM10"       # ST-Link VCP (Nucleo-F429ZI, USART3 @ PD8/PD9)
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
        bad_until = self._bad_ports_until.get(FIXED_STM32_PORT.upper(), 0.0)
        if bad_until > time.monotonic():
            self._throttled_no_port_log(
                f"[STM32] {FIXED_STM32_PORT} cooldown dolana kadar bekleniyor."
            )
            return None

        self._log_info(
            "[STM32] Sabit port seçimi: %s @ %d baud",
            FIXED_STM32_PORT,
            self.baudrate,
        )
        return Stm32PortCandidate(device=FIXED_STM32_PORT, description="fixed STM32 port")

    # ── Port Açma ─────────────────────────────────────────────────────────────

    def _open_serial(self, candidate: Stm32PortCandidate) -> Any:
        import serial as serial_lib

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
