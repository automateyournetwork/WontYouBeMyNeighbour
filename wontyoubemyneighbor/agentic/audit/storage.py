"""
Audit Storage

Provides:
- Persistent audit log storage
- Advanced querying
- Log archival
- Retention policies
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum

from .logger import AuditEvent, AuditEventType, AuditSeverity, get_audit_logger


@dataclass
class AuditQuery:
    """Query parameters for audit log search"""

    event_types: Optional[List[AuditEventType]] = None
    severities: Optional[List[AuditSeverity]] = None
    actor_id: Optional[str] = None
    actor_type: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    tenant_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    outcome: Optional[str] = None
    tags: Optional[List[str]] = None
    ip_address: Optional[str] = None
    search_text: Optional[str] = None
    offset: int = 0
    limit: int = 100

    def to_dict(self) -> dict:
        return {
            "event_types": [e.value for e in self.event_types] if self.event_types else None,
            "severities": [s.value for s in self.severities] if self.severities else None,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "tenant_id": self.tenant_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "outcome": self.outcome,
            "tags": self.tags,
            "ip_address": self.ip_address,
            "search_text": self.search_text,
            "offset": self.offset,
            "limit": self.limit
        }


@dataclass
class AuditQueryResult:
    """Result of an audit query"""

    events: List[AuditEvent]
    total: int
    offset: int
    limit: int
    query: AuditQuery

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.events) < self.total

    def to_dict(self) -> dict:
        return {
            "events": [e.to_dict() for e in self.events],
            "total": self.total,
            "offset": self.offset,
            "limit": self.limit,
            "has_more": self.has_more
        }


class RetentionPolicy(Enum):
    """Audit log retention policies"""
    KEEP_ALL = "keep_all"
    DAYS_7 = "7_days"
    DAYS_30 = "30_days"
    DAYS_90 = "90_days"
    DAYS_365 = "365_days"
    YEARS_3 = "3_years"
    YEARS_7 = "7_years"


class AuditStorage:
    """Stores and queries audit logs"""

    RETENTION_DAYS = {
        RetentionPolicy.KEEP_ALL: None,
        RetentionPolicy.DAYS_7: 7,
        RetentionPolicy.DAYS_30: 30,
        RetentionPolicy.DAYS_90: 90,
        RetentionPolicy.DAYS_365: 365,
        RetentionPolicy.YEARS_3: 365 * 3,
        RetentionPolicy.YEARS_7: 365 * 7
    }

    def __init__(self):
        self.logger = get_audit_logger()
        self.archived: List[AuditEvent] = []
        self.retention_policy = RetentionPolicy.DAYS_90
        self._indexes: Dict[str, Dict[str, List[str]]] = {
            "actor_id": {},
            "target_id": {},
            "event_type": {},
            "tenant_id": {},
            "date": {}
        }

    def query(self, query: AuditQuery) -> AuditQueryResult:
        """Query audit logs with filters"""
        # Combine active and archived events
        all_events = self.logger.events + self.archived

        # Apply filters
        filtered = all_events

        if query.event_types:
            filtered = [e for e in filtered if e.event_type in query.event_types]

        if query.severities:
            filtered = [e for e in filtered if e.severity in query.severities]

        if query.actor_id:
            filtered = [e for e in filtered if e.actor_id == query.actor_id]

        if query.actor_type:
            filtered = [e for e in filtered if e.actor_type == query.actor_type]

        if query.target_type:
            filtered = [e for e in filtered if e.target_type == query.target_type]

        if query.target_id:
            filtered = [e for e in filtered if e.target_id == query.target_id]

        if query.tenant_id:
            filtered = [e for e in filtered if e.tenant_id == query.tenant_id]

        if query.start_time:
            filtered = [e for e in filtered if e.timestamp >= query.start_time]

        if query.end_time:
            filtered = [e for e in filtered if e.timestamp <= query.end_time]

        if query.outcome:
            filtered = [e for e in filtered if e.outcome == query.outcome]

        if query.tags:
            filtered = [e for e in filtered
                        if any(tag in e.tags for tag in query.tags)]

        if query.ip_address:
            filtered = [e for e in filtered if e.ip_address == query.ip_address]

        if query.search_text:
            search_lower = query.search_text.lower()
            filtered = [e for e in filtered
                        if search_lower in e.action.lower() or
                        search_lower in str(e.details).lower()]

        # Sort by timestamp descending
        filtered.sort(key=lambda e: e.timestamp, reverse=True)

        # Apply pagination
        total = len(filtered)
        paginated = filtered[query.offset:query.offset + query.limit]

        return AuditQueryResult(
            events=paginated,
            total=total,
            offset=query.offset,
            limit=query.limit,
            query=query
        )

    def get_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 1000
    ) -> List[AuditEvent]:
        """Get events within date range"""
        query = AuditQuery(
            start_time=start_date,
            end_time=end_date,
            limit=limit
        )
        result = self.query(query)
        return result.events

    def get_security_events(
        self,
        days: int = 7,
        limit: int = 100
    ) -> List[AuditEvent]:
        """Get security-related events"""
        security_types = [
            AuditEventType.AUTH_LOGIN_FAILED,
            AuditEventType.AUTHZ_ACCESS_DENIED,
            AuditEventType.SECURITY_THREAT_DETECTED,
            AuditEventType.SECURITY_POLICY_VIOLATED,
            AuditEventType.SECURITY_ANOMALY_DETECTED,
            AuditEventType.APIKEY_RATE_LIMITED
        ]
        query = AuditQuery(
            event_types=security_types,
            start_time=datetime.now() - timedelta(days=days),
            limit=limit
        )
        result = self.query(query)
        return result.events

    def get_user_activity(
        self,
        user_id: str,
        days: int = 30,
        limit: int = 100
    ) -> List[AuditEvent]:
        """Get user activity"""
        query = AuditQuery(
            actor_id=user_id,
            start_time=datetime.now() - timedelta(days=days),
            limit=limit
        )
        result = self.query(query)
        return result.events

    def get_resource_history(
        self,
        resource_type: str,
        resource_id: str,
        limit: int = 100
    ) -> List[AuditEvent]:
        """Get history for a specific resource"""
        query = AuditQuery(
            target_type=resource_type,
            target_id=resource_id,
            limit=limit
        )
        result = self.query(query)
        return result.events

    def archive_old_events(self) -> int:
        """Archive events based on retention policy"""
        retention_days = self.RETENTION_DAYS.get(self.retention_policy)
        if retention_days is None:
            return 0

        cutoff = datetime.now() - timedelta(days=retention_days)
        to_archive = [e for e in self.logger.events if e.timestamp < cutoff]

        if to_archive:
            self.archived.extend(to_archive)
            self.logger.events = [e for e in self.logger.events
                                  if e.timestamp >= cutoff]

        return len(to_archive)

    def purge_archived(self, days: int = 365) -> int:
        """Purge old archived events"""
        cutoff = datetime.now() - timedelta(days=days)
        original_count = len(self.archived)
        self.archived = [e for e in self.archived if e.timestamp >= cutoff]
        return original_count - len(self.archived)

    def set_retention_policy(self, policy: RetentionPolicy) -> None:
        """Set retention policy"""
        self.retention_policy = policy

    def get_summary(
        self,
        days: int = 7
    ) -> Dict[str, Any]:
        """Get audit summary for specified days"""
        cutoff = datetime.now() - timedelta(days=days)
        events = [e for e in self.logger.events if e.timestamp >= cutoff]

        # Calculate statistics
        type_counts: Dict[str, int] = {}
        severity_counts: Dict[str, int] = {}
        outcome_counts: Dict[str, int] = {}
        daily_counts: Dict[str, int] = {}
        actor_counts: Dict[str, int] = {}

        for event in events:
            type_counts[event.event_type.value] = type_counts.get(event.event_type.value, 0) + 1
            severity_counts[event.severity.value] = severity_counts.get(event.severity.value, 0) + 1
            outcome_counts[event.outcome] = outcome_counts.get(event.outcome, 0) + 1

            day_key = event.timestamp.strftime("%Y-%m-%d")
            daily_counts[day_key] = daily_counts.get(day_key, 0) + 1

            if event.actor_id:
                actor_counts[event.actor_id] = actor_counts.get(event.actor_id, 0) + 1

        # Top actors
        top_actors = sorted(actor_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "period_days": days,
            "total_events": len(events),
            "by_type": type_counts,
            "by_severity": severity_counts,
            "by_outcome": outcome_counts,
            "daily_counts": daily_counts,
            "top_actors": [{"actor_id": a, "count": c} for a, c in top_actors],
            "failures": outcome_counts.get("failure", 0) + outcome_counts.get("error", 0),
            "security_events": sum(
                type_counts.get(t.value, 0)
                for t in [
                    AuditEventType.AUTH_LOGIN_FAILED,
                    AuditEventType.AUTHZ_ACCESS_DENIED,
                    AuditEventType.SECURITY_THREAT_DETECTED,
                    AuditEventType.SECURITY_POLICY_VIOLATED
                ]
            )
        }

    def get_statistics(self) -> dict:
        """Get storage statistics"""
        return {
            "active_events": len(self.logger.events),
            "archived_events": len(self.archived),
            "total_events": len(self.logger.events) + len(self.archived),
            "retention_policy": self.retention_policy.value,
            "retention_days": self.RETENTION_DAYS.get(self.retention_policy),
            "logger_stats": self.logger.get_statistics()
        }


# Global audit storage instance
_audit_storage: Optional[AuditStorage] = None


def get_audit_storage() -> AuditStorage:
    """Get or create the global audit storage"""
    global _audit_storage
    if _audit_storage is None:
        _audit_storage = AuditStorage()
    return _audit_storage
