from __future__ import annotations

import logging
import queue
import re
import socket
import struct
import threading
import time
from pathlib import Path
from queue import Queue
from typing import Any, Callable

from database.patient_database import get_patient_database
from database.session_manager import get_session_manager
from event_bus import EventPriority, get_event_bus
from services.headless_services import MosquittoSupervisor, NetworkStatusService, UdpDiscoveryService
from utils.dongu_guvenligi import dongu_hatasini_bildir
from utils.simple_signal import SimpleSignal
from utils.stm32_transport import Stm32SerialTransport

# STM_NACK sonrasi ham-paket tekrar oynatma icin AZAMI YAS (sn). Keep-alive turundan
# (0.5 sn) biraz genis tutuldu; daha eskisi 'guncel niyet' sayilmaz.
_RETRY_MAX_AGE_S = 0.75

#: D1.72 (B-1.17): kalıcı NACK'te AYNI RUN paketinin en çok kaç kez yeniden oynatılacağı. Eskiden sınır yoktu:
#: her yazım bir NACK, her NACK bir yeniden oynatma doğuruyordu (ölçüldü: 1,5 sn'de 96 yazım). Keep-alive güncel
#: durumu zaten her turda yeni bir paketle gönderir. ⚠️ STOP (tüm duty 0) için sınır YOK — Ö.4-Y8: STOP'un yeniden
#: gönderimi azaltılmaz.
_NACK_RUN_TEKRAR_SINIRI = 1


class _NackTekrari:
    """STM_NACK yeniden oynatma İSTEĞİ (D1.72 · B-1.17): kuyruğa paketin KENDİSİ değil bu işaret girer.

    ⚠️ NEDEN: eskiden okuyucu iş parçacığı NACK'lenen son paketi kuyruğa KENDİSİ koyuyordu. Gönderici meşgulken
    araya bir STOP girdiyse sıra [STOP, eski RUN] oluyor ve bobin acil durdurmadan SONRA eski duty ile yeniden
    enerjileniyordu (ölçüldü: son paket RUN, ~0,48 sn — bir sonraki keep-alive'a dek). Kararı artık TEK tüketici
    (gönderici) işareti işlerken verir: porta son yazılan paket hâlâ bu RUN değilse ya da kuyrukta daha yeni bir
    niyet bekliyorsa eski RUN OYNATILMAZ. Tek tüketici karar verdiği için denetle-sonra-yap aralığı yoktur: işaret
    işlendikten sonra konan paket her zaman tekrarın ARDINDAN yazılır. STOP her koşulda yeniden oynatılır (Y8)."""

    __slots__ = ("paket", "tekrar")

    def __init__(self, paket: Any, tekrar: int) -> None:
        self.paket = paket
        self.tekrar = tekrar


