"""
Audit Logger

Provides:
- Structured audit event logging
- Event categorization
- Context enrichment
- Real-time event emission
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from enum import Enum


class AuditEventType(Enum):
    """Types of audit events"""
    # Authentication events
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_LOGIN_FAILED = "auth.login_failed"
    AUTH_PASSWORD_CHANGE = "auth.password_change"
    AUTH_MFA_ENABLED = "auth.mfa_enabled"
    AUTH_MFA_DISABLED = "auth.mfa_disabled"
    AUTH_SESSION_EXPIRED = "auth.session_expired"

    # Authorization events
    AUTHZ_ACCESS_GRANTED = "authz.access_granted"
    AUTHZ_ACCESS_DENIED = "authz.access_denied"
    AUTHZ_ROLE_ASSIGNED = "authz.role_assigned"
    AUTHZ_ROLE_REVOKED = "authz.role_revoked"
    AUTHZ_PERMISSION_CHANGED = "authz.permission_changed"

    # API key events
    APIKEY_CREATED = "apikey.created"
    APIKEY_ROTATED = "apikey.rotated"
    APIKEY_REVOKED = "apikey.revoked"
    APIKEY_USED = "apikey.used"
    APIKEY_RATE_LIMITED = "apikey.rate_limited"

    # Resource events
    RESOURCE_CREATED = "resource.created"
    RESOURCE_UPDATED = "resource.updated"
    RESOURCE_DELETED = "resource.deleted"
    RESOURCE_ACCESSED = "resource.accessed"

    # Network events
    NETWORK_DEPLOYED = "network.deployed"
    NETWORK_STOPPED = "network.stopped"
    NETWORK_CONFIG_CHANGED = "network.config_changed"

    # Agent events
    AGENT_STARTED = "agent.started"
    AGENT_STOPPED = "agent.stopped"
    AGENT_CONFIG_CHANGED = "agent.config_changed"
    AGENT_ERROR = "agent.error"

    # Protocol events
    PROTOCOL_ENABLED = "protocol.enabled"
    PROTOCOL_DISABLED = "protocol.disabled"
    PROTOCOL_STATE_CHANGE = "protocol.state_change"

    # Admin events
    ADMIN_USER_CREATED = "admin.user_created"
    ADMIN_USER_DELETED = "admin.user_deleted"
    ADMIN_TENANT_CREATED = "admin.tenant_created"
    ADMIN_TENANT_DELETED = "admin.tenant_deleted"
    ADMIN_SETTINGS_CHANGED = "admin.settings_changed"

    # Security events
    SECURITY_THREAT_DETECTED = "security.threat_detected"
    SECURITY_POLICY_VIOLATED = "security.policy_violated"
    SECURITY_ANOMALY_DETECTED = "security.anomaly_detected"

    # System events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"
    SYSTEM_BACKUP = "system.backup"
    SYSTEM_RESTORE = "system.restore"

    # Custom events
    CUSTOM = "custom"


class AuditSeverity(Enum):
    """Severity levels for audit events"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Represents a single audit event"""

    id: str
    event_type: AuditEventType
    severity: AuditSeverity
    timestamp: datetime
    actor_id: Optional[str] = None  # User or service that caused the event
    actor_type: str = "user"  # user, service, system
    target_type: Optional[str] = None  # Type of resource affected
    target_id: Optional[str] = None  # ID of resource affected
    action: str = ""  # Human-readable action description
    outcome: str = "success"  # success, failure, error
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    tenant_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "action": self.action,
            "outcome": self.outcome,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "details": self.details,
            "tags": self.tags
        }


