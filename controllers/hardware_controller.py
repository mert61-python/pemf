import time
import queue
import struct
import zlib
import logging
import threading
from utils.stm32_protocol_limits import (
    duty_percent_to_ratio,
    normalize_duration_minutes,
    normalize_frequency_hz,
    normalize_phase_deg,
)

class HardwareController:
    """
    Headless donanım kontrolcüsü. Eski PyQt tabanlı unified_control_window.py
    içindeki donanım paketleme ve kuyruğa (Queue) iletme mantığını soyutlar.
    """
    def __init__(self, core_instance):
        self.core = core_instance
        self.logger = logging.getLogger(self.__class__.__name__)

        # 5 Bobin için bellek içi (In-Memory) state
        # Arayüz olmadığı için (Headless), parametreler burada tutulur
        self.coils_state = {
            i: {
                "is_running": False,
                "duty": 0.0,
                "phase": 0.0,
                "freq": 100.0,
                "duration": 0
            } for i in range(1, 6)
        }

        # P0 fix: coils_state + paket kurulumunu koruyan TEK kilit. API thread'leri
        # (update_coil/start_all/stop_all/on_disconnect) ile 1 Hz keep-alive thread'i
        # ayni sozluge yaris icinde eriyordu → bir STOP, es-zamanli keep-alive tazelemesiyle
        # ezilip bobin enerjili kalabiliyordu. RLock re-entrant (public metod → _send... nested).
        self._state_lock = threading.RLock()

        # P0 fix: donanim-tarafi SURE siniri (per-bobin monotonic deadline). Session-DISI
        # surus yollarinda (/api/coil/{id}/control, /api/coil/batch, /api/ai/ai_pro/frame)
        # yazilim watchdog'u YOKTU ve keep-alive her sn paketi (duration dahil) yeniden
        # gonderip firmware'in kendi sure-timer'ini resetliyordu → bobin SURESIZ enerjili
        # kalabiliyordu. Burada kullanicinin/uygulamanin ZATEN girdigi sureyi zorunlu kilariz
        # (yeni bir guvenlik-limiti DEGIL; istenen sureyi uygular). duration=0 → sinirsiz (degismedi).
        self._coil_deadline = {i: None for i in range(1, 6)}

        # P0 fix: STOP garanti-teslim. Tek STOP paketi seri yazma hatasinda dusserse keep-alive
        # normalde tazelemezdi (any_running False). Durdurma sonrasi paketi birkac dongu tekrar
        # gonderir → dusen STOP telafi edilir.
        self._force_send_left = 0

        self._keep_alive_stop = threading.Event()
        self._keep_alive_thread = threading.Thread(target=self._keep_alive_loop, daemon=True, name="HWKeepAlive")
        self._keep_alive_thread.start()

    def _keep_alive_loop(self):
        while not self._keep_alive_stop.is_set():
            try:
                self._tick()
            except Exception:
                self.logger.exception("keep-alive tick hatasi")
            time.sleep(1.0)

    def _tick(self):
        """Her saniye: (1) sure-limiti dolan bobinleri donanim-tarafi otomatik durdur,
        (2) calisan bobinler icin keep-alive paketi + STOP-sonrasi birkac tazeleme gonder."""
        with self._state_lock:
            now = time.monotonic()
            expired = [
                i for i in range(1, 6)
                if self.coils_state[i]["is_running"]
                and self._coil_deadline[i] is not None
                and now >= self._coil_deadline[i]
            ]
            for i in expired:
                self.coils_state[i]["is_running"] = False
                self.coils_state[i]["duty"] = 0.0
                self._coil_deadline[i] = None
            if expired:
                self._force_send_left = 3
                self.logger.info("Bobin(ler) %s sure limiti doldu → donanim-tarafi otomatik durduruldu.", expired)

            any_running = any(self.coils_state[i]["is_running"] for i in range(1, 6))
            need_send = any_running or self._force_send_left > 0
            if self._force_send_left > 0:
                self._force_send_left -= 1
            if need_send:
                self._send_stm_manual_update()

    def stop(self):
        self._keep_alive_stop.set()

    def update_coil(self, coil_id: int, freq: float, duty: float, phase: float, duration: int, start: bool = True):
        """
        Belirli bir bobinin durumunu günceller ve STM32'ye yeni komut paketini fırlatır.
        duration birimi STM32 firmware ile uyumlu olarak dakikadır.
        """
        if coil_id < 1 or coil_id > 5:
            self.logger.warning(f"Geçersiz bobin ID: {coil_id}")
            return False

        with self._state_lock:
            if start:
                dur_min = normalize_duration_minutes(duration)
                self.coils_state[coil_id]["is_running"] = True
                self.coils_state[coil_id]["freq"] = normalize_frequency_hz(freq)
                # duty birimi her zaman yüzde kabul edilir; ust limit firmware/timer tarafinda saturate olur.
                self.coils_state[coil_id]["duty"] = duty_percent_to_ratio(duty)
                self.coils_state[coil_id]["phase"] = normalize_phase_deg(phase)
                self.coils_state[coil_id]["duration"] = dur_min
                # Istenen sure > 0 ise donanim-tarafi deadline kur (keep-alive'a ragmen durur).
                self._coil_deadline[coil_id] = (time.monotonic() + dur_min * 60) if dur_min > 0 else None
            else:
                self.coils_state[coil_id]["is_running"] = False
                self.coils_state[coil_id]["duty"] = 0.0
                self._coil_deadline[coil_id] = None
                self._force_send_left = 3  # dusen STOP'u telafi et

            self.logger.info(f"Coil {coil_id} durumu güncellendi: Start={start}, Freq={freq}, Duty={duty}, Phase={phase}, Dur={duration}")
            self._send_stm_manual_update()
        return True

    def start_all_coils(self, freq=100.0, duty=25.0, phase=0.0, duration=30):
        """Tüm STM bobinlerini başlatır. duration birimi dakikadır."""
        with self._state_lock:
            dur_min = normalize_duration_minutes(duration)
            deadline = (time.monotonic() + dur_min * 60) if dur_min > 0 else None
            for i in range(1, 6):
                self.coils_state[i]["is_running"] = True
                self.coils_state[i]["freq"] = normalize_frequency_hz(freq)
                self.coils_state[i]["duty"] = duty_percent_to_ratio(duty)
                self.coils_state[i]["phase"] = normalize_phase_deg(phase)
                self.coils_state[i]["duration"] = dur_min
                self._coil_deadline[i] = deadline

            self.logger.info(f"Tüm bobinler (1-5) başlatıldı. Freq={freq}, Duty={duty}")
            self._send_stm_manual_update()
        return True

    def stop_all_coils(self):
        with self._state_lock:
            for i in range(1, 6):
                self.coils_state[i]["is_running"] = False
                self.coils_state[i]["duty"] = 0.0
                self._coil_deadline[i] = None
            self._force_send_left = 3  # dusen STOP'u telafi et

            self.logger.info("Tüm bobinler (1-5) durduruldu.")
            self._send_stm_manual_update()
        return True

    def on_disconnect(self):
        """STM seri bağlantısı koptuğunda çağrılır. Tüm bobin durumlarını SIFIRLA:
        (1) keep-alive artık 'çalışıyor' paketi tazelemesin, (2) bağlantı dönünce ESKİ
        freq/duty ile otomatik RE-FIRE olmasın (firmware watchdog'u geçersiz kılınmasın)."""
        with self._state_lock:
            for i in range(1, 6):
                self.coils_state[i]["is_running"] = False
                self.coils_state[i]["duty"] = 0.0
                self.coils_state[i]["duration"] = 0
                self._coil_deadline[i] = None
            self._force_send_left = 0  # baglanti kopuk → gonderim anlamsiz
        self.logger.warning("STM bağlantısı koptu → tüm bobin durumları sıfırlandı (re-fire engellendi).")
        return True

    def _send_stm_manual_update(self):
        """
        Tüm bobinlerin güncel statüsünü okur, binary STM32 paketine çevirir
        ve HeadlessCore.hw_send_queue kuyruğuna koyar.
        """
        if not self.core or not hasattr(self.core, '_hw_send_queue'):
            self.logger.warning("HeadlessCore referansı veya '_hw_send_queue' bulunamadı!")
            return

        stm32_duties = []
        stm32_phases = []
        stm32_freqs = []
        stm32_durs = []

        # State okuma + paket kurulumu kilit altinda (keep-alive/API yarisi). RLock re-entrant.
        with self._state_lock:
            for i in range(1, 6):
                state = self.coils_state[i]
                if state["is_running"]:
                    stm32_duties.append(state["duty"])
                    stm32_phases.append(state["phase"])
                    stm32_freqs.append(state["freq"])
                    stm32_durs.append(state["duration"])
                else:
                    stm32_duties.append(0.0)
                    stm32_phases.append(0.0)
                    stm32_freqs.append(state["freq"]) # kapalıysa da son freq kalır
                    stm32_durs.append(0)

        ref_ms = int(time.monotonic() * 1000) % 1000

        # Binary STM32 Packet Format:
        # <BB : header (0xAA, 0x55)
        # 5f  : duty
        # 5f  : phase
        # 5f  : freq
        # 5I  : duration
        # H   : ref_ms
        # I   : crc32

        fmt = '<BB 5f 5f 5f 5I H'
        data_bytes = struct.pack(
            fmt,
            0xAA, 0x55,
            *stm32_duties,
            *stm32_phases,
            *stm32_freqs,
            *stm32_durs,
            ref_ms
        )
        crc32_val = zlib.crc32(data_bytes) & 0xFFFFFFFF
        stm_msg = data_bytes + struct.pack('<I', crc32_val)

        udp_pkt = b''
        ESP32_IP = "192.168.137.255"
        ESP32_PORT = 5005

        try:
            self.core._hw_send_queue.put_nowait((stm_msg, udp_pkt, ESP32_IP, ESP32_PORT))
        except queue.Full:
            try:
                self.core._hw_send_queue.get_nowait()
                self.core._hw_send_queue.put_nowait((stm_msg, udp_pkt, ESP32_IP, ESP32_PORT))
            except queue.Empty:
                pass
