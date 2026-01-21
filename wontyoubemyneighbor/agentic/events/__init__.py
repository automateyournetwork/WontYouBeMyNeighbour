"""
Event Bus Module

Provides:
- Publish-subscribe messaging
- Event routing
- Event filtering
- Event history
"""

from .bus import (
    Event,
    EventType,
    EventPriority,
    EventBus,
    get_event_bus
)
from .subscribers import (
    Subscriber,
    SubscriberConfig,
    SubscriberManager,
    get_subscriber_manager
)
from .channels import (
    Channel,
    ChannelType,
    ChannelConfig,
    ChannelManager,
    get_channel_manager
)

__all__ = [
    # Bus
    "Event",
    "EventType",
    "EventPriority",
    "EventBus",
    "get_event_bus",
    # Subscribers
    "Subscriber",
    "SubscriberConfig",
    "SubscriberManager",
    "get_subscriber_manager",
    # Channels
    "Channel",
    "ChannelType",
    "ChannelConfig",
    "ChannelManager",
    "get_channel_manager"
]
