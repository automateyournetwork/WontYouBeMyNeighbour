"""
Alert Definitions

Provides:
- Alert definitions
- Severity levels
- Alert lifecycle management
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from enum import Enum


class AlertSeverity(Enum):
    """Alert severity levels"""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    INFO = 5


class AlertStatus(Enum):
    """Alert status"""
    ACTIVE = "active"  # Alert is active
    ACKNOWLEDGED = "acknowledged"  # Seen but not resolved
    RESOLVED = "resolved"  # Issue resolved
    SUPPRESSED = "suppressed"  # Temporarily suppressed
    EXPIRED = "expired"  # Auto-expired
    ESCALATED = "escalated"  # Escalated to higher level


class AlertCategory(Enum):
    """Alert categories"""
    SYSTEM = "system"  # System alerts
    NETWORK = "network"  # Network alerts
    PROTOCOL = "protocol"  # Protocol alerts
    SECURITY = "security"  # Security alerts
    PERFORMANCE = "performance"  # Performance alerts
    CONFIGURATION = "configuration"  # Config alerts
    CAPACITY = "capacity"  # Capacity alerts
    CUSTOM = "custom"  # Custom alerts


@dataclass
class AlertConfig:
    """Alert configuration"""
    
    auto_resolve_hours: int = 24  # Auto-resolve after N hours
    auto_expire_hours: int = 168  # Auto-expire after 7 days
    flap_threshold: int = 5  # Flapping detection threshold
    flap_window_minutes: int = 60  # Flapping detection window
    dedupe_window_minutes: int = 5  # Deduplication window
    suppress_duration_minutes: int = 60  # Default suppress duration
    notification_delay_seconds: int = 0  # Delay before notification
    repeat_notification_minutes: int = 60  # Repeat notification interval
    max_notifications: int = 10  # Max notifications per alert
    tags: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "auto_resolve_hours": self.auto_resolve_hours,
            "auto_expire_hours": self.auto_expire_hours,
            "flap_threshold": self.flap_threshold,
            "flap_window_minutes": self.flap_window_minutes,
            "dedupe_window_minutes": self.dedupe_window_minutes,
            "suppress_duration_minutes": self.suppress_duration_minutes,
            "notification_delay_seconds": self.notification_delay_seconds,
            "repeat_notification_minutes": self.repeat_notification_minutes,
            "max_notifications": self.max_notifications,
            "tags": self.tags,
            "extra": self.extra
        }


@dataclass
class AlertEvent:
    """Alert lifecycle event"""
    
    timestamp: datetime
    event_type: str  # created, acknowledged, resolved, etc.
    user: Optional[str] = None
    note: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "user": self.user,
            "note": self.note,
            "metadata": self.metadata
        }


@dataclass
class Alert:
    """Alert definition"""
    
    id: str
    name: str
    description: str
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.ACTIVE
    category: AlertCategory = AlertCategory.CUSTOM
    config: AlertConfig = field(default_factory=AlertConfig)
    
    # Source information
    source: str = ""  # Source system/component
    source_id: Optional[str] = None  # Source identifier
    
    # Alert content
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    
    # Lifecycle
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    suppress_until: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    # Tracking
    events: List[AlertEvent] = field(default_factory=list)
    notification_count: int = 0
    last_notified_at: Optional[datetime] = None
    escalation_level: int = 0
    flap_count: int = 0
    
    # Related
    related_alerts: List[str] = field(default_factory=list)
    parent_alert_id: Optional[str] = None
    
    def __post_init__(self):
        # Add creation event
        self.events.append(AlertEvent(
            timestamp=self.created_at,
            event_type="created"
        ))
        
        # Set expiry
        if self.config.auto_expire_hours > 0:
            self.expires_at = self.created_at + timedelta(hours=self.config.auto_expire_hours)
    
    def acknowledge(self, user: str, note: str = "") -> None:
        """Acknowledge alert"""
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_at = datetime.now()
        self.acknowledged_by = user
        self.updated_at = datetime.now()
        
        self.events.append(AlertEvent(
            timestamp=datetime.now(),
            event_type="acknowledged",
            user=user,
            note=note
        ))
    
    def resolve(self, user: Optional[str] = None, note: str = "") -> None:
        """Resolve alert"""
        self.status = AlertStatus.RESOLVED
        self.resolved_at = datetime.now()
        self.resolved_by = user
        self.updated_at = datetime.now()
        
        self.events.append(AlertEvent(
            timestamp=datetime.now(),
            event_type="resolved",
            user=user,
            note=note
        ))
    
    def suppress(self, minutes: Optional[int] = None, user: Optional[str] = None) -> None:
        """Suppress alert"""
        duration = minutes or self.config.suppress_duration_minutes
        self.status = AlertStatus.SUPPRESSED
        self.suppress_until = datetime.now() + timedelta(minutes=duration)
        self.updated_at = datetime.now()
        
        self.events.append(AlertEvent(
            timestamp=datetime.now(),
            event_type="suppressed",
            user=user,
            metadata={"suppress_until": self.suppress_until.isoformat()}
        ))
    
    def escalate(self, level: Optional[int] = None) -> None:
        """Escalate alert"""
        self.escalation_level = level if level is not None else self.escalation_level + 1
        self.status = AlertStatus.ESCALATED
        self.updated_at = datetime.now()
        
        self.events.append(AlertEvent(
            timestamp=datetime.now(),
            event_type="escalated",
            metadata={"escalation_level": self.escalation_level}
        ))
    
    def reactivate(self, reason: str = "") -> None:
        """Reactivate alert"""
        if self.status in (AlertStatus.RESOLVED, AlertStatus.SUPPRESSED, AlertStatus.EXPIRED):
            self.status = AlertStatus.ACTIVE
            self.flap_count += 1
            self.updated_at = datetime.now()
            
            self.events.append(AlertEvent(
                timestamp=datetime.now(),
                event_type="reactivated",
                note=reason
            ))
    
    def record_notification(self) -> None:
        """Record notification sent"""
        self.notification_count += 1
        self.last_notified_at = datetime.now()
        self.updated_at = datetime.now()
    
    def is_expired(self) -> bool:
        """Check if alert is expired"""
        if self.expires_at and datetime.now() >= self.expires_at:
            return True
        return False
    
    def is_suppressed(self) -> bool:
        """Check if alert is currently suppressed"""
        if self.suppress_until and datetime.now() < self.suppress_until:
            return True
        return False
    
    def is_flapping(self) -> bool:
        """Check if alert is flapping"""
        if self.flap_count >= self.config.flap_threshold:
            return True
        return False
    
    def should_notify(self) -> bool:
        """Check if notification should be sent"""
        if self.status in (AlertStatus.RESOLVED, AlertStatus.SUPPRESSED, AlertStatus.EXPIRED):
            return False
        
        if self.notification_count >= self.config.max_notifications:
            return False
        
        if self.last_notified_at:
            repeat_interval = timedelta(minutes=self.config.repeat_notification_minutes)
            if datetime.now() - self.last_notified_at < repeat_interval:
                return False
        
        return True
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "severity": self.severity.value,
            "status": self.status.value,
            "category": self.category.value,
            "config": self.config.to_dict(),
            "source": self.source,
            "source_id": self.source_id,
            "message": self.message,
            "details": self.details,
            "labels": self.labels,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
            "suppress_until": self.suppress_until.isoformat() if self.suppress_until else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "events": [e.to_dict() for e in self.events[-10:]],  # Last 10 events
            "notification_count": self.notification_count,
            "last_notified_at": self.last_notified_at.isoformat() if self.last_notified_at else None,
            "escalation_level": self.escalation_level,
            "flap_count": self.flap_count,
            "related_alerts": self.related_alerts,
            "parent_alert_id": self.parent_alert_id,
            "is_flapping": self.is_flapping(),
            "is_suppressed": self.is_suppressed()
        }


class AlertManager:
    """Manages alerts"""
    
    def __init__(self):
        self.alerts: Dict[str, Alert] = {}
        self._handlers: Dict[str, Callable] = {}
        self._init_builtin_handlers()
    
    def _init_builtin_handlers(self) -> None:
        """Initialize built-in handlers"""
        
        def log_handler(alert: Alert) -> None:
            """Log alert"""
            print(f"[{alert.severity.name}] {alert.name}: {alert.message}")
        
        def auto_resolve_handler(alert: Alert) -> None:
            """Auto-resolve old alerts"""
            if alert.config.auto_resolve_hours > 0:
                age = datetime.now() - alert.created_at
                if age.total_seconds() / 3600 >= alert.config.auto_resolve_hours:
                    alert.resolve(note="Auto-resolved due to age")
        
        self._handlers = {
            "log": log_handler,
            "auto_resolve": auto_resolve_handler
        }
    
    def register_handler(self, name: str, handler: Callable) -> None:
        """Register alert handler"""
        self._handlers[name] = handler
    
    def create_alert(
        self,
        name: str,
        description: str,
        severity: AlertSeverity,
        category: AlertCategory = AlertCategory.CUSTOM,
        config: Optional[AlertConfig] = None,
        source: str = "",
        source_id: Optional[str] = None,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> Alert:
        """Create a new alert"""
        alert_id = f"alert_{uuid.uuid4().hex[:8]}"
        
        alert = Alert(
            id=alert_id,
            name=name,
            description=description,
            severity=severity,
            category=category,
            config=config or AlertConfig(),
            source=source,
            source_id=source_id,
            message=message,
            details=details or {},
            labels=labels or {}
        )
        
        self.alerts[alert_id] = alert
        return alert
    
    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get alert by ID"""
        return self.alerts.get(alert_id)
    
    def update_alert(self, alert_id: str, **kwargs) -> Optional[Alert]:
        """Update alert properties"""
        alert = self.alerts.get(alert_id)
        if not alert:
            return None
        
        for key, value in kwargs.items():
            if hasattr(alert, key):
                setattr(alert, key, value)
        
        alert.updated_at = datetime.now()
        return alert
    
    def delete_alert(self, alert_id: str) -> bool:
        """Delete alert"""
        if alert_id in self.alerts:
            del self.alerts[alert_id]
            return True
        return False
    
    def acknowledge_alert(
        self,
        alert_id: str,
        user: str,
        note: str = ""
    ) -> bool:
        """Acknowledge alert"""
        alert = self.alerts.get(alert_id)
        if alert:
            alert.acknowledge(user, note)
            return True
        return False
    
    def resolve_alert(
        self,
        alert_id: str,
        user: Optional[str] = None,
        note: str = ""
    ) -> bool:
        """Resolve alert"""
        alert = self.alerts.get(alert_id)
        if alert:
            alert.resolve(user, note)
            return True
        return False
    
    def suppress_alert(
        self,
        alert_id: str,
        minutes: Optional[int] = None,
        user: Optional[str] = None
    ) -> bool:
        """Suppress alert"""
        alert = self.alerts.get(alert_id)
        if alert:
            alert.suppress(minutes, user)
            return True
        return False
    
    def escalate_alert(
        self,
        alert_id: str,
        level: Optional[int] = None
    ) -> bool:
        """Escalate alert"""
        alert = self.alerts.get(alert_id)
        if alert:
            alert.escalate(level)
            return True
        return False
    
    def find_duplicate(
        self,
        name: str,
        source: str,
        source_id: Optional[str] = None,
        window_minutes: int = 5
    ) -> Optional[Alert]:
        """Find duplicate alert within window"""
        cutoff = datetime.now() - timedelta(minutes=window_minutes)
        
        for alert in self.alerts.values():
            if alert.status == AlertStatus.RESOLVED:
                continue
            if alert.created_at < cutoff:
                continue
            if alert.name == name and alert.source == source:
                if source_id is None or alert.source_id == source_id:
                    return alert
        
        return None
    
    def get_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        status: Optional[AlertStatus] = None,
        category: Optional[AlertCategory] = None,
        source: Optional[str] = None,
        label_key: Optional[str] = None,
        label_value: Optional[str] = None,
        active_only: bool = False
    ) -> List[Alert]:
        """Get alerts with filtering"""
        alerts = list(self.alerts.values())
        
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if status:
            alerts = [a for a in alerts if a.status == status]
        if category:
            alerts = [a for a in alerts if a.category == category]
        if source:
            alerts = [a for a in alerts if a.source == source]
        if label_key and label_value:
            alerts = [a for a in alerts if a.labels.get(label_key) == label_value]
        if active_only:
            alerts = [a for a in alerts if a.status == AlertStatus.ACTIVE]
        
        # Sort by severity then created_at
        alerts.sort(key=lambda a: (a.severity.value, -a.created_at.timestamp()))
        
        return alerts
    
    def get_active_count(self) -> Dict[str, int]:
        """Get count of active alerts by severity"""
        counts = {s.name: 0 for s in AlertSeverity}
        for alert in self.alerts.values():
            if alert.status == AlertStatus.ACTIVE:
                counts[alert.severity.name] += 1
        return counts
    
    def cleanup_expired(self) -> int:
        """Cleanup expired alerts"""
        expired = []
        for alert_id, alert in self.alerts.items():
            if alert.is_expired():
                alert.status = AlertStatus.EXPIRED
                expired.append(alert_id)
        return len(expired)
    
    def bulk_acknowledge(
        self,
        alert_ids: List[str],
        user: str,
        note: str = ""
    ) -> int:
        """Bulk acknowledge alerts"""
        count = 0
        for alert_id in alert_ids:
            if self.acknowledge_alert(alert_id, user, note):
                count += 1
        return count
    
    def bulk_resolve(
        self,
        alert_ids: List[str],
        user: Optional[str] = None,
        note: str = ""
    ) -> int:
        """Bulk resolve alerts"""
        count = 0
        for alert_id in alert_ids:
            if self.resolve_alert(alert_id, user, note):
                count += 1
        return count
    
    def get_statistics(self) -> dict:
        """Get alert statistics"""
        by_severity = {s.name: 0 for s in AlertSeverity}
        by_status = {s.value: 0 for s in AlertStatus}
        by_category = {c.value: 0 for c in AlertCategory}
        flapping_count = 0
        
        for alert in self.alerts.values():
            by_severity[alert.severity.name] += 1
            by_status[alert.status.value] += 1
            by_category[alert.category.value] += 1
            if alert.is_flapping():
                flapping_count += 1
        
        return {
            "total_alerts": len(self.alerts),
            "active_alerts": by_status.get("active", 0),
            "by_severity": by_severity,
            "by_status": by_status,
            "by_category": by_category,
            "flapping_alerts": flapping_count,
            "registered_handlers": len(self._handlers)
        }


# Global alert manager instance
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Get or create the global alert manager"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager
