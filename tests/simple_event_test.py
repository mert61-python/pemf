# -*- coding: utf-8 -*-
"""
Simple EventBus Test
EventBus'ın temel işlevselliğini test eder

@author: merta
"""

import asyncio
import logging
from datetime import datetime

from event_bus import get_event_bus, EventTypes, EventPriority, Event

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleEventListener:
    """Basit event listener"""
    
    def __init__(self, name: str):
        self.name = name
        self.received_events = []
        self.event_bus = get_event_bus()
        
        # Event'leri dinle
        self.event_bus.subscribe(
            EventTypes.ESP_CONNECTED,
            self._handle_esp_connected,
            self.name
        )
        
        self.event_bus.subscribe(
            EventTypes.ESP_DATA_RECEIVED,
            self._handle_esp_data,
            self.name
        )
        
        self.event_bus.subscribe(
            EventTypes.DATA_PWM_UPDATE,
            self._handle_pwm_update,
            self.name
        )
    
    def _handle_esp_connected(self, event: Event):
        """ESP connection event handler"""
        self.received_events.append(("esp_connected", event.data))
        logger.info(f"{self.name}: ESP connected - {event.data}")
    
    def _handle_esp_data(self, event: Event):
        """ESP data event handler"""
        self.received_events.append(("esp_data", event.data))
        logger.info(f"{self.name}: ESP data - {event.data}")
    
    def _handle_pwm_update(self, event: Event):
        """PWM update event handler"""
        self.received_events.append(("pwm_update", event.data))
        logger.info(f"{self.name}: PWM update - {event.data}")


async def test_basic_event_bus():
    """EventBus'ın temel işlevselliğini test et"""
    
    logger.info("=== Basic EventBus Test Started ===")
    
    event_bus = get_event_bus()
    
    # Event listener'ları oluştur
    listener1 = SimpleEventListener("listener1")
    listener2 = SimpleEventListener("listener2")
    
    # Event'leri yayınla
    logger.info("Publishing ESP connected event...")
    event_bus.publish(
        EventTypes.ESP_CONNECTED,
        {
            "coil_id": "ESP001",
            "ip": "192.168.1.100"
        },
        source="test_publisher"
    )
    
    # Kısa bekleme
    await asyncio.sleep(0.1)
    
    logger.info("Publishing ESP data event...")
    event_bus.publish(
        EventTypes.ESP_DATA_RECEIVED,
        {
            "coil_id": "ESP001",
            "sensor_data": {
                "temperature": 25.5,
                "humidity": 62.3
            }
        },
        source="test_publisher"
    )
    
    await asyncio.sleep(0.1)
    
    logger.info("Publishing PWM update event...")
    await event_bus.publish_async(
        EventTypes.DATA_PWM_UPDATE,
        {
            "action": "start",
            "frequency": 1000,
            "duty_cycle": 50
        },
        source="test_publisher",
        priority=EventPriority.HIGH
    )
    
    await asyncio.sleep(0.1)
    
    # Sonuçları kontrol et
    logger.info("Checking results...")
    
    # Listener1 sonuçları
    logger.info(f"Listener1 received {len(listener1.received_events)} events:")
    for event_type, data in listener1.received_events:
        logger.info(f"  - {event_type}: {data}")
    
    # Listener2 sonuçları
    logger.info(f"Listener2 received {len(listener2.received_events)} events:")
    for event_type, data in listener2.received_events:
        logger.info(f"  - {event_type}: {data}")
    
    # Assertions
    assert len(listener1.received_events) == 3, f"Listener1 should receive 3 events, got {len(listener1.received_events)}"
    assert len(listener2.received_events) == 3, f"Listener2 should receive 3 events, got {len(listener2.received_events)}"
    
    # Test statistics
    stats = event_bus.get_stats()
    logger.info(f"EventBus statistics: {stats}")
    
    logger.info("✓ Basic EventBus test passed!")


