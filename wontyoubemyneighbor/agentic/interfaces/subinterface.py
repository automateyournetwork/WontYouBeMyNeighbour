"""
Subinterface Support (VLANs / 802.1Q / L3 Routed)

Provides subinterface capabilities for agents, supporting both:
- 802.1Q VLAN subinterfaces (L2 tagged)
- L3 Routed subinterfaces (no encapsulation, multiple IPs per port)

Features:
- Create VLAN subinterfaces (eth0.10, eth0.20, etc.)
- Create L3 routed subinterfaces (eth0:0, eth0:1, etc.)
- 802.1Q VLAN tagging for L2 subinterfaces
- IPv4 and IPv6 addressing per subinterface
- Interface state management
- Statistics per subinterface
- Support for point-to-point L3 links
"""

import asyncio
import logging
import subprocess
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from datetime import datetime
import time

logger = logging.getLogger("Subinterface")

# Singleton manager instance
_subinterface_manager: Optional["SubinterfaceManager"] = None


class EncapsulationType(Enum):
    """Subinterface encapsulation type"""
    DOT1Q = "802.1Q"      # Standard 802.1Q tagging
    DOT1AD = "802.1ad"    # QinQ (double tagging)
    NATIVE = "native"     # Untagged/native VLAN
    NONE = "none"         # L3 routed subinterface (no encapsulation)


class InterfaceMode(Enum):
    """Interface mode - L2 (switchport) or L3 (routed)"""
    L2_ACCESS = "access"        # L2 access port (single VLAN)
    L2_TRUNK = "trunk"          # L2 trunk port (multiple VLANs)
    L3_ROUTED = "routed"        # L3 routed port (no switchport)
    L3_SUBINTERFACE = "l3_sub"  # L3 subinterface on routed port


class InterfaceState(Enum):
    """Interface operational state"""
    UP = "up"
    DOWN = "down"
    ADMIN_DOWN = "admin_down"
    UNKNOWN = "unknown"


@dataclass
class InterfaceStatistics:
    """Interface traffic statistics"""
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    tx_packets: int = 0
    rx_errors: int = 0
    tx_errors: int = 0
    rx_dropped: int = 0
    tx_dropped: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "rx_bytes": self.rx_bytes,
            "tx_bytes": self.tx_bytes,
            "rx_packets": self.rx_packets,
            "tx_packets": self.tx_packets,
            "rx_errors": self.rx_errors,
            "tx_errors": self.tx_errors,
            "rx_dropped": self.rx_dropped,
            "tx_dropped": self.tx_dropped
        }


