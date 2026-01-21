"""
Notification Channels

Provides:
- Notification channel definitions
- Channel configuration
- Notification routing
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from enum import Enum

from .definitions import Alert, AlertSeverity


class ChannelType(Enum):
    """Notification channel types"""
    EMAIL = "email"
    SLACK = "slack"
    PAGERDUTY = "pagerduty"
    WEBHOOK = "webhook"
    SMS = "sms"
    TEAMS = "teams"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    LOG = "log"
    SNMP_TRAP = "snmp_trap"
    SYSLOG = "syslog"
    CUSTOM = "custom"


class ChannelStatus(Enum):
    """Channel status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"


@dataclass
class ChannelConfig:
    """Channel configuration"""
    
    # Common settings
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000
    retry_count: int = 3
    retry_delay_seconds: int = 30
    timeout_seconds: int = 30
    
    # Filtering
    min_severity: AlertSeverity = AlertSeverity.INFO
    categories: List[str] = field(default_factory=list)  # Empty = all
    sources: List[str] = field(default_factory=list)  # Empty = all
    labels: Dict[str, str] = field(default_factory=dict)  # Required labels
    
    # Formatting
    template: Optional[str] = None
    include_details: bool = True
    include_events: bool = False
    
    # Channel-specific
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "rate_limit_per_hour": self.rate_limit_per_hour,
            "retry_count": self.retry_count,
            "retry_delay_seconds": self.retry_delay_seconds,
            "timeout_seconds": self.timeout_seconds,
            "min_severity": self.min_severity.value,
            "categories": self.categories,
            "sources": self.sources,
            "labels": self.labels,
            "template": self.template,
            "include_details": self.include_details,
            "include_events": self.include_events,
            "extra": self.extra
        }


@dataclass
class NotificationResult:
    """Result of notification attempt"""
    
    channel_id: str
    alert_id: str
    success: bool
    timestamp: datetime
    error: Optional[str] = None
    response: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    
    def to_dict(self) -> dict:
        return {
            "channel_id": self.channel_id,
            "alert_id": self.alert_id,
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
            "error": self.error,
            "response": self.response,
            "retry_count": self.retry_count
        }


@dataclass
class NotificationChannel:
    """Notification channel definition"""
    
    id: str
    name: str
    channel_type: ChannelType
    description: str = ""
    config: ChannelConfig = field(default_factory=ChannelConfig)
    status: ChannelStatus = ChannelStatus.ACTIVE
    enabled: bool = True
    
    # Connection settings
    endpoint: str = ""  # URL, email, phone, etc.
    credentials: Dict[str, str] = field(default_factory=dict)
    
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Rate limiting
    notifications_this_minute: int = 0
    notifications_this_hour: int = 0
    last_notification_at: Optional[datetime] = None
    minute_reset_at: Optional[datetime] = None
    hour_reset_at: Optional[datetime] = None
    
    # Statistics
    total_notifications: int = 0
    successful_notifications: int = 0
    failed_notifications: int = 0
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    
    # Results history
    results: List[NotificationResult] = field(default_factory=list)
    
    def should_accept_alert(self, alert: Alert) -> bool:
        """Check if channel should accept this alert"""
        if not self.enabled:
            return False
        
        if self.status != ChannelStatus.ACTIVE:
            return False
        
        # Severity filter
        if alert.severity.value > self.config.min_severity.value:
            return False
        
        # Category filter
        if self.config.categories and alert.category.value not in self.config.categories:
            return False
        
        # Source filter
        if self.config.sources and alert.source not in self.config.sources:
            return False
        
        # Label filter
        for key, value in self.config.labels.items():
            if alert.labels.get(key) != value:
                return False
        
        return True
    
    def check_rate_limit(self) -> bool:
        """Check if rate limit allows notification"""
        now = datetime.now()
        
        # Reset minute counter
        if self.minute_reset_at is None or now >= self.minute_reset_at:
            self.notifications_this_minute = 0
            self.minute_reset_at = now + timedelta(minutes=1)
        
        # Reset hour counter
        if self.hour_reset_at is None or now >= self.hour_reset_at:
            self.notifications_this_hour = 0
            self.hour_reset_at = now + timedelta(hours=1)
        
        # Check limits
        if self.notifications_this_minute >= self.config.rate_limit_per_minute:
            return False
        
        if self.notifications_this_hour >= self.config.rate_limit_per_hour:
            return False
        
        return True
    
    def record_notification(self, result: NotificationResult) -> None:
        """Record notification result"""
        self.total_notifications += 1
        self.notifications_this_minute += 1
        self.notifications_this_hour += 1
        self.last_notification_at = datetime.now()
        
        if result.success:
            self.successful_notifications += 1
        else:
            self.failed_notifications += 1
            self.last_error = result.error
            self.last_error_at = datetime.now()
            
            # Set error status after multiple failures
            if self.failed_notifications > 3 and self.successful_notifications == 0:
                self.status = ChannelStatus.ERROR
        
        # Keep last 100 results
        self.results.append(result)
        if len(self.results) > 100:
            self.results = self.results[-100:]
        
        self.updated_at = datetime.now()
    
    def get_success_rate(self) -> float:
        """Get notification success rate"""
        if self.total_notifications == 0:
            return 1.0
        return self.successful_notifications / self.total_notifications
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "channel_type": self.channel_type.value,
            "description": self.description,
            "config": self.config.to_dict(),
            "status": self.status.value,
            "enabled": self.enabled,
            "endpoint": self.endpoint,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_notification_at": self.last_notification_at.isoformat() if self.last_notification_at else None,
            "total_notifications": self.total_notifications,
            "successful_notifications": self.successful_notifications,
            "failed_notifications": self.failed_notifications,
            "success_rate": self.get_success_rate(),
            "last_error": self.last_error,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None
        }


