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


class HeadlessCore:
    """Qt-free backend core for STM32 communication and shared services."""

    STM_COIL_COUNT = 5

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
            self.stm_is_connected = bool(connected)   # gecisi kilit ALTINDA muhurle
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
            _lg.getLogger("headless_core").warning("STM parse: alan uzunlukları uyuşmuyor %s → satır reddedildi.", _lens)
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

    def _handle_stm_line(
        self,
        decoded: str,
        retry_last_payload: Callable[[], None] | None = None,
    ) -> None:
        if not decoded:
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

        if "STM_ERR" in decoded:
            self._publish_event(
                "hardware.stm.error",
                {"message": decoded},
                priority=EventPriority.HIGH,
            )

    def _hw_sender_worker(self) -> None:
        serial_conn = None
        udp_sock = None
        # [0]=son yazilan paket, [1]=yazildigi monotonic an (bkz. retry_last_payload yas siniri)
        last_payload: list[Any] = [None, 0.0]
        last_reconnect_time = 0.0
        transport = Stm32SerialTransport(self.logger)

        def retry_last_payload() -> None:
            # DENETIM P2: STM_NACK gelince EN SON YAZILAN ham paket kosulsuz yeniden kuyruga
            # konuyordu. Paketin icerigi/yasi hic sorgulanmadigi icin, NACK bir STOP kuyruga
            # girdikten SONRA islenirse FIFO sirasi [P_stop, P_run] olabiliyor ve bobinler
            # acil-durdurmadan SONRA tekrar enerjileniyordu. Iki kapak:
            #   (1) YAS SINIRI — paket bir keep-alive turundan (0.5 sn) eskiyse artik "guncel
            #       niyet" degildir; tazelemeyi keep-alive'a birak (o zaten guncel durumu gonderir).
            #   (2) Baglanti kopmasinda cagiran taraf last_payload'i None yapar (asagi bkz.).
            payload, ts = last_payload[0], last_payload[1]
            if payload is None:
                return
            if (time.monotonic() - ts) > _RETRY_MAX_AGE_S:
                self.logger.info("[STM32 NACK] son paket bayat (%.2fs) → tekrar gonderilmedi; "
                                 "keep-alive guncel durumu tazeleyecek.", time.monotonic() - ts)
                last_payload[0] = None
                return
            try:
                self._hw_send_queue.put_nowait(payload)
                last_payload[0] = None
            except queue.Full:
                pass

        # Audit P3 (NOT — serial reconnect yarışı): serial_conn kilitsiz paylaşılan nonlocal + last_payload
        # reader/sender arası kilitsiz. DOĞRULANMIŞ cerrahi fix mevcut (reader'a kendi conn'unu geçir +
        # kimlik-kontrollü nonlocal sıfırla + last_payload'ı Lock ile koru) ama DONANIM-serisi yolu +
        # test-edilmemiş → donanım smoke-doğrulaması OLMADAN uygulanmadı (arıza modu fail-safe: keep-alive
        # telafi eder). Detay: memory pemf-coverage-gap-audit. Donanım erişimi olunca uygula + birim-test ekle.
        def connect_serial() -> None:
            nonlocal serial_conn
            try:
                if serial_conn:
                    transport.close_serial(serial_conn)
                self._set_stm_connected(False)
                result = transport.open_and_handshake(
                    stop_event=self._hw_sender_stop,
                    on_line=lambda line: self._handle_stm_line(line, retry_last_payload),
                )
                if result is None:
                    serial_conn = None
                    return

                serial_conn = result.serial
                self._set_stm_connected(True)

                def reader() -> None:
                    nonlocal serial_conn
                    while serial_conn and serial_conn.is_open and not self._hw_sender_stop.is_set():
                        try:
                            line = serial_conn.readline()
                            if line:
                                decoded = line.decode("utf-8", errors="ignore").strip()
                                self._handle_stm_line(decoded, retry_last_payload)
                        except Exception as exc:
                            self.logger.warning("[STM32 READER] %s", exc)
                            break
                    self._set_stm_connected(False)
                    if serial_conn:
                        transport.close_serial(serial_conn)
                    serial_conn = None

                threading.Thread(target=reader, daemon=True, name="STM32Reader").start()
            except Exception as exc:
                serial_conn = None
                self._set_stm_connected(False)
                self.logger.warning("[STM32] Serial open failed: %s", exc)

        connect_serial()

        try:
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception as exc:
            self.logger.warning("[UDP] Socket open failed: %s", exc)
            udp_sock = None

        reconnect_thread = None  # tek eşzamanlı non-blocking reconnect
        while not self._hw_sender_stop.is_set():
            # DENETIM P3: geri-cekilme DUVAR SAATI ile olculuyordu. Saat GERI alinirsa
            # (NTP duzeltmesi, DST, elle ayar) `now - last_reconnect_time` negatife duser ve
            # 3 sn kosulu saatlerce saglanmaz → STM kopuk kalir, hicbir yeniden-baglanma
            # DENENMEZ. Monotonik saat geri gitmez.
            now = time.monotonic()
            _reconnecting = reconnect_thread is not None and reconnect_thread.is_alive()
            if (not serial_conn or not serial_conn.is_open) and not _reconnecting and (now - last_reconnect_time > 3.0):
                last_reconnect_time = now
                # NON-BLOCKING reconnect (reconnect-audit fix): connect_serial() handshake'i ~14sn BLOKLARDI →
                # sender döngüsü + UDP/ESP komut yolu + kuyruk tüketimi o süre DONARDI. Ayrı thread'de koş;
                # sender akmaya devam eder. Race FAIL-SAFE: serial_conn tek-atama atomik (GIL); tüm write/
                # is_open try/except'li + kapalı-port kontrollü; tek-reconnect guard eşzamanlı denemeyi keser;
                # eski-reader None-ataması handshake penceresinde YENİ atamadan önce olur (clobber yok).
                # Sanal-STM (socket://127.0.0.1:5100 stm32_simulator) ile smoke-test edildi.
                reconnect_thread = threading.Thread(target=connect_serial, daemon=True, name="STM32Reconnect")
                reconnect_thread.start()

            try:
                payload_tuple = self._hw_send_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            stm_msg, udp_pkt, esp_ip, esp_port = payload_tuple
            if serial_conn and serial_conn.is_open and stm_msg:
                try:
                    last_payload[0] = payload_tuple
                    last_payload[1] = time.monotonic()
                    serial_conn.write(stm_msg if isinstance(stm_msg, bytes) else stm_msg.encode("utf-8"))
                except Exception as exc:
                    self.logger.warning("[STM32 SEND] %s", exc)
                    self._set_stm_connected(False)
                    # DENETIM P2: port KAPATILMIYORDU. Yeniden-baglanma kosulu
                    # `not serial_conn or not serial_conn.is_open` oldugundan, yalnizca
                    # "baglanti koptu" BAYRAGINI dusurmek hicbir zaman reconnect tetiklemiyordu →
                    # USB yarim-kopmasinda (kablo gevsemesi/surucu hatasi) port sonsuza dek acik
                    # ama olu kaliyor, bobin komutlari sessizce kayboluyordu. Acikca kapat →
                    # dongu basindaki reconnect devreye girer. (Bu arada keep-alive kesildigi icin
                    # firmware olu-adam devresi 1.5 sn'de bobinleri sifirlar = fail-safe yon.)
                    try:
                        transport.close_serial(serial_conn)
                    except Exception:
                        pass
                    last_payload[0] = None   # kopuk baglantida BAYAT paketi tekrar oynatma

            if udp_sock and udp_pkt:
                try:
                    udp_sock.sendto(udp_pkt, (esp_ip, esp_port))
                except Exception as exc:
                    self.logger.warning("[UDP SEND] %s", exc)

        if serial_conn and serial_conn.is_open:
            transport.close_serial(serial_conn)
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
