"""
BLE Provisioner Service - ESP32-S3 cihazlarını BLE üzerinden toplu yapılandırır.

LattePanda gateway kurulumunda:
- ESP'lere WiFi SSID/şifre gönderir (PEMF-Gateway hotspot)
- MQTT broker IP/port bilgisi gönderir (local Mosquitto)
- Cihaz keşfi ve durumu takip eder

Gerekli paket: pip install bleak
BLE UUID'leri: SharedDefs.h ile uyumlu
"""

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
from typing import Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal

logger = logging.getLogger(__name__)

# BLE UUIDs (SharedDefs.h ile uyumlu)
BLE_SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
BLE_CHAR_COMMAND_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"    # Command (START/STOP/SET_PARAMS/UPDATE_FIRMWARE)
BLE_CHAR_WIFI_SSID_UUID = "c6f6696d-74d3-469a-8b3d-71b569502928"  # WiFi SSID
BLE_CHAR_WIFI_PASS_UUID = "4466b8d7-06c8-47e9-a76f-22a912c9bf13"  # WiFi password
BLE_CHAR_MQTT_CFG_UUID = "d3a2f8e1-94b7-4c6e-b0d5-7e8f1a2b3c4d"  # MQTT broker config

# Firmware ile ayni anahtar olmali (Secrets.h -> DEFAULT_BLE_CMD_HMAC_KEY)
DEFAULT_BLE_HMAC_KEY = "PEMF_CHANGE_THIS_HMAC_KEY_2026"

# Default provisioning config
DEFAULT_WIFI_SSID = "PEMF-Gateway"
DEFAULT_WIFI_PASS = "pemf2024gateway"
DEFAULT_MQTT_HOST = "192.168.137.1"
DEFAULT_MQTT_PORT = 1883


