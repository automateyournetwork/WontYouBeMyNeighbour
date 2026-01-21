"""
Health Monitor - Continuous monitoring of network health

Monitors:
- OSPF adjacency states
- BGP peer sessions
- IS-IS adjacencies
- Route table convergence
- Protocol metrics
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from collections import deque

logger = logging.getLogger("HealthMonitor")


class EventSeverity(Enum):
    """Event severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    RECOVERY = "recovery"


@dataclass
class HealthEvent:
    """
    Health monitoring event

    Attributes:
        timestamp: Event occurrence time
        severity: Event severity level
        event_type: Type of event (adjacency_down, peer_lost, etc.)
        protocol: Affected protocol (ospf, bgp, isis)
        agent_id: Agent that detected the event
        peer_id: Affected peer/neighbor (if applicable)
        details: Additional event details
        auto_remediated: Whether auto-remediation was attempted
    """
    timestamp: datetime
    severity: EventSeverity
    event_type: str
    protocol: str
    agent_id: str
    peer_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    auto_remediated: bool = False
    remediation_result: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "event_type": self.event_type,
            "protocol": self.protocol,
            "agent_id": self.agent_id,
            "peer_id": self.peer_id,
            "details": self.details,
            "auto_remediated": self.auto_remediated,
            "remediation_result": self.remediation_result,
        }


