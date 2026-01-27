"""
SLA Monitor

Service Level Agreement monitoring and tracking for network services.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
import uuid
import statistics


class SLAMetricType(Enum):
    """Type of SLA metric."""
    AVAILABILITY = "availability"  # Uptime percentage
    LATENCY = "latency"  # Response time
    PACKET_LOSS = "packet_loss"  # Loss percentage
    JITTER = "jitter"  # Latency variation
    THROUGHPUT = "throughput"  # Bandwidth
    MTTR = "mttr"  # Mean time to repair
    MTBF = "mtbf"  # Mean time between failures
    ERROR_RATE = "error_rate"  # Error percentage
    RESPONSE_TIME = "response_time"  # API/service response
    CUSTOM = "custom"


class SLAStatus(Enum):
    """SLA compliance status."""
    COMPLIANT = "compliant"
    AT_RISK = "at_risk"
    VIOLATED = "violated"
    UNKNOWN = "unknown"


class ViolationSeverity(Enum):
    """Severity of SLA violation."""
    MINOR = "minor"  # < 5% breach
    MODERATE = "moderate"  # 5-15% breach
    MAJOR = "major"  # 15-30% breach
    CRITICAL = "critical"  # > 30% breach


@dataclass
class SLATarget:
    """Target threshold for an SLA metric."""
    metric_type: SLAMetricType = SLAMetricType.AVAILABILITY
    target_value: float = 99.9  # Target to meet
    comparison: str = ">="  # >=, <=, ==, >, <
    unit: str = "%"  # %, ms, Mbps, etc.
    warning_threshold: float = 99.5  # At-risk threshold

    def to_dict(self) -> Dict:
        return {
            "metric_type": self.metric_type.value,
            "target_value": self.target_value,
            "comparison": self.comparison,
            "unit": self.unit,
            "warning_threshold": self.warning_threshold
        }

    def check_value(self, value: float) -> SLAStatus:
        """Check if a value meets the SLA target."""
        if self.comparison == ">=":
            if value >= self.target_value:
                return SLAStatus.COMPLIANT
            elif value >= self.warning_threshold:
                return SLAStatus.AT_RISK
            return SLAStatus.VIOLATED
        elif self.comparison == "<=":
            if value <= self.target_value:
                return SLAStatus.COMPLIANT
            elif value <= self.warning_threshold:
                return SLAStatus.AT_RISK
            return SLAStatus.VIOLATED
        elif self.comparison == "<":
            if value < self.target_value:
                return SLAStatus.COMPLIANT
            return SLAStatus.VIOLATED
        elif self.comparison == ">":
            if value > self.target_value:
                return SLAStatus.COMPLIANT
            return SLAStatus.VIOLATED
        else:
            if value == self.target_value:
                return SLAStatus.COMPLIANT
            return SLAStatus.VIOLATED


@dataclass
class SLAMetricSample:
    """A single SLA metric measurement."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sla_id: str = ""
    metric_type: SLAMetricType = SLAMetricType.AVAILABILITY
    value: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    source: str = ""  # Where the measurement came from

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "sla_id": self.sla_id,
            "metric_type": self.metric_type.value,
            "value": self.value,
            "timestamp": self.timestamp,
            "source": self.source
        }


