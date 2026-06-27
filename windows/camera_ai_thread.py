import os

import time
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

# cv2, mediapipe, onnxruntime, joblib paketleri opsiyoneldir.
# LattePanda'da kurulu olmayabilir — run() içinde lazy import yapıyoruz.
# Top-level import crash'ini önlemek için burada import etmiyoruz.


class CameraAIThread(QThread):
    frame_ready = pyqtSignal(QImage)
    prediction_ready = pyqtSignal(float, float, float, list, list, float)  # x, y, z, duties, phases, e_field
    error_occurred = pyqtSignal(str)

    def __init__(self, base_path):
        super().__init__()
        self.base_path = base_path  # ai_hub/em_kedi/ dizinine işaret eder
        self._running = True
        self.is_calibrated = False
        self.ref_palm_width_pixels = None
        self.Z_SENSITIVITY = 1000
        self.trigger_calibration = False
        self.current_organ_id = 0  # Default organ ID

        # Extra AI parameters (em_kedi / BiLSTM_XXL_Raw modeli)
        self.achieved_B_target = 0.001  # Kedi modeli B alanını Tesla cinsinden (1 mT = 0.001 T) bekler
        self.duty_sum_target = 1.5    # Default 1.5 ratio sum

    def set_organ_id(self, organ_id):
        self.current_organ_id = organ_id

    def calibrate(self):
        self.trigger_calibration = True

    def run(self):
        try:
            # Lazy import — bu paketler LattePanda'da olmayabilir.
            # Import hatası olursa kullanıcıya anlaşılır bir hata mesajı göster.
            try:
                import cv2
                import mediapipe as mp
            except ImportError as ie:
                self.error_occurred.emit(
                    f"Kamera AI paketi eksik: {ie}\n"
                    f"Lütfen: pip install opencv-python mediapipe"
                )
                return

            # KediPredictor sınıfını ai_hub/em_kedi/ üzerinden import et
            import sys
            ai_hub_em_kedi = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ai_hub', 'em_kedi')
            if ai_hub_em_kedi not in sys.path:
                sys.path.insert(0, os.path.dirname(ai_hub_em_kedi))  # ai_hub/ dizinini ekle

            try:
                from ai_hub.em_kedi.inference_em_kedi import KediPredictor
            except ImportError:
                # Fallback: doğrudan dosya yolu üzerinden
                sys.path.insert(0, ai_hub_em_kedi)
                from inference_em_kedi import KediPredictor

            try:
                predictor = KediPredictor(
                    scaler_x=os.path.join(self.base_path, 'scaler_X.pkl'),
                    scaler_extra=os.path.join(self.base_path, 'scaler_extra.pkl'),
                    scaler_y=os.path.join(self.base_path, 'scaler_y.pkl'),
                    providers=["CPUExecutionProvider"],
                )
            except Exception as e:
                self.error_occurred.emit(
                    f"BiLSTM_XXL_Raw modeli yüklenemedi: {e}\n"
                    f"Model yolu: {self.base_path}"
                )
                return

            # ── MediaPipe el takibi ───────────────────────────────────────────
            mp_hands = None
            hands = None
            mp_draw = None

            # mediapipe versiyon uyumluluğu:
            # - Eski API (< 0.10): mp.solutions.hands
            # - Yeni API (>= 0.10): tasks API
            try:
                mp_hands = mp.solutions.hands
                hands = mp_hands.Hands(
                    max_num_hands=1,
                    min_detection_confidence=0.7,
                    min_tracking_confidence=0.7
                )
                mp_draw = mp.solutions.drawing_utils
            except AttributeError as ae:
                self.error_occurred.emit(
                    f"Mediapipe başlatma hatası: {ae}\n"
                    "Protobuf veya Mediapipe sürüm uyumsuzluğu algılandı."
                )
                return

            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                self.error_occurred.emit("Kamera bağlı değil veya açılamadı.")
                return

            last_inference_time = 0
            INFERENCE_INTERVAL = 0.1  # 10 Hz (Arayüz 20Hz bekliyor, 10Hz performans/kararlılık dengesi için idealdir)
            
            failed_frames = 0

            while self._running:
                ret, frame = cap.read()
                if not ret:
                    failed_frames += 1
                    if failed_frames > 30:  # ~1 saniye boyunca görüntü alınamazsa
                        self.error_occurred.emit("Kamera bağlantısı koptu veya görüntü okunamıyor.")
                        break
                    QThread.msleep(30)  # CPU'yu %100 kullanmasını engellemek için
                    continue
                else:
                    failed_frames = 0

                frame = cv2.flip(frame, 1)
                h, w, _ = frame.shape

                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = hands.process(rgb_frame)

                current_z_mm = 0
                x_mm, y_mm = 0.0, 0.0
                detected = False

                if results.multi_hand_landmarks:
                    for hand_lms in results.multi_hand_landmarks:
                        tip = hand_lms.landmark[8]
                        p5  = hand_lms.landmark[5]
                        p17 = hand_lms.landmark[17]

                        p5_pix  = (p5.x * w,  p5.y * h)
                        p17_pix = (p17.x * w, p17.y * h)
                        current_palm_width = np.sqrt(
                            (p5_pix[0] - p17_pix[0]) ** 2 + (p5_pix[1] - p17_pix[1]) ** 2
                        )

                        if self.trigger_calibration:
                            self.ref_palm_width_pixels = current_palm_width
                            self.is_calibrated = True
                            self.trigger_calibration = False

                        if self.is_calibrated and self.ref_palm_width_pixels:
                            ratio = current_palm_width / self.ref_palm_width_pixels
                            z_raw = (1.0 - ratio) * self.Z_SENSITIVITY
                            current_z_mm = max(-300, min(300, z_raw))

                        x_mm = (tip.x * 600) - 300
                        y_mm = ((1.0 - tip.y) * 600) - 300
                        detected = True

                        # Çizimler
                        cx, cy = int(tip.x * w), int(tip.y * h)
                        cv2.circle(rgb_frame, (cx, cy), 15, (255, 0, 0), -1)
                        mp_draw.draw_landmarks(rgb_frame, hand_lms, mp_hands.HAND_CONNECTIONS)

                current_time = time.time()
                if detected and (current_time - last_inference_time >= INFERENCE_INTERVAL):
                    last_inference_time = current_time

                    try:
                        # KediPredictor.predict() → {D1..D7, P1..P7, result_E} vb.
                        result = predictor.predict(
                            x=x_mm,
                            y=y_mm,
                            z=current_z_mm,
                            organ_id=self.current_organ_id,
                            achieved_B=self.achieved_B_target,
                            duty_sum=self.duty_sum_target,
                        )

                        # [FIX] 8 Bobin desteği ve eksik veriler için `.get` kullanarak Production-Ready okuma
                        # AI Pro policy: model output is a duty ratio and may reach 0.50.
                        # Do not apply the legacy 0.49 clamp; Unified sends the same 50% to STM.
                        D_vals = np.clip(
                            [result.get(f"D{i}", 0.0) for i in range(1, 9)], 0.0, 0.50
                        )
                        P_vals = [result.get(f"P{i}", 0.0) for i in range(1, 9)]
                        E_val  = float(max(0.0, result.get("result_E", 0.0)))

                        self.prediction_ready.emit(
                            x_mm, y_mm, current_z_mm,
                            D_vals.tolist(), P_vals, E_val
                        )
                    except Exception as pred_err:
                        self.error_occurred.emit(f"Tahmin hatası: {pred_err}")

                # QImage oluştur ve UI'a yolla
                bytes_per_line = 3 * w
                q_img = QImage(
                    rgb_frame.data, w, h, bytes_per_line,
                    QImage.Format.Format_RGB888
                ).copy()
                self.frame_ready.emit(q_img)

                # Not: cap.read() zaten yeni frame gelene kadar (örn. 30 FPS için 33ms) bloklar.
                # QThread.msleep(30) eklemek frame hızını yarı yarıya düşürür. Bunu küçük bir değere çektik.
                QThread.msleep(5)

        except Exception as e:
            self.error_occurred.emit(f"Kamera hatası: {str(e)}")
        finally:
            if 'hands' in locals() and hands is not None:
                try:
                    hands.close()
                except Exception:
                    pass
            if 'cap' in locals() and cap.isOpened():
                cap.release()

    def stop(self):
        self._running = False
        if not self.wait(5000):
            import logging
            logging.getLogger(__name__).warning("CameraAIThread graceful kapatılamadı, kaynak kilitlenmesini engellemek için terminate atlanıyor.")
