"""
Notification Channels

Provides:
- Channel types (email, Slack, webhook, SMS)
- Channel configuration
- Channel management
- Delivery abstraction
"""

import uuid
import json
import hashlib
import hmac
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class ChannelType(Enum):
    """Types of notification channels"""
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    SMS = "sms"
    TEAMS = "teams"
    PAGERDUTY = "pagerduty"
    DISCORD = "discord"


class ChannelStatus(Enum):
    """Channel status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"


@dataclass
class ChannelConfig:
    """Channel configuration"""

    id: str
    name: str
    channel_type: ChannelType
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    status: ChannelStatus = ChannelStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_used_at: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0
    last_error: Optional[str] = None

    def to_dict(self) -> dict:
        # Hide sensitive config values
        safe_config = {}
        for k, v in self.config.items():
            if any(s in k.lower() for s in ["password", "secret", "token", "key", "auth"]):
                safe_config[k] = "***"
            else:
                safe_config[k] = v

        return {
            "id": self.id,
            "name": self.name,
            "channel_type": self.channel_type.value,
            "enabled": self.enabled,
            "config": safe_config,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_error": self.last_error
        }


@dataclass
class DeliveryResult:
    """Result of notification delivery"""

    success: bool
    channel_id: str
    message_id: Optional[str] = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    response_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
            "response_data": self.response_data
        }


class NotificationChannel(ABC):
    """Abstract base class for notification channels"""

    def __init__(self, config: ChannelConfig):
        self.config = config

    @abstractmethod
    def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        **kwargs
    ) -> DeliveryResult:
        """Send notification through this channel"""
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """Validate channel configuration"""
        pass

    def test(self) -> DeliveryResult:
        """Test the channel"""
        try:
            return self.send(
                recipient="test",
                subject="Test Notification",
                body="This is a test notification from ADN Platform."
            )
        except Exception as e:
            return DeliveryResult(
                success=False,
                channel_id=self.config.id,
                error=str(e)
            )


class EmailChannel(NotificationChannel):
    """Email notification channel"""

    def validate_config(self) -> bool:
        required = ["smtp_host", "smtp_port", "from_address"]
        return all(k in self.config.config for k in required)

    def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        **kwargs
    ) -> DeliveryResult:
        """Send email notification (simulated)"""
        if not self.validate_config():
            return DeliveryResult(
                success=False,
                channel_id=self.config.id,
                error="Invalid channel configuration"
            )

        # Simulated email sending
        message_id = f"email_{uuid.uuid4().hex[:12]}"

        self.config.last_used_at = datetime.now()
        self.config.success_count += 1

        return DeliveryResult(
            success=True,
            channel_id=self.config.id,
            message_id=message_id,
            response_data={
                "recipient": recipient,
                "subject": subject,
                "smtp_host": self.config.config.get("smtp_host")
            }
        )


class SlackChannel(NotificationChannel):
    """Slack notification channel"""

    def validate_config(self) -> bool:
        return "webhook_url" in self.config.config or "bot_token" in self.config.config

    def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        **kwargs
    ) -> DeliveryResult:
        """Send Slack notification (simulated)"""
        if not self.validate_config():
            return DeliveryResult(
                success=False,
                channel_id=self.config.id,
                error="Invalid channel configuration"
            )

        # Simulated Slack sending
        message_id = f"slack_{uuid.uuid4().hex[:12]}"

        self.config.last_used_at = datetime.now()
        self.config.success_count += 1

        return DeliveryResult(
            success=True,
            channel_id=self.config.id,
            message_id=message_id,
            response_data={
                "channel": recipient,
                "blocks": kwargs.get("blocks", [])
            }
        )


class WebhookChannel(NotificationChannel):
    """Webhook notification channel"""

    def validate_config(self) -> bool:
        return "url" in self.config.config

    def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        **kwargs
    ) -> DeliveryResult:
        """Send webhook notification (simulated)"""
        if not self.validate_config():
            return DeliveryResult(
                success=False,
                channel_id=self.config.id,
                error="Invalid channel configuration"
            )

        # Build payload
        payload = {
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }

        # Generate signature
        secret = self.config.config.get("secret", "")
        if secret:
            signature = hmac.new(
                secret.encode(),
                json.dumps(payload).encode(),
                hashlib.sha256
            ).hexdigest()
        else:
            signature = None

        # Simulated webhook call
        message_id = f"webhook_{uuid.uuid4().hex[:12]}"

        self.config.last_used_at = datetime.now()
        self.config.success_count += 1

        return DeliveryResult(
            success=True,
            channel_id=self.config.id,
            message_id=message_id,
            response_data={
                "url": self.config.config["url"],
                "signature": signature,
                "payload_size": len(json.dumps(payload))
            }
        )


class SMSChannel(NotificationChannel):
    """SMS notification channel"""

    def validate_config(self) -> bool:
        required = ["provider", "api_key"]
        return all(k in self.config.config for k in required)

    def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        **kwargs
    ) -> DeliveryResult:
        """Send SMS notification (simulated)"""
        if not self.validate_config():
            return DeliveryResult(
                success=False,
                channel_id=self.config.id,
                error="Invalid channel configuration"
            )

        # Combine subject and body for SMS
        message = f"{subject}: {body}"
        if len(message) > 160:
            message = message[:157] + "..."

        # Simulated SMS sending
        message_id = f"sms_{uuid.uuid4().hex[:12]}"

        self.config.last_used_at = datetime.now()
        self.config.success_count += 1

        return DeliveryResult(
            success=True,
            channel_id=self.config.id,
            message_id=message_id,
            response_data={
                "recipient": recipient,
                "message_length": len(message),
                "provider": self.config.config["provider"]
            }
        )


class ChannelManager:
    """Manages notification channels"""

    # Channel class mapping
    CHANNEL_CLASSES = {
        ChannelType.EMAIL: EmailChannel,
        ChannelType.SLACK: SlackChannel,
        ChannelType.WEBHOOK: WebhookChannel,
        ChannelType.SMS: SMSChannel
    }

    def __init__(self):
        self.channels: Dict[str, ChannelConfig] = {}
        self._instances: Dict[str, NotificationChannel] = {}

    def create_channel(
        self,
        name: str,
        channel_type: ChannelType,
        config: Dict[str, Any],
        enabled: bool = True
    ) -> ChannelConfig:
        """Create a notification channel"""
        channel_id = f"channel_{uuid.uuid4().hex[:8]}"

        channel_config = ChannelConfig(
            id=channel_id,
            name=name,
            channel_type=channel_type,
            enabled=enabled,
            config=config
        )

        self.channels[channel_id] = channel_config

        # Create channel instance
        if channel_type in self.CHANNEL_CLASSES:
            self._instances[channel_id] = self.CHANNEL_CLASSES[channel_type](channel_config)

        return channel_config

    def get_channel(self, channel_id: str) -> Optional[ChannelConfig]:
        """Get channel by ID"""
        return self.channels.get(channel_id)

    def get_channel_instance(self, channel_id: str) -> Optional[NotificationChannel]:
        """Get channel instance"""
        return self._instances.get(channel_id)

    def update_channel(
        self,
        channel_id: str,
        **kwargs
    ) -> Optional[ChannelConfig]:
        """Update channel configuration"""
        channel = self.channels.get(channel_id)
        if not channel:
            return None

        for key, value in kwargs.items():
            if key == "config":
                channel.config.update(value)
            elif hasattr(channel, key):
                setattr(channel, key, value)

        channel.updated_at = datetime.now()
        return channel

    def delete_channel(self, channel_id: str) -> bool:
        """Delete a channel"""
        if channel_id in self.channels:
            del self.channels[channel_id]
            if channel_id in self._instances:
                del self._instances[channel_id]
            return True
        return False

    def enable_channel(self, channel_id: str) -> bool:
        """Enable a channel"""
        channel = self.channels.get(channel_id)
        if channel:
            channel.enabled = True
            channel.status = ChannelStatus.ACTIVE
            return True
        return False

    def disable_channel(self, channel_id: str) -> bool:
        """Disable a channel"""
        channel = self.channels.get(channel_id)
        if channel:
            channel.enabled = False
            channel.status = ChannelStatus.INACTIVE
            return True
        return False

    def send(
        self,
        channel_id: str,
        recipient: str,
        subject: str,
        body: str,
        **kwargs
    ) -> DeliveryResult:
        """Send notification through a channel"""
        channel = self.channels.get(channel_id)
        if not channel:
            return DeliveryResult(
                success=False,
                channel_id=channel_id,
                error="Channel not found"
            )

        if not channel.enabled:
            return DeliveryResult(
                success=False,
                channel_id=channel_id,
                error="Channel is disabled"
            )

        instance = self._instances.get(channel_id)
        if not instance:
            return DeliveryResult(
                success=False,
                channel_id=channel_id,
                error="Channel instance not available"
            )

        try:
            result = instance.send(recipient, subject, body, **kwargs)
            if result.success:
                channel.success_count += 1
                channel.last_error = None
            else:
                channel.failure_count += 1
                channel.last_error = result.error
            channel.last_used_at = datetime.now()
            return result
        except Exception as e:
            channel.failure_count += 1
            channel.last_error = str(e)
            channel.status = ChannelStatus.ERROR
            return DeliveryResult(
                success=False,
                channel_id=channel_id,
                error=str(e)
            )

    def test_channel(self, channel_id: str) -> DeliveryResult:
        """Test a channel"""
        instance = self._instances.get(channel_id)
        if not instance:
            return DeliveryResult(
                success=False,
                channel_id=channel_id,
                error="Channel instance not available"
            )
        return instance.test()

    def get_channels(
        self,
        channel_type: Optional[ChannelType] = None,
        enabled_only: bool = False
    ) -> List[ChannelConfig]:
        """Get all channels"""
        channels = list(self.channels.values())
        if channel_type:
            channels = [c for c in channels if c.channel_type == channel_type]
        if enabled_only:
            channels = [c for c in channels if c.enabled]
        return channels

    def get_channels_by_type(self, channel_type: ChannelType) -> List[ChannelConfig]:
        """Get channels by type"""
        return [c for c in self.channels.values() if c.channel_type == channel_type]

    def get_statistics(self) -> dict:
        """Get channel statistics"""
        by_type = {}
        total_success = 0
        total_failure = 0

        for channel in self.channels.values():
            type_name = channel.channel_type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1
            total_success += channel.success_count
            total_failure += channel.failure_count

        return {
            "total_channels": len(self.channels),
            "enabled_channels": len([c for c in self.channels.values() if c.enabled]),
            "by_type": by_type,
            "total_success": total_success,
            "total_failure": total_failure,
            "success_rate": total_success / (total_success + total_failure) if (total_success + total_failure) > 0 else 1.0
        }


# Global channel manager instance
_channel_manager: Optional[ChannelManager] = None


def get_channel_manager() -> ChannelManager:
    """Get or create the global channel manager"""
    global _channel_manager
    if _channel_manager is None:
        _channel_manager = ChannelManager()
    return _channel_manager
