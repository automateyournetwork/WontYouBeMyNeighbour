"""Tests for event bus module"""

import pytest
from agentic.events import (
    Event, EventType, EventPriority, EventBus, get_event_bus
)


class TestEventBus:
    """Tests for EventBus"""

    def test_publish_event(self):
        """Test event publishing"""
        bus = EventBus()
        event = bus.publish(
            event_type=EventType.SYSTEM_START,
            source="test",
            payload={"message": "Test event"}
        )
        assert event is not None
        assert event.event_type == EventType.SYSTEM_START
        assert event.source == "test"

    def test_get_event(self):
        """Test retrieving event by ID"""
        bus = EventBus()
        event = bus.publish(
            event_type=EventType.AGENT_START,
            source="test"
        )

        retrieved = bus.get_event(event.id)
        assert retrieved is not None
        assert retrieved.id == event.id

    def test_get_history(self):
        """Test event history"""
        bus = EventBus()
        bus.publish(EventType.SYSTEM_START, "test1")
        bus.publish(EventType.SYSTEM_START, "test2")
        bus.publish(EventType.AGENT_START, "test3")

        # Get all history
        history = bus.get_history(limit=10)
        assert len(history) >= 3

        # Filter by type
        startup_events = bus.get_history(event_type=EventType.SYSTEM_START, limit=10)
        assert all(e.event_type == EventType.SYSTEM_START for e in startup_events)

    def test_event_priority(self):
        """Test event priorities"""
        bus = EventBus()

        low = bus.publish(EventType.CUSTOM, "test", priority=EventPriority.LOW)
        high = bus.publish(EventType.CUSTOM, "test", priority=EventPriority.HIGH)
        critical = bus.publish(EventType.CUSTOM, "test", priority=EventPriority.CRITICAL)

        assert low.priority == EventPriority.LOW
        assert high.priority == EventPriority.HIGH
        assert critical.priority == EventPriority.CRITICAL


class TestEvent:
    """Tests for Event dataclass"""

    def test_to_dict(self):
        """Test event serialization"""
        event = Event(
            id="evt-1",
            event_type=EventType.LINK_UP,
            source="test",
            payload={"network": "test-net"},
            priority=EventPriority.NORMAL,
            tags=["network", "deployment"]
        )

        data = event.to_dict()
        assert data["id"] == "evt-1"
        assert data["event_type"] == EventType.LINK_UP.value
        assert data["source"] == "test"
        assert "network" in data["tags"]


class TestEventType:
    """Tests for EventType enum"""

    def test_event_types_exist(self):
        """Test event types are defined"""
        assert hasattr(EventType, "SYSTEM_START")
        assert hasattr(EventType, "AGENT_START")
        assert hasattr(EventType, "LINK_UP")

    def test_event_type_values(self):
        """Test event type values are strings"""
        for event_type in EventType:
            assert isinstance(event_type.value, str)


class TestEventPriority:
    """Tests for EventPriority enum"""

    def test_priority_order(self):
        """Test priority values exist"""
        assert hasattr(EventPriority, "LOW")
        assert hasattr(EventPriority, "NORMAL")
        assert hasattr(EventPriority, "HIGH")
        assert hasattr(EventPriority, "CRITICAL")
