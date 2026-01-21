"""
Health Checking

Provides:
- Health check definitions
- Health check execution
- Health status tracking
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from enum import Enum


class HealthStatus(Enum):
    """Health status"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class HealthCheckType(Enum):
    """Health check types"""
    HTTP = "http"
    TCP = "tcp"
    GRPC = "grpc"
    SCRIPT = "script"
    TTL = "ttl"
    CUSTOM = "custom"


@dataclass
class HealthCheckResult:
    """Result of a health check"""

    check_id: str
    status: HealthStatus
    timestamp: datetime = field(default_factory=datetime.now)
    latency_ms: float = 0.0
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "latency_ms": self.latency_ms,
            "message": self.message,
            "details": self.details
        }


@dataclass
class HealthCheck:
    """Health check definition"""

    id: str
    name: str
    target: str  # Service name or instance ID
    check_type: HealthCheckType = HealthCheckType.HTTP

    # HTTP settings
    http_url: Optional[str] = None
    http_method: str = "GET"
    http_headers: Dict[str, str] = field(default_factory=dict)
    http_body: Optional[str] = None
    expected_status: int = 200

    # TCP settings
    tcp_host: Optional[str] = None
    tcp_port: Optional[int] = None

    # Timing
    interval_seconds: int = 10
    timeout_seconds: int = 5
    deregister_after_failures: int = 3

    # Thresholds
    success_threshold: int = 2
    failure_threshold: int = 3

    # State
    enabled: bool = True
    last_status: HealthStatus = HealthStatus.UNKNOWN
    last_check_at: Optional[datetime] = None
    consecutive_successes: int = 0
    consecutive_failures: int = 0

    # History
    history: List[HealthCheckResult] = field(default_factory=list)
    max_history: int = 100

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def record_result(self, result: HealthCheckResult) -> None:
        """Record health check result"""
        self.last_check_at = result.timestamp
        self.last_status = result.status

        if result.status == HealthStatus.HEALTHY:
            self.consecutive_successes += 1
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
            self.consecutive_successes = 0

        self.history.append(result)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def is_due(self) -> bool:
        """Check if health check is due"""
        if not self.enabled:
            return False
        if not self.last_check_at:
            return True
        next_check = self.last_check_at + timedelta(seconds=self.interval_seconds)
        return datetime.now() >= next_check

    def get_success_rate(self, window: int = 10) -> float:
        """Get success rate over window"""
        recent = self.history[-window:] if self.history else []
        if not recent:
            return 0.0
        successes = sum(1 for r in recent if r.status == HealthStatus.HEALTHY)
        return successes / len(recent)

    def get_average_latency(self, window: int = 10) -> float:
        """Get average latency over window"""
        recent = self.history[-window:] if self.history else []
        if not recent:
            return 0.0
        return sum(r.latency_ms for r in recent) / len(recent)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "target": self.target,
            "check_type": self.check_type.value,
            "http_url": self.http_url,
            "http_method": self.http_method,
            "expected_status": self.expected_status,
            "tcp_host": self.tcp_host,
            "tcp_port": self.tcp_port,
            "interval_seconds": self.interval_seconds,
            "timeout_seconds": self.timeout_seconds,
            "deregister_after_failures": self.deregister_after_failures,
            "success_threshold": self.success_threshold,
            "failure_threshold": self.failure_threshold,
            "enabled": self.enabled,
            "last_status": self.last_status.value,
            "last_check_at": self.last_check_at.isoformat() if self.last_check_at else None,
            "consecutive_successes": self.consecutive_successes,
            "consecutive_failures": self.consecutive_failures,
            "success_rate": self.get_success_rate(),
            "average_latency_ms": self.get_average_latency(),
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata
        }


