"""
Event Channels

Provides:
- Channel definitions
- Channel routing
- Channel management
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from enum import Enum

from .bus import Event, EventType, EventPriority, get_event_bus


class ChannelType(Enum):
    """Types of event channels"""
    DEFAULT = "default"  # Default channel for all events
    PROTOCOL = "protocol"  # Protocol events (OSPF, BGP, IS-IS)
    NETWORK = "network"  # Network infrastructure events
    SYSTEM = "system"  # System events
    AGENT = "agent"  # Agent lifecycle events
    API = "api"  # API events
    JOB = "job"  # Job/scheduler events
    PIPELINE = "pipeline"  # Pipeline events
    WORKFLOW = "workflow"  # Workflow events
    ALERT = "alert"  # Alert events
    CUSTOM = "custom"  # Custom channels


@dataclass
class ChannelConfig:
    """Channel configuration"""

    max_subscribers: int = 100
    retention_hours: int = 24
    persistence_enabled: bool = False
    encryption_enabled: bool = False
    compression_enabled: bool = False
    throttle_events_per_second: int = 0  # 0 = unlimited
    dedupe_enabled: bool = False
    dedupe_window_seconds: int = 60
    filter_event_types: List[str] = field(default_factory=list)
    filter_sources: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "max_subscribers": self.max_subscribers,
            "retention_hours": self.retention_hours,
            "persistence_enabled": self.persistence_enabled,
            "encryption_enabled": self.encryption_enabled,
            "compression_enabled": self.compression_enabled,
            "throttle_events_per_second": self.throttle_events_per_second,
            "dedupe_enabled": self.dedupe_enabled,
            "dedupe_window_seconds": self.dedupe_window_seconds,
            "filter_event_types": self.filter_event_types,
            "filter_sources": self.filter_sources,
            "extra": self.extra
        }


@dataclass
class Channel:
    """Event channel"""

    id: str
    name: str
    channel_type: ChannelType
    description: str = ""
    config: ChannelConfig = field(default_factory=ChannelConfig)
    patterns: List[str] = field(default_factory=list)  # Event patterns to route
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    subscriber_ids: Set[str] = field(default_factory=set)
    events_routed: int = 0
    last_event_at: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)

    def accepts_event(self, event: Event) -> bool:
        """Check if channel accepts event"""
        # Check event type filter
        if self.config.filter_event_types:
            if event.event_type.value not in self.config.filter_event_types:
                return False

        # Check source filter
        if self.config.filter_sources:
            if event.source not in self.config.filter_sources:
                return False

        # Check pattern match
        if self.patterns:
            event_type_str = event.event_type.value
            matched = False
            for pattern in self.patterns:
                if self._matches_pattern(event_type_str, pattern):
                    matched = True
                    break
            if not matched:
                return False

        return True

    def _matches_pattern(self, event_type: str, pattern: str) -> bool:
        """Check if event type matches pattern"""
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return event_type.startswith(prefix)
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return event_type.startswith(prefix)
        return event_type == pattern

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "channel_type": self.channel_type.value,
            "description": self.description,
            "config": self.config.to_dict(),
            "patterns": self.patterns,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "subscriber_count": len(self.subscriber_ids),
            "events_routed": self.events_routed,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
            "tags": self.tags
        }


class ChannelManager:
    """Manages event channels"""

    def __init__(self):
        self.channels: Dict[str, Channel] = {}
        self._event_bus = get_event_bus()
        self._init_default_channels()

    def _init_default_channels(self) -> None:
        """Initialize default event channels"""

        # Default channel
        self.create_channel(
            name="default",
            channel_type=ChannelType.DEFAULT,
            description="Default channel for all events",
            patterns=["*"]
        )

        # Protocol channel
        self.create_channel(
            name="protocol",
            channel_type=ChannelType.PROTOCOL,
            description="Protocol events (OSPF, BGP, IS-IS, GRE, BFD)",
            patterns=["ospf.*", "bgp.*", "isis.*", "gre.*", "bfd.*"]
        )

        # Network channel
        self.create_channel(
            name="network",
            channel_type=ChannelType.NETWORK,
            description="Network infrastructure events",
            patterns=["network.*"]
        )

        # System channel
        self.create_channel(
            name="system",
            channel_type=ChannelType.SYSTEM,
            description="System lifecycle events",
            patterns=["system.*"]
        )

        # Agent channel
        self.create_channel(
            name="agent",
            channel_type=ChannelType.AGENT,
            description="Agent lifecycle events",
            patterns=["agent.*"]
        )

        # API channel
        self.create_channel(
            name="api",
            channel_type=ChannelType.API,
            description="API request/response events",
            patterns=["api.*"]
        )

        # Job channel
        self.create_channel(
            name="job",
            channel_type=ChannelType.JOB,
            description="Scheduler and job events",
            patterns=["job.*"]
        )

        # Pipeline channel
        self.create_channel(
            name="pipeline",
            channel_type=ChannelType.PIPELINE,
            description="Data pipeline events",
            patterns=["pipeline.*"]
        )

        # Workflow channel
        self.create_channel(
            name="workflow",
            channel_type=ChannelType.WORKFLOW,
            description="Workflow execution events",
            patterns=["workflow.*"]
        )

        # Alert channel
        self.create_channel(
            name="alert",
            channel_type=ChannelType.ALERT,
            description="Alert events",
            patterns=["alert.*"]
        )

    def create_channel(
        self,
        name: str,
        channel_type: ChannelType,
        description: str = "",
        patterns: Optional[List[str]] = None,
        config: Optional[ChannelConfig] = None,
        tags: Optional[List[str]] = None
    ) -> Channel:
        """Create a new channel"""
        channel_id = f"ch_{uuid.uuid4().hex[:8]}"

        channel = Channel(
            id=channel_id,
            name=name,
            channel_type=channel_type,
            description=description,
            patterns=patterns or [],
            config=config or ChannelConfig(),
            tags=tags or []
        )

        self.channels[channel_id] = channel
        return channel

    def get_channel(self, channel_id: str) -> Optional[Channel]:
        """Get channel by ID"""
        return self.channels.get(channel_id)

    def get_channel_by_name(self, name: str) -> Optional[Channel]:
        """Get channel by name"""
        for channel in self.channels.values():
            if channel.name == name:
                return channel
        return None

    def update_channel(
        self,
        channel_id: str,
        **kwargs
    ) -> Optional[Channel]:
        """Update channel properties"""
        channel = self.channels.get(channel_id)
        if not channel:
            return None

        for key, value in kwargs.items():
            if hasattr(channel, key):
                setattr(channel, key, value)

        return channel

    def delete_channel(self, channel_id: str) -> bool:
        """Delete a channel"""
        if channel_id in self.channels:
            del self.channels[channel_id]
            return True
        return False

    def enable_channel(self, channel_id: str) -> bool:
        """Enable a channel"""
        channel = self.channels.get(channel_id)
        if channel:
            channel.enabled = True
            return True
        return False

    def disable_channel(self, channel_id: str) -> bool:
        """Disable a channel"""
        channel = self.channels.get(channel_id)
        if channel:
            channel.enabled = False
            return True
        return False

    def add_subscriber(
        self,
        channel_id: str,
        subscriber_id: str
    ) -> bool:
        """Add subscriber to channel"""
        channel = self.channels.get(channel_id)
        if not channel:
            return False

        if len(channel.subscriber_ids) >= channel.config.max_subscribers:
            return False

        channel.subscriber_ids.add(subscriber_id)
        return True

    def remove_subscriber(
        self,
        channel_id: str,
        subscriber_id: str
    ) -> bool:
        """Remove subscriber from channel"""
        channel = self.channels.get(channel_id)
        if not channel:
            return False

        channel.subscriber_ids.discard(subscriber_id)
        return True

    def add_pattern(
        self,
        channel_id: str,
        pattern: str
    ) -> bool:
        """Add pattern to channel"""
        channel = self.channels.get(channel_id)
        if not channel:
            return False

        if pattern not in channel.patterns:
            channel.patterns.append(pattern)

        return True

    def remove_pattern(
        self,
        channel_id: str,
        pattern: str
    ) -> bool:
        """Remove pattern from channel"""
        channel = self.channels.get(channel_id)
        if not channel:
            return False

        if pattern in channel.patterns:
            channel.patterns.remove(pattern)

        return True

    def route_event(self, event: Event) -> List[str]:
        """Route event to matching channels"""
        matching_channels = []

        for channel in self.channels.values():
            if channel.enabled and channel.accepts_event(event):
                channel.events_routed += 1
                channel.last_event_at = datetime.now()
                matching_channels.append(channel.id)

        return matching_channels

    def get_channels_for_event(self, event: Event) -> List[Channel]:
        """Get channels that would receive an event"""
        return [
            channel for channel in self.channels.values()
            if channel.enabled and channel.accepts_event(event)
        ]

    def get_channels(
        self,
        channel_type: Optional[ChannelType] = None,
        enabled_only: bool = False,
        tag: Optional[str] = None
    ) -> List[Channel]:
        """Get channels with filtering"""
        channels = list(self.channels.values())

        if channel_type:
            channels = [c for c in channels if c.channel_type == channel_type]
        if enabled_only:
            channels = [c for c in channels if c.enabled]
        if tag:
            channels = [c for c in channels if tag in c.tags]

        return channels

    def get_statistics(self) -> dict:
        """Get channel statistics"""
        total_routed = 0
        total_subscribers = 0
        by_type = {}

        for channel in self.channels.values():
            total_routed += channel.events_routed
            total_subscribers += len(channel.subscriber_ids)
            by_type[channel.channel_type.value] = by_type.get(channel.channel_type.value, 0) + 1

        return {
            "total_channels": len(self.channels),
            "enabled_channels": len([c for c in self.channels.values() if c.enabled]),
            "total_events_routed": total_routed,
            "total_subscribers": total_subscribers,
            "by_type": by_type
        }


# Global channel manager instance
_channel_manager: Optional[ChannelManager] = None


def get_channel_manager() -> ChannelManager:
    """Get or create the global channel manager"""
    global _channel_manager
    if _channel_manager is None:
        _channel_manager = ChannelManager()
    return _channel_manager
