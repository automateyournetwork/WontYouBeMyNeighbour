"""
Traffic Generator - Generates synthetic network traffic for testing

Provides:
- Multiple traffic flow types (TCP, UDP, ICMP)
- Traffic profiles (constant, burst, ramp, random)
- Bandwidth and PPS configuration
- Flow scheduling and management
"""

import logging
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
import random
import math

logger = logging.getLogger("TrafficGenerator")


class FlowType(Enum):
    """Types of traffic flows"""
    TCP = "tcp"
    UDP = "udp"
    ICMP = "icmp"
    HTTP = "http"
    HTTPS = "https"
    DNS = "dns"
    CUSTOM = "custom"


class FlowStatus(Enum):
    """Status of a traffic flow"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrafficPattern(Enum):
    """Traffic generation patterns"""
    CONSTANT = "constant"      # Steady rate
    BURST = "burst"            # Periodic bursts
    RAMP = "ramp"              # Gradually increasing
    SINE = "sine"              # Sinusoidal variation
    RANDOM = "random"          # Random variation
    POISSON = "poisson"        # Poisson distribution


@dataclass
class TrafficProfile:
    """
    Traffic generation profile configuration

    Attributes:
        profile_id: Unique identifier
        name: Human-readable name
        pattern: Traffic pattern type
        base_rate_mbps: Base bandwidth in Mbps
        peak_rate_mbps: Peak bandwidth in Mbps
        duration_seconds: How long to generate traffic
        packet_size: Packet size in bytes
        burst_interval_seconds: Interval between bursts
        burst_duration_seconds: Duration of each burst
    """
    profile_id: str
    name: str
    pattern: TrafficPattern = TrafficPattern.CONSTANT
    base_rate_mbps: float = 10.0
    peak_rate_mbps: float = 100.0
    duration_seconds: int = 60
    packet_size: int = 1500
    burst_interval_seconds: int = 10
    burst_duration_seconds: int = 2
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_rate_at_time(self, elapsed_seconds: float) -> float:
        """
        Calculate the target rate at a given time

        Args:
            elapsed_seconds: Time since start

        Returns:
            Target rate in Mbps
        """
        if self.pattern == TrafficPattern.CONSTANT:
            return self.base_rate_mbps

        elif self.pattern == TrafficPattern.BURST:
            cycle = elapsed_seconds % (self.burst_interval_seconds + self.burst_duration_seconds)
            if cycle < self.burst_duration_seconds:
                return self.peak_rate_mbps
            return self.base_rate_mbps

        elif self.pattern == TrafficPattern.RAMP:
            progress = elapsed_seconds / self.duration_seconds
            return self.base_rate_mbps + progress * (self.peak_rate_mbps - self.base_rate_mbps)

        elif self.pattern == TrafficPattern.SINE:
            # Oscillate between base and peak with period of duration
            phase = (elapsed_seconds / self.duration_seconds) * 2 * math.pi
            amplitude = (self.peak_rate_mbps - self.base_rate_mbps) / 2
            return self.base_rate_mbps + amplitude + amplitude * math.sin(phase)

        elif self.pattern == TrafficPattern.RANDOM:
            return random.uniform(self.base_rate_mbps, self.peak_rate_mbps)

        elif self.pattern == TrafficPattern.POISSON:
            # Generate Poisson-like bursts
            lambda_param = 1 / self.burst_interval_seconds
            if random.random() < lambda_param:
                return self.peak_rate_mbps
            return self.base_rate_mbps

        return self.base_rate_mbps

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "pattern": self.pattern.value,
            "base_rate_mbps": self.base_rate_mbps,
            "peak_rate_mbps": self.peak_rate_mbps,
            "duration_seconds": self.duration_seconds,
            "packet_size": self.packet_size,
            "burst_interval_seconds": self.burst_interval_seconds,
            "burst_duration_seconds": self.burst_duration_seconds,
            "metadata": self.metadata
        }


@dataclass
class TrafficFlow:
    """
    A traffic flow between source and destination

    Attributes:
        flow_id: Unique identifier
        source_agent: Source agent ID
        dest_agent: Destination agent ID
        source_ip: Source IP address
        dest_ip: Destination IP address
        dest_port: Destination port
        flow_type: Type of traffic
        profile: Traffic generation profile
        status: Current status
    """
    flow_id: str
    source_agent: str
    dest_agent: str
    source_ip: str
    dest_ip: str
    dest_port: int
    flow_type: FlowType
    profile: TrafficProfile
    status: FlowStatus = FlowStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    bytes_sent: int = 0
    packets_sent: int = 0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time since start"""
        if not self.started_at:
            return 0
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()

    @property
    def avg_rate_mbps(self) -> float:
        """Calculate average throughput in Mbps"""
        if self.elapsed_seconds <= 0:
            return 0
        return (self.bytes_sent * 8) / (self.elapsed_seconds * 1_000_000)

    @property
    def is_active(self) -> bool:
        """Check if flow is currently active"""
        return self.status in {FlowStatus.RUNNING, FlowStatus.PAUSED}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flow_id": self.flow_id,
            "source_agent": self.source_agent,
            "dest_agent": self.dest_agent,
            "source_ip": self.source_ip,
            "dest_ip": self.dest_ip,
            "dest_port": self.dest_port,
            "flow_type": self.flow_type.value,
            "profile": self.profile.to_dict(),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "bytes_sent": self.bytes_sent,
            "packets_sent": self.packets_sent,
            "elapsed_seconds": self.elapsed_seconds,
            "avg_rate_mbps": self.avg_rate_mbps,
            "error_message": self.error_message,
            "metadata": self.metadata
        }


