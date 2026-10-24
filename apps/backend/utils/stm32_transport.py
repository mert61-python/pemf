# Author: mertaygn, cglrgrkn
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
FIXED_STM32_PORT = "COM10"  # default/legacy (ST-Link VCP, Nucleo-F429ZI USART3 @ PD8/PD9)
ST_LINK_USB_VID = 0x0483  # STMicroelectronics
# ST-Link VCP USB PID'leri (V1/V2/V2-1/V3). Onboard STM CDC (örn LattePanda, PID 0x5740)
# BU SETTE YOK → oto-algılamada onboard STM'i ELER, yanlış porta (COM3) gitmez.
ST_LINK_USB_PIDS = frozenset({0x3744, 0x3748, 0x374B, 0x374D, 0x374E, 0x374F, 0x3752, 0x3753})
DEFAULT_BAUDRATE = 115200
DEFAULT_HANDSHAKE_TIMEOUT_SEC = 12.0
# ⚠️ D2.10 (B-1.14): STM takılı değilken yeniden deneme (~3 sn) her seferinde "Port seçimi" INFO + "Bağlantı başarısız" WARNING
# (oto-algılamada ayrıca 15 sn'de bir "ST-Link bulunamadı") basıyordu — sahadaki 1.9.50 günlüğünün %75-90'ı; 10 MB'lık dosya 3-10
# günde dönüp NACK / watchdog / çökme izini siliyordu. Artık DURUM DEĞİŞİMİNDE bir kez (ilk başarısızlık, hata metni ya da port
# değişince, başarıdan sonraki ilk başarısızlık) + bu aralıkla ÖZET (ardışık deneme sayısı + son hata). Başarı durumu sıfırlar.
# Kapı: tests/test_stm_YOKKEN_gunluk_DURUM_degisiminde_ve_OZETLE_D210.py
DEFAULT_NO_PORT_LOG_INTERVAL_SEC = 600.0
DEFAULT_FAILURE_SUMMARY_INTERVAL_SEC = 600.0
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
    #: TD1 · TD7: el sıkışma doğrulama yoklamasının özeti (`_dogrulama_yoklamasi`) — {kabul, kimlik, crc_nack, yoklama}.
    dogrulama: Optional[dict] = None


#: STM32 binary komut paketindeki BOBİN ALANI SAYISI = firmware `NUM_COILS`.
#: ⚠️ Bu, backend topolojisindeki STM bobin sayısı DEĞİL, PROTOKOL GENİŞLİĞİdir. İkisi
#: 2026-09-10'da ayrıldı: firmware 7 bobin sürebiliyor (bobin 6-7 ESP'den taşındı), ama
#: backend `STM_COIL_IDS` hâlâ 1-5 — kullanılmayan alanlar SIFIR gider. Paket genişliği
#: firmware ile BİREBİR olmak ZORUNDA: bir alan fazla/eksik → CRC ve boyut tutmaz →
#: firmware her paketi NACK'ler → HİÇBİR bobin çalışmaz.
#: Kapı: tests/test_stm32_source_parity.py (bu değeri firmware kaynağından çözüp karşılaştırır).
STM_PAKET_BOBIN_SAYISI = 7

#: `struct` biçimi ve paket boyu — SAYIYI ELLE YAZMA, yukarıdaki sabitten türet.
#: ⚠️ SON ALAN `B` = `unipolar_maskesi` (2026-09-11): bit i set → bobin i+1 UNIPOLAR
#: surulsun. Bu bir ISTEKTIR; firmware onu DONANIM YETENEGIYLE OR'lar
#: (`PEMF_BOBIN_UNIPOLAR_MASKESI`) → yalniz-unipolar bobin (6-7) bipolara CEVRILEMEZ.
STM_PAKET_FMT = "<BB {n}f {n}f {n}f {n}I H B".format(n=STM_PAKET_BOBIN_SAYISI)
#: crc32 dahil toplam boy (7 bobin → 121 bayt).
STM_PAKET_BOYU = struct.calcsize(STM_PAKET_FMT) + 4

#: Y68 (sahip; Oturum 13 / TD1): komut paketi PROTOKOL REVİZYONU — firmware `main.c::PEMF_PROTOKOL_REV` ile BİREBİR
#: (kapı: tests/test_stm32_source_parity.py). 1 = 5 kanal / 88 B · 2 = 7 kanal / 120 B · 3 = 7 kanal + kip baytı / 121 B
#: + kimlik sorgusu. Kart banner'da ve kimlik yanıtında `proto=` / `pkt=` basar.
STM_PROTOKOL_REV = 3
#: Y68: kimlik sorgusu çerçevesi (firmware `KIMLIK_SORGU_B0..B3`). ⚠️ 0xAA İÇERMEZ → eski firmware'in RX durum makinesi
#: bu baytları SESSİZCE yok sayar (NACK yok, PWM'e dokunulmaz); yeni firmware `-> STM_ID: <banner gövdesi>` döner.
STM_KIMLIK_SORGUSU = bytes((0xA5, 0x5A, 0x49, 0x44))

