"""
API Analytics and Rate Limiting

Provides comprehensive API usage tracking, analytics, and rate limiting.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import logging
import threading
import time

logger = logging.getLogger(__name__)


class TimeWindow(Enum):
    """Time windows for analytics aggregation."""
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    ALL = "all"


class MetricType(Enum):
    """Types of metrics tracked."""
    REQUEST_COUNT = "request_count"
    ERROR_COUNT = "error_count"
    RESPONSE_TIME = "response_time"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    BYTES_IN = "bytes_in"
    BYTES_OUT = "bytes_out"


@dataclass
class RequestMetric:
    """Individual request metric."""
    timestamp: datetime
    endpoint: str
    method: str
    client_ip: str
    status_code: int
    response_time_ms: float
    request_size: int = 0
    response_size: int = 0
    user_agent: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "endpoint": self.endpoint,
            "method": self.method,
            "client_ip": self.client_ip,
            "status_code": self.status_code,
            "response_time_ms": self.response_time_ms,
            "request_size": self.request_size,
            "response_size": self.response_size,
            "user_agent": self.user_agent,
            "error_message": self.error_message,
            "is_error": self.status_code >= 400
        }


@dataclass
class EndpointStats:
    """Statistics for a single endpoint."""
    endpoint: str
    total_requests: int = 0
    error_requests: int = 0
    total_response_time_ms: float = 0.0
    min_response_time_ms: float = float('inf')
    max_response_time_ms: float = 0.0
    total_bytes_in: int = 0
    total_bytes_out: int = 0
    status_codes: Dict[int, int] = field(default_factory=dict)
    methods: Dict[str, int] = field(default_factory=dict)
    first_request: Optional[datetime] = None
    last_request: Optional[datetime] = None

    @property
    def avg_response_time_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_response_time_ms / self.total_requests

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.error_requests / self.total_requests) * 100

    @property
    def requests_per_minute(self) -> float:
        if not self.first_request or not self.last_request:
            return 0.0
        duration = (self.last_request - self.first_request).total_seconds()
        if duration <= 0:
            return self.total_requests
        return (self.total_requests / duration) * 60

    def to_dict(self) -> Dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "total_requests": self.total_requests,
            "error_requests": self.error_requests,
            "error_rate": round(self.error_rate, 2),
            "avg_response_time_ms": round(self.avg_response_time_ms, 2),
            "min_response_time_ms": round(self.min_response_time_ms, 2) if self.min_response_time_ms != float('inf') else 0,
            "max_response_time_ms": round(self.max_response_time_ms, 2),
            "total_bytes_in": self.total_bytes_in,
            "total_bytes_out": self.total_bytes_out,
            "requests_per_minute": round(self.requests_per_minute, 2),
            "status_codes": self.status_codes,
            "methods": self.methods,
            "first_request": self.first_request.isoformat() if self.first_request else None,
            "last_request": self.last_request.isoformat() if self.last_request else None
        }


@dataclass
class ClientStats:
    """Statistics for a single client."""
    client_ip: str
    total_requests: int = 0
    error_requests: int = 0
    total_response_time_ms: float = 0.0
    total_bytes_in: int = 0
    total_bytes_out: int = 0
    endpoints_accessed: Dict[str, int] = field(default_factory=dict)
    first_request: Optional[datetime] = None
    last_request: Optional[datetime] = None
    is_rate_limited: bool = False
    rate_limit_until: Optional[datetime] = None

    @property
    def avg_response_time_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_response_time_ms / self.total_requests

    @property
    def requests_per_minute(self) -> float:
        if not self.first_request or not self.last_request:
            return 0.0
        duration = (self.last_request - self.first_request).total_seconds()
        if duration <= 0:
            return self.total_requests
        return (self.total_requests / duration) * 60

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_ip": self.client_ip,
            "total_requests": self.total_requests,
            "error_requests": self.error_requests,
            "avg_response_time_ms": round(self.avg_response_time_ms, 2),
            "total_bytes_in": self.total_bytes_in,
            "total_bytes_out": self.total_bytes_out,
            "requests_per_minute": round(self.requests_per_minute, 2),
            "endpoints_accessed": self.endpoints_accessed,
            "unique_endpoints": len(self.endpoints_accessed),
            "first_request": self.first_request.isoformat() if self.first_request else None,
            "last_request": self.last_request.isoformat() if self.last_request else None,
            "is_rate_limited": self.is_rate_limited,
            "rate_limit_until": self.rate_limit_until.isoformat() if self.rate_limit_until else None
        }


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_limit: int = 20  # Max requests in 1 second
    block_duration_seconds: int = 60
    enabled: bool = True
    whitelist: List[str] = field(default_factory=list)
    blacklist: List[str] = field(default_factory=list)
    endpoint_limits: Dict[str, int] = field(default_factory=dict)  # Override per endpoint

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requests_per_minute": self.requests_per_minute,
            "requests_per_hour": self.requests_per_hour,
            "burst_limit": self.burst_limit,
            "block_duration_seconds": self.block_duration_seconds,
            "enabled": self.enabled,
            "whitelist": self.whitelist,
            "blacklist": self.blacklist,
            "endpoint_limits": self.endpoint_limits
        }


@dataclass
class TimeSeriesPoint:
    """A point in a time series."""
    timestamp: datetime
    value: float
    count: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "count": self.count
        }


class APIAnalytics:
    """API analytics and rate limiting engine."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # Request storage (circular buffer)
        self._max_requests = 100000
        self._requests: List[RequestMetric] = []
        self._requests_lock = threading.Lock()

        # Aggregated stats
        self._endpoint_stats: Dict[str, EndpointStats] = {}
        self._client_stats: Dict[str, ClientStats] = {}

        # Rate limiting
        self._rate_limit_config = RateLimitConfig()
        self._client_request_times: Dict[str, List[datetime]] = defaultdict(list)
        self._blocked_clients: Dict[str, datetime] = {}

        # Time series data (for graphs)
        self._time_series: Dict[str, List[TimeSeriesPoint]] = defaultdict(list)

        # Summary stats
        self._total_requests = 0
        self._total_errors = 0
        self._start_time = datetime.now()

        logger.info("APIAnalytics initialized")

    def record_request(
        self,
        endpoint: str,
        method: str,
        client_ip: str,
        status_code: int,
        response_time_ms: float,
        request_size: int = 0,
        response_size: int = 0,
        user_agent: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Record a new API request."""
        now = datetime.now()
        is_error = status_code >= 400

        # Create metric
        metric = RequestMetric(
            timestamp=now,
            endpoint=endpoint,
            method=method,
            client_ip=client_ip,
            status_code=status_code,
            response_time_ms=response_time_ms,
            request_size=request_size,
            response_size=response_size,
            user_agent=user_agent,
            error_message=error_message
        )

        # Store request
        with self._requests_lock:
            self._requests.append(metric)
            # Trim if exceeds max
            if len(self._requests) > self._max_requests:
                self._requests = self._requests[-self._max_requests:]

        # Update endpoint stats
        self._update_endpoint_stats(endpoint, method, status_code, response_time_ms,
                                    request_size, response_size, now, is_error)

        # Update client stats
        self._update_client_stats(client_ip, endpoint, status_code, response_time_ms,
                                  request_size, response_size, now, is_error)

        # Update rate limiting tracking
        self._track_rate_limit(client_ip, now)

        # Update time series
        self._update_time_series(now, response_time_ms, is_error)

        # Update totals
        self._total_requests += 1
        if is_error:
            self._total_errors += 1

    def _update_endpoint_stats(
        self, endpoint: str, method: str, status_code: int, response_time_ms: float,
        request_size: int, response_size: int, timestamp: datetime, is_error: bool
    ) -> None:
        """Update statistics for an endpoint."""
        if endpoint not in self._endpoint_stats:
            self._endpoint_stats[endpoint] = EndpointStats(endpoint=endpoint)

        stats = self._endpoint_stats[endpoint]
        stats.total_requests += 1
        if is_error:
            stats.error_requests += 1

        stats.total_response_time_ms += response_time_ms
        stats.min_response_time_ms = min(stats.min_response_time_ms, response_time_ms)
        stats.max_response_time_ms = max(stats.max_response_time_ms, response_time_ms)
        stats.total_bytes_in += request_size
        stats.total_bytes_out += response_size

        # Track status codes
        stats.status_codes[status_code] = stats.status_codes.get(status_code, 0) + 1

        # Track methods
        stats.methods[method] = stats.methods.get(method, 0) + 1

        # Update timestamps
        if stats.first_request is None:
            stats.first_request = timestamp
        stats.last_request = timestamp

    def _update_client_stats(
        self, client_ip: str, endpoint: str, status_code: int, response_time_ms: float,
        request_size: int, response_size: int, timestamp: datetime, is_error: bool
    ) -> None:
        """Update statistics for a client."""
        if client_ip not in self._client_stats:
            self._client_stats[client_ip] = ClientStats(client_ip=client_ip)

        stats = self._client_stats[client_ip]
        stats.total_requests += 1
        if is_error:
            stats.error_requests += 1

        stats.total_response_time_ms += response_time_ms
        stats.total_bytes_in += request_size
        stats.total_bytes_out += response_size

        # Track endpoints
        stats.endpoints_accessed[endpoint] = stats.endpoints_accessed.get(endpoint, 0) + 1

        # Update timestamps
        if stats.first_request is None:
            stats.first_request = timestamp
        stats.last_request = timestamp

    def _track_rate_limit(self, client_ip: str, timestamp: datetime) -> None:
        """Track request times for rate limiting."""
        # Clean old entries (older than 1 hour)
        cutoff = timestamp - timedelta(hours=1)
        self._client_request_times[client_ip] = [
            t for t in self._client_request_times[client_ip]
            if t > cutoff
        ]
        self._client_request_times[client_ip].append(timestamp)

    def _update_time_series(self, timestamp: datetime, response_time_ms: float, is_error: bool) -> None:
        """Update time series data."""
        # Round to minute for aggregation
        minute_key = timestamp.replace(second=0, microsecond=0)

        # Request count time series
        req_series = self._time_series["requests"]
        if req_series and req_series[-1].timestamp == minute_key:
            req_series[-1].count += 1
            req_series[-1].value = req_series[-1].count
        else:
            req_series.append(TimeSeriesPoint(timestamp=minute_key, value=1, count=1))

        # Response time time series
        rt_series = self._time_series["response_time"]
        if rt_series and rt_series[-1].timestamp == minute_key:
            rt_series[-1].value = (rt_series[-1].value * rt_series[-1].count + response_time_ms) / (rt_series[-1].count + 1)
            rt_series[-1].count += 1
        else:
            rt_series.append(TimeSeriesPoint(timestamp=minute_key, value=response_time_ms, count=1))

        # Error count time series
        if is_error:
            err_series = self._time_series["errors"]
            if err_series and err_series[-1].timestamp == minute_key:
                err_series[-1].count += 1
                err_series[-1].value = err_series[-1].count
            else:
                err_series.append(TimeSeriesPoint(timestamp=minute_key, value=1, count=1))

        # Trim old data (keep last 24 hours)
        cutoff = timestamp - timedelta(hours=24)
        for key in self._time_series:
            self._time_series[key] = [
                p for p in self._time_series[key]
                if p.timestamp > cutoff
            ]

    def check_rate_limit(self, client_ip: str, endpoint: str = None) -> Tuple[bool, Optional[str]]:
        """
        Check if a client is rate limited.
        Returns (is_allowed, reason) tuple.
        """
        if not self._rate_limit_config.enabled:
            return True, None

        # Check whitelist
        if client_ip in self._rate_limit_config.whitelist:
            return True, None

        # Check blacklist
        if client_ip in self._rate_limit_config.blacklist:
            return False, "Client is blacklisted"

        # Check if currently blocked
        if client_ip in self._blocked_clients:
            block_until = self._blocked_clients[client_ip]
            if datetime.now() < block_until:
                return False, f"Rate limited until {block_until.isoformat()}"
            else:
                del self._blocked_clients[client_ip]

        now = datetime.now()
        request_times = self._client_request_times.get(client_ip, [])

        # Get limit for endpoint
        if endpoint and endpoint in self._rate_limit_config.endpoint_limits:
            limit_per_minute = self._rate_limit_config.endpoint_limits[endpoint]
        else:
            limit_per_minute = self._rate_limit_config.requests_per_minute

        # Check burst limit (last second)
        one_second_ago = now - timedelta(seconds=1)
        burst_count = sum(1 for t in request_times if t > one_second_ago)
        if burst_count >= self._rate_limit_config.burst_limit:
            self._block_client(client_ip)
            return False, f"Burst limit exceeded ({burst_count} requests in 1 second)"

        # Check per-minute limit
        one_minute_ago = now - timedelta(minutes=1)
        minute_count = sum(1 for t in request_times if t > one_minute_ago)
        if minute_count >= limit_per_minute:
            self._block_client(client_ip)
            return False, f"Rate limit exceeded ({minute_count} requests in last minute)"

        # Check per-hour limit
        one_hour_ago = now - timedelta(hours=1)
        hour_count = sum(1 for t in request_times if t > one_hour_ago)
        if hour_count >= self._rate_limit_config.requests_per_hour:
            self._block_client(client_ip)
            return False, f"Hourly limit exceeded ({hour_count} requests in last hour)"

        return True, None

    def _block_client(self, client_ip: str) -> None:
        """Block a client for the configured duration."""
        block_until = datetime.now() + timedelta(seconds=self._rate_limit_config.block_duration_seconds)
        self._blocked_clients[client_ip] = block_until

        # Update client stats
        if client_ip in self._client_stats:
            self._client_stats[client_ip].is_rate_limited = True
            self._client_stats[client_ip].rate_limit_until = block_until

        logger.warning(f"Client {client_ip} blocked until {block_until}")

    def get_endpoint_stats(self, endpoint: str, window: TimeWindow = None) -> Optional[EndpointStats]:
        """Get statistics for a specific endpoint."""
        if window is None or window == TimeWindow.ALL:
            return self._endpoint_stats.get(endpoint)

        # Calculate stats for time window
        cutoff = self._get_window_cutoff(window)
        if cutoff is None:
            return self._endpoint_stats.get(endpoint)

        # Filter requests
        with self._requests_lock:
            filtered = [r for r in self._requests if r.endpoint == endpoint and r.timestamp > cutoff]

        if not filtered:
            return None

        stats = EndpointStats(endpoint=endpoint)
        for r in filtered:
            stats.total_requests += 1
            if r.status_code >= 400:
                stats.error_requests += 1
            stats.total_response_time_ms += r.response_time_ms
            stats.min_response_time_ms = min(stats.min_response_time_ms, r.response_time_ms)
            stats.max_response_time_ms = max(stats.max_response_time_ms, r.response_time_ms)
            stats.total_bytes_in += r.request_size
            stats.total_bytes_out += r.response_size
            stats.status_codes[r.status_code] = stats.status_codes.get(r.status_code, 0) + 1
            stats.methods[r.method] = stats.methods.get(r.method, 0) + 1
            if stats.first_request is None:
                stats.first_request = r.timestamp
            stats.last_request = r.timestamp

        return stats

    def get_client_stats(self, client_ip: str, window: TimeWindow = None) -> Optional[ClientStats]:
        """Get statistics for a specific client."""
        if window is None or window == TimeWindow.ALL:
            return self._client_stats.get(client_ip)

        # Calculate stats for time window
        cutoff = self._get_window_cutoff(window)
        if cutoff is None:
            return self._client_stats.get(client_ip)

        # Filter requests
        with self._requests_lock:
            filtered = [r for r in self._requests if r.client_ip == client_ip and r.timestamp > cutoff]

        if not filtered:
            return None

        stats = ClientStats(client_ip=client_ip)
        for r in filtered:
            stats.total_requests += 1
            if r.status_code >= 400:
                stats.error_requests += 1
            stats.total_response_time_ms += r.response_time_ms
            stats.total_bytes_in += r.request_size
            stats.total_bytes_out += r.response_size
            stats.endpoints_accessed[r.endpoint] = stats.endpoints_accessed.get(r.endpoint, 0) + 1
            if stats.first_request is None:
                stats.first_request = r.timestamp
            stats.last_request = r.timestamp

        # Check current rate limit status
        if client_ip in self._blocked_clients:
            stats.is_rate_limited = True
            stats.rate_limit_until = self._blocked_clients[client_ip]

        return stats

    def _get_window_cutoff(self, window: TimeWindow) -> Optional[datetime]:
        """Get the cutoff datetime for a time window."""
        now = datetime.now()
        if window == TimeWindow.MINUTE:
            return now - timedelta(minutes=1)
        elif window == TimeWindow.HOUR:
            return now - timedelta(hours=1)
        elif window == TimeWindow.DAY:
            return now - timedelta(days=1)
        elif window == TimeWindow.WEEK:
            return now - timedelta(weeks=1)
        elif window == TimeWindow.MONTH:
            return now - timedelta(days=30)
        return None

    def get_all_endpoint_stats(self, window: TimeWindow = None) -> List[EndpointStats]:
        """Get statistics for all endpoints."""
        if window is None or window == TimeWindow.ALL:
            return list(self._endpoint_stats.values())

        endpoints = set(self._endpoint_stats.keys())
        return [self.get_endpoint_stats(e, window) for e in endpoints if self.get_endpoint_stats(e, window)]

    def get_all_client_stats(self, window: TimeWindow = None) -> List[ClientStats]:
        """Get statistics for all clients."""
        if window is None or window == TimeWindow.ALL:
            return list(self._client_stats.values())

        clients = set(self._client_stats.keys())
        return [self.get_client_stats(c, window) for c in clients if self.get_client_stats(c, window)]

    def get_top_endpoints(self, limit: int = 10, metric: str = "requests") -> List[Dict[str, Any]]:
        """Get top endpoints by a metric."""
        endpoints = list(self._endpoint_stats.values())

        if metric == "requests":
            endpoints.sort(key=lambda e: e.total_requests, reverse=True)
        elif metric == "errors":
            endpoints.sort(key=lambda e: e.error_requests, reverse=True)
        elif metric == "response_time":
            endpoints.sort(key=lambda e: e.avg_response_time_ms, reverse=True)
        elif metric == "bytes":
            endpoints.sort(key=lambda e: e.total_bytes_out, reverse=True)

        return [e.to_dict() for e in endpoints[:limit]]

    def get_top_clients(self, limit: int = 10, metric: str = "requests") -> List[Dict[str, Any]]:
        """Get top clients by a metric."""
        clients = list(self._client_stats.values())

        if metric == "requests":
            clients.sort(key=lambda c: c.total_requests, reverse=True)
        elif metric == "errors":
            clients.sort(key=lambda c: c.error_requests, reverse=True)
        elif metric == "bytes":
            clients.sort(key=lambda c: c.total_bytes_out, reverse=True)

        return [c.to_dict() for c in clients[:limit]]

    def get_time_series(self, metric: str = "requests", window: TimeWindow = TimeWindow.HOUR) -> List[Dict[str, Any]]:
        """Get time series data for a metric."""
        series = self._time_series.get(metric, [])

        cutoff = self._get_window_cutoff(window)
        if cutoff:
            series = [p for p in series if p.timestamp > cutoff]

        return [p.to_dict() for p in series]

    def get_recent_requests(self, limit: int = 100, endpoint: str = None, client_ip: str = None) -> List[Dict[str, Any]]:
        """Get recent requests with optional filtering."""
        with self._requests_lock:
            requests = self._requests.copy()

        if endpoint:
            requests = [r for r in requests if r.endpoint == endpoint]
        if client_ip:
            requests = [r for r in requests if r.client_ip == client_ip]

        # Return most recent
        requests = requests[-limit:]
        requests.reverse()  # Newest first

        return [r.to_dict() for r in requests]

    def get_error_summary(self, window: TimeWindow = TimeWindow.HOUR) -> Dict[str, Any]:
        """Get summary of errors."""
        cutoff = self._get_window_cutoff(window)

        with self._requests_lock:
            if cutoff:
                errors = [r for r in self._requests if r.status_code >= 400 and r.timestamp > cutoff]
            else:
                errors = [r for r in self._requests if r.status_code >= 400]

        # Group by status code
        by_status = defaultdict(int)
        by_endpoint = defaultdict(int)
        error_messages = defaultdict(int)

        for e in errors:
            by_status[e.status_code] += 1
            by_endpoint[e.endpoint] += 1
            if e.error_message:
                error_messages[e.error_message] += 1

        return {
            "total_errors": len(errors),
            "by_status_code": dict(by_status),
            "by_endpoint": dict(by_endpoint),
            "common_messages": dict(list(sorted(error_messages.items(), key=lambda x: x[1], reverse=True))[:10]),
            "recent_errors": [e.to_dict() for e in errors[-10:]]
        }

    def get_rate_limit_config(self) -> Dict[str, Any]:
        """Get current rate limit configuration."""
        return self._rate_limit_config.to_dict()

    def set_rate_limit_config(
        self,
        requests_per_minute: int = None,
        requests_per_hour: int = None,
        burst_limit: int = None,
        block_duration_seconds: int = None,
        enabled: bool = None,
        whitelist: List[str] = None,
        blacklist: List[str] = None,
        endpoint_limits: Dict[str, int] = None
    ) -> Dict[str, Any]:
        """Update rate limit configuration."""
        if requests_per_minute is not None:
            self._rate_limit_config.requests_per_minute = requests_per_minute
        if requests_per_hour is not None:
            self._rate_limit_config.requests_per_hour = requests_per_hour
        if burst_limit is not None:
            self._rate_limit_config.burst_limit = burst_limit
        if block_duration_seconds is not None:
            self._rate_limit_config.block_duration_seconds = block_duration_seconds
        if enabled is not None:
            self._rate_limit_config.enabled = enabled
        if whitelist is not None:
            self._rate_limit_config.whitelist = whitelist
        if blacklist is not None:
            self._rate_limit_config.blacklist = blacklist
        if endpoint_limits is not None:
            self._rate_limit_config.endpoint_limits = endpoint_limits

        return self._rate_limit_config.to_dict()

    def get_blocked_clients(self) -> List[Dict[str, Any]]:
        """Get list of currently blocked clients."""
        now = datetime.now()
        blocked = []
        for client_ip, until in list(self._blocked_clients.items()):
            if until > now:
                blocked.append({
                    "client_ip": client_ip,
                    "blocked_until": until.isoformat(),
                    "remaining_seconds": (until - now).total_seconds()
                })
            else:
                del self._blocked_clients[client_ip]
        return blocked

    def unblock_client(self, client_ip: str) -> bool:
        """Unblock a client."""
        if client_ip in self._blocked_clients:
            del self._blocked_clients[client_ip]
            if client_ip in self._client_stats:
                self._client_stats[client_ip].is_rate_limited = False
                self._client_stats[client_ip].rate_limit_until = None
            return True
        return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get overall analytics statistics."""
        uptime = (datetime.now() - self._start_time).total_seconds()

        return {
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "error_rate": round((self._total_errors / max(self._total_requests, 1)) * 100, 2),
            "unique_endpoints": len(self._endpoint_stats),
            "unique_clients": len(self._client_stats),
            "blocked_clients": len(self._blocked_clients),
            "requests_per_second": round(self._total_requests / max(uptime, 1), 2),
            "uptime_seconds": round(uptime, 2),
            "start_time": self._start_time.isoformat(),
            "rate_limiting_enabled": self._rate_limit_config.enabled,
            "stored_requests": len(self._requests),
            "max_stored_requests": self._max_requests
        }

    def clear_stats(self, keep_config: bool = True) -> None:
        """Clear all statistics."""
        with self._requests_lock:
            self._requests = []

        self._endpoint_stats = {}
        self._client_stats = {}
        self._client_request_times = defaultdict(list)
        self._blocked_clients = {}
        self._time_series = defaultdict(list)
        self._total_requests = 0
        self._total_errors = 0
        self._start_time = datetime.now()

        if not keep_config:
            self._rate_limit_config = RateLimitConfig()

        logger.info("Analytics statistics cleared")
