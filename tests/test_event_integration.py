# -*- coding: utf-8 -*-
"""
EventBus Integration Test
PEMF Medical System EventBus entegrasyonunu test eder

Bu test dosyası, EventBus'ın GUI bileşenleri ve WebSocket server
arasındaki gevşek bağlılığı nasıl sağladığını gösterir.

@author: merta
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any

from event_bus import get_event_bus, EventTypes, EventPriority, Event
from websocket_server_refactored import WebSocketServerRefactored
from gui_event_integration import PWMCommandHandler

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MockESPClient:
    """
    Test için mock ESP client
    
    Gerçek ESP cihazını simüle eder ve WebSocket server'a bağlanır.
    """
    
    def __init__(self, coil_id: str, server_host: str = "localhost", server_port: int = 8765):
        self.coil_id = coil_id
        self.server_host = server_host
        self.server_port = server_port
        self.websocket = None
        self.running = False
        
        # Mock sensor data
        self.temperature = 25.0
        self.humidity = 60.0
        self.pressure = 1013.25
    
    async def connect(self):
        """WebSocket server'a bağlan"""
        import websockets
        
        try:
            uri = f"ws://{self.server_host}:{self.server_port}"
            self.websocket = await websockets.connect(uri)
            self.running = True
            
            # İlk bağlantı mesajını gönder
            connection_message = {
                "type": "connection",
                "coil_id": self.coil_id,
                "ip": "192.168.1.100",  # Mock IP
                "timestamp": datetime.now().isoformat()
            }
            
            await self.websocket.send(json.dumps(connection_message))
            logger.info(f"Mock ESP {self.coil_id} connected to server")
            
            # Heartbeat ve data gönderme task'larını başlat
            await asyncio.gather(
                self._heartbeat_loop(),
                self._data_loop(),
                self._listen_loop()
            )
            
        except Exception as e:
            logger.error(f"Mock ESP {self.coil_id} connection failed: {e}")
            self.running = False
    
    async def _heartbeat_loop(self):
        """Heartbeat mesajları gönder"""
        while self.running:
            try:
                heartbeat_message = {
                    "type": "heartbeat",
                    "coil_id": self.coil_id,
                    "timestamp": datetime.now().isoformat()
                }
                
                await self.websocket.send(json.dumps(heartbeat_message))
                await asyncio.sleep(5)  # 5 saniyede bir heartbeat
                
            except Exception as e:
                logger.error(f"Mock ESP {self.coil_id} heartbeat error: {e}")
                break
    
    async def _data_loop(self):
        """Sensor data mesajları gönder"""
        while self.running:
            try:
                # Mock sensor data'yı güncelle (simülasyon)
                self.temperature += (time.time() % 10 - 5) * 0.1  # ±0.5°C variation
                self.humidity += (time.time() % 8 - 4) * 0.2      # ±0.8% variation
                self.pressure += (time.time() % 6 - 3) * 0.5      # ±1.5 hPa variation
                
                sensor_message = {
                    "type": "sensor_data",
                    "coil_id": self.coil_id,
                    "data": {
                        "temperature": round(self.temperature, 2),
                        "humidity": round(self.humidity, 2),
                        "pressure": round(self.pressure, 2)
                    },
                    "timestamp": datetime.now().isoformat()
                }
                
                await self.websocket.send(json.dumps(sensor_message))
                await asyncio.sleep(2)  # 2 saniyede bir sensor data
                
            except Exception as e:
                logger.error(f"Mock ESP {self.coil_id} data error: {e}")
                break
    
    async def _listen_loop(self):
        """Server'dan gelen mesajları dinle"""
        while self.running:
            try:
                message = await self.websocket.recv()
                logger.info(f"Mock ESP {self.coil_id} received: {message}")
                
                # PWM command'larını işle
                if "pwm" in message.lower():
                    ack_message = {
                        "type": "ack",
                        "coil_id": self.coil_id,
                        "message": "PWM command received",
                        "timestamp": datetime.now().isoformat()
                    }
                    await self.websocket.send(json.dumps(ack_message))
                
            except Exception as e:
                logger.error(f"Mock ESP {self.coil_id} listen error: {e}")
                break
    
    async def disconnect(self):
        """Bağlantıyı kapat"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
        logger.info(f"Mock ESP {self.coil_id} disconnected")


class EventBusTestMonitor:
    """
    EventBus test monitor
    
    Tüm event'leri dinler ve test sonuçlarını raporlar.
    """
    
    def __init__(self):
        self.event_bus = get_event_bus()
        self.received_events = []
        
        # Tüm event tiplerini dinle
        self.event_bus.subscribe("*", self._monitor_event, "test_monitor")
    
    def _monitor_event(self, event: Event):
        """Event'leri monitör et"""
        self.received_events.append({
            "type": event.event_type,
            "source": event.source,
            "timestamp": event.timestamp,
            "data": event.data
        })
        
        logger.info(f"EVENT MONITOR: {event.event_type} from {event.source}")
    
    def get_events_by_type(self, event_type: str) -> list:
        """Belirli tip event'leri getir"""
        return [e for e in self.received_events if e["type"] == event_type]
    
    def get_event_count(self) -> int:
        """Toplam event sayısını getir"""
        return len(self.received_events)
    
    def clear_events(self):
        """Event history'yi temizle"""
        self.received_events.clear()


