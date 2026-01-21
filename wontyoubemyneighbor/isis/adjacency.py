"""
IS-IS Adjacency Management

Handles neighbor discovery, adjacency state machine, and DIS election
for IS-IS protocol operation.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime


class AdjacencyState(Enum):
    """IS-IS adjacency states (3-state model per RFC 1195)"""
    DOWN = 0         # Initial state, no adjacency
    INITIALIZING = 1 # Hellos received but not confirmed bidirectional
    UP = 2           # Fully established adjacency


class CircuitType(Enum):
    """IS-IS circuit (interface) types"""
    BROADCAST = 1
    POINT_TO_POINT = 2


@dataclass
class ISISAdjacency:
    """
    Represents an IS-IS adjacency with a neighbor router.

    Attributes:
        system_id: Neighbor's 6-byte system ID (as hex string)
        interface: Local interface name
        level: Adjacency level (1, 2, or 3 for L1/L2)
        state: Current adjacency state
        circuit_type: Type of circuit (broadcast or P2P)
        priority: Neighbor's DIS priority (broadcast only)
        lan_id: LAN ID on broadcast networks
        area_addresses: Neighbor's configured area addresses
        ip_addresses: Neighbor's IP addresses
        hold_time: Hold time from neighbor's hello
        last_hello: Timestamp of last hello received
    """
    system_id: str
    interface: str
    level: int = 3  # Default to L1/L2
    state: AdjacencyState = AdjacencyState.DOWN
    circuit_type: CircuitType = CircuitType.BROADCAST
    priority: int = 64
    lan_id: Optional[str] = None
    area_addresses: List[str] = field(default_factory=list)
    ip_addresses: List[str] = field(default_factory=list)
    hold_time: int = 30
    last_hello: Optional[datetime] = None

    # Statistics
    hellos_received: int = 0
    hellos_sent: int = 0
    state_changes: int = 0
    uptime: Optional[datetime] = None

    def __post_init__(self):
        """Initialize state tracking"""
        self._state_history: List[tuple] = []

    def get_state_name(self) -> str:
        """Get human-readable state name"""
        return self.state.name

    def is_up(self) -> bool:
        """Check if adjacency is fully established"""
        return self.state == AdjacencyState.UP

    def transition_to(self, new_state: AdjacencyState, reason: str = "") -> None:
        """
        Transition to a new adjacency state.

        Args:
            new_state: New state to transition to
            reason: Reason for state change (for logging)
        """
        old_state = self.state
        self.state = new_state
        self.state_changes += 1

        # Record state change
        self._state_history.append((
            datetime.now(),
            old_state,
            new_state,
            reason
        ))

        # Track uptime
        if new_state == AdjacencyState.UP:
            self.uptime = datetime.now()
        elif old_state == AdjacencyState.UP:
            self.uptime = None

    def get_uptime_seconds(self) -> int:
        """Get adjacency uptime in seconds"""
        if self.uptime is None:
            return 0
        return int((datetime.now() - self.uptime).total_seconds())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "system_id": self.system_id,
            "interface": self.interface,
            "level": self.level,
            "state": self.state.name,
            "circuit_type": self.circuit_type.name,
            "priority": self.priority,
            "lan_id": self.lan_id,
            "area_addresses": self.area_addresses,
            "ip_addresses": self.ip_addresses,
            "hold_time": self.hold_time,
            "hellos_received": self.hellos_received,
            "hellos_sent": self.hellos_sent,
            "state_changes": self.state_changes,
            "uptime_seconds": self.get_uptime_seconds(),
        }


class ISISAdjacencyManager:
    """
    Manages IS-IS adjacencies for a router.

    Handles:
    - Adjacency state machine transitions
    - Hold timer management
    - DIS (Designated Intermediate System) election
    - Adjacency timeout detection
    """

    def __init__(
        self,
        system_id: str,
        area_addresses: List[str],
        level: int = 3,  # L1/L2 by default
        hello_interval: int = 10,
        hello_multiplier: int = 3,
    ):
        """
        Initialize adjacency manager.

        Args:
            system_id: Local router's system ID
            area_addresses: Local router's area addresses
            level: Router's IS-IS level configuration
            hello_interval: Hello transmission interval
            hello_multiplier: Hold time multiplier
        """
        self.system_id = system_id
        self.area_addresses = area_addresses
        self.level = level
        self.hello_interval = hello_interval
        self.hello_multiplier = hello_multiplier

        # Adjacency storage: {interface: {system_id: ISISAdjacency}}
        self._adjacencies: Dict[str, Dict[str, ISISAdjacency]] = {}

        # DIS per interface per level
        self._dis: Dict[str, Dict[int, str]] = {}  # {interface: {level: system_id}}

        # Callbacks
        self.on_adjacency_up: Optional[Callable[[ISISAdjacency], None]] = None
        self.on_adjacency_down: Optional[Callable[[ISISAdjacency], None]] = None
        self.on_dis_change: Optional[Callable[[str, int, str], None]] = None

        # Timer tasks
        self._hold_timer_task: Optional[asyncio.Task] = None

        self.logger = logging.getLogger("ISISAdjacency")

    def get_adjacencies(self, interface: Optional[str] = None, level: Optional[int] = None) -> List[ISISAdjacency]:
        """
        Get adjacencies, optionally filtered by interface and/or level.

        Args:
            interface: Filter by interface name
            level: Filter by level (1, 2, or 3)

        Returns:
            List of matching adjacencies
        """
        result = []

        interfaces = [interface] if interface else self._adjacencies.keys()

        for iface in interfaces:
            if iface not in self._adjacencies:
                continue
            for adj in self._adjacencies[iface].values():
                if level is None or adj.level == level or adj.level == 3:
                    result.append(adj)

        return result

    def get_adjacency(self, interface: str, system_id: str) -> Optional[ISISAdjacency]:
        """Get specific adjacency by interface and system ID"""
        if interface not in self._adjacencies:
            return None
        return self._adjacencies[interface].get(system_id)

    def process_hello(
        self,
        interface: str,
        system_id: str,
        level: int,
        circuit_type: CircuitType,
        priority: int,
        area_addresses: List[str],
        ip_addresses: List[str],
        hold_time: int,
        lan_id: Optional[str] = None,
        neighbors_in_hello: Optional[List[str]] = None,
    ) -> Optional[ISISAdjacency]:
        """
        Process a received IS-IS Hello (IIH) PDU.

        Args:
            interface: Interface hello was received on
            system_id: Sender's system ID
            level: Level of the hello (1, 2)
            circuit_type: Circuit type (broadcast/P2P)
            priority: DIS priority (broadcast only)
            area_addresses: Sender's area addresses
            ip_addresses: Sender's IP addresses
            hold_time: Hold time value
            lan_id: LAN ID (broadcast only)
            neighbors_in_hello: List of neighbors sender sees (for 3-way handshake)

        Returns:
            Updated ISISAdjacency or None if rejected
        """
        # Check level compatibility
        if not self._check_level_compatibility(level):
            self.logger.debug(f"Level incompatible with {system_id}: they={level}, we={self.level}")
            return None

        # Check area compatibility for L1
        if level == 1 and not self._check_area_compatibility(area_addresses):
            self.logger.debug(f"Area mismatch with {system_id} for L1 adjacency")
            return None

        # Get or create adjacency
        if interface not in self._adjacencies:
            self._adjacencies[interface] = {}

        adj = self._adjacencies[interface].get(system_id)

        if adj is None:
            # New adjacency
            adj = ISISAdjacency(
                system_id=system_id,
                interface=interface,
                level=level,
                circuit_type=circuit_type,
                priority=priority,
                area_addresses=area_addresses,
                ip_addresses=ip_addresses,
                hold_time=hold_time,
                lan_id=lan_id,
            )
            self._adjacencies[interface][system_id] = adj
            self.logger.info(f"New neighbor discovered: {system_id} on {interface}")

        # Update adjacency info
        adj.area_addresses = area_addresses
        adj.ip_addresses = ip_addresses
        adj.hold_time = hold_time
        adj.priority = priority
        adj.lan_id = lan_id
        adj.last_hello = datetime.now()
        adj.hellos_received += 1

        # Process adjacency state machine
        old_state = adj.state

        if adj.state == AdjacencyState.DOWN:
            # Transition to Initializing
            adj.transition_to(AdjacencyState.INITIALIZING, "Hello received")

        elif adj.state == AdjacencyState.INITIALIZING:
            # Check if neighbor sees us (3-way handshake)
            if neighbors_in_hello and self.system_id in neighbors_in_hello:
                adj.transition_to(AdjacencyState.UP, "3-way handshake complete")
                self.logger.info(f"Adjacency UP with {system_id} on {interface} (Level {level})")
                if self.on_adjacency_up:
                    self.on_adjacency_up(adj)
            # On P2P links, also go UP if we don't have neighbor list
            elif circuit_type == CircuitType.POINT_TO_POINT and neighbors_in_hello is None:
                adj.transition_to(AdjacencyState.UP, "P2P hello exchange complete")
                self.logger.info(f"Adjacency UP with {system_id} on {interface} (Level {level})")
                if self.on_adjacency_up:
                    self.on_adjacency_up(adj)

        elif adj.state == AdjacencyState.UP:
            # Adjacency already up, just refresh
            pass

        # DIS election on broadcast networks
        if circuit_type == CircuitType.BROADCAST and adj.state == AdjacencyState.UP:
            self._run_dis_election(interface, level)

        return adj

    def _check_level_compatibility(self, neighbor_level: int) -> bool:
        """
        Check if neighbor's level is compatible with ours.

        Level compatibility matrix:
        - L1 router can only form adjacency with L1 or L1/L2 routers
        - L2 router can only form adjacency with L2 or L1/L2 routers
        - L1/L2 router can form adjacency with any level
        """
        if self.level == 3:  # We are L1/L2
            return True
        if neighbor_level == 3:  # Neighbor is L1/L2
            return True
        return self.level == neighbor_level

    def _check_area_compatibility(self, neighbor_areas: List[str]) -> bool:
        """
        Check if neighbor's areas overlap with ours.
        Required for L1 adjacencies.
        """
        for our_area in self.area_addresses:
            if our_area in neighbor_areas:
                return True
        return False

    def _run_dis_election(self, interface: str, level: int) -> None:
        """
        Run DIS election for a broadcast interface.

        DIS is elected based on:
        1. Highest priority wins
        2. On tie, highest system ID wins
        3. DIS can be preempted (unlike OSPF DR)
        """
        candidates = []

        # Add ourselves
        candidates.append((
            64,  # Our priority (default)
            self.system_id,
            True  # Is local
        ))

        # Add UP neighbors
        for adj in self.get_adjacencies(interface, level):
            if adj.is_up():
                candidates.append((
                    adj.priority,
                    adj.system_id,
                    False
                ))

        if not candidates:
            return

        # Sort by priority (desc), then system_id (desc)
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)

        new_dis = candidates[0][1]

        # Check if DIS changed
        current_dis = self._dis.get(interface, {}).get(level)

        if current_dis != new_dis:
            if interface not in self._dis:
                self._dis[interface] = {}
            self._dis[interface][level] = new_dis

            self.logger.info(f"DIS elected on {interface} L{level}: {new_dis}")

            if self.on_dis_change:
                self.on_dis_change(interface, level, new_dis)

    def get_dis(self, interface: str, level: int) -> Optional[str]:
        """Get current DIS for interface/level"""
        return self._dis.get(interface, {}).get(level)

    def is_dis(self, interface: str, level: int) -> bool:
        """Check if we are DIS for interface/level"""
        return self.get_dis(interface, level) == self.system_id

    async def start_hold_timer(self) -> None:
        """Start the hold timer check task"""
        self._hold_timer_task = asyncio.create_task(self._hold_timer_loop())

    async def stop(self) -> None:
        """Stop adjacency manager"""
        if self._hold_timer_task:
            self._hold_timer_task.cancel()
            try:
                await self._hold_timer_task
            except asyncio.CancelledError:
                pass

    async def _hold_timer_loop(self) -> None:
        """Check for expired adjacencies"""
        while True:
            try:
                await asyncio.sleep(1)  # Check every second
                self._check_hold_timers()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in hold timer loop: {e}")

    def _check_hold_timers(self) -> None:
        """Check all adjacencies for hold timer expiry"""
        now = datetime.now()

        for interface, adjacencies in list(self._adjacencies.items()):
            for system_id, adj in list(adjacencies.items()):
                if adj.last_hello is None:
                    continue

                elapsed = (now - adj.last_hello).total_seconds()

                if elapsed > adj.hold_time:
                    # Hold timer expired - adjacency down
                    self.logger.warning(f"Hold timer expired for {system_id} on {interface}")
                    old_state = adj.state
                    adj.transition_to(AdjacencyState.DOWN, "Hold timer expired")

                    if old_state == AdjacencyState.UP and self.on_adjacency_down:
                        self.on_adjacency_down(adj)

                    # Remove adjacency
                    del self._adjacencies[interface][system_id]

                    # Re-run DIS election if needed
                    if adj.circuit_type == CircuitType.BROADCAST:
                        self._run_dis_election(interface, adj.level)

    def get_statistics(self) -> Dict[str, Any]:
        """Get adjacency manager statistics"""
        total = 0
        up = 0
        by_level = {1: 0, 2: 0}

        for adjacencies in self._adjacencies.values():
            for adj in adjacencies.values():
                total += 1
                if adj.is_up():
                    up += 1
                if adj.level in by_level:
                    by_level[adj.level] += 1
                elif adj.level == 3:
                    by_level[1] += 1
                    by_level[2] += 1

        return {
            "total_adjacencies": total,
            "up_adjacencies": up,
            "level_1_adjacencies": by_level[1],
            "level_2_adjacencies": by_level[2],
            "dis_interfaces": {
                iface: {f"L{level}": dis for level, dis in levels.items()}
                for iface, levels in self._dis.items()
            }
        }
