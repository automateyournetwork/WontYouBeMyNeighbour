"""
Traffic Generation Module

Provides traffic generation and analysis capabilities:
- iPerf-style traffic generation
- Bandwidth testing between agents
- Latency and jitter measurement
- Traffic profile management
"""

from .generator import (
    TrafficGenerator,
    TrafficFlow,
    TrafficProfile,
    TrafficPattern,
    FlowType,
    FlowStatus,
    get_traffic_generator
)

from .iperf import (
    IPerfClient,
    IPerfServer,
    IPerfResult,
    IPerfProtocol,
    get_iperf_manager
)

__all__ = [
    # Generator
    "TrafficGenerator",
    "TrafficFlow",
    "TrafficProfile",
    "TrafficPattern",
    "FlowType",
    "FlowStatus",
    "get_traffic_generator",
    # iPerf
    "IPerfClient",
    "IPerfServer",
    "IPerfResult",
    "IPerfProtocol",
    "get_iperf_manager"
]
