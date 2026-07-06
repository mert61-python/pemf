#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STM32 Binary Protocol Simulator
================================

Bu script, GUI'nin binary paket protokolünü (main.c ile identik 88-byte format)
anlayan ve yanıt veren bir Python STM32 emülatörüdür.

KULLANıM:
  1. Bu scripti çalıştırın:
       python utils/stm32_simulator.py

  2. Not: GUI STM32 bağlantısı şimdilik COM10 @ 115200 baud'a kilitli.
     socket:// simülatör bağlantısı, bu sabit port modu aktifken kullanılmaz.

  Örnek:
       python utils/stm32_simulator.py

PAKET FORMATI (88 byte, main.c ile identik):
  0xAA 0x55
  float[5]   duty      (20 byte)
  float[5]   phase     (20 byte)
  float[5]   freq      (20 byte)
  uint32[5]  duration  (20 byte)
  uint16     ref_ms    ( 2 byte)
  uint32     crc32     ( 4 byte)
  ─────────────────────────────
  Toplam: 88 byte

YANIT FORMATI (ASCII, \r\n ile biten):
  -> STM_READY: DDS v2.2 (5-ch SIM) Waiting for commands...\r\n
  -> STM_OK: D=%d,%d,%d,%d,%d P=%d,%d,%d,%d,%d F=%d,%d,%d,%d,%d T=%lu,...\r\n
  -> STM_NACK: <sebep>\r\n
  -> STM_ERR: Watchdog Timeout! Baglanti koptu, bobinler 0'landi.\r\n
  -> STM_STOPPED: Sure(ler) doldu, bobinler kapatildi.\r\n
