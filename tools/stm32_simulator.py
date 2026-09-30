#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""
STM32 Binary Protocol Simulator
================================

Bu script, GUI'nin binary paket protokolünü (main.c ile identik 88-byte format)
anlayan ve yanıt veren bir Python STM32 emülatörüdür.

KULLANıM:
  1. Bu scripti çalıştırın:
       python apps/backend/utils/stm32_simulator.py

  2. Not: GUI STM32 bağlantısı şimdilik COM10 @ 115200 baud'a kilitli.
     socket:// simülatör bağlantısı, bu sabit port modu aktifken kullanılmaz.

  Örnek:
       python apps/backend/utils/stm32_simulator.py

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

NOT (2026-08-19): Firmware v2.3'e gecti — dalga sozlesmesi SIMETRIK BIPOLAR
(A=[0,duty), B=[yarim,yarim+duty), arada LOW; net DC=0; duty tavani ~%50) ve
derleme-kapili NTC termal kesme eklendi. BU SIM PROTOKOL-SEVIYESIDIR: paket
cozme/CRC/ACK/watchdog'u taklit eder, DALGA BICIMINI MODELLEMEZ — dalga fizigi
kilitleri tests/test_stm_dalga_sozlesmesi.py'dedir. READY dizesi firmware ile
hizali tutulur (backend 'STM_READY' alt-dizesini esler; surum eki serbesttir).

