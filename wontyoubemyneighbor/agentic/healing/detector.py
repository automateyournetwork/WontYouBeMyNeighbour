"""
Anomaly Detector - Detects patterns and anomalies in network behavior

Detects:
- Flapping adjacencies/peers
- Route instability
- Resource exhaustion trends
- Configuration drift
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
from collections import deque

logger = logging.getLogger("AnomalyDetector")


class AnomalyType(Enum):
    """Types of anomalies"""
    ADJACENCY_FLAP = "adjacency_flap"
    PEER_FLAP = "peer_flap"
    ROUTE_INSTABILITY = "route_instability"
    RESOURCE_TREND = "resource_trend"
    CONFIG_DRIFT = "config_drift"
    CONVERGENCE_SLOW = "convergence_slow"


@dataclass
class Anomaly:
    """
    Detected anomaly

    Attributes:
        timestamp: Detection time
        anomaly_type: Type of anomaly
        agent_id: Affected agent
        severity: Anomaly severity (1-10)
        description: Human-readable description
        affected_resources: List of affected resources
        metrics: Anomaly metrics
        recommended_action: Suggested remediation
    """
    timestamp: datetime
    anomaly_type: AnomalyType
    agent_id: str
    severity: int
    description: str
    affected_resources: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    recommended_action: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "anomaly_type": self.anomaly_type.value,
            "agent_id": self.agent_id,
            "severity": self.severity,
            "description": self.description,
            "affected_resources": self.affected_resources,
            "metrics": self.metrics,
            "recommended_action": self.recommended_action,
        }


class AnomalyDetector:
    """
    Anomaly detection engine

    Analyzes patterns in health events and metrics to detect anomalies.
    """

    def __init__(
        self,
        flap_threshold: int = 3,
        flap_window_minutes: int = 5,
        route_change_threshold: float = 30.0,
        max_anomalies: int = 500
    ):
        """
        Initialize anomaly detector

        Args:
            flap_threshold: Number of state changes to consider flapping
            flap_window_minutes: Time window for flap detection
            route_change_threshold: Percentage route change to flag
            max_anomalies: Maximum anomalies to retain
        """
        self.flap_threshold = flap_threshold
        self.flap_window = timedelta(minutes=flap_window_minutes)
        self.route_change_threshold = route_change_threshold
        self._anomalies: deque = deque(maxlen=max_anomalies)

        # State tracking for pattern detection
        self._adjacency_events: Dict[str, List[datetime]] = {}  # key -> [timestamps]
        self._peer_events: Dict[str, List[datetime]] = {}
        self._route_changes: Dict[str, List[tuple]] = {}  # agent_id -> [(timestamp, count)]

    def _generate_key(self, agent_id: str, peer_id: str) -> str:
        """Generate tracking key for agent-peer pair"""
        return f"{agent_id}:{peer_id}"

    def record_adjacency_event(self, agent_id: str, neighbor_id: str, event_type: str) -> Optional[Anomaly]:
        """
        Record OSPF adjacency event and check for flapping

        Args:
            agent_id: Agent ID
            neighbor_id: OSPF neighbor ID
            event_type: Event type (up/down)

        Returns:
            Anomaly if flapping detected, None otherwise
        """
        key = self._generate_key(agent_id, neighbor_id)
        now = datetime.now()

        if key not in self._adjacency_events:
            self._adjacency_events[key] = []

        # Add current event
        self._adjacency_events[key].append(now)

        # Clean old events outside window
        cutoff = now - self.flap_window
        self._adjacency_events[key] = [
            t for t in self._adjacency_events[key] if t > cutoff
        ]

        # Check for flapping
        if len(self._adjacency_events[key]) >= self.flap_threshold:
            anomaly = Anomaly(
                timestamp=now,
                anomaly_type=AnomalyType.ADJACENCY_FLAP,
                agent_id=agent_id,
                severity=7,
                description=f"OSPF adjacency flapping detected with neighbor {neighbor_id}",
                affected_resources=[neighbor_id],
                metrics={
                    "event_count": len(self._adjacency_events[key]),
                    "window_minutes": self.flap_window.total_seconds() / 60,
                },
                recommended_action="Check physical connectivity, interface stability, or authentication"
            )
            self._anomalies.append(anomaly)
            return anomaly

        return None

    def record_peer_event(self, agent_id: str, peer_ip: str, event_type: str) -> Optional[Anomaly]:
        """
        Record BGP peer event and check for flapping

        Args:
            agent_id: Agent ID
            peer_ip: BGP peer IP
            event_type: Event type (established/down)

        Returns:
            Anomaly if flapping detected, None otherwise
        """
        key = self._generate_key(agent_id, peer_ip)
        now = datetime.now()

        if key not in self._peer_events:
            self._peer_events[key] = []

        self._peer_events[key].append(now)

        # Clean old events
        cutoff = now - self.flap_window
        self._peer_events[key] = [
            t for t in self._peer_events[key] if t > cutoff
        ]

        # Check for flapping
        if len(self._peer_events[key]) >= self.flap_threshold:
            anomaly = Anomaly(
                timestamp=now,
                anomaly_type=AnomalyType.PEER_FLAP,
                agent_id=agent_id,
                severity=8,
                description=f"BGP peer flapping detected with {peer_ip}",
                affected_resources=[peer_ip],
                metrics={
                    "event_count": len(self._peer_events[key]),
                    "window_minutes": self.flap_window.total_seconds() / 60,
                },
                recommended_action="Consider route flap dampening, check peer stability"
            )
            self._anomalies.append(anomaly)
            return anomaly

        return None

    def record_route_count(self, agent_id: str, route_count: int) -> Optional[Anomaly]:
        """
        Record route count and detect instability

        Args:
            agent_id: Agent ID
            route_count: Current route count

        Returns:
            Anomaly if instability detected, None otherwise
        """
        now = datetime.now()

        if agent_id not in self._route_changes:
            self._route_changes[agent_id] = []

        self._route_changes[agent_id].append((now, route_count))

        # Keep only recent changes
        cutoff = now - timedelta(minutes=10)
        self._route_changes[agent_id] = [
            (t, c) for t, c in self._route_changes[agent_id] if t > cutoff
        ]

        # Analyze for instability
        if len(self._route_changes[agent_id]) >= 3:
            counts = [c for _, c in self._route_changes[agent_id]]
            if max(counts) > 0:
                variance = (max(counts) - min(counts)) / max(counts) * 100
                if variance > self.route_change_threshold:
                    anomaly = Anomaly(
                        timestamp=now,
                        anomaly_type=AnomalyType.ROUTE_INSTABILITY,
                        agent_id=agent_id,
                        severity=6,
                        description=f"Route table instability detected: {variance:.1f}% variance",
                        metrics={
                            "min_routes": min(counts),
                            "max_routes": max(counts),
                            "variance_pct": round(variance, 2),
                        },
                        recommended_action="Check for routing loops, filter updates, or convergence issues"
                    )
                    self._anomalies.append(anomaly)
                    return anomaly

        return None

    def analyze_convergence(
        self,
        agent_id: str,
        convergence_time_ms: float,
        baseline_ms: float = 1000.0
    ) -> Optional[Anomaly]:
        """
        Analyze convergence time for anomalies

        Args:
            agent_id: Agent ID
            convergence_time_ms: Measured convergence time
            baseline_ms: Expected baseline convergence time

        Returns:
            Anomaly if slow convergence detected, None otherwise
        """
        if convergence_time_ms > baseline_ms * 3:
            anomaly = Anomaly(
                timestamp=datetime.now(),
                anomaly_type=AnomalyType.CONVERGENCE_SLOW,
                agent_id=agent_id,
                severity=5,
                description=f"Slow convergence detected: {convergence_time_ms:.0f}ms (baseline: {baseline_ms:.0f}ms)",
                metrics={
                    "convergence_ms": convergence_time_ms,
                    "baseline_ms": baseline_ms,
                    "slowdown_factor": round(convergence_time_ms / baseline_ms, 2),
                },
                recommended_action="Check SPF timers, LSDB size, or CPU load"
            )
            self._anomalies.append(anomaly)
            return anomaly

        return None

    def get_anomalies(
        self,
        limit: int = 50,
        anomaly_type: Optional[AnomalyType] = None,
        min_severity: int = 0
    ) -> List[Anomaly]:
        """
        Get detected anomalies

        Args:
            limit: Maximum anomalies to return
            anomaly_type: Filter by type (optional)
            min_severity: Minimum severity to include

        Returns:
            List of anomalies
        """
        anomalies = list(self._anomalies)[-limit:]

        if anomaly_type:
            anomalies = [a for a in anomalies if a.anomaly_type == anomaly_type]

        if min_severity > 0:
            anomalies = [a for a in anomalies if a.severity >= min_severity]

        return anomalies

    def get_statistics(self) -> Dict[str, Any]:
        """Get anomaly detection statistics"""
        type_counts = {}
        for anomaly in self._anomalies:
            type_name = anomaly.anomaly_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

        return {
            "total_anomalies": len(self._anomalies),
            "anomalies_by_type": type_counts,
            "tracked_adjacencies": len(self._adjacency_events),
            "tracked_peers": len(self._peer_events),
            "tracked_route_agents": len(self._route_changes),
        }