@dataclass
class SLAViolation:
    """Record of an SLA violation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sla_id: str = ""
    sla_name: str = ""
    metric_type: SLAMetricType = SLAMetricType.AVAILABILITY
    target_value: float = 0.0
    actual_value: float = 0.0
    breach_percentage: float = 0.0
    severity: ViolationSeverity = ViolationSeverity.MINOR
    start_time: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    end_time: Optional[str] = None
    duration_minutes: int = 0
    acknowledged: bool = False
    acknowledged_by: str = ""
    resolution: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "sla_id": self.sla_id,
            "sla_name": self.sla_name,
            "metric_type": self.metric_type.value,
            "target_value": self.target_value,
            "actual_value": self.actual_value,
            "breach_percentage": self.breach_percentage,
            "severity": self.severity.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_minutes": self.duration_minutes,
            "acknowledged": self.acknowledged,
            "acknowledged_by": self.acknowledged_by,
            "resolution": self.resolution
        }


@dataclass
class SLAReport:
    """SLA compliance report for a period."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sla_id: str = ""
    sla_name: str = ""
    period_start: str = ""
    period_end: str = ""

    # Overall status
    overall_status: SLAStatus = SLAStatus.UNKNOWN
    compliance_percentage: float = 0.0

    # Per-metric results
    metric_results: Dict[str, Dict] = field(default_factory=dict)

    # Violations in period
    violation_count: int = 0
    total_downtime_minutes: int = 0

    # Statistics
    availability_avg: float = 0.0
    latency_avg: float = 0.0
    latency_p95: float = 0.0
    latency_p99: float = 0.0

    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "sla_id": self.sla_id,
            "sla_name": self.sla_name,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "overall_status": self.overall_status.value,
            "compliance_percentage": self.compliance_percentage,
            "metric_results": self.metric_results,
            "violation_count": self.violation_count,
            "total_downtime_minutes": self.total_downtime_minutes,
            "availability_avg": self.availability_avg,
            "latency_avg": self.latency_avg,
            "latency_p95": self.latency_p95,
            "latency_p99": self.latency_p99,
            "generated_at": self.generated_at
        }


