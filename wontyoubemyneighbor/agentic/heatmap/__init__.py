"""
Traffic Heatmap Visualization Module

Provides visual representation of network traffic patterns:
- Link utilization heatmaps
- Node traffic intensity visualization
- Time-series traffic animation
- Hotspot detection and alerting
"""

from .collector import (
    TrafficCollector,
    TrafficSample,
    LinkTraffic,
    NodeTraffic,
    get_traffic_collector
)

from .renderer import (
    HeatmapRenderer,
    HeatmapData,
    HeatmapCell,
    ColorScale,
    HeatmapType
)

__all__ = [
    # Collector
    "TrafficCollector",
    "TrafficSample",
    "LinkTraffic",
    "NodeTraffic",
    "get_traffic_collector",
    # Renderer
    "HeatmapRenderer",
    "HeatmapData",
    "HeatmapCell",
    "ColorScale",
    "HeatmapType"
]