#: TD1 · TD7: el sıkışmadan SONRA kartın paketimizi GERÇEKTEN kabul ettiğinin ölçümü (doğrulama yoklaması). Ölçüldü (tezgâh
#: 2026-10-14): 120 baytlık saha imajı banner'ı 121 baytlık imajla AYNI basıyor ve boşta hiç paket gitmediği için kart
#: uyumsuzluğu ancak seans başlatılınca (NACK) görünüyordu; USB yeniden bağlanmasında da hiç paket gitmiyordu (25 sn'de
#: STM_OK 0). Yoklama = kimlik sorgusu + en çok `DOGRULAMA_YOKLAMA_SAYISI` sıfır-duty paketi (STOP — çıkışlara güvenli;
#: el sıkışmanın kendi yoklamasıyla aynı paket). Doğrudan porta yazılır (HWSender kuyruğu DEĞİL → NACK'te yeniden oynatma
#: yok). Sonuç `Stm32OpenResult.dogrulama`'da; karar `HeadlessCore` (çekirdek satırları `on_line`'dan ayrıca görür).
#: ⚠️ T-a (Tezgâh-2 #1): backend el sıkışmasının değerleri BİLEREK değişmedi (yoklama 3, pencere 1,5 sn). (a) El sıkışma bu pencere
#: bitmeden dönmez → yeniden bağlanmada ACİL DURDUR'un porta İLK yazımı en çok bu kadar gecikir (pencere 4,2 sn'ye çıkarılınca TD3 /
#: T2D-1 kapısında yanıtsız kartta E-stop STOP'u porta YAZILAMADI). (b) Fazladan yoklamanın GEÇ gelen NACK'i el sıkışmadan SONRA canlı
#: hatta düşüp yeniden gönderim zinciri başlatır (geç NACK'li saha kartında E-stop raporu "yanıtsız" yerine "red"). Kayıplı NACK'li eski
#: kartta backend'in kesin kararı canlı trafiğin NACK'lerinden gelir (`live_state` sistematik red). Servis araçları (kimlik betiği,
#: `stm_yak` doğrulaması — portu ARAÇ tutar, backend kapalı) daha çok yoklamayla ölçer: `utils.stm32_uart.ARAC_*`.
DOGRULAMA_YOKLAMA_SAYISI = 3
DOGRULAMA_ARALIK_SN = 0.1
DOGRULAMA_SURESI_SN = 1.5
#: Kimlik yanıtı gerçek kartta ~10 ms'de gelir; eski kart hiç yanıtlamaz → kabul görüldükten sonra en çok bu kadar beklenir.
DOGRULAMA_KIMLIK_BEKLEME_SN = 0.6