class HealthMonitor:
    """
    Network health monitor

    Continuously monitors network state and detects issues.
    """

    def __init__(self, check_interval: float = 5.0, max_events: int = 1000):
        """
        Initialize health monitor

        Args:
            check_interval: Seconds between health checks
            max_events: Maximum events to retain in history
        """
        self.check_interval = check_interval
        self._events: deque = deque(maxlen=max_events)
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Tracked state
        self._ospf_neighbors: Dict[str, Dict[str, str]] = {}  # agent_id -> {neighbor_id: state}
        self._bgp_peers: Dict[str, Dict[str, str]] = {}  # agent_id -> {peer_ip: state}
        self._isis_adjacencies: Dict[str, Dict[str, str]] = {}  # agent_id -> {adj_id: state}
        self._route_counts: Dict[str, int] = {}  # agent_id -> route_count

        # Event callbacks
        self._event_callbacks: List[Callable[[HealthEvent], None]] = []

        # Remediation callback
        self._remediation_callback: Optional[Callable[[HealthEvent], None]] = None

    def register_event_callback(self, callback: Callable[[HealthEvent], None]) -> None:
        """Register callback for health events"""
        self._event_callbacks.append(callback)

    def set_remediation_callback(self, callback: Callable[[HealthEvent], None]) -> None:
        """Set callback for triggering remediation"""
        self._remediation_callback = callback

    def _emit_event(self, event: HealthEvent) -> None:
        """Emit health event to all callbacks"""
        self._events.append(event)
        for callback in self._event_callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Event callback error: {e}")

        # Trigger remediation for critical events
        if event.severity == EventSeverity.CRITICAL and self._remediation_callback:
            try:
                self._remediation_callback(event)
            except Exception as e:
                logger.error(f"Remediation callback error: {e}")

    def update_ospf_state(self, agent_id: str, neighbors: Dict[str, str]) -> List[HealthEvent]:
        """
        Update OSPF neighbor state and detect changes

        Args:
            agent_id: Agent ID
            neighbors: Dict of neighbor_id -> state (e.g., "Full", "2-Way", "Down")

        Returns:
            List of generated health events
        """
        events = []
        prev_neighbors = self._ospf_neighbors.get(agent_id, {})

        # Check for state changes
        for neighbor_id, new_state in neighbors.items():
            old_state = prev_neighbors.get(neighbor_id)

            if old_state != new_state:
                if new_state.lower() in ["down", "init", "attempt"]:
                    # Adjacency lost or degraded
                    event = HealthEvent(
                        timestamp=datetime.now(),
                        severity=EventSeverity.CRITICAL if old_state and old_state.lower() == "full" else EventSeverity.WARNING,
                        event_type="ospf_adjacency_down" if new_state.lower() == "down" else "ospf_adjacency_degraded",
                        protocol="ospf",
                        agent_id=agent_id,
                        peer_id=neighbor_id,
                        details={
                            "old_state": old_state,
                            "new_state": new_state,
                        }
                    )
                    events.append(event)
                    self._emit_event(event)

                elif new_state.lower() == "full" and old_state and old_state.lower() != "full":
                    # Adjacency recovered
                    event = HealthEvent(
                        timestamp=datetime.now(),
                        severity=EventSeverity.RECOVERY,
                        event_type="ospf_adjacency_recovered",
                        protocol="ospf",
                        agent_id=agent_id,
                        peer_id=neighbor_id,
                        details={
                            "old_state": old_state,
                            "new_state": new_state,
                        }
                    )
                    events.append(event)
                    self._emit_event(event)

        # Check for lost neighbors
        for neighbor_id in prev_neighbors:
            if neighbor_id not in neighbors:
                event = HealthEvent(
                    timestamp=datetime.now(),
                    severity=EventSeverity.CRITICAL,
                    event_type="ospf_neighbor_lost",
                    protocol="ospf",
                    agent_id=agent_id,
                    peer_id=neighbor_id,
                    details={"last_state": prev_neighbors[neighbor_id]}
                )
                events.append(event)
                self._emit_event(event)

        self._ospf_neighbors[agent_id] = neighbors.copy()
        return events

    def update_bgp_state(self, agent_id: str, peers: Dict[str, str]) -> List[HealthEvent]:
        """
        Update BGP peer state and detect changes

        Args:
            agent_id: Agent ID
            peers: Dict of peer_ip -> state (e.g., "Established", "Active", "Idle")

        Returns:
            List of generated health events
        """
        events = []
        prev_peers = self._bgp_peers.get(agent_id, {})

        for peer_ip, new_state in peers.items():
            old_state = prev_peers.get(peer_ip)

            if old_state != new_state:
                if new_state.lower() in ["idle", "active", "connect"]:
                    # Peer session down or flapping
                    event = HealthEvent(
                        timestamp=datetime.now(),
                        severity=EventSeverity.CRITICAL if old_state and old_state.lower() == "established" else EventSeverity.WARNING,
                        event_type="bgp_peer_down" if new_state.lower() == "idle" else "bgp_peer_transitioning",
                        protocol="bgp",
                        agent_id=agent_id,
                        peer_id=peer_ip,
                        details={
                            "old_state": old_state,
                            "new_state": new_state,
                        }
                    )
                    events.append(event)
                    self._emit_event(event)

                elif new_state.lower() == "established" and old_state and old_state.lower() != "established":
                    # Peer session recovered
                    event = HealthEvent(
                        timestamp=datetime.now(),
                        severity=EventSeverity.RECOVERY,
                        event_type="bgp_peer_recovered",
                        protocol="bgp",
                        agent_id=agent_id,
                        peer_id=peer_ip,
                        details={
                            "old_state": old_state,
                            "new_state": new_state,
                        }
                    )
                    events.append(event)
                    self._emit_event(event)

        # Check for lost peers
        for peer_ip in prev_peers:
            if peer_ip not in peers:
                event = HealthEvent(
                    timestamp=datetime.now(),
                    severity=EventSeverity.CRITICAL,
                    event_type="bgp_peer_lost",
                    protocol="bgp",
                    agent_id=agent_id,
                    peer_id=peer_ip,
                    details={"last_state": prev_peers[peer_ip]}
                )
                events.append(event)
                self._emit_event(event)

        self._bgp_peers[agent_id] = peers.copy()
        return events

    def update_isis_state(self, agent_id: str, adjacencies: Dict[str, str]) -> List[HealthEvent]:
        """
        Update IS-IS adjacency state and detect changes

        Args:
            agent_id: Agent ID
            adjacencies: Dict of adj_id -> state (e.g., "Up", "Init", "Down")

        Returns:
            List of generated health events
        """
        events = []
        prev_adjs = self._isis_adjacencies.get(agent_id, {})

        for adj_id, new_state in adjacencies.items():
            old_state = prev_adjs.get(adj_id)

            if old_state != new_state:
                if new_state.lower() in ["down", "init"]:
                    event = HealthEvent(
                        timestamp=datetime.now(),
                        severity=EventSeverity.CRITICAL if old_state and old_state.lower() == "up" else EventSeverity.WARNING,
                        event_type="isis_adjacency_down",
                        protocol="isis",
                        agent_id=agent_id,
                        peer_id=adj_id,
                        details={
                            "old_state": old_state,
                            "new_state": new_state,
                        }
                    )
                    events.append(event)
                    self._emit_event(event)

                elif new_state.lower() == "up" and old_state and old_state.lower() != "up":
                    event = HealthEvent(
                        timestamp=datetime.now(),
                        severity=EventSeverity.RECOVERY,
                        event_type="isis_adjacency_recovered",
                        protocol="isis",
                        agent_id=agent_id,
                        peer_id=adj_id,
                        details={
                            "old_state": old_state,
                            "new_state": new_state,
                        }
                    )
                    events.append(event)
                    self._emit_event(event)

        self._isis_adjacencies[agent_id] = adjacencies.copy()
        return events

    def update_route_count(self, agent_id: str, route_count: int, threshold_pct: float = 20.0) -> List[HealthEvent]:
        """
        Update route count and detect significant changes

        Args:
            agent_id: Agent ID
            route_count: Current number of routes
            threshold_pct: Percentage change to trigger event

        Returns:
            List of generated health events
        """
        events = []
        prev_count = self._route_counts.get(agent_id)

        if prev_count is not None and prev_count > 0:
            change_pct = ((route_count - prev_count) / prev_count) * 100

            if abs(change_pct) >= threshold_pct:
                event = HealthEvent(
                    timestamp=datetime.now(),
                    severity=EventSeverity.WARNING if route_count < prev_count else EventSeverity.INFO,
                    event_type="route_count_change",
                    protocol="routing",
                    agent_id=agent_id,
                    details={
                        "old_count": prev_count,
                        "new_count": route_count,
                        "change_pct": round(change_pct, 2),
                    }
                )
                events.append(event)
                self._emit_event(event)

        self._route_counts[agent_id] = route_count
        return events

    def get_events(self, limit: int = 100, severity: Optional[EventSeverity] = None) -> List[HealthEvent]:
        """
        Get recent health events

        Args:
            limit: Maximum events to return
            severity: Filter by severity (optional)

        Returns:
            List of health events
        """
        events = list(self._events)[-limit:]
        if severity:
            events = [e for e in events if e.severity == severity]
        return events

    def get_current_state(self) -> Dict[str, Any]:
        """Get current monitored state"""
        return {
            "ospf_neighbors": self._ospf_neighbors,
            "bgp_peers": self._bgp_peers,
            "isis_adjacencies": self._isis_adjacencies,
            "route_counts": self._route_counts,
            "event_count": len(self._events),
        }

    def get_health_summary(self) -> Dict[str, Any]:
        """
        Get health summary across all agents

        Returns:
            Summary of healthy/unhealthy states
        """
        # Count healthy OSPF adjacencies
        ospf_full = sum(
            sum(1 for s in neighbors.values() if s.lower() == "full")
            for neighbors in self._ospf_neighbors.values()
        )
        ospf_total = sum(len(n) for n in self._ospf_neighbors.values())

        # Count healthy BGP peers
        bgp_established = sum(
            sum(1 for s in peers.values() if s.lower() == "established")
            for peers in self._bgp_peers.values()
        )
        bgp_total = sum(len(p) for p in self._bgp_peers.values())

        # Count healthy IS-IS adjacencies
        isis_up = sum(
            sum(1 for s in adjs.values() if s.lower() == "up")
            for adjs in self._isis_adjacencies.values()
        )
        isis_total = sum(len(a) for a in self._isis_adjacencies.values())

        # Recent critical events
        recent_critical = len([
            e for e in list(self._events)[-50:]
            if e.severity == EventSeverity.CRITICAL
        ])

        return {
            "ospf": {
                "healthy": ospf_full,
                "total": ospf_total,
                "health_pct": round((ospf_full / ospf_total * 100) if ospf_total > 0 else 100, 1)
            },
            "bgp": {
                "healthy": bgp_established,
                "total": bgp_total,
                "health_pct": round((bgp_established / bgp_total * 100) if bgp_total > 0 else 100, 1)
            },
            "isis": {
                "healthy": isis_up,
                "total": isis_total,
                "health_pct": round((isis_up / isis_total * 100) if isis_total > 0 else 100, 1)
            },
            "recent_critical_events": recent_critical,
            "monitored_agents": len(set(
                list(self._ospf_neighbors.keys()) +
                list(self._bgp_peers.keys()) +
                list(self._isis_adjacencies.keys())
            ))
        }