@dataclass
class Subinterface:
    """
    A subinterface - either VLAN-tagged (e.g., eth0.10) or L3 routed (e.g., eth0:0)

    Supports two modes:
    1. VLAN subinterface: 802.1Q tagged interface with VLAN ID
    2. L3 routed subinterface: Untagged interface for additional IPs on L3 port

    Examples:
    - VLAN: eth0.100 (VLAN 100 on eth0)
    - L3 routed: eth0:0 (secondary IP on routed port eth0)
    """
    # Identity
    name: str  # e.g., "eth0.10" for VLAN, "eth0:0" for L3 routed
    parent_interface: str  # e.g., "eth0"
    subif_index: int  # Subinterface index (VLAN ID for 802.1Q, or sequence number for L3)

    # Configuration
    encapsulation: EncapsulationType = EncapsulationType.DOT1Q
    interface_mode: InterfaceMode = InterfaceMode.L2_TRUNK
    description: str = ""
    mtu: int = 1500  # Note: VLAN subinterface MTU should be <= parent - 4 for tag

    # Addressing
    ipv4_addresses: List[str] = field(default_factory=list)  # e.g., ["192.168.10.1/24"]
    ipv6_addresses: List[str] = field(default_factory=list)  # e.g., ["fd00:10::1/64"]

    # State
    admin_state: InterfaceState = InterfaceState.UP
    oper_state: InterfaceState = InterfaceState.UNKNOWN
    created_at: float = field(default_factory=time.time)

    # Statistics
    statistics: InterfaceStatistics = field(default_factory=InterfaceStatistics)

    # QinQ outer VLAN (for 802.1ad)
    outer_vlan_id: Optional[int] = None

    # L3 specific - for point-to-point links
    unnumbered_interface: Optional[str] = None  # Borrow IP from another interface

    @property
    def vlan_id(self) -> Optional[int]:
        """Get VLAN ID (only valid for 802.1Q/802.1ad encapsulation)"""
        if self.encapsulation in (EncapsulationType.DOT1Q, EncapsulationType.DOT1AD):
            return self.subif_index
        return None

    @property
    def is_l3_routed(self) -> bool:
        """Check if this is an L3 routed subinterface (no VLAN tagging)"""
        return self.encapsulation == EncapsulationType.NONE

    def get_full_name(self) -> str:
        """Get the full interface name based on type"""
        if self.is_l3_routed:
            # L3 routed subinterface: eth0:0, eth0:1, etc.
            return f"{self.parent_interface}:{self.subif_index}"
        else:
            # VLAN subinterface: eth0.100, eth0.200, etc.
            return f"{self.parent_interface}.{self.subif_index}"

    def is_up(self) -> bool:
        """Check if interface is operationally up"""
        return self.oper_state == InterfaceState.UP and self.admin_state == InterfaceState.UP

    def get_primary_ipv4(self) -> Optional[str]:
        """Get primary IPv4 address (first one)"""
        return self.ipv4_addresses[0] if self.ipv4_addresses else None

    def get_primary_ipv6(self) -> Optional[str]:
        """Get primary IPv6 address (first one)"""
        return self.ipv6_addresses[0] if self.ipv6_addresses else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "parent_interface": self.parent_interface,
            "subif_index": self.subif_index,
            "vlan_id": self.vlan_id,  # None for L3 routed
            "encapsulation": self.encapsulation.value,
            "interface_mode": self.interface_mode.value,
            "is_l3_routed": self.is_l3_routed,
            "description": self.description,
            "mtu": self.mtu,
            "ipv4_addresses": self.ipv4_addresses,
            "ipv6_addresses": self.ipv6_addresses,
            "admin_state": self.admin_state.value,
            "oper_state": self.oper_state.value,
            "is_up": self.is_up(),
            "created_at": datetime.fromtimestamp(self.created_at).isoformat(),
            "statistics": self.statistics.to_dict(),
            "outer_vlan_id": self.outer_vlan_id,
            "unnumbered_interface": self.unnumbered_interface
        }