async def test_event_bus_integration():
    """
    EventBus entegrasyonunu test et
    
    Bu test:
    1. WebSocket server'ı başlatır
    2. Mock ESP client'ları bağlar
    3. Event'lerin doğru şekilde yayınlandığını kontrol eder
    4. PWM command'larının çalıştığını test eder
    """
    
    logger.info("=== EventBus Integration Test Started ===")
    
    # Test monitor'ı başlat
    monitor = EventBusTestMonitor()
    
    # WebSocket server'ı başlat
    websocket_server = WebSocketServerRefactored()
    
    # PWM command handler'ı başlat
    pwm_handler = PWMCommandHandler(websocket_server)
    
    try:
        # Server'ı başlat
        logger.info("Starting WebSocket server...")
        await websocket_server.start()
        
        # Kısa bekleme
        await asyncio.sleep(1)
        
        # Mock ESP client'ları oluştur
        esp1 = MockESPClient("ESP001")
        esp2 = MockESPClient("ESP002")
        
        # ESP client'ları bağla (background task'lar olarak)
        logger.info("Connecting mock ESP clients...")
        esp1_task = asyncio.create_task(esp1.connect())
        esp2_task = asyncio.create_task(esp2.connect())
        
        # ESP'lerin bağlanması için bekle
        await asyncio.sleep(3)
        
        # Event'leri kontrol et
        logger.info("Checking events...")
        
        # ESP connection events
        connection_events = monitor.get_events_by_type(EventTypes.ESP_CONNECTED)
        assert len(connection_events) >= 2, f"Expected 2+ connection events, got {len(connection_events)}"
        logger.info(f"✓ ESP connection events: {len(connection_events)}")
        
        # ESP heartbeat events
        await asyncio.sleep(6)  # Heartbeat'lerin gelmesi için bekle
        heartbeat_events = monitor.get_events_by_type(EventTypes.ESP_HEARTBEAT)
        assert len(heartbeat_events) >= 2, f"Expected 2+ heartbeat events, got {len(heartbeat_events)}"
        logger.info(f"✓ ESP heartbeat events: {len(heartbeat_events)}")
        
        # ESP data events
        data_events = monitor.get_events_by_type(EventTypes.ESP_DATA_RECEIVED)
        assert len(data_events) >= 2, f"Expected 2+ data events, got {len(data_events)}"
        logger.info(f"✓ ESP data events: {len(data_events)}")
        
        # PWM command test
        logger.info("Testing PWM commands...")
        event_bus = get_event_bus()
        
        # PWM start command gönder
        await event_bus.publish_async(
            EventTypes.DATA_PWM_UPDATE,
            {
                "action": "start",
                "frequency": 1000,
                "duty_cycle": 75,
                "target": "all_esps"
            },
            source="test_client",
            priority=EventPriority.HIGH
        )
        
        await asyncio.sleep(2)  # Command'ın işlenmesi için bekle
        
        # PWM stop command gönder
        await event_bus.publish_async(
            EventTypes.DATA_PWM_UPDATE,
            {
                "action": "stop",
                "target": "ESP001"
            },
            source="test_client",
            priority=EventPriority.HIGH
        )
        
        await asyncio.sleep(2)
        
        # PWM events'leri kontrol et
        pwm_events = monitor.get_events_by_type(EventTypes.DATA_PWM_UPDATE)
        assert len(pwm_events) >= 2, f"Expected 2+ PWM events, got {len(pwm_events)}"
        logger.info(f"✓ PWM command events: {len(pwm_events)}")
        
        # Event statistics
        total_events = monitor.get_event_count()
        logger.info(f"✓ Total events processed: {total_events}")
        
        # EventBus statistics
        stats = event_bus.get_stats()
        logger.info(f"✓ EventBus stats: {stats}")
        
        logger.info("=== All tests passed! ===")
        
    except AssertionError as e:
        logger.error(f"Test failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Test error: {e}")
        raise
    finally:
        # Cleanup
        logger.info("Cleaning up...")
        
        # ESP client'ları durdur
        await esp1.disconnect()
        await esp2.disconnect()
        
        # Server'ı durdur
        await websocket_server.stop()
        
        # Task'ları iptal et
        esp1_task.cancel()
        esp2_task.cancel()
        
        logger.info("Cleanup completed")


