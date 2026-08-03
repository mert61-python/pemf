import logging
import queue
import struct
import threading
import time
import zlib

from utils.stm32_protocol_limits import (
    DURATION_MAX_MINUTES,
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

    # DENETIM P2 (marj): keep-alive 1 Hz iken firmware'in 1500 ms "Olu Adam" watchdog'una
    # yalnizca ~500 ms pay kaliyordu. Windows'ta tek bir GC duraklamasi, agir AI cikarimi,
    # yogun log yazimi ya da DUSEN tek bir seri paket bu payi yiyip firmware'in TUM bobinleri
    # sifirlamasina yol acabiliyordu — tedavi ortasinda gereksiz kesinti (fail-safe yonde ama
    # klinik olarak kotu). 2 Hz'e cikarildi → pay ~1000 ms ve tek paket kaybi tolere edilir.
    # Maliyet ihmal edilebilir: 88 baytlik paket, 2 Hz = ~176 B/s (115200 baud hattinda %0.2).
    # _tick ayrica bobin-basi sure-deadline'ini kontrol ettiginden, deadline uygulamasi da
    # iki kat hassaslasir.
    KEEP_ALIVE_INTERVAL_S = 0.5
    # Dusen STOP telafisi TICK cinsindendir → kadans degisirse WALL-CLOCK kapsama
    # sabit kalsin diye sureden turetilir (~3 sn, eski 3 tick x 1.0 sn ile ayni).
    STOP_RESEND_TICKS = 6
    _FIRMWARE_DEADMAN_MS = 1500   # firmware/main.c ile AYNI olmali (bkz. main.c watchdog blogu)

    def _keep_alive_loop(self):
        while not self._keep_alive_stop.is_set():
            try:
                self._tick()
            except Exception:
                self.logger.exception("keep-alive tick hatasi")
            time.sleep(self.KEEP_ALIVE_INTERVAL_S)

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
                self._force_send_left = self.STOP_RESEND_TICKS
                self.logger.info("Bobin(ler) %s sure limiti doldu → donanim-tarafi otomatik durduruldu.", expired)

            any_running = any(self.coils_state[i]["is_running"] for i in range(1, 6))
            need_send = any_running or self._force_send_left > 0
            if self._force_send_left > 0:
                self._force_send_left -= 1
            if need_send:
                self._send_stm_manual_update()

    def stop(self):
        self._keep_alive_stop.set()

    def update_coil(self, coil_id: int, freq: float, duty: float, phase: float, duration: int,
                    start: bool = True, duration_seconds: float | None = None):
        """
        Belirli bir bobinin durumunu günceller ve STM32'ye yeni komut paketini fırlatır.
        duration birimi STM32 firmware ile uyumlu olarak dakikadır.
        """
        if coil_id < 1 or coil_id > 5:
            self.logger.warning(f"Geçersiz bobin ID: {coil_id}")
            return False

        # DENETIM P2 (kismi uygulama): normalize_* cagrilari ESKIDEN state'e YAZARKEN
        # calisiyordu. Biri istisna firlatirsa (ornegin duty_percent_to_ratio icindeki
        # float(percent) sayisal-olmayan girdide ValueError verir; clamp_float'un try'i
        # DISINDA kalir) bobin YARIM guncellenmis kaliyordu: is_running=True + YENI freq,
        # ama ESKI duty/faz ve deadline YOK. Keep-alive bu karma durumu surmeye devam
        # ederken API 'basarisiz' donuyordu — operator komutun uygulanmadigini saniyor.
        # Cozum: TUM degerleri state'e DOKUNMADAN once hesapla; biri patlarsa hicbir sey
        # degismez ve cagirana durustce hata gider (bobin eski, tutarli durumunda kalir).
        if start:
            try:
                _dur_min = normalize_duration_minutes(duration)
                _freq = normalize_frequency_hz(freq)
                # duty birimi her zaman yüzde kabul edilir; ust limit firmware/timer tarafinda saturate olur.
                _duty = duty_percent_to_ratio(duty)
                _phase = normalize_phase_deg(phase)
            except Exception:
                self.logger.exception(
                    "Coil %s parametre normalizasyonu basarisiz (freq=%r duty=%r phase=%r dur=%r) "
                    "→ bobin durumu DEGISTIRILMEDI.", coil_id, freq, duty, phase, duration)
                return False

        with self._state_lock:
            if start:
                dur_min = _dur_min
                self.coils_state[coil_id]["is_running"] = True
                self.coils_state[coil_id]["freq"] = _freq
                self.coils_state[coil_id]["duty"] = _duty
                self.coils_state[coil_id]["phase"] = _phase
                self.coils_state[coil_id]["duration"] = dur_min
                # Audit P2: dur_min<=0'da deadline=None → keep-alive firmware timer'ini SINIRSIZ tazeler
                # + _active_session yoksa sure-watchdog da yok → KAPAKSIZ enerjileme. Sinirsiz birakmak
                # yerine DURATION_MAX_MINUTES ust-kapak (geriye-uyumlu; keep-alive'a ragmen eninde durur).
                _dl_min = dur_min if dur_min > 0 else DURATION_MAX_MINUTES
                # DENETIM P3 (fazla-tedavi): STM firmware suresi DAKIKA granulerliginde oldugundan
                # saniye→dakika donusumu YUKARI yuvarlanir (30 sn → 1 dk). Firmware icin bu dogru
                # (tedaviyi yarida kesmez), ama YAZILIM deadline'i monotonik SANIYE tutar → gercek
                # sureyi tam uygulayabilir. Cagiran hassas saniyeyi verirse onu kullan; vermezse
                # eski davranis (dakika x 60). Boylece 30 sn'lik komut 30 sn surer, 60 sn degil;
                # firmware yine 1 dk'lik yedek kapak olarak kalir.
                if duration_seconds and duration_seconds > 0:
                    _dl_secs = min(float(duration_seconds), DURATION_MAX_MINUTES * 60.0)
                else:
                    _dl_secs = _dl_min * 60
                self._coil_deadline[coil_id] = time.monotonic() + _dl_secs
            else:
                self.coils_state[coil_id]["is_running"] = False
                self.coils_state[coil_id]["duty"] = 0.0
                self._coil_deadline[coil_id] = None
                self._force_send_left = self.STOP_RESEND_TICKS  # dusen STOP'u telafi et

            self.logger.info(f"Coil {coil_id} durumu güncellendi: Start={start}, Freq={freq}, Duty={duty}, Phase={phase}, Dur={duration}")
            self._send_stm_manual_update()
        return True

    def start_all_coils(self, freq=100.0, duty=25.0, phase=0.0, duration=30):
        """Tüm STM bobinlerini başlatır. duration birimi dakikadır."""
        with self._state_lock:
            dur_min = normalize_duration_minutes(duration)
            # Audit P2: dur_min<=0'da kapaksiz kalmasin → DURATION_MAX_MINUTES ust-kapak (bkz. update_coil).
            _dl_min = dur_min if dur_min > 0 else DURATION_MAX_MINUTES
            deadline = time.monotonic() + _dl_min * 60
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
            self._force_send_left = self.STOP_RESEND_TICKS  # dusen STOP'u telafi et

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

        # DENETIM P3: kuyruk dolu iken EN ESKI paket atilip yenisi konuyordu, ama ikinci
        # put_nowait icin queue.Full YAKALANMIYORDU (yalniz queue.Empty). Es-zamanli bir
        # tuketici/uretici (STM_NACK retry) araya girip kuyrugu yeniden doldurursa istisna
        # cagirana SIZAR: _stop_session_coils dongusu ORTASINDA kesilir → kalan bobinlere STOP
        # hic gonderilmez. Guvenlik yolunda (STOP) istisna sizmasi kabul edilemez.
        # Yeni davranis: kisa bir yeniden-deneme, sonra SESSIZ-DEGIL kayip (keep-alive/
        # _force_send_left zaten sonraki tur telafi eder — bkz. STOP_RESEND_TICKS).
        _pkt = (stm_msg, udp_pkt, ESP32_IP, ESP32_PORT)
        for _attempt in range(3):
            try:
                self.core._hw_send_queue.put_nowait(_pkt)
                return
            except queue.Full:
                try:
                    self.core._hw_send_queue.get_nowait()   # en eskiyi at, yer ac
                except queue.Empty:
                    pass
        self.logger.warning(
            "HW kuyrugu dolu — paket kuyruga alinamadi (keep-alive sonraki turda tazeleyecek).")
