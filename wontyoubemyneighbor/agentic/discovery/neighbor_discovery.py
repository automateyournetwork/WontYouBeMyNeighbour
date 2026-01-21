"""
IPv6 Neighbor Discovery (ND) for ASI Overlay Network

Implements RFC 4861 Neighbor Discovery protocol for the ASI agent overlay:
- Neighbor Solicitation (NS) - probe for neighbors
- Neighbor Advertisement (NA) - respond to probes
- Router Solicitation (RS) - discover routers (optional)
- Neighbor table maintenance

The ASI overlay uses ULA addresses (fd00:a510::/48) for agent-to-agent
visibility and management, separate from the user-defined underlay.

3-Layer Architecture:
  Layer 1: Docker Network (container networking)
  Layer 2: ASI Overlay (IPv6 agent mesh - this module)
  Layer 3: Underlay (user-defined routing topology)
"""

import asyncio
import logging
import socket
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, IntEnum
from typing import Dict, List, Optional, Any, Callable, Tuple
import ipaddress


# ICMPv6 Types for Neighbor Discovery (RFC 4861)
class ICMPv6Type(IntEnum):
    """ICMPv6 message types for Neighbor Discovery"""
    ROUTER_SOLICITATION = 133
    ROUTER_ADVERTISEMENT = 134
    NEIGHBOR_SOLICITATION = 135
    NEIGHBOR_ADVERTISEMENT = 136
    REDIRECT = 137


class NeighborState(Enum):
    """NUD (Neighbor Unreachability Detection) states"""
    INCOMPLETE = "incomplete"  # Address resolution in progress
    REACHABLE = "reachable"    # Recently confirmed reachable
    STALE = "stale"            # Reachable time expired, need confirmation
    DELAY = "delay"            # Waiting for upper-layer confirmation
    PROBE = "probe"            # Actively probing


@dataclass
class NeighborEntry:
    """Neighbor cache entry"""

    # IPv6 address of the neighbor
    ipv6_address: str

    # Agent identification
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    router_id: Optional[str] = None

    # State machine
    state: NeighborState = NeighborState.INCOMPLETE

    # Docker/Layer 1 info
    docker_ip: Optional[str] = None  # Layer 1 Docker network IP
    mac_address: Optional[str] = None

    # Timestamps
    discovered_at: datetime = field(default_factory=datetime.now)
    last_seen_at: datetime = field(default_factory=datetime.now)
    last_probed_at: Optional[datetime] = None
    reachable_until: Optional[datetime] = None

    # Health tracking
    probe_count: int = 0
    consecutive_failures: int = 0

    # Metadata from NS/NA exchanges
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_reachable(self) -> bool:
        """Check if neighbor is considered reachable"""
        return self.state in (NeighborState.REACHABLE, NeighborState.STALE, NeighborState.DELAY)

    @property
    def age_seconds(self) -> float:
        """Time since discovery in seconds"""
        return (datetime.now() - self.discovered_at).total_seconds()

    @property
    def idle_seconds(self) -> float:
        """Time since last seen in seconds"""
        return (datetime.now() - self.last_seen_at).total_seconds()

    def mark_reachable(self, reachable_time_seconds: int = 30) -> None:
        """Mark neighbor as reachable"""
        self.state = NeighborState.REACHABLE
        self.last_seen_at = datetime.now()
        self.reachable_until = datetime.now() + timedelta(seconds=reachable_time_seconds)
        self.consecutive_failures = 0

    def mark_stale(self) -> None:
        """Mark neighbor as stale (needs reconfirmation)"""
        if self.state == NeighborState.REACHABLE:
            self.state = NeighborState.STALE

    def mark_probe(self) -> None:
        """Mark neighbor as being probed"""
        self.state = NeighborState.PROBE
        self.last_probed_at = datetime.now()
        self.probe_count += 1

    def mark_failed(self) -> None:
        """Mark probe failure"""
        self.consecutive_failures += 1
        if self.consecutive_failures >= 3:
            self.state = NeighborState.INCOMPLETE

    def to_dict(self) -> dict:
        return {
            "ipv6_address": self.ipv6_address,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "router_id": self.router_id,
            "state": self.state.value,
            "docker_ip": self.docker_ip,
            "mac_address": self.mac_address,
            "is_reachable": self.is_reachable,
            "discovered_at": self.discovered_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
            "last_probed_at": self.last_probed_at.isoformat() if self.last_probed_at else None,
            "reachable_until": self.reachable_until.isoformat() if self.reachable_until else None,
            "probe_count": self.probe_count,
            "consecutive_failures": self.consecutive_failures,
            "age_seconds": self.age_seconds,
            "idle_seconds": self.idle_seconds,
            "metadata": self.metadata
        }


