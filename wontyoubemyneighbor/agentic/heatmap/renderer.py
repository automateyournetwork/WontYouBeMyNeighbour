"""
Heatmap Renderer - Generates visual heatmap data for traffic visualization

Renders:
- Grid-based heatmaps for link utilization
- Node-centric traffic intensity maps
- Time-series animated heatmaps
- Geographic overlay data
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
import math

logger = logging.getLogger("HeatmapRenderer")


class HeatmapType(Enum):
    """Types of heatmap visualizations"""
    LINK_UTILIZATION = "link_utilization"
    NODE_TRAFFIC = "node_traffic"
    LATENCY = "latency"
    PACKET_LOSS = "packet_loss"
    ERROR_RATE = "error_rate"
    PROTOCOL_ACTIVITY = "protocol_activity"


class ColorScale(Enum):
    """Predefined color scales for heatmaps"""
    TRAFFIC = "traffic"       # Green -> Yellow -> Red
    THERMAL = "thermal"       # Blue -> Purple -> Red
    VIRIDIS = "viridis"       # Purple -> Green -> Yellow
    COOLWARM = "coolwarm"     # Blue -> White -> Red
    SEVERITY = "severity"     # Green -> Yellow -> Orange -> Red


@dataclass
class HeatmapCell:
    """
    A single cell in the heatmap grid

    Attributes:
        x: X coordinate
        y: Y coordinate
        value: Normalized value (0-1)
        raw_value: Original value
        label: Display label
        color: Computed RGB color
    """
    x: int
    y: int
    value: float
    raw_value: float
    label: str = ""
    color: str = "#000000"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "value": self.value,
            "raw_value": self.raw_value,
            "label": self.label,
            "color": self.color,
            "metadata": self.metadata
        }


@dataclass
class HeatmapData:
    """
    Complete heatmap visualization data

    Attributes:
        heatmap_id: Unique identifier
        heatmap_type: Type of heatmap
        title: Display title
        width: Grid width
        height: Grid height
        cells: Heatmap cells
        color_scale: Color scale used
        min_value: Minimum value in data
        max_value: Maximum value in data
    """
    heatmap_id: str
    heatmap_type: HeatmapType
    title: str
    width: int
    height: int
    cells: List[HeatmapCell] = field(default_factory=list)
    color_scale: ColorScale = ColorScale.TRAFFIC
    min_value: float = 0.0
    max_value: float = 100.0
    generated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "heatmap_id": self.heatmap_id,
            "heatmap_type": self.heatmap_type.value,
            "title": self.title,
            "width": self.width,
            "height": self.height,
            "cells": [c.to_dict() for c in self.cells],
            "color_scale": self.color_scale.value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "generated_at": self.generated_at.isoformat(),
            "cell_count": len(self.cells),
            "metadata": self.metadata
        }


class HeatmapRenderer:
    """
    Renders traffic data as heatmap visualizations
    """

    def __init__(self):
        """Initialize heatmap renderer"""
        self._heatmap_counter = 0

        # Color scale definitions (RGB tuples)
        self._color_scales = {
            ColorScale.TRAFFIC: [
                (0.0, (34, 139, 34)),    # Forest green
                (0.3, (144, 238, 144)),  # Light green
                (0.5, (255, 255, 0)),    # Yellow
                (0.7, (255, 165, 0)),    # Orange
                (0.85, (255, 69, 0)),    # Red-orange
                (1.0, (139, 0, 0))       # Dark red
            ],
            ColorScale.THERMAL: [
                (0.0, (0, 0, 139)),      # Dark blue
                (0.25, (65, 105, 225)),  # Royal blue
                (0.5, (148, 0, 211)),    # Violet
                (0.75, (255, 20, 147)),  # Deep pink
                (1.0, (255, 0, 0))       # Red
            ],
            ColorScale.VIRIDIS: [
                (0.0, (68, 1, 84)),      # Dark purple
                (0.25, (59, 82, 139)),   # Blue-purple
                (0.5, (33, 145, 140)),   # Teal
                (0.75, (94, 201, 98)),   # Green
                (1.0, (253, 231, 37))    # Yellow
            ],
            ColorScale.COOLWARM: [
                (0.0, (59, 76, 192)),    # Blue
                (0.25, (103, 169, 207)), # Light blue
                (0.5, (247, 247, 247)),  # White
                (0.75, (239, 138, 98)),  # Light red
                (1.0, (180, 4, 38))      # Red
            ],
            ColorScale.SEVERITY: [
                (0.0, (46, 204, 113)),   # Green
                (0.33, (241, 196, 15)),  # Yellow
                (0.66, (230, 126, 34)),  # Orange
                (1.0, (231, 76, 60))     # Red
            ]
        }

    def _generate_heatmap_id(self) -> str:
        """Generate unique heatmap ID"""
        self._heatmap_counter += 1
        return f"heatmap-{self._heatmap_counter:06d}"

    def _interpolate_color(
        self,
        value: float,
        scale: ColorScale
    ) -> str:
        """
        Interpolate color based on value and scale

        Args:
            value: Normalized value (0-1)
            scale: Color scale to use

        Returns:
            Hex color string
        """
        value = max(0.0, min(1.0, value))
        stops = self._color_scales.get(scale, self._color_scales[ColorScale.TRAFFIC])

        # Find surrounding stops
        lower_stop = stops[0]
        upper_stop = stops[-1]

        for i in range(len(stops) - 1):
            if stops[i][0] <= value <= stops[i + 1][0]:
                lower_stop = stops[i]
                upper_stop = stops[i + 1]
                break

        # Interpolate
        if upper_stop[0] == lower_stop[0]:
            t = 0
        else:
            t = (value - lower_stop[0]) / (upper_stop[0] - lower_stop[0])

        r = int(lower_stop[1][0] + t * (upper_stop[1][0] - lower_stop[1][0]))
        g = int(lower_stop[1][1] + t * (upper_stop[1][1] - lower_stop[1][1]))
        b = int(lower_stop[1][2] + t * (upper_stop[1][2] - lower_stop[1][2]))

        return f"#{r:02x}{g:02x}{b:02x}"

    def render_link_heatmap(
        self,
        links: List[Dict[str, Any]],
        color_scale: ColorScale = ColorScale.TRAFFIC,
        title: str = "Link Utilization Heatmap"
    ) -> HeatmapData:
        """
        Render a heatmap of link utilization

        Args:
            links: List of link data with utilization values
            color_scale: Color scale to use
            title: Heatmap title

        Returns:
            HeatmapData for visualization
        """
        if not links:
            return HeatmapData(
                heatmap_id=self._generate_heatmap_id(),
                heatmap_type=HeatmapType.LINK_UTILIZATION,
                title=title,
                width=0,
                height=0,
                color_scale=color_scale
            )

        # Create grid layout based on number of links
        num_links = len(links)
        cols = int(math.ceil(math.sqrt(num_links)))
        rows = int(math.ceil(num_links / cols))

        cells = []
        max_util = max(l.get("utilization", 0) for l in links)
        min_util = min(l.get("utilization", 0) for l in links)

        for i, link in enumerate(links):
            x = i % cols
            y = i // cols
            util = link.get("utilization", 0)

            # Normalize to 0-1 (using 100 as max for utilization)
            normalized = util / 100.0

            cell = HeatmapCell(
                x=x,
                y=y,
                value=normalized,
                raw_value=util,
                label=f"{link.get('source', '')} -> {link.get('dest', '')}",
                color=self._interpolate_color(normalized, color_scale),
                metadata={
                    "link_id": link.get("link_id", ""),
                    "interface": link.get("interface", ""),
                    "throughput_gbps": link.get("throughput_gbps", 0)
                }
            )
            cells.append(cell)

        return HeatmapData(
            heatmap_id=self._generate_heatmap_id(),
            heatmap_type=HeatmapType.LINK_UTILIZATION,
            title=title,
            width=cols,
            height=rows,
            cells=cells,
            color_scale=color_scale,
            min_value=min_util,
            max_value=max_util,
            metadata={
                "total_links": num_links,
                "high_utilization_count": len([l for l in links if l.get("utilization", 0) > 80])
            }
        )

    def render_node_heatmap(
        self,
        nodes: List[Dict[str, Any]],
        color_scale: ColorScale = ColorScale.TRAFFIC,
        title: str = "Node Traffic Heatmap"
    ) -> HeatmapData:
        """
        Render a heatmap of node traffic intensity

        Args:
            nodes: List of node data with traffic values
            color_scale: Color scale to use
            title: Heatmap title

        Returns:
            HeatmapData for visualization
        """
        if not nodes:
            return HeatmapData(
                heatmap_id=self._generate_heatmap_id(),
                heatmap_type=HeatmapType.NODE_TRAFFIC,
                title=title,
                width=0,
                height=0,
                color_scale=color_scale
            )

        num_nodes = len(nodes)
        cols = int(math.ceil(math.sqrt(num_nodes)))
        rows = int(math.ceil(num_nodes / cols))

        # Find max traffic for normalization
        max_traffic = max(n.get("total_traffic_gbps", 0) for n in nodes)
        if max_traffic == 0:
            max_traffic = 1  # Avoid division by zero

        cells = []
        for i, node in enumerate(nodes):
            x = i % cols
            y = i // cols
            traffic = node.get("total_traffic_gbps", 0)
            normalized = traffic / max_traffic

            cell = HeatmapCell(
                x=x,
                y=y,
                value=normalized,
                raw_value=traffic,
                label=node.get("hostname", node.get("node_id", "")),
                color=self._interpolate_color(normalized, color_scale),
                metadata={
                    "node_id": node.get("node_id", ""),
                    "avg_utilization": node.get("avg_utilization", 0),
                    "interface_count": node.get("interface_count", 0)
                }
            )
            cells.append(cell)

        return HeatmapData(
            heatmap_id=self._generate_heatmap_id(),
            heatmap_type=HeatmapType.NODE_TRAFFIC,
            title=title,
            width=cols,
            height=rows,
            cells=cells,
            color_scale=color_scale,
            min_value=0,
            max_value=max_traffic,
            metadata={
                "total_nodes": num_nodes
            }
        )

    def render_matrix_heatmap(
        self,
        source_nodes: List[str],
        dest_nodes: List[str],
        traffic_matrix: Dict[Tuple[str, str], float],
        color_scale: ColorScale = ColorScale.TRAFFIC,
        title: str = "Traffic Matrix Heatmap"
    ) -> HeatmapData:
        """
        Render a source-destination traffic matrix heatmap

        Args:
            source_nodes: List of source node IDs
            dest_nodes: List of destination node IDs
            traffic_matrix: Dict mapping (source, dest) -> traffic value
            color_scale: Color scale to use
            title: Heatmap title

        Returns:
            HeatmapData for visualization
        """
        if not source_nodes or not dest_nodes:
            return HeatmapData(
                heatmap_id=self._generate_heatmap_id(),
                heatmap_type=HeatmapType.NODE_TRAFFIC,
                title=title,
                width=0,
                height=0,
                color_scale=color_scale
            )

        width = len(dest_nodes)
        height = len(source_nodes)

        # Find max value for normalization
        max_value = max(traffic_matrix.values()) if traffic_matrix else 1

        cells = []
        for y, source in enumerate(source_nodes):
            for x, dest in enumerate(dest_nodes):
                value = traffic_matrix.get((source, dest), 0)
                normalized = value / max_value if max_value > 0 else 0

                cell = HeatmapCell(
                    x=x,
                    y=y,
                    value=normalized,
                    raw_value=value,
                    label=f"{source} -> {dest}",
                    color=self._interpolate_color(normalized, color_scale),
                    metadata={
                        "source": source,
                        "dest": dest
                    }
                )
                cells.append(cell)

        return HeatmapData(
            heatmap_id=self._generate_heatmap_id(),
            heatmap_type=HeatmapType.NODE_TRAFFIC,
            title=title,
            width=width,
            height=height,
            cells=cells,
            color_scale=color_scale,
            min_value=0,
            max_value=max_value,
            metadata={
                "source_count": len(source_nodes),
                "dest_count": len(dest_nodes),
                "source_labels": source_nodes,
                "dest_labels": dest_nodes
            }
        )

    def render_time_series_heatmap(
        self,
        link_id: str,
        samples: List[Dict[str, Any]],
        time_buckets: int = 24,
        color_scale: ColorScale = ColorScale.TRAFFIC,
        title: str = "Traffic Time Series"
    ) -> HeatmapData:
        """
        Render a time-series heatmap for a single link

        Args:
            link_id: Link identifier
            samples: Time series samples
            time_buckets: Number of time buckets
            color_scale: Color scale to use
            title: Heatmap title

        Returns:
            HeatmapData for visualization
        """
        if not samples:
            return HeatmapData(
                heatmap_id=self._generate_heatmap_id(),
                heatmap_type=HeatmapType.LINK_UTILIZATION,
                title=title,
                width=time_buckets,
                height=1,
                color_scale=color_scale
            )

        # Aggregate samples into time buckets
        bucket_values: List[List[float]] = [[] for _ in range(time_buckets)]

        for sample in samples:
            # Map timestamp to bucket
            ts = sample.get("timestamp", "")
            util = sample.get("utilization_percent", 0)

            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue

            # Calculate bucket index based on hour
            bucket_idx = ts.hour % time_buckets
            bucket_values[bucket_idx].append(util)

        # Create cells
        cells = []
        for x, values in enumerate(bucket_values):
            avg_util = sum(values) / len(values) if values else 0
            normalized = avg_util / 100.0

            cell = HeatmapCell(
                x=x,
                y=0,
                value=normalized,
                raw_value=avg_util,
                label=f"{x:02d}:00",
                color=self._interpolate_color(normalized, color_scale),
                metadata={
                    "hour": x,
                    "sample_count": len(values),
                    "min_util": min(values) if values else 0,
                    "max_util": max(values) if values else 0
                }
            )
            cells.append(cell)

        return HeatmapData(
            heatmap_id=self._generate_heatmap_id(),
            heatmap_type=HeatmapType.LINK_UTILIZATION,
            title=f"{title}: {link_id}",
            width=time_buckets,
            height=1,
            cells=cells,
            color_scale=color_scale,
            min_value=0,
            max_value=100,
            metadata={
                "link_id": link_id,
                "total_samples": len(samples),
                "time_buckets": time_buckets
            }
        )

    def render_protocol_heatmap(
        self,
        protocol_data: Dict[str, Dict[str, float]],
        color_scale: ColorScale = ColorScale.VIRIDIS,
        title: str = "Protocol Activity Heatmap"
    ) -> HeatmapData:
        """
        Render a heatmap of protocol activity across nodes

        Args:
            protocol_data: Dict mapping node_id -> protocol -> activity level
            color_scale: Color scale to use
            title: Heatmap title

        Returns:
            HeatmapData for visualization
        """
        if not protocol_data:
            return HeatmapData(
                heatmap_id=self._generate_heatmap_id(),
                heatmap_type=HeatmapType.PROTOCOL_ACTIVITY,
                title=title,
                width=0,
                height=0,
                color_scale=color_scale
            )

        # Get all protocols
        protocols = set()
        for node_protocols in protocol_data.values():
            protocols.update(node_protocols.keys())
        protocols = sorted(protocols)

        nodes = sorted(protocol_data.keys())

        # Find max activity for normalization
        max_activity = 0
        for node_protocols in protocol_data.values():
            max_activity = max(max_activity, max(node_protocols.values()) if node_protocols else 0)
        if max_activity == 0:
            max_activity = 1

        cells = []
        for y, node in enumerate(nodes):
            for x, protocol in enumerate(protocols):
                activity = protocol_data.get(node, {}).get(protocol, 0)
                normalized = activity / max_activity

                cell = HeatmapCell(
                    x=x,
                    y=y,
                    value=normalized,
                    raw_value=activity,
                    label=f"{node}: {protocol}",
                    color=self._interpolate_color(normalized, color_scale),
                    metadata={
                        "node": node,
                        "protocol": protocol
                    }
                )
                cells.append(cell)

        return HeatmapData(
            heatmap_id=self._generate_heatmap_id(),
            heatmap_type=HeatmapType.PROTOCOL_ACTIVITY,
            title=title,
            width=len(protocols),
            height=len(nodes),
            cells=cells,
            color_scale=color_scale,
            min_value=0,
            max_value=max_activity,
            metadata={
                "protocols": protocols,
                "nodes": nodes
            }
        )

    def get_color_legend(
        self,
        color_scale: ColorScale,
        min_value: float = 0,
        max_value: float = 100,
        steps: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Generate a color legend for a heatmap

        Args:
            color_scale: Color scale to use
            min_value: Minimum value
            max_value: Maximum value
            steps: Number of legend steps

        Returns:
            List of legend entries
        """
        legend = []
        for i in range(steps + 1):
            normalized = i / steps
            value = min_value + normalized * (max_value - min_value)
            color = self._interpolate_color(normalized, color_scale)

            legend.append({
                "value": value,
                "normalized": normalized,
                "color": color,
                "label": f"{value:.1f}"
            })

        return legend

    def get_available_scales(self) -> List[Dict[str, str]]:
        """Get list of available color scales"""
        return [
            {"id": scale.value, "name": scale.name.replace("_", " ").title()}
            for scale in ColorScale
        ]

    def get_statistics(self) -> Dict[str, Any]:
        """Get renderer statistics"""
        return {
            "heatmaps_generated": self._heatmap_counter,
            "available_scales": len(self._color_scales),
            "heatmap_types": [t.value for t in HeatmapType]
        }


# Global renderer instance
_global_renderer: Optional[HeatmapRenderer] = None


def get_heatmap_renderer() -> HeatmapRenderer:
    """Get or create the global heatmap renderer"""
    global _global_renderer
    if _global_renderer is None:
        _global_renderer = HeatmapRenderer()
    return _global_renderer
