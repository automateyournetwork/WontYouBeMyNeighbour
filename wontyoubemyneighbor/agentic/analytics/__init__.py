"""
API Analytics Module

This module provides API usage analytics, rate limiting, and monitoring including:
- Request tracking and metrics
- Rate limiting per client/endpoint
- Response time analysis
- Error rate tracking
- Usage dashboards

Classes:
    TimeWindow: Enum of time windows for analytics
    MetricType: Enum of metric types
    RequestMetric: Individual request metric
    EndpointStats: Statistics for an endpoint
    ClientStats: Statistics for a client
    APIAnalytics: Main analytics engine

Functions:
    get_api_analytics: Get the singleton APIAnalytics instance
    record_request: Record an API request
    get_endpoint_stats: Get stats for an endpoint
    get_client_stats: Get stats for a client
"""

from .api_analytics import (
    TimeWindow,
    MetricType,
    RequestMetric,
    EndpointStats,
    ClientStats,
    RateLimitConfig,
    APIAnalytics,
)


# Singleton instance
_analytics_instance = None


def get_api_analytics() -> APIAnalytics:
    """Get the singleton APIAnalytics instance."""
    global _analytics_instance
    if _analytics_instance is None:
        _analytics_instance = APIAnalytics()
    return _analytics_instance


def record_request(
    endpoint: str,
    method: str,
    client_ip: str,
    status_code: int,
    response_time_ms: float,
    request_size: int = 0,
    response_size: int = 0
) -> None:
    """Record an API request."""
    analytics = get_api_analytics()
    analytics.record_request(
        endpoint=endpoint,
        method=method,
        client_ip=client_ip,
        status_code=status_code,
        response_time_ms=response_time_ms,
        request_size=request_size,
        response_size=response_size
    )


def get_endpoint_stats(endpoint: str, window: TimeWindow = None) -> EndpointStats:
    """Get statistics for an endpoint."""
    analytics = get_api_analytics()
    return analytics.get_endpoint_stats(endpoint, window)


def get_client_stats(client_ip: str, window: TimeWindow = None) -> ClientStats:
    """Get statistics for a client."""
    analytics = get_api_analytics()
    return analytics.get_client_stats(client_ip, window)


def check_rate_limit(client_ip: str, endpoint: str) -> bool:
    """Check if a client is rate limited for an endpoint."""
    analytics = get_api_analytics()
    return analytics.check_rate_limit(client_ip, endpoint)


__all__ = [
    'TimeWindow',
    'MetricType',
    'RequestMetric',
    'EndpointStats',
    'ClientStats',
    'RateLimitConfig',
    'APIAnalytics',
    'get_api_analytics',
    'record_request',
    'get_endpoint_stats',
    'get_client_stats',
    'check_rate_limit',
]
