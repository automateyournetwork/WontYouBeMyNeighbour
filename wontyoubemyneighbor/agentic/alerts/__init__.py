"""
Alert Management Module

Provides:
- Alert definitions
- Notification channels
- Escalation policies
- Alert routing
"""

from .definitions import (
    Alert,
    AlertSeverity,
    AlertStatus,
    AlertCategory,
    AlertConfig,
    AlertManager,
    get_alert_manager
)
from .channels import (
    NotificationChannel,
    ChannelType,
    ChannelStatus,
    ChannelConfig,
    ChannelManager,
    get_channel_manager
)
from .escalation import (
    EscalationPolicy,
    EscalationLevel,
    EscalationTrigger,
    EscalationAction,
    EscalationManager,
    get_escalation_manager
)

__all__ = [
    # Definitions
    "Alert",
    "AlertSeverity",
    "AlertStatus",
    "AlertCategory",
    "AlertConfig",
    "AlertManager",
    "get_alert_manager",
    # Channels
    "NotificationChannel",
    "ChannelType",
    "ChannelStatus",
    "ChannelConfig",
    "ChannelManager",
    "get_channel_manager",
    # Escalation
    "EscalationPolicy",
    "EscalationLevel",
    "EscalationTrigger",
    "EscalationAction",
    "EscalationManager",
    "get_escalation_manager"
]
