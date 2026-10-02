# Author: mertaygn, cglrgrkn
import logging
import queue
import struct
import threading
import time
import zlib

from utils import estop_mandali
from utils.dongu_guvenligi import dongu_hatasini_bildir
from utils.stm32_protocol_limits import (
    DURATION_MAX_MINUTES,
    duty_percent_to_ratio,
    normalize_duration_minutes,
    normalize_frequency_hz,
    normalize_phase_deg,
)
from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI, STM_PAKET_FMT

#: STM'in SÜRDÜĞÜ bobin sayısı (faz 4, sahip kararı 2026-09-10: bobin 6-7 ESP'den taşındı).
#: ⚠️ Bu, PAKET genişliği (`STM_PAKET_BOBIN_SAYISI`) ile AYNI OLMAK ZORUNDA DEĞİL — protokol
#: daha geniş olabilir ve fazla alanlar sıfır gider. Ama topolojiden BÜYÜK olamaz: olursa
#: `_send_stm_manual_update` var olmayan bir `coils_state` girdisi arar.
#: Kaynak sözleşmesi: `servers.live_state.STM_COIL_IDS` ile aynı kapsam.
#: Kapı: tests/test_bobin_topolojisi.py
STM_BOBIN_SAYISI = 7

#: Süre VERİLMEDEN başlatılan bir bobinin yazılım deadline'ı (dakika).
#
# ⚠️ NEDEN AYRI BİR SABİT (kampanya bulgusu S03, 2026-08-14): burada eskiden
# `DURATION_MAX_MINUTES` (9999) kullanılıyordu. O değer bir KLİNİK sınır değil, **STM32 firmware
# protokol sınırıdır** (`utils/stm32_protocol_limits`; `test_stm32_source_parity` onu firmware
# kaynağıyla birebir eşler). Üst-kapak olarak kullanılınca `duration=0` ile başlatılan bobin
# ölçülen ~6,9 GÜN boyunca enerjili kalabiliyordu — pratikte kapaksız. "Protokol maksimumu" ile
# "güvenli gözetimsiz varsayılan" farklı şeylerdir; protokol sabiti DEĞİŞTİRİLMEZ (parite).
#
# Değer, ürünün KENDİ emsalinden alındı: `ai_router._AI_PRO_MAX_DURATION_MIN = 120` — gerekçesi
# aynı ("günlerce/gözetimsiz PEMF sürüşünü engeller"). Böylece otonom ve elle sürüş yolları aynı
# klinik sınırı paylaşır.
#
# ⚠️ freq/duty/48°C safety-limit'leriyle İLGİSİ YOKTUR; onlar sahip kararıyla kaldırıldı ve
# GERİ EKLENMEZ. Buradaki sınır yalnız SÜREdir.
GOZETIMSIZ_VARSAYILAN_DAKIKA = 120


class ParametreGecersiz(ValueError):
    """START parametresi donanım paketine çevrilemiyor (sayı değil / float32'ye sığmıyor / süre taşıyor).

    D1.95 (B-1.13 · B-1.16): API uçları bunu 422'ye çevirir; `HardwareController` reddeder ve durum DEĞİŞMEZ.
    Metin HAM GİRDİYİ taşımaz (422 zarfında ham değer dönmesin — B-10.148)."""


def surus_parametrelerini_hazirla(freq, duty, phase, duration, duration_seconds=None) -> dict:
    """START parametrelerini donanıma GİDECEK değerlere çevirir — DURUM YAZILMADAN ÖNCE (D1.95 · B-1.13/B-1.16).

    ⚠️ NEDEN: süre (`float(duration_seconds)`) ve paket dönüşümü (`struct.pack`) eskiden durum YAZILDIKTAN SONRA
    yapılıyordu. 310 haneli süre `is_running=True` yazıp deadline'ı None bırakıyordu (keep-alive bobini SÜRESİZ
    enerjili tutar, API 500); duty ≥ 3,4e40 (%) durumu yazıp sonraki HER paketi — STOP ve keep-alive dahil —
    `OverflowError` ile düşürüyordu (hayalet 'completed' seans). Duty ÜST sınırı EKLENMEZ (Ö.4-Y9, Y20): yalnız
    paketin `f` (float32) alanına SIĞMAYAN değer reddedilir; protokol `normalize_*` sınırları aynen uygulanır.

    @return {"freq": Hz, "duty": oran, "duty_yuzde": %, "faz": derece, "sure_dk": dk, "son_tarih_s": sn}
    @raises ParametreGecersiz"""
    try:
        sure_dk = normalize_duration_minutes(duration)
        f = normalize_frequency_hz(freq)
        d = duty_percent_to_ratio(duty)
        faz = normalize_phase_deg(phase)
        struct.pack("<fff", d, faz, f)  # paketin float32 alanlarına SIĞIYOR mu (OverflowError)
        if duration_seconds and duration_seconds > 0:
            son_tarih_s = min(float(duration_seconds), DURATION_MAX_MINUTES * 60.0)
        else:
            son_tarih_s = float((sure_dk if sure_dk > 0 else GOZETIMSIZ_VARSAYILAN_DAKIKA) * 60)
    except (TypeError, ValueError, OverflowError, struct.error) as exc:
        raise ParametreGecersiz(
            f"Sürüş parametresi donanım paketine çevrilemiyor ({type(exc).__name__}: sayı değil ya da taşıyor)."
        ) from exc
    return {
        "freq": f,
        "duty": d,
        "duty_yuzde": d * 100.0,
        "faz": faz,
        "sure_dk": sure_dk,
        "son_tarih_s": son_tarih_s,
    }