YANIT FORMATI (ASCII, \r\n ile biten) — firmware ile HİZALI (D0Ö.13):
  -> STM_READY: DDS v2.3 (7-ch KARMA uni=0x60 SIM) Waiting for commands...\r\n   (kip/maske pemf_surus.h'den)
  -> STM_OK: D=<NUM_COILS alan> P=<...> F=<...> T=<...> K=<etkin maske = yetenek | istek>\r\n
  -> STM_NACK: <sebep>\r\n
  -> STM_ERR: Watchdog Timeout! Baglanti koptu, bobinler 0'landi.\r\n
  -> STM_STOPPED: Sure(ler) doldu, bobinler kapatildi.\r\n
"""

import argparse
import logging
import math
import re
import socket
import struct
import threading
import time
import zlib
from pathlib import Path

# ─── Logging ─────────────────────────────────────────────────────────────────
# NOT (audit B-5.3): basicConfig MODÜL-DÜZEYİNDE değil — import edildiğinde merkezî
# logging yapılandırmasını (backend_service._configure_logging) ezmesin. Yalnız standalone
# çalıştırıldığında (__main__) yapılandırılır. Modül kendi logger'ını kullanır (aşağıda).
log = logging.getLogger("STM32Sim")

# ─── Sabitler ─────────────────────────────────────────────────────────────────
SIM_HOST = "127.0.0.1"
SIM_PORT = 5100
READY_DELAY_S = 2.0  # USB CDC enumerate simülasyonu (2 s)

# Binary paket yapısı: <BB 5f 5f 5f 5I H I
#   B  B         → header[2]         = 0xAA, 0x55
#   Nf Nf Nf     → duty[N], phase[N], freq[N]  (N = NUM_COILS)
#   5I           → duration[5]
#   H            → ref_ms
#   I            → crc32
# ⚠️ SAYIYI ELLE YAZMA: bicim NUM_COILS'ten turer. 2026-09-10'da 5 -> 7 (bobin 6-7 ESP'den
# STM'e tasindi) ve paket 88 -> 120 bayt oldu. Simulator, firmware ve backend UCU birden
# ayni genislikte olmak ZORUNDA; kapi: tests/test_stm32_source_parity.py.
NUM_COILS = 7
#: ⚠️ `B` = unipolar_maskesi (2026-09-11, arayuz kip dugmesi). Paket 120 → 121 bayt.
PKT_FMT = "<BB {n}f {n}f {n}f {n}I H B I".format(n=NUM_COILS)
PKT_SIZE = struct.calcsize(PKT_FMT)
assert PKT_SIZE == 121, f"Paket boyutu {PKT_SIZE} != 121!"

DUTY_MIN = 0.0
PHASE_MIN = 0.0
PHASE_MAX = 360.0
FREQ_MIN = 1.0
# ⚠️ DENETİM 2026-08-04: burada 10000.0 yazıyordu. Firmware'in GERÇEK sınırı
# FREQ_MAX = DDS_ISR_HZ / DDS_MIN_TICKS_PER_PERIOD = 50000/2 = 25000 Hz (main.c:158-160) ve
# apps/backend/utils/stm32_protocol_limits.FREQ_MAX_HZ de 25000. Simülatör 10 kHz üstünü NACK'lediği için
# E2E güvenlik testleri SEVKEDİLENDEN FARKLI bir cihazı doğruluyordu (10–25 kHz aralığı hiç
# test edilmiyordu). Değer artık firmware ile AYNI formülden türetiliyor.
DDS_ISR_HZ = 50000.0
DDS_MIN_TICKS_PER_PERIOD = 2.0
FREQ_MAX = DDS_ISR_HZ / DDS_MIN_TICKS_PER_PERIOD  # = 25000.0
DUR_MAX = 9999
REF_MS_MAX = 999
WATCHDOG_MS = 1500  # ms — main.c ile aynı

# ⚠️ D0Ö.13 (B-10.268): SÜRÜŞ KİPİ YETENEK MASKESİ firmware'in DERLENEN değerinden TÜRER — elle yazılan
# "SYM-BIPOLAR" 2026-09-11 karma yapılandırmasında YALAN söylüyordu (firmware "KARMA uni=0x60" basar).
_SURUS_BASLIGI = Path(__file__).resolve().parents[1] / "firmware" / "stm32_pemf" / "Core" / "Inc" / "pemf_surus.h"


def _c_yorumsuz(metin: str) -> str:
    """C yorumlarını boşlukla değiştirir, string literallerini korur.

    ⚠️ D0Ö.13 ek: yorumdaki eski bir `#define PEMF_BOBIN_UNIPOLAR_MASKESI 0x00U` satırı (ör. belge
    bloğunda tarihçe) naif aramayı KANDIRIRDI — simülatör ve kapısı birlikte yanlış maskeyi okurdu.
    """
    return re.sub(
        r'"(?:\\.|[^"\\\n])*"|/\*.*?\*/|//[^\n]*',
        lambda m: m.group(0) if m.group(0).startswith('"') else " ",
        metin,
        flags=re.S,
    )


def maske_tanimi(baslik_metni: str) -> int:
    """Başlık metnindeki TEK, yorum DIŞI `#define PEMF_BOBIN_UNIPOLAR_MASKESI` değeri (yoksa/birden çoksa hata).

    ⚠️ Önişlemciyi GÖRMEZ — yalnız metinde ÇİFT tanım (ör. `#if/#else`in iki dalında birer tanım) gürültülü
    HATA verir (hangi dalın derlendiğini bilemez). TEK tanımlı `#if`/`#ifndef` varsayılan dalı (kardeş
    `PEMF_BOBIN_TERS_MASKESI`nin deseni) ise SESSİZCE başlıktaki değeri okur; `-D` ile birleşince (`#ifndef` + `-D`)
    derlenen değer başlıktakinden sapar — simülatör ve hizalama kapısı birlikte YEŞİL kalır (D0Ö.13 ek-3, tur 6).
    D0Ö.13 ek-4 (tur 7) kesinlik: `-D` tek başına bugünkü DÜZ tanımı ezemez (GCC önce `-D`'yi işler, başlıktaki
    sonraki `#define` "redefined" uyarısıyla onu değiştirir — başlık kazanır). Bugün (2026-09-30) başlıkta tek düz
    tanım var (`pemf_surus.h`; tanımı saran koşullu blok yalnız include koruması, :148-150'de ayrı bir `#ifndef`
    bloğu var) ve `.cproject`'te PEMF_* için `-D` yok (yalnız DEBUG, USE_HAL_DRIVER, STM32F429xx); desen
    değişirse bu okuyucu da güncellenmeli.
    """
    bulunan = re.findall(
        r"^[ \t]*#[ \t]*define[ \t]+PEMF_BOBIN_UNIPOLAR_MASKESI[ \t]+(0x[0-9A-Fa-f]+|\d+)[uU]?\b",
        _c_yorumsuz(baslik_metni),
        flags=re.M,
    )
    if len(bulunan) != 1:
        raise RuntimeError(
            f"PEMF_BOBIN_UNIPOLAR_MASKESI tanim sayisi {len(bulunan)} (1 bekleniyordu) — simulator firmware ile hizalanamaz"
        )
    return int(bulunan[0], 0)


def _firmware_unipolar_maskesi() -> int:
    """`pemf_surus.h` → `PEMF_BOBIN_UNIPOLAR_MASKESI` (bit i = bobin i+1 YALNIZ unipolar sürülebilir)."""
    try:
        metin = _SURUS_BASLIGI.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise RuntimeError(
            f"firmware basligi okunamadi: {_SURUS_BASLIGI} ({e}) — simulator firmware agaci olmadan hizalanamaz"
        ) from e
    return maske_tanimi(metin)


UNIPOLAR_YETENEK_MASKESI = _firmware_unipolar_maskesi()


def firmware_ack_yuzdesi(duty: float) -> int:
    """`main.c` ACK: `(long)(parsed.coil[i].duty * 100.0f)` — float32 çarpım, sıfıra doğru kırpma.

    ⚠️ D0Ö.13 ek: eskiden double ile `int(duty * 100)` idi — ürünün paketiyle 1-100 arası tamsayı
    yüzdelerin 48'inde firmware'den 1 EKSİK basıyordu (0.35f → 34, firmware 35; 0.01f → 0 → süre 0
    iken ürün bobini "durdu" gösterir). `duty` paketten gelen float32 değerdir; çarpım double'da TAM
    olduğundan float32'ye tek yuvarlama IEEE float32 çarpımının aynısıdır. Taşma/NaN: ARM `VCVT`
    32-bit doyurur, NaN → 0 (sonsuz/NaN duty zaten `decode_packet`te NACK'lenir). ⚠️ D0Ö.13 ek-4 (tur 7): doyurma bir
    VARSAYIMDIR — C'de `(long)` taşması tanımsız davranış; hard-float Cortex-M4 + -Os'ta `vcvt.s32.f32` beklenir ama
    objdump/tezgâhla ÖLÇÜLMEDİ (yayın öncesi / tezgâh listesinde).
    """
    try:
        carpim = struct.unpack("<f", struct.pack("<f", duty * 100.0))[0]
    except OverflowError:  # float32 aralığını aşan sonlu değer → +/-inf
        carpim = math.copysign(math.inf, duty)
    if math.isnan(carpim):
        return 0
    if math.isinf(carpim):
        return 2**31 - 1 if carpim > 0 else -(2**31)
    return max(-(2**31), min(2**31 - 1, int(carpim)))


def _banner_kipi(maske: int) -> str:
    """`main.c` banner üçlüsünün AYNISI: 0 → SYM-BIPOLAR, tüm bobinler → UNIPOLAR tek-bacak, aksi → KARMA."""
    if maske == 0:
        return "SYM-BIPOLAR"
    if maske == (1 << NUM_COILS) - 1:
        return "UNIPOLAR tek-bacak"
    return "KARMA"


def crc32_of(data: bytes) -> int:
    """IEEE 802.3 / zlib CRC32 — main.c calculate_crc32 ile identik."""
    return zlib.crc32(data) & 0xFFFFFFFF


def decode_packet(raw: bytes):
    """
    `PKT_SIZE` baytlık binary paketi çözer (7 bobin + kip baytı → 121 bayt).
    Başarıda ((duty, phase, freq, duration, ref_ms, unipolar_maskesi), None) döner — ⚠️ 6'LI.
    Hata durumunda (None, sebep_str) döner.
    (D0Ö.12: bu satır "5'li dönüş, 120 bayt" diyordu; `run()` 5'e açıp ilk pakette ölüyordu.)

    ⚠️ ALAN DİLİMLERİ `NUM_COILS`TEN TÜRER — ELLE YAZILMAZ (2026-09-11 düzeltmesi).
    2026-09-10'da `NUM_COILS` 5→7 ve `PKT_SIZE` 88→120 yapıldı ama BU FONKSİYONDAKİ
    dilimler `fields[2:7]`, `fields[7:12]`… diye 5 bobine SABİT kalmıştı. Sonuç:
    `ref_ms = fields[22]` aslında `freq[6]`yı okuyordu → simülatör her geçerli paketi
    yanlış çözüp reddediyordu. Yani simülatör SEVK EDİLENDEN FARKLI bir cihazı
    doğruluyordu ve `headless_core`daki "sanal-STM ile smoke-test edildi" notu geçersizdi.
    ⚠️ Parite kapısı (`tests/test_stm32_source_parity.py`) bunu GÖREMEDİ: yalnız SABİTLERİ
    (`NUM_COILS`, `PKT_SIZE`) eşliyordu, ÇÖZÜMLEME DAVRANIŞINI değil. Davranış kapısı:
    `tests/test_stm32_simulator_cozumleme.py`.
    """
    if len(raw) != PKT_SIZE:
        return None, f"boyut={len(raw)} != {PKT_SIZE}"

    # CRC doğrulama (son 4 byte hariç)
    calc_crc = crc32_of(raw[:-4])
    pkt_crc = struct.unpack_from("<I", raw, PKT_SIZE - 4)[0]
    if calc_crc != pkt_crc:
        return None, f"CRC calc={calc_crc:08X} pkt={pkt_crc:08X}"

    fields = struct.unpack(PKT_FMT, raw)
    hdr0, hdr1 = fields[0], fields[1]
    if hdr0 != 0xAA or hdr1 != 0x55:
        return None, f"header={hdr0:02X}{hdr1:02X}"

    # Yerleşim: [0,1]=header · duty[N] · phase[N] · freq[N] · duration[N] · ref_ms · crc32
    n = NUM_COILS
    duty = list(fields[2 : 2 + n])
    phase = list(fields[2 + n : 2 + 2 * n])
    freq = list(fields[2 + 2 * n : 2 + 3 * n])
    duration = list(fields[2 + 3 * n : 2 + 4 * n])
    ref_ms = fields[2 + 4 * n]
    unipolar_maskesi = fields[3 + 4 * n]
    # fields[4 + 4*n] = crc32 (zaten doğrulandı)

    # Değer kontrolleri
    if ref_ms > REF_MS_MAX:
        return None, f"ref_ms={ref_ms} > {REF_MS_MAX}"

    for i in range(NUM_COILS):
        # ⚠️ D0Ö.13 ek: firmware (`main.c` Coil_DecodeAndValidatePacket) sonlu-olmayan değeri ÖNCE ve bu
        # metinle NACK'ler. Eskiden NaN/+inf duty `< DUTY_MIN`'den geçiyor, `_send_ack` çöküyor ve
        # bağlantı KAPANIYORDU (firmware NACK'leyip sürer).
        for alan, dizi in (("duty", duty), ("phase", phase), ("freq", freq)):
            if not math.isfinite(dizi[i]):
                return None, f"RANGE coil={i + 1} field={alan} value=nonfinite"
        if duty[i] < DUTY_MIN:
            return None, f"coil={i + 1} duty={duty[i]:.3f} < {DUTY_MIN}"
        if not (PHASE_MIN <= phase[i] <= PHASE_MAX):
            return None, f"coil={i + 1} phase={phase[i]:.1f} out of [0,360]"
        if not (FREQ_MIN <= freq[i] <= FREQ_MAX):
            return None, f"coil={i + 1} freq={freq[i]:.1f} out of [{FREQ_MIN},{FREQ_MAX}]"
        if duration[i] > DUR_MAX:
            return None, f"coil={i + 1} duration={duration[i]} > {DUR_MAX}"

    return (duty, phase, freq, duration, ref_ms, unipolar_maskesi), None


class Stm32SimClient:
    """Tek bir GUI bağlantısını yöneten sınıf."""

    def __init__(self, conn: socket.socket, addr):
        self.conn = conn
        self.addr = addr
        self._lock = threading.Lock()
        self._coil_duty = [0.0] * NUM_COILS
        self._coil_start_ms = [None] * NUM_COILS  # datetime.now() veya None
        self._last_pkt_time = time.monotonic()
        self._any_active = False
        # D0Ö.12 ek: bağlantı bitince bekçi/süre işçileri DURUR (eskiden `while True` idi — her
        # bağlantı iki kalıcı thread sızdırıyordu). `run()`'ın `finally`'si kurar.
        self._dur = threading.Event()

    def _send(self, msg: str):
        try:
            with self._lock:
                self.conn.sendall(msg.encode("utf-8"))
        except Exception as e:
            log.warning("Gönderim hatası: %s", e)

    def _send_ready(self):
        time.sleep(READY_DELAY_S)  # USB enumerate simülasyonu
        # ⚠️ KANAL SAYISI TÜRETİLİR: elle yazılan "5-ch" 2026-09-10 geçişinde BAYATLADI ve
        # banner okuyan araçlar (scripts/stm_firmware_kimligi.py) simülatörü ESKİ firmware
        # sanardı. Tek kaynak `NUM_COILS`. ⚠️ D0Ö.13: kip ve maske de firmware'in derlenen maskesinden
        # (main.c banner'ı: "%u-ch %s uni=0x%02X"); "SIM" eki gerçek karttan ayırt ettirir.
        msg = (
            f"-> STM_READY: DDS v2.3 ({NUM_COILS}-ch {_banner_kipi(UNIPOLAR_YETENEK_MASKESI)} "
            f"uni=0x{UNIPOLAR_YETENEK_MASKESI:02X} SIM) Waiting for commands...\r\n"
        )
        self._send(msg)
        log.info("✅ STM_READY gönderildi → %s", self.addr)

    def _send_ack(self, duty, phase, freq, duration, kip_istegi: int = 0):
        # ⚠️ D0Ö.13 (B-10.267): firmware ACK'i NUM_COILS alan + ` K=<ETKİN maske>` basar (main.c ACK döngüsü;
        # etkin = yetenek | istek). Eskiden 5 alan ve K= yoktu → simülatörle koşan ürün bobin 6-7 için
        # coil_update almaz (onaysız/bayat görünür), kip göstergesi beslenmezdi.
        n = NUM_COILS
        # Firmware etkin kipi yalnız NUM_COILS bit üzerinden kurar (yetenek de kırpılır — main.c:640-641).
        etkin = (UNIPOLAR_YETENEK_MASKESI | int(kip_istegi)) & ((1 << n) - 1)
        msg = (
            "-> STM_OK: "
            f"D={','.join(str(firmware_ack_yuzdesi(duty[i])) for i in range(n))} "
            f"P={','.join(str(int(phase[i])) for i in range(n))} "
            f"F={','.join(str(int(freq[i])) for i in range(n))} "
            f"T={','.join(str(duration[i]) for i in range(n))} "
            f"K={etkin}"
            "\r\n"
        )
        self._send(msg)
        active = [i + 1 for i in range(NUM_COILS) if duty[i] > 0]
        log.info(
            "📨 STM_OK | Aktif bobinler: %s | Duty: %s | Freq: %s Hz",
            active or "yok",
            [f"{d:.2f}" for d in duty],
            [f"{f:.0f}" for f in freq],
        )

    def _watchdog_worker(self):
        """1.5 s iletişim yoksa bobinleri sıfırla — main.c ile aynı davranış."""
        while not self._dur.wait(0.2):
            if self._any_active:
                elapsed_ms = (time.monotonic() - self._last_pkt_time) * 1000
                if elapsed_ms > WATCHDOG_MS:
                    self._any_active = False
                    self._coil_duty = [0.0] * NUM_COILS
                    msg = "-> STM_ERR: Watchdog Timeout! Baglanti koptu, bobinler 0'landi.\r\n"
                    self._send(msg)
                    log.warning("⏱️  Watchdog tetiklendi (%d ms iletişim yok)", int(elapsed_ms))

    def _duration_worker(self):
        """Süre dolduğunda bobinleri kapat — main.c ile aynı davranış."""
        while not self._dur.wait(0.5):
            stopped_any = False
            for i in range(NUM_COILS):
                if self._coil_start_ms[i] is not None and self._coil_duty[i] > 0:
                    # dur_min bilgisi burada yok; duration tracking için
                    # dışarıdan set edilen _coil_dur_min listesi kullanılıyor
                    dur_min = getattr(self, "_coil_dur_min", [0] * NUM_COILS)[i]
                    if dur_min > 0:
                        elapsed_s = time.monotonic() - self._coil_start_ms[i]
                        target_s = dur_min * 60.0
                        if elapsed_s >= target_s:
                            self._coil_duty[i] = 0.0
                            self._coil_start_ms[i] = None
                            stopped_any = True
                            log.info("⏹️  Bobin %d süresi doldu (%d dk)", i + 1, dur_min)
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
                        break  # daha fazla veri bekle
                    raw = buf[:PKT_SIZE]
                    buf = buf[PKT_SIZE:]

                    result, err = decode_packet(raw)
                    if err:
                        nack = f"-> STM_NACK: {err}\r\n"
                        self._send(nack)
                        log.warning("❌ NACK: %s", err)
                        continue

                    # ⚠️ D0Ö.12 (B-10.176): `decode_packet` 2026-09-11'den beri 6'lı döner (kip maskesi).
                    # Burada 5'e açılıyordu → ürünün İLK geçerli paketinde ValueError, genel `except`
                    # bağlantıyı KAPATIYORDU (sanal-STM ilk gerçek pakette ölüyordu). Kapı:
                    # tests/test_stm32_simulator_run_yolu.py
                    duty, phase, freq, duration, ref_ms, kip_istegi = result
                    self._last_pkt_time = time.monotonic()
                    self._any_active = any(d > 0 for d in duty)
                    self._coil_duty = list(duty)
                    self._coil_dur_min = list(duration)

                    # Süre başlangıcı güncelle
                    for i in range(NUM_COILS):
                        if duty[i] > 0 and self._coil_start_ms[i] is None:
                            self._coil_start_ms[i] = time.monotonic()
                        elif duty[i] == 0:
                            self._coil_start_ms[i] = None

                    self._send_ack(duty, phase, freq, duration, kip_istegi)

        except ConnectionResetError:
            log.info("🔌 Bağlantı sıfırlandı: %s", self.addr)
        except Exception as e:
            log.error("Hata: %s", e)
        finally:
            self._dur.set()  # bekçi/süre işçileri bu bağlantıyla birlikte biter
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
            t = threading.Thread(target=client.run, daemon=True, name=f"SimClient-{addr[1]}")
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
    parser.add_argument("--host", default=SIM_HOST, help=f"Sunucu adresi (varsayılan: {SIM_HOST})")
    parser.add_argument("--port", type=int, default=SIM_PORT, help=f"TCP port (varsayılan: {SIM_PORT})")
    parser.add_argument("--set-port", action="store_true", help="Sabit COM10 modunda devre dışı; bilgi mesajı yazdırır")
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
