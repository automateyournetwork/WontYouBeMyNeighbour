"""
LACP - Link Aggregation Control Protocol (IEEE 802.3ad / 802.1AX)

Provides link aggregation (bonding/port-channeling) capabilities for agents.
Allows bundling multiple physical interfaces into a single logical interface
for increased bandwidth and redundancy.

Features:
- Create port-channels/LAGs (Link Aggregation Groups)
- LACP mode selection (active/passive)
- Load balancing algorithms (layer2, layer3, layer3+4)
- Member interface management
- LACP state machine per port
- Partner information tracking
"""

import asyncio
import logging
import time
import subprocess
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from enum import Enum
from datetime import datetime

logger = logging.getLogger("LACP")

# Singleton LACP manager instance
_lacp_manager: Optional["LACPManager"] = None


class LACPMode(Enum):
    """LACP negotiation mode"""
    ACTIVE = "active"    # Actively send LACPDU
    PASSIVE = "passive"  # Only respond to LACPDU
    ON = "on"           # Force aggregation without LACP (static)


class LACPState(Enum):
    """LACP port state flags (IEEE 802.3ad)"""
    LACP_ACTIVITY = 0x01      # Active (1) or Passive (0)
    LACP_TIMEOUT = 0x02       # Short (1) or Long (0) timeout
    AGGREGATION = 0x04        # Aggregatable (1) or Individual (0)
    SYNCHRONIZATION = 0x08   # In sync (1) or out of sync (0)
    COLLECTING = 0x10        # Collecting frames (1)
    DISTRIBUTING = 0x20      # Distributing frames (1)
    DEFAULTED = 0x40         # Using default partner info (1)
    EXPIRED = 0x80           # Expired (1)


class LACPPortState(Enum):
    """High-level LACP port state"""
    DETACHED = "detached"
    WAITING = "waiting"
    ATTACHED = "attached"
    COLLECTING = "collecting"
    DISTRIBUTING = "distributing"
    ACTIVE = "active"  # Both collecting and distributing


class LoadBalanceAlgorithm(Enum):
    """Load balancing hash algorithm for LAG"""
    LAYER2 = "layer2"           # MAC address based
    LAYER3 = "layer3"           # IP address based
    LAYER34 = "layer3+4"        # IP + port based
    LAYER2_3 = "layer2+3"       # MAC + IP based
    ENCAP2_3 = "encap2+3"       # Encapsulation + MAC + IP
    ENCAP3_4 = "encap3+4"       # Encapsulation + IP + port


@dataclass
class LACPPartnerInfo:
    """Information about the LACP partner (remote side)"""
    system_id: str = ""         # Partner's system MAC
    system_priority: int = 32768
    key: int = 0
    port_id: int = 0
    port_priority: int = 32768
    state: int = 0              # LACP state flags bitmap

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system_id": self.system_id,
            "system_priority": self.system_priority,
            "key": self.key,
            "port_id": self.port_id,
            "port_priority": self.port_priority,
            "state": self.state,
            "state_flags": self._decode_state_flags()
        }

    def _decode_state_flags(self) -> List[str]:
        """Decode state bitmap to flag names"""
        flags = []
        for flag in LACPState:
            if self.state & flag.value:
                flags.append(flag.name)
        return flags


@dataclass
class LACPMemberPort:
    """A member port in a LAG"""
    interface: str
    port_id: int = 0
    port_priority: int = 32768
    state: LACPPortState = LACPPortState.DETACHED
    lacp_state: int = 0  # LACP state flags bitmap
    partner: Optional[LACPPartnerInfo] = None

    # Statistics
    lacpdu_sent: int = 0
    lacpdu_received: int = 0
    lacpdu_errors: int = 0

    # Timing
    last_lacpdu_sent: float = 0
    last_lacpdu_received: float = 0

    # Selection state
    selected: bool = False
    standby: bool = False

    def is_active(self) -> bool:
        """Check if port is actively forwarding"""
        return self.state == LACPPortState.ACTIVE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interface": self.interface,
            "port_id": self.port_id,
            "port_priority": self.port_priority,
            "state": self.state.value,
            "lacp_state": self.lacp_state,
            "lacp_state_flags": self._decode_lacp_state(),
            "partner": self.partner.to_dict() if self.partner else None,
            "selected": self.selected,
            "standby": self.standby,
            "lacpdu_sent": self.lacpdu_sent,
            "lacpdu_received": self.lacpdu_received,
            "lacpdu_errors": self.lacpdu_errors,
            "last_lacpdu_sent": datetime.fromtimestamp(self.last_lacpdu_sent).isoformat() if self.last_lacpdu_sent else None,
            "last_lacpdu_received": datetime.fromtimestamp(self.last_lacpdu_received).isoformat() if self.last_lacpdu_received else None
        }

    def _decode_lacp_state(self) -> List[str]:
        """Decode LACP state bitmap to flag names"""
        flags = []
        for flag in LACPState:
            if self.lacp_state & flag.value:
                flags.append(flag.name)
        return flags


