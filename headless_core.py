from __future__ import annotations

import logging
import queue
import re
import socket
import threading
import time
from pathlib import Path
from queue import Queue
from typing import Any, Callable

from database.patient_database import get_patient_database
from database.session_manager import get_session_manager
from event_bus import EventPriority, get_event_bus
from services.headless_services import MosquittoSupervisor, NetworkStatusService, UdpDiscoveryService
from utils.simple_signal import SimpleSignal
from utils.stm32_transport import Stm32SerialTransport

# STM_NACK sonrasi ham-paket tekrar oynatma icin AZAMI YAS (sn). Keep-alive turundan
# (0.5 sn) biraz genis tutuldu; daha eskisi 'guncel niyet' sayilmaz.
_RETRY_MAX_AGE_S = 0.75


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
        self._stm_state_lock = threading.RLock()
        self.stm_connected_signal.connect(self._on_stm_connected_slot)

        self.patient_db = get_patient_database(self.app_data_dir)
        self.session_manager = get_session_manager(self.app_data_dir)

        self.mosquitto_supervisor = None
        self.network_status_service = None
        self.udp_discovery_service = None
        if start_headless_services:
            self.start_headless_services(ensure_mosquitto=ensure_mosquitto)

        self._hw_send_queue: Queue = Queue(maxsize=4)
        self._hw_sender_stop = threading.Event()
        self._hw_sender_thread = threading.Thread(
            target=self._hw_sender_worker,
            daemon=True,
            name="HWSender",
        )
        self._hw_sender_thread.start()
        self._publish_event("system.core.started", {"appDataDir": str(self.app_data_dir)})

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

    def _on_stm_connected_slot(self, is_connected: bool) -> None:
        with self._stm_state_lock:
            self.stm_is_connected = bool(is_connected)
        self.logger.info("STM32 connection state updated: %s", self.stm_is_connected)
        self._publish_event(
            "hardware.stm.connected" if is_connected else "hardware.stm.disconnected",
            {"connected": bool(is_connected)},
            priority=EventPriority.HIGH,
        )

    def _parse_stm_ok(self, decoded: str) -> list[dict[str, Any]]:
        num = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
        vals = rf"({num}(?:,{num})*)"
        match = re.search(rf"D={vals}\s+P={vals}\s+F={vals}\s+T={vals}", decoded)
        if not match:
            return []

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
            return

        if "STM_ERR" in decoded:
            self._publish_event(
                "hardware.stm.error",
                {"message": decoded},
                priority=EventPriority.HIGH,
            )

    def _hw_sender_worker(self) -> None:
        udp_sock = None
        # [0]=son yazilan paket, [1]=yazildigi monotonic an (bkz. retry_last_payload yas siniri)
        # ⚠️ `payload_lock` ile korunur: reader thread'i (retry_last_payload) okur, sender yazar.
        last_payload: list[Any] = [None, 0.0]
        payload_lock = threading.Lock()
        last_reconnect_time = 0.0
        transport = Stm32SerialTransport(self.logger)

        # ⚠️ Seri bağlantı PAYLAŞILAN durumdur: sender (bu thread), reader ve reconnect
        # thread'leri birlikte erişir. `nesil`, eski bir reader'ın YENİ bağlantıyı
        # kapatmasını engelleyen kimlik damgasıdır (bkz. connect_serial gerekçesi).
        baglanti = SeriBaglantiDurumu()

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
            with payload_lock:
                payload, ts = last_payload[0], last_payload[1]
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
            try:
                self._hw_send_queue.put_nowait(payload)
                with payload_lock:
                    if last_payload[0] is payload:
                        last_payload[0] = None
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
                        self.logger.warning("[STM32 READER] %s", exc)
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

        connect_serial()

        try:
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception as exc:
            self.logger.warning("[UDP] Socket open failed: %s", exc)
            udp_sock = None

        reconnect_thread = None  # tek eşzamanlı non-blocking reconnect
        last_port_check = 0.0  # kablo-çıktı yoklamasının son anı (monotonic)
        while not self._hw_sender_stop.is_set():
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
                    self.logger.warning(
                        "[STM32] Seri port kayboldu (%s) → bağlantı düşürülüyor, bobinler çevrimdışı.",
                        getattr(_conn, "port", "?"),
                    )
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

            stm_msg, udp_pkt, esp_ip, esp_port = payload_tuple
            _yaz_conn = _aktif_baglanti()
            if _yaz_conn is not None and _yaz_conn.is_open and stm_msg:
                try:
                    with payload_lock:
                        last_payload[0] = payload_tuple
                        last_payload[1] = time.monotonic()
                    _yaz_conn.write(stm_msg if isinstance(stm_msg, bytes) else stm_msg.encode("utf-8"))
                except Exception as exc:
                    self.logger.warning("[STM32 SEND] %s", exc)
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

            if udp_sock and udp_pkt:
                try:
                    udp_sock.sendto(udp_pkt, (esp_ip, esp_port))
                except Exception as exc:
                    self.logger.warning("[UDP SEND] %s", exc)

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