@dataclass
class NeighborDiscoveryConfig:
    """ND configuration parameters"""

    # Timing parameters (RFC 4861 recommended)
    reachable_time_ms: int = 30000  # 30 seconds
    retrans_timer_ms: int = 1000    # 1 second
    delay_first_probe_time_ms: int = 5000  # 5 seconds
    max_unicast_probes: int = 3
    max_multicast_probes: int = 3

    # ASI-specific
    discovery_interval_ms: int = 10000  # Periodic discovery every 10s
    stale_timeout_ms: int = 60000       # Consider stale after 60s
    cleanup_interval_ms: int = 30000    # Cleanup every 30s
    max_neighbors: int = 256            # Max neighbor cache size

    # Network settings
    overlay_prefix: str = "fd00:a510:0"
    multicast_group: str = "ff02::1"    # All-nodes multicast

    # Agent identification
    local_agent_id: Optional[str] = None
    local_agent_name: Optional[str] = None
    local_router_id: Optional[str] = None


class NeighborDiscoveryProtocol:
    """
    IPv6 Neighbor Discovery Protocol for ASI Overlay

    Implements neighbor discovery and maintenance for the ASI agent mesh.
    Uses ICMPv6 NS/NA messages over the IPv6 overlay network.
    """

    def __init__(self, config: Optional[NeighborDiscoveryConfig] = None):
        """
        Initialize ND protocol

        Args:
            config: ND configuration parameters
        """
        self.config = config or NeighborDiscoveryConfig()
        self.logger = logging.getLogger("NeighborDiscovery")

        # Neighbor cache: IPv6 address -> NeighborEntry
        self._neighbors: Dict[str, NeighborEntry] = {}

        # Local addresses
        self._local_ipv6: Optional[str] = None

        # Event listeners
        self._listeners: List[Callable] = []

        # Background tasks
        self._running = False
        self._discovery_task: Optional[asyncio.Task] = None
        self._maintenance_task: Optional[asyncio.Task] = None

        # Socket for ICMPv6 (will be created on start)
        self._socket: Optional[socket.socket] = None

    def set_local_address(self, ipv6_address: str) -> None:
        """Set local IPv6 overlay address"""
        # Strip prefix length if present
        addr = ipv6_address.split('/')[0]
        self._local_ipv6 = addr
        self.logger.info(f"Local IPv6 overlay address: {addr}")

    async def start(self) -> None:
        """Start ND protocol"""
        if self._running:
            return

        self._running = True
        self.logger.info("Starting IPv6 Neighbor Discovery protocol")

        # Create ICMPv6 socket (requires privileges)
        try:
            self._socket = socket.socket(
                socket.AF_INET6,
                socket.SOCK_RAW,
                socket.IPPROTO_ICMPV6
            )
            self._socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, 255)
            self._socket.setblocking(False)
            self.logger.info("ICMPv6 raw socket created")
        except PermissionError:
            self.logger.warning(
                "Cannot create raw ICMPv6 socket (requires root). "
                "Falling back to simulated ND via TCP."
            )
            self._socket = None
        except Exception as e:
            self.logger.warning(f"ICMPv6 socket error: {e}. Using simulated ND.")
            self._socket = None

        # Start background tasks
        self._discovery_task = asyncio.create_task(self._discovery_loop())
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())

        self.logger.info("Neighbor Discovery started")

    async def stop(self) -> None:
        """Stop ND protocol"""
        if not self._running:
            return

        self._running = False

        # Cancel background tasks
        if self._discovery_task:
            self._discovery_task.cancel()
            try:
                await self._discovery_task
            except asyncio.CancelledError:
                pass

        if self._maintenance_task:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass

        # Close socket
        if self._socket:
            self._socket.close()
            self._socket = None

        self.logger.info("Neighbor Discovery stopped")

    async def _discovery_loop(self) -> None:
        """Periodic neighbor discovery"""
        while self._running:
            try:
                await self._send_multicast_probe()
                await asyncio.sleep(self.config.discovery_interval_ms / 1000)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Discovery loop error: {e}")
                await asyncio.sleep(1)

    async def _maintenance_loop(self) -> None:
        """Neighbor cache maintenance"""
        while self._running:
            try:
                await self._maintain_cache()
                await asyncio.sleep(self.config.cleanup_interval_ms / 1000)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Maintenance loop error: {e}")
                await asyncio.sleep(1)

    async def _send_multicast_probe(self) -> None:
        """Send multicast Neighbor Solicitation to all-nodes"""
        if not self._local_ipv6:
            return

        # Build NS message
        ns_msg = self._build_neighbor_solicitation(self.config.multicast_group)

        if self._socket:
            try:
                # Send to all-nodes multicast
                dest = (self.config.multicast_group, 0, 0, 0)
                self._socket.sendto(ns_msg, dest)
                self.logger.debug(f"Sent multicast NS to {self.config.multicast_group}")
            except Exception as e:
                self.logger.debug(f"Multicast NS send failed: {e}")
        else:
            # Simulated ND via TCP (for non-root operation)
            await self._simulated_multicast_discovery()

    async def _simulated_multicast_discovery(self) -> None:
        """
        Simulated ND when raw sockets aren't available

        Uses TCP probes to known ASI overlay addresses in the network
        """
        if not self._local_ipv6:
            return

        # Extract network prefix from local address
        # Format: fd00:a510:0:NETWORK_ID::AGENT_INDEX
        try:
            parts = self._local_ipv6.split('::')
            if len(parts) == 2:
                prefix = parts[0]  # fd00:a510:0:NETWORK_ID
                local_index = int(parts[1]) if parts[1] else 1

                # Probe other potential agents (1-64)
                for agent_idx in range(1, 65):
                    if agent_idx == local_index:
                        continue

                    target_ipv6 = f"{prefix}::{agent_idx}"

                    # Only probe if not already known or stale
                    neighbor = self._neighbors.get(target_ipv6)
                    if neighbor and neighbor.is_reachable:
                        continue

                    # Probe via TCP (port 8888 is agent webui)
                    reachable = await self._tcp_probe(target_ipv6, 8888)
                    if reachable:
                        self._add_or_update_neighbor(target_ipv6)

        except Exception as e:
            self.logger.debug(f"Simulated discovery error: {e}")

    async def _tcp_probe(self, ipv6_address: str, port: int) -> bool:
        """Probe IPv6 address via TCP connection"""
        try:
            # Use asyncio for non-blocking connect
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ipv6_address, port),
                timeout=1.0
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    async def _maintain_cache(self) -> None:
        """Maintain neighbor cache (NUD, cleanup)"""
        now = datetime.now()
        stale_threshold = timedelta(milliseconds=self.config.stale_timeout_ms)

        to_remove = []

        for ipv6, neighbor in self._neighbors.items():
            # Check reachable timeout
            if neighbor.state == NeighborState.REACHABLE:
                if neighbor.reachable_until and now > neighbor.reachable_until:
                    neighbor.mark_stale()
                    self._notify("neighbor_stale", neighbor)

            # Check stale entries for removal
            elif neighbor.state == NeighborState.STALE:
                if now - neighbor.last_seen_at > stale_threshold:
                    # Attempt unicast probe before removal
                    neighbor.mark_probe()
                    await self._send_unicast_probe(ipv6)

            # Check failed probes
            elif neighbor.state == NeighborState.PROBE:
                if neighbor.probe_count >= self.config.max_unicast_probes:
                    to_remove.append(ipv6)

        # Remove failed neighbors
        for ipv6 in to_remove:
            neighbor = self._neighbors.pop(ipv6, None)
            if neighbor:
                self._notify("neighbor_removed", neighbor)
                self.logger.info(f"Removed unreachable neighbor: {ipv6}")

    async def _send_unicast_probe(self, target_ipv6: str) -> None:
        """Send unicast NS to specific neighbor"""
        ns_msg = self._build_neighbor_solicitation(target_ipv6)

        if self._socket:
            try:
                dest = (target_ipv6, 0, 0, 0)
                self._socket.sendto(ns_msg, dest)
                self.logger.debug(f"Sent unicast NS to {target_ipv6}")
            except Exception as e:
                self.logger.debug(f"Unicast NS failed to {target_ipv6}: {e}")
        else:
            # Simulated probe
            reachable = await self._tcp_probe(target_ipv6, 8888)
            neighbor = self._neighbors.get(target_ipv6)
            if neighbor:
                if reachable:
                    neighbor.mark_reachable()
                else:
                    neighbor.mark_failed()

    def _build_neighbor_solicitation(self, target: str) -> bytes:
        """Build ICMPv6 Neighbor Solicitation message"""
        # ICMPv6 Header: Type (1) + Code (1) + Checksum (2) + Reserved (4)
        # Target Address (16)
        # Options: Source Link-Layer Address (optional)

        icmp_type = ICMPv6Type.NEIGHBOR_SOLICITATION
        icmp_code = 0

        # Target address as bytes
        try:
            target_bytes = ipaddress.IPv6Address(target).packed
        except Exception:
            target_bytes = b'\x00' * 16

        # Build message (checksum will be handled by kernel)
        msg = struct.pack('!BBHI', icmp_type, icmp_code, 0, 0)  # 8 bytes
        msg += target_bytes  # 16 bytes

        return msg

    def _build_neighbor_advertisement(self, target: str, solicited: bool = True) -> bytes:
        """Build ICMPv6 Neighbor Advertisement message"""
        icmp_type = ICMPv6Type.NEIGHBOR_ADVERTISEMENT
        icmp_code = 0

        # Flags: R=Router, S=Solicited, O=Override
        flags = 0
        if solicited:
            flags |= 0x40000000  # Solicited flag
        flags |= 0x20000000  # Override flag

        try:
            target_bytes = ipaddress.IPv6Address(target).packed
        except Exception:
            target_bytes = b'\x00' * 16

        msg = struct.pack('!BBHI', icmp_type, icmp_code, 0, flags)
        msg += target_bytes

        return msg

    def _add_or_update_neighbor(
        self,
        ipv6_address: str,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        router_id: Optional[str] = None,
        docker_ip: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> NeighborEntry:
        """Add or update neighbor in cache"""
        # Strip prefix length
        ipv6_addr = ipv6_address.split('/')[0]

        if ipv6_addr in self._neighbors:
            neighbor = self._neighbors[ipv6_addr]
            neighbor.mark_reachable(self.config.reachable_time_ms // 1000)

            # Update optional fields if provided
            if agent_id:
                neighbor.agent_id = agent_id
            if agent_name:
                neighbor.agent_name = agent_name
            if router_id:
                neighbor.router_id = router_id
            if docker_ip:
                neighbor.docker_ip = docker_ip
            if metadata:
                neighbor.metadata.update(metadata)

            self._notify("neighbor_updated", neighbor)
        else:
            neighbor = NeighborEntry(
                ipv6_address=ipv6_addr,
                agent_id=agent_id,
                agent_name=agent_name,
                router_id=router_id,
                docker_ip=docker_ip,
                state=NeighborState.REACHABLE,
                metadata=metadata or {}
            )
            neighbor.reachable_until = datetime.now() + timedelta(
                milliseconds=self.config.reachable_time_ms
            )

            self._neighbors[ipv6_addr] = neighbor
            self._notify("neighbor_discovered", neighbor)
            self.logger.info(f"Discovered new neighbor: {ipv6_addr} (agent={agent_name})")

        return neighbor

    def handle_ns(
        self,
        source_ipv6: str,
        target_ipv6: str,
        source_info: Optional[Dict[str, Any]] = None
    ) -> Optional[bytes]:
        """
        Handle incoming Neighbor Solicitation

        Args:
            source_ipv6: Source IPv6 address of NS
            target_ipv6: Target address being solicited
            source_info: Additional info about source (agent_id, etc.)

        Returns:
            NA response message if we are the target, None otherwise
        """
        # Check if we are the target
        if self._local_ipv6 and target_ipv6.split('/')[0] == self._local_ipv6:
            # Add source as neighbor
            self._add_or_update_neighbor(
                source_ipv6,
                agent_id=source_info.get("agent_id") if source_info else None,
                agent_name=source_info.get("agent_name") if source_info else None,
                router_id=source_info.get("router_id") if source_info else None,
                metadata=source_info
            )

            # Build NA response
            return self._build_neighbor_advertisement(self._local_ipv6, solicited=True)

        return None

    def handle_na(
        self,
        source_ipv6: str,
        target_ipv6: str,
        source_info: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Handle incoming Neighbor Advertisement

        Args:
            source_ipv6: Source IPv6 address of NA
            target_ipv6: Address being advertised
            source_info: Additional info about source
        """
        self._add_or_update_neighbor(
            target_ipv6,
            agent_id=source_info.get("agent_id") if source_info else None,
            agent_name=source_info.get("agent_name") if source_info else None,
            router_id=source_info.get("router_id") if source_info else None,
            metadata=source_info
        )

    def get_neighbors(self, reachable_only: bool = False) -> List[NeighborEntry]:
        """Get all neighbors"""
        neighbors = list(self._neighbors.values())
        if reachable_only:
            neighbors = [n for n in neighbors if n.is_reachable]
        return neighbors

    def get_neighbor(self, ipv6_address: str) -> Optional[NeighborEntry]:
        """Get specific neighbor by IPv6 address"""
        addr = ipv6_address.split('/')[0]
        return self._neighbors.get(addr)

    def get_neighbor_by_agent(self, agent_id: str) -> Optional[NeighborEntry]:
        """Get neighbor by agent ID"""
        for neighbor in self._neighbors.values():
            if neighbor.agent_id == agent_id:
                return neighbor
        return None

    def add_listener(self, callback: Callable[[str, NeighborEntry], None]) -> None:
        """Add event listener for neighbor events"""
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable) -> None:
        """Remove event listener"""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self, event: str, neighbor: NeighborEntry) -> None:
        """Notify listeners of neighbor event"""
        for listener in self._listeners:
            try:
                listener(event, neighbor)
            except Exception as e:
                self.logger.debug(f"Listener error: {e}")

    def get_statistics(self) -> dict:
        """Get ND statistics"""
        by_state = {}
        for state in NeighborState:
            by_state[state.value] = sum(
                1 for n in self._neighbors.values() if n.state == state
            )

        return {
            "total_neighbors": len(self._neighbors),
            "reachable_neighbors": sum(1 for n in self._neighbors.values() if n.is_reachable),
            "by_state": by_state,
            "local_ipv6": self._local_ipv6,
            "running": self._running
        }

    def to_dict(self) -> dict:
        """Get full state as dict"""
        return {
            "config": {
                "reachable_time_ms": self.config.reachable_time_ms,
                "discovery_interval_ms": self.config.discovery_interval_ms,
                "overlay_prefix": self.config.overlay_prefix,
                "local_agent_id": self.config.local_agent_id,
                "local_agent_name": self.config.local_agent_name
            },
            "local_ipv6": self._local_ipv6,
            "running": self._running,
            "statistics": self.get_statistics(),
            "neighbors": [n.to_dict() for n in self._neighbors.values()]
        }


# Global ND instance
_nd_protocol: Optional[NeighborDiscoveryProtocol] = None


def get_neighbor_discovery() -> NeighborDiscoveryProtocol:
    """Get or create global ND protocol instance"""
    global _nd_protocol
    if _nd_protocol is None:
        _nd_protocol = NeighborDiscoveryProtocol()
    return _nd_protocol


async def start_neighbor_discovery(
    local_ipv6: str,
    agent_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    router_id: Optional[str] = None
) -> NeighborDiscoveryProtocol:
    """Start ND protocol with local agent info"""
    nd = get_neighbor_discovery()

    # Configure
    nd.config.local_agent_id = agent_id
    nd.config.local_agent_name = agent_name
    nd.config.local_router_id = router_id
    nd.set_local_address(local_ipv6)

    # Start
    await nd.start()
    return nd


async def stop_neighbor_discovery() -> None:
    """Stop ND protocol"""
    nd = get_neighbor_discovery()
    await nd.stop()


def get_discovered_neighbors(reachable_only: bool = True) -> List[Dict[str, Any]]:
    """Get discovered neighbors as list of dicts"""
    nd = get_neighbor_discovery()
    return [n.to_dict() for n in nd.get_neighbors(reachable_only)]