@dataclass
class LinkAggregationGroup:
    """
    A Link Aggregation Group (LAG) / Port-Channel / Bond.

    Bundles multiple physical interfaces into a single logical interface.
    """
    name: str  # e.g., "bond0", "port-channel1", "ae0"
    lag_id: int = 0

    # Configuration
    mode: LACPMode = LACPMode.ACTIVE
    load_balance: LoadBalanceAlgorithm = LoadBalanceAlgorithm.LAYER34
    min_links: int = 1  # Minimum active links for LAG to be up
    max_links: int = 8  # Maximum members

    # LACP parameters
    system_id: str = ""  # Local system MAC
    system_priority: int = 32768
    admin_key: int = 0
    lacp_rate: str = "slow"  # "slow" (30s) or "fast" (1s)

    # Member ports
    members: Dict[str, LACPMemberPort] = field(default_factory=dict)

    # State
    oper_state: str = "down"  # "up" or "down"
    active_members: int = 0

    # IP addressing (if configured)
    ipv4_addresses: List[str] = field(default_factory=list)
    ipv6_addresses: List[str] = field(default_factory=list)

    # Statistics (aggregate)
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    tx_packets: int = 0

    def add_member(self, interface: str, port_priority: int = 32768) -> LACPMemberPort:
        """Add a member interface to the LAG"""
        if len(self.members) >= self.max_links:
            raise ValueError(f"LAG {self.name} already has maximum {self.max_links} members")

        port_id = len(self.members) + 1
        member = LACPMemberPort(
            interface=interface,
            port_id=port_id,
            port_priority=port_priority
        )
        self.members[interface] = member
        logger.info(f"Added member {interface} to LAG {self.name}")
        return member

    def remove_member(self, interface: str) -> bool:
        """Remove a member interface from the LAG"""
        if interface in self.members:
            del self.members[interface]
            logger.info(f"Removed member {interface} from LAG {self.name}")
            return True
        return False

    def get_active_members(self) -> List[LACPMemberPort]:
        """Get list of active member ports"""
        return [m for m in self.members.values() if m.is_active()]

    def update_state(self):
        """Update LAG operational state based on member states"""
        active = self.get_active_members()
        self.active_members = len(active)
        self.oper_state = "up" if self.active_members >= self.min_links else "down"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "lag_id": self.lag_id,
            "mode": self.mode.value,
            "load_balance": self.load_balance.value,
            "min_links": self.min_links,
            "max_links": self.max_links,
            "system_id": self.system_id,
            "system_priority": self.system_priority,
            "admin_key": self.admin_key,
            "lacp_rate": self.lacp_rate,
            "oper_state": self.oper_state,
            "active_members": self.active_members,
            "total_members": len(self.members),
            "members": {k: v.to_dict() for k, v in self.members.items()},
            "ipv4_addresses": self.ipv4_addresses,
            "ipv6_addresses": self.ipv6_addresses,
            "statistics": {
                "rx_bytes": self.rx_bytes,
                "tx_bytes": self.tx_bytes,
                "rx_packets": self.rx_packets,
                "tx_packets": self.tx_packets
            }
        }