async def test_loose_coupling():
    """
    Gevşek bağlılığı test et
    
    Bu test, GUI bileşenlerinin WebSocket server'a doğrudan bağlı olmadığını
    ve sadece event'ler üzerinden iletişim kurduğunu gösterir.
    """
    
    logger.info("=== Loose Coupling Test Started ===")
    
    event_bus = get_event_bus()
    monitor = EventBusTestMonitor()
    
    # Mock GUI component
    class MockGUIComponent:
        def __init__(self, name: str):
            self.name = name
            self.received_events = []
            
            # Event'leri dinle
            event_bus.subscribe(
                EventTypes.ESP_CONNECTED,
                self._handle_esp_connected,
                self.name
            )
            
            event_bus.subscribe(
                EventTypes.ESP_DATA_RECEIVED,
                self._handle_esp_data,
                self.name
            )
        
        def _handle_esp_connected(self, event: Event):
            self.received_events.append(("esp_connected", event.data))
            logger.info(f"{self.name}: ESP connected - {event.data['coil_id']}")
        
        def _handle_esp_data(self, event: Event):
            self.received_events.append(("esp_data", event.data))
            logger.info(f"{self.name}: ESP data - {event.data['coil_id']}")
        
        def send_pwm_command(self, action: str, target: str = "all_esps"):
            """PWM command gönder (WebSocket server'a doğrudan bağlı değil)"""
            event_bus.publish(
                EventTypes.DATA_PWM_UPDATE,
                {
                    "action": action,
                    "target": target,
                    "source_component": self.name
                },
                source=self.name
            )
    
    # Mock GUI bileşenlerini oluştur
    main_window = MockGUIComponent("main_window")
    pwm_control = MockGUIComponent("pwm_control")
    data_viz = MockGUIComponent("data_visualization")
    
    # Mock event'ler gönder (WebSocket server olmadan)
    logger.info("Sending mock events...")
    
    # ESP connection event
    await event_bus.publish_async(
        EventTypes.ESP_CONNECTED,
        {
            "coil_id": "ESP001",
            "ip": "192.168.1.100"
        },
        source="mock_websocket_server"
    )
    
    # ESP data event
    await event_bus.publish_async(
        EventTypes.ESP_DATA_RECEIVED,
        {
            "coil_id": "ESP001",
            "sensor_data": {
                "temperature": 25.5,
                "humidity": 62.3,
                "pressure": 1013.25
            }
        },
        source="mock_websocket_server"
    )
    
    await asyncio.sleep(1)  # Event'lerin işlenmesi için bekle
    
    # GUI bileşenlerinin event'leri aldığını kontrol et
    assert len(main_window.received_events) == 2, "Main window should receive 2 events"
    assert len(pwm_control.received_events) == 2, "PWM control should receive 2 events"
    assert len(data_viz.received_events) == 2, "Data viz should receive 2 events"
    
    logger.info("✓ All GUI components received events independently")
    
    # PWM command test (WebSocket server olmadan)
    pwm_control.send_pwm_command("start")
    
    await asyncio.sleep(1)
    
    # PWM event'inin yayınlandığını kontrol et
    pwm_events = monitor.get_events_by_type(EventTypes.DATA_PWM_UPDATE)
    assert len(pwm_events) >= 1, "PWM command should be published"
    
    logger.info("✓ PWM command sent without direct WebSocket dependency")
    
    logger.info("=== Loose Coupling Test Passed! ===")


if __name__ == "__main__":
    async def run_all_tests():
        """Tüm testleri çalıştır"""
        try:
            # Test 1: EventBus integration
            await test_event_bus_integration()
            
            # Test 2: Loose coupling
            await test_loose_coupling()
            
            logger.info("🎉 ALL TESTS PASSED! 🎉")
            logger.info("EventBus successfully provides loose coupling between components")
            
        except Exception as e:
            logger.error(f"❌ TESTS FAILED: {e}")
            raise
    
    # Test'leri çalıştır
    asyncio.run(run_all_tests())