@dataclass
class SLADefinition:
    """Complete SLA definition."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""

    # What the SLA covers
    service_name: str = ""
    service_type: str = ""  # network, application, infrastructure
    scope: List[str] = field(default_factory=list)  # Device IDs, interface names, etc.

    # Targets
    targets: List[SLATarget] = field(default_factory=list)

    # Time window
    measurement_window: str = "24h"  # 1h, 24h, 7d, 30d

    # Notifications
    notify_on_violation: bool = True
    notify_on_at_risk: bool = True
    notification_emails: List[str] = field(default_factory=list)

    # Status
    enabled: bool = True
    status: SLAStatus = SLAStatus.UNKNOWN
    current_values: Dict[str, float] = field(default_factory=dict)

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    owner: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "service_name": self.service_name,
            "service_type": self.service_type,
            "scope": self.scope,
            "targets": [t.to_dict() for t in self.targets],
            "measurement_window": self.measurement_window,
            "notify_on_violation": self.notify_on_violation,
            "notify_on_at_risk": self.notify_on_at_risk,
            "notification_emails": self.notification_emails,
            "enabled": self.enabled,
            "status": self.status.value,
            "current_values": self.current_values,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "owner": self.owner,
            "tags": self.tags
        }


class SLAMonitor:
    """
    SLA Monitoring and tracking system.

    Tracks service level agreements, monitors metrics, detects violations,
    and generates compliance reports.
    """

    def __init__(self):
        self._slas: Dict[str, SLADefinition] = {}
        self._samples: Dict[str, List[SLAMetricSample]] = {}  # sla_id -> samples
        self._violations: Dict[str, SLAViolation] = {}
        self._reports: Dict[str, SLAReport] = {}
        self._active_violations: Dict[str, str] = {}  # sla_id -> violation_id

        # Initialize with some default SLA templates
        self._init_default_templates()

    def _init_default_templates(self):
        """Create default SLA templates."""
        # Network availability SLA
        network_sla = SLADefinition(
            name="Network Infrastructure SLA",
            description="Core network availability and performance",
            service_name="Network Core",
            service_type="network",
            targets=[
                SLATarget(SLAMetricType.AVAILABILITY, 99.99, ">=", "%", 99.9),
                SLATarget(SLAMetricType.LATENCY, 50, "<=", "ms", 100),
                SLATarget(SLAMetricType.PACKET_LOSS, 0.1, "<=", "%", 1.0),
            ],
            measurement_window="30d"
        )
        self._slas[network_sla.id] = network_sla

    # ==================== SLA Management ====================

    def create_sla(self, sla: SLADefinition) -> SLADefinition:
        """Create a new SLA definition."""
        self._slas[sla.id] = sla
        self._samples[sla.id] = []
        return sla

    def get_sla(self, sla_id: str) -> Optional[SLADefinition]:
        """Get an SLA by ID."""
        return self._slas.get(sla_id)

    def update_sla(self, sla_id: str, updates: Dict) -> Optional[SLADefinition]:
        """Update an SLA definition."""
        sla = self._slas.get(sla_id)
        if not sla:
            return None

        for key, value in updates.items():
            if hasattr(sla, key):
                setattr(sla, key, value)

        sla.updated_at = datetime.utcnow().isoformat()
        return sla

    def delete_sla(self, sla_id: str) -> bool:
        """Delete an SLA."""
        if sla_id in self._slas:
            del self._slas[sla_id]
            self._samples.pop(sla_id, None)
            return True
        return False

    def list_slas(self, enabled_only: bool = False) -> List[SLADefinition]:
        """List all SLAs."""
        slas = list(self._slas.values())
        if enabled_only:
            slas = [s for s in slas if s.enabled]
        return slas

    # ==================== Metric Recording ====================

    def record_metric(
        self,
        sla_id: str,
        metric_type: SLAMetricType,
        value: float,
        source: str = ""
    ) -> Optional[SLAMetricSample]:
        """Record an SLA metric sample."""
        sla = self._slas.get(sla_id)
        if not sla:
            return None

        sample = SLAMetricSample(
            sla_id=sla_id,
            metric_type=metric_type,
            value=value,
            source=source
        )

        if sla_id not in self._samples:
            self._samples[sla_id] = []

        self._samples[sla_id].append(sample)

        # Keep only last 1000 samples per SLA
        if len(self._samples[sla_id]) > 1000:
            self._samples[sla_id] = self._samples[sla_id][-1000:]

        # Update current value
        sla.current_values[metric_type.value] = value

        # Check for violations
        self._check_violation(sla, metric_type, value)

        return sample

    def _check_violation(self, sla: SLADefinition, metric_type: SLAMetricType, value: float):
        """Check if a metric value violates the SLA."""
        for target in sla.targets:
            if target.metric_type != metric_type:
                continue

            status = target.check_value(value)

            # Update SLA status
            if status == SLAStatus.VIOLATED:
                self._handle_violation(sla, target, value)
            elif status == SLAStatus.COMPLIANT and sla.id in self._active_violations:
                self._resolve_violation(sla.id)

            # Update overall SLA status
            sla.status = status

    def _handle_violation(self, sla: SLADefinition, target: SLATarget, value: float):
        """Handle a detected SLA violation."""
        # Check if there's already an active violation
        if sla.id in self._active_violations:
            # Update existing violation
            violation_id = self._active_violations[sla.id]
            violation = self._violations.get(violation_id)
            if violation:
                violation.actual_value = value
                violation.duration_minutes += 1  # Approximate
            return

        # Calculate breach percentage
        if target.comparison in (">=", ">"):
            breach_pct = ((target.target_value - value) / target.target_value) * 100
        else:
            breach_pct = ((value - target.target_value) / target.target_value) * 100

        # Determine severity
        if breach_pct < 5:
            severity = ViolationSeverity.MINOR
        elif breach_pct < 15:
            severity = ViolationSeverity.MODERATE
        elif breach_pct < 30:
            severity = ViolationSeverity.MAJOR
        else:
            severity = ViolationSeverity.CRITICAL

        # Create violation
        violation = SLAViolation(
            sla_id=sla.id,
            sla_name=sla.name,
            metric_type=target.metric_type,
            target_value=target.target_value,
            actual_value=value,
            breach_percentage=breach_pct,
            severity=severity
        )

        self._violations[violation.id] = violation
        self._active_violations[sla.id] = violation.id

    def _resolve_violation(self, sla_id: str):
        """Mark an active violation as resolved."""
        if sla_id not in self._active_violations:
            return

        violation_id = self._active_violations[sla_id]
        violation = self._violations.get(violation_id)

        if violation:
            violation.end_time = datetime.utcnow().isoformat()
            # Calculate duration
            try:
                start = datetime.fromisoformat(violation.start_time.replace('Z', '+00:00'))
                end = datetime.fromisoformat(violation.end_time.replace('Z', '+00:00'))
                violation.duration_minutes = int((end - start).total_seconds() / 60)
            except:
                pass

        del self._active_violations[sla_id]

    # ==================== Violation Management ====================

    def get_violations(
        self,
        sla_id: Optional[str] = None,
        active_only: bool = False,
        limit: int = 100
    ) -> List[SLAViolation]:
        """Get SLA violations."""
        violations = list(self._violations.values())

        if sla_id:
            violations = [v for v in violations if v.sla_id == sla_id]

        if active_only:
            violations = [v for v in violations if v.end_time is None]

        # Sort by start time descending
        violations.sort(key=lambda v: v.start_time, reverse=True)

        return violations[:limit]

    def acknowledge_violation(self, violation_id: str, acknowledged_by: str) -> Optional[SLAViolation]:
        """Acknowledge a violation."""
        violation = self._violations.get(violation_id)
        if violation:
            violation.acknowledged = True
            violation.acknowledged_by = acknowledged_by
        return violation

    def resolve_violation(self, violation_id: str, resolution: str) -> Optional[SLAViolation]:
        """Mark a violation as resolved with resolution notes."""
        violation = self._violations.get(violation_id)
        if violation:
            violation.resolution = resolution
            if not violation.end_time:
                violation.end_time = datetime.utcnow().isoformat()
        return violation

    # ==================== Reporting ====================

    def generate_report(self, sla_id: str, days: int = 30) -> Optional[SLAReport]:
        """Generate an SLA compliance report."""
        sla = self._slas.get(sla_id)
        if not sla:
            return None

        now = datetime.utcnow()
        period_start = (now - timedelta(days=days)).isoformat()
        period_end = now.isoformat()

        report = SLAReport(
            sla_id=sla_id,
            sla_name=sla.name,
            period_start=period_start,
            period_end=period_end
        )

        # Get samples for the period
        samples = self._samples.get(sla_id, [])
        period_samples = [s for s in samples
                         if s.timestamp >= period_start and s.timestamp <= period_end]

        # Calculate metrics per type
        metric_values: Dict[str, List[float]] = {}
        for sample in period_samples:
            mt = sample.metric_type.value
            if mt not in metric_values:
                metric_values[mt] = []
            metric_values[mt].append(sample.value)

        # Calculate stats for each target
        all_compliant = True
        for target in sla.targets:
            mt = target.metric_type.value
            values = metric_values.get(mt, [])

            if values:
                avg = statistics.mean(values)
                status = target.check_value(avg)

                result = {
                    "target": target.target_value,
                    "actual": round(avg, 2),
                    "min": round(min(values), 2),
                    "max": round(max(values), 2),
                    "samples": len(values),
                    "status": status.value
                }

                if len(values) >= 2:
                    result["std_dev"] = round(statistics.stdev(values), 2)

                report.metric_results[mt] = result

                if status != SLAStatus.COMPLIANT:
                    all_compliant = False

        # Count violations in period
        violations = [v for v in self._violations.values()
                     if v.sla_id == sla_id and v.start_time >= period_start]
        report.violation_count = len(violations)
        report.total_downtime_minutes = sum(v.duration_minutes for v in violations)

        # Overall stats
        availability_values = metric_values.get("availability", [])
        if availability_values:
            report.availability_avg = round(statistics.mean(availability_values), 2)

        latency_values = metric_values.get("latency", [])
        if latency_values:
            report.latency_avg = round(statistics.mean(latency_values), 2)
            sorted_latency = sorted(latency_values)
            n = len(sorted_latency)
            report.latency_p95 = sorted_latency[int(n * 0.95)] if n > 20 else max(latency_values)
            report.latency_p99 = sorted_latency[int(n * 0.99)] if n > 100 else max(latency_values)

        # Calculate compliance percentage
        if period_samples:
            compliant_count = sum(1 for s in period_samples
                                  for t in sla.targets
                                  if t.metric_type == s.metric_type and
                                  t.check_value(s.value) == SLAStatus.COMPLIANT)
            total_checks = len(period_samples) * len(sla.targets) if sla.targets else 1
            report.compliance_percentage = round((compliant_count / total_checks) * 100, 2)

        # Determine overall status
        if report.compliance_percentage >= 99:
            report.overall_status = SLAStatus.COMPLIANT
        elif report.compliance_percentage >= 95:
            report.overall_status = SLAStatus.AT_RISK
        else:
            report.overall_status = SLAStatus.VIOLATED

        self._reports[report.id] = report
        return report

    def get_reports(self, sla_id: Optional[str] = None) -> List[SLAReport]:
        """Get generated reports."""
        reports = list(self._reports.values())
        if sla_id:
            reports = [r for r in reports if r.sla_id == sla_id]
        return sorted(reports, key=lambda r: r.generated_at, reverse=True)

    # ==================== Statistics ====================

    def get_statistics(self) -> Dict[str, Any]:
        """Get SLA monitoring statistics."""
        slas = list(self._slas.values())
        violations = list(self._violations.values())

        # Count by status
        by_status = {}
        for status in SLAStatus:
            count = len([s for s in slas if s.status == status])
            if count > 0:
                by_status[status.value] = count

        # Active violations
        active_violations = len([v for v in violations if v.end_time is None])

        # Critical violations (last 24h)
        now = datetime.utcnow()
        day_ago = (now - timedelta(days=1)).isoformat()
        recent_critical = len([v for v in violations
                              if v.start_time >= day_ago and
                              v.severity in (ViolationSeverity.MAJOR, ViolationSeverity.CRITICAL)])

        return {
            "total_slas": len(slas),
            "enabled_slas": len([s for s in slas if s.enabled]),
            "by_status": by_status,
            "total_violations": len(violations),
            "active_violations": active_violations,
            "critical_violations_24h": recent_critical,
            "total_samples": sum(len(samples) for samples in self._samples.values()),
            "total_reports": len(self._reports)
        }

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get a summary for dashboard display."""
        slas = list(self._slas.values())

        # Calculate overall compliance
        compliant = len([s for s in slas if s.status == SLAStatus.COMPLIANT])
        at_risk = len([s for s in slas if s.status == SLAStatus.AT_RISK])
        violated = len([s for s in slas if s.status == SLAStatus.VIOLATED])

        # Top SLAs by risk
        risk_slas = sorted(slas, key=lambda s: (
            {"violated": 0, "at_risk": 1, "unknown": 2, "compliant": 3}.get(s.status.value, 4)
        ))[:5]

        return {
            "overall_health": "critical" if violated > 0 else ("warning" if at_risk > 0 else "healthy"),
            "compliant_count": compliant,
            "at_risk_count": at_risk,
            "violated_count": violated,
            "total_slas": len(slas),
            "compliance_rate": round((compliant / len(slas)) * 100, 1) if slas else 100,
            "top_risk_slas": [s.to_dict() for s in risk_slas]
        }


# Singleton instance
_sla_monitor: Optional[SLAMonitor] = None


def get_sla_monitor() -> SLAMonitor:
    """Get the singleton SLA monitor instance."""
    global _sla_monitor
    if _sla_monitor is None:
        _sla_monitor = SLAMonitor()
    return _sla_monitor