def sifir_hz_durdurma_mi(freq) -> bool:
    """A-05 (sahip kararı): 0 Hz BAŞLATMA = o bobin için STOP — arayüzün "bobini parkla" niyeti (D1.53 · B-1.10).

    YALNIZ tam sıfır. Sıfır olmayan her değer (negatif ve 0 < f < 1 dahil) protokol sınırına gider
    (`normalize_frequency_hz` / `normalize_esp_frequency_hz`, 1 Hz tabanı — Ö.4-Y9 TAŞIYICI, KALDIRILMAZ).
    Eskiden 0 Hz o sınırda sessizce 1 Hz'e çekilip istenen duty ile SÜRÜLÜYORDU: operatör bobini parkladığını
    sanırken bobin enerjili, kayıt "0 Hz". Okunamayan değer (None, metin) durdurma SAYILMAZ (eski yol)."""
    try:
        return float(freq) == 0.0
    except (TypeError, ValueError):
        return False


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
            i: {"is_running": False, "duty": 0.0, "phase": 0.0, "freq": 100.0, "duration": 0}
            for i in range(1, STM_BOBIN_SAYISI + 1)
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
        self._coil_deadline = {i: None for i in range(1, STM_BOBIN_SAYISI + 1)}

        # P0 fix: STOP garanti-teslim. Tek STOP paketi seri yazma hatasinda dusserse keep-alive
        # normalde tazelemezdi (any_running False). Durdurma sonrasi paketi birkac dongu tekrar
        # gonderir → dusen STOP telafi edilir.
        self._force_send_left = 0

        # ── SÜRÜŞ KİPİ (sahip kararı 2026-09-11: arayüzde düğmeyle ayarlanır) ──────────
        # Bit i set → bobin i+1 UNIPOLAR sürülsün. Varsayılan 0 = "hepsi bipolar İSTE".
        # ⚠️ Bu bir İSTEKTİR. Firmware onu DONANIM YETENEĞİYLE OR'lar
        # (`PEMF_BOBIN_UNIPOLAR_MASKESI` = 0x60) → bobin 6-7 sürücüsü tek yönlü olduğu
        # için onlar HER HÂLÜKÂRDA unipolar kalır. Backend bunu taklit ETMEZ: tek doğru
        # yer firmware'dir, burada da kopyalarsak iki kaynak sessizce ayrışır.
        # Gerçekte ne uygulandığı ACK satırındaki `K=` alanından okunur.
        self._unipolar_maskesi = 0

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
    _FIRMWARE_DEADMAN_MS = 1500  # firmware/stm32_pemf/Core/Src/main.c ile AYNI olmali (bkz. main.c watchdog blogu)

    def _keep_alive_loop(self):
        while not self._keep_alive_stop.is_set():
            try:
                self._tick()
            except Exception:
                # D1.19 (B-10.121): bildirim fırlatırsa keep-alive + bobin-başı süre sınırı iş parçacığı
                # cihaz yeniden başlayana dek ölürdü (firmware ölü-adam 1,5 sn'de keser — güvenli yön).
                dongu_hatasini_bildir("keep-alive tick hatasi", logger=self.logger)
            time.sleep(self.KEEP_ALIVE_INTERVAL_S)

    def _tick(self):
        """Her saniye: (1) sure-limiti dolan bobinleri donanim-tarafi otomatik durdur,
        (2) calisan bobinler icin keep-alive paketi + STOP-sonrasi birkac tazeleme gonder."""
        with self._state_lock:
            now = time.monotonic()
            expired = [
                i
                for i in range(1, STM_BOBIN_SAYISI + 1)
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

            any_running = any(self.coils_state[i]["is_running"] for i in range(1, STM_BOBIN_SAYISI + 1))
            need_send = any_running or self._force_send_left > 0
            if self._force_send_left > 0:
                self._force_send_left -= 1
            if need_send:
                self._send_stm_manual_update()

    def stop(self):
        self._keep_alive_stop.set()

    def surus_kipi_ayarla(self, unipolar_maskesi: int) -> int:
        """Sürüş kipi İSTEĞİNİ ayarlar (bit i set = bobin i+1 unipolar). @return uygulanan istek.

        ⚠️ ANINDA ETKİLİ DEĞİL — bir sonraki pakette gider. Hiçbir bobin çalışmıyorsa
        keep-alive paket GÖNDERMEZ (`need_send = any_running or ...`), yani kip değişimi
        bobin başlayana kadar karta ULAŞMAZ. Bu kasıtlı: boşta UART'ı meşgul etmiyoruz ve
        kip yalnız sürüş anında anlam taşıyor. Operatöre "kaydedildi" demek için yeterli.

        ⚠️ Maske YETENEĞİ KALDIRAMAZ: firmware `yetenek || istek` uygular. Bobin 6-7'ye
        bipolar istemek SESSİZCE yok sayılmaz — ACK'teki `K=` alanı gerçek kipi gösterir.
        """
        try:
            m = int(unipolar_maskesi) & 0xFF
        except (TypeError, ValueError):
            self.logger.warning("Gecersiz surus kipi maskesi: %r — DEGISTIRILMEDI", unipolar_maskesi)
            return int(self._unipolar_maskesi)
        with self._state_lock:
            self._unipolar_maskesi = m
            calisan = any(self.coils_state[i]["is_running"] for i in range(1, STM_BOBIN_SAYISI + 1))
            if calisan:
                # Çalışan bobin varsa kipi HEMEN tazele (sonraki keep-alive turunu bekleme).
                self._force_send_left = self.STOP_RESEND_TICKS
                self._send_stm_manual_update()
        self.logger.info("Surus kipi istegi: maske=0x%02X (calisan bobin: %s)", m, calisan)
        return m

    def _stm_surus_hazir(self) -> bool:
        """STM kopukken BAŞLATMA reddedilsin mi? (True = sürülebilir)

        ⚠️ SAHA 2026-09-11: STM kopukken (`stmConnected: false`, hiç COM portu yok)
        `/api/coil/1/control` `{"status":"success"}` dönüyordu. Donanım yokken "başarılı"
        demek, operatöre tedavinin uygulandığını sandırır — SESSİZ BAŞARISIZLIK.

        ⚠️ FAIL-OPEN BİLİNÇLİ: durum okunamazsa `True` döner, yani ENGELLEMEZ. Kapının
        amacı sahte başarıyı kesmek; kendi arızasıyla cihazı kilitlemek DEĞİL. Kopuk
        bağlantıda zaten iki katman daha var: firmware'in 1500 ms ölü-adam devresi
        bobinleri sıfırlar ve arayüz kontrolü kilitler.

        ⚠️ Gecikmeli (lazy) import: bu modülün import grafiğini `servers` katmanına
        bağlamamak için. `live_state` yalnız stdlib+fastapi+utils kullanır → döngü yok.
        """
        return not self._stm_baslatma_engeli()

    def _stm_baslatma_engeli(self) -> str:
        """START'ı engelleyen STM durumu; "" = engel yok. ⚠️ STOP / E-stop bu kapıdan HİÇ geçmez (Ö.4-Y8).

        Üç engel (her biri fail-open: durum okunamazsa ENGELLEMEZ — bkz. `_stm_surus_hazir`):
          1. STM bağlı değil (canlı durum, arayüzün gördüğü alan).
          2. D1.52 (B-1.4): firmware KESİN uyumsuz (`core.stm_uyumlu is False`; `None` = banner tanınmadı,
             ENGELLEMEZ). Eskiden yalnız `/api/session/start` bakıyordu; tekil/batch/`hardware/command`/AI (Auto)
             200 "success" dönüp koşu kaydı açıyordu — kart paketi reddederken.
          3. D1.52: kart komutları SİSTEMATİK reddediyor (`stm_komutlari_reddediyor`, NACK kapısı)."""
        try:
            from servers.live_state import stm_komutlari_reddediyor, stm_surus_hazir
        except Exception:
            self.logger.debug("STM surus durumu okunamadi → baslatma ENGELLENMEDI", exc_info=True)
            return ""
        try:
            if not stm_surus_hazir():
                return "STM32 bağlı değil. USB (ST-Link) kablosunu takın; bağlantı gelince komutu yeniden verin."
        except Exception:
            self.logger.debug("STM baglanti durumu okunamadi → baslatma ENGELLENMEDI", exc_info=True)
        core = getattr(self, "core", None)
        if getattr(core, "stm_uyumlu", None) is False:
            sebep = getattr(core, "stm_uyumsuzluk_sebebi", "") or "kanal sayısı paket genişliğiyle uyuşmuyor"
            return f"STM32 firmware'i bu sürümle UYUMSUZ ({sebep}). Kartı güncel firmware ile yeniden programlayın."
        try:
            if stm_komutlari_reddediyor():
                return "STM32 kartı komutları sistematik olarak REDDEDİYOR (firmware/protokol uyuşmazlığı)."
        except Exception:
            self.logger.debug("STM red durumu okunamadi → baslatma ENGELLENMEDI", exc_info=True)
        return ""

    def _gonderici_baslatmaya_hazir(self) -> bool:
        """START kapısı: HWSender ŞU AN canlı mı? Ölüyse canlandırmayı DENER (sonraki STOP'lar yazılsın) ama bu START'ı
        REDDEDER (False).

        ⚠️ 1-C inceleme i5-F-3 (ölçüldü 30/30): ölü göndericiyi canlandıran START, canlandırmanın KENDİ kopuş olayıyla
        yarışıyordu — yeni çalışan bağlantıyı yeniden kurarken `on_disconnect` HC'yi "durdu"ya çeker; START durumu bundan
        ÖNCE yazmışsa "başarılı" dönüp koşu kaydı açılıyor ama keep-alive susuyordu (bobin yalnız ölü-adama dek). STM
        yeniden bağlanırken başlatma zaten anlamsızdır: operatör "gönderici yeniden başlatıldı — yeniden deneyin" görür.
        STOP yolları bu kapıdan GEÇMEZ (Ö.4-Y8): `_gonderici_canli` canlandırıp gönderimi sürdürür."""
        core = getattr(self, "core", None)
        canli = getattr(core, "hw_gonderici_canli", None)
        if not callable(canli):
            return True
        try:
            if canli():
                return True
        except Exception:
            dongu_hatasini_bildir("HWSender canlilik denetimi basarisiz → gonderici OLU sayildi", logger=self.logger)
            return False
        self._gonderici_canli()  # canlandırmayı dene (sonraki STOP'lar için); bu START yine de reddedilir
        return False

    def _gonderici_canli(self) -> bool:
        """HWSender (kuyruk → seri port) canlı mı? Ölüyse bir kez yeniden başlatmayı dener (D1.55 · B-1.23).

        ⚠️ NEDEN: gönderici ölüyken paket kuyruğa GİRER ama porta HİÇ yazılmaz. Eskiden STOP yolu bu durumda
        "kuyruğa verildi=True" dönüyor, E-stop `stmStopped` diye yayınlıyordu (porta 0 bayt).

        Çekirdek canlılık BİLDİRMİYORSA (`_hw_send_queue` taşıyan yalın test vekilleri) True — eski davranış;
        üretim çekirdeği (`HeadlessCore`) her zaman bildirir ve kapı gerçek çekirdekle ölçülür. Sorgu
        fırlatırsa False: "kuyruğa verildi" iddiası doğrulanamadı."""
        core = getattr(self, "core", None)
        canli = getattr(core, "hw_gonderici_canli", None)
        if not callable(canli):
            return True
        try:
            if canli():
                return True
            canlandir = getattr(core, "hw_gondericiyi_canlandir", None)
            if callable(canlandir) and canlandir():
                return True
        except Exception:
            dongu_hatasini_bildir("HWSender canlilik denetimi basarisiz → gonderici OLU sayildi", logger=self.logger)
            return False
        dongu_hatasini_bildir(
            "ACİL: HWSender ÖLÜ ve yeniden başlatılamadı — paketler porta YAZILMIYOR (firmware ölü-adam 1,5 sn'de keser).",
            logger=self.logger,
            exc_info=False,
        )
        return False

    def update_coil(
        self,
        coil_id: int,
        freq: float,
        duty: float,
        phase: float,
        duration: int,
        start: bool = True,
        duration_seconds: float | None = None,
        nesil: int | None = None,
    ):
        """
        Belirli bir bobinin durumunu günceller ve STM32'ye yeni komut paketini fırlatır.
        duration birimi STM32 firmware ile uyumlu olarak dakikadır.
        `nesil`: START niyetinin sürüş nesli (D1.81); verilmezse `estop_mandali.surus_baglami` bağlamındaki değer.
        """
        if coil_id < 1 or coil_id > STM_BOBIN_SAYISI:
            self.logger.warning(f"Geçersiz bobin ID: {coil_id}")
            return False

        # ⚠️ D1.53 (B-1.10 · A-05): 0 Hz BAŞLATMA = bu bobin için STOP — başlatma kapılarından ve protokol
        # sınırından ÖNCE (STOP hiçbir kapıya takılmaz, Ö.4-Y8). START YAPILMADIĞI için dönüş False: seans,
        # AI ve legacy çağıranlar bunu "başlamadı" okur ve koşu kaydı AÇMAZ. (Tekil/batch uçları arayüzün
        # "parkla" isteğini kendileri STOP olarak işler.)
        _sifir_hz_durdurma = bool(start) and sifir_hz_durdurma_mi(freq)
        if _sifir_hz_durdurma:
            self.logger.warning("Bobin %s: 0 Hz başlatma = DURDURMA (A-05) — bobin durduruluyor.", coil_id)
            start = False

        # ⚠️ STM KOPUKSA BAŞLATMA REDDEDİLİR — ama DURDURMA ASLA (bkz. `_stm_surus_hazir`).
        # `start` kontrolü ŞART: STOP/E-stop kayıtlı sahip kararıyla hiçbir koşulda
        # kapılanmaz, ayrıca kopuk bağlantıda STOP'u reddetmek yeniden bağlanınca
        # bobinlerin ESKİ duty ile canlanmasına yol açar (keep-alive eski state'i sürer).
        if start:
            _engel = self._stm_baslatma_engeli()
            if _engel:
                self.logger.warning("Bobin %s BAŞLATILMADI: %s", coil_id, _engel)
                return False
        # ⚠️ D1.55 (B-1.23): gönderici ÖLÜYKEN (ve yeniden başlatılamıyorken) BAŞLATMA da reddedilir — durum
        # yazılırsa "başarılı" denir ama komut porta gitmez (sahte başarılı seans), gönderici dönünce de
        # keep-alive bobini HABERSİZ enerjilerdi. Durdurma ASLA kapılanmaz (Ö.4-Y8).
        if start and not self._gonderici_baslatmaya_hazir():
            self.logger.warning("Bobin %s BAŞLATILMADI: donanım gönderici iş parçacığı çalışmıyor.", coil_id)
            return False

        # DENETIM P2 (kismi uygulama): normalize_* cagrilari ESKIDEN state'e YAZARKEN
        # calisiyordu. Biri istisna firlatirsa (ornegin duty_percent_to_ratio icindeki
        # float(percent) sayisal-olmayan girdide ValueError verir; clamp_float'un try'i
        # DISINDA kalir) bobin YARIM guncellenmis kaliyordu: is_running=True + YENI freq,
        # ama ESKI duty/faz ve deadline YOK. Keep-alive bu karma durumu surmeye devam
        # ederken API 'basarisiz' donuyordu — operator komutun uygulanmadigini saniyor.
        # Cozum: TUM degerleri state'e DOKUNMADAN once hesapla; biri patlarsa hicbir sey
        # degismez ve cagirana durustce hata gider (bobin eski, tutarli durumunda kalir).
        # D1.95 (B-1.13 · B-1.16): süre ve paket dönüşümleri de (float(), struct.pack) BURADA, durumdan ÖNCE.
        if start:
            try:
                _p = surus_parametrelerini_hazirla(freq, duty, phase, duration, duration_seconds)
            except ParametreGecersiz:
                self.logger.exception(
                    "Coil %s parametre normalizasyonu basarisiz (freq=%.40r duty=%.40r phase=%.40r dur=%.40r "
                    "dur_s=%.40r) → bobin durumu DEGISTIRILMEDI.",
                    coil_id,
                    freq,
                    duty,
                    phase,
                    duration,
                    duration_seconds,
                )
                return False

        with self._state_lock:
            if start:
                # ⚠️ D1.81 (B-5.3 · Y4): ACİL DURDURMA MANDALI ve SÜRÜŞ NESLİ — DURUM KİLİDİ ALTINDA, durum yazımıyla
                # aynı kritik bölgede. Kilidin dışında denetlemek (ya da çağıranda "tahmin sonrası seans hâlâ aktif mi"
                # bakmak) denetle-sonra-yap aralığı bırakır: o aralıkta gelen E-stop STOP'unu gönderir, ardından bu START
                # bobini YENİDEN enerjilerdi (İG-5.3/5.4). Burada ya E-stop'tan önce yazılırız (E-stop'un STOP'u bizden
                # SONRA gider) ya da sonra denetleriz (mandal/bayat nesil → red). STOP bu kapıdan geçmez (Ö.4-Y8).
                _engel = estop_mandali.baslatma_engeli(nesil if nesil is not None else estop_mandali.baglam_nesli())
                if _engel:
                    self.logger.warning("Bobin %s BAŞLATILMADI: %s", coil_id, _engel)
                    return False
                dur_min = _p["sure_dk"]
                self.coils_state[coil_id]["is_running"] = True
                self.coils_state[coil_id]["freq"] = _p["freq"]
                self.coils_state[coil_id]["duty"] = _p["duty"]
                self.coils_state[coil_id]["phase"] = _p["faz"]
                self.coils_state[coil_id]["duration"] = dur_min
                # Audit P2: dur_min<=0'da deadline=None → keep-alive firmware timer'ini SINIRSIZ tazeler
                # + _active_session yoksa sure-watchdog da yok → KAPAKSIZ enerjileme.
                # ⚠️ KAPAK ARTIK PROTOKOL TAVANI DEGIL (kampanya bulgusu S03, 2026-08-14):
                # DURATION_MAX_MINUTES=9999 bir KLINIK sinir degil, STM32 firmware PROTOKOL
                # sinriridir (test_stm32_source_parity onu firmware kaynagiyla esler). Ust-kapak
                # olarak kullanilinca sure verilmeyen bobin ~6,9 GUN sürebiliyordu — olculdu.
                # "Protokol maksimumu" ile "guvenli gozetimsiz varsayilan" ayri seylerdir.
                # DENETIM P3 (fazla-tedavi): STM firmware suresi DAKIKA granulerliginde oldugundan
                # saniye→dakika donusumu YUKARI yuvarlanir (30 sn → 1 dk). Firmware icin bu dogru
                # (tedaviyi yarida kesmez), ama YAZILIM deadline'i monotonik SANIYE tutar → gercek
                # sureyi tam uygulayabilir. Cagiran hassas saniyeyi verirse onu kullan; vermezse
                # eski davranis (dakika x 60; dakika <= 0 → GOZETIMSIZ_VARSAYILAN_DAKIKA). Hesap
                # `surus_parametrelerini_hazirla`da — durum yazilmadan ONCE (D1.95).
                self._coil_deadline[coil_id] = time.monotonic() + _p["son_tarih_s"]
            else:
                self.coils_state[coil_id]["is_running"] = False
                self.coils_state[coil_id]["duty"] = 0.0
                self._coil_deadline[coil_id] = None
                self._force_send_left = self.STOP_RESEND_TICKS  # dusen STOP'u telafi et

            self.logger.info(
                f"Coil {coil_id} durumu güncellendi: Start={start}, Freq={freq}, Duty={duty}, Phase={phase}, Dur={duration}"
            )
            _kuyruga_verildi = self._send_stm_manual_update()
        # DENETIM 2. TUR [1.1] tamamlamasi (adversaryal review #1, 2026-08-20): STOP donusu artik
        # `stop_all_coils` (:268-279, E-stop yolu, 2026-08-09 denetimi) ile AYNI sozlesmeyi tasir —
        # "STOP paketi donanim kuyruguna VERILDI" (fiziksel teyit degil). False ise STOP su an
        # KESINLIKLE gonderilmemistir; STOP_RESEND_TICKS sonraki keep-alive turlarinda telafi
        # etmeyi DENER ama cagiran fail-safe davranmalidir (_stop_session_coils bunu
        # `hardware_stop_unconfirmed` olarak operatore tasir). Eski hali kosulsuz True donuyordu →
        # kuyruga hic girmemis STOP "teyitli" sayiliyordu.
        # ⚠️ START yolunda donus BILEREK degismedi (True): state atomik uygulandi ve keep-alive
        # her turda tam durumu zaten tazeler; False donmek yukaridaki normalize dalinin
        # "parametre reddedildi, state DEGISMEDI" anlamiyla "gecici kuyruk dolulugu"nu
        # karistirirdi. Kilit: tests/test_session_stop_dogrulama.py (karsit-kanit dahil).
        if not start:
            # D1.53: 0 Hz isteğinde STOP gönderildi ama istenen START YAPILMADI → False.
            return False if _sifir_hz_durdurma else bool(_kuyruga_verildi)
        return True

    def start_all_coils(self, freq=100.0, duty=25.0, phase=0.0, duration=30, nesil: int | None = None):
        """Tüm STM bobinlerini başlatır. duration birimi dakikadır. `nesil`: bkz. `update_coil` (D1.81)."""
        if sifir_hz_durdurma_mi(freq):  # D1.53 (A-05): 0 Hz = TÜM bobinler için STOP; START yapılmadı → False
            self.logger.warning("TÜM bobinler: 0 Hz başlatma = DURDURMA (A-05) — bobinler durduruluyor.")
            self.stop_all_coils()
            return False
        # ⚠️ AYNI KAPI BURADA DA OLMAK ZORUNDA: bu metot `update_coil`i ÇAĞIRMAZ (aşağıdaki
        # yorumun anlattığı "BURAYA TAŞINMAMIŞTI" arızasının aynı sınıfı). Yalnız `update_coil`
        # kapatılsa seans ve AI yolları STM kopukken hâlâ sessizce "başarılı" dönerdi —
        # kısmi düzeltme, düzeltilmemiş demektir.
        _engel = self._stm_baslatma_engeli()
        if _engel:
            self.logger.warning("TÜM bobinler BAŞLATILMADI: %s", _engel)
            return False
        if not self._gonderici_baslatmaya_hazir():  # D1.55 (B-1.23) + i5-F-3 — gerekçe update_coil'de
            self.logger.warning("TÜM bobinler BAŞLATILMADI: donanım gönderici iş parçacığı çalışmıyor.")
            return False
        # DENETIM P2 (kismi uygulama) — update_coil:144-169'daki AYNI desen, gerekcesi orada.
        # Buraya TASINMAMISTI (git kaniti: 1413235 tek hunk, yalniz update_coil bolgesi).
        # normalize_* cagrilari dongu icinde, state'e YAZARKEN calisiyordu. duty TEK skalerdir
        # ve 5 bobinde paylasilir → duty_percent_to_ratio'nun float(percent)'i (clamp_float'in
        # try'i DISINDA, stm32_protocol_limits.py:45) sayisal-olmayan girdide HER ZAMAN i=1'de
        # patlar: bobin 1 is_running=True + YENI freq alir, bobin 2-5 dokunulmaz, HICBIR bobinin
        # deadline'i yazilmaz. Bobin 1 BOSTA ise _coil_deadline[1] None kalir → _tick onu ASLA
        # sure-asimina dusuremez (bkz. :103 `is not None` kosulu) → SURESIZ "calisiyor" gostergesi
        # + sonsuz keep-alive (olculdu: 50 tick → 50 paket, is_running hala True).
        # ⚠️ Bu bir freq/duty GUVENLIK-LIMITI DEGIL — onlar sahip karariyla kaldirildi ve GERI
        # EKLENMEZ (bkz. :30-31 ve stm32_protocol_limits.py:12-14). Burada YALNIZ yazma
        # ATOMIKLIGI saglanir: BASARILI cagri 5 bobini de istenen freq/duty'ye almaya devam eder.
        # D1.95 (B-1.13 · B-1.16): paket dönüşümü (float32 sığma) de durumdan ÖNCE — gerekçe `surus_parametrelerini_hazirla`.
        try:
            _p = surus_parametrelerini_hazirla(freq, duty, phase, duration)
        except ParametreGecersiz:
            self.logger.exception(
                "start_all_coils parametre normalizasyonu basarisiz (freq=%.40r duty=%.40r phase=%.40r dur=%.40r) "
                "→ HICBIR bobin durumu DEGISTIRILMEDI.",
                freq,
                duty,
                phase,
                duration,
            )
            return False

        with self._state_lock:
            # D1.81 (B-5.3 · Y4): mandal + sürüş nesli DURUM KİLİDİ ALTINDA — gerekçe `update_coil`'de (AI (Auto) bu yolu kullanır).
            _engel = estop_mandali.baslatma_engeli(nesil if nesil is not None else estop_mandali.baglam_nesli())
            if _engel:
                self.logger.warning("TÜM bobinler BAŞLATILMADI: %s", _engel)
                return False
            dur_min = _p["sure_dk"]
            # Audit P2: dur_min<=0'da kapaksiz kalmasin. ⚠️ Kapak PROTOKOL TAVANI DEGIL, klinik
            # varsayilan (bkz. GOZETIMSIZ_VARSAYILAN_DAKIKA ve update_coil'deki gerekce). TUM
            # bobinleri ayni anda surdugu icin burada kapaksizlik daha da agir sonuc dogururdu.
            deadline = time.monotonic() + _p["son_tarih_s"]
            for i in range(1, STM_BOBIN_SAYISI + 1):
                self.coils_state[i]["is_running"] = True
                self.coils_state[i]["freq"] = _p["freq"]
                self.coils_state[i]["duty"] = _p["duty"]
                self.coils_state[i]["phase"] = _p["faz"]
                self.coils_state[i]["duration"] = dur_min
                self._coil_deadline[i] = deadline

            self.logger.info(f"Tüm bobinler (1-5) başlatıldı. Freq={freq}, Duty={duty}")
            self._send_stm_manual_update()
        return True

    def stop_all_coils(self):
        with self._state_lock:
            # D1.81 (B-5.3): her TAM durdurma uçuştaki START niyetlerini geçersiz kılar (nesil++) — durum kilidi altında,
            # böylece kilide takılı bir START ya bu STOP'tan önce yazılır (STOP sonra gider) ya da bayat nesille reddedilir.
            estop_mandali.nesil_artir()
            for i in range(1, STM_BOBIN_SAYISI + 1):
                self.coils_state[i]["is_running"] = False
                self.coils_state[i]["duty"] = 0.0
                self._coil_deadline[i] = None
            self._force_send_left = self.STOP_RESEND_TICKS  # dusen STOP'u telafi et

            # ⚠️ DENETİM 2026-08-09 (ENGEL) — ARTIK KOŞULSUZ `True` DÖNMÜYOR.
            # Eski hâli, paket kuyruğa HİÇ alınamamış olsa bile True dönüyordu; `_emergency_stop_all`
            # bunu `stmStopped` olarak yayınlıyor, arayüz de "çıktılar kesildi" diyordu. Yani
            # STOP'un düştüğü durum ile başarılı durum operatöre AYNI görünüyordu.
            # Bu dönüş "STOP paketi donanım kuyruğuna VERİLDİ ve gönderici CANLI" demektir (fiziksel teyit
            # değil — D1.55'ten beri ölü gönderici "verildi" sayılmaz); False ise STOP porta gitmemiştir →
            # çağıran fail-closed davranmalıdır. "Porta YAZILDI" bilgisi E-stop'ta ayrıca ölçülür
            # (`HeadlessCore.hw_stop_yazildi_bekle`).
            kuyruga_verildi = self._send_stm_manual_update()
            if kuyruga_verildi:
                self.logger.info("Tüm bobinler (1-5) durduruldu.")
            else:
                self.logger.error("ACİL: STOP paketi STM kuyruğuna VERİLEMEDİ — bobinler durmamış olabilir!")
        return kuyruga_verildi

    def on_disconnect(self):
        """STM seri bağlantısı koptuğunda çağrılır. Tüm bobin durumlarını SIFIRLA:
        (1) keep-alive artık 'çalışıyor' paketi tazelemesin, (2) bağlantı dönünce ESKİ
        freq/duty ile otomatik RE-FIRE olmasın (firmware watchdog'u geçersiz kılınmasın)."""
        with self._state_lock:
            # D1.81: bağlantı kopmadan ÖNCE kurulmuş START niyeti, bağlantı dönünce bobini ESKİ niyetle enerjilemesin.
            estop_mandali.nesil_artir()
            for i in range(1, STM_BOBIN_SAYISI + 1):
                self.coils_state[i]["is_running"] = False
                self.coils_state[i]["duty"] = 0.0
                self.coils_state[i]["duration"] = 0
                self._coil_deadline[i] = None
            self._force_send_left = 0  # baglanti kopuk → gonderim anlamsiz
        self.logger.warning("STM bağlantısı koptu → tüm bobin durumları sıfırlandı (re-fire engellendi).")
        return True

    def _send_stm_manual_update(self) -> bool:
        """
        Tüm bobinlerin güncel statüsünü okur, binary STM32 paketine çevirir
        ve HeadlessCore.hw_send_queue kuyruğuna koyar.

        Dönen: paket kuyruğa ALINDI mı. (2026-08-09: eskiden `None` dönüyordu; `stop_all_coils`
        bunu kullanamadığı için başarısız STOP'u "başarılı" bildiriyordu — bkz. oradaki not.)
        Diğer çağıranlar dönüşü yok sayar; davranışları DEĞİŞMEZ.
        """
        if not self.core or not hasattr(self.core, '_hw_send_queue'):
            self.logger.warning("HeadlessCore referansı veya '_hw_send_queue' bulunamadı!")
            return False

        stm32_duties = []
        stm32_phases = []
        stm32_freqs = []
        stm32_durs = []

        # State okuma + paket kurulumu kilit altinda (keep-alive/API yarisi). RLock re-entrant.
        # ⚠️ DONGU PAKET GENISLIGINDE, topoloji genisliginde DEGIL (2026-09-10). Firmware
        # NUM_COILS=7 (bobin 6-7 ESP'den STM'e tasindi) ama backend `coils_state` hala 1-5
        # tutuyor; taniomlanmayan bobinler SIFIR gider. Bir alan eksik gonderilirse boyut/CRC
        # tutmaz ve firmware TUM paketleri NACK'ler → hicbir bobin calismaz. Faz 4'te
        # `coils_state` 7'ye cikinca bu dongu KENDILIGINDEN dogru davranir.
        with self._state_lock:
            for i in range(1, STM_PAKET_BOBIN_SAYISI + 1):
                state = self.coils_state.get(i)
                if state is None:
                    # Bu bobin backend topolojisinde henuz YOK → sifir alan (surus komutu gitmez).
                    stm32_duties.append(0.0)
                    stm32_phases.append(0.0)
                    stm32_freqs.append(100.0)
                    stm32_durs.append(0)
                elif state["is_running"]:
                    stm32_duties.append(state["duty"])
                    stm32_phases.append(state["phase"])
                    stm32_freqs.append(state["freq"])
                    stm32_durs.append(state["duration"])
                else:
                    stm32_duties.append(0.0)
                    stm32_phases.append(0.0)
                    stm32_freqs.append(state["freq"])  # kapalıysa da son freq kalır
                    stm32_durs.append(0)

        # DENETIM P3 — BILINCLI OLARAK DEGISTIRILMEDI (firmware protokol degisikligi + tezgah
        # olcumu ister). Sorun: bu paket-kurucu HER keep-alive turunda (2 Hz) taze bir ref_ms
        # tasir; firmware tarafinda `out->ref_ms_valid = 1U` KOSULSUZDUR (main.c:415) ve
        # main.c:568-591 blogu 5 bobinin g_dds_tick'ini kosulsuz yeniden konumlandirir → DDS faz
        # sayaci duzenli olarak Python'un saatinden turetilen bir degere ZIPLAR. Python
        # time.monotonic() ile STM HAL_GetTick() ayri saatler oldugundan, periyodun 1000 ms'i tam
        # bolmedigi frekanslarda (or. AI Pro'nun 1 Hz'i) her turda gercek bir faz sicramasi olur.
        # ZARAR SINIRI (kodda dogrulandi): elektriksel degil, dalga-formu sureklilik kaybi —
        # ISR once tick'i tpp'ye klempler (main.c:829-837), her polarite gecisinde ~500 ns
        # dead-time uygulanir (904-919), duty slew-limiter + tpp-1 klempi korunur → shoot-through
        # ya da sinir-disi surus YOK. DOGRU COZUM: protokole "yeniden hizalama YAPMA" isareti
        # eklemek (ref_ms icin ayrilmis bir deger ya da ayri bir bayrak) ve yalnizca parametre
        # GERCEKTEN degistiginde hizalamak. Bu iki tarafi birden degistirir ve 1 Hz'de
        # osiloskopla dogrulanmadan uygulanmamalidir.
        ref_ms = int(time.monotonic() * 1000) % 1000

        # Binary STM32 Packet Format (genislik = STM_PAKET_BOBIN_SAYISI, su an 7 → 121 bayt):
        # <BB : header (0xAA, 0x55)
        # Nf  : duty · Nf : phase · Nf : freq · NI : duration
        # H   : ref_ms
        # B   : unipolar_maskesi (ISTEK; firmware yetenekle OR'lar)
        # I   : crc32
        # ⚠️ BICIM DIZESI ELLE YAZILMAZ → utils/stm32_transport.STM_PAKET_FMT (tek kaynak).
        with self._state_lock:
            _kip = int(self._unipolar_maskesi) & 0xFF
        data_bytes = struct.pack(
            STM_PAKET_FMT, 0xAA, 0x55, *stm32_duties, *stm32_phases, *stm32_freqs, *stm32_durs, ref_ms, _kip
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
            except queue.Full:
                try:
                    self.core._hw_send_queue.get_nowait()  # en eskiyi at, yer ac
                except queue.Empty:
                    pass
                continue
            # ⚠️ D1.55 (B-1.23): paket KUYRUKTA ama gönderici ölüyse porta HİÇ yazılmaz → "verildi" denmez.
            # Paket yine de kuyrukta KALIR (Y8: gönderim azaltılmaz) — gönderici yeniden başlarsa yazılır.
            return self._gonderici_canli()
        self.logger.warning("HW kuyrugu dolu — paket kuyruga alinamadi (keep-alive sonraki turda tazeleyecek).")
        return False