class TrafficGenerator:
    """
    Manages traffic generation across the network
    """

    def __init__(self):
        """Initialize traffic generator"""
        self._flows: Dict[str, TrafficFlow] = {}
        self._profiles: Dict[str, TrafficProfile] = {}
        self._flow_counter = 0
        self._profile_counter = 0
        self._running_tasks: Dict[str, asyncio.Task] = {}

        # Create default profiles
        self._create_default_profiles()

    def _generate_flow_id(self) -> str:
        """Generate unique flow ID"""
        self._flow_counter += 1
        return f"flow-{self._flow_counter:06d}"

    def _generate_profile_id(self) -> str:
        """Generate unique profile ID"""
        self._profile_counter += 1
        return f"profile-{self._profile_counter:06d}"

    def _create_default_profiles(self):
        """Create default traffic profiles"""
        defaults = [
            TrafficProfile(
                profile_id=self._generate_profile_id(),
                name="Light Load",
                pattern=TrafficPattern.CONSTANT,
                base_rate_mbps=10,
                peak_rate_mbps=10,
                duration_seconds=60
            ),
            TrafficProfile(
                profile_id=self._generate_profile_id(),
                name="Medium Load",
                pattern=TrafficPattern.CONSTANT,
                base_rate_mbps=100,
                peak_rate_mbps=100,
                duration_seconds=60
            ),
            TrafficProfile(
                profile_id=self._generate_profile_id(),
                name="Heavy Load",
                pattern=TrafficPattern.CONSTANT,
                base_rate_mbps=1000,
                peak_rate_mbps=1000,
                duration_seconds=60
            ),
            TrafficProfile(
                profile_id=self._generate_profile_id(),
                name="Burst Traffic",
                pattern=TrafficPattern.BURST,
                base_rate_mbps=10,
                peak_rate_mbps=500,
                duration_seconds=120,
                burst_interval_seconds=10,
                burst_duration_seconds=2
            ),
            TrafficProfile(
                profile_id=self._generate_profile_id(),
                name="Ramp Up",
                pattern=TrafficPattern.RAMP,
                base_rate_mbps=10,
                peak_rate_mbps=1000,
                duration_seconds=300
            ),
            TrafficProfile(
                profile_id=self._generate_profile_id(),
                name="Stress Test",
                pattern=TrafficPattern.CONSTANT,
                base_rate_mbps=10000,
                peak_rate_mbps=10000,
                duration_seconds=60
            )
        ]

        for profile in defaults:
            self._profiles[profile.profile_id] = profile

    def create_profile(
        self,
        name: str,
        pattern: TrafficPattern = TrafficPattern.CONSTANT,
        base_rate_mbps: float = 10.0,
        peak_rate_mbps: float = 100.0,
        duration_seconds: int = 60,
        packet_size: int = 1500,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TrafficProfile:
        """
        Create a new traffic profile

        Args:
            name: Profile name
            pattern: Traffic pattern
            base_rate_mbps: Base rate in Mbps
            peak_rate_mbps: Peak rate in Mbps
            duration_seconds: Duration in seconds
            packet_size: Packet size in bytes
            metadata: Additional metadata

        Returns:
            Created TrafficProfile
        """
        profile = TrafficProfile(
            profile_id=self._generate_profile_id(),
            name=name,
            pattern=pattern,
            base_rate_mbps=base_rate_mbps,
            peak_rate_mbps=peak_rate_mbps,
            duration_seconds=duration_seconds,
            packet_size=packet_size,
            metadata=metadata or {}
        )

        self._profiles[profile.profile_id] = profile
        logger.info(f"Created traffic profile: {name}")
        return profile

    def get_profile(self, profile_id: str) -> Optional[TrafficProfile]:
        """Get a profile by ID"""
        return self._profiles.get(profile_id)

    def get_profile_by_name(self, name: str) -> Optional[TrafficProfile]:
        """Get a profile by name"""
        for profile in self._profiles.values():
            if profile.name == name:
                return profile
        return None

    def get_all_profiles(self) -> List[TrafficProfile]:
        """Get all traffic profiles"""
        return list(self._profiles.values())

    def create_flow(
        self,
        source_agent: str,
        dest_agent: str,
        source_ip: str,
        dest_ip: str,
        dest_port: int = 5001,
        flow_type: FlowType = FlowType.TCP,
        profile: Optional[TrafficProfile] = None,
        profile_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TrafficFlow:
        """
        Create a new traffic flow

        Args:
            source_agent: Source agent ID
            dest_agent: Destination agent ID
            source_ip: Source IP address
            dest_ip: Destination IP address
            dest_port: Destination port
            flow_type: Type of traffic
            profile: Traffic profile (or use profile_id)
            profile_id: Profile ID to use
            metadata: Additional metadata

        Returns:
            Created TrafficFlow
        """
        # Get profile
        if profile is None and profile_id:
            profile = self._profiles.get(profile_id)
        if profile is None:
            # Use default light load profile
            profile = self.get_profile_by_name("Light Load")

        flow = TrafficFlow(
            flow_id=self._generate_flow_id(),
            source_agent=source_agent,
            dest_agent=dest_agent,
            source_ip=source_ip,
            dest_ip=dest_ip,
            dest_port=dest_port,
            flow_type=flow_type,
            profile=profile,
            metadata=metadata or {}
        )

        self._flows[flow.flow_id] = flow
        logger.info(f"Created flow: {source_agent} -> {dest_agent} ({flow_type.value})")
        return flow

    async def start_flow(self, flow_id: str) -> bool:
        """
        Start a traffic flow

        Args:
            flow_id: Flow to start

        Returns:
            True if started successfully
        """
        flow = self._flows.get(flow_id)
        if not flow:
            logger.warning(f"Flow not found: {flow_id}")
            return False

        if flow.status == FlowStatus.RUNNING:
            logger.warning(f"Flow already running: {flow_id}")
            return False

        flow.status = FlowStatus.RUNNING
        flow.started_at = datetime.now()

        # Start simulation task
        task = asyncio.create_task(self._simulate_flow(flow))
        self._running_tasks[flow_id] = task

        logger.info(f"Started flow: {flow_id}")
        return True

    async def _simulate_flow(self, flow: TrafficFlow):
        """
        Simulate traffic generation for a flow

        Args:
            flow: Flow to simulate
        """
        try:
            start_time = datetime.now()
            update_interval = 1.0  # Update stats every second

            while flow.status == FlowStatus.RUNNING:
                elapsed = (datetime.now() - start_time).total_seconds()

                if elapsed >= flow.profile.duration_seconds:
                    break

                # Calculate current rate
                current_rate = flow.profile.get_rate_at_time(elapsed)

                # Simulate bytes sent this interval
                bytes_this_interval = int((current_rate * 1_000_000 / 8) * update_interval)
                packets_this_interval = bytes_this_interval // flow.profile.packet_size

                flow.bytes_sent += bytes_this_interval
                flow.packets_sent += packets_this_interval

                await asyncio.sleep(update_interval)

            flow.status = FlowStatus.COMPLETED
            flow.completed_at = datetime.now()
            logger.info(f"Flow completed: {flow.flow_id}, sent {flow.bytes_sent} bytes")

        except asyncio.CancelledError:
            flow.status = FlowStatus.CANCELLED
            flow.completed_at = datetime.now()
            logger.info(f"Flow cancelled: {flow.flow_id}")

        except Exception as e:
            flow.status = FlowStatus.FAILED
            flow.error_message = str(e)
            flow.completed_at = datetime.now()
            logger.error(f"Flow failed: {flow.flow_id}: {e}")

    async def stop_flow(self, flow_id: str) -> bool:
        """
        Stop a running flow

        Args:
            flow_id: Flow to stop

        Returns:
            True if stopped successfully
        """
        flow = self._flows.get(flow_id)
        if not flow:
            return False

        if flow_id in self._running_tasks:
            self._running_tasks[flow_id].cancel()
            del self._running_tasks[flow_id]

        flow.status = FlowStatus.CANCELLED
        flow.completed_at = datetime.now()
        logger.info(f"Stopped flow: {flow_id}")
        return True

    async def pause_flow(self, flow_id: str) -> bool:
        """Pause a running flow"""
        flow = self._flows.get(flow_id)
        if not flow or flow.status != FlowStatus.RUNNING:
            return False

        flow.status = FlowStatus.PAUSED
        logger.info(f"Paused flow: {flow_id}")
        return True

    async def resume_flow(self, flow_id: str) -> bool:
        """Resume a paused flow"""
        flow = self._flows.get(flow_id)
        if not flow or flow.status != FlowStatus.PAUSED:
            return False

        flow.status = FlowStatus.RUNNING
        logger.info(f"Resumed flow: {flow_id}")
        return True

    def get_flow(self, flow_id: str) -> Optional[TrafficFlow]:
        """Get a flow by ID"""
        return self._flows.get(flow_id)

    def get_all_flows(self) -> List[TrafficFlow]:
        """Get all flows"""
        return list(self._flows.values())

    def get_active_flows(self) -> List[TrafficFlow]:
        """Get all active flows"""
        return [f for f in self._flows.values() if f.is_active]

    def get_flows_by_agent(self, agent_id: str) -> List[TrafficFlow]:
        """Get flows for a specific agent (as source or destination)"""
        return [
            f for f in self._flows.values()
            if f.source_agent == agent_id or f.dest_agent == agent_id
        ]

    async def stop_all_flows(self):
        """Stop all running flows"""
        for flow_id in list(self._running_tasks.keys()):
            await self.stop_flow(flow_id)
        logger.info("Stopped all flows")

    def get_traffic_summary(self) -> Dict[str, Any]:
        """Get overall traffic generation summary"""
        total_flows = len(self._flows)
        active_flows = len(self.get_active_flows())
        completed_flows = len([f for f in self._flows.values() if f.status == FlowStatus.COMPLETED])
        failed_flows = len([f for f in self._flows.values() if f.status == FlowStatus.FAILED])

        total_bytes = sum(f.bytes_sent for f in self._flows.values())
        total_packets = sum(f.packets_sent for f in self._flows.values())

        return {
            "total_flows": total_flows,
            "active_flows": active_flows,
            "completed_flows": completed_flows,
            "failed_flows": failed_flows,
            "total_bytes_sent": total_bytes,
            "total_packets_sent": total_packets,
            "total_profiles": len(self._profiles)
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Get generator statistics"""
        return {
            "total_flows": len(self._flows),
            "total_profiles": len(self._profiles),
            "running_tasks": len(self._running_tasks),
            "flow_types": [t.value for t in FlowType],
            "traffic_patterns": [p.value for p in TrafficPattern]
        }


# Global generator instance
_global_generator: Optional[TrafficGenerator] = None


def get_traffic_generator() -> TrafficGenerator:
    """Get or create the global traffic generator"""
    global _global_generator
    if _global_generator is None:
        _global_generator = TrafficGenerator()
    return _global_generator