class LACPManager:
    """
    Manages all LAGs for an agent.

    Handles:
    - LAG creation and deletion
    - Member interface management
    - LACP state machine
    - Statistics collection
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.lags: Dict[str, LinkAggregationGroup] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        # Global LACP settings
        self.system_id = ""  # Will be set from agent's MAC
        self.system_priority = 32768

    async def start(self):
        """Start the LACP manager"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"LACP manager started for agent {self.agent_id}")

    async def stop(self):
        """Stop the LACP manager"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"LACP manager stopped for agent {self.agent_id}")

    async def _run(self):
        """Main manager loop"""
        while self._running:
            try:
                # Process LACP state machines
                await self._process_lacp()

                # Update LAG states
                for lag in self.lags.values():
                    lag.update_state()

                # Collect statistics
                await self._collect_statistics()

                # LACP fast rate is 1 second, slow is 30 seconds
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"LACP manager error: {e}")
                await asyncio.sleep(5)

    async def _process_lacp(self):
        """Process LACP state machines for all LAGs"""
        for lag in self.lags.values():
            if lag.mode == LACPMode.ON:
                # Static aggregation - no LACP
                continue

            for member in lag.members.values():
                await self._process_member_lacp(lag, member)

    async def _process_member_lacp(self, lag: LinkAggregationGroup, member: LACPMemberPort):
        """Process LACP state machine for a member port"""
        # Simplified LACP state machine
        now = time.time()

        # Check for timeout
        timeout = 3 if lag.lacp_rate == "fast" else 90  # 3x LACPDU interval
        if member.last_lacpdu_received and now - member.last_lacpdu_received > timeout:
            member.state = LACPPortState.DETACHED
            member.selected = False
            return

        # State transitions based on LACP mode
        if lag.mode == LACPMode.ACTIVE:
            # Active mode - always try to form aggregation
            if member.state == LACPPortState.DETACHED:
                member.state = LACPPortState.WAITING
            elif member.state == LACPPortState.WAITING:
                if member.partner:
                    member.state = LACPPortState.ATTACHED
            elif member.state == LACPPortState.ATTACHED:
                if member.partner and member.partner.state & LACPState.SYNCHRONIZATION.value:
                    member.state = LACPPortState.COLLECTING
            elif member.state == LACPPortState.COLLECTING:
                if member.partner and member.partner.state & LACPState.COLLECTING.value:
                    member.state = LACPPortState.DISTRIBUTING
            elif member.state == LACPPortState.DISTRIBUTING:
                if member.partner and member.partner.state & LACPState.DISTRIBUTING.value:
                    member.state = LACPPortState.ACTIVE
                    member.selected = True

        elif lag.mode == LACPMode.PASSIVE:
            # Passive mode - wait for partner
            if member.partner and member.partner.state & LACPState.LACP_ACTIVITY.value:
                # Partner is active, proceed
                if member.state == LACPPortState.DETACHED:
                    member.state = LACPPortState.ATTACHED
                elif member.state == LACPPortState.ATTACHED:
                    member.state = LACPPortState.ACTIVE
                    member.selected = True

    async def _collect_statistics(self):
        """Collect statistics for all LAGs"""
        # Try to get stats from system
        try:
            for lag_name, lag in self.lags.items():
                result = subprocess.run(
                    ["ip", "-s", "link", "show", lag_name],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    # Parse statistics (simplified)
                    pass
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    def create_lag(
        self,
        name: str,
        mode: LACPMode = LACPMode.ACTIVE,
        load_balance: LoadBalanceAlgorithm = LoadBalanceAlgorithm.LAYER34,
        min_links: int = 1,
        lacp_rate: str = "slow"
    ) -> LinkAggregationGroup:
        """Create a new LAG"""
        if name in self.lags:
            raise ValueError(f"LAG {name} already exists")

        lag = LinkAggregationGroup(
            name=name,
            lag_id=len(self.lags) + 1,
            mode=mode,
            load_balance=load_balance,
            min_links=min_links,
            system_id=self.system_id,
            system_priority=self.system_priority,
            lacp_rate=lacp_rate
        )
        self.lags[name] = lag
        logger.info(f"Created LAG {name} with mode {mode.value}")
        return lag

    def delete_lag(self, name: str) -> bool:
        """Delete a LAG"""
        if name in self.lags:
            del self.lags[name]
            logger.info(f"Deleted LAG {name}")
            return True
        return False

    def get_lag(self, name: str) -> Optional[LinkAggregationGroup]:
        """Get a LAG by name"""
        return self.lags.get(name)

    def list_lags(self) -> List[LinkAggregationGroup]:
        """List all LAGs"""
        return list(self.lags.values())

    def add_member_to_lag(self, lag_name: str, interface: str, port_priority: int = 32768) -> LACPMemberPort:
        """Add a member interface to a LAG"""
        lag = self.lags.get(lag_name)
        if not lag:
            raise ValueError(f"LAG {lag_name} does not exist")
        return lag.add_member(interface, port_priority)

    def remove_member_from_lag(self, lag_name: str, interface: str) -> bool:
        """Remove a member interface from a LAG"""
        lag = self.lags.get(lag_name)
        if not lag:
            return False
        return lag.remove_member(interface)

    def get_statistics(self) -> Dict[str, Any]:
        """Get LACP manager statistics"""
        return {
            "agent_id": self.agent_id,
            "system_id": self.system_id,
            "system_priority": self.system_priority,
            "lag_count": len(self.lags),
            "running": self._running,
            "lags": {name: lag.to_dict() for name, lag in self.lags.items()}
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert LACP state to dictionary"""
        return self.get_statistics()


def get_lacp_manager(agent_id: str = "local") -> LACPManager:
    """Get or create the LACP manager singleton"""
    global _lacp_manager
    if _lacp_manager is None:
        _lacp_manager = LACPManager(agent_id)
    return _lacp_manager


async def start_lacp(agent_id: str) -> LACPManager:
    """Start the LACP manager for an agent"""
    global _lacp_manager
    _lacp_manager = LACPManager(agent_id)
    await _lacp_manager.start()
    return _lacp_manager


async def stop_lacp():
    """Stop the LACP manager"""
    global _lacp_manager
    if _lacp_manager:
        await _lacp_manager.stop()
        _lacp_manager = None


def get_lag_list() -> List[Dict[str, Any]]:
    """Get all LAGs as dictionaries"""
    manager = get_lacp_manager()
    return [lag.to_dict() for lag in manager.list_lags()]


def get_lacp_statistics() -> Dict[str, Any]:
    """Get LACP manager statistics"""
    manager = get_lacp_manager()
    return manager.get_statistics()
