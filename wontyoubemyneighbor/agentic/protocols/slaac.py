"""
IPv6 SLAAC (Stateless Address Autoconfiguration) for Agents

Based on RFC 4862 - IPv6 Stateless Address Autoconfiguration

Agents use SLAAC to self-assign IPv6 addresses for:
- Loopback interfaces (mesh communication)
- Agent-to-agent peering
- Management plane addressing

Prefix used: fd00:10::/64 (ULA prefix for agent mesh)
EUI-64 generation from agent ID for globally unique addresses within the mesh.
"""

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger("SLAAC")


class AddressState(Enum):
    """DAD (Duplicate Address Detection) states per RFC 4862"""
    TENTATIVE = "tentative"     # Address being verified (DAD in progress)
    PREFERRED = "preferred"     # Address is valid and preferred
    DEPRECATED = "deprecated"   # Valid but should not be used for new connections
    INVALID = "invalid"         # Address is no longer valid


class AddressScope(Enum):
    """IPv6 address scopes"""
    LINK_LOCAL = "link-local"   # fe80::/10 - single link only
    SITE_LOCAL = "site-local"   # Deprecated in RFC 3879
    GLOBAL = "global"           # Global unicast
    ULA = "ula"                 # Unique Local Address fd00::/8


@dataclass
class SLAACAddress:
    """An IPv6 address generated via SLAAC"""
    address: str              # Full IPv6 address
    prefix: str               # Network prefix (e.g., fd00:10::/64)
    prefix_length: int        # Prefix length (typically 64)
    interface_id: str         # EUI-64 or random interface identifier

    state: AddressState = AddressState.TENTATIVE
    scope: AddressScope = AddressScope.ULA

    # RFC 4862 lifetimes
    valid_lifetime: int = 2592000       # Default 30 days in seconds
    preferred_lifetime: int = 604800    # Default 7 days in seconds

    created_at: datetime = field(default_factory=datetime.now)
    dad_completed: bool = False
    dad_attempts: int = 0

    def __post_init__(self):
        # Calculate expiry times
        self.valid_until = self.created_at + timedelta(seconds=self.valid_lifetime)
        self.preferred_until = self.created_at + timedelta(seconds=self.preferred_lifetime)

    @property
    def is_valid(self) -> bool:
        """Check if address is still valid"""
        now = datetime.now()
        return (self.state in (AddressState.PREFERRED, AddressState.DEPRECATED) and
                now < self.valid_until)

    @property
    def is_preferred(self) -> bool:
        """Check if address is preferred for new connections"""
        now = datetime.now()
        return self.state == AddressState.PREFERRED and now < self.preferred_until

    @property
    def full_cidr(self) -> str:
        """Return address with prefix length"""
        return f"{self.address}/{self.prefix_length}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "address": self.address,
            "full_cidr": self.full_cidr,
            "prefix": self.prefix,
            "prefix_length": self.prefix_length,
            "interface_id": self.interface_id,
            "state": self.state.value,
            "scope": self.scope.value,
            "valid_lifetime": self.valid_lifetime,
            "preferred_lifetime": self.preferred_lifetime,
            "valid_until": self.valid_until.isoformat(),
            "preferred_until": self.preferred_until.isoformat(),
            "created_at": self.created_at.isoformat(),
            "dad_completed": self.dad_completed,
            "is_valid": self.is_valid,
            "is_preferred": self.is_preferred
        }


# Agent mesh network prefix (ULA per RFC 4193)
# fd00:a510::/48 - "a510" = "ASI0" for ASI Overlay
# Agent format: fd00:a510:0:{network}::{agent}/64
AGENT_MESH_PREFIX = "fd00:a510::"
AGENT_MESH_PREFIX_LEN = 48

# Default network segment within the /48
DEFAULT_NETWORK_SEGMENT = 1


