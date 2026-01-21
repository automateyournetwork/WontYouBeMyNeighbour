"""
Event Bus

Provides:
- Event definitions
- Event publishing
- Event routing
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Set
from datetime import datetime
from enum import Enum
import asyncio
from collections import deque


class EventType(Enum):
    """Types of events"""
    # System events
    SYSTEM_START = "system.start"
    SYSTEM_STOP = "system.stop"
    SYSTEM_ERROR = "system.error"

    # Protocol events
    OSPF_NEIGHBOR_UP = "ospf.neighbor.up"
    OSPF_NEIGHBOR_DOWN = "ospf.neighbor.down"
    OSPF_LSA_RECEIVED = "ospf.lsa.received"
    OSPF_SPF_COMPLETE = "ospf.spf.complete"

    BGP_PEER_UP = "bgp.peer.up"
    BGP_PEER_DOWN = "bgp.peer.down"
    BGP_ROUTE_RECEIVED = "bgp.route.received"
    BGP_ROUTE_WITHDRAWN = "bgp.route.withdrawn"

    ISIS_ADJACENCY_UP = "isis.adjacency.up"
    ISIS_ADJACENCY_DOWN = "isis.adjacency.down"
    ISIS_LSP_RECEIVED = "isis.lsp.received"

    # Network events
    LINK_UP = "network.link.up"
    LINK_DOWN = "network.link.down"
    INTERFACE_STATUS = "network.interface.status"
    ROUTE_CHANGE = "network.route.change"

    # Agent events
    AGENT_START = "agent.start"
    AGENT_STOP = "agent.stop"
    AGENT_CONFIG_CHANGE = "agent.config.change"
    AGENT_ERROR = "agent.error"

    # API events
    API_REQUEST = "api.request"
    API_RESPONSE = "api.response"
    API_ERROR = "api.error"

    # Job events
    JOB_STARTED = "job.started"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"

    # Pipeline events
    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"

    # Workflow events
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"

    # Alert events
    ALERT_TRIGGERED = "alert.triggered"
    ALERT_RESOLVED = "alert.resolved"

    # Custom events
    CUSTOM = "custom"


class EventPriority(Enum):
    """Event priority levels"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Event:
    """Event definition"""

    id: str
    event_type: EventType
    source: str  # Source component/module
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL
    timestamp: datetime = field(default_factory=datetime.now)
    correlation_id: Optional[str] = None  # For related events
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    # Delivery tracking
    delivered_to: List[str] = field(default_factory=list)
    delivery_count: int = 0
    acknowledged: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "source": self.source,
            "payload": self.payload,
            "priority": self.priority.value,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
            "tags": self.tags,
            "delivered_to": self.delivered_to,
            "delivery_count": self.delivery_count,
            "acknowledged": self.acknowledged
        }