class BLEProvisionerWorker(QObject):
    """
    BLE üzerinden ESP32 cihazlarını yapılandıran worker.
    QThread içinde çalıştırılır, async BLE (bleak) işlemleri yapar.
    """

    # Signals
    scan_started = pyqtSignal()
    scan_finished = pyqtSignal()
    device_found = pyqtSignal(str, str)  # address, name
    provision_started = pyqtSignal(str)  # address
    provision_progress = pyqtSignal(str, str)  # address, step_description
    provision_success = pyqtSignal(str)  # address
    provision_failed = pyqtSignal(str, str)  # address, error_message
    command_sent = pyqtSignal(str, str)  # address, command_name
    command_failed = pyqtSignal(str, str)  # address, error_message
    all_done = pyqtSignal(int, int)  # success_count, fail_count
    error_occurred = pyqtSignal(str)  # error_message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wifi_ssid = DEFAULT_WIFI_SSID
        self._wifi_pass = DEFAULT_WIFI_PASS
        self._mqtt_host = DEFAULT_MQTT_HOST
        self._mqtt_port = DEFAULT_MQTT_PORT
        self._scan_timeout = 10.0  # seconds
        self._target_addresses: list[str] = []  # Empty = all found devices
        self._ble_hmac_key = DEFAULT_BLE_HMAC_KEY

    def set_wifi_config(self, ssid: str, password: str):
        """WiFi yapılandırmasını ayarla."""
        self._wifi_ssid = ssid
        self._wifi_pass = password

    def set_mqtt_config(self, host: str, port: int = 1883):
        """MQTT broker yapılandırmasını ayarla."""
        self._mqtt_host = host
        self._mqtt_port = port

    def set_target_devices(self, addresses: list[str]):
        """Hedef cihaz adreslerini ayarla. Boş = tüm PEMF cihazları."""
        self._target_addresses = addresses

    def set_ble_hmac_key(self, key: str):
        """BLE komut imzalama anahtarını ayarla (firmware ile aynı olmalı)."""
        self._ble_hmac_key = key or DEFAULT_BLE_HMAC_KEY

    def _build_signed_command_payload(
        self,
        command: str,
        freq: int = 0,
        duty: int = 0,
        duration: int = 0,
        start_at: int = 0,
    ) -> bytes:
        """
        Firmware'deki signing formati ile birebir HMAC üretir:
        command|freq|duty|duration|start_at|nonce
        """
        nonce = secrets.token_hex(8)
        cmd_upper = (command or "").upper()
        signing_data = f"{cmd_upper}|{int(freq)}|{int(duty)}|{int(duration)}|{int(start_at)}|{nonce}"
        digest = hmac.new(
            self._ble_hmac_key.encode("utf-8"),
            signing_data.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        payload = {
            "command": cmd_upper,
            "freq": int(freq),
            "duty": int(duty),
            "duration": int(duration),
            "start_at": int(start_at),
            "nonce": nonce,
            "hmac": digest,
        }
        return json.dumps(payload, ensure_ascii=True).encode("utf-8")

    def run_scan(self):
        """ESP32-S3 PEMF cihazları için BLE tarama başlat."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._async_scan())
            loop.close()
        except ImportError:
            self.error_occurred.emit("bleak paketi yüklü değil. 'pip install bleak' komutunu çalıştırın.")
        except Exception as e:
            self.error_occurred.emit(f"BLE tarama hatası: {e}")

    def run_provision(self):
        """Bulunan/hedef cihazları yapılandır."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._async_provision_all())
            loop.close()
        except ImportError:
            self.error_occurred.emit("bleak paketi yüklü değil. 'pip install bleak' komutunu çalıştırın.")
        except Exception as e:
            self.error_occurred.emit(f"BLE provisioning hatası: {e}")

    async def _async_scan(self):
        """Async BLE tarama."""
        from bleak import BleakScanner

        self.scan_started.emit()
        logger.info(f"BLE tarama başlatılıyor ({self._scan_timeout}s)...")

        try:
            devices = await BleakScanner.discover(timeout=self._scan_timeout)
        except Exception as e:
            err_str = str(e)
            if "2147020577" in err_str or "kullanıma hazır değil" in err_str:
                self.error_occurred.emit("Bluetooth adaptörü kapalı. Lütfen Windows ayarlarından Bluetooth'u açın.")
            else:
                self.error_occurred.emit(f"BLE tarama hatası: {e}")
            self.scan_finished.emit()
            return
        pemf_devices = []

        for device in devices:
            name = device.name or ""
            # PEMF ESP32 cihazları "PEMF_Coil_X" veya "ESP32" ismiyle yayın yapar
            if "PEMF" in name.upper() or "ESP32" in name.upper():
                pemf_devices.append(device)
                self.device_found.emit(device.address, name)
                logger.info(f"PEMF cihazı bulundu: {name} ({device.address})")

        logger.info(f"BLE tarama tamamlandı: {len(pemf_devices)} PEMF cihazı bulundu")
        self.scan_finished.emit()

    async def _async_provision_all(self):
        """Tüm hedef cihazları sırayla yapılandır."""
        from bleak import BleakScanner

        # Önce tarama yap
        self.scan_started.emit()
        try:
            devices = await BleakScanner.discover(timeout=self._scan_timeout)
        except Exception as e:
            err_str = str(e)
            if "2147020577" in err_str or "kullanıma hazır değil" in err_str:
                self.error_occurred.emit("Bluetooth adaptörü kapalı. Lütfen Windows ayarlarından Bluetooth'u açın.")
            else:
                self.error_occurred.emit(f"BLE tarama hatası: {e}")
            self.scan_finished.emit()
            self.all_done.emit(0, 0)
            return
        self.scan_finished.emit()

        # PEMF cihazlarını filtrele
        pemf_devices = []
        for device in devices:
            name = device.name or ""
            if "PEMF" in name.upper() or "ESP32" in name.upper():
                # Target listesi varsa sadece onları al
                if self._target_addresses and device.address not in self._target_addresses:
                    continue
                pemf_devices.append(device)
                self.device_found.emit(device.address, name)

        if not pemf_devices:
            self.error_occurred.emit("Hiç PEMF cihazı bulunamadı!")
            self.all_done.emit(0, 0)
            return

        success_count = 0
        fail_count = 0

        for device in pemf_devices:
            ok = await self._provision_device(device.address, device.name or "Unknown")
            if ok:
                success_count += 1
            else:
                fail_count += 1
            # Cihazlar arası bekleme (BLE stability)
            await asyncio.sleep(2.0)

        self.all_done.emit(success_count, fail_count)
        logger.info(f"Provisioning tamamlandı: {success_count} başarılı, {fail_count} başarısız")

    async def _provision_device(self, address: str, name: str) -> bool:
        """Tek bir ESP32 cihazını BLE üzerinden yapılandır."""
        from bleak import BleakClient

        self.provision_started.emit(address)
        logger.info(f"Provisioning başlatılıyor: {name} ({address})")

        try:
            async with BleakClient(address, timeout=15.0) as client:
                if not client.is_connected:
                    self.provision_failed.emit(address, "BLE bağlantısı kurulamadı")
                    return False

                # Step 1: MQTT broker yapılandırması gönder (Önce bu gönderilmeli, PASS gidince bağ kopar)
                self.provision_progress.emit(address, "MQTT broker yapılandırması gönderiliyor...")
                mqtt_data = json.dumps({
                    "target": "local",
                    "host": self._mqtt_host,
                    "port": self._mqtt_port,
                }).encode('utf-8')

                try:
                    await client.write_gatt_char(BLE_CHAR_MQTT_CFG_UUID, mqtt_data, response=True)
                    logger.info(f"  [{name}] MQTT config gönderildi: {self._mqtt_host}:{self._mqtt_port}")
                except Exception as e:
                    logger.warning(f"  [{name}] MQTT config yazılamadı, atlanıyor: {e}")

                await asyncio.sleep(0.5)

                # Step 2: WiFi yapılandırması gönder
                self.provision_progress.emit(address, "WiFi yapılandırması gönderiliyor...")
                try:
                    await client.write_gatt_char(BLE_CHAR_WIFI_SSID_UUID, self._wifi_ssid.encode('utf-8'), response=True)
                    await asyncio.sleep(0.5)
                    await client.write_gatt_char(BLE_CHAR_WIFI_PASS_UUID, self._wifi_pass.encode('utf-8'), response=True)
                    logger.info(f"  [{name}] WiFi SSID/PASS gönderildi: SSID={self._wifi_ssid}")
                except Exception as e:
                    err_str = str(e)
                    # Eğer ESP32 biz daha ACK almadan BLE'yi kapatıp Wi-Fi'a geçerse bu hatalar döner, başarılı saymalıyız.
                    if "2147023673" in err_str or "Unreachable" in err_str or "Not connected" in err_str or "Abort" in err_str:
                        logger.warning(f"  [{name}] ACK tam alınamadı ama ESP yapılandırmayı aldı (BLE kapandı). Başarılı kabul ediliyor: {err_str}")
                    else:
                        self.provision_failed.emit(address, f"WiFi config yazma hatası: {e}")
                        return False

                await asyncio.sleep(1.0)

                self.provision_success.emit(address)
                logger.info(f"  [{name}] Provisioning başarılı!")
                return True

        except Exception as e:
            self.provision_failed.emit(address, str(e))
            logger.error(f"  [{name}] Provisioning hatası: {e}")
            return False

    async def send_signed_command(
        self,
        address: str,
        command: str,
        freq: int = 0,
        duty: int = 0,
        duration: int = 0,
        start_at: int = 0,
    ) -> bool:
        """BLE komut karakteristiğine imzalı komut gönderir (HMAC-SHA256)."""
        from bleak import BleakClient

        payload = self._build_signed_command_payload(
            command=command,
            freq=freq,
            duty=duty,
            duration=duration,
            start_at=start_at,
        )

        try:
            async with BleakClient(address, timeout=15.0) as client:
                if not client.is_connected:
                    self.command_failed.emit(address, "BLE bağlantısı kurulamadı")
                    return False

                await client.write_gatt_char(BLE_CHAR_COMMAND_UUID, payload, response=True)
                self.command_sent.emit(address, command.upper())
                logger.info(f"  [{address}] Signed BLE command gönderildi: {command.upper()}")
                return True
        except Exception as e:
            self.command_failed.emit(address, str(e))
            logger.error(f"  [{address}] Signed BLE command hatası: {e}")
            return False


class BLEProvisionerThread(QThread):
    """
    BLE provisioner'ı ayrı bir thread'de çalıştırır.
    Worker sinyallerini dışarıya iletir.
    """

    # Forward signals from worker
    scan_started = pyqtSignal()
    scan_finished = pyqtSignal()
    device_found = pyqtSignal(str, str)
    provision_started = pyqtSignal(str)
    provision_progress = pyqtSignal(str, str)
    provision_success = pyqtSignal(str)
    provision_failed = pyqtSignal(str, str)
    command_sent = pyqtSignal(str, str)
    command_failed = pyqtSignal(str, str)
    all_done = pyqtSignal(int, int)
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "scan"  # "scan" or "provision"
        self._worker = BLEProvisionerWorker()
        self._command_args: Optional[dict] = None

        # Connect worker signals to thread signals
        self._worker.scan_started.connect(self.scan_started)
        self._worker.scan_finished.connect(self.scan_finished)
        self._worker.device_found.connect(self.device_found)
        self._worker.provision_started.connect(self.provision_started)
        self._worker.provision_progress.connect(self.provision_progress)
        self._worker.provision_success.connect(self.provision_success)
        self._worker.provision_failed.connect(self.provision_failed)
        self._worker.command_sent.connect(self.command_sent)
        self._worker.command_failed.connect(self.command_failed)
        self._worker.all_done.connect(self.all_done)
        self._worker.error_occurred.connect(self.error_occurred)

    @property
    def worker(self) -> BLEProvisionerWorker:
        return self._worker

    def start_scan(self):
        """BLE tarama modu ile başlat."""
        self._mode = "scan"
        self.start()

    def start_provision(self):
        """Provisioning modu ile başlat."""
        self._mode = "provision"
        self.start()

    def start_send_signed_command(
        self,
        address: str,
        command: str,
        freq: int = 0,
        duty: int = 0,
        duration: int = 0,
        start_at: int = 0,
    ):
        """Imzali BLE komut gonderim modunu baslat."""
        self._mode = "command"
        self._command_args = {
            "address": address,
            "command": command,
            "freq": freq,
            "duty": duty,
            "duration": duration,
            "start_at": start_at,
        }
        self.start()

    def run(self):
        """Thread çalışma metodu."""
        if self._mode == "scan":
            self._worker.run_scan()
        elif self._mode == "command":
            if not self._command_args:
                self.error_occurred.emit("Komut parametreleri eksik")
                return
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    self._worker.send_signed_command(
                        address=self._command_args["address"],
                        command=self._command_args["command"],
                        freq=self._command_args["freq"],
                        duty=self._command_args["duty"],
                        duration=self._command_args["duration"],
                        start_at=self._command_args["start_at"],
                    )
                )
                loop.close()
            except Exception as e:
                self.error_occurred.emit(f"BLE signed command hatası: {e}")
        else:
            self._worker.run_provision()