@dataclass
class PhysicalInterface:
    """
    A physical interface that can have subinterfaces.

    Tracks the parent interface and all its subinterfaces.
    Supports both L2 (switchport) and L3 (routed) modes.

    L2 Mode (default):
    - Can have 802.1Q tagged subinterfaces (VLANs)
    - Trunk or access mode

    L3 Mode (no switchport):
    - Can have L3 routed subinterfaces (secondary IPs)
    - Used for router interfaces, point-to-point links
    """
    name: str  # e.g., "eth0"
    mac_address: str = ""
    mtu: int = 1500
    admin_state: InterfaceState = InterfaceState.UP
    oper_state: InterfaceState = InterfaceState.UNKNOWN

    # Interface mode - determines what type of subinterfaces are allowed
    interface_mode: InterfaceMode = InterfaceMode.L2_TRUNK

    # Primary IP addresses (for L3 routed mode)
    ipv4_address: Optional[str] = None  # e.g., "192.168.1.1/24"
    ipv6_address: Optional[str] = None  # e.g., "2001:db8::1/64"

    # Subinterfaces keyed by index (VLAN ID for L2, sequence for L3)
    subinterfaces: Dict[int, Subinterface] = field(default_factory=dict)

    # L2 specific - Native VLAN (untagged)
    native_vlan: Optional[int] = None

    # L2 specific - Trunk mode (allows multiple VLANs)
    trunk_mode: bool = False
    allowed_vlans: List[int] = field(default_factory=list)  # Empty = all

    @property
    def is_l3_routed(self) -> bool:
        """Check if interface is in L3 routed mode"""
        return self.interface_mode in (InterfaceMode.L3_ROUTED, InterfaceMode.L3_SUBINTERFACE)

    def get_subinterface(self, index: int) -> Optional[Subinterface]:
        """Get a subinterface by index (VLAN ID or sequence number)"""
        return self.subinterfaces.get(index)

    def list_subinterfaces(self) -> List[Subinterface]:
        """List all subinterfaces"""
        return list(self.subinterfaces.values())

    def list_vlan_subinterfaces(self) -> List[Subinterface]:
        """List only VLAN (802.1Q) subinterfaces"""
        return [s for s in self.subinterfaces.values() if not s.is_l3_routed]

    def list_l3_subinterfaces(self) -> List[Subinterface]:
        """List only L3 routed subinterfaces"""
        return [s for s in self.subinterfaces.values() if s.is_l3_routed]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "mac_address": self.mac_address,
            "mtu": self.mtu,
            "admin_state": self.admin_state.value,
            "oper_state": self.oper_state.value,
            "interface_mode": self.interface_mode.value,
            "is_l3_routed": self.is_l3_routed,
            "ipv4_address": self.ipv4_address,
            "ipv6_address": self.ipv6_address,
            "native_vlan": self.native_vlan,
            "trunk_mode": self.trunk_mode,
            "allowed_vlans": self.allowed_vlans,
            "subinterface_count": len(self.subinterfaces),
            "vlan_subinterfaces": len(self.list_vlan_subinterfaces()),
            "l3_subinterfaces": len(self.list_l3_subinterfaces()),
            "subinterfaces": {str(idx): sub.to_dict() for idx, sub in self.subinterfaces.items()}
        }