class HealthChecker:
    """Health checker for services"""

    def __init__(self):
        self.checks: Dict[str, HealthCheck] = {}
        self._handlers: Dict[HealthCheckType, Callable] = {}
        self._init_builtin_handlers()

    def _init_builtin_handlers(self) -> None:
        """Initialize built-in health check handlers"""

        def http_handler(check: HealthCheck) -> HealthCheckResult:
            """HTTP health check (simulated)"""
            import time
            start = time.time()

            # Simulate HTTP check
            status = HealthStatus.HEALTHY
            message = "HTTP check passed"
            latency = (time.time() - start) * 1000 + 5  # Add simulated latency

            return HealthCheckResult(
                check_id=check.id,
                status=status,
                latency_ms=latency,
                message=message,
                details={"url": check.http_url, "method": check.http_method}
            )

        def tcp_handler(check: HealthCheck) -> HealthCheckResult:
            """TCP health check (simulated)"""
            import time
            start = time.time()

            # Simulate TCP check
            status = HealthStatus.HEALTHY
            message = "TCP connection successful"
            latency = (time.time() - start) * 1000 + 2

            return HealthCheckResult(
                check_id=check.id,
                status=status,
                latency_ms=latency,
                message=message,
                details={"host": check.tcp_host, "port": check.tcp_port}
            )

        def ttl_handler(check: HealthCheck) -> HealthCheckResult:
            """TTL-based health check"""
            # Check if we've received a heartbeat recently
            if check.last_check_at:
                age = (datetime.now() - check.last_check_at).total_seconds()
                if age <= check.interval_seconds * 2:
                    return HealthCheckResult(
                        check_id=check.id,
                        status=HealthStatus.HEALTHY,
                        message="TTL check passed"
                    )

            return HealthCheckResult(
                check_id=check.id,
                status=HealthStatus.UNHEALTHY,
                message="TTL expired"
            )

        self._handlers = {
            HealthCheckType.HTTP: http_handler,
            HealthCheckType.TCP: tcp_handler,
            HealthCheckType.TTL: ttl_handler
        }

    def register_handler(
        self,
        check_type: HealthCheckType,
        handler: Callable
    ) -> None:
        """Register health check handler"""
        self._handlers[check_type] = handler

    def create_check(
        self,
        name: str,
        target: str,
        check_type: HealthCheckType = HealthCheckType.HTTP,
        http_url: Optional[str] = None,
        tcp_host: Optional[str] = None,
        tcp_port: Optional[int] = None,
        interval_seconds: int = 10,
        timeout_seconds: int = 5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> HealthCheck:
        """Create a health check"""
        check_id = f"hc_{uuid.uuid4().hex[:8]}"

        check = HealthCheck(
            id=check_id,
            name=name,
            target=target,
            check_type=check_type,
            http_url=http_url,
            tcp_host=tcp_host,
            tcp_port=tcp_port,
            interval_seconds=interval_seconds,
            timeout_seconds=timeout_seconds,
            metadata=metadata or {}
        )

        self.checks[check_id] = check
        return check

    def get_check(self, check_id: str) -> Optional[HealthCheck]:
        """Get health check by ID"""
        return self.checks.get(check_id)

    def delete_check(self, check_id: str) -> bool:
        """Delete health check"""
        if check_id in self.checks:
            del self.checks[check_id]
            return True
        return False

    def enable_check(self, check_id: str) -> bool:
        """Enable health check"""
        check = self.checks.get(check_id)
        if check:
            check.enabled = True
            return True
        return False

    def disable_check(self, check_id: str) -> bool:
        """Disable health check"""
        check = self.checks.get(check_id)
        if check:
            check.enabled = False
            return True
        return False

    def execute_check(self, check_id: str) -> Optional[HealthCheckResult]:
        """Execute a specific health check"""
        check = self.checks.get(check_id)
        if not check:
            return None

        handler = self._handlers.get(check.check_type)
        if not handler:
            return HealthCheckResult(
                check_id=check_id,
                status=HealthStatus.UNKNOWN,
                message=f"No handler for check type: {check.check_type.value}"
            )

        try:
            result = handler(check)
            check.record_result(result)
            return result
        except Exception as e:
            result = HealthCheckResult(
                check_id=check_id,
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {str(e)}"
            )
            check.record_result(result)
            return result

    def execute_all_due(self) -> List[HealthCheckResult]:
        """Execute all due health checks"""
        results = []
        for check in self.checks.values():
            if check.is_due():
                result = self.execute_check(check.id)
                if result:
                    results.append(result)
        return results

    def get_checks_for_target(self, target: str) -> List[HealthCheck]:
        """Get health checks for a target"""
        return [c for c in self.checks.values() if c.target == target]

    def get_all_checks(
        self,
        enabled_only: bool = False,
        check_type: Optional[HealthCheckType] = None
    ) -> List[HealthCheck]:
        """Get all health checks"""
        checks = list(self.checks.values())

        if enabled_only:
            checks = [c for c in checks if c.enabled]

        if check_type:
            checks = [c for c in checks if c.check_type == check_type]

        return checks

    def get_unhealthy_checks(self) -> List[HealthCheck]:
        """Get unhealthy checks"""
        return [
            c for c in self.checks.values()
            if c.last_status in (HealthStatus.UNHEALTHY, HealthStatus.DEGRADED)
        ]

    def ttl_heartbeat(self, check_id: str) -> bool:
        """Send TTL heartbeat"""
        check = self.checks.get(check_id)
        if check and check.check_type == HealthCheckType.TTL:
            check.last_check_at = datetime.now()
            check.last_status = HealthStatus.HEALTHY
            return True
        return False

    def get_statistics(self) -> dict:
        """Get health checker statistics"""
        by_status = {s.value: 0 for s in HealthStatus}
        by_type = {t.value: 0 for t in HealthCheckType}

        for check in self.checks.values():
            by_status[check.last_status.value] += 1
            by_type[check.check_type.value] += 1

        return {
            "total_checks": len(self.checks),
            "enabled_checks": len([c for c in self.checks.values() if c.enabled]),
            "unhealthy_checks": len(self.get_unhealthy_checks()),
            "by_status": by_status,
            "by_type": by_type,
            "registered_handlers": len(self._handlers)
        }


# Global health checker instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get or create the global health checker"""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker
