"""
Traffic Simulator for ASI Network

Provides realistic traffic simulation, flow visualization,
heatmap generation, and congestion detection.
"""

import asyncio
import random
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class CongestionLevel(Enum):
    """Traffic congestion levels."""
    NONE = "none"           # 0-25% utilization
    LOW = "low"             # 25-50% utilization
    MEDIUM = "medium"       # 50-75% utilization
    HIGH = "high"           # 75-90% utilization
    CRITICAL = "critical"   # 90-100% utilization


class TrafficPattern(Enum):
    """Predefined traffic patterns."""
    CONSTANT = "constant"           # Steady traffic rate
    BURST = "burst"                 # Periodic bursts
    RANDOM = "random"               # Random variations
    WAVE = "wave"                   # Sinusoidal pattern
    RAMP_UP = "ramp_up"             # Gradually increasing
    RAMP_DOWN = "ramp_down"         # Gradually decreasing
    BUSINESS_HOURS = "business_hours"  # High during work hours
    DDOS = "ddos"                   # Simulated attack pattern


@dataclass
class FlowStatistics:
    """Statistics for a traffic flow."""
    packets_sent: int = 0
    packets_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    packets_dropped: int = 0
    latency_ms: float = 0.0
    jitter_ms: float = 0.0
    packet_loss_pct: float = 0.0
    throughput_bps: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "packets_dropped": self.packets_dropped,
            "latency_ms": round(self.latency_ms, 2),
            "jitter_ms": round(self.jitter_ms, 2),
            "packet_loss_pct": round(self.packet_loss_pct, 2),
            "throughput_bps": round(self.throughput_bps, 2),
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class TrafficFlow:
    """Represents a traffic flow between two endpoints."""
    flow_id: str
    source_agent: str
    source_interface: str
    dest_agent: str
    dest_interface: str
    protocol: str = "tcp"           # tcp, udp, icmp
    application: str = "generic"    # http, ssh, bgp, ospf, etc.
    source_port: int = 0
    dest_port: int = 0
    rate_bps: float = 1_000_000     # Target rate in bits per second
    packet_size: int = 1500         # Average packet size
    priority: int = 0               # QoS priority (0-7)
    pattern: TrafficPattern = TrafficPattern.CONSTANT
    active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    statistics: FlowStatistics = field(default_factory=FlowStatistics)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "flow_id": self.flow_id,
            "source_agent": self.source_agent,
            "source_interface": self.source_interface,
            "dest_agent": self.dest_agent,
            "dest_interface": self.dest_interface,
            "protocol": self.protocol,
            "application": self.application,
            "source_port": self.source_port,
            "dest_port": self.dest_port,
            "rate_bps": self.rate_bps,
            "rate_human": self._format_rate(self.rate_bps),
            "packet_size": self.packet_size,
            "priority": self.priority,
            "pattern": self.pattern.value,
            "active": self.active,
            "created_at": self.created_at.isoformat(),
            "statistics": self.statistics.to_dict(),
        }

    @staticmethod
    def _format_rate(bps: float) -> str:
        """Format rate in human-readable form."""
        if bps >= 1_000_000_000:
            return f"{bps / 1_000_000_000:.1f} Gbps"
        elif bps >= 1_000_000:
            return f"{bps / 1_000_000:.1f} Mbps"
        elif bps >= 1_000:
            return f"{bps / 1_000:.1f} Kbps"
        return f"{bps:.0f} bps"


@dataclass
class LinkUtilization:
    """Utilization data for a link."""
    source_agent: str
    dest_agent: str
    source_interface: str
    dest_interface: str
    capacity_bps: float = 1_000_000_000  # 1 Gbps default
    current_rate_bps: float = 0
    utilization_pct: float = 0.0
    congestion: CongestionLevel = CongestionLevel.NONE
    flow_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_agent": self.source_agent,
            "dest_agent": self.dest_agent,
            "source_interface": self.source_interface,
            "dest_interface": self.dest_interface,
            "capacity_bps": self.capacity_bps,
            "current_rate_bps": round(self.current_rate_bps, 2),
            "utilization_pct": round(self.utilization_pct, 2),
            "congestion": self.congestion.value,
            "flow_count": self.flow_count,
        }