class ChannelManager:
    """Manages notification channels"""
    
    def __init__(self):
        self.channels: Dict[str, NotificationChannel] = {}
        self._senders: Dict[ChannelType, Callable] = {}
        self._init_builtin_senders()
        self._init_builtin_channels()
    
    def _init_builtin_senders(self) -> None:
        """Initialize built-in notification senders"""
        
        def send_log(channel: NotificationChannel, alert: Alert) -> NotificationResult:
            """Send to log"""
            print(f"[{channel.name}] Alert: {alert.name} - {alert.message}")
            return NotificationResult(
                channel_id=channel.id,
                alert_id=alert.id,
                success=True,
                timestamp=datetime.now()
            )
        
        def send_webhook(channel: NotificationChannel, alert: Alert) -> NotificationResult:
            """Send to webhook (simulated)"""
            # In production, this would make an HTTP POST
            return NotificationResult(
                channel_id=channel.id,
                alert_id=alert.id,
                success=True,
                timestamp=datetime.now(),
                response={"status": "delivered"}
            )
        
        def send_email(channel: NotificationChannel, alert: Alert) -> NotificationResult:
            """Send email (simulated)"""
            # In production, this would send an email
            return NotificationResult(
                channel_id=channel.id,
                alert_id=alert.id,
                success=True,
                timestamp=datetime.now(),
                response={"message_id": f"msg_{uuid.uuid4().hex[:8]}"}
            )
        
        def send_slack(channel: NotificationChannel, alert: Alert) -> NotificationResult:
            """Send to Slack (simulated)"""
            # In production, this would post to Slack API
            return NotificationResult(
                channel_id=channel.id,
                alert_id=alert.id,
                success=True,
                timestamp=datetime.now(),
                response={"ts": datetime.now().timestamp()}
            )
        
        def send_pagerduty(channel: NotificationChannel, alert: Alert) -> NotificationResult:
            """Send to PagerDuty (simulated)"""
            return NotificationResult(
                channel_id=channel.id,
                alert_id=alert.id,
                success=True,
                timestamp=datetime.now(),
                response={"incident_key": f"inc_{uuid.uuid4().hex[:8]}"}
            )
        
        self._senders = {
            ChannelType.LOG: send_log,
            ChannelType.WEBHOOK: send_webhook,
            ChannelType.EMAIL: send_email,
            ChannelType.SLACK: send_slack,
            ChannelType.PAGERDUTY: send_pagerduty
        }
    
    def _init_builtin_channels(self) -> None:
        """Initialize built-in channels"""
        
        # Log channel (always available)
        self.create_channel(
            name="Console Log",
            channel_type=ChannelType.LOG,
            description="Log alerts to console",
            endpoint="stdout"
        )
        
        # Email channel
        self.create_channel(
            name="Email Alerts",
            channel_type=ChannelType.EMAIL,
            description="Send alerts via email",
            endpoint="alerts@example.com",
            config=ChannelConfig(min_severity=AlertSeverity.MEDIUM)
        )
        
        # Slack channel
        self.create_channel(
            name="Slack #alerts",
            channel_type=ChannelType.SLACK,
            description="Post alerts to Slack channel",
            endpoint="https://hooks.slack.com/services/xxx",
            config=ChannelConfig(min_severity=AlertSeverity.HIGH)
        )
        
        # PagerDuty channel
        self.create_channel(
            name="PagerDuty On-Call",
            channel_type=ChannelType.PAGERDUTY,
            description="Page on-call engineer",
            endpoint="https://events.pagerduty.com/v2/enqueue",
            config=ChannelConfig(min_severity=AlertSeverity.CRITICAL)
        )
    
    def register_sender(
        self,
        channel_type: ChannelType,
        sender: Callable
    ) -> None:
        """Register a notification sender"""
        self._senders[channel_type] = sender
    
    def create_channel(
        self,
        name: str,
        channel_type: ChannelType,
        description: str = "",
        config: Optional[ChannelConfig] = None,
        endpoint: str = "",
        credentials: Optional[Dict[str, str]] = None,
        enabled: bool = True
    ) -> NotificationChannel:
        """Create a new channel"""
        channel_id = f"ch_{uuid.uuid4().hex[:8]}"
        
        channel = NotificationChannel(
            id=channel_id,
            name=name,
            channel_type=channel_type,
            description=description,
            config=config or ChannelConfig(),
            endpoint=endpoint,
            credentials=credentials or {},
            enabled=enabled
        )
        
        self.channels[channel_id] = channel
        return channel
    
    def get_channel(self, channel_id: str) -> Optional[NotificationChannel]:
        """Get channel by ID"""
        return self.channels.get(channel_id)
    
    def get_channel_by_name(self, name: str) -> Optional[NotificationChannel]:
        """Get channel by name"""
        for channel in self.channels.values():
            if channel.name == name:
                return channel
        return None
    
    def update_channel(
        self,
        channel_id: str,
        **kwargs
    ) -> Optional[NotificationChannel]:
        """Update channel"""
        channel = self.channels.get(channel_id)
        if not channel:
            return None
        
        for key, value in kwargs.items():
            if hasattr(channel, key):
                setattr(channel, key, value)
        
        channel.updated_at = datetime.now()
        return channel
    
    def delete_channel(self, channel_id: str) -> bool:
        """Delete channel"""
        if channel_id in self.channels:
            del self.channels[channel_id]
            return True
        return False
    
    def enable_channel(self, channel_id: str) -> bool:
        """Enable channel"""
        channel = self.channels.get(channel_id)
        if channel:
            channel.enabled = True
            channel.status = ChannelStatus.ACTIVE
            channel.updated_at = datetime.now()
            return True
        return False
    
    def disable_channel(self, channel_id: str) -> bool:
        """Disable channel"""
        channel = self.channels.get(channel_id)
        if channel:
            channel.enabled = False
            channel.status = ChannelStatus.INACTIVE
            channel.updated_at = datetime.now()
            return True
        return False
    
    def send_notification(
        self,
        channel_id: str,
        alert: Alert
    ) -> Optional[NotificationResult]:
        """Send notification through channel"""
        channel = self.channels.get(channel_id)
        if not channel:
            return None
        
        # Check if channel accepts this alert
        if not channel.should_accept_alert(alert):
            return None
        
        # Check rate limit
        if not channel.check_rate_limit():
            return NotificationResult(
                channel_id=channel_id,
                alert_id=alert.id,
                success=False,
                timestamp=datetime.now(),
                error="Rate limit exceeded"
            )
        
        # Get sender
        sender = self._senders.get(channel.channel_type)
        if not sender:
            return NotificationResult(
                channel_id=channel_id,
                alert_id=alert.id,
                success=False,
                timestamp=datetime.now(),
                error=f"No sender for channel type: {channel.channel_type.value}"
            )
        
        # Send notification
        try:
            result = sender(channel, alert)
            channel.record_notification(result)
            return result
        except Exception as e:
            result = NotificationResult(
                channel_id=channel_id,
                alert_id=alert.id,
                success=False,
                timestamp=datetime.now(),
                error=str(e)
            )
            channel.record_notification(result)
            return result
    
    def broadcast_alert(
        self,
        alert: Alert
    ) -> List[NotificationResult]:
        """Send alert to all applicable channels"""
        results = []
        for channel_id, channel in self.channels.items():
            if channel.enabled and channel.should_accept_alert(alert):
                result = self.send_notification(channel_id, alert)
                if result:
                    results.append(result)
        return results
    
    def get_channels(
        self,
        channel_type: Optional[ChannelType] = None,
        status: Optional[ChannelStatus] = None,
        enabled_only: bool = False
    ) -> List[NotificationChannel]:
        """Get channels with filtering"""
        channels = list(self.channels.values())
        
        if channel_type:
            channels = [c for c in channels if c.channel_type == channel_type]
        if status:
            channels = [c for c in channels if c.status == status]
        if enabled_only:
            channels = [c for c in channels if c.enabled]
        
        return channels
    
    def test_channel(self, channel_id: str) -> NotificationResult:
        """Test channel with dummy alert"""
        from .definitions import AlertCategory
        
        channel = self.channels.get(channel_id)
        if not channel:
            return NotificationResult(
                channel_id=channel_id,
                alert_id="test",
                success=False,
                timestamp=datetime.now(),
                error="Channel not found"
            )
        
        # Create test alert
        test_alert = Alert(
            id="test_alert",
            name="Test Alert",
            description="This is a test notification",
            severity=AlertSeverity.INFO,
            category=AlertCategory.CUSTOM,
            message="Testing notification channel"
        )
        
        sender = self._senders.get(channel.channel_type)
        if not sender:
            return NotificationResult(
                channel_id=channel_id,
                alert_id="test",
                success=False,
                timestamp=datetime.now(),
                error=f"No sender for channel type: {channel.channel_type.value}"
            )
        
        try:
            return sender(channel, test_alert)
        except Exception as e:
            return NotificationResult(
                channel_id=channel_id,
                alert_id="test",
                success=False,
                timestamp=datetime.now(),
                error=str(e)
            )
    
    def get_statistics(self) -> dict:
        """Get channel statistics"""
        total_notifications = 0
        total_successful = 0
        by_type = {}
        by_status = {}
        
        for channel in self.channels.values():
            total_notifications += channel.total_notifications
            total_successful += channel.successful_notifications
            by_type[channel.channel_type.value] = by_type.get(channel.channel_type.value, 0) + 1
            by_status[channel.status.value] = by_status.get(channel.status.value, 0) + 1
        
        return {
            "total_channels": len(self.channels),
            "enabled_channels": len([c for c in self.channels.values() if c.enabled]),
            "total_notifications": total_notifications,
            "total_successful": total_successful,
            "success_rate": total_successful / total_notifications if total_notifications > 0 else 1.0,
            "by_type": by_type,
            "by_status": by_status,
            "registered_senders": len(self._senders)
        }


# Global channel manager instance
_channel_manager: Optional[ChannelManager] = None


def get_channel_manager() -> ChannelManager:
    """Get or create the global channel manager"""
    global _channel_manager
    if _channel_manager is None:
        _channel_manager = ChannelManager()
    return _channel_manager
