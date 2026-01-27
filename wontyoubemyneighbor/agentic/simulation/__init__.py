"""
Traffic Simulation Module

Provides traffic simulation and visualization for the ASI network.
"""

from .traffic_simulator import (
    TrafficSimulator,
    TrafficFlow,
    TrafficPattern,
    FlowStatistics,
    CongestionLevel,
    get_traffic_simulator,
    simulate_traffic,
    get_traffic_flows,
    get_traffic_heatmap,
    get_congestion_report,
)

__all__ = [
    "TrafficSimulator",
    "TrafficFlow",
    "TrafficPattern",
    "FlowStatistics",
    "CongestionLevel",
    "get_traffic_simulator",
    "simulate_traffic",
    "get_traffic_flows",
    "get_traffic_heatmap",
    "get_congestion_report",
]