"""

import argparse
import logging
import socket
import struct
import threading
import time
import zlib

# ─── Logging ─────────────────────────────────────────────────────────────────
# NOT (audit B-5.3): basicConfig MODÜL-DÜZEYİNDE değil — import edildiğinde merkezî
# logging yapılandırmasını (backend_service._configure_logging) ezmesin. Yalnız standalone
# çalıştırıldığında (__main__) yapılandırılır. Modül kendi logger'ını kullanır (aşağıda).
log = logging.getLogger("STM32Sim")

# ─── Sabitler ─────────────────────────────────────────────────────────────────
SIM_HOST      = "127.0.0.1"
SIM_PORT      = 5100
READY_DELAY_S = 2.0   # USB CDC enumerate simülasyonu (2 s)

# Binary paket yapısı: <BB 5f 5f 5f 5I H I
#   B  B         → header[2]         = 0xAA, 0x55
#   5f 5f 5f     → duty[5], phase[5], freq[5]
#   5I           → duration[5]
#   H            → ref_ms
#   I            → crc32
PKT_FMT  = "<BB 5f 5f 5f 5I H I"
PKT_SIZE = struct.calcsize(PKT_FMT)   # 88 byte
assert PKT_SIZE == 88, f"Paket boyutu {PKT_SIZE} != 88!"

NUM_COILS         = 5
DUTY_MIN          = 0.0
PHASE_MIN         = 0.0
PHASE_MAX         = 360.0
FREQ_MIN          = 1.0
FREQ_MAX          = 10000.0
DUR_MAX           = 9999
REF_MS_MAX        = 999
WATCHDOG_MS       = 1500   # ms — main.c ile aynı


def crc32_of(data: bytes) -> int:
    """IEEE 802.3 / zlib CRC32 — main.c calculate_crc32 ile identik."""
    return zlib.crc32(data) & 0xFFFFFFFF


def decode_packet(raw: bytes):
    """
    88-byte binary paketi çözer.
    Başarıda (duty, phase, freq, duration, ref_ms) tuple döner.
    Hata durumunda (None, sebep_str) döner.
    """
    if len(raw) != PKT_SIZE:
        return None, f"boyut={len(raw)} != {PKT_SIZE}"

    # CRC doğrulama (son 4 byte hariç)
    calc_crc = crc32_of(raw[:-4])
    pkt_crc  = struct.unpack_from("<I", raw, PKT_SIZE - 4)[0]
    if calc_crc != pkt_crc:
        return None, f"CRC calc={calc_crc:08X} pkt={pkt_crc:08X}"

    fields = struct.unpack(PKT_FMT, raw)
    hdr0, hdr1 = fields[0], fields[1]
    if hdr0 != 0xAA or hdr1 != 0x55:
        return None, f"header={hdr0:02X}{hdr1:02X}"

    duty     = list(fields[2 :7 ])   # float[5]
    phase    = list(fields[7 :12])   # float[5]
    freq     = list(fields[12:17])   # float[5]
    duration = list(fields[17:22])   # uint32[5]
    ref_ms   = fields[22]            # uint16
    # fields[23] = crc32 (zaten doğrulandı)

    # Değer kontrolleri
    if ref_ms > REF_MS_MAX:
        return None, f"ref_ms={ref_ms} > {REF_MS_MAX}"

    for i in range(NUM_COILS):
        if duty[i] < DUTY_MIN:
            return None, f"coil={i+1} duty={duty[i]:.3f} < {DUTY_MIN}"
        if not (PHASE_MIN <= phase[i] <= PHASE_MAX):
            return None, f"coil={i+1} phase={phase[i]:.1f} out of [0,360]"
        if not (FREQ_MIN <= freq[i] <= FREQ_MAX):
            return None, f"coil={i+1} freq={freq[i]:.1f} out of [{FREQ_MIN},{FREQ_MAX}]"
        if duration[i] > DUR_MAX:
            return None, f"coil={i+1} duration={duration[i]} > {DUR_MAX}"

    return (duty, phase, freq, duration, ref_ms), None


class Stm32SimClient:
    """Tek bir GUI bağlantısını yöneten sınıf."""

    def __init__(self, conn: socket.socket, addr):
        self.conn = conn
        self.addr = addr
        self._lock = threading.Lock()
        self._coil_duty     = [0.0] * NUM_COILS
        self._coil_start_ms = [None] * NUM_COILS   # datetime.now() veya None
        self._last_pkt_time = time.monotonic()
        self._any_active    = False

    def _send(self, msg: str):
        try:
            with self._lock:
                self.conn.sendall(msg.encode("utf-8"))
        except Exception as e:
            log.warning("Gönderim hatası: %s", e)

    def _send_ready(self):
        time.sleep(READY_DELAY_S)   # USB enumerate simülasyonu
        msg = "-> STM_READY: DDS v2.2 (5-ch SIM) Waiting for commands...\r\n"
        self._send(msg)
        log.info("✅ STM_READY gönderildi → %s", self.addr)

    def _send_ack(self, duty, phase, freq, duration):
        msg = (
            "-> STM_OK: "
            f"D={int(duty[0]*100)},{int(duty[1]*100)},{int(duty[2]*100)},{int(duty[3]*100)},{int(duty[4]*100)} "
            f"P={int(phase[0])},{int(phase[1])},{int(phase[2])},{int(phase[3])},{int(phase[4])} "
            f"F={int(freq[0])},{int(freq[1])},{int(freq[2])},{int(freq[3])},{int(freq[4])} "
            f"T={duration[0]},{duration[1]},{duration[2]},{duration[3]},{duration[4]}"
            "\r\n"
        )
        self._send(msg)
        active = [i+1 for i in range(NUM_COILS) if duty[i] > 0]
        log.info("📨 STM_OK | Aktif bobinler: %s | Duty: %s | Freq: %s Hz",
                 active or "yok",
                 [f"{d:.2f}" for d in duty],
                 [f"{f:.0f}" for f in freq])

    def _watchdog_worker(self):
        """1.5 s iletişim yoksa bobinleri sıfırla — main.c ile aynı davranış."""
        while True:
            time.sleep(0.2)
            if self._any_active:
                elapsed_ms = (time.monotonic() - self._last_pkt_time) * 1000
                if elapsed_ms > WATCHDOG_MS:
                    self._any_active = False
                    self._coil_duty  = [0.0] * NUM_COILS
                    msg = "-> STM_ERR: Watchdog Timeout! Baglanti koptu, bobinler 0'landi.\r\n"
                    self._send(msg)
                    log.warning("⏱️  Watchdog tetiklendi (%d ms iletişim yok)", int(elapsed_ms))

    def _duration_worker(self):
        """Süre dolduğunda bobinleri kapat — main.c ile aynı davranış."""
        while True:
            time.sleep(0.5)
            stopped_any = False
            for i in range(NUM_COILS):
                if self._coil_start_ms[i] is not None and self._coil_duty[i] > 0:
                    # dur_min bilgisi burada yok; duration tracking için
                    # dışarıdan set edilen _coil_dur_min listesi kullanılıyor
                    dur_min = getattr(self, "_coil_dur_min", [0]*NUM_COILS)[i]
                    if dur_min > 0:
                        elapsed_s  = time.monotonic() - self._coil_start_ms[i]
                        target_s   = dur_min * 60.0
                        if elapsed_s >= target_s:
                            self._coil_duty[i]     = 0.0
                            self._coil_start_ms[i] = None
                            stopped_any = True
                            log.info("⏹️  Bobin %d süresi doldu (%d dk)", i+1, dur_min)
            if stopped_any:
                msg = "-> STM_STOPPED: Sure(ler) doldu, bobinler kapatildi.\r\n"
                self._send(msg)

    def run(self):
        log.info("🔌 Bağlantı: %s", self.addr)
        threading.Thread(target=self._send_ready, daemon=True).start()
        threading.Thread(target=self._watchdog_worker, daemon=True).start()
        threading.Thread(target=self._duration_worker, daemon=True).start()

        self._coil_dur_min = [0] * NUM_COILS

        buf = b""
        try:
            while True:
                chunk = self.conn.recv(256)
                if not chunk:
                    log.info("🔌 Bağlantı kapatıldı: %s", self.addr)
                    break
                buf += chunk

                # 88-byte paket ara (header 0xAA 0x55)
                while True:
                    aa_idx = buf.find(b"\xaa\x55")
                    if aa_idx < 0:
                        buf = b""
                        break
                    if aa_idx > 0:
                        log.debug("  %d byte atlandı (header bekleniyordu)", aa_idx)
                        buf = buf[aa_idx:]
                    if len(buf) < PKT_SIZE:
                        break   # daha fazla veri bekle
                    raw = buf[:PKT_SIZE]
                    buf = buf[PKT_SIZE:]

                    result, err = decode_packet(raw)
                    if err:
                        nack = f"-> STM_NACK: {err}\r\n"
                        self._send(nack)
                        log.warning("❌ NACK: %s", err)
                        continue

                    duty, phase, freq, duration, ref_ms = result
                    self._last_pkt_time = time.monotonic()
                    self._any_active    = any(d > 0 for d in duty)
                    self._coil_duty     = list(duty)
                    self._coil_dur_min  = list(duration)

                    # Süre başlangıcı güncelle
                    for i in range(NUM_COILS):
                        if duty[i] > 0 and self._coil_start_ms[i] is None:
                            self._coil_start_ms[i] = time.monotonic()
                        elif duty[i] == 0:
                            self._coil_start_ms[i] = None

                    self._send_ack(duty, phase, freq, duration)

        except ConnectionResetError:
            log.info("🔌 Bağlantı sıfırlandı: %s", self.addr)
        except Exception as e:
            log.error("Hata: %s", e)
        finally:
            try:
                self.conn.close()
            except Exception:
                pass


def run_server(host: str = SIM_HOST, port: int = SIM_PORT):
    """TCP sunucusu — sabit COM10 modu kapatılırsa test için kullanılabilir."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((host, port))
    except OSError as e:
        log.error("Sunucu başlatılamadı %s:%d — %s", host, port, e)
        return
    srv.listen(1)
    log.info("=" * 60)
    log.info("  STM32 Binary Simulator — TCP %s:%d", host, port)
    log.info("  Not: GUI sabit COM10 modundayken socket simulator kullanılmaz")
    log.info("  Paket boyutu: %d byte (88-byte binary + CRC32)", PKT_SIZE)
    log.info("=" * 60)
    log.info("  Bağlantı bekleniyor...")

    while True:
        try:
            conn, addr = srv.accept()
            client = Stm32SimClient(conn, addr)
            t = threading.Thread(target=client.run, daemon=True,
                                 name=f"SimClient-{addr[1]}")
            t.start()
        except KeyboardInterrupt:
            log.info("Simulator kapatıldı.")
            break
        except Exception as e:
            log.error("Sunucu hatası: %s", e)


def set_gui_port(host: str = SIM_HOST, port: int = SIM_PORT):
    """
    Sabit COM10 modu aktifken GUI socket simulator portuna yönlendirilmez.
    """
    print("GUI STM32 bağlantısı şimdilik COM10 @ 115200 baud'a kilitli.")
    print(f"socket://{host}:{port} ayarı uygulanmadı.")


def main():
    parser = argparse.ArgumentParser(
        description="STM32 Binary Protocol Simulator (GUI test aracı)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--host", default=SIM_HOST,
                        help=f"Sunucu adresi (varsayılan: {SIM_HOST})")
    parser.add_argument("--port", type=int, default=SIM_PORT,
                        help=f"TCP port (varsayılan: {SIM_PORT})")
    parser.add_argument("--set-port", action="store_true",
                        help="Sabit COM10 modunda devre dışı; bilgi mesajı yazdırır")
    args = parser.parse_args()

    if args.set_port:
        set_gui_port(args.host, args.port)
        return

    run_server(args.host, args.port)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    main()