class EventBus:
    """Central event bus for publish-subscribe messaging"""

    def __init__(self, history_size: int = 1000):
        self._subscribers: Dict[str, Dict[str, Callable]] = {}  # event_type -> {subscriber_id: callback}
        self._pattern_subscribers: Dict[str, Dict[str, Callable]] = {}  # pattern -> {subscriber_id: callback}
        self._history: deque = deque(maxlen=history_size)
        self._pending_events: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._stats = {
            "total_published": 0,
            "total_delivered": 0,
            "by_type": {},
            "by_source": {}
        }

    def subscribe(
        self,
        event_type: EventType,
        subscriber_id: str,
        callback: Callable
    ) -> bool:
        """Subscribe to a specific event type"""
        type_key = event_type.value
        if type_key not in self._subscribers:
            self._subscribers[type_key] = {}

        self._subscribers[type_key][subscriber_id] = callback
        return True

    def subscribe_pattern(
        self,
        pattern: str,
        subscriber_id: str,
        callback: Callable
    ) -> bool:
        """Subscribe to events matching a pattern (e.g., 'ospf.*')"""
        if pattern not in self._pattern_subscribers:
            self._pattern_subscribers[pattern] = {}

        self._pattern_subscribers[pattern][subscriber_id] = callback
        return True

    def unsubscribe(
        self,
        event_type: EventType,
        subscriber_id: str
    ) -> bool:
        """Unsubscribe from an event type"""
        type_key = event_type.value
        if type_key in self._subscribers and subscriber_id in self._subscribers[type_key]:
            del self._subscribers[type_key][subscriber_id]
            return True
        return False

    def unsubscribe_pattern(
        self,
        pattern: str,
        subscriber_id: str
    ) -> bool:
        """Unsubscribe from a pattern"""
        if pattern in self._pattern_subscribers and subscriber_id in self._pattern_subscribers[pattern]:
            del self._pattern_subscribers[pattern][subscriber_id]
            return True
        return False

    def unsubscribe_all(self, subscriber_id: str) -> int:
        """Unsubscribe from all events"""
        count = 0
        for type_key in list(self._subscribers.keys()):
            if subscriber_id in self._subscribers[type_key]:
                del self._subscribers[type_key][subscriber_id]
                count += 1

        for pattern in list(self._pattern_subscribers.keys()):
            if subscriber_id in self._pattern_subscribers[pattern]:
                del self._pattern_subscribers[pattern][subscriber_id]
                count += 1

        return count

    def publish(
        self,
        event_type: EventType,
        source: str,
        payload: Optional[Dict[str, Any]] = None,
        priority: EventPriority = EventPriority.NORMAL,
        correlation_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Event:
        """Publish an event"""
        event = Event(
            id=f"evt_{uuid.uuid4().hex[:12]}",
            event_type=event_type,
            source=source,
            payload=payload or {},
            priority=priority,
            correlation_id=correlation_id,
            tags=tags or []
        )

        self._history.append(event)
        self._stats["total_published"] += 1
        self._stats["by_type"][event_type.value] = self._stats["by_type"].get(event_type.value, 0) + 1
        self._stats["by_source"][source] = self._stats["by_source"].get(source, 0) + 1

        # Deliver to subscribers synchronously
        self._deliver_event(event)

        return event

    async def publish_async(
        self,
        event_type: EventType,
        source: str,
        payload: Optional[Dict[str, Any]] = None,
        priority: EventPriority = EventPriority.NORMAL,
        correlation_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Event:
        """Publish an event asynchronously"""
        event = Event(
            id=f"evt_{uuid.uuid4().hex[:12]}",
            event_type=event_type,
            source=source,
            payload=payload or {},
            priority=priority,
            correlation_id=correlation_id,
            tags=tags or []
        )

        self._history.append(event)
        self._stats["total_published"] += 1
        self._stats["by_type"][event_type.value] = self._stats["by_type"].get(event_type.value, 0) + 1
        self._stats["by_source"][source] = self._stats["by_source"].get(source, 0) + 1

        # Deliver to subscribers asynchronously
        await self._deliver_event_async(event)

        return event

    def _deliver_event(self, event: Event) -> int:
        """Deliver event to subscribers synchronously"""
        delivered = 0
        type_key = event.event_type.value

        # Direct subscribers
        if type_key in self._subscribers:
            for subscriber_id, callback in self._subscribers[type_key].items():
                try:
                    callback(event)
                    event.delivered_to.append(subscriber_id)
                    event.delivery_count += 1
                    delivered += 1
                except Exception:
                    pass

        # Pattern subscribers
        for pattern, subscribers in self._pattern_subscribers.items():
            if self._matches_pattern(type_key, pattern):
                for subscriber_id, callback in subscribers.items():
                    try:
                        callback(event)
                        event.delivered_to.append(subscriber_id)
                        event.delivery_count += 1
                        delivered += 1
                    except Exception:
                        pass

        self._stats["total_delivered"] += delivered
        return delivered

    async def _deliver_event_async(self, event: Event) -> int:
        """Deliver event to subscribers asynchronously"""
        delivered = 0
        type_key = event.event_type.value

        # Direct subscribers
        if type_key in self._subscribers:
            for subscriber_id, callback in self._subscribers[type_key].items():
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                    event.delivered_to.append(subscriber_id)
                    event.delivery_count += 1
                    delivered += 1
                except Exception:
                    pass

        # Pattern subscribers
        for pattern, subscribers in self._pattern_subscribers.items():
            if self._matches_pattern(type_key, pattern):
                for subscriber_id, callback in subscribers.items():
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(event)
                        else:
                            callback(event)
                        event.delivered_to.append(subscriber_id)
                        event.delivery_count += 1
                        delivered += 1
                    except Exception:
                        pass

        self._stats["total_delivered"] += delivered
        return delivered

    def _matches_pattern(self, event_type: str, pattern: str) -> bool:
        """Check if event type matches a pattern"""
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return event_type.startswith(prefix)
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return event_type.startswith(prefix)
        return event_type == pattern

    def get_history(
        self,
        event_type: Optional[EventType] = None,
        source: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Event]:
        """Get event history"""
        events = list(self._history)

        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if source:
            events = [e for e in events if e.source == source]
        if since:
            events = [e for e in events if e.timestamp >= since]

        return events[-limit:]

    def get_event(self, event_id: str) -> Optional[Event]:
        """Get event by ID"""
        for event in self._history:
            if event.id == event_id:
                return event
        return None

    def acknowledge(self, event_id: str) -> bool:
        """Acknowledge an event"""
        event = self.get_event(event_id)
        if event:
            event.acknowledged = True
            return True
        return False

    def get_subscribers(
        self,
        event_type: Optional[EventType] = None
    ) -> Dict[str, List[str]]:
        """Get subscribers by event type"""
        if event_type:
            type_key = event_type.value
            return {type_key: list(self._subscribers.get(type_key, {}).keys())}

        result = {}
        for type_key, subs in self._subscribers.items():
            result[type_key] = list(subs.keys())
        return result

    def get_pattern_subscribers(self) -> Dict[str, List[str]]:
        """Get pattern subscribers"""
        result = {}
        for pattern, subs in self._pattern_subscribers.items():
            result[pattern] = list(subs.keys())
        return result

    def clear_history(self) -> int:
        """Clear event history"""
        count = len(self._history)
        self._history.clear()
        return count

    def get_statistics(self) -> dict:
        """Get event bus statistics"""
        return {
            "total_published": self._stats["total_published"],
            "total_delivered": self._stats["total_delivered"],
            "history_size": len(self._history),
            "subscriber_count": sum(len(subs) for subs in self._subscribers.values()),
            "pattern_subscriber_count": sum(len(subs) for subs in self._pattern_subscribers.values()),
            "event_types_used": len(self._stats["by_type"]),
            "by_type": dict(self._stats["by_type"]),
            "by_source": dict(self._stats["by_source"])
        }


# Global event bus instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get or create the global event bus"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
