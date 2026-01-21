"""
Traffic Analyzer - Analyzes network traffic patterns and metrics

Provides analysis of:
- Bandwidth utilization per link
- Traffic flow patterns
- Congestion detection
- Historical traffic trends
- Peak usage identification
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
import statistics

logger = logging.getLogger("TrafficAnalyzer")


class TrafficDirection(Enum):
    """Traffic direction"""
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    BIDIRECTIONAL = "bidirectional"


class CongestionLevel(Enum):
    """Congestion severity level"""
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TrafficMetric:
    """
    Traffic metric sample

    Attributes:
        timestamp: When the metric was recorded
        link_id: Identifier for the link
        source: Source agent/interface
        destination: Destination agent/interface
        bytes_in: Inbound bytes
        bytes_out: Outbound bytes
        packets_in: Inbound packets
        packets_out: Outbound packets
        bandwidth_capacity: Link capacity in bps
        latency_ms: Measured latency in milliseconds
        jitter_ms: Measured jitter in milliseconds
        packet_loss: Packet loss percentage (0-100)
    """
    timestamp: datetime
    link_id: str
    source: str
    destination: str
    bytes_in: int = 0
    bytes_out: int = 0
    packets_in: int = 0
    packets_out: int = 0
    bandwidth_capacity: int = 1_000_000_000  # Default 1Gbps
    latency_ms: float = 0.0
    jitter_ms: float = 0.0
    packet_loss: float = 0.0

    @property
    def utilization_in(self) -> float:
        """Calculate inbound utilization percentage"""
        if self.bandwidth_capacity <= 0:
            return 0.0
        # Assume 1 second sample, convert bytes to bits
        return min(100.0, (self.bytes_in * 8 / self.bandwidth_capacity) * 100)

    @property
    def utilization_out(self) -> float:
        """Calculate outbound utilization percentage"""
        if self.bandwidth_capacity <= 0:
            return 0.0
        return min(100.0, (self.bytes_out * 8 / self.bandwidth_capacity) * 100)

    @property
    def utilization_total(self) -> float:
        """Calculate total utilization percentage"""
        return max(self.utilization_in, self.utilization_out)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "link_id": self.link_id,
            "source": self.source,
            "destination": self.destination,
            "bytes_in": self.bytes_in,
            "bytes_out": self.bytes_out,
            "packets_in": self.packets_in,
            "packets_out": self.packets_out,
            "bandwidth_capacity": self.bandwidth_capacity,
            "latency_ms": self.latency_ms,
            "jitter_ms": self.jitter_ms,
            "packet_loss": self.packet_loss,
            "utilization_in": self.utilization_in,
            "utilization_out": self.utilization_out,
            "utilization_total": self.utilization_total
        }


@dataclass
class TrafficPattern:
    """
    Detected traffic pattern

    Attributes:
        pattern_id: Unique identifier
        pattern_type: Type of pattern detected
        description: Human-readable description
        affected_links: Links exhibiting this pattern
        start_time: When pattern started
        end_time: When pattern ended (None if ongoing)
        severity: Pattern severity
        metrics: Associated metrics
    """
    pattern_id: str
    pattern_type: str
    description: str
    affected_links: List[str]
    start_time: datetime
    end_time: Optional[datetime] = None
    severity: str = "info"
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> Optional[timedelta]:
        """Calculate pattern duration"""
        if self.end_time:
            return self.end_time - self.start_time
        return datetime.now() - self.start_time

    @property
    def is_ongoing(self) -> bool:
        """Check if pattern is still active"""
        return self.end_time is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type,
            "description": self.description,
            "affected_links": self.affected_links,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration.total_seconds() if self.duration else None,
            "is_ongoing": self.is_ongoing,
            "severity": self.severity,
            "metrics": self.metrics
        }


@dataclass
class AnalysisResult:
    """
    Traffic analysis result

    Attributes:
        analysis_id: Unique identifier
        timestamp: When analysis was performed
        period_start: Start of analysis period
        period_end: End of analysis period
        link_summaries: Per-link summary statistics
        patterns: Detected traffic patterns
        congestion_points: Identified congestion areas
        recommendations: Suggested optimizations
    """
    analysis_id: str
    timestamp: datetime
    period_start: datetime
    period_end: datetime
    link_summaries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    patterns: List[TrafficPattern] = field(default_factory=list)
    congestion_points: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "timestamp": self.timestamp.isoformat(),
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "link_summaries": self.link_summaries,
            "patterns": [p.to_dict() for p in self.patterns],
            "congestion_points": self.congestion_points,
            "recommendations": self.recommendations
        }


class TrafficAnalyzer:
    """
    Analyzes network traffic patterns and identifies optimization opportunities
    """

    def __init__(self, history_window: int = 3600):
        """
        Initialize traffic analyzer

        Args:
            history_window: Number of seconds of history to retain
        """
        self._metrics: Dict[str, List[TrafficMetric]] = defaultdict(list)
        self._patterns: List[TrafficPattern] = []
        self._history_window = history_window
        self._analysis_counter = 0
        self._pattern_counter = 0

        # Thresholds for pattern detection
        self._congestion_threshold = 80.0  # % utilization
        self._high_latency_threshold = 50.0  # ms
        self._packet_loss_threshold = 1.0  # %
        self._asymmetry_threshold = 30.0  # % difference between in/out

    def _generate_analysis_id(self) -> str:
        """Generate unique analysis ID"""
        self._analysis_counter += 1
        return f"analysis-{self._analysis_counter:06d}"

    def _generate_pattern_id(self) -> str:
        """Generate unique pattern ID"""
        self._pattern_counter += 1
        return f"pattern-{self._pattern_counter:06d}"

    def record_metric(self, metric: TrafficMetric) -> None:
        """
        Record a traffic metric sample

        Args:
            metric: Traffic metric to record
        """
        self._metrics[metric.link_id].append(metric)
        self._prune_old_metrics()
        self._detect_patterns(metric.link_id)

    def record_metrics(self, metrics: List[TrafficMetric]) -> None:
        """Record multiple metrics at once"""
        for metric in metrics:
            self._metrics[metric.link_id].append(metric)
        self._prune_old_metrics()
        for link_id in set(m.link_id for m in metrics):
            self._detect_patterns(link_id)

    def _prune_old_metrics(self) -> None:
        """Remove metrics older than history window"""
        cutoff = datetime.now() - timedelta(seconds=self._history_window)
        for link_id in list(self._metrics.keys()):
            self._metrics[link_id] = [
                m for m in self._metrics[link_id]
                if m.timestamp > cutoff
            ]
            if not self._metrics[link_id]:
                del self._metrics[link_id]

    def _detect_patterns(self, link_id: str) -> None:
        """Detect traffic patterns for a link"""
        metrics = self._metrics.get(link_id, [])
        if len(metrics) < 3:
            return

        recent = metrics[-10:]  # Last 10 samples

        # Check for congestion
        avg_util = statistics.mean(m.utilization_total for m in recent)
        if avg_util >= self._congestion_threshold:
            self._record_pattern(
                pattern_type="congestion",
                description=f"High utilization on {link_id}: {avg_util:.1f}%",
                affected_links=[link_id],
                severity="warning" if avg_util < 90 else "critical",
                metrics={"avg_utilization": avg_util}
            )

        # Check for high latency
        avg_latency = statistics.mean(m.latency_ms for m in recent)
        if avg_latency >= self._high_latency_threshold:
            self._record_pattern(
                pattern_type="high_latency",
                description=f"High latency on {link_id}: {avg_latency:.1f}ms",
                affected_links=[link_id],
                severity="warning",
                metrics={"avg_latency_ms": avg_latency}
            )

        # Check for packet loss
        avg_loss = statistics.mean(m.packet_loss for m in recent)
        if avg_loss >= self._packet_loss_threshold:
            self._record_pattern(
                pattern_type="packet_loss",
                description=f"Packet loss on {link_id}: {avg_loss:.2f}%",
                affected_links=[link_id],
                severity="warning" if avg_loss < 5 else "critical",
                metrics={"avg_packet_loss": avg_loss}
            )

        # Check for asymmetric traffic
        avg_in = statistics.mean(m.utilization_in for m in recent)
        avg_out = statistics.mean(m.utilization_out for m in recent)
        asymmetry = abs(avg_in - avg_out)
        if asymmetry >= self._asymmetry_threshold and max(avg_in, avg_out) > 20:
            direction = "inbound" if avg_in > avg_out else "outbound"
            self._record_pattern(
                pattern_type="asymmetric_traffic",
                description=f"Asymmetric traffic on {link_id}: {direction} heavy ({asymmetry:.1f}% difference)",
                affected_links=[link_id],
                severity="info",
                metrics={
                    "avg_utilization_in": avg_in,
                    "avg_utilization_out": avg_out,
                    "asymmetry": asymmetry
                }
            )

    def _record_pattern(
        self,
        pattern_type: str,
        description: str,
        affected_links: List[str],
        severity: str = "info",
        metrics: Optional[Dict[str, Any]] = None
    ) -> TrafficPattern:
        """Record a detected pattern"""
        # Check for existing similar pattern
        for pattern in self._patterns:
            if (pattern.pattern_type == pattern_type and
                pattern.is_ongoing and
                set(pattern.affected_links) == set(affected_links)):
                # Update existing pattern
                pattern.metrics = metrics or {}
                return pattern

        # Create new pattern
        pattern = TrafficPattern(
            pattern_id=self._generate_pattern_id(),
            pattern_type=pattern_type,
            description=description,
            affected_links=affected_links,
            start_time=datetime.now(),
            severity=severity,
            metrics=metrics or {}
        )
        self._patterns.append(pattern)
        logger.info(f"Detected pattern: {pattern_type} on {affected_links}")
        return pattern

    def analyze(
        self,
        period_minutes: int = 60
    ) -> AnalysisResult:
        """
        Perform comprehensive traffic analysis

        Args:
            period_minutes: Analysis period in minutes

        Returns:
            AnalysisResult with summaries and recommendations
        """
        now = datetime.now()
        period_start = now - timedelta(minutes=period_minutes)

        result = AnalysisResult(
            analysis_id=self._generate_analysis_id(),
            timestamp=now,
            period_start=period_start,
            period_end=now
        )

        # Analyze each link
        for link_id, metrics in self._metrics.items():
            # Filter to analysis period
            period_metrics = [
                m for m in metrics
                if m.timestamp >= period_start
            ]
            if not period_metrics:
                continue

            summary = self._compute_link_summary(link_id, period_metrics)
            result.link_summaries[link_id] = summary

            # Check for congestion
            if summary["avg_utilization"] >= self._congestion_threshold:
                result.congestion_points.append({
                    "link_id": link_id,
                    "avg_utilization": summary["avg_utilization"],
                    "peak_utilization": summary["peak_utilization"],
                    "congestion_level": self._get_congestion_level(summary["avg_utilization"]).value
                })

        # Include recent patterns
        result.patterns = [
            p for p in self._patterns
            if p.start_time >= period_start or p.is_ongoing
        ]

        # Generate recommendations
        result.recommendations = self._generate_recommendations(result)

        return result

    def _compute_link_summary(
        self,
        link_id: str,
        metrics: List[TrafficMetric]
    ) -> Dict[str, Any]:
        """Compute summary statistics for a link"""
        if not metrics:
            return {}

        utils = [m.utilization_total for m in metrics]
        latencies = [m.latency_ms for m in metrics]
        losses = [m.packet_loss for m in metrics]

        return {
            "link_id": link_id,
            "source": metrics[0].source,
            "destination": metrics[0].destination,
            "sample_count": len(metrics),
            "bandwidth_capacity": metrics[0].bandwidth_capacity,
            "avg_utilization": statistics.mean(utils),
            "peak_utilization": max(utils),
            "min_utilization": min(utils),
            "std_dev_utilization": statistics.stdev(utils) if len(utils) > 1 else 0,
            "avg_latency_ms": statistics.mean(latencies),
            "peak_latency_ms": max(latencies),
            "avg_packet_loss": statistics.mean(losses),
            "total_bytes_in": sum(m.bytes_in for m in metrics),
            "total_bytes_out": sum(m.bytes_out for m in metrics),
            "total_packets_in": sum(m.packets_in for m in metrics),
            "total_packets_out": sum(m.packets_out for m in metrics)
        }

    def _get_congestion_level(self, utilization: float) -> CongestionLevel:
        """Determine congestion level from utilization"""
        if utilization < 50:
            return CongestionLevel.NONE
        elif utilization < 70:
            return CongestionLevel.LOW
        elif utilization < 85:
            return CongestionLevel.MODERATE
        elif utilization < 95:
            return CongestionLevel.HIGH
        else:
            return CongestionLevel.CRITICAL

    def _generate_recommendations(self, result: AnalysisResult) -> List[str]:
        """Generate optimization recommendations based on analysis"""
        recommendations = []

        # Congestion recommendations
        if result.congestion_points:
            for point in result.congestion_points:
                link_id = point["link_id"]
                util = point["avg_utilization"]
                level = point["congestion_level"]

                if level == "critical":
                    recommendations.append(
                        f"CRITICAL: Link {link_id} at {util:.1f}% utilization. "
                        f"Consider: 1) Increase link capacity, 2) Implement load balancing, "
                        f"3) Adjust OSPF costs to prefer alternate paths"
                    )
                elif level == "high":
                    recommendations.append(
                        f"HIGH: Link {link_id} at {util:.1f}% utilization. "
                        f"Consider adjusting OSPF costs or BGP policies to distribute traffic"
                    )
                else:
                    recommendations.append(
                        f"Monitor link {link_id} ({util:.1f}% utilization) for potential congestion"
                    )

        # Pattern-based recommendations
        for pattern in result.patterns:
            if pattern.pattern_type == "asymmetric_traffic":
                recommendations.append(
                    f"Asymmetric traffic detected on {', '.join(pattern.affected_links)}. "
                    f"Review traffic engineering policies"
                )
            elif pattern.pattern_type == "high_latency":
                recommendations.append(
                    f"High latency on {', '.join(pattern.affected_links)}. "
                    f"Consider: 1) Check for congestion, 2) Review QoS settings, "
                    f"3) Verify path optimality"
                )
            elif pattern.pattern_type == "packet_loss":
                recommendations.append(
                    f"Packet loss detected on {', '.join(pattern.affected_links)}. "
                    f"Investigate: 1) Hardware issues, 2) Buffer overflows, 3) QoS policies"
                )

        # Load balancing recommendations
        if len(result.link_summaries) > 1:
            utils = [s["avg_utilization"] for s in result.link_summaries.values()]
            if max(utils) - min(utils) > 40:
                recommendations.append(
                    "Uneven traffic distribution detected across links. "
                    "Consider implementing ECMP or adjusting route costs"
                )

        return recommendations

    def get_link_metrics(
        self,
        link_id: str,
        last_n: int = 100
    ) -> List[TrafficMetric]:
        """Get recent metrics for a specific link"""
        metrics = self._metrics.get(link_id, [])
        return metrics[-last_n:]

    def get_all_link_ids(self) -> List[str]:
        """Get all tracked link IDs"""
        return list(self._metrics.keys())

    def get_active_patterns(self) -> List[TrafficPattern]:
        """Get all currently active patterns"""
        return [p for p in self._patterns if p.is_ongoing]

    def get_pattern_history(self, limit: int = 50) -> List[TrafficPattern]:
        """Get pattern history"""
        return self._patterns[-limit:]

    def close_pattern(self, pattern_id: str) -> bool:
        """Close an active pattern"""
        for pattern in self._patterns:
            if pattern.pattern_id == pattern_id and pattern.is_ongoing:
                pattern.end_time = datetime.now()
                return True
        return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get analyzer statistics"""
        total_metrics = sum(len(m) for m in self._metrics.values())
        return {
            "tracked_links": len(self._metrics),
            "total_metrics": total_metrics,
            "active_patterns": len(self.get_active_patterns()),
            "total_patterns": len(self._patterns),
            "history_window_seconds": self._history_window
        }


# Global analyzer instance
_global_analyzer: Optional[TrafficAnalyzer] = None


def get_traffic_analyzer() -> TrafficAnalyzer:
    """Get or create the global traffic analyzer"""
    global _global_analyzer
    if _global_analyzer is None:
        _global_analyzer = TrafficAnalyzer()
    return _global_analyzer