class SLAACManager:
    """
    Manages IPv6 SLAAC address generation for agents.

    Per RFC 4862, generates:
    - Link-local addresses (fe80::/10)
    - Global/ULA addresses from router advertisements

    For the agent mesh, we use ULA prefix fd00:10::/64
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id

        # Store generated addresses per interface
        self.addresses: Dict[str, List[SLAACAddress]] = {}

        # EUI-64 interface identifier derived from agent ID
        self.eui64 = self._generate_eui64(agent_id)

        # Track link-local address
        self.link_local: Optional[SLAACAddress] = None

        # Mesh address (ULA)
        self.mesh_address: Optional[SLAACAddress] = None

        # DAD (Duplicate Address Detection) settings
        self.dad_transmits = 1  # Number of NS messages for DAD
        self.dad_retransmit_timer = 1.0  # Seconds between DAD attempts

        logger.info(f"[SLAAC] Manager initialized for agent {agent_id}")
        logger.info(f"[SLAAC] EUI-64 interface identifier: {self.eui64}")

    def _generate_eui64(self, agent_id: str) -> str:
        """
        Generate EUI-64 interface identifier from agent ID.

        RFC 4291 defines EUI-64 format for IPv6 interface identifiers.
        We derive it from agent_id hash to ensure uniqueness.

        Returns:
            64-bit interface identifier as 4 hex groups (e.g., "1234:5678:9abc:def0")
        """
        # Hash the agent_id to get consistent 64 bits
        hash_bytes = hashlib.sha256(agent_id.encode()).digest()[:8]

        # Convert to EUI-64 format
        # Set the universal/local bit (7th bit of first byte) to 1 for local
        first_byte = hash_bytes[0] | 0x02  # Set locally administered bit

        # Format as 4 hex groups
        eui64 = f"{first_byte:02x}{hash_bytes[1]:02x}:{hash_bytes[2]:02x}{hash_bytes[3]:02x}:" \
                f"{hash_bytes[4]:02x}{hash_bytes[5]:02x}:{hash_bytes[6]:02x}{hash_bytes[7]:02x}"

        return eui64

    def generate_link_local(self, interface: str = "lo0") -> SLAACAddress:
        """
        Generate link-local address (fe80::/10).

        Every IPv6 interface must have a link-local address.
        Format: fe80::EUI-64

        Args:
            interface: Interface name

        Returns:
            Generated link-local address
        """
        address = f"fe80::{self.eui64}"

        addr = SLAACAddress(
            address=address,
            prefix="fe80::",
            prefix_length=10,
            interface_id=self.eui64,
            scope=AddressScope.LINK_LOCAL,
            valid_lifetime=0xFFFFFFFF,  # Infinite for link-local
            preferred_lifetime=0xFFFFFFFF
        )

        # Complete DAD (in real implementation this would be async)
        addr.dad_completed = True
        addr.state = AddressState.PREFERRED

        self.link_local = addr

        if interface not in self.addresses:
            self.addresses[interface] = []
        self.addresses[interface].append(addr)

        logger.info(f"[SLAAC] Generated link-local address: {address}")
        return addr

    def generate_mesh_address(self,
                               network_segment: int = DEFAULT_NETWORK_SEGMENT,
                               agent_number: Optional[int] = None,
                               interface: str = "lo0") -> SLAACAddress:
        """
        Generate mesh network address (ULA) for agent-to-agent communication.

        Uses the ASI Overlay format: fd00:a510:0:{network}::{agent}/64

        Args:
            network_segment: Network segment (default 1)
            agent_number: Agent number (auto-derived from agent_id if not provided)
            interface: Interface name

        Returns:
            Generated mesh address
        """
        # Derive agent number from agent_id if not provided
        if agent_number is None:
            # Hash agent_id to get a deterministic number (1-65535)
            hash_bytes = hashlib.sha256(self.agent_id.encode()).digest()
            agent_number = int.from_bytes(hash_bytes[:2], 'big') % 65534 + 1

        self.agent_number = agent_number
        self.network_segment = network_segment

        # Format: fd00:a510:0:{network}::{agent}/64
        address = f"fd00:a510:0:{network_segment:x}::{agent_number:x}"
        prefix = f"fd00:a510:0:{network_segment:x}::/64"

        addr = SLAACAddress(
            address=address,
            prefix=prefix,
            prefix_length=64,
            interface_id=f"::{agent_number:x}",
            scope=AddressScope.ULA,
            valid_lifetime=86400 * 365,  # 1 year for mesh
            preferred_lifetime=86400 * 30  # 30 days
        )

        # Complete DAD
        addr.dad_completed = True
        addr.state = AddressState.PREFERRED

        self.mesh_address = addr

        if interface not in self.addresses:
            self.addresses[interface] = []
        self.addresses[interface].append(addr)

        logger.info(f"[SLAAC] Generated mesh address: {address}/64 (agent #{agent_number} on network {network_segment})")
        return addr

    def generate_privacy_address(self,
                                  prefix: str = AGENT_MESH_PREFIX,
                                  prefix_len: int = AGENT_MESH_PREFIX_LEN,
                                  interface: str = "lo0") -> SLAACAddress:
        """
        Generate temporary privacy address per RFC 4941.

        Uses random interface identifier instead of EUI-64 for privacy.
        These addresses have shorter lifetimes.

        Args:
            prefix: Network prefix
            prefix_len: Prefix length
            interface: Interface name

        Returns:
            Generated privacy address
        """
        # Generate random 64-bit interface ID
        random_bytes = uuid.uuid4().bytes[:8]

        # Set locally administered bit and clear group bit
        first_byte = (random_bytes[0] | 0x02) & 0xfe

        random_iid = f"{first_byte:02x}{random_bytes[1]:02x}:{random_bytes[2]:02x}{random_bytes[3]:02x}:" \
                     f"{random_bytes[4]:02x}{random_bytes[5]:02x}:{random_bytes[6]:02x}{random_bytes[7]:02x}"

        address = f"{prefix.rstrip(':')}{random_iid}"

        addr = SLAACAddress(
            address=address,
            prefix=f"{prefix.rstrip(':')}/{prefix_len}",
            prefix_length=prefix_len,
            interface_id=random_iid,
            scope=AddressScope.ULA,
            valid_lifetime=86400,  # 1 day
            preferred_lifetime=3600  # 1 hour (prefer new addresses quickly)
        )

        addr.dad_completed = True
        addr.state = AddressState.PREFERRED

        if interface not in self.addresses:
            self.addresses[interface] = []
        self.addresses[interface].append(addr)

        logger.info(f"[SLAAC] Generated privacy address: {address}/{prefix_len}")
        return addr

    def auto_configure(self, interface: str = "lo0", network_segment: int = DEFAULT_NETWORK_SEGMENT) -> Dict[str, SLAACAddress]:
        """
        Perform full SLAAC auto-configuration for an interface.

        Generates:
        1. Link-local address (fe80::EUI-64)
        2. Mesh ULA address (fd00:a510:0:{net}::{agent}/64)

        Args:
            interface: Interface to configure
            network_segment: Network segment within fd00:a510::/48

        Returns:
            Dictionary of generated addresses
        """
        result = {}

        # Generate link-local
        result['link_local'] = self.generate_link_local(interface)

        # Generate mesh address using ASI overlay format
        result['mesh'] = self.generate_mesh_address(network_segment=network_segment, interface=interface)

        logger.info(f"[SLAAC] Auto-configured interface {interface} with {len(result)} addresses")
        return result

    def get_mesh_address(self) -> Optional[str]:
        """Get the agent's mesh address (ULA)"""
        if self.mesh_address and self.mesh_address.is_valid:
            return self.mesh_address.address
        return None

    def get_link_local(self) -> Optional[str]:
        """Get the agent's link-local address"""
        if self.link_local and self.link_local.is_valid:
            return self.link_local.address
        return None

    def get_all_addresses(self, interface: Optional[str] = None) -> List[SLAACAddress]:
        """Get all addresses, optionally filtered by interface"""
        if interface:
            return self.addresses.get(interface, [])

        all_addrs = []
        for addrs in self.addresses.values():
            all_addrs.extend(addrs)
        return all_addrs

    def get_preferred_address(self) -> Optional[str]:
        """Get the best address to use for new connections"""
        # Prefer mesh address over link-local
        if self.mesh_address and self.mesh_address.is_preferred:
            return self.mesh_address.address
        if self.link_local and self.link_local.is_preferred:
            return self.link_local.address
        return None

    def refresh_addresses(self):
        """Update address states based on lifetimes"""
        now = datetime.now()

        for interface, addrs in self.addresses.items():
            for addr in addrs:
                if addr.state == AddressState.PREFERRED:
                    if now >= addr.preferred_until:
                        addr.state = AddressState.DEPRECATED
                        logger.info(f"[SLAAC] Address {addr.address} deprecated")
                    if now >= addr.valid_until:
                        addr.state = AddressState.INVALID
                        logger.info(f"[SLAAC] Address {addr.address} invalidated")

    def get_status(self) -> Dict[str, Any]:
        """Get SLAAC manager status"""
        return {
            "agent_id": self.agent_id,
            "eui64": self.eui64,
            "agent_number": getattr(self, 'agent_number', None),
            "network_segment": getattr(self, 'network_segment', DEFAULT_NETWORK_SEGMENT),
            "mesh_address": self.mesh_address.to_dict() if self.mesh_address else None,
            "link_local": self.link_local.to_dict() if self.link_local else None,
            "total_addresses": sum(len(a) for a in self.addresses.values()),
            "interfaces": list(self.addresses.keys()),
            "addresses_by_interface": {
                iface: [a.to_dict() for a in addrs]
                for iface, addrs in self.addresses.items()
            }
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return self.get_status()


# Singleton manager instances per agent
_slaac_managers: Dict[str, SLAACManager] = {}


def get_slaac_manager(agent_id: str = "local") -> SLAACManager:
    """Get or create SLAAC manager for an agent"""
    if agent_id not in _slaac_managers:
        _slaac_managers[agent_id] = SLAACManager(agent_id)
    return _slaac_managers[agent_id]


def initialize_agent_slaac(agent_id: str, interface: str = "lo0", network_segment: int = DEFAULT_NETWORK_SEGMENT) -> Dict[str, Any]:
    """
    Initialize SLAAC for an agent and return assigned addresses.

    This is the main entry point for agent IPv6 auto-configuration.
    Uses ASI Overlay format: fd00:a510:0:{net}::{agent}/64

    Args:
        agent_id: Unique agent identifier
        interface: Interface to configure (default loopback)
        network_segment: Network segment within fd00:a510::/48

    Returns:
        Dictionary with generated addresses
    """
    manager = get_slaac_manager(agent_id)
    addresses = manager.auto_configure(interface, network_segment)

    return {
        "success": True,
        "agent_id": agent_id,
        "interface": interface,
        "network_segment": manager.network_segment,
        "agent_number": manager.agent_number,
        "mesh_address": addresses['mesh'].full_cidr,
        "link_local": addresses['link_local'].full_cidr,
        "eui64": manager.eui64,
        "details": manager.get_status()
    }
