from abc import ABC, abstractmethod

class BaseTreatmentStrategy(ABC):
    """Tedavi modları (Manuel, Otonom vb.) için ortak State Machine (Strategy) arayüzü."""
    
    @abstractmethod
    def on_tick(self, window):
        """Her 1 saniyede (1Hz) QTimer tarafından çağrılır."""
        pass

class ManualModeStrategy(BaseTreatmentStrategy):
    """Klasik manuel kullanım modu. Kullanıcının belirlediği süreyi (countdown) yönetir."""
    
    def on_tick(self, window):
        # 1. State Manager üzerinden anlık (lock-free) durumları al
        # QTimer UI thread'de çalıştığı için Python'ın dict erişimi GIL sayesinde güvenlidir.
        states = window.state_manager._states
        
        for coil_id in range(1, 9):
            state = states[coil_id]
            
            # Sadece çalışan bobinler için geri sayım yap
            if state.running or state.pwm_active:
                
                # 2. Geri Sayım (Countdown) Kontrolü
                if state.remaining_sec is not None and state.remaining_sec > 0:
                    state.remaining_sec -= 1
                    
                    # Değişimi arayüze anında yansıtmak için sinyali manuel ateşliyoruz
                    window.state_manager.coil_state_updated.emit(coil_id, state)
                    
                    # 3. Süre dolduysa bobini durdur
                    if state.remaining_sec <= 0:
                        window.logger.info(f"Bobin {coil_id} süresi doldu, durduruluyor.")
                        
                        # UI'daki mevcut güvenli durdurma metodunu çağırıyoruz
                        if hasattr(window, 'stop_coil'):
                            window.stop_coil(coil_id)
                        
                        # Durduktan sonra UI'ı tekrar güncelle
                        state.running = False
                        state.pwm_active = False
                        window.state_manager.coil_state_updated.emit(coil_id, state)

class AutonomousModeStrategy(BaseTreatmentStrategy):
    """
    Kamera (Yapay Zeka) tarafından dinamik yönetilen tedavi modu.
    Eli (veya hedefi) takip eder, DTO'yu günceller ve donanıma komut yollar.
    """
    
    def on_tick(self, window):
        # Otonom modda periyodik kontroller (örneğin güvenlik, zaman sınırı)
        # Eğer yapay zeka belirli bir süre sinyal göndermezse sistemi durdurmak için 
        # buraya watchdog mantığı eklenebilir.
        pass

    def process_ai_prediction(self, window, x, y, z, duties, phases, e_field):
        """
        camera_ai_thread.py'den prediction_ready sinyali geldiğinde tetiklenir.
        SADECE sistem 'Otonom Mod'da ise veya 'AI Tracking' aktifse işlenmelidir.
        """
        # 1. UI Güncellemeleri (God Object yerine Strategy üzerinden güvenli erişim)
        window.lbl_x.setText(f"X: {x:.1f} mm")
        window.lbl_y.setText(f"Y: {y:.1f} mm")
        window.lbl_z.setText(f"Z: {z:.1f} mm")
        window.lbl_e_field.setText(f"Anlık E-Alan: {e_field:.2f} V/m")
        
        # 2. Gelen yapay zeka kararını State Manager (DTO) içine kaydet
        states = window.state_manager._states
        num_coils = min(8, len(duties), len(phases))
        
        for i in range(num_coils):
            coil_id = i + 1
            
            # AI'dan gelen duty 0.0 - 0.49 aralığında. Yüzdeye çevir (%0 - %50)
            duty_val = duties[i] * 100.0
            if duty_val < 0.1: duty_val = 0.0
            if duty_val > 50.0: duty_val = 50.0
                
            phase_val = phases[i]
            
            # UI Label güncellemeleri
            if getattr(window, 'ai_pro_result_labels', None) and coil_id in window.ai_pro_result_labels:
                window.ai_pro_result_labels[coil_id]['d'].setText(f"{duty_val:.1f} %")
                window.ai_pro_result_labels[coil_id]['p'].setText(f"{phase_val:.1f} °")
            
            # DTO'yu güncelle
            state = states[coil_id]
            state.duty = duty_val
            state.phase = phase_val
            # Arayüze bu bobinin güncellendiğini haber ver
            window.state_manager.coil_state_updated.emit(coil_id, state)

        # 3. Eğer AI takibi / Otonom Mod açıksa donanıma gönder
        if getattr(window, 'ai_pro_tracking_active', False):
            # Otonom mod aktifken bobin komutlarını ESP32/STM32'ye iletiyoruz.
            if hasattr(window, '_send_stm_manual_update'):
                window._send_stm_manual_update()
            elif hasattr(window, '_send_udp_live_update'):
                window._send_udp_live_update(duties, phases)