def build_stm32_zero_duty_packet(freq_hz: float = 100.0) -> bytes:
    """main.c ile uyumlu SIFIR-DUTY paketi (ping/stop). Genişlik: STM_PAKET_BOBIN_SAYISI."""
    n = STM_PAKET_BOBIN_SAYISI
    ref_ms = int(time.monotonic() * 1000) % 1000
    data = struct.pack(
        STM_PAKET_FMT,
        0xAA,
        0x55,
        *([0.0] * n),
        *([0.0] * n),
        *([float(freq_hz)] * n),
        *([0] * n),
        ref_ms,
        0,  # unipolar_maskesi: sifir-duty ping/stop paketinde kip ISTEGI YOK
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
        failure_summary_interval_sec: float = DEFAULT_FAILURE_SUMMARY_INTERVAL_SEC,
    ) -> None:
        self.logger = logger
        self.baudrate = int(baudrate)
        self.handshake_timeout_sec = float(handshake_timeout_sec)
        self.no_port_log_interval_sec = float(no_port_log_interval_sec)
        self.bad_port_cooldown_sec = float(bad_port_cooldown_sec)
        self.failure_summary_interval_sec = float(failure_summary_interval_sec)
        self.settings = settings
        self._last_no_port_log = -float("inf")
        self._bad_ports_until: dict[str, float] = {}
        # D2.10: durum-değişimi günlüğü — son yazılan port seçimi, başarısızlık imzası (port + hata), ardışık deneme sayısı.
        self._son_secim_logu: Optional[tuple] = None
        self._hata_imzasi: Optional[tuple] = None
        self._ardisik_hata = 0
        self._son_hata_ozeti = 0.0
        #: D1.103 (B-1.21): son el sıkışmada görülen `STM_NACK` satırı sayısı (zaman aşımı teşhisini seçer).
        self._el_sikisma_nack = 0

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
                self._hata_imzasi = None  # D2.10: port AÇILDI → sonraki açılış hatası YENİ durumdur, yeniden yazılır
                if self._el_sikisma_nack:
                    # ⚠️ D1.103 (B-1.21, ölçüldü d01t83 durum D): kart YANIT VERİYOR ama sıfır-duty yoklamasını REDDEDİYOR
                    # (resetsiz bağlanan eski/uyumsuz firmware — banner da görülmedi). Eskiden aşağıdaki kablo/port
                    # metni basılıyordu → destek yanlış yöne (USART3/COM10) gidiyordu.
                    self._log_warning(
                        "[STM32] Handshake zaman aşımı (%.1f s) → %s; kart YANIT VERİYOR ama sıfır-duty yoklamasını %d "
                        "kez REDDETTİ (STM_NACK) ve STM_READY görülmedi — karttaki firmware bu uygulamanın %d baytlık "
                        "paketini anlamıyor, kimlik okunamadı. Kartı güncel firmware ile yeniden yakın "
                        "(docs/SAHA-ISLERI-REHBERI.md B-2) ya da RESET'e basıp açılış satırını okutun. Port kapatıldı.",
                        self.handshake_timeout_sec,
                        candidate.label(),
                        self._el_sikisma_nack,
                        STM_PAKET_BOYU,
                    )
                    return None
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
            if self._ardisik_hata:
                self._log_info("[STM32] Bağlantı %d başarısız denemeden sonra kuruldu.", self._ardisik_hata)
            self._durum_sifirla()
            # TD1 · TD7: kart paketimizi GERÇEKTEN kabul ediyor mu (banner bunu söyleyemez) — her bağlantıda, yeniden
            # bağlanma dahil. Yoklama hatası bağlantıyı DÜŞÜRMEZ (yalnız kanıt eksik kalır).
            dogrulama = self._dogrulama_yoklamasi(serial_obj, candidate, stop_event, on_line, ready_line)
            return Stm32OpenResult(serial=serial_obj, candidate=candidate, ready_line=ready_line, dogrulama=dogrulama)
        except Exception as exc:
            if serial_obj is not None:
                self.close_serial(serial_obj)
            self._mark_bad(candidate.device)
            self._baglanti_hatasi(candidate, exc)
            return None

    def close_serial(self, serial_obj: Any) -> None:
        try:
            if serial_obj and getattr(serial_obj, "is_open", False):
                serial_obj.close()
        except Exception:
            pass

    def port_hala_var(self, port_adi: Optional[str]) -> bool:
        """Bu port hâlâ sistemde numaralandırılıyor mu? (kablo çıktı mı)

        ⚠️ NEDEN GEREKLİ (sahip talebi 2026-09-11: "kablo çıktı bobinler offline dönsün"):
        Hiçbir bobin çalışmazken UART **tamamen sessizdir** — keep-alive koşulsuz değildir
        ve firmware de ilk paketten sonra ping'i keser. Yazma da okuma da olmadığı için
        kopuş hiçbir istisna üretmez; arayüz STM'i sonsuza dek "bağlı" gösterirdi.
        USB çekilince COM portu numaralandırmadan DÜŞER → kesin ölçüt budur.

        ⚠️ FAIL-OPEN: numaralandırma yapılamazsa (pyserial yok, izin hatası) `True` döner.
        "Bilmiyorum"u "koptu" saymak, çalışan bir bağlantıyı boşuna düşürürdü.

        ⚠️ SANAL PORTLAR MUAF: `socket://` (stm32_simulator), `loop://`, `rfc2217://`
        işletim sistemi port listesinde GÖRÜNMEZ; onları "kayboldu" saymak simülatör
        tabanlı testleri ve uzak-seri köprüyü anında koparırdı.
        """
        if not port_adi:
            return True
        if "://" in str(port_adi):
            return True  # sanal/uzak port — numaralandırmaya tabi değil
        try:
            from serial.tools import list_ports

            mevcut = {str(p.device).upper() for p in list_ports.comports()}
        except Exception:
            return True  # numaralandıramıyoruz → "koptu" DEME
        return str(port_adi).upper() in mevcut

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
            self._throttled_no_port_log(f"[STM32] {candidate.device} cooldown dolana kadar bekleniyor.")
            return None
        # D2.10: seçim yalnız DEĞİŞİNCE (ya da başarılı bağlantıdan sonraki ilk denemede) yazılır.
        secim = (candidate.label(), self.baudrate)
        if secim != self._son_secim_logu:
            self._son_secim_logu = secim
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
            desc = getattr(p, "description", "") or ""
            descu = desc.upper().replace("-", "")
            is_stlink = (
                (vid == ST_LINK_USB_VID and pid in ST_LINK_USB_PIDS) or "STLINKVIRTUALCOM" in descu or "STLINK" in descu
            )
            if is_stlink:
                return Stm32PortCandidate(device=p.device, description=f"oto ST-Link: {desc}".strip())
        return None

    # ── Port Açma ─────────────────────────────────────────────────────────────

    def _open_serial(self, candidate: Stm32PortCandidate) -> Any:
        import serial as serial_lib

        dev = candidate.device
        # socket:// (STM simülatörü / uzak-seri köprü) + rfc2217:// + loop:// → serial_for_url.
        # Gerçek COM (ST-Link VCP) → klasik Serial. Böylece SANAL-STM ile test edilebilir + sahada
        # uzak-seri desteklenir; gerçek-COM yolu ve DTR/RTS davranışı DEĞİŞMEZ (geriye uyumlu).
        if "://" in dev:
            serial_obj = serial_lib.serial_for_url(dev, baudrate=self.baudrate, timeout=0.3, write_timeout=1.0)
        else:
            serial_obj = serial_lib.Serial(
                candidate.device,
                self.baudrate,
                timeout=0.3,
                write_timeout=1.0,
                dsrdtr=False,  # DTR kapalı: ST-Link VCP’de aynı anda MCU reset'ini önler
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
        READY lines only. The active probe is a valid zero-duty packet (STM_PAKET_BOYU bayt):
        it is safe for outputs and returns STM_OK when the protocol path works.
        """
        start = time.monotonic()
        deadline = start + self.handshake_timeout_sec
        next_probe_at = start + HANDSHAKE_PASSIVE_LISTEN_SEC
        self._el_sikisma_nack = 0

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
                    if "STM_NACK" in decoded:
                        self._el_sikisma_nack += 1

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

    def _dogrulama_yoklamasi(
        self,
        serial_obj: Any,
        candidate: Stm32PortCandidate,
        stop_event: Any,
        on_line: Optional[Callable[[str], None]],
        ready_line: str,
        *,
        yoklama_sayisi: int | None = None,
        sure_sn: float | None = None,
    ) -> dict:
        """TD1 · TD7 (Y68): el sıkışmadan SONRA kimlik sorgusu + en çok `DOGRULAMA_YOKLAMA_SAYISI` sıfır-duty paketi.

        Çıkış: kabul (STM_OK / RANGE NACK) görüldü VE (kimlik geldi ya da `DOGRULAMA_KIMLIK_BEKLEME_SN` doldu) · arada kabul
        olmadan `PAKET_RED_CRC_ESIGI` CRC NACK · `DOGRULAMA_SURESI_SN` doldu. Okunan her satır `on_line`'a verilir (karar
        çekirdekte: `HeadlessCore` aynı satırları sınıflar). ⚠️ Sıfır-duty paketi STOP'tur (çıkışlara güvenli; el sıkışma
        yoklamasının aynısı) ve DOĞRUDAN porta yazılır — HWSender kuyruğuna girmez, NACK'te yeniden oynatılmaz.
        ⚠️ ESKİ kart kimlik sorgusunu (0xAA'sız çerçeve) yok sayar: NACK'i ve PWM etkisi YOK.
        `yoklama_sayisi` / `sure_sn` (T-a): yalnız servis araçları verir (`stm32_uart.kart_dogrula`); backend el sıkışması varsayılanla."""
        from utils.stm32_kimlik import KANIT_KABUL, KIMLIK_YANIT_ONEKI, PAKET_RED_CRC_ESIGI, paket_yaniti_siniflandir

        ozet: dict = {
            "kabul": paket_yaniti_siniflandir(ready_line) == KANIT_KABUL,
            "kimlik": None,
            "crc_nack": 0,
            "yoklama": 0,
        }
        try:
            serial_obj.write(STM_KIMLIK_SORGUSU)
        except Exception as exc:
            self._log_warning("[STM32] Kimlik sorgusu yazılamadı %s: %s", candidate.device, exc)
            return ozet
        azami_yoklama = DOGRULAMA_YOKLAMA_SAYISI if yoklama_sayisi is None else int(yoklama_sayisi)
        pencere = DOGRULAMA_SURESI_SN if sure_sn is None else float(sure_sn)
        bas = time.monotonic()
        sonraki_yoklama = bas
        while time.monotonic() - bas < pencere:
            if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
                break
            if ozet["crc_nack"] >= PAKET_RED_CRC_ESIGI and not ozet["kabul"]:
                break
            if ozet["kabul"] and (ozet["kimlik"] or time.monotonic() - bas >= DOGRULAMA_KIMLIK_BEKLEME_SN):
                break
            simdi = time.monotonic()
            if not ozet["kabul"] and ozet["yoklama"] < azami_yoklama and simdi >= sonraki_yoklama:
                try:
                    serial_obj.write(build_stm32_zero_duty_packet())
                except Exception as exc:
                    self._log_warning("[STM32] Doğrulama yoklaması yazılamadı %s: %s", candidate.device, exc)
                    break
                ozet["yoklama"] += 1
                sonraki_yoklama = simdi + DOGRULAMA_ARALIK_SN
            try:
                line = serial_obj.readline()
            except Exception as exc:
                self._log_warning("[STM32] Doğrulama okuma hatası %s: %s", candidate.device, exc)
                break
            if not line:
                continue
            decoded = line.decode("utf-8", errors="ignore").strip()
            if not decoded:
                continue
            if on_line is not None:
                try:
                    on_line(decoded)
                except Exception as exc:
                    self._log_warning("[STM32] Doğrulama callback hatası: %s", exc)
            if KIMLIK_YANIT_ONEKI in decoded:
                ozet["kimlik"] = decoded
            sinif = paket_yaniti_siniflandir(decoded)
            if sinif == KANIT_KABUL:
                ozet["kabul"] = True
            elif sinif == "crc" and not ozet["kabul"]:
                ozet["crc_nack"] += 1
        self._log_info(
            "[STM32] El sıkışma doğrulaması: kabul=%s kimlik=%s crc_nack=%d yoklama=%d (%.2f sn)",
            ozet["kabul"],
            "VAR" if ozet["kimlik"] else "YOK",
            ozet["crc_nack"],
            ozet["yoklama"],
            time.monotonic() - bas,
        )
        return ozet

    # ── Yardımcı Metodlar ─────────────────────────────────────────────────────

    def _mark_bad(self, device: str) -> None:
        if device:
            self._bad_ports_until[device.upper()] = time.monotonic() + self.bad_port_cooldown_sec

    def _throttled_no_port_log(self, message: str) -> None:
        now = time.monotonic()
        if now - self._last_no_port_log >= self.no_port_log_interval_sec:
            self._last_no_port_log = now
            self._log_info(message)

    def _baglanti_hatasi(self, candidate: Stm32PortCandidate, exc: Exception) -> None:
        """D2.10: açılamayan port DURUM DEĞİŞİMİNDE bir kez (ilk / farklı hata ya da port) + seyrek ÖZETLE yazılır."""
        self._ardisik_hata += 1
        now = time.monotonic()
        imza = (candidate.device.upper(), type(exc).__name__, str(exc))
        if imza != self._hata_imzasi:
            self._hata_imzasi = imza
            self._son_hata_ozeti = now
            self._log_warning(
                "[STM32] Bağlantı başarısız → %s: %s (yeniden denenecek; aynı hata %d sn'de bir özetlenir)",
                candidate.label(),
                exc,
                int(self.failure_summary_interval_sec),
            )
        elif now - self._son_hata_ozeti >= self.failure_summary_interval_sec:
            self._son_hata_ozeti = now
            self._log_warning(
                "[STM32] Bağlantı hâlâ kurulamıyor → %s: %d ardışık deneme; son hata: %s",
                candidate.label(),
                self._ardisik_hata,
                exc,
            )

    def _durum_sifirla(self) -> None:
        """Başarılı bağlantı: bir sonraki kesinti / seçim / 'port yok' durumu yeniden BİR KEZ yazılsın."""
        self._ardisik_hata = 0
        self._hata_imzasi = None
        self._son_secim_logu = None
        self._last_no_port_log = -float("inf")

    def _log_info(self, message: str, *args: Any) -> None:
        if self.logger:
            self.logger.info(message, *args)

    def _log_warning(self, message: str, *args: Any) -> None:
        if self.logger:
            self.logger.warning(message, *args)
