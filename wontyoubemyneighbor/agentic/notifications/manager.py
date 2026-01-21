"""
Notification Manager

Provides:
- Notification sending
- Delivery tracking
- User preferences
- Notification history
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
from enum import Enum

from .channels import ChannelType, DeliveryResult, get_channel_manager
from .templates import get_template_manager


class NotificationStatus(Enum):
    """Notification delivery status"""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NotificationPriority(Enum):
    """Notification priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationCategory(Enum):
    """Notification categories"""
    ALERT = "alert"
    SYSTEM = "system"
    SECURITY = "security"
    NETWORK = "network"
    USER = "user"
    REPORT = "report"
    MAINTENANCE = "maintenance"


@dataclass
class Notification:
    """Represents a notification"""

    id: str
    recipient: str
    subject: str
    body: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    category: NotificationCategory = NotificationCategory.SYSTEM
    status: NotificationStatus = NotificationStatus.PENDING
    channel_type: Optional[ChannelType] = None
    channel_id: Optional[str] = None
    template_id: Optional[str] = None
    template_variables: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    message_id: Optional[str] = None

    @property
    def is_pending(self) -> bool:
        return self.status == NotificationStatus.PENDING

    @property
    def can_retry(self) -> bool:
        return self.status == NotificationStatus.FAILED and self.retry_count < self.max_retries

    def mark_sent(self, message_id: Optional[str] = None) -> None:
        """Mark notification as sent"""
        self.status = NotificationStatus.SENT
        self.sent_at = datetime.now()
        if message_id:
            self.message_id = message_id

    def mark_delivered(self) -> None:
        """Mark notification as delivered"""
        self.status = NotificationStatus.DELIVERED
        self.delivered_at = datetime.now()

    def mark_failed(self, error: str) -> None:
        """Mark notification as failed"""
        self.status = NotificationStatus.FAILED
        self.failed_at = datetime.now()
        self.error_message = error
        self.retry_count += 1

    def cancel(self) -> None:
        """Cancel the notification"""
        self.status = NotificationStatus.CANCELLED

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "recipient": self.recipient,
            "subject": self.subject,
            "body": self.body,
            "priority": self.priority.value,
            "category": self.category.value,
            "status": self.status.value,
            "channel_type": self.channel_type.value if self.channel_type else None,
            "channel_id": self.channel_id,
            "template_id": self.template_id,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "failed_at": self.failed_at.isoformat() if self.failed_at else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "message_id": self.message_id
        }


@dataclass
class NotificationPreference:
    """User notification preferences"""

    user_id: str
    enabled: bool = True
    channels: Dict[str, bool] = field(default_factory=dict)  # channel_type -> enabled
    categories: Dict[str, bool] = field(default_factory=dict)  # category -> enabled
    priorities: Dict[str, bool] = field(default_factory=dict)  # priority -> enabled
    quiet_hours_start: Optional[int] = None  # Hour (0-23)
    quiet_hours_end: Optional[int] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    slack_user_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def is_channel_enabled(self, channel_type: ChannelType) -> bool:
        """Check if channel is enabled"""
        return self.channels.get(channel_type.value, True)

    def is_category_enabled(self, category: NotificationCategory) -> bool:
        """Check if category is enabled"""
        return self.categories.get(category.value, True)

    def is_priority_enabled(self, priority: NotificationPriority) -> bool:
        """Check if priority is enabled"""
        # Urgent always enabled
        if priority == NotificationPriority.URGENT:
            return True
        return self.priorities.get(priority.value, True)

    def is_quiet_hours(self) -> bool:
        """Check if currently in quiet hours"""
        if self.quiet_hours_start is None or self.quiet_hours_end is None:
            return False

        current_hour = datetime.now().hour
        if self.quiet_hours_start <= self.quiet_hours_end:
            return self.quiet_hours_start <= current_hour < self.quiet_hours_end
        else:
            # Spans midnight
            return current_hour >= self.quiet_hours_start or current_hour < self.quiet_hours_end

    def should_notify(
        self,
        channel_type: ChannelType,
        category: NotificationCategory,
        priority: NotificationPriority
    ) -> bool:
        """Check if notification should be sent based on preferences"""
        if not self.enabled:
            return False

        # Urgent bypasses quiet hours
        if priority == NotificationPriority.URGENT:
            return True

        if self.is_quiet_hours():
            return False

        return (
            self.is_channel_enabled(channel_type) and
            self.is_category_enabled(category) and
            self.is_priority_enabled(priority)
        )

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "enabled": self.enabled,
            "channels": self.channels,
            "categories": self.categories,
            "priorities": self.priorities,
            "quiet_hours_start": self.quiet_hours_start,
            "quiet_hours_end": self.quiet_hours_end,
            "email": self.email,
            "phone": self.phone,
            "slack_user_id": self.slack_user_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class NotificationManager:
    """Manages notifications"""

    def __init__(self):
        self.notifications: Dict[str, Notification] = {}
        self.preferences: Dict[str, NotificationPreference] = {}
        self.history: List[Notification] = []
        self._max_history = 10000
        self._channel_manager = get_channel_manager()
        self._template_manager = get_template_manager()

    def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        channel_id: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        category: NotificationCategory = NotificationCategory.SYSTEM,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Notification:
        """Send a notification"""
        notification_id = f"notif_{uuid.uuid4().hex[:12]}"

        channel = self._channel_manager.get_channel(channel_id)
        channel_type = channel.channel_type if channel else None

        notification = Notification(
            id=notification_id,
            recipient=recipient,
            subject=subject,
            body=body,
            priority=priority,
            category=category,
            channel_type=channel_type,
            channel_id=channel_id,
            metadata=metadata or {}
        )

        self.notifications[notification_id] = notification

        # Send through channel
        result = self._channel_manager.send(channel_id, recipient, subject, body)

        if result.success:
            notification.mark_sent(result.message_id)
            notification.mark_delivered()
        else:
            notification.mark_failed(result.error or "Unknown error")

        return notification

    def send_with_template(
        self,
        recipient: str,
        template_name: str,
        variables: Dict[str, Any],
        channel_id: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        category: NotificationCategory = NotificationCategory.SYSTEM,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Notification]:
        """Send notification using a template"""
        rendered = self._template_manager.render_by_name(template_name, variables)
        if not rendered:
            return None

        notification = self.send(
            recipient=recipient,
            subject=rendered["subject"],
            body=rendered["body"],
            channel_id=channel_id,
            priority=priority,
            category=category,
            metadata=metadata
        )

        # Store template info
        template = self._template_manager.get_template_by_name(template_name)
        if template:
            notification.template_id = template.id
            notification.template_variables = variables

        return notification

    def send_to_user(
        self,
        user_id: str,
        subject: str,
        body: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        category: NotificationCategory = NotificationCategory.SYSTEM,
        preferred_channel: Optional[ChannelType] = None
    ) -> List[Notification]:
        """Send notification to user based on preferences"""
        preferences = self.get_preferences(user_id)
        notifications = []

        # Get available channels
        channels = self._channel_manager.get_channels(enabled_only=True)

        for channel in channels:
            if preferred_channel and channel.channel_type != preferred_channel:
                continue

            if preferences.should_notify(channel.channel_type, category, priority):
                # Get recipient based on channel type
                recipient = self._get_recipient_for_channel(preferences, channel.channel_type)
                if recipient:
                    notification = self.send(
                        recipient=recipient,
                        subject=subject,
                        body=body,
                        channel_id=channel.id,
                        priority=priority,
                        category=category,
                        metadata={"user_id": user_id}
                    )
                    notifications.append(notification)

                    # Only send to preferred channel if specified
                    if preferred_channel:
                        break

        return notifications

    def broadcast(
        self,
        subject: str,
        body: str,
        user_ids: List[str],
        priority: NotificationPriority = NotificationPriority.NORMAL,
        category: NotificationCategory = NotificationCategory.SYSTEM
    ) -> Dict[str, List[Notification]]:
        """Broadcast notification to multiple users"""
        results = {}
        for user_id in user_ids:
            results[user_id] = self.send_to_user(
                user_id=user_id,
                subject=subject,
                body=body,
                priority=priority,
                category=category
            )
        return results

    def retry(self, notification_id: str) -> Optional[Notification]:
        """Retry a failed notification"""
        notification = self.notifications.get(notification_id)
        if not notification or not notification.can_retry:
            return None

        notification.status = NotificationStatus.PENDING

        if notification.channel_id:
            result = self._channel_manager.send(
                notification.channel_id,
                notification.recipient,
                notification.subject,
                notification.body
            )

            if result.success:
                notification.mark_sent(result.message_id)
                notification.mark_delivered()
            else:
                notification.mark_failed(result.error or "Unknown error")

        return notification

    def cancel(self, notification_id: str) -> bool:
        """Cancel a pending notification"""
        notification = self.notifications.get(notification_id)
        if notification and notification.is_pending:
            notification.cancel()
            return True
        return False

    def get_notification(self, notification_id: str) -> Optional[Notification]:
        """Get notification by ID"""
        return self.notifications.get(notification_id)

    def get_notifications(
        self,
        recipient: Optional[str] = None,
        status: Optional[NotificationStatus] = None,
        category: Optional[NotificationCategory] = None,
        priority: Optional[NotificationPriority] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Notification]:
        """Get notifications with filtering"""
        notifications = list(self.notifications.values())

        if recipient:
            notifications = [n for n in notifications if n.recipient == recipient]
        if status:
            notifications = [n for n in notifications if n.status == status]
        if category:
            notifications = [n for n in notifications if n.category == category]
        if priority:
            notifications = [n for n in notifications if n.priority == priority]
        if since:
            notifications = [n for n in notifications if n.created_at >= since]

        notifications.sort(key=lambda n: n.created_at, reverse=True)
        return notifications[:limit]

    def get_pending(self) -> List[Notification]:
        """Get pending notifications"""
        return [n for n in self.notifications.values() if n.is_pending]

    def get_failed(self, retriable_only: bool = False) -> List[Notification]:
        """Get failed notifications"""
        failed = [n for n in self.notifications.values() if n.status == NotificationStatus.FAILED]
        if retriable_only:
            failed = [n for n in failed if n.can_retry]
        return failed

    # Preferences management

    def get_preferences(self, user_id: str) -> NotificationPreference:
        """Get or create user preferences"""
        if user_id not in self.preferences:
            self.preferences[user_id] = NotificationPreference(user_id=user_id)
        return self.preferences[user_id]

    def update_preferences(
        self,
        user_id: str,
        **kwargs
    ) -> NotificationPreference:
        """Update user preferences"""
        preferences = self.get_preferences(user_id)

        for key, value in kwargs.items():
            if hasattr(preferences, key):
                setattr(preferences, key, value)

        preferences.updated_at = datetime.now()
        return preferences

    def set_channel_preference(
        self,
        user_id: str,
        channel_type: ChannelType,
        enabled: bool
    ) -> NotificationPreference:
        """Set channel preference for user"""
        preferences = self.get_preferences(user_id)
        preferences.channels[channel_type.value] = enabled
        preferences.updated_at = datetime.now()
        return preferences

    def set_category_preference(
        self,
        user_id: str,
        category: NotificationCategory,
        enabled: bool
    ) -> NotificationPreference:
        """Set category preference for user"""
        preferences = self.get_preferences(user_id)
        preferences.categories[category.value] = enabled
        preferences.updated_at = datetime.now()
        return preferences

    def set_quiet_hours(
        self,
        user_id: str,
        start_hour: Optional[int],
        end_hour: Optional[int]
    ) -> NotificationPreference:
        """Set quiet hours for user"""
        preferences = self.get_preferences(user_id)
        preferences.quiet_hours_start = start_hour
        preferences.quiet_hours_end = end_hour
        preferences.updated_at = datetime.now()
        return preferences

    def _get_recipient_for_channel(
        self,
        preferences: NotificationPreference,
        channel_type: ChannelType
    ) -> Optional[str]:
        """Get recipient address for channel type"""
        if channel_type == ChannelType.EMAIL:
            return preferences.email
        elif channel_type == ChannelType.SMS:
            return preferences.phone
        elif channel_type == ChannelType.SLACK:
            return preferences.slack_user_id
        else:
            return preferences.user_id

    def archive_notification(self, notification_id: str) -> bool:
        """Archive a notification"""
        notification = self.notifications.get(notification_id)
        if notification:
            self.history.append(notification)
            del self.notifications[notification_id]

            # Trim history
            if len(self.history) > self._max_history:
                self.history = self.history[-self._max_history // 2:]

            return True
        return False

    def get_history(
        self,
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Notification]:
        """Get notification history"""
        history = self.history
        if user_id:
            history = [n for n in history if n.metadata.get("user_id") == user_id]
        return sorted(history, key=lambda n: n.created_at, reverse=True)[:limit]

    def cleanup_old_notifications(self, days: int = 30) -> int:
        """Archive old delivered/failed notifications"""
        cutoff = datetime.now() - timedelta(days=days)
        archived = 0

        for notification_id in list(self.notifications.keys()):
            notification = self.notifications[notification_id]
            if notification.status in (NotificationStatus.DELIVERED, NotificationStatus.FAILED, NotificationStatus.CANCELLED):
                if notification.created_at < cutoff:
                    self.archive_notification(notification_id)
                    archived += 1

        return archived

    def get_statistics(self) -> dict:
        """Get notification statistics"""
        by_status = {}
        by_category = {}
        by_priority = {}

        for notification in self.notifications.values():
            by_status[notification.status.value] = by_status.get(notification.status.value, 0) + 1
            by_category[notification.category.value] = by_category.get(notification.category.value, 0) + 1
            by_priority[notification.priority.value] = by_priority.get(notification.priority.value, 0) + 1

        delivered = by_status.get("delivered", 0)
        failed = by_status.get("failed", 0)
        total = delivered + failed

        return {
            "total_notifications": len(self.notifications),
            "total_preferences": len(self.preferences),
            "history_count": len(self.history),
            "by_status": by_status,
            "by_category": by_category,
            "by_priority": by_priority,
            "delivery_rate": delivered / total if total > 0 else 1.0,
            "pending_count": len(self.get_pending()),
            "failed_count": len(self.get_failed())
        }


# Global notification manager instance
_notification_manager: Optional[NotificationManager] = None


def get_notification_manager() -> NotificationManager:
    """Get or create the global notification manager"""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager
