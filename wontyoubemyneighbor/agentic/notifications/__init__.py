"""
Notification System

Provides:
- Multi-channel notifications (email, Slack, webhook, SMS)
- Notification templates
- Delivery tracking
- User preferences
"""

from .channels import (
    NotificationChannel,
    ChannelType,
    ChannelConfig,
    EmailChannel,
    SlackChannel,
    WebhookChannel,
    SMSChannel,
    ChannelManager,
    get_channel_manager
)

from .templates import (
    NotificationTemplate,
    TemplateVariable,
    TemplateManager,
    get_template_manager
)

from .manager import (
    Notification,
    NotificationStatus,
    NotificationPriority,
    NotificationPreference,
    NotificationManager,
    get_notification_manager
)

__all__ = [
    # Channels
    "NotificationChannel",
    "ChannelType",
    "ChannelConfig",
    "EmailChannel",
    "SlackChannel",
    "WebhookChannel",
    "SMSChannel",
    "ChannelManager",
    "get_channel_manager",
    # Templates
    "NotificationTemplate",
    "TemplateVariable",
    "TemplateManager",
    "get_template_manager",
    # Manager
    "Notification",
    "NotificationStatus",
    "NotificationPriority",
    "NotificationPreference",
    "NotificationManager",
    "get_notification_manager"
]