class TrafficSimulator:
    """
    Traffic simulator for ASI network.

    Simulates realistic traffic patterns between agents,
    calculates link utilization, and detects congestion.
    """

    # Singleton instance
    _instance: Optional["TrafficSimulator"] = None

    def __new__(cls) -> "TrafficSimulator":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._flows: Dict[str, TrafficFlow] = {}
        self._link_utilization: Dict[str, LinkUtilization] = {}
        self._history: List[Dict[str, Any]] = []
        self._running = False
        self._simulation_task: Optional[asyncio.Task] = None
        self._flow_counter = 0

        # Default link capacities
        self._default_capacity_bps = 1_000_000_000  # 1 Gbps

        # Simulation parameters
        self._update_interval = 1.0  # seconds
        self._history_max_size = 3600  # 1 hour at 1s intervals

        logger.info("TrafficSimulator initialized")

    def _generate_flow_id(self) -> str:
        """Generate unique flow ID."""
        self._flow_counter += 1
        return f"flow-{self._flow_counter:06d}"

    def _get_link_key(self, src_agent: str, dst_agent: str) -> str:
        """Generate link key (sorted for bidirectional)."""
        return f"{min(src_agent, dst_agent)}:{max(src_agent, dst_agent)}"

    # ==== Flow Management ====

    def create_flow(
        self,
        source_agent: str,
        source_interface: str,
        dest_agent: str,
        dest_interface: str,
        rate_bps: float = 1_000_000,
        protocol: str = "tcp",
        application: str = "generic",
        pattern: TrafficPattern = TrafficPattern.CONSTANT,
        source_port: int = 0,
        dest_port: int = 0,
        priority: int = 0,
    ) -> TrafficFlow:
        """Create a new traffic flow."""
        flow_id = self._generate_flow_id()

        # Auto-assign ports if not specified
        if source_port == 0:
            source_port = random.randint(49152, 65535)
        if dest_port == 0:
            dest_port = self._get_default_port(application)

        flow = TrafficFlow(
            flow_id=flow_id,
            source_agent=source_agent,
            source_interface=source_interface,
            dest_agent=dest_agent,
            dest_interface=dest_interface,
            rate_bps=rate_bps,
            protocol=protocol,
            application=application,
            pattern=pattern,
            source_port=source_port,
            dest_port=dest_port,
            priority=priority,
        )

        self._flows[flow_id] = flow
        self._update_link_utilization()

        logger.info(f"Created flow {flow_id}: {source_agent} -> {dest_agent} @ {flow._format_rate(rate_bps)}")
        return flow

    def delete_flow(self, flow_id: str) -> bool:
        """Delete a traffic flow."""
        if flow_id in self._flows:
            del self._flows[flow_id]
            self._update_link_utilization()
            logger.info(f"Deleted flow {flow_id}")
            return True
        return False

    def get_flow(self, flow_id: str) -> Optional[TrafficFlow]:
        """Get a flow by ID."""
        return self._flows.get(flow_id)

    def list_flows(
        self,
        source_agent: Optional[str] = None,
        dest_agent: Optional[str] = None,
        active_only: bool = False,
    ) -> List[TrafficFlow]:
        """List traffic flows with optional filtering."""
        flows = list(self._flows.values())

        if source_agent:
            flows = [f for f in flows if f.source_agent == source_agent]
        if dest_agent:
            flows = [f for f in flows if f.dest_agent == dest_agent]
        if active_only:
            flows = [f for f in flows if f.active]

        return flows

    def set_flow_active(self, flow_id: str, active: bool) -> bool:
        """Enable or disable a flow."""
        if flow_id in self._flows:
            self._flows[flow_id].active = active
            self._update_link_utilization()
            return True
        return False

    def update_flow_rate(self, flow_id: str, rate_bps: float) -> bool:
        """Update flow rate."""
        if flow_id in self._flows:
            self._flows[flow_id].rate_bps = rate_bps
            self._update_link_utilization()
            return True
        return False

    # ==== Traffic Patterns ====

    def create_traffic_scenario(
        self,
        scenario: str,
        agents: List[str],
    ) -> List[TrafficFlow]:
        """Create a predefined traffic scenario."""
        flows = []

        if scenario == "mesh":
            # Full mesh - every agent talks to every other
            for i, src in enumerate(agents):
                for j, dst in enumerate(agents):
                    if i != j:
                        flow = self.create_flow(
                            source_agent=src,
                            source_interface="eth0",
                            dest_agent=dst,
                            dest_interface="eth0",
                            rate_bps=random.uniform(100_000, 10_000_000),
                            pattern=TrafficPattern.RANDOM,
                        )
                        flows.append(flow)

        elif scenario == "hub_spoke":
            # First agent is hub, others are spokes
            if len(agents) >= 2:
                hub = agents[0]
                for spoke in agents[1:]:
                    # Hub to spoke
                    flow1 = self.create_flow(
                        source_agent=hub,
                        source_interface="eth0",
                        dest_agent=spoke,
                        dest_interface="eth0",
                        rate_bps=random.uniform(1_000_000, 100_000_000),
                        pattern=TrafficPattern.BUSINESS_HOURS,
                    )
                    # Spoke to hub
                    flow2 = self.create_flow(
                        source_agent=spoke,
                        source_interface="eth0",
                        dest_agent=hub,
                        dest_interface="eth0",
                        rate_bps=random.uniform(100_000, 10_000_000),
                        pattern=TrafficPattern.BURST,
                    )
                    flows.extend([flow1, flow2])

        elif scenario == "backbone":
            # Linear backbone with traffic across
            for i in range(len(agents) - 1):
                flow = self.create_flow(
                    source_agent=agents[i],
                    source_interface="eth0",
                    dest_agent=agents[i + 1],
                    dest_interface="eth0",
                    rate_bps=500_000_000,  # 500 Mbps
                    pattern=TrafficPattern.WAVE,
                    application="bgp",
                )
                flows.append(flow)

        elif scenario == "ddos":
            # DDoS attack simulation - many sources to one target
            if len(agents) >= 2:
                target = agents[0]
                for attacker in agents[1:]:
                    flow = self.create_flow(
                        source_agent=attacker,
                        source_interface="eth0",
                        dest_agent=target,
                        dest_interface="eth0",
                        rate_bps=random.uniform(100_000_000, 500_000_000),
                        pattern=TrafficPattern.DDOS,
                        protocol="udp",
                    )
                    flows.append(flow)

        logger.info(f"Created scenario '{scenario}' with {len(flows)} flows")
        return flows

    # ==== Simulation Engine ====

    async def start_simulation(self):
        """Start the traffic simulation."""
        if self._running:
            return

        self._running = True
        self._simulation_task = asyncio.create_task(self._simulation_loop())
        logger.info("Traffic simulation started")

    async def stop_simulation(self):
        """Stop the traffic simulation."""
        self._running = False
        if self._simulation_task:
            self._simulation_task.cancel()
            try:
                await self._simulation_task
            except asyncio.CancelledError:
                pass
        logger.info("Traffic simulation stopped")

    async def _simulation_loop(self):
        """Main simulation loop."""
        while self._running:
            try:
                self._simulate_step()
                await asyncio.sleep(self._update_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Simulation error: {e}")

    def _simulate_step(self):
        """Perform one simulation step."""
        current_time = datetime.now()

        for flow in self._flows.values():
            if not flow.active:
                continue

            # Calculate actual rate based on pattern
            actual_rate = self._apply_pattern(flow.rate_bps, flow.pattern, current_time)

            # Calculate packets and bytes for this interval
            bits_sent = actual_rate * self._update_interval
            bytes_sent = bits_sent / 8
            packets_sent = int(bytes_sent / flow.packet_size) or 1

            # Simulate some packet loss and latency
            loss_rate = random.uniform(0, 0.01)  # 0-1% loss
            packets_received = int(packets_sent * (1 - loss_rate))
            bytes_received = packets_received * flow.packet_size

            # Update statistics
            stats = flow.statistics
            stats.packets_sent += packets_sent
            stats.packets_received += packets_received
            stats.bytes_sent += int(bytes_sent)
            stats.bytes_received += int(bytes_received)
            stats.packets_dropped += packets_sent - packets_received
            stats.latency_ms = random.uniform(1, 50)
            stats.jitter_ms = random.uniform(0, 5)
            stats.packet_loss_pct = (stats.packets_dropped / max(stats.packets_sent, 1)) * 100
            stats.throughput_bps = actual_rate
            stats.last_updated = current_time

        # Update link utilization
        self._update_link_utilization()

        # Record history
        self._record_history()

    def _apply_pattern(
        self,
        base_rate: float,
        pattern: TrafficPattern,
        current_time: datetime,
    ) -> float:
        """Apply traffic pattern to base rate."""
        if pattern == TrafficPattern.CONSTANT:
            return base_rate

        elif pattern == TrafficPattern.BURST:
            # Burst every 10 seconds
            if current_time.second % 10 < 2:
                return base_rate * 3
            return base_rate * 0.3

        elif pattern == TrafficPattern.RANDOM:
            return base_rate * random.uniform(0.2, 1.5)

        elif pattern == TrafficPattern.WAVE:
            # Sinusoidal pattern
            import math
            phase = (current_time.second / 30) * math.pi
            multiplier = 0.5 + 0.5 * math.sin(phase)
            return base_rate * multiplier

        elif pattern == TrafficPattern.RAMP_UP:
            # Gradually increase over 60 seconds
            progress = current_time.second / 60
            return base_rate * progress

        elif pattern == TrafficPattern.RAMP_DOWN:
            # Gradually decrease over 60 seconds
            progress = 1 - (current_time.second / 60)
            return base_rate * progress

        elif pattern == TrafficPattern.BUSINESS_HOURS:
            # Higher during 9-17 hours
            hour = current_time.hour
            if 9 <= hour < 17:
                return base_rate * random.uniform(0.8, 1.2)
            elif 7 <= hour < 9 or 17 <= hour < 19:
                return base_rate * random.uniform(0.4, 0.6)
            else:
                return base_rate * random.uniform(0.1, 0.2)

        elif pattern == TrafficPattern.DDOS:
            # Aggressive random bursts
            return base_rate * random.uniform(0.5, 2.0)

        return base_rate

    def _update_link_utilization(self):
        """Update link utilization based on active flows."""
        # Reset utilization
        link_rates: Dict[str, float] = defaultdict(float)
        link_flows: Dict[str, int] = defaultdict(int)

        # Aggregate flow rates per link
        for flow in self._flows.values():
            if not flow.active:
                continue

            link_key = self._get_link_key(flow.source_agent, flow.dest_agent)
            link_rates[link_key] += flow.statistics.throughput_bps or flow.rate_bps
            link_flows[link_key] += 1

        # Update link utilization objects
        for link_key in link_rates:
            agents = link_key.split(":")
            if link_key not in self._link_utilization:
                self._link_utilization[link_key] = LinkUtilization(
                    source_agent=agents[0],
                    dest_agent=agents[1],
                    source_interface="eth0",
                    dest_interface="eth0",
                    capacity_bps=self._default_capacity_bps,
                )

            util = self._link_utilization[link_key]
            util.current_rate_bps = link_rates[link_key]
            util.utilization_pct = (util.current_rate_bps / util.capacity_bps) * 100
            util.flow_count = link_flows[link_key]
            util.congestion = self._get_congestion_level(util.utilization_pct)

    def _get_congestion_level(self, utilization_pct: float) -> CongestionLevel:
        """Determine congestion level from utilization."""
        if utilization_pct >= 90:
            return CongestionLevel.CRITICAL
        elif utilization_pct >= 75:
            return CongestionLevel.HIGH
        elif utilization_pct >= 50:
            return CongestionLevel.MEDIUM
        elif utilization_pct >= 25:
            return CongestionLevel.LOW
        return CongestionLevel.NONE

    def _record_history(self):
        """Record current state to history."""
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "total_flows": len([f for f in self._flows.values() if f.active]),
            "total_throughput_bps": sum(
                f.statistics.throughput_bps
                for f in self._flows.values()
                if f.active
            ),
            "links": {
                k: v.to_dict() for k, v in self._link_utilization.items()
            },
        }

        self._history.append(snapshot)

        # Trim history if too large
        if len(self._history) > self._history_max_size:
            self._history = self._history[-self._history_max_size:]

    # ==== Data Access ====

    def get_traffic_heatmap(self) -> Dict[str, Any]:
        """Get traffic heatmap data for visualization."""
        links = []

        for link_key, util in self._link_utilization.items():
            links.append({
                "id": link_key,
                "source": util.source_agent,
                "target": util.dest_agent,
                "utilization": util.utilization_pct,
                "rate_bps": util.current_rate_bps,
                "congestion": util.congestion.value,
                "color": self._get_congestion_color(util.congestion),
                "width": self._get_link_width(util.utilization_pct),
            })

        return {
            "links": links,
            "timestamp": datetime.now().isoformat(),
            "total_links": len(links),
            "congested_links": len([l for l in links if l["congestion"] in ["high", "critical"]]),
        }

    def _get_congestion_color(self, level: CongestionLevel) -> str:
        """Get color for congestion level."""
        colors = {
            CongestionLevel.NONE: "#22c55e",      # green
            CongestionLevel.LOW: "#84cc16",       # lime
            CongestionLevel.MEDIUM: "#eab308",    # yellow
            CongestionLevel.HIGH: "#f97316",      # orange
            CongestionLevel.CRITICAL: "#ef4444",  # red
        }
        return colors.get(level, "#6b7280")

    def _get_link_width(self, utilization_pct: float) -> float:
        """Get link visual width based on utilization."""
        return max(1, min(10, utilization_pct / 10))

    def get_congestion_report(self) -> Dict[str, Any]:
        """Get congestion analysis report."""
        congested = []

        for link_key, util in self._link_utilization.items():
            if util.congestion in [CongestionLevel.HIGH, CongestionLevel.CRITICAL]:
                # Find flows contributing to congestion
                contributing_flows = [
                    f.flow_id
                    for f in self._flows.values()
                    if f.active and self._get_link_key(f.source_agent, f.dest_agent) == link_key
                ]

                congested.append({
                    "link": link_key,
                    "source_agent": util.source_agent,
                    "dest_agent": util.dest_agent,
                    "utilization_pct": util.utilization_pct,
                    "congestion": util.congestion.value,
                    "current_rate_bps": util.current_rate_bps,
                    "capacity_bps": util.capacity_bps,
                    "flow_count": util.flow_count,
                    "contributing_flows": contributing_flows,
                    "recommendation": self._get_congestion_recommendation(util),
                })

        return {
            "timestamp": datetime.now().isoformat(),
            "total_links": len(self._link_utilization),
            "congested_links": len(congested),
            "details": sorted(congested, key=lambda x: -x["utilization_pct"]),
        }

    def _get_congestion_recommendation(self, util: LinkUtilization) -> str:
        """Generate recommendation for congestion."""
        if util.congestion == CongestionLevel.CRITICAL:
            return f"Critical congestion on {util.source_agent}-{util.dest_agent}. Consider adding parallel link or increasing capacity."
        elif util.congestion == CongestionLevel.HIGH:
            return f"High utilization on {util.source_agent}-{util.dest_agent}. Monitor for potential issues."
        return ""

    def get_flow_visualization(self) -> Dict[str, Any]:
        """Get data for flow visualization (animated packets)."""
        flow_visuals = []

        for flow in self._flows.values():
            if not flow.active:
                continue

            # Calculate packets per second for animation speed
            pps = flow.statistics.throughput_bps / (flow.packet_size * 8)

            flow_visuals.append({
                "flow_id": flow.flow_id,
                "source": flow.source_agent,
                "target": flow.dest_agent,
                "color": self._get_application_color(flow.application),
                "speed": min(1.0, pps / 1000),  # Normalize speed
                "size": self._get_packet_size_visual(flow.packet_size),
                "protocol": flow.protocol,
                "application": flow.application,
            })

        return {
            "flows": flow_visuals,
            "timestamp": datetime.now().isoformat(),
        }

    def _get_application_color(self, application: str) -> str:
        """Get color for application type."""
        colors = {
            "bgp": "#8b5cf6",       # purple
            "ospf": "#06b6d4",      # cyan
            "isis": "#ec4899",      # pink
            "http": "#3b82f6",      # blue
            "https": "#3b82f6",     # blue
            "ssh": "#10b981",       # green
            "dns": "#f59e0b",       # amber
            "ntp": "#6366f1",       # indigo
            "snmp": "#14b8a6",      # teal
            "syslog": "#f97316",    # orange
        }
        return colors.get(application, "#6b7280")

    def _get_packet_size_visual(self, packet_size: int) -> float:
        """Get visual size for packet."""
        if packet_size <= 64:
            return 0.3
        elif packet_size <= 512:
            return 0.5
        elif packet_size <= 1500:
            return 0.8
        return 1.0

    def get_history(
        self,
        minutes: int = 60,
    ) -> List[Dict[str, Any]]:
        """Get historical traffic data."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        cutoff_str = cutoff.isoformat()

        return [
            h for h in self._history
            if h["timestamp"] >= cutoff_str
        ]

    def get_statistics(self) -> Dict[str, Any]:
        """Get overall traffic statistics."""
        active_flows = [f for f in self._flows.values() if f.active]

        total_throughput = sum(f.statistics.throughput_bps for f in active_flows)
        total_packets = sum(f.statistics.packets_sent for f in active_flows)
        total_bytes = sum(f.statistics.bytes_sent for f in active_flows)

        return {
            "total_flows": len(self._flows),
            "active_flows": len(active_flows),
            "total_throughput_bps": total_throughput,
            "total_throughput_human": TrafficFlow._format_rate(total_throughput),
            "total_packets_sent": total_packets,
            "total_bytes_sent": total_bytes,
            "total_links": len(self._link_utilization),
            "congested_links": len([
                u for u in self._link_utilization.values()
                if u.congestion in [CongestionLevel.HIGH, CongestionLevel.CRITICAL]
            ]),
            "simulation_running": self._running,
            "timestamp": datetime.now().isoformat(),
        }

    @staticmethod
    def _get_default_port(application: str) -> int:
        """Get default port for application."""
        ports = {
            "http": 80,
            "https": 443,
            "ssh": 22,
            "bgp": 179,
            "ospf": 89,
            "dns": 53,
            "snmp": 161,
            "syslog": 514,
            "ntp": 123,
        }
        return ports.get(application, 0)


# Singleton accessor
def get_traffic_simulator() -> TrafficSimulator:
    """Get the traffic simulator instance."""
    return TrafficSimulator()


# Convenience functions
def simulate_traffic(
    source_agent: str,
    dest_agent: str,
    rate_bps: float = 1_000_000,
    pattern: str = "constant",
) -> TrafficFlow:
    """Create and start simulating traffic between agents."""
    simulator = get_traffic_simulator()
    pattern_enum = TrafficPattern(pattern) if pattern in [p.value for p in TrafficPattern] else TrafficPattern.CONSTANT

    return simulator.create_flow(
        source_agent=source_agent,
        source_interface="eth0",
        dest_agent=dest_agent,
        dest_interface="eth0",
        rate_bps=rate_bps,
        pattern=pattern_enum,
    )


def get_traffic_flows(
    source_agent: Optional[str] = None,
    dest_agent: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get traffic flows as dictionaries."""
    simulator = get_traffic_simulator()
    flows = simulator.list_flows(source_agent=source_agent, dest_agent=dest_agent)
    return [f.to_dict() for f in flows]


def get_traffic_heatmap() -> Dict[str, Any]:
    """Get traffic heatmap data."""
    return get_traffic_simulator().get_traffic_heatmap()


def get_congestion_report() -> Dict[str, Any]:
    """Get congestion report."""
    return get_traffic_simulator().get_congestion_report()
