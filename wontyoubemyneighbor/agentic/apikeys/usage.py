"""
API Key Usage Tracking

Provides:
- Usage recording and analytics
- Usage summaries and reports
- Quota tracking
- Usage alerts
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict


class UsagePeriod(Enum):
    """Usage tracking periods"""
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


@dataclass
class UsageRecord:
    """Single usage record"""

    key_id: str
    endpoint: str
    method: str
    timestamp: datetime = field(default_factory=datetime.now)
    response_code: int = 200
    latency_ms: float = 0.0
    request_size_bytes: int = 0
    response_size_bytes: int = 0
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "key_id": self.key_id,
            "endpoint": self.endpoint,
            "method": self.method,
            "timestamp": self.timestamp.isoformat(),
            "response_code": self.response_code,
            "latency_ms": self.latency_ms,
            "request_size_bytes": self.request_size_bytes,
            "response_size_bytes": self.response_size_bytes
        }


@dataclass
class UsageSummary:
    """Usage summary for a key"""

    key_id: str
    period: UsagePeriod
    period_start: datetime
    period_end: datetime
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0
    total_request_bytes: int = 0
    total_response_bytes: int = 0
    endpoint_counts: Dict[str, int] = field(default_factory=dict)
    method_counts: Dict[str, int] = field(default_factory=dict)
    error_counts: Dict[int, int] = field(default_factory=dict)
    unique_ips: int = 0

    @property
    def avg_latency_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    def to_dict(self) -> dict:
        return {
            "key_id": self.key_id,
            "period": self.period.value,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "avg_latency_ms": self.avg_latency_ms,
            "success_rate": self.success_rate,
            "total_request_bytes": self.total_request_bytes,
            "total_response_bytes": self.total_response_bytes,
            "endpoint_counts": self.endpoint_counts,
            "method_counts": self.method_counts,
            "error_counts": {str(k): v for k, v in self.error_counts.items()},
            "unique_ips": self.unique_ips
        }


class UsageTracker:
    """Tracks API key usage"""

    def __init__(self, max_records: int = 100000):
        self.records: List[UsageRecord] = []
        self.max_records = max_records
        # Aggregated counts per key
        self._key_counts: Dict[str, int] = defaultdict(int)
        self._hourly_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._daily_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # Unique IPs per key
        self._key_ips: Dict[str, set] = defaultdict(set)
        # Endpoint tracking
        self._endpoint_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def record(
        self,
        key_id: str,
        endpoint: str,
        method: str,
        response_code: int = 200,
        latency_ms: float = 0.0,
        request_size_bytes: int = 0,
        response_size_bytes: int = 0,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> UsageRecord:
        """Record a usage event"""
        record = UsageRecord(
            key_id=key_id,
            endpoint=endpoint,
            method=method,
            response_code=response_code,
            latency_ms=latency_ms,
            request_size_bytes=request_size_bytes,
            response_size_bytes=response_size_bytes,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata or {}
        )

        self.records.append(record)

        # Update aggregated counts
        self._key_counts[key_id] += 1

        # Hourly tracking
        hour_key = record.timestamp.strftime("%Y-%m-%d-%H")
        self._hourly_counts[key_id][hour_key] += 1

        # Daily tracking
        day_key = record.timestamp.strftime("%Y-%m-%d")
        self._daily_counts[key_id][day_key] += 1

        # IP tracking
        if ip_address:
            self._key_ips[key_id].add(ip_address)

        # Endpoint tracking
        self._endpoint_counts[key_id][endpoint] += 1

        # Trim if needed
        if len(self.records) > self.max_records:
            self.records = self.records[-self.max_records // 2:]

        return record

    def get_records(
        self,
        key_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        endpoint: Optional[str] = None,
        limit: int = 100
    ) -> List[UsageRecord]:
        """Get usage records with filters"""
        records = self.records

        if key_id:
            records = [r for r in records if r.key_id == key_id]

        if start_time:
            records = [r for r in records if r.timestamp >= start_time]

        if end_time:
            records = [r for r in records if r.timestamp <= end_time]

        if endpoint:
            records = [r for r in records if r.endpoint == endpoint]

        return records[-limit:]

    def get_summary(
        self,
        key_id: str,
        period: UsagePeriod = UsagePeriod.DAY,
        periods_back: int = 1
    ) -> UsageSummary:
        """Get usage summary for a key"""
        now = datetime.now()

        # Calculate period boundaries
        if period == UsagePeriod.MINUTE:
            period_start = now - timedelta(minutes=periods_back)
        elif period == UsagePeriod.HOUR:
            period_start = now - timedelta(hours=periods_back)
        elif period == UsagePeriod.DAY:
            period_start = now - timedelta(days=periods_back)
        elif period == UsagePeriod.WEEK:
            period_start = now - timedelta(weeks=periods_back)
        else:  # MONTH
            period_start = now - timedelta(days=30 * periods_back)

        # Filter records
        records = [
            r for r in self.records
            if r.key_id == key_id and r.timestamp >= period_start
        ]

        # Build summary
        summary = UsageSummary(
            key_id=key_id,
            period=period,
            period_start=period_start,
            period_end=now
        )

        ips = set()
        for record in records:
            summary.total_requests += 1
            summary.total_latency_ms += record.latency_ms
            summary.total_request_bytes += record.request_size_bytes
            summary.total_response_bytes += record.response_size_bytes

            if 200 <= record.response_code < 400:
                summary.successful_requests += 1
            else:
                summary.failed_requests += 1
                summary.error_counts[record.response_code] = \
                    summary.error_counts.get(record.response_code, 0) + 1

            summary.endpoint_counts[record.endpoint] = \
                summary.endpoint_counts.get(record.endpoint, 0) + 1
            summary.method_counts[record.method] = \
                summary.method_counts.get(record.method, 0) + 1

            if record.ip_address:
                ips.add(record.ip_address)

        summary.unique_ips = len(ips)
        return summary

    def get_key_usage(self, key_id: str) -> Dict[str, Any]:
        """Get comprehensive usage data for a key"""
        total = self._key_counts.get(key_id, 0)
        hourly = dict(self._hourly_counts.get(key_id, {}))
        daily = dict(self._daily_counts.get(key_id, {}))
        endpoints = dict(self._endpoint_counts.get(key_id, {}))
        unique_ips = len(self._key_ips.get(key_id, set()))

        # Recent summary
        recent_summary = self.get_summary(key_id, UsagePeriod.HOUR, 1)

        return {
            "key_id": key_id,
            "total_requests": total,
            "unique_ips": unique_ips,
            "hourly_counts": hourly,
            "daily_counts": daily,
            "endpoint_counts": endpoints,
            "recent_hour": recent_summary.to_dict()
        }

    def get_top_keys(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get keys with highest usage"""
        sorted_keys = sorted(
            self._key_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]

        return [
            {"key_id": k, "total_requests": v}
            for k, v in sorted_keys
        ]

    def get_top_endpoints(
        self,
        key_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get most used endpoints"""
        if key_id:
            endpoint_counts = self._endpoint_counts.get(key_id, {})
        else:
            # Aggregate across all keys
            endpoint_counts: Dict[str, int] = {}
            for key_endpoints in self._endpoint_counts.values():
                for ep, count in key_endpoints.items():
                    endpoint_counts[ep] = endpoint_counts.get(ep, 0) + count

        sorted_endpoints = sorted(
            endpoint_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]

        return [
            {"endpoint": ep, "count": count}
            for ep, count in sorted_endpoints
        ]

    def get_statistics(self) -> dict:
        """Get tracker statistics"""
        total_records = len(self.records)
        unique_keys = len(self._key_counts)

        # Calculate recent stats
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        recent_records = [r for r in self.records if r.timestamp >= hour_ago]

        return {
            "total_records": total_records,
            "max_records": self.max_records,
            "unique_keys": unique_keys,
            "records_last_hour": len(recent_records),
            "top_keys": self.get_top_keys(5),
            "top_endpoints": self.get_top_endpoints(limit=5)
        }

    def clear_old_records(self, days: int = 30) -> int:
        """Clear records older than specified days"""
        cutoff = datetime.now() - timedelta(days=days)
        original_count = len(self.records)
        self.records = [r for r in self.records if r.timestamp >= cutoff]
        return original_count - len(self.records)


# Global usage tracker instance
_usage_tracker: Optional[UsageTracker] = None


def get_usage_tracker() -> UsageTracker:
    """Get or create the global usage tracker"""
    global _usage_tracker
    if _usage_tracker is None:
        _usage_tracker = UsageTracker()
    return _usage_tracker
