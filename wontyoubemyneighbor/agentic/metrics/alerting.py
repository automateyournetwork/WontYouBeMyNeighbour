"""
Alerting System

Provides:
- Alert rules
- Condition evaluation
- Alert management
- Notification support
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from enum import Enum


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertCondition(Enum):
    """Alert condition types"""
    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    GREATER_EQUAL = "gte"
    LESS_EQUAL = "lte"
    EQUAL = "eq"
    NOT_EQUAL = "neq"
    ABSENT = "absent"
    PRESENT = "present"


class AlertStatus(Enum):
    """Alert status"""
    PENDING = "pending"
    FIRING = "firing"
    RESOLVED = "resolved"
    SILENCED = "silenced"


@dataclass
class Alert:
    """Represents an alert"""

    id: str
    rule_id: str
    name: str
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.FIRING
    message: str = ""
    metric_name: str = ""
    metric_value: Optional[float] = None
    threshold: Optional[float] = None
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: Optional[datetime] = None
    last_evaluated_at: datetime = field(default_factory=datetime.now)
    notified: bool = False
    notification_count: int = 0

    @property
    def duration_seconds(self) -> int:
        """Get alert duration"""
        end = self.ended_at or datetime.now()
        return int((end - self.started_at).total_seconds())

    @property
    def is_active(self) -> bool:
        """Check if alert is active"""
        return self.status in (AlertStatus.FIRING, AlertStatus.PENDING)

    def resolve(self) -> None:
        """Resolve the alert"""
        self.status = AlertStatus.RESOLVED
        self.ended_at = datetime.now()

    def silence(self) -> None:
        """Silence the alert"""
        self.status = AlertStatus.SILENCED

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "name": self.name,
            "severity": self.severity.value,
            "status": self.status.value,
            "message": self.message,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "labels": self.labels,
            "annotations": self.annotations,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "notified": self.notified,
            "notification_count": self.notification_count
        }


@dataclass
class AlertRule:
    """Alert rule definition"""

    id: str
    name: str
    metric_name: str
    condition: AlertCondition
    threshold: float
    severity: AlertSeverity = AlertSeverity.WARNING
    description: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    for_duration: timedelta = field(default_factory=lambda: timedelta(minutes=0))
    repeat_interval: timedelta = field(default_factory=lambda: timedelta(hours=4))
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Tracking
    last_evaluated_at: Optional[datetime] = None
    last_fired_at: Optional[datetime] = None
    consecutive_violations: int = 0

    def evaluate(self, value: Optional[float]) -> bool:
        """Evaluate if condition is met"""
        if value is None:
            if self.condition == AlertCondition.ABSENT:
                return True
            elif self.condition == AlertCondition.PRESENT:
                return False
            return False

        if self.condition == AlertCondition.ABSENT:
            return False
        elif self.condition == AlertCondition.PRESENT:
            return True
        elif self.condition == AlertCondition.GREATER_THAN:
            return value > self.threshold
        elif self.condition == AlertCondition.LESS_THAN:
            return value < self.threshold
        elif self.condition == AlertCondition.GREATER_EQUAL:
            return value >= self.threshold
        elif self.condition == AlertCondition.LESS_EQUAL:
            return value <= self.threshold
        elif self.condition == AlertCondition.EQUAL:
            return value == self.threshold
        elif self.condition == AlertCondition.NOT_EQUAL:
            return value != self.threshold

        return False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "metric_name": self.metric_name,
            "condition": self.condition.value,
            "threshold": self.threshold,
            "severity": self.severity.value,
            "description": self.description,
            "labels": self.labels,
            "annotations": self.annotations,
            "enabled": self.enabled,
            "for_duration_seconds": self.for_duration.total_seconds(),
            "repeat_interval_seconds": self.repeat_interval.total_seconds(),
            "created_at": self.created_at.isoformat(),
            "last_evaluated_at": self.last_evaluated_at.isoformat() if self.last_evaluated_at else None,
            "last_fired_at": self.last_fired_at.isoformat() if self.last_fired_at else None,
            "consecutive_violations": self.consecutive_violations
        }


class AlertManager:
    """Manages alerts and alert rules"""

    def __init__(self):
        self.rules: Dict[str, AlertRule] = {}
        self.alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        self._max_history = 1000
        self._notification_handlers: List[Callable[[Alert], None]] = []
        self._metric_getter: Optional[Callable[[str, Dict[str, str]], Optional[float]]] = None

    def create_rule(
        self,
        name: str,
        metric_name: str,
        condition: AlertCondition,
        threshold: float,
        severity: AlertSeverity = AlertSeverity.WARNING,
        description: str = "",
        labels: Optional[Dict[str, str]] = None,
        for_duration: Optional[timedelta] = None,
        repeat_interval: Optional[timedelta] = None
    ) -> AlertRule:
        """Create an alert rule"""
        rule_id = f"rule_{uuid.uuid4().hex[:8]}"

        rule = AlertRule(
            id=rule_id,
            name=name,
            metric_name=metric_name,
            condition=condition,
            threshold=threshold,
            severity=severity,
            description=description,
            labels=labels or {},
            for_duration=for_duration or timedelta(minutes=0),
            repeat_interval=repeat_interval or timedelta(hours=4)
        )

        self.rules[rule_id] = rule
        return rule

    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """Get rule by ID"""
        return self.rules.get(rule_id)

    def update_rule(
        self,
        rule_id: str,
        **kwargs
    ) -> Optional[AlertRule]:
        """Update an alert rule"""
        rule = self.rules.get(rule_id)
        if not rule:
            return None

        for key, value in kwargs.items():
            if hasattr(rule, key):
                setattr(rule, key, value)

        rule.updated_at = datetime.now()
        return rule

    def delete_rule(self, rule_id: str) -> bool:
        """Delete an alert rule"""
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False

    def enable_rule(self, rule_id: str) -> bool:
        """Enable an alert rule"""
        rule = self.rules.get(rule_id)
        if rule:
            rule.enabled = True
            return True
        return False

    def disable_rule(self, rule_id: str) -> bool:
        """Disable an alert rule"""
        rule = self.rules.get(rule_id)
        if rule:
            rule.enabled = False
            return True
        return False

    def set_metric_getter(
        self,
        getter: Callable[[str, Dict[str, str]], Optional[float]]
    ) -> None:
        """Set function to get metric values"""
        self._metric_getter = getter

    def evaluate_rule(self, rule_id: str, value: Optional[float] = None) -> Optional[Alert]:
        """Evaluate a single rule"""
        rule = self.rules.get(rule_id)
        if not rule or not rule.enabled:
            return None

        # Get metric value if not provided
        if value is None and self._metric_getter:
            value = self._metric_getter(rule.metric_name, rule.labels)

        rule.last_evaluated_at = datetime.now()
        condition_met = rule.evaluate(value)

        if condition_met:
            rule.consecutive_violations += 1

            # Check for_duration
            if rule.for_duration.total_seconds() > 0:
                required_violations = max(1, int(rule.for_duration.total_seconds() / 60))
                if rule.consecutive_violations < required_violations:
                    return None

            # Find existing alert
            existing = self._find_existing_alert(rule.id)

            if existing:
                existing.last_evaluated_at = datetime.now()
                existing.metric_value = value
                return existing
            else:
                # Create new alert
                alert = self._create_alert(rule, value)
                rule.last_fired_at = datetime.now()
                return alert
        else:
            rule.consecutive_violations = 0
            # Resolve existing alert
            existing = self._find_existing_alert(rule.id)
            if existing:
                existing.resolve()
                self._archive_alert(existing)
            return None

    def evaluate_all(self) -> List[Alert]:
        """Evaluate all enabled rules"""
        new_alerts = []
        for rule in self.rules.values():
            if rule.enabled:
                alert = self.evaluate_rule(rule.id)
                if alert and alert.status == AlertStatus.FIRING:
                    new_alerts.append(alert)
        return new_alerts

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get alert by ID"""
        return self.alerts.get(alert_id)

    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts"""
        return [a for a in self.alerts.values() if a.is_active]

    def get_alerts_by_severity(self, severity: AlertSeverity) -> List[Alert]:
        """Get alerts by severity"""
        return [a for a in self.alerts.values() if a.severity == severity and a.is_active]

    def resolve_alert(self, alert_id: str) -> bool:
        """Manually resolve an alert"""
        alert = self.alerts.get(alert_id)
        if alert:
            alert.resolve()
            self._archive_alert(alert)
            return True
        return False

    def silence_alert(self, alert_id: str) -> bool:
        """Silence an alert"""
        alert = self.alerts.get(alert_id)
        if alert:
            alert.silence()
            return True
        return False

    def get_alert_history(self, limit: int = 100) -> List[Alert]:
        """Get alert history"""
        return sorted(
            self.alert_history,
            key=lambda a: a.started_at,
            reverse=True
        )[:limit]

    def add_notification_handler(
        self,
        handler: Callable[[Alert], None]
    ) -> None:
        """Add notification handler"""
        self._notification_handlers.append(handler)

    def get_rules(self, enabled_only: bool = False) -> List[AlertRule]:
        """Get all rules"""
        rules = list(self.rules.values())
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        return rules

    def get_statistics(self) -> dict:
        """Get alert manager statistics"""
        active = self.get_active_alerts()
        by_severity = {}
        for alert in active:
            by_severity[alert.severity.value] = by_severity.get(alert.severity.value, 0) + 1

        return {
            "total_rules": len(self.rules),
            "enabled_rules": len([r for r in self.rules.values() if r.enabled]),
            "active_alerts": len(active),
            "total_alerts": len(self.alerts),
            "alert_history_count": len(self.alert_history),
            "by_severity": by_severity,
            "notification_handlers": len(self._notification_handlers)
        }

    def _create_alert(self, rule: AlertRule, value: Optional[float]) -> Alert:
        """Create alert from rule"""
        alert_id = f"alert_{uuid.uuid4().hex[:12]}"

        message = rule.description or f"{rule.name}: {rule.metric_name} {rule.condition.value} {rule.threshold}"
        if value is not None:
            message += f" (current: {value})"

        alert = Alert(
            id=alert_id,
            rule_id=rule.id,
            name=rule.name,
            severity=rule.severity,
            message=message,
            metric_name=rule.metric_name,
            metric_value=value,
            threshold=rule.threshold,
            labels=rule.labels.copy(),
            annotations=rule.annotations.copy()
        )

        self.alerts[alert_id] = alert
        self._notify(alert)
        return alert

    def _find_existing_alert(self, rule_id: str) -> Optional[Alert]:
        """Find existing alert for rule"""
        for alert in self.alerts.values():
            if alert.rule_id == rule_id and alert.is_active:
                return alert
        return None

    def _archive_alert(self, alert: Alert) -> None:
        """Archive a resolved alert"""
        self.alert_history.append(alert)
        if alert.id in self.alerts:
            del self.alerts[alert.id]

        # Trim history
        if len(self.alert_history) > self._max_history:
            self.alert_history = self.alert_history[-self._max_history // 2:]

    def _notify(self, alert: Alert) -> None:
        """Send notifications"""
        for handler in self._notification_handlers:
            try:
                handler(alert)
                alert.notified = True
                alert.notification_count += 1
            except Exception:
                pass


# Global alert manager instance
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Get or create the global alert manager"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager
