"""
Traffic Collector - Collects and aggregates network traffic data

Collects:
- Per-link bandwidth utilization
- Per-node traffic volume
- Time-series traffic samples
- Traffic flow direction analysis
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
import random

logger = logging.getLogger("TrafficCollector")


class TrafficDirection(Enum):
    """Traffic direction on a link"""
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    BIDIRECTIONAL = "bidirectional"


@dataclass
class TrafficSample:
    """
    A single traffic measurement sample

    Attributes:
        timestamp: When the sample was taken
        bytes_in: Inbound bytes
        bytes_out: Outbound bytes
        packets_in: Inbound packets
        packets_out: Outbound packets
        utilization_percent: Link utilization percentage
    """
    timestamp: datetime
    bytes_in: int
    bytes_out: int
    packets_in: int
    packets_out: int
    utilization_percent: float

    @property
    def total_bytes(self) -> int:
        return self.bytes_in + self.bytes_out

    @property
    def total_packets(self) -> int:
        return self.packets_in + self.packets_out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "bytes_in": self.bytes_in,
            "bytes_out": self.bytes_out,
            "packets_in": self.packets_in,
            "packets_out": self.packets_out,
            "total_bytes": self.total_bytes,
            "total_packets": self.total_packets,
            "utilization_percent": self.utilization_percent
        }


@dataclass
class LinkTraffic:
    """
    Traffic data for a network link

    Attributes:
        link_id: Unique link identifier
        source_node: Source node ID
        dest_node: Destination node ID
        interface: Interface name
        capacity_bps: Link capacity in bits per second
        samples: Historical traffic samples
    """
    link_id: str
    source_node: str
    dest_node: str
    interface: str
    capacity_bps: int
    samples: List[TrafficSample] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def current_utilization(self) -> float:
        """Get current utilization percentage"""
        if not self.samples:
            return 0.0
        return self.samples[-1].utilization_percent

    @property
    def avg_utilization(self) -> float:
        """Get average utilization over all samples"""
        if not self.samples:
            return 0.0
        return sum(s.utilization_percent for s in self.samples) / len(self.samples)

    @property
    def peak_utilization(self) -> float:
        """Get peak utilization"""
        if not self.samples:
            return 0.0
        return max(s.utilization_percent for s in self.samples)

    @property
    def current_throughput_bps(self) -> int:
        """Get current throughput in bits per second"""
        if not self.samples or len(self.samples) < 2:
            return 0
        # Calculate from last two samples
        s1, s2 = self.samples[-2], self.samples[-1]
        time_diff = (s2.timestamp - s1.timestamp).total_seconds()
        if time_diff <= 0:
            return 0
        byte_diff = s2.total_bytes - s1.total_bytes
        return int((byte_diff * 8) / time_diff)

    def add_sample(self, sample: TrafficSample, max_samples: int = 1000):
        """Add a traffic sample"""
        self.samples.append(sample)
        if len(self.samples) > max_samples:
            self.samples = self.samples[-max_samples:]

    def get_samples_since(self, since: datetime) -> List[TrafficSample]:
        """Get samples since a specific time"""
        return [s for s in self.samples if s.timestamp > since]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "link_id": self.link_id,
            "source_node": self.source_node,
            "dest_node": self.dest_node,
            "interface": self.interface,
            "capacity_bps": self.capacity_bps,
            "capacity_gbps": self.capacity_bps / 1_000_000_000,
            "current_utilization": self.current_utilization,
            "avg_utilization": self.avg_utilization,
            "peak_utilization": self.peak_utilization,
            "current_throughput_bps": self.current_throughput_bps,
            "sample_count": len(self.samples),
            "metadata": self.metadata
        }


@dataclass
class NodeTraffic:
    """
    Traffic data for a network node

    Attributes:
        node_id: Node identifier
        hostname: Node hostname
        total_interfaces: Number of interfaces
        active_interfaces: Number of active interfaces
        link_traffic: Traffic data for each link
    """
    node_id: str
    hostname: str
    total_interfaces: int = 0
    active_interfaces: int = 0
    link_traffic: Dict[str, LinkTraffic] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_inbound_bps(self) -> int:
        """Total inbound traffic in bits per second"""
        total = 0
        for link in self.link_traffic.values():
            if link.samples:
                total += link.samples[-1].bytes_in * 8
        return total

    @property
    def total_outbound_bps(self) -> int:
        """Total outbound traffic in bits per second"""
        total = 0
        for link in self.link_traffic.values():
            if link.samples:
                total += link.samples[-1].bytes_out * 8
        return total

    @property
    def avg_utilization(self) -> float:
        """Average utilization across all links"""
        if not self.link_traffic:
            return 0.0
        return sum(l.current_utilization for l in self.link_traffic.values()) / len(self.link_traffic)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "total_interfaces": self.total_interfaces,
            "active_interfaces": self.active_interfaces,
            "total_inbound_bps": self.total_inbound_bps,
            "total_outbound_bps": self.total_outbound_bps,
            "total_inbound_gbps": self.total_inbound_bps / 1_000_000_000,
            "total_outbound_gbps": self.total_outbound_bps / 1_000_000_000,
            "avg_utilization": self.avg_utilization,
            "link_count": len(self.link_traffic),
            "metadata": self.metadata
        }


class TrafficCollector:
    """
    Collects and manages network traffic data for heatmap visualization
    """

    def __init__(self, sample_interval_seconds: int = 5, retention_hours: int = 24):
        """
        Initialize traffic collector

        Args:
            sample_interval_seconds: How often to sample traffic
            retention_hours: How long to retain samples
        """
        self._nodes: Dict[str, NodeTraffic] = {}
        self._links: Dict[str, LinkTraffic] = {}
        self._sample_interval = sample_interval_seconds
        self._retention_hours = retention_hours
        self._collection_active = False
        self._last_collection = datetime.now()

        # Hotspot detection thresholds
        self._high_utilization_threshold = 80.0
        self._critical_utilization_threshold = 95.0

        # Detected hotspots
        self._hotspots: List[Dict[str, Any]] = []

    def register_node(
        self,
        node_id: str,
        hostname: str,
        total_interfaces: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> NodeTraffic:
        """
        Register a node for traffic collection

        Args:
            node_id: Unique node identifier
            hostname: Node hostname
            total_interfaces: Total number of interfaces
            metadata: Additional metadata

        Returns:
            Created NodeTraffic instance
        """
        node = NodeTraffic(
            node_id=node_id,
            hostname=hostname,
            total_interfaces=total_interfaces,
            metadata=metadata or {}
        )
        self._nodes[node_id] = node
        logger.info(f"Registered node for traffic collection: {hostname}")
        return node

    def register_link(
        self,
        link_id: str,
        source_node: str,
        dest_node: str,
        interface: str,
        capacity_bps: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> LinkTraffic:
        """
        Register a link for traffic collection

        Args:
            link_id: Unique link identifier
            source_node: Source node ID
            dest_node: Destination node ID
            interface: Interface name
            capacity_bps: Link capacity in bits per second
            metadata: Additional metadata

        Returns:
            Created LinkTraffic instance
        """
        link = LinkTraffic(
            link_id=link_id,
            source_node=source_node,
            dest_node=dest_node,
            interface=interface,
            capacity_bps=capacity_bps,
            metadata=metadata or {}
        )
        self._links[link_id] = link

        # Associate with nodes
        if source_node in self._nodes:
            self._nodes[source_node].link_traffic[link_id] = link
            self._nodes[source_node].active_interfaces += 1

        logger.info(f"Registered link for traffic collection: {source_node} -> {dest_node}")
        return link

    def record_sample(
        self,
        link_id: str,
        bytes_in: int,
        bytes_out: int,
        packets_in: int,
        packets_out: int,
        timestamp: Optional[datetime] = None
    ) -> Optional[TrafficSample]:
        """
        Record a traffic sample for a link

        Args:
            link_id: Link to record sample for
            bytes_in: Inbound bytes
            bytes_out: Outbound bytes
            packets_in: Inbound packets
            packets_out: Outbound packets
            timestamp: Sample timestamp (defaults to now)

        Returns:
            Created TrafficSample, or None if link not found
        """
        link = self._links.get(link_id)
        if not link:
            logger.warning(f"Link not found: {link_id}")
            return None

        # Calculate utilization
        total_bits = (bytes_in + bytes_out) * 8
        utilization = (total_bits / link.capacity_bps) * 100 if link.capacity_bps > 0 else 0
        utilization = min(utilization, 100.0)  # Cap at 100%

        sample = TrafficSample(
            timestamp=timestamp or datetime.now(),
            bytes_in=bytes_in,
            bytes_out=bytes_out,
            packets_in=packets_in,
            packets_out=packets_out,
            utilization_percent=utilization
        )

        link.add_sample(sample)
        self._check_hotspot(link, sample)

        return sample

    def _check_hotspot(self, link: LinkTraffic, sample: TrafficSample):
        """Check if this sample indicates a hotspot condition"""
        if sample.utilization_percent >= self._critical_utilization_threshold:
            hotspot = {
                "link_id": link.link_id,
                "source_node": link.source_node,
                "dest_node": link.dest_node,
                "utilization": sample.utilization_percent,
                "severity": "critical",
                "detected_at": sample.timestamp.isoformat()
            }
            self._hotspots.append(hotspot)
            logger.warning(f"CRITICAL hotspot detected on {link.link_id}: {sample.utilization_percent:.1f}%")
        elif sample.utilization_percent >= self._high_utilization_threshold:
            hotspot = {
                "link_id": link.link_id,
                "source_node": link.source_node,
                "dest_node": link.dest_node,
                "utilization": sample.utilization_percent,
                "severity": "high",
                "detected_at": sample.timestamp.isoformat()
            }
            self._hotspots.append(hotspot)
            logger.info(f"High utilization on {link.link_id}: {sample.utilization_percent:.1f}%")

        # Keep only recent hotspots
        cutoff = datetime.now() - timedelta(hours=1)
        self._hotspots = [
            h for h in self._hotspots
            if datetime.fromisoformat(h["detected_at"]) > cutoff
        ][-100:]  # Keep last 100

    def simulate_traffic(self):
        """
        Simulate traffic data for all registered links
        Used for demo/testing purposes
        """
        for link in self._links.values():
            # Generate random traffic with some patterns
            base_util = random.uniform(20, 60)
            variation = random.uniform(-10, 30)
            utilization = max(0, min(100, base_util + variation))

            capacity_bytes = link.capacity_bps / 8
            bytes_total = int(capacity_bytes * (utilization / 100))
            bytes_in = int(bytes_total * random.uniform(0.3, 0.7))
            bytes_out = bytes_total - bytes_in

            packets_in = bytes_in // 1500  # Assume ~1500 byte packets
            packets_out = bytes_out // 1500

            self.record_sample(
                link_id=link.link_id,
                bytes_in=bytes_in,
                bytes_out=bytes_out,
                packets_in=packets_in,
                packets_out=packets_out
            )

    def get_node(self, node_id: str) -> Optional[NodeTraffic]:
        """Get a specific node"""
        return self._nodes.get(node_id)

    def get_link(self, link_id: str) -> Optional[LinkTraffic]:
        """Get a specific link"""
        return self._links.get(link_id)

    def get_all_nodes(self) -> List[NodeTraffic]:
        """Get all registered nodes"""
        return list(self._nodes.values())

    def get_all_links(self) -> List[LinkTraffic]:
        """Get all registered links"""
        return list(self._links.values())

    def get_hotspots(self, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get detected hotspots

        Args:
            severity: Filter by severity (high, critical)

        Returns:
            List of hotspot records
        """
        if severity:
            return [h for h in self._hotspots if h["severity"] == severity]
        return self._hotspots

    def get_top_utilized_links(self, limit: int = 10) -> List[LinkTraffic]:
        """Get the most heavily utilized links"""
        sorted_links = sorted(
            self._links.values(),
            key=lambda l: l.current_utilization,
            reverse=True
        )
        return sorted_links[:limit]

    def get_traffic_summary(self) -> Dict[str, Any]:
        """
        Get overall traffic summary

        Returns:
            Traffic summary statistics
        """
        total_links = len(self._links)
        total_nodes = len(self._nodes)

        if not self._links:
            return {
                "total_nodes": total_nodes,
                "total_links": total_links,
                "avg_utilization": 0,
                "peak_utilization": 0,
                "hotspot_count": 0,
                "critical_hotspots": 0
            }

        utilizations = [l.current_utilization for l in self._links.values()]

        return {
            "total_nodes": total_nodes,
            "total_links": total_links,
            "avg_utilization": sum(utilizations) / len(utilizations),
            "peak_utilization": max(utilizations),
            "min_utilization": min(utilizations),
            "hotspot_count": len(self._hotspots),
            "critical_hotspots": len([h for h in self._hotspots if h["severity"] == "critical"]),
            "high_utilization_links": len([u for u in utilizations if u >= self._high_utilization_threshold]),
            "collection_active": self._collection_active,
            "last_collection": self._last_collection.isoformat()
        }

    def get_time_series(
        self,
        link_id: str,
        duration_minutes: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Get time series data for a link

        Args:
            link_id: Link to get data for
            duration_minutes: How far back to look

        Returns:
            List of time series data points
        """
        link = self._links.get(link_id)
        if not link:
            return []

        cutoff = datetime.now() - timedelta(minutes=duration_minutes)
        samples = link.get_samples_since(cutoff)

        return [s.to_dict() for s in samples]

    def cleanup_old_samples(self):
        """Remove samples older than retention period"""
        cutoff = datetime.now() - timedelta(hours=self._retention_hours)

        for link in self._links.values():
            link.samples = [s for s in link.samples if s.timestamp > cutoff]

        logger.debug("Cleaned up old traffic samples")

    def get_statistics(self) -> Dict[str, Any]:
        """Get collector statistics"""
        total_samples = sum(len(l.samples) for l in self._links.values())

        return {
            "total_nodes": len(self._nodes),
            "total_links": len(self._links),
            "total_samples": total_samples,
            "sample_interval_seconds": self._sample_interval,
            "retention_hours": self._retention_hours,
            "high_utilization_threshold": self._high_utilization_threshold,
            "critical_utilization_threshold": self._critical_utilization_threshold
        }


# Global collector instance
_global_collector: Optional[TrafficCollector] = None


def get_traffic_collector() -> TrafficCollector:
    """Get or create the global traffic collector"""
    global _global_collector
    if _global_collector is None:
        _global_collector = TrafficCollector()
    return _global_collector