async def test_wildcard_events():
    """Wildcard event subscription'ı test et"""
    
    logger.info("=== Wildcard Events Test Started ===")
    
    event_bus = get_event_bus()
    
    # Wildcard listener
    wildcard_events = []
    
    def wildcard_handler(event: Event):
        wildcard_events.append((event.event_type, event.data))
        logger.info(f"Wildcard: {event.event_type} from {event.source}")
    
    # Tüm event'leri dinle
    event_bus.subscribe("*", wildcard_handler, "wildcard_listener")
    
    # ESP event'lerini dinle
    esp_events = []
    
    def esp_handler(event: Event):
        esp_events.append((event.event_type, event.data))
        logger.info(f"ESP: {event.event_type}")
    
    event_bus.subscribe("esp.*", esp_handler, "esp_listener")
    
    # Event'leri yayınla
    event_bus.publish(EventTypes.ESP_CONNECTED, {"coil_id": "ESP001"}, source="test")
    event_bus.publish(EventTypes.ESP_DISCONNECTED, {"coil_id": "ESP001"}, source="test")
    event_bus.publish(EventTypes.SYSTEM_STARTUP, {"component": "test"}, source="test")
    event_bus.publish(EventTypes.DATA_PWM_UPDATE, {"action": "start"}, source="test")
    
    await asyncio.sleep(0.1)
    
    # Sonuçları kontrol et
    logger.info(f"Wildcard listener received {len(wildcard_events)} events")
    logger.info(f"ESP listener received {len(esp_events)} events")
    
    assert len(wildcard_events) == 4, f"Wildcard should receive 4 events, got {len(wildcard_events)}"
    assert len(esp_events) == 2, f"ESP listener should receive 2 events, got {len(esp_events)}"
    
    logger.info("✓ Wildcard events test passed!")


async def test_event_priority():
    """Event priority'yi test et"""
    
    logger.info("=== Event Priority Test Started ===")
    
    event_bus = get_event_bus()
    
    # Event sırası
    event_order = []
    
    def high_priority_handler(event: Event):
        event_order.append("high")
        logger.info("High priority handler executed")
    
    def medium_priority_handler(event: Event):
        event_order.append("medium")
        logger.info("Medium priority handler executed")
    
    def low_priority_handler(event: Event):
        event_order.append("low")
        logger.info("Low priority handler executed")
    
    # Farklı priority'lerde subscription'lar
    event_bus.subscribe(
        EventTypes.ESP_CONNECTED,
        low_priority_handler,
        "low_listener",
        priority=EventPriority.LOW
    )
    
    event_bus.subscribe(
        EventTypes.ESP_CONNECTED,
        high_priority_handler,
        "high_listener",
        priority=EventPriority.HIGH
    )
    
    event_bus.subscribe(
        EventTypes.ESP_CONNECTED,
        medium_priority_handler,
        "medium_listener",
        priority=EventPriority.NORMAL
    )
    
    # Event yayınla
    event_bus.publish(
        EventTypes.ESP_CONNECTED,
        {"coil_id": "ESP001"},
        source="test",
        priority=EventPriority.HIGH
    )
    
    await asyncio.sleep(0.1)
    
    # Sırayı kontrol et (HIGH -> MEDIUM -> LOW)
    logger.info(f"Event execution order: {event_order}")
    assert event_order == ["high", "medium", "low"], f"Expected ['high', 'medium', 'low'], got {event_order}"
    
    logger.info("✓ Event priority test passed!")


async def test_event_history():
    """Event history'yi test et"""
    
    logger.info("=== Event History Test Started ===")
    
    event_bus = get_event_bus()
    
    # Event'leri yayınla
    for i in range(5):
        event_bus.publish(
            EventTypes.ESP_HEARTBEAT,
            {"coil_id": f"ESP{i:03d}", "sequence": i},
            source="test"
        )
    
    await asyncio.sleep(0.1)
    
    # History'yi kontrol et
    history = event_bus.get_event_history()
    logger.info(f"Event history contains {len(history)} events")
    
    # Son 5 event'i kontrol et
    recent_events = history[-5:]
    for i, event in enumerate(recent_events):
        assert event.data["sequence"] == i, f"Expected sequence {i}, got {event.data['sequence']}"
    
    logger.info("✓ Event history test passed!")


if __name__ == "__main__":
    async def run_all_tests():
        """Tüm testleri çalıştır"""
        try:
            await test_basic_event_bus()
            await test_wildcard_events()
            await test_event_priority()
            await test_event_history()
            
            logger.info("🎉 ALL EVENTBUS TESTS PASSED! 🎉")
            
        except Exception as e:
            logger.error(f"❌ TESTS FAILED: {e}")
            raise
    
    asyncio.run(run_all_tests())
