"""
Event Subscribers

Provides:
- Subscriber definitions
- Subscriber management
- Event filtering
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Set
from datetime import datetime
from enum import Enum

from .bus import Event, EventType, EventPriority, get_event_bus


@dataclass
class SubscriberConfig:
    """Subscriber configuration"""

    filter_sources: List[str] = field(default_factory=list)  # Only from these sources
    filter_tags: List[str] = field(default_factory=list)  # Only with these tags
    min_priority: EventPriority = EventPriority.LOW  # Minimum priority
    max_queue_size: int = 1000  # Max queued events
    batch_size: int = 1  # Process events in batches
    batch_timeout_ms: int = 100  # Batch timeout
    retry_count: int = 3  # Retry failed deliveries
    retry_delay_ms: int = 1000  # Retry delay
    dedupe_window_ms: int = 0  # Deduplication window (0 = disabled)

    def to_dict(self) -> dict:
        return {
            "filter_sources": self.filter_sources,
            "filter_tags": self.filter_tags,
            "min_priority": self.min_priority.value,
            "max_queue_size": self.max_queue_size,
            "batch_size": self.batch_size,
            "batch_timeout_ms": self.batch_timeout_ms,
            "retry_count": self.retry_count,
            "retry_delay_ms": self.retry_delay_ms,
            "dedupe_window_ms": self.dedupe_window_ms
        }


@dataclass
class Subscriber:
    """Event subscriber"""

    id: str
    name: str
    description: str = ""
    event_types: List[EventType] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    config: SubscriberConfig = field(default_factory=SubscriberConfig)
    handler: Optional[Callable] = None
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    last_event_at: Optional[datetime] = None
    events_received: int = 0
    events_processed: int = 0
    events_failed: int = 0
    tags: List[str] = field(default_factory=list)

    def should_receive(self, event: Event) -> bool:
        """Check if subscriber should receive event"""
        # Check priority
        if event.priority.value < self.config.min_priority.value:
            return False

        # Check source filter
        if self.config.filter_sources and event.source not in self.config.filter_sources:
            return False

        # Check tag filter
        if self.config.filter_tags:
            if not any(tag in event.tags for tag in self.config.filter_tags):
                return False

        return True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "event_types": [e.value for e in self.event_types],
            "patterns": self.patterns,
            "config": self.config.to_dict(),
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
            "events_received": self.events_received,
            "events_processed": self.events_processed,
            "events_failed": self.events_failed,
            "tags": self.tags
        }


class SubscriberManager:
    """Manages event subscribers"""

    def __init__(self):
        self.subscribers: Dict[str, Subscriber] = {}
        self._event_bus = get_event_bus()
        self._handlers: Dict[str, Callable] = {}
        self._register_builtin_handlers()

    def _register_builtin_handlers(self) -> None:
        """Register built-in event handlers"""

        def log_handler(event: Event) -> None:
            """Log events"""
            pass  # Simulated logging

        def alert_handler(event: Event) -> None:
            """Generate alerts from events"""
            pass  # Simulated alerting

        def metrics_handler(event: Event) -> None:
            """Export events as metrics"""
            pass  # Simulated metrics

        def webhook_handler(event: Event) -> None:
            """Send events to webhooks"""
            pass  # Simulated webhook

        def email_handler(event: Event) -> None:
            """Send events via email"""
            pass  # Simulated email

        def slack_handler(event: Event) -> None:
            """Send events to Slack"""
            pass  # Simulated Slack

        def storage_handler(event: Event) -> None:
            """Store events for persistence"""
            pass  # Simulated storage

        def aggregation_handler(event: Event) -> None:
            """Aggregate events for analytics"""
            pass  # Simulated aggregation

        self._handlers = {
            "log": log_handler,
            "alert": alert_handler,
            "metrics": metrics_handler,
            "webhook": webhook_handler,
            "email": email_handler,
            "slack": slack_handler,
            "storage": storage_handler,
            "aggregation": aggregation_handler
        }

    def register_handler(
        self,
        name: str,
        handler: Callable
    ) -> None:
        """Register a custom event handler"""
        self._handlers[name] = handler

    def get_handler(self, name: str) -> Optional[Callable]:
        """Get handler by name"""
        return self._handlers.get(name)

    def get_available_handlers(self) -> List[str]:
        """Get list of available handlers"""
        return list(self._handlers.keys())

    def create_subscriber(
        self,
        name: str,
        event_types: Optional[List[EventType]] = None,
        patterns: Optional[List[str]] = None,
        handler_name: Optional[str] = None,
        handler: Optional[Callable] = None,
        config: Optional[SubscriberConfig] = None,
        description: str = "",
        tags: Optional[List[str]] = None
    ) -> Subscriber:
        """Create a new subscriber"""
        subscriber_id = f"sub_{uuid.uuid4().hex[:8]}"

        # Get handler
        if handler_name and not handler:
            handler = self._handlers.get(handler_name)

        subscriber = Subscriber(
            id=subscriber_id,
            name=name,
            description=description,
            event_types=event_types or [],
            patterns=patterns or [],
            config=config or SubscriberConfig(),
            handler=handler,
            tags=tags or []
        )

        self.subscribers[subscriber_id] = subscriber

        # Register with event bus
        self._register_with_bus(subscriber)

        return subscriber

    def _register_with_bus(self, subscriber: Subscriber) -> None:
        """Register subscriber with event bus"""
        def wrapped_handler(event: Event):
            if subscriber.enabled and subscriber.should_receive(event):
                subscriber.events_received += 1
                subscriber.last_event_at = datetime.now()
                try:
                    if subscriber.handler:
                        subscriber.handler(event)
                    subscriber.events_processed += 1
                except Exception:
                    subscriber.events_failed += 1

        # Subscribe to specific event types
        for event_type in subscriber.event_types:
            self._event_bus.subscribe(event_type, subscriber.id, wrapped_handler)

        # Subscribe to patterns
        for pattern in subscriber.patterns:
            self._event_bus.subscribe_pattern(pattern, subscriber.id, wrapped_handler)

    def get_subscriber(self, subscriber_id: str) -> Optional[Subscriber]:
        """Get subscriber by ID"""
        return self.subscribers.get(subscriber_id)

    def update_subscriber(
        self,
        subscriber_id: str,
        **kwargs
    ) -> Optional[Subscriber]:
        """Update subscriber properties"""
        subscriber = self.subscribers.get(subscriber_id)
        if not subscriber:
            return None

        for key, value in kwargs.items():
            if hasattr(subscriber, key):
                setattr(subscriber, key, value)

        return subscriber

    def delete_subscriber(self, subscriber_id: str) -> bool:
        """Delete a subscriber"""
        subscriber = self.subscribers.get(subscriber_id)
        if not subscriber:
            return False

        # Unsubscribe from event bus
        self._event_bus.unsubscribe_all(subscriber_id)

        del self.subscribers[subscriber_id]
        return True

    def enable_subscriber(self, subscriber_id: str) -> bool:
        """Enable a subscriber"""
        subscriber = self.subscribers.get(subscriber_id)
        if subscriber:
            subscriber.enabled = True
            return True
        return False

    def disable_subscriber(self, subscriber_id: str) -> bool:
        """Disable a subscriber"""
        subscriber = self.subscribers.get(subscriber_id)
        if subscriber:
            subscriber.enabled = False
            return True
        return False

    def add_event_type(
        self,
        subscriber_id: str,
        event_type: EventType
    ) -> bool:
        """Add event type to subscriber"""
        subscriber = self.subscribers.get(subscriber_id)
        if not subscriber:
            return False

        if event_type not in subscriber.event_types:
            subscriber.event_types.append(event_type)
            # Re-register with bus
            self._event_bus.unsubscribe_all(subscriber_id)
            self._register_with_bus(subscriber)

        return True

    def remove_event_type(
        self,
        subscriber_id: str,
        event_type: EventType
    ) -> bool:
        """Remove event type from subscriber"""
        subscriber = self.subscribers.get(subscriber_id)
        if not subscriber:
            return False

        if event_type in subscriber.event_types:
            subscriber.event_types.remove(event_type)
            # Re-register with bus
            self._event_bus.unsubscribe_all(subscriber_id)
            self._register_with_bus(subscriber)

        return True

    def add_pattern(
        self,
        subscriber_id: str,
        pattern: str
    ) -> bool:
        """Add pattern to subscriber"""
        subscriber = self.subscribers.get(subscriber_id)
        if not subscriber:
            return False

        if pattern not in subscriber.patterns:
            subscriber.patterns.append(pattern)
            # Re-register with bus
            self._event_bus.unsubscribe_all(subscriber_id)
            self._register_with_bus(subscriber)

        return True

    def remove_pattern(
        self,
        subscriber_id: str,
        pattern: str
    ) -> bool:
        """Remove pattern from subscriber"""
        subscriber = self.subscribers.get(subscriber_id)
        if not subscriber:
            return False

        if pattern in subscriber.patterns:
            subscriber.patterns.remove(pattern)
            # Re-register with bus
            self._event_bus.unsubscribe_all(subscriber_id)
            self._register_with_bus(subscriber)

        return True

    def get_subscribers(
        self,
        event_type: Optional[EventType] = None,
        enabled_only: bool = False,
        tag: Optional[str] = None
    ) -> List[Subscriber]:
        """Get subscribers with filtering"""
        subscribers = list(self.subscribers.values())

        if event_type:
            subscribers = [s for s in subscribers if event_type in s.event_types]
        if enabled_only:
            subscribers = [s for s in subscribers if s.enabled]
        if tag:
            subscribers = [s for s in subscribers if tag in s.tags]

        return subscribers

    def get_statistics(self) -> dict:
        """Get subscriber statistics"""
        total_received = 0
        total_processed = 0
        total_failed = 0

        for subscriber in self.subscribers.values():
            total_received += subscriber.events_received
            total_processed += subscriber.events_processed
            total_failed += subscriber.events_failed

        return {
            "total_subscribers": len(self.subscribers),
            "enabled_subscribers": len([s for s in self.subscribers.values() if s.enabled]),
            "total_events_received": total_received,
            "total_events_processed": total_processed,
            "total_events_failed": total_failed,
            "available_handlers": len(self._handlers),
            "process_rate": total_processed / total_received if total_received > 0 else 1.0
        }


# Global subscriber manager instance
_subscriber_manager: Optional[SubscriberManager] = None


def get_subscriber_manager() -> SubscriberManager:
    """Get or create the global subscriber manager"""
    global _subscriber_manager
    if _subscriber_manager is None:
        _subscriber_manager = SubscriberManager()
    return _subscriber_manager
