import time
import queue
import logging

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

    def update_coil(self, coil_id: int, freq: float, duty: float, phase: float, duration: int, start: bool = True):
        """
        Belirli bir bobinin durumunu günceller ve STM32'ye yeni komut paketini fırlatır.
        """
        if coil_id < 1 or coil_id > 5:
            self.logger.warning(f"Geçersiz bobin ID: {coil_id}")
            return False

        if start:
            self.coils_state[coil_id]["is_running"] = True
            self.coils_state[coil_id]["freq"] = max(1.0, min(10000.0, freq))
            self.coils_state[coil_id]["duty"] = max(0.0, min(0.49, duty / 100.0 if duty > 1.0 else duty))
            self.coils_state[coil_id]["phase"] = max(0.0, min(360.0, phase))
            self.coils_state[coil_id]["duration"] = duration
        else:
            self.coils_state[coil_id]["is_running"] = False
            self.coils_state[coil_id]["duty"] = 0.0

        self.logger.info(f"Coil {coil_id} durumu güncellendi: Start={start}, Freq={freq}, Duty={duty}, Phase={phase}, Dur={duration}")
        self._send_stm_manual_update()
        return True

    def start_all_coils(self, freq=100.0, duty=25.0, phase=0.0, duration=30):
        for i in range(1, 6):
            self.coils_state[i]["is_running"] = True
            self.coils_state[i]["freq"] = freq
            self.coils_state[i]["duty"] = duty / 100.0
            self.coils_state[i]["phase"] = phase
            self.coils_state[i]["duration"] = duration
            
        self.logger.info(f"Tüm bobinler (1-5) başlatıldı. Freq={freq}, Duty={duty}")
        self._send_stm_manual_update()
        return True

    def stop_all_coils(self):
        for i in range(1, 6):
            self.coils_state[i]["is_running"] = False
            self.coils_state[i]["duty"] = 0.0
            
        self.logger.info("Tüm bobinler (1-5) durduruldu.")
        self._send_stm_manual_update()
        return True

    def _send_stm_manual_update(self):
        """
        Tüm bobinlerin güncel statüsünü okur, ST[...]EN formatına paketler
        ve HeadlessCore.hw_send_queue kuyruğuna koyar.
        """
        if not self.core or not hasattr(self.core, '_hw_send_queue'):
            self.logger.warning("HeadlessCore referansı veya '_hw_send_queue' bulunamadı!")
            return

        stm32_duties = []
        stm32_phases = []
        stm32_freqs = []
        stm32_durs = []
        
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

        ref_ms = int(time.monotonic() * 1000) % 10

        # STM32 mesajı: ST[d0..4][p0..4][f0..4][dur0..4][ref]EN
        stm_msg = (
            f"ST[{stm32_duties[0]:.2f},{stm32_duties[1]:.2f},"
            f"{stm32_duties[2]:.2f},{stm32_duties[3]:.2f},{stm32_duties[4]:.2f}]"
            f"[{stm32_phases[0]:.1f},{stm32_phases[1]:.1f},"
            f"{stm32_phases[2]:.1f},{stm32_phases[3]:.1f},{stm32_phases[4]:.1f}]"
            f"[{stm32_freqs[0]:.1f},{stm32_freqs[1]:.1f},"
            f"{stm32_freqs[2]:.1f},{stm32_freqs[3]:.1f},{stm32_freqs[4]:.1f}]"
            f"[{stm32_durs[0]},{stm32_durs[1]},{stm32_durs[2]},{stm32_durs[3]},{stm32_durs[4]}]"
            f"[{ref_ms}]EN"
        )
        
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