class SubinterfaceManager:
    """
    Manages all subinterfaces for an agent.

    Handles:
    - Subinterface creation and deletion
    - IP address assignment
    - Interface state management
    - Statistics collection
    - System interface configuration (via ip command)
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.interfaces: Dict[str, PhysicalInterface] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the subinterface manager"""
        if self._running:
            return

        self._running = True
        # Discover existing interfaces
        await self._discover_interfaces()
        # Start monitoring task
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"Subinterface manager started for agent {self.agent_id}")

    async def stop(self):
        """Stop the subinterface manager"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"Subinterface manager stopped for agent {self.agent_id}")

    async def _monitor_loop(self):
        """Monitor interface states and collect statistics"""
        while self._running:
            try:
                await self._update_interface_states()
                await self._collect_statistics()
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Subinterface monitor error: {e}")
                await asyncio.sleep(10)

    async def _discover_interfaces(self):
        """Discover existing physical interfaces"""
        try:
            result = subprocess.run(
                ["ip", "-j", "link", "show"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                interfaces = json.loads(result.stdout.decode())
                for iface in interfaces:
                    name = iface.get("ifname", "")
                    # Skip loopback and virtual interfaces
                    if name and not name.startswith("lo") and not name.startswith("veth"):
                        if "." not in name:  # Physical interface (not subinterface)
                            if name not in self.interfaces:
                                self.interfaces[name] = PhysicalInterface(
                                    name=name,
                                    mac_address=iface.get("address", ""),
                                    mtu=iface.get("mtu", 1500)
                                )
        except Exception as e:
            logger.debug(f"Interface discovery error: {e}")

    async def _update_interface_states(self):
        """Update operational states of all interfaces"""
        try:
            result = subprocess.run(
                ["ip", "-j", "link", "show"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                interfaces = json.loads(result.stdout.decode())
                iface_states = {i["ifname"]: i for i in interfaces}

                # Update physical interfaces
                for name, iface in self.interfaces.items():
                    if name in iface_states:
                        state_info = iface_states[name]
                        flags = state_info.get("flags", [])
                        iface.oper_state = InterfaceState.UP if "UP" in flags else InterfaceState.DOWN

                    # Update subinterfaces
                    for vlan_id, subif in iface.subinterfaces.items():
                        subif_name = f"{name}.{vlan_id}"
                        if subif_name in iface_states:
                            state_info = iface_states[subif_name]
                            flags = state_info.get("flags", [])
                            subif.oper_state = InterfaceState.UP if "UP" in flags else InterfaceState.DOWN
        except Exception as e:
            logger.debug(f"State update error: {e}")

    async def _collect_statistics(self):
        """Collect interface statistics"""
        try:
            result = subprocess.run(
                ["ip", "-j", "-s", "link", "show"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                interfaces = json.loads(result.stdout.decode())
                for iface_data in interfaces:
                    name = iface_data.get("ifname", "")
                    stats = iface_data.get("stats64", {})

                    # Check if it's a subinterface
                    if "." in name:
                        parent, vlan_str = name.rsplit(".", 1)
                        try:
                            vlan_id = int(vlan_str)
                            if parent in self.interfaces:
                                subif = self.interfaces[parent].subinterfaces.get(vlan_id)
                                if subif:
                                    rx = stats.get("rx", {})
                                    tx = stats.get("tx", {})
                                    subif.statistics = InterfaceStatistics(
                                        rx_bytes=rx.get("bytes", 0),
                                        tx_bytes=tx.get("bytes", 0),
                                        rx_packets=rx.get("packets", 0),
                                        tx_packets=tx.get("packets", 0),
                                        rx_errors=rx.get("errors", 0),
                                        tx_errors=tx.get("errors", 0),
                                        rx_dropped=rx.get("dropped", 0),
                                        tx_dropped=tx.get("dropped", 0)
                                    )
                        except ValueError:
                            pass
        except Exception as e:
            logger.debug(f"Statistics collection error: {e}")

    def register_interface(self, name: str, mac_address: str = "", mtu: int = 1500) -> PhysicalInterface:
        """Register a physical interface"""
        if name not in self.interfaces:
            self.interfaces[name] = PhysicalInterface(
                name=name,
                mac_address=mac_address,
                mtu=mtu
            )
        return self.interfaces[name]

    def create_subinterface(
        self,
        parent_interface: str,
        vlan_id: int,
        description: str = "",
        mtu: Optional[int] = None,
        ipv4_addresses: Optional[List[str]] = None,
        ipv6_addresses: Optional[List[str]] = None,
        encapsulation: EncapsulationType = EncapsulationType.DOT1Q
    ) -> Subinterface:
        """
        Create a new subinterface.

        Args:
            parent_interface: Name of parent interface (e.g., "eth0")
            vlan_id: VLAN ID (1-4094)
            description: Optional description
            mtu: MTU (defaults to parent MTU - 4)
            ipv4_addresses: List of IPv4 addresses with prefix (e.g., ["192.168.10.1/24"])
            ipv6_addresses: List of IPv6 addresses with prefix
            encapsulation: Encapsulation type (default 802.1Q)

        Returns:
            Created Subinterface object
        """
        # Validate VLAN ID
        if vlan_id < 1 or vlan_id > 4094:
            raise ValueError(f"VLAN ID must be between 1 and 4094, got {vlan_id}")

        # Ensure parent interface exists
        if parent_interface not in self.interfaces:
            self.register_interface(parent_interface)

        parent = self.interfaces[parent_interface]

        # Check if subinterface already exists
        if vlan_id in parent.subinterfaces:
            raise ValueError(f"Subinterface {parent_interface}.{vlan_id} already exists")

        # Calculate MTU
        if mtu is None:
            mtu = parent.mtu - 4  # Account for VLAN tag

        # Create subinterface name
        subif_name = f"{parent_interface}.{vlan_id}"

        # Create subinterface object
        subif = Subinterface(
            name=subif_name,
            parent_interface=parent_interface,
            vlan_id=vlan_id,
            encapsulation=encapsulation,
            description=description,
            mtu=mtu,
            ipv4_addresses=ipv4_addresses or [],
            ipv6_addresses=ipv6_addresses or []
        )

        # Add to parent
        parent.subinterfaces[vlan_id] = subif

        # Try to create in system
        self._create_system_subinterface(subif)

        logger.info(f"Created subinterface {subif_name} (VLAN {vlan_id})")
        return subif

    def _create_system_subinterface(self, subif: Subinterface):
        """Create the subinterface in the system (via ip command)"""
        try:
            # Create VLAN interface
            subprocess.run(
                ["ip", "link", "add", "link", subif.parent_interface,
                 "name", subif.name, "type", "vlan", "id", str(subif.vlan_id)],
                capture_output=True,
                timeout=5
            )

            # Set MTU
            subprocess.run(
                ["ip", "link", "set", subif.name, "mtu", str(subif.mtu)],
                capture_output=True,
                timeout=5
            )

            # Add IPv4 addresses
            for addr in subif.ipv4_addresses:
                subprocess.run(
                    ["ip", "addr", "add", addr, "dev", subif.name],
                    capture_output=True,
                    timeout=5
                )

            # Add IPv6 addresses
            for addr in subif.ipv6_addresses:
                subprocess.run(
                    ["ip", "-6", "addr", "add", addr, "dev", subif.name],
                    capture_output=True,
                    timeout=5
                )

            # Bring interface up
            if subif.admin_state == InterfaceState.UP:
                subprocess.run(
                    ["ip", "link", "set", subif.name, "up"],
                    capture_output=True,
                    timeout=5
                )

            subif.oper_state = InterfaceState.UP
        except Exception as e:
            logger.warning(f"Failed to create system subinterface {subif.name}: {e}")

    def delete_subinterface(self, parent_interface: str, vlan_id: int) -> bool:
        """
        Delete a subinterface.

        Args:
            parent_interface: Name of parent interface
            vlan_id: VLAN ID

        Returns:
            True if deleted, False if not found
        """
        if parent_interface not in self.interfaces:
            return False

        parent = self.interfaces[parent_interface]
        if vlan_id not in parent.subinterfaces:
            return False

        subif = parent.subinterfaces[vlan_id]

        # Remove from system
        try:
            subprocess.run(
                ["ip", "link", "delete", subif.name],
                capture_output=True,
                timeout=5
            )
        except Exception as e:
            logger.warning(f"Failed to delete system subinterface {subif.name}: {e}")

        del parent.subinterfaces[vlan_id]
        logger.info(f"Deleted subinterface {subif.name}")
        return True

    def add_ip_address(
        self,
        parent_interface: str,
        vlan_id: int,
        address: str,
        is_ipv6: bool = False
    ) -> bool:
        """Add an IP address to a subinterface"""
        if parent_interface not in self.interfaces:
            return False

        subif = self.interfaces[parent_interface].subinterfaces.get(vlan_id)
        if not subif:
            return False

        if is_ipv6:
            if address not in subif.ipv6_addresses:
                subif.ipv6_addresses.append(address)
                # Add to system
                try:
                    subprocess.run(
                        ["ip", "-6", "addr", "add", address, "dev", subif.name],
                        capture_output=True,
                        timeout=5
                    )
                except Exception:
                    pass
        else:
            if address not in subif.ipv4_addresses:
                subif.ipv4_addresses.append(address)
                # Add to system
                try:
                    subprocess.run(
                        ["ip", "addr", "add", address, "dev", subif.name],
                        capture_output=True,
                        timeout=5
                    )
                except Exception:
                    pass

        return True

    def remove_ip_address(
        self,
        parent_interface: str,
        vlan_id: int,
        address: str,
        is_ipv6: bool = False
    ) -> bool:
        """Remove an IP address from a subinterface"""
        if parent_interface not in self.interfaces:
            return False

        subif = self.interfaces[parent_interface].subinterfaces.get(vlan_id)
        if not subif:
            return False

        if is_ipv6:
            if address in subif.ipv6_addresses:
                subif.ipv6_addresses.remove(address)
                try:
                    subprocess.run(
                        ["ip", "-6", "addr", "del", address, "dev", subif.name],
                        capture_output=True,
                        timeout=5
                    )
                except Exception:
                    pass
        else:
            if address in subif.ipv4_addresses:
                subif.ipv4_addresses.remove(address)
                try:
                    subprocess.run(
                        ["ip", "addr", "del", address, "dev", subif.name],
                        capture_output=True,
                        timeout=5
                    )
                except Exception:
                    pass

        return True

    def set_admin_state(self, parent_interface: str, vlan_id: int, state: InterfaceState) -> bool:
        """Set the administrative state of a subinterface"""
        if parent_interface not in self.interfaces:
            return False

        subif = self.interfaces[parent_interface].subinterfaces.get(vlan_id)
        if not subif:
            return False

        subif.admin_state = state

        # Apply to system
        try:
            cmd = "up" if state == InterfaceState.UP else "down"
            subprocess.run(
                ["ip", "link", "set", subif.name, cmd],
                capture_output=True,
                timeout=5
            )
        except Exception:
            pass

        return True

    def get_interface(self, name: str) -> Optional[PhysicalInterface]:
        """Get a physical interface by name"""
        return self.interfaces.get(name)

    def get_subinterface(self, parent: str, vlan_id: int) -> Optional[Subinterface]:
        """Get a subinterface"""
        if parent in self.interfaces:
            return self.interfaces[parent].subinterfaces.get(vlan_id)
        return None

    def list_all_subinterfaces(self) -> List[Subinterface]:
        """List all subinterfaces across all physical interfaces"""
        result = []
        for iface in self.interfaces.values():
            result.extend(iface.list_subinterfaces())
        return result

    def get_statistics(self) -> Dict[str, Any]:
        """Get manager statistics"""
        total_subifs = sum(len(iface.subinterfaces) for iface in self.interfaces.values())
        return {
            "agent_id": self.agent_id,
            "physical_interfaces": len(self.interfaces),
            "total_subinterfaces": total_subifs,
            "running": self._running
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert manager state to dictionary"""
        return {
            "agent_id": self.agent_id,
            "running": self._running,
            "interfaces": {name: iface.to_dict() for name, iface in self.interfaces.items()},
            "statistics": self.get_statistics()
        }


def get_subinterface_manager(agent_id: str = "local") -> SubinterfaceManager:
    """Get or create the subinterface manager singleton"""
    global _subinterface_manager
    if _subinterface_manager is None:
        _subinterface_manager = SubinterfaceManager(agent_id)
    return _subinterface_manager


async def start_subinterface_manager(agent_id: str) -> SubinterfaceManager:
    """Start the subinterface manager for an agent"""
    global _subinterface_manager
    _subinterface_manager = SubinterfaceManager(agent_id)
    await _subinterface_manager.start()
    return _subinterface_manager


async def stop_subinterface_manager():
    """Stop the subinterface manager"""
    global _subinterface_manager
    if _subinterface_manager:
        await _subinterface_manager.stop()
        _subinterface_manager = None


def list_subinterfaces() -> List[Dict[str, Any]]:
    """List all subinterfaces as dictionaries"""
    manager = get_subinterface_manager()
    return [s.to_dict() for s in manager.list_all_subinterfaces()]


def get_subinterface_statistics() -> Dict[str, Any]:
    """Get subinterface manager statistics"""
    manager = get_subinterface_manager()
    return manager.get_statistics()