class SeriBaglantiDurumu:
    """Paylaşılan seri bağlantı + **NESİL** damgası (thread-güvenli).

    ===========================================================================
    ⚠️ NEDEN AYRI BİR SINIF — KAPATILAN YARIŞ (Audit P3, 2026-09-11)
    ===========================================================================
    Bağlantıya ÜÇ thread dokunur: sender (ana döngü), `reader` ve `reconnect`.
    Eskiden `serial_conn` kilitsiz bir nonlocal'dı ve reader kapanırken KİMLİK
    KONTROLÜ YAPMADAN `serial_conn = None` diyordu. Kablo takılıp çıkarıldığında:

        1) kablo çıkar → reader'ın `readline()`ı patlar, döngüden çıkar
        2) 3 sn sonra reconnect YENİ bağlantıyı kurar
        3) ESKİ reader thread'i nihayet çalışır → `close(YENİ)` + `None`

    → Kablo TAKILI ve firmware sağlamken bağlantı anında düşer; döngü tekrarlar.
    Tam olarak "geri takınca hazıra dönmüyor" şikâyeti.

    Çözüm: her reader kendi `conn`unu ve `nesil`ini taşır; paylaşılan durumu
    **yalnızca hâlâ kendisininse** bırakır. Eski kodun "None-ataması yeni atamadan
    önce olur" gerekçesi bir GARANTİ değil, thread zamanlaması VARSAYIMIYDI.

    Kapı: tests/test_stm_seri_yeniden_baglanma.py (mutasyonla kanıtlı)
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._conn: Any = None
        self._nesil = 0

    def aktif(self) -> Any:
        with self._lock:
            return self._conn

    def yerlestir(self, conn: Any) -> int:
        """Yeni bağlantıyı kur; sahibine nesil damgasını döndür."""
        with self._lock:
            self._conn = conn
            return self._nesil

    def gecersizle(self) -> Any:
        """Mevcut bağlantıyı bırak ve nesli ilerlet → eski reader'lar YABANCI olur.

        @return kapatılması gereken eski bağlantı (yoksa None)
        """
        with self._lock:
            eski = self._conn
            self._conn = None
            self._nesil += 1
            return eski

    def birak(self, conn: Any, nesil: int) -> bool:
        """KİMLİK KONTROLLÜ bırakma.

        @return True → paylaşılan durum GERÇEKTEN bu bağlantıyı tutuyordu ve bırakıldı.
                False → araya YENİ bir bağlantı girmiş; çağıran ona DOKUNMAMALI.
        """
        with self._lock:
            benim = self._nesil == nesil and self._conn is conn
            if benim:
                self._conn = None
                self._nesil += 1
            return benim


#: "Seri port hâlâ duruyor mu" yoklamasının periyodu (sn).
#
# ⚠️ NEDEN VAR (sahip talebi 2026-09-11: "kablo çıktı bobinler offline dönsün"):
# Boştayken (hiçbir bobin çalışmazken) UART **tamamen sessizdir** — keep-alive koşulsuz
# değildir (`hardware_controller._tick`: `need_send = any_running or ...`) ve firmware de
# ilk paketten sonra ping'i keser. Dolayısıyla ne yazma hatası ne okuma hatası oluşur ve
# kablo çıkışı FARK EDİLMEZ: arayüz STM'i sonsuza dek "bağlı" gösterir.
# Port varlığı kesin ölçüttür: USB çekilince COM portu numaralandırmadan düşer.
# 2 sn, kopuşun operatöre anında görünmesi ile numaralandırma maliyeti arasında denge.
_PORT_CHECK_S = 2.0


def _tum_duty_sifir_mi(stm_msg: Any) -> bool:
    """Porta yazılan STM paketi bir STOP mu (TÜM bobinlerin duty alanı 0)? (D1.55 · B-1.23)

    Paket biçimi `utils.stm32_transport.STM_PAKET_FMT`: `<BB` başlık (0xAA 0x55), ardından bobin başına
    duty (`f`). Biçim tanınmazsa False — "STOP yazıldı" iddiası ancak paket gerçekten okunabiliyorsa kurulur."""
    from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI

    n = STM_PAKET_BOBIN_SAYISI
    if not isinstance(stm_msg, (bytes, bytearray)) or len(stm_msg) < 2 + 4 * n:
        return False
    if stm_msg[0] != 0xAA or stm_msg[1] != 0x55:
        return False
    return all(d == 0.0 for d in struct.unpack_from(f"<{n}f", stm_msg, 2))


class HeadlessCore:
    """Qt-free backend core for STM32 communication and shared services."""

    #: STM ACK satirindaki bobin sayisi (faz 4, 2026-09-10: 5 → 7).
    #: ⚠️ Ayristirici uzunluktan BAGIMSIZ (virgulle ayirir); bu sabit yalniz KIRPMA
    #: sinirridir. Kucuk kalirsa bobin 6-7'nin ACK degerleri SESSIZCE atilir ve
    #: canli durum bayat kalir (arayuz 'Aktif' der, gercek duty gorunmez).
    STM_COIL_COUNT = 7

    def __init__(
        self,
        app_data_dir: str | Path,
        *,
        api_port: int = 8000,
        start_headless_services: bool = True,
        ensure_mosquitto: bool = True,
        event_bus=None,
    ) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.app_data_dir = Path(app_data_dir)
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.api_port = int(api_port)

        self.event_bus = event_bus or get_event_bus()
        self.stm_connected_signal = SimpleSignal()
        self.stm_is_connected = False
        # ⚠️ "BAGLI" ile "UYUMLU" AYRI: kart konusuyor olabilir ama backend'in paketledigi
        # genisligi anlamayan bir firmware kosuyor olabilir (bkz. `_stm_kimligini_isle`).
        # Baslangic `None` = HENUZ BANNER GORULMEDI (bilinmiyor); `False` DEGIL — aksi halde
        # kart hic konusmadan once "uyumsuz" deyip seansi bosuna reddederdik.
        self.stm_kimlik = None
        self.stm_uyumlu: bool | None = None
        self.stm_uyumsuzluk_sebebi: str = ""
        self._stm_state_lock = threading.RLock()
        self.stm_connected_signal.connect(self._on_stm_connected_slot)

        # ⚠️ D1.37 (B-3.8): DB AÇILAMASA DA ÇEKİRDEK KURULUR — backend DB'siz (kısıtlı) açılır.
        # Eskiden iki açılış SARMASIZDI: at-rest göçü dosya kilidine takılınca düz-metin DB
        # `GocBekliyorHatasi` verir (sahip kararı 3903ea9: karantinaya ALINMAZ), istisna `main()`'den
        # kaçar ve HİÇBİR uç açılmazdı — ACİL DURDUR dahil. GENEL yakalanır (plan C1-7): Karar-6
        # fail-closed ve bozuk dosya `RuntimeError`ları da aynı sonucu doğuruyordu. Neden
        # `db_acilis_hatalari`na yazılır → `/api/health` `dbReady=false` + `dbSebep`, seans 503.
        # Açılamayan DB bu süreçte YENİDEN DENENMEZ (`acilis_hatasini_kilitle`): sağlık ucu async;
        # her çağrıda göçü (kalıcı kilitte ≥6 sn) yeniden denemek olay döngüsünü — ACİL DURDUR'u —
        # bloklar ve launcher'ın 3 sn'lik dbReady okuması "bilinmiyor"a düşüp güncellemeyi onaylardı.
        self.db_acilis_hatalari: dict[str, str] = {}
        self.patient_db = self._db_ac("hasta", lambda: get_patient_database(self.app_data_dir))
        self.session_manager = self._db_ac("tedavi", lambda: get_session_manager(self.app_data_dir))

        self.mosquitto_supervisor = None
        self.network_status_service = None
        self.udp_discovery_service = None
        if start_headless_services:
            self.start_headless_services(ensure_mosquitto=ensure_mosquitto)

        self._hw_send_queue: Queue = Queue(maxsize=4)
        self._hw_sender_stop = threading.Event()
        self._hw_izlemeyi_kur()
        self._hw_sender_thread = threading.Thread(
            target=self._hw_sender_worker,
            daemon=True,
            name="HWSender",
        )
        self._hw_sender_thread.start()
        self._publish_event("system.core.started", {"appDataDir": str(self.app_data_dir)})

    # ── HWSender DENETİMİ (D1.55 · B-1.23) ─────────────────────────────────────────────────────
    # ⚠️ NEDEN: HWSender (kuyruk → seri port) ölürse `HardwareController._send_stm_manual_update` paketi
    # kuyruğa koyup "kuyruğa verildi=True" diyordu; E-stop bunu `stmStopped` diye yayınlıyor, porta ise
    # 0 bayt gidiyordu (ölçüldü: ölü göndericide stop_all ×5 True, yazım sayısı 4→4). Tek koruma firmware
    # ölü-adam devresiydi (1,5 sn). Artık: (1) döngü tur hatasında ÖLMEZ, (2) ölü gönderici yeniden
    # başlatılır, (3) çağıran canlılığı sorar, (4) E-stop "STOP porta YAZILDI" bilgisini yazım izinden okur.
    # Y8: hiçbiri STOP'u kapılamaz ya da gönderimini azaltmaz — yalnız RAPORLANAN teyit dürüstleşir.

    #: Ölü HWSender en sık bu aralıkta yeniden başlatılır (sn): başlar başlamaz ölen bir çalışan
    #: (ör. iş parçacığı tükenmesi) saniyede onlarca iş parçacığı doğurmasın.
    _HW_CANLANDIRMA_ARALIGI_S = 3.0

    def _hw_izlemeyi_kur(self) -> None:
        """Canlandırma kilidi ve yazım izi. İdempotent: `__new__` ile kurulan çekirdekler (testler) bunu
        `_hw_sender_worker` başlarken alır; üretimde `__init__` iş parçacığından ÖNCE kurar."""
        if getattr(self, "_hw_yazim_kosulu", None) is None:
            self._hw_yazim_kosulu = threading.Condition()
            self._hw_yazim_sayaci = 0  # porta başarıyla yazılan paket sayısı
            self._hw_son_stop_yazimi = 0  # son tüm-duty-0 (STOP) yazımının sayaç değeri
        if getattr(self, "_hw_canlandirma_kilidi", None) is None:
            self._hw_canlandirma_kilidi = threading.Lock()
            self._hw_son_canlandirma = 0.0

    def hw_gonderici_canli(self) -> bool:
        """HWSender iş parçacığı yaşıyor mu?"""
        t = getattr(self, "_hw_sender_thread", None)
        return bool(t is not None and t.is_alive())

    def hw_gondericiyi_canlandir(self) -> bool:
        """Ölü HWSender'ı yeniden başlatır. @return gönderici ŞİMDİ canlı mı.

        Kapanışta (`_hw_sender_stop` kurulu) başlatmaz; en sık `_HW_CANLANDIRMA_ARALIGI_S`'de bir dener.
        Yeni çalışan aynı `_seri_baglanti`yı devralır: `connect_serial` önce eski bağlantıyı geçersizleyip
        KAPATIR — ölü çalışanın okuyucusu portu tutuyor olabilir ve COM portu tek erişimlidir."""
        if self.hw_gonderici_canli():
            return True
        self._hw_izlemeyi_kur()
        with self._hw_canlandirma_kilidi:
            if self.hw_gonderici_canli():
                return True
            if self._hw_sender_stop.is_set():
                return False
            simdi = time.monotonic()
            if simdi - self._hw_son_canlandirma < self._HW_CANLANDIRMA_ARALIGI_S:
                return False
            self._hw_son_canlandirma = simdi
            try:
                t = threading.Thread(target=self._hw_sender_worker, daemon=True, name="HWSender")
                t.start()
            except Exception:
                dongu_hatasini_bildir(
                    "[HWSender] ÖLÜ ve yeniden BAŞLATILAMADI — STM'e paket yazılamıyor (firmware ölü-adam 1,5 sn'de keser).",
                    logger=self.logger,
                )
                return False
            self._hw_sender_thread = t
        dongu_hatasini_bildir(
            "[HWSender] ÖLÜ bulundu → yeniden başlatıldı (seri bağlantı yeniden kurulacak).",
            logger=self.logger,
            exc_info=False,
        )
        return t.is_alive()

    def hw_yazim_isareti(self) -> int:
        """Şimdiye dek porta yazılan paket sayısı — `hw_stop_yazildi_bekle` ile birlikte kullanılır."""
        self._hw_izlemeyi_kur()
        with self._hw_yazim_kosulu:
            return self._hw_yazim_sayaci

    def hw_stop_yazildi_bekle(self, isaret: int, zaman_asimi: float) -> bool:
        """`isaret` alındıktan SONRA porta tüm-duty-0 (STOP) paketi YAZILDI mı? En çok `zaman_asimi` sn bekler.

        Kuyruğa vermek yetmez: gönderici ölüyse ya da bağlantı yoksa paket porta hiç gitmez."""
        self._hw_izlemeyi_kur()
        bitis = time.monotonic() + max(0.0, float(zaman_asimi))
        with self._hw_yazim_kosulu:
            while self._hw_son_stop_yazimi <= isaret:
                kalan = bitis - time.monotonic()
                if kalan <= 0:
                    return False
                self._hw_yazim_kosulu.wait(kalan)
            return True

    def _hw_yazimi_kaydet(self, stm_msg: Any) -> None:
        """Gönderici: porta BAŞARIYLA yazılan paketi say; tüm duty alanları 0 ise STOP yazımı olarak işaretle."""
        try:
            stop_mu = _tum_duty_sifir_mi(stm_msg)
        except Exception:
            stop_mu = False
        kosul = getattr(self, "_hw_yazim_kosulu", None)
        if kosul is None:
            return
        with kosul:
            self._hw_yazim_sayaci += 1
            if stop_mu:
                self._hw_son_stop_yazimi = self._hw_yazim_sayaci
            kosul.notify_all()

    #: `db_acilis_hatalari` anahtarı → operatöre gösterilen ad.
    _DB_ADI = {"hasta": "Hasta veritabanı", "tedavi": "Tedavi kaydı veritabanı"}

    def _db_ac(self, ad: str, ac: Callable[[], Any]):
        """DB'yi aç; açılamazsa None döndür, nedeni kaydet ve bu süreçte yeniden denemeyi kilitle (D1.37).

        Neden metni `/api/health`'e gider (auth-muaf, tünelden erişilebilir) → dosya YOLU ya da istisna
        ayrıntısı İÇERMEZ; tam zincir yalnız günlüğe yazılır."""
        try:
            return ac()
        except Exception as exc:  # noqa: BLE001 — GENEL (C1-7): göç, Karar-6 fail-closed, bozuk dosya
            from database import patient_database as _pdb
            from database import treatment_history_db as _thdb
            from database.sqlcipher_util import GocBekliyorHatasi

            ad_metni = self._DB_ADI.get(ad, ad)
            if isinstance(exc, GocBekliyorHatasi):
                sebep = (
                    f"{ad_metni} göç bekliyor: at-rest şifreleme göçü tamamlanmadı (dosya kilitli olabilir); "
                    "dosya korunuyor, karantinaya alınmadı. Cihazı yeniden başlatın — göç yeniden denenecek."
                )
            else:
                sebep = (
                    f"{ad_metni} açılamadı ({type(exc).__name__}). Cihazı yeniden başlatın; "
                    "sorun sürerse teknik desteğe başvurun."
                )
            self.db_acilis_hatalari[ad] = sebep
            (_pdb if ad == "hasta" else _thdb).acilis_hatasini_kilitle(self.app_data_dir, exc)
            self.logger.error(
                "%s — backend DB'SİZ (kısıtlı) açılıyor: ACİL DURDUR ve STOP çalışır, yeni seans 503.",
                sebep,
                exc_info=True,
            )
            return None

    def start_headless_services(self, *, ensure_mosquitto: bool = True) -> None:
        """Start Qt-free support services used by production service mode."""
        try:
            self.mosquitto_supervisor = MosquittoSupervisor(
                port=1883,
                ensure_running=ensure_mosquitto,
                start_mdns=True,
                event_bus=self.event_bus,
            )
            self.mosquitto_supervisor.start()
            self.logger.info("MosquittoSupervisor started.")
        except Exception as exc:
            self.logger.warning("MosquittoSupervisor could not start: %s", exc)

        try:
            self.network_status_service = NetworkStatusService(
                mqtt_port=1883,
                event_bus=self.event_bus,
            )
            self.network_status_service.start()
            self.logger.info("NetworkStatusService started.")
        except Exception as exc:
            self.logger.warning("NetworkStatusService could not start: %s", exc)

        try:
            self.udp_discovery_service = UdpDiscoveryService(
                api_port=self.api_port,
                discovery_port=5051,
                mqtt_port=1883,
                event_bus=self.event_bus,
                logger_instance=self.logger,
            )
            self.udp_discovery_service.start()
            self.logger.info("UdpDiscoveryService started.")
        except Exception as exc:
            self.logger.warning("UdpDiscoveryService could not start: %s", exc)

    def _publish_event(
        self,
        event_type: str,
        data: dict[str, Any],
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        try:
            self.event_bus.publish(
                event_type,
                data,
                priority=priority,
                source="headless_core",
            )
        except Exception:
            self.logger.exception("Event publish failed: %s", event_type)

    def _set_stm_connected(self, connected: bool) -> None:
        """DENETIM P3: karsilastirma kilit ICINDE, emit kilit DISINDA yapiliyordu → iki thread
        (reader / sender / reconnect) ayni gecisi es-zamanli gorup CIFT emit edebiliyor, ters
        siralanan emit'lerde ise son durum KAYBOLABILIYORDU (ornegin 'kopuk' emit'i 'bagli'dan
        sonra islenirse UI/acil-durdurma zinciri yanlis durumda kalir). Durum guncellemesi ve
        bildirim artik AYNI kilit altinda atomik.

        DEADLOCK YOK: bagli slot (_on_stm_connected_slot) ayni kilidi TEKRAR alir, ancak
        `_stm_state_lock` bir threading.RLock'tur ve SimpleSignal.emit SENKRONDUR → slot,
        kilidi zaten tutan AYNI thread'de kosar; RLock yeniden-girise izin verir."""
        with self._stm_state_lock:
            if self.stm_is_connected == connected:
                return
            self.stm_is_connected = bool(connected)  # gecisi kilit ALTINDA muhurle
            self.stm_connected_signal.emit(connected)

    def _stm_kimligini_isle(self, banner: str) -> None:
        """`STM_READY` banner'indan kart kimligini cikar ve UYUM kararini sakla.

        ⚠️ KARAR UC DURUMLUDUR (`apps/backend/utils/stm32_kimlik.uyum_denetle`):
            True  = kanal sayisi paket genisligimizle esitti
            False = KESIN uyumsuz  -> seans baslatma reddedilir
            None  = banner taninmadi ("bilinmiyor") -> seans ENGELLENMEZ, ama GORUNUR

        "Bilinmiyor"un seansi engellememesi bilincli: banner bicimi ileride degisip UYUMLU
        bir firmware de taninmayabilir; o durumda calisan bir klinigi durdurmak, cozdugumuz
        sorundan buyuk bir zarar olurdu. Yalnizca KESIN uyumsuzlukta reddediyoruz.

        ⚠️ BU KAPI ACIL DURDURMAYI ENGELLEMEZ. Uyumsuz firmware'de bile STOP yolu acik
        kalir (depo degismezi: bobinler her seyden once durur).
        """
        from utils.stm32_kimlik import banner_ayristir, uyum_denetle
        from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI

        kimlik = banner_ayristir(banner)
        uyumlu, sebep = uyum_denetle(kimlik, STM_PAKET_BOBIN_SAYISI)
        with self._stm_state_lock:
            onceki = self.stm_uyumlu
            self.stm_kimlik = kimlik
            self.stm_uyumlu = uyumlu
            self.stm_uyumsuzluk_sebebi = sebep
        if uyumlu is False:
            # ⚠️ `error`: bu, operatorun SEANS BASLATAMAYACAGI anlamina gelir; `warning`
            # destek log'unda kaybolurdu.
            self.logger.error("STM32 FIRMWARE UYUMSUZ — %s", sebep)
        elif uyumlu is None:
            self.logger.warning("STM32 firmware kimligi okunamadi — %s", sebep)
        elif onceki is not True:
            self.logger.info(
                "STM32 firmware uyumlu: %s, %d kanal, %s",
                kimlik.surum,
                kimlik.kanal,
                kimlik.kip,
            )
        if uyumlu is not True:
            self._publish_event(
                "hardware.stm.uyumsuz",
                {"uyumlu": uyumlu, "sebep": sebep, "banner": (kimlik.ham if kimlik else banner.strip())},
                priority=EventPriority.HIGH,
            )

    def _on_stm_connected_slot(self, is_connected: bool) -> None:
        with self._stm_state_lock:
            self.stm_is_connected = bool(is_connected)
        # ⚠️ 1-B bağımsız inceleme (i1/B1): olay ÖNCE yayınlanır, bildirim SONRA ve fırlatamaz. Eskiden günlük
        # olaydan önceydi: günlük fırlatınca (kilitli dosya, disk dolu) `SimpleSignal.emit` istisnayı yutuyor ve
        # `hardware.stm.disconnected` HİÇ yayınlanmıyordu — api_server o olayla canlı durumu düşürür,
        # `on_disconnect()` çağırır ve STM kullanan seansı ACİL DURDURUR (Y8: bu zincir günlüğe bağlı olamaz).
        self._publish_event(
            "hardware.stm.connected" if is_connected else "hardware.stm.disconnected",
            {"connected": bool(is_connected)},
            priority=EventPriority.HIGH,
        )
        dongu_hatasini_bildir(
            "STM32 connection state updated: %s",
            bool(is_connected),
            logger=self.logger,
            seviye=logging.INFO,
            exc_info=False,
        )

    def _parse_stm_ok(self, decoded: str) -> list[dict[str, Any]]:
        num = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
        vals = rf"({num}(?:,{num})*)"
        match = re.search(rf"D={vals}\s+P={vals}\s+F={vals}\s+T={vals}", decoded)
        if not match:
            return []

        # ETKIN SURUS KIPI (`K=<maske>`): firmware'in GERCEKTEN uyguladigi kip.
        # ⚠️ Istenen DEGIL etkin: firmware `yetenek || istek` uygular, yani bobin 6-7
        # arayuz "bipolar" dese bile 1 gelir. Arayuz dugmesinin gercekten ne yaptigini
        # gosteren TEK kaynak budur; istegi geri yansitmak YALAN olurdu.
        # Eski firmware bu alani basmaz -> anahtar HIC koyulmaz (None de degil).
        _k = re.search(r"[,\s]K=(\d+)", decoded)
        _etkin_kip = int(_k.group(1)) if _k else None

        d_vals = [float(x) for x in match.group(1).split(",")]
        p_vals = [float(x) for x in match.group(2).split(",")]
        f_vals = [float(x) for x in match.group(3).split(",")]
        t_vals = [int(float(x)) for x in match.group(4).split(",")]

        # Audit P3: alan uzunlukları eşit değilse SESSİZCE kırpma yerine uyar + satırı reddet — min ötesi
        # bobinler coil_update yayınlamaz → live_state bayat/yanlış kalır (UI/telemetri desync).
        _lens = (len(d_vals), len(p_vals), len(f_vals), len(t_vals))
        if len(set(_lens)) > 1:
            import logging as _lg

            _lg.getLogger("headless_core").warning(
                "STM parse: alan uzunlukları uyuşmuyor %s → satır reddedildi.", _lens
            )
            return []
        updates: list[dict[str, Any]] = []
        max_items = min(self.STM_COIL_COUNT, len(d_vals), len(p_vals), len(f_vals), len(t_vals))
        for index in range(max_items):
            coil_id = index + 1
            duty = float(d_vals[index])
            # DENETIM P3: firmware ACK'i duty'yi TAMSAYI yuzde basar ("D=%d", (int)(duty*100)) →
            # C cast sifira dogru kirptigi icin %1'in ALTINDAKI her duty 0 olarak gelir. Oysa
            # firmware fiziksel surusu TAM cozunurlukle yapar (tpp x duty). `running = duty > 0`
            # bu yuzden dusuk-duty bobini "durdu" gosteriyordu → canli durum/telemetri gercekle
            # celisir (operator bobini kapali sanir). Frekans/faz 0 DEGILSE bobin hala surulüyor
            # olabilir; bu durumu "calisiyor" say ve ACK'in cozunurluk sinirini logla.
            running = duty > 0.0
            if not running and float(f_vals[index]) > 0.0 and int(t_vals[index]) > 0:
                running = True
            updates.append(
                {
                    "coil_id": coil_id,
                    "duty": duty,
                    "duty_cycle": duty,
                    "freq": float(f_vals[index]),
                    "frequency": float(f_vals[index]),
                    "phase": float(p_vals[index]),
                    "duration_min": int(t_vals[index]),
                    "running": running,
                    "pwm_active": running,
                    # ⚠️ ETKİN kip (istenen DEĞİL): firmware `yetenek || istek` uygular.
                    # Alan YOKSA (eski firmware) anahtar HİÇ KONMAZ → aşağı akış
                    # "bildirilmedi" ile "bipolar" ayırt edebilsin.
                    **({"unipolar": bool((_etkin_kip >> index) & 1)} if _etkin_kip is not None else {}),
                }
            )
        return updates

    #: Bobin 6-7 sensor telemetrisi (faz 3, 2026-09-10). ⚠️ Bu, o iki bobinin sicakliginin
    #: arayuze ulastigi TEK yoldur; arayuzdeki 48 °C istemci interlock'u buna bagimlidir
    #: (cihaz-tarafli termal kesme sahip karariyla YOK). Sozlesme:
    #:     -> STM_TELE: C=6,T=34.20,A=27.10,B=1.842
    #: ⚠️ ALANLAR OPSIYONEL ve bu KASITLIDIR: olculmeyen alan HIC GONDERILMEZ (0.0
    #: gondermek "olculdu" gibi kaydedilir — gecmiste ayni desen PDF'e "0.0 °C olculdu"
    #: yazdirmisti). Akim alani YOK: ACS712 tasinmiyor (sahip karari 3).
    _TELE_DESENI = re.compile(
        r"STM_TELE:\s*C=(?P<c>[0-9]+)"
        r"(?:.*?[,\s]T=(?P<t>[+-]?[0-9]*[.]?[0-9]+))?"
        r"(?:.*?[,\s]A=(?P<a>[+-]?[0-9]*[.]?[0-9]+))?"
        r"(?:.*?[,\s]B=(?P<b>[+-]?[0-9]*[.]?[0-9]+))?"
        # `N` = B zirvesinin turedigi ornek sayisi; `S=1` = manyetik ham eksen tam olcege
        # DAYANDI (|B| GUVENILMEZ). Firmware ikisini de yalniz `B` ile birlikte basar.
        r"(?:.*?[,\s]N=(?P<n>[0-9]+))?"
        r"(?:.*?[,\s]S=(?P<s>[01]))?"
        # ISARETLI EKSEN UCLARI (mT): saniyelik pencerenin min/max'i. Tepeden-tepeye
        # bunlardan TURETILIR. ⚠️ `B=` tepe BUYUKLUKTUR (isaretsiz) ve unipolar (0->+B)
        # ile bipolari (-B->+B) AYNI gosterir; bipolar/faz kazancini YALNIZ bunlar tasir.
        r"(?:.*?[,\s]XN=(?P<xn>[+-]?[0-9]*[.]?[0-9]+))?"
        r"(?:.*?[,\s]XP=(?P<xp>[+-]?[0-9]*[.]?[0-9]+))?"
        r"(?:.*?[,\s]YN=(?P<yn>[+-]?[0-9]*[.]?[0-9]+))?"
        r"(?:.*?[,\s]YP=(?P<yp>[+-]?[0-9]*[.]?[0-9]+))?"
        r"(?:.*?[,\s]ZN=(?P<zn>[+-]?[0-9]*[.]?[0-9]+))?"
        r"(?:.*?[,\s]ZP=(?P<zp>[+-]?[0-9]*[.]?[0-9]+))?"
        r"(?:.*?[,\s]I=(?P<i>[+-]?[0-9]*[.]?[0-9]+))?"
        r"(?:.*?[,\s]X=(?P<x>[01]))?"
    )

    def _parse_stm_tele(self, decoded: str) -> dict | None:
        """`STM_TELE` satirini olay govdesine cevirir; eslesmezse None.

        Eksik alan ANAHTARI HIC KOYULMAZ (None de koyulmaz) → asagi akis "olculmedi" ile
        "0.0 olculdu"yu ayirt edebilir.
        """
        m = self._TELE_DESENI.search(decoded)
        if not m:
            return None
        try:
            coil_id = int(m.group("c"))
        except (TypeError, ValueError):
            return None
        if not (1 <= coil_id <= 8):
            return None
        govde: dict = {"coil_id": coil_id}
        # ⚠️ `I` = ACS712 akimi (bobin 1-5). `X=1` = ADC tavanina dayandi (bolucusuz
        # ~12 A ustu, bkz. firmware/.../pemf_akim.h) → deger GUVENILMEZ; yutulmaz,
        # isaretlenir ki operatore soylenebilsin.
        for anahtar, alan in (
            ("t", "object_temp"),
            ("a", "ambient_temp"),
            ("b", "magnetic_field"),
            ("xn", "mag_x_min"),
            ("xp", "mag_x_max"),
            ("yn", "mag_y_min"),
            ("yp", "mag_y_max"),
            ("zn", "mag_z_min"),
            ("zp", "mag_z_max"),
            ("i", "current"),
        ):
            ham = m.group(anahtar)
            if ham is None:
                continue
            try:
                govde[alan] = float(ham)
            except ValueError:
                continue
        # ⚠️ `magnetic_field` ARTIK ANLIK DEGIL, SON 1 SANIYENIN **ZIRVESI** (firmware
        # 2026-09-11, sahip karari). Bobinler birlikte anahtarlandigi icin anlik ornek
        # darbenin neresine dustugune gore 0 ile tam alan arasi rastgele bir sayi
        # veriyordu. `magnetic_samples` o zirvenin kac ornekten turedigi (~400 beklenir;
        # dusmesi I2C hattinin yavasladigini soyler) — alan YOKKEN anahtar KOYULMAZ.
        _n = m.group("n")
        if _n is not None and "magnetic_field" in govde:
            try:
                govde["magnetic_samples"] = int(_n)
            except ValueError:
                pass
        if m.group("s") == "1" and "magnetic_field" in govde:
            govde["magnetic_saturated"] = True
        if m.group("x") == "1":
            govde["current_saturated"] = True
        if not any(k in govde for k in ("object_temp", "ambient_temp", "magnetic_field", "current")):
            return None  # yalniz C (ve/veya X) geldi → tasinacak olcum yok
        return govde

    def _tum_bobinleri_sifirla_yayinla(self) -> None:
        """Watchdog ve termal (STM_EVT) dallarının ORTAK bobin sıfırlama yayını (P4 · D1.30).

        Her STM bobini için arayüz durumunu sıfırlar (duty/frekans/faz/süre 0, running/pwm_active
        False). Eskiden iki dalda birebir İKİZ blok vardı ve watchdog kopyası kapısızdı (bobin 7'yi
        atlayan mutantta 179/179 yeşil) — bir kopyaya yapılan düzeltme diğerinde kalırdı.

        ⚠️ YALNIZ YAYIN: donanım (HardwareController) sıfırlaması B-1.18'in (D1.73) konusudur. Oraya
        eklenecek her davranış PARAMETREYLE yalnız watchdog dalına açılmalı — termal dalın davranışı
        sahip kararı olmadan DEĞİŞMEZ (A-47: termal kesme YOK, dal yalnız firmware satırını ayrıştırır)."""
        for coil_id in range(1, self.STM_COIL_COUNT + 1):
            self._publish_event(
                "hardware.stm.coil_update",
                {
                    "coil_id": coil_id,
                    "duty": 0.0,
                    "duty_cycle": 0.0,
                    "freq": 0.0,
                    "frequency": 0.0,
                    "phase": 0.0,
                    "duration_min": 0,
                    "running": False,
                    "pwm_active": False,
                },
                priority=EventPriority.HIGH,
            )

    def _handle_stm_line(
        self,
        decoded: str,
        retry_last_payload: Callable[[], None] | None = None,
    ) -> None:
        if not decoded:
            return

        if "STM_TELE" in decoded:
            # ⚠️ INFO'ya YAZILMAZ: 1 Hz x 2 bobin = gunde ~170k satir; log'u bogar ve gercek
            # olaylari (NACK/watchdog/termal) goze batmaz hale getirir. DEBUG yeterli.
            self.logger.debug("[STM32] %s", decoded)
            govde = self._parse_stm_tele(decoded)
            if govde is not None:
                self._publish_event("hardware.stm.telemetry", govde)
            return

        self.logger.info("[STM32] %s", decoded)

        if "STM_READY" in decoded or "STM_OK:" in decoded:
            self._set_stm_connected(True)

        # ⚠️ UYUM KAPISI (2026-09-18) — "BAGLI" ile "UYUMLU" AYRI SEYLERDIR.
        # Eskiden yalnizca yukaridaki satir vardi: `STM_READY` gorulunce baglanti YESIL
        # oluyor, satirin ICERIGINE HIC BAKILMIYORDU. Eski firmware (5 bobin) 88 baytlik
        # paket bekler; backend 120 bayt gonderir → kart CRC'yi yanlis ofsetten okur, her
        # pakete NACK doner ve PWM durumuna HIC dokunmaz. Belirti: gosterge YESIL, hata
        # penceresi YOK, hicbir bobin baslamiyor. Tek teshis yolu UART'i elle dinlemekti.
        if "STM_READY" in decoded:
            self._stm_kimligini_isle(decoded)

        if "STM_OK:" in decoded:
            try:
                for update in self._parse_stm_ok(decoded):
                    self._publish_event("hardware.stm.coil_update", update)
            except Exception as exc:
                self.logger.error("STM_OK parse error: %s", exc)
                self._publish_event(
                    "hardware.stm.error",
                    {"message": f"STM_OK parse error: {exc}", "raw": decoded},
                    priority=EventPriority.HIGH,
                )
            return

        if "STM_NACK" in decoded:
            self.logger.warning("[STM32 NACK] Packet rejected; retrying last payload once.")
            self._publish_event(
                "hardware.stm.nack",
                {"message": decoded},
                priority=EventPriority.HIGH,
            )
            if retry_last_payload:
                retry_last_payload()
            return

        if "Watchdog Timeout" in decoded:
            self._publish_event(
                "hardware.stm.watchdog_timeout",
                {"message": decoded},
                priority=EventPriority.CRITICAL,
            )
            self._tum_bobinleri_sifirla_yayinla()
            return

        if "STM_EVT" in decoded:
            # M2 (denetim 2026-09-03): firmware NTC termal kesme (PEMF_NTC_TERMAL_ENABLED=1)
            # yeniden derlenirse '-> STM_EVT: TERMAL kesme (>=48C) ...' gonderir. Bu dal
            # OLMADAN satir hicbir kosula uymuyor, jenerik logger'a dusup SESSIZCE yutuluyordu
            # -> operatore/UI'ye ulasmiyordu (hasta guvenligi olayi kaybi). Watchdog dalıyla
            # ayni kalibi izler: CRITICAL olay + etkilenen bobinleri sifirla. (Termal su an
            # firmware'de KAPALI oldugundan latent; parser once inmeli, sonra firmware acilmali.)
            self._publish_event(
                "hardware.stm.thermal_cutoff",
                {"message": decoded},
                priority=EventPriority.CRITICAL,
            )
            self._tum_bobinleri_sifirla_yayinla()
            return

        if "STM_ERR" in decoded:
            self._publish_event(
                "hardware.stm.error",
                {"message": decoded},
                priority=EventPriority.HIGH,
            )

    def _hw_sender_worker(self) -> None:
        udp_sock = None
        # [0]=son yazilan paket, [1]=yazildigi monotonic an (bkz. retry_last_payload yas siniri),
        # [2]=bu paketin kacinci NACK tekrari oldugu (D1.72; 0 = ilk yazim)
        # ⚠️ `payload_lock` ile korunur: reader thread'i (retry_last_payload) okur, sender yazar.
        last_payload: list[Any] = [None, 0.0, 0]
        payload_lock = threading.Lock()
        last_reconnect_time = 0.0
        transport = Stm32SerialTransport(self.logger)
        self._hw_izlemeyi_kur()

        # ⚠️ Seri bağlantı PAYLAŞILAN durumdur: sender (bu thread), reader ve reconnect
        # thread'leri birlikte erişir. `nesil`, eski bir reader'ın YENİ bağlantıyı
        # kapatmasını engelleyen kimlik damgasıdır (bkz. connect_serial gerekçesi).
        # D1.55: yeniden başlatılan çalışan AYNI durumu devralır (`hw_gondericiyi_canlandir`) — ölü
        # çalışanın okuyucusu portu hâlâ tutuyorsa `connect_serial` onu geçersizleyip kapatır.
        baglanti = getattr(self, "_seri_baglanti", None)
        if baglanti is None:
            baglanti = SeriBaglantiDurumu()
            self._seri_baglanti = baglanti

        def retry_last_payload() -> None:
            # DENETIM P2: STM_NACK gelince EN SON YAZILAN ham paket kosulsuz yeniden kuyruga
            # konuyordu. Paketin icerigi/yasi hic sorgulanmadigi icin, NACK bir STOP kuyruga
            # girdikten SONRA islenirse FIFO sirasi [P_stop, P_run] olabiliyor ve bobinler
            # acil-durdurmadan SONRA tekrar enerjileniyordu. Iki kapak:
            #   (1) YAS SINIRI — paket bir keep-alive turundan (0.5 sn) eskiyse artik "guncel
            #       niyet" degildir; tazelemeyi keep-alive'a birak (o zaten guncel durumu gonderir).
            #   (2) Baglanti kopmasinda cagiran taraf last_payload'i None yapar (asagi bkz.).
            # ⚠️ KİLİT ŞART: bu fonksiyon READER thread'inden çağrılır, `last_payload`ı ise
            # SENDER thread'i yazar. Kilitsiz okumada paket ile zaman damgası FARKLI turlardan
            # gelebilir → bayat bir paket "taze" sanılıp yeniden oynatılır (STOP'tan sonra
            # yeniden enerjileme riski; yaş sınırının koruduğu şeyin ta kendisi).
            # ⚠️ D1.72 (B-1.17): yaş sınırı (0,75 sn) keep-alive turundan (0,5 sn) GENİŞ olduğu için [P_stop, P_run]
            # sırasını KAPATMIYORDU (ölçüldü: E-stop'tan sonra son paket RUN). Artık paketin kendisi değil
            # `_NackTekrari` işareti kuyruğa girer; "daha yeni niyet var mı" kararını gönderici verir.
            with payload_lock:
                payload, ts, tekrar = last_payload[0], last_payload[1], last_payload[2]
            if payload is None:
                return
            if (time.monotonic() - ts) > _RETRY_MAX_AGE_S:
                self.logger.info(
                    "[STM32 NACK] son paket bayat (%.2fs) → tekrar gonderilmedi; keep-alive guncel durumu tazeleyecek.",
                    time.monotonic() - ts,
                )
                with payload_lock:
                    if last_payload[0] is payload:  # arada tazelenmişse DOKUNMA
                        last_payload[0] = None
                return
            if tekrar >= _NACK_RUN_TEKRAR_SINIRI and not _tum_duty_sifir_mi(payload[0]):
                # Kalıcı NACK: aynı RUN bir kez yeniden oynatıldı ve yine reddedildi → bırak (keep-alive güncel
                # durumu yeni paketle tazeler; sistematik red ayrıca STM_RED kapısında ele alınır). STOP'a uygulanmaz.
                dongu_hatasini_bildir(
                    "[STM32 NACK] ayni RUN paketi %d kez yeniden oynatildi ve yine reddedildi → tekrar BIRAKILDI.",
                    tekrar,
                    logger=self.logger,
                    seviye=logging.WARNING,
                    exc_info=False,
                )
                return
            try:
                self._hw_send_queue.put_nowait(_NackTekrari(payload, tekrar + 1))
            except queue.Full:
                pass

        # ====================================================================
        # ⚠️ AUDIT P3 KAPATILDI (2026-09-11, sahip talebi: "kablo çıktı bobinler offline
        # dönsün, geri takınca hazıra dönebilmeli").
        # --------------------------------------------------------------------
        # ESKİ HÂL: `serial_conn` kilitsiz paylaşılan bir nonlocal'dı ve reader kapanırken
        # KİMLİK KONTROLÜ YAPMADAN `serial_conn = None` diyordu. Eski koddaki gerekçe
        # "eski-reader None-ataması YENİ atamadan ÖNCE olur (clobber yok)" diyordu — bu bir
        # GARANTİ DEĞİL, thread zamanlaması hakkında bir VARSAYIMDIR. Gerçek sıralama:
        #   1) kablo çıkar → reader'ın readline()'ı patlar, döngüden çıkar
        #   2) 3 sn sonra ana döngü reconnect açar, YENİ bağlantı kurulur (serial_conn = YENİ)
        #   3) ESKİ reader thread'i nihayet çalışır → close_serial(YENİ) + serial_conn = None
        # → kablo TAKILI, firmware sağlam, ama bağlantı hemen düşürülür ve döngü tekrarlar.
        # Tam olarak "geri takınca hazıra dönmüyor" şikâyeti.
        #
        # YENİ HÂL: `baglanti` sözlüğü + `serial_lock` + NESİL SAYACI. Her reader kendi
        # connection nesnesini ve nesil numarasını taşır; kapanışta paylaşılan durumu
        # YALNIZCA hâlâ kendisininse temizler. `last_payload` da artık kilitli.
        # ====================================================================
        def _aktif_baglanti():
            return baglanti.aktif()

        def connect_serial() -> None:
            # Eski bağlantıyı KAPAT ve nesli ilerlet → o nesle ait reader artık "yabancı"dır.
            eski = baglanti.gecersizle()
            if eski is not None:
                try:
                    transport.close_serial(eski)
                except Exception:
                    pass
            self._set_stm_connected(False)

            try:
                result = transport.open_and_handshake(
                    stop_event=self._hw_sender_stop,
                    on_line=lambda line: self._handle_stm_line(line, retry_last_payload),
                )
            except Exception as exc:
                self.logger.warning("[STM32] Serial open failed: %s", exc)
                return
            if result is None:
                return

            yeni = result.serial
            nesil = baglanti.yerlestir(yeni)
            self._set_stm_connected(True)
            threading.Thread(target=reader, args=(yeni, nesil), daemon=True, name="STM32Reader").start()

        def reader(conn, nesil: int) -> None:
            """Kendi `conn`unu okur — paylaşılan duruma KÖR. Kapanışta kimlik doğrular."""
            try:
                while not self._hw_sender_stop.is_set():
                    try:
                        if not conn.is_open:
                            break
                        line = conn.readline()
                    except Exception as exc:
                        dongu_hatasini_bildir(  # D1.19 (B-10.121)
                            "[STM32 READER] %s", exc, logger=self.logger, seviye=logging.WARNING, exc_info=False
                        )
                        break
                    if line:
                        decoded = line.decode("utf-8", errors="ignore").strip()
                        self._handle_stm_line(decoded, retry_last_payload)
            finally:
                # ⚠️ KİMLİK KONTROLÜ — bu blok olmadan eski reader YENİ bağlantıyı öldürür.
                benim = baglanti.birak(conn, nesil)
                if benim:
                    self._set_stm_connected(False)
                # Kendi conn'unu HER ZAMAN kapat (yabancıysa bile kendi kaynağıdır).
                try:
                    transport.close_serial(conn)
                except Exception:
                    pass

        try:
            connect_serial()
        except Exception:
            # D1.55 (B-1.23): ilk bağlantı denemesi (okuyucu iş parçacığı başlatma dahil) fırlatsa da çalışan
            # DÖNGÜYE girer — döngü kopuk bağlantıyı yeniden bağlanma ile toparlar; eskiden çalışan ölürdü.
            dongu_hatasini_bildir(
                "[STM32] ilk baglanti denemesi basarisiz — dongu yeniden deneyecek", logger=self.logger
            )

        try:
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception as exc:
            self.logger.warning("[UDP] Socket open failed: %s", exc)
            udp_sock = None

        reconnect_thread = None  # tek eşzamanlı non-blocking reconnect
        last_port_check = 0.0  # kablo-çıktı yoklamasının son anı (monotonic)
        while not self._hw_sender_stop.is_set():
            try:
                # DENETIM P3: geri-cekilme DUVAR SAATI ile olculuyordu. Saat GERI alinirsa
                # (NTP duzeltmesi, DST, elle ayar) `now - last_reconnect_time` negatife duser ve
                # 3 sn kosulu saatlerce saglanmaz → STM kopuk kalir, hicbir yeniden-baglanma
                # DENENMEZ. Monotonik saat geri gitmez.
                now = time.monotonic()
                _conn = _aktif_baglanti()

                # ── KABLO ÇIKTI MI? (port hâlâ enumerate ediliyor mu) ────────────────────────
                # ⚠️ NEDEN SESSİZLİK BEKÇİSİ DEĞİL: keep-alive KOŞULSUZ DEĞİL — hiçbir bobin
                # çalışmıyorken paket gönderilmez (`hardware_controller._tick`: `need_send =
                # any_running or ...`) ve firmware de ilk paketten sonra ping'i keser. Yani BOŞTA
                # UART tamamen sessizdir; "N saniyedir satır gelmedi" kuralı boşta YANLIŞ tetikler.
                # Port varlığı ise kesin bir ölçüttür: USB çekilince COM portu numaralandırmadan
                # DÜŞER. Böylece hiçbir yazma/okuma denemesi olmadan da kopuş ANINDA görülür ve
                # bobinler arayüzde offline'a döner (sahip talebi 2026-09-11).
                if _conn is not None and (now - last_port_check > _PORT_CHECK_S):
                    last_port_check = now
                    if not transport.port_hala_var(getattr(_conn, "port", None)):
                        # ⚠️ D1.19 inceleme (r4): ÖNCE durum geçişleri, SONRA bildirim — ve bildirim döngüyü
                        # öldüremez. Eskiden çıplak uyarı geçişlerden önceydi: fırlatırsa HWSender ölür, kopuş
                        # bildirilmez (bayat "bağlı"), yeniden bağlanma olmaz, kuyruktaki STOP yazılmazdı.
                        _kaybolan_port = getattr(_conn, "port", "?")
                        if baglanti.aktif() is _conn:
                            baglanti.gecersizle()
                        self._set_stm_connected(False)
                        try:
                            transport.close_serial(_conn)
                        except Exception:
                            pass
                        with payload_lock:
                            last_payload[0] = None  # kopuk hatta BAYAT paketi tekrar oynatma
                        _conn = None
                        dongu_hatasini_bildir(
                            "[STM32] Seri port kayboldu (%s) → bağlantı düşürülüyor, bobinler çevrimdışı.",
                            _kaybolan_port,
                            logger=self.logger,
                            seviye=logging.WARNING,
                            exc_info=False,
                        )

                _reconnecting = reconnect_thread is not None and reconnect_thread.is_alive()
                _kopuk = _conn is None or not _conn.is_open
                if _kopuk and not _reconnecting and (now - last_reconnect_time > 3.0):
                    last_reconnect_time = now
                    # NON-BLOCKING reconnect: `connect_serial()` handshake'i ~14 sn BLOKLAR →
                    # sender döngüsü + UDP/ESP komut yolu + kuyruk tüketimi o süre DONARDI.
                    # ⚠️ Yarış artık VARSAYIMLA değil KİMLİKLE çözülüyor: her reader kendi
                    # connection'ını ve nesil numarasını taşır, paylaşılan durumu yalnız hâlâ
                    # kendisininse temizler (bkz. `connect_serial`/`reader`).
                    reconnect_thread = threading.Thread(target=connect_serial, daemon=True, name="STM32Reconnect")
                    reconnect_thread.start()

                try:
                    payload_tuple = self._hw_send_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                _tekrar = 0
                if isinstance(payload_tuple, _NackTekrari):
                    # ⚠️ D1.72 (B-1.17): NACK yeniden oynatmasının kararı BURADA, tek tüketicide verilir. Eski RUN
                    # ancak (a) porta son yazılan paket hâlâ oysa (arada STOP ya da yeni komut YAZILMADIYSA ve bağlantı
                    # kopup paket düşürülmediyse) ve (b) kuyrukta daha yeni bir niyet BEKLEMİYORSA yeniden yazılır
                    # (tekrar sınırı işaret kurulurken `retry_last_payload`ta uygulanır). STOP (tüm duty 0) her
                    # koşulda yeniden yazılır — Ö.4-Y8: STOP'un yeniden gönderimi azaltılmaz.
                    _isaret = payload_tuple
                    if not _tum_duty_sifir_mi(_isaret.paket[0]):
                        with payload_lock:
                            _son_yazilan = last_payload[0]
                        if _son_yazilan is not _isaret.paket or not self._hw_send_queue.empty():
                            continue
                    payload_tuple, _tekrar = _isaret.paket, _isaret.tekrar

                stm_msg, udp_pkt, esp_ip, esp_port = payload_tuple
                _yaz_conn = _aktif_baglanti()
                if _yaz_conn is not None and _yaz_conn.is_open and stm_msg:
                    try:
                        with payload_lock:
                            last_payload[0] = payload_tuple
                            last_payload[1] = time.monotonic()
                            last_payload[2] = _tekrar
                        _yaz_conn.write(stm_msg if isinstance(stm_msg, bytes) else stm_msg.encode("utf-8"))
                    except Exception as exc:
                        # D1.19 (B-10.121): bildirim fırlatırsa HWSender ölür → sonraki STM paketleri (STOP dahil)
                        # "kuyruğa verildi" ama HİÇ yazılmaz (B-1.23 sahte teyidinin bir kaynağı).
                        dongu_hatasini_bildir(
                            "[STM32 SEND] %s", exc, logger=self.logger, seviye=logging.WARNING, exc_info=False
                        )
                        # Paylaşılan durumu YALNIZ hâlâ bu bağlantıysa düşür (araya yeni bir
                        # bağlantı girmiş olabilir — eski yazma hatası onu öldürmemeli).
                        _benim = baglanti.aktif() is _yaz_conn
                        if _benim:
                            baglanti.gecersizle()
                        if _benim:
                            self._set_stm_connected(False)
                        # DENETIM P2: port KAPATILMIYORDU. Yeniden-baglanma kosulu
                        # `not serial_conn or not serial_conn.is_open` oldugundan, yalnizca
                        # "baglanti koptu" BAYRAGINI dusurmek hicbir zaman reconnect tetiklemiyordu →
                        # USB yarim-kopmasinda (kablo gevsemesi/surucu hatasi) port sonsuza dek acik
                        # ama olu kaliyor, bobin komutlari sessizce kayboluyordu. Acikca kapat →
                        # dongu basindaki reconnect devreye girer. (Bu arada keep-alive kesildigi icin
                        # firmware olu-adam devresi 1.5 sn'de bobinleri sifirlar = fail-safe yon.)
                        try:
                            transport.close_serial(_yaz_conn)
                        except Exception:
                            pass
                        with payload_lock:
                            last_payload[0] = None  # kopuk baglantida BAYAT paketi tekrar oynatma
                    else:
                        # D1.55: yazım izi — E-stop "STOP porta YAZILDI" bilgisini buradan okur
                        # (`hw_stop_yazildi_bekle`). `else`: izin kendisi yazım hatası sayılmaz.
                        self._hw_yazimi_kaydet(stm_msg)

                if udp_sock and udp_pkt:
                    try:
                        udp_sock.sendto(udp_pkt, (esp_ip, esp_port))
                    except Exception as exc:
                        dongu_hatasini_bildir(
                            "[UDP SEND] %s", exc, logger=self.logger, seviye=logging.WARNING, exc_info=False
                        )
            except Exception:
                # ⚠️ D1.55 (B-1.23): TUR HATASI HWSender'I ÖLDÜREMEZ. Eskiden döngü gövdesi korumasızdı:
                # port yoklaması, kuyruk, paket çözme ya da yeniden bağlanma iş parçacığı başlatma (tükenme)
                # bir kez fırlatınca gönderici ÖLÜYOR, sonraki her paket (STOP dahil) "kuyruğa verildi"
                # sayılıp porta HİÇ yazılmıyordu. Tur atlanır (o turun paketi düşer — STOP'u
                # `STOP_RESEND_TICKS` telafi eder), kısa geri çekilmeyle döngü SÜRER.
                dongu_hatasini_bildir(
                    "[HWSender] tur hatasi — dongu SURUYOR (kuyruktaki STOP dahil paketler yazilmaya devam eder)",
                    logger=self.logger,
                )
                self._hw_sender_stop.wait(0.05)

        _son = baglanti.gecersizle()
        if _son is not None:
            try:
                transport.close_serial(_son)
            except Exception:
                pass
        if udp_sock:
            try:
                udp_sock.close()
            except Exception:
                pass

    def quit(self) -> None:
        """Clean up worker threads and optional legacy services."""
        self._publish_event("system.core.stopping", {})
        self._hw_sender_stop.set()
        if self._hw_sender_thread.is_alive():
            self._hw_sender_thread.join(timeout=2.0)

        if self.udp_discovery_service:
            try:
                self.udp_discovery_service.stop()
            except Exception:
                self.logger.exception("UDP discovery shutdown failed")

        if self.network_status_service:
            try:
                self.network_status_service.stop()
            except Exception:
                self.logger.exception("Network status service shutdown failed")

        if self.mosquitto_supervisor:
            try:
                self.mosquitto_supervisor.stop()
            except Exception:
                self.logger.exception("Mosquitto supervisor shutdown failed")

        self._set_stm_connected(False)
        self._publish_event("system.core.stopped", {})

    stop = quit

    def get_service_status(self) -> dict[str, Any]:
        """Return a snapshot of headless support services."""
        return {
            "stm": {"connected": self.stm_is_connected},
            "mosquitto": self.mosquitto_supervisor.get_status() if self.mosquitto_supervisor else {},
            "network": self.network_status_service.get_status() if self.network_status_service else {},
            "discovery": self.udp_discovery_service.get_status() if self.udp_discovery_service else {},
        }
