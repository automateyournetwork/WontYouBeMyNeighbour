"""
Audit Export

Provides:
- Export to multiple formats
- Scheduled exports
- Compliance reports
"""

import json
import csv
import io
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum

from .logger import AuditEvent, AuditEventType, AuditSeverity
from .storage import AuditStorage, AuditQuery, get_audit_storage


class ExportFormat(Enum):
    """Export format options"""
    JSON = "json"
    CSV = "csv"
    SYSLOG = "syslog"
    CEF = "cef"  # Common Event Format


@dataclass
class ExportResult:
    """Result of an export operation"""

    format: ExportFormat
    event_count: int
    data: str
    filename: str
    exported_at: datetime = field(default_factory=datetime.now)
    size_bytes: int = 0

    def __post_init__(self):
        self.size_bytes = len(self.data.encode('utf-8'))

    def to_dict(self) -> dict:
        return {
            "format": self.format.value,
            "event_count": self.event_count,
            "filename": self.filename,
            "exported_at": self.exported_at.isoformat(),
            "size_bytes": self.size_bytes
        }


class AuditExporter:
    """Exports audit logs in various formats"""

    def __init__(self):
        self.storage = get_audit_storage()
        self.export_history: List[ExportResult] = []
        self._max_history = 100

    def export(
        self,
        format: ExportFormat,
        query: Optional[AuditQuery] = None,
        events: Optional[List[AuditEvent]] = None
    ) -> ExportResult:
        """Export audit events to specified format"""
        if events is None:
            if query is None:
                query = AuditQuery(limit=10000)
            result = self.storage.query(query)
            events = result.events

        # Generate export data
        if format == ExportFormat.JSON:
            data = self._export_json(events)
        elif format == ExportFormat.CSV:
            data = self._export_csv(events)
        elif format == ExportFormat.SYSLOG:
            data = self._export_syslog(events)
        elif format == ExportFormat.CEF:
            data = self._export_cef(events)
        else:
            data = self._export_json(events)

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"audit_export_{timestamp}.{format.value}"

        result = ExportResult(
            format=format,
            event_count=len(events),
            data=data,
            filename=filename
        )

        # Save to history
        self.export_history.append(result)
        if len(self.export_history) > self._max_history:
            self.export_history = self.export_history[-self._max_history // 2:]

        return result

    def export_json(self, query: Optional[AuditQuery] = None) -> ExportResult:
        """Export to JSON format"""
        return self.export(ExportFormat.JSON, query)

    def export_csv(self, query: Optional[AuditQuery] = None) -> ExportResult:
        """Export to CSV format"""
        return self.export(ExportFormat.CSV, query)

    def export_syslog(self, query: Optional[AuditQuery] = None) -> ExportResult:
        """Export to Syslog format"""
        return self.export(ExportFormat.SYSLOG, query)

    def export_cef(self, query: Optional[AuditQuery] = None) -> ExportResult:
        """Export to CEF format"""
        return self.export(ExportFormat.CEF, query)

    def generate_compliance_report(
        self,
        days: int = 30,
        compliance_type: str = "general"
    ) -> Dict[str, Any]:
        """Generate compliance report"""
        query = AuditQuery(
            start_time=datetime.now() - timedelta(days=days),
            limit=50000
        )
        result = self.storage.query(query)
        events = result.events

        # Calculate metrics
        auth_events = [e for e in events if e.event_type.value.startswith("auth.")]
        authz_events = [e for e in events if e.event_type.value.startswith("authz.")]
        security_events = [e for e in events if e.event_type.value.startswith("security.")]
        admin_events = [e for e in events if e.event_type.value.startswith("admin.")]

        # Calculate success rates
        auth_success = len([e for e in auth_events if e.outcome == "success"])
        auth_total = len(auth_events) or 1
        authz_granted = len([e for e in authz_events if e.outcome == "success"])
        authz_total = len(authz_events) or 1

        # Unique users and IPs
        unique_users = set(e.actor_id for e in events if e.actor_id)
        unique_ips = set(e.ip_address for e in events if e.ip_address)

        # Daily breakdown
        daily_events: Dict[str, int] = {}
        for event in events:
            day = event.timestamp.strftime("%Y-%m-%d")
            daily_events[day] = daily_events.get(day, 0) + 1

        report = {
            "report_type": compliance_type,
            "generated_at": datetime.now().isoformat(),
            "period_days": days,
            "summary": {
                "total_events": len(events),
                "unique_users": len(unique_users),
                "unique_ips": len(unique_ips)
            },
            "authentication": {
                "total_events": len(auth_events),
                "successful": auth_success,
                "failed": len(auth_events) - auth_success,
                "success_rate": auth_success / auth_total
            },
            "authorization": {
                "total_events": len(authz_events),
                "granted": authz_granted,
                "denied": len(authz_events) - authz_granted,
                "grant_rate": authz_granted / authz_total
            },
            "security": {
                "total_events": len(security_events),
                "threats_detected": len([e for e in security_events
                                          if e.event_type == AuditEventType.SECURITY_THREAT_DETECTED]),
                "policy_violations": len([e for e in security_events
                                           if e.event_type == AuditEventType.SECURITY_POLICY_VIOLATED])
            },
            "administration": {
                "total_events": len(admin_events),
                "user_changes": len([e for e in admin_events
                                      if "user" in e.event_type.value]),
                "settings_changes": len([e for e in admin_events
                                          if e.event_type == AuditEventType.ADMIN_SETTINGS_CHANGED])
            },
            "daily_breakdown": daily_events,
            "top_actors": self._get_top_actors(events, 10),
            "findings": self._generate_findings(events)
        }

        return report

    def get_export_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get export history"""
        return [r.to_dict() for r in self.export_history[-limit:]]

    def get_statistics(self) -> dict:
        """Get exporter statistics"""
        total_exported = sum(r.event_count for r in self.export_history)
        total_size = sum(r.size_bytes for r in self.export_history)

        format_counts: Dict[str, int] = {}
        for result in self.export_history:
            format_counts[result.format.value] = format_counts.get(result.format.value, 0) + 1

        return {
            "total_exports": len(self.export_history),
            "total_events_exported": total_exported,
            "total_bytes_exported": total_size,
            "by_format": format_counts,
            "available_formats": [f.value for f in ExportFormat]
        }

    def _export_json(self, events: List[AuditEvent]) -> str:
        """Export to JSON"""
        data = {
            "exported_at": datetime.now().isoformat(),
            "event_count": len(events),
            "events": [e.to_dict() for e in events]
        }
        return json.dumps(data, indent=2)

    def _export_csv(self, events: List[AuditEvent]) -> str:
        """Export to CSV"""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "id", "event_type", "severity", "timestamp",
            "actor_id", "actor_type", "target_type", "target_id",
            "action", "outcome", "ip_address", "tenant_id"
        ])

        # Data rows
        for event in events:
            writer.writerow([
                event.id,
                event.event_type.value,
                event.severity.value,
                event.timestamp.isoformat(),
                event.actor_id or "",
                event.actor_type,
                event.target_type or "",
                event.target_id or "",
                event.action,
                event.outcome,
                event.ip_address or "",
                event.tenant_id or ""
            ])

        return output.getvalue()

    def _export_syslog(self, events: List[AuditEvent]) -> str:
        """Export to Syslog format (RFC 5424)"""
        lines = []
        severity_map = {
            AuditSeverity.DEBUG: 7,
            AuditSeverity.INFO: 6,
            AuditSeverity.WARNING: 4,
            AuditSeverity.ERROR: 3,
            AuditSeverity.CRITICAL: 2
        }

        for event in events:
            pri = 8 * 16 + severity_map.get(event.severity, 6)  # Facility 16 (local0)
            timestamp = event.timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
            hostname = "adn-platform"
            app_name = "audit"
            procid = "-"
            msgid = event.event_type.value

            # Structured data
            sd = f'[audit@1 actor="{event.actor_id or "-"}" ' \
                 f'target="{event.target_id or "-"}" ' \
                 f'outcome="{event.outcome}"]'

            msg = event.action

            line = f"<{pri}>1 {timestamp} {hostname} {app_name} {procid} {msgid} {sd} {msg}"
            lines.append(line)

        return "\n".join(lines)

    def _export_cef(self, events: List[AuditEvent]) -> str:
        """Export to Common Event Format"""
        lines = []
        severity_map = {
            AuditSeverity.DEBUG: 0,
            AuditSeverity.INFO: 3,
            AuditSeverity.WARNING: 5,
            AuditSeverity.ERROR: 7,
            AuditSeverity.CRITICAL: 10
        }

        for event in events:
            cef_version = "0"
            device_vendor = "ADN"
            device_product = "Platform"
            device_version = "1.0"
            signature_id = event.event_type.value.replace(".", "_")
            name = event.action[:63] if event.action else event.event_type.value
            severity = severity_map.get(event.severity, 5)

            # Extension fields
            extensions = []
            if event.actor_id:
                extensions.append(f"suser={event.actor_id}")
            if event.ip_address:
                extensions.append(f"src={event.ip_address}")
            if event.target_id:
                extensions.append(f"dproc={event.target_id}")
            extensions.append(f"outcome={event.outcome}")
            extensions.append(f"rt={int(event.timestamp.timestamp() * 1000)}")

            ext_str = " ".join(extensions)

            line = f"CEF:{cef_version}|{device_vendor}|{device_product}|" \
                   f"{device_version}|{signature_id}|{name}|{severity}|{ext_str}"
            lines.append(line)

        return "\n".join(lines)

    def _get_top_actors(self, events: List[AuditEvent], limit: int) -> List[Dict[str, Any]]:
        """Get top actors by event count"""
        actor_counts: Dict[str, int] = {}
        for event in events:
            if event.actor_id:
                actor_counts[event.actor_id] = actor_counts.get(event.actor_id, 0) + 1

        sorted_actors = sorted(actor_counts.items(), key=lambda x: x[1], reverse=True)
        return [{"actor_id": a, "event_count": c} for a, c in sorted_actors[:limit]]

    def _generate_findings(self, events: List[AuditEvent]) -> List[Dict[str, Any]]:
        """Generate compliance findings"""
        findings = []

        # Check for failed login attempts
        failed_logins = [e for e in events
                         if e.event_type == AuditEventType.AUTH_LOGIN_FAILED]
        if len(failed_logins) > 10:
            findings.append({
                "severity": "warning",
                "category": "authentication",
                "description": f"High number of failed login attempts: {len(failed_logins)}",
                "recommendation": "Review failed login patterns for potential brute force attempts"
            })

        # Check for access denials
        access_denied = [e for e in events
                          if e.event_type == AuditEventType.AUTHZ_ACCESS_DENIED]
        if len(access_denied) > 50:
            findings.append({
                "severity": "info",
                "category": "authorization",
                "description": f"Elevated access denial count: {len(access_denied)}",
                "recommendation": "Review access control policies"
            })

        # Check for security events
        security_events = [e for e in events
                           if e.event_type.value.startswith("security.")]
        if security_events:
            findings.append({
                "severity": "critical" if len(security_events) > 5 else "warning",
                "category": "security",
                "description": f"Security events detected: {len(security_events)}",
                "recommendation": "Investigate security events immediately"
            })

        return findings


# Global audit exporter instance
_audit_exporter: Optional[AuditExporter] = None


def get_audit_exporter() -> AuditExporter:
    """Get or create the global audit exporter"""
    global _audit_exporter
    if _audit_exporter is None:
        _audit_exporter = AuditExporter()
    return _audit_exporter