class AuditLogger:
    """Logs and manages audit events"""

    def __init__(self):
        self.events: List[AuditEvent] = []
        self._max_events = 100000
        self._listeners: List[Callable[[AuditEvent], None]] = []
        self._enabled = True
        self._min_severity = AuditSeverity.DEBUG

    def log(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity = AuditSeverity.INFO,
        actor_id: Optional[str] = None,
        actor_type: str = "user",
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        action: str = "",
        outcome: str = "success",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        tenant_id: Optional[str] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> AuditEvent:
        """Log an audit event"""
        if not self._enabled:
            return None

        # Check severity threshold
        severity_order = list(AuditSeverity)
        if severity_order.index(severity) < severity_order.index(self._min_severity):
            return None

        event = AuditEvent(
            id=f"evt_{uuid.uuid4().hex[:12]}",
            event_type=event_type,
            severity=severity,
            timestamp=datetime.now(),
            actor_id=actor_id,
            actor_type=actor_type,
            target_type=target_type,
            target_id=target_id,
            action=action,
            outcome=outcome,
            ip_address=ip_address,
            user_agent=user_agent,
            tenant_id=tenant_id,
            session_id=session_id,
            request_id=request_id,
            details=details or {},
            tags=tags or []
        )

        self.events.append(event)

        # Notify listeners
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass

        # Trim if needed
        if len(self.events) > self._max_events:
            self.events = self.events[-self._max_events // 2:]

        return event

    def log_auth(
        self,
        event_type: AuditEventType,
        user_id: str,
        success: bool = True,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        """Convenience method for authentication events"""
        return self.log(
            event_type=event_type,
            severity=AuditSeverity.INFO if success else AuditSeverity.WARNING,
            actor_id=user_id,
            actor_type="user",
            action=f"Authentication: {event_type.value}",
            outcome="success" if success else "failure",
            ip_address=ip_address,
            details=details,
            tags=["authentication"]
        )

    def log_access(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        granted: bool = True,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        """Convenience method for access events"""
        return self.log(
            event_type=AuditEventType.AUTHZ_ACCESS_GRANTED if granted else AuditEventType.AUTHZ_ACCESS_DENIED,
            severity=AuditSeverity.INFO if granted else AuditSeverity.WARNING,
            actor_id=user_id,
            actor_type="user",
            target_type=resource_type,
            target_id=resource_id,
            action=action,
            outcome="success" if granted else "denied",
            ip_address=ip_address,
            details=details,
            tags=["authorization"]
        )

    def log_resource(
        self,
        event_type: AuditEventType,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        """Convenience method for resource events"""
        return self.log(
            event_type=event_type,
            severity=AuditSeverity.INFO,
            actor_id=user_id,
            actor_type="user",
            target_type=resource_type,
            target_id=resource_id,
            action=action,
            details=details,
            tags=["resource", resource_type]
        )

    def log_security(
        self,
        event_type: AuditEventType,
        description: str,
        severity: AuditSeverity = AuditSeverity.WARNING,
        actor_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        """Convenience method for security events"""
        return self.log(
            event_type=event_type,
            severity=severity,
            actor_id=actor_id,
            actor_type="system",
            action=description,
            ip_address=ip_address,
            details=details,
            tags=["security"]
        )

    def log_system(
        self,
        event_type: AuditEventType,
        description: str,
        severity: AuditSeverity = AuditSeverity.INFO,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        """Convenience method for system events"""
        return self.log(
            event_type=event_type,
            severity=severity,
            actor_type="system",
            action=description,
            details=details,
            tags=["system"]
        )

    def add_listener(self, listener: Callable[[AuditEvent], None]) -> None:
        """Add event listener for real-time notifications"""
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[AuditEvent], None]) -> None:
        """Remove event listener"""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def enable(self) -> None:
        """Enable audit logging"""
        self._enabled = True

    def disable(self) -> None:
        """Disable audit logging"""
        self._enabled = False

    def set_min_severity(self, severity: AuditSeverity) -> None:
        """Set minimum severity level"""
        self._min_severity = severity

    def get_recent(self, limit: int = 100) -> List[AuditEvent]:
        """Get recent events"""
        return self.events[-limit:]

    def get_by_actor(self, actor_id: str, limit: int = 100) -> List[AuditEvent]:
        """Get events by actor"""
        events = [e for e in self.events if e.actor_id == actor_id]
        return events[-limit:]

    def get_by_type(self, event_type: AuditEventType, limit: int = 100) -> List[AuditEvent]:
        """Get events by type"""
        events = [e for e in self.events if e.event_type == event_type]
        return events[-limit:]

    def get_statistics(self) -> dict:
        """Get audit logger statistics"""
        # Count by type
        type_counts: Dict[str, int] = {}
        severity_counts: Dict[str, int] = {}
        outcome_counts: Dict[str, int] = {}

        for event in self.events:
            type_counts[event.event_type.value] = type_counts.get(event.event_type.value, 0) + 1
            severity_counts[event.severity.value] = severity_counts.get(event.severity.value, 0) + 1
            outcome_counts[event.outcome] = outcome_counts.get(event.outcome, 0) + 1

        return {
            "total_events": len(self.events),
            "max_events": self._max_events,
            "enabled": self._enabled,
            "min_severity": self._min_severity.value,
            "listeners": len(self._listeners),
            "by_type": type_counts,
            "by_severity": severity_counts,
            "by_outcome": outcome_counts
        }

    def clear(self) -> int:
        """Clear all events and return count"""
        count = len(self.events)
        self.events = []
        return count


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get or create the global audit logger"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
