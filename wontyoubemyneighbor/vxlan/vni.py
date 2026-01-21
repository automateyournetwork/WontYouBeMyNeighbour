"""
VXLAN Network Identifier (VNI) Management

Manages VNI allocation, mapping, and associated configuration
for VXLAN overlay networks.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any
from enum import Enum


class VNIType(Enum):
    """VNI types for different use cases"""
    L2VNI = "l2vni"      # Layer 2 VNI for bridging
    L3VNI = "l3vni"      # Layer 3 VNI for routing (VRF)


@dataclass
class VNI:
    """
    VXLAN Network Identifier configuration.

    Represents a single VXLAN segment with its associated
    configuration and state.
    """
    vni_id: int                          # VNI value (1-16777215)
    vni_type: VNIType = VNIType.L2VNI    # L2 or L3 VNI
    vlan_id: Optional[int] = None        # Associated VLAN (for L2VNI)
    vrf_name: Optional[str] = None       # Associated VRF (for L3VNI)
    rd: Optional[str] = None             # Route Distinguisher
    rt_import: List[str] = field(default_factory=list)  # Import Route Targets
    rt_export: List[str] = field(default_factory=list)  # Export Route Targets
    anycast_gateway_ip: Optional[str] = None  # Anycast gateway IP
    anycast_gateway_mac: Optional[str] = None  # Anycast gateway MAC

    # Learned information
    learned_macs: Dict[str, str] = field(default_factory=dict)  # {MAC: VTEP_IP}
    learned_ips: Dict[str, str] = field(default_factory=dict)   # {IP: MAC}

    # Multicast group for BUM traffic (if using multicast)
    mcast_group: Optional[str] = None

    # Statistics
    packets_encap: int = 0
    packets_decap: int = 0
    bytes_encap: int = 0
    bytes_decap: int = 0

    def __post_init__(self):
        """Validate VNI configuration"""
        if not 1 <= self.vni_id <= 16777215:
            raise ValueError(f"VNI must be 1-16777215, got {self.vni_id}")

        if self.vlan_id is not None and not 1 <= self.vlan_id <= 4094:
            raise ValueError(f"VLAN must be 1-4094, got {self.vlan_id}")

    def is_l2vni(self) -> bool:
        """Check if this is an L2 VNI"""
        return self.vni_type == VNIType.L2VNI

    def is_l3vni(self) -> bool:
        """Check if this is an L3 VNI"""
        return self.vni_type == VNIType.L3VNI

    def add_learned_mac(self, mac: str, vtep_ip: str) -> None:
        """Record learned MAC address"""
        self.learned_macs[mac.upper()] = vtep_ip

    def remove_learned_mac(self, mac: str) -> None:
        """Remove learned MAC address"""
        self.learned_macs.pop(mac.upper(), None)

    def get_vtep_for_mac(self, mac: str) -> Optional[str]:
        """Get VTEP IP for a MAC address"""
        return self.learned_macs.get(mac.upper())

    def add_learned_ip(self, ip: str, mac: str) -> None:
        """Record learned IP to MAC binding"""
        self.learned_ips[ip] = mac.upper()

    def get_mac_for_ip(self, ip: str) -> Optional[str]:
        """Get MAC address for an IP"""
        return self.learned_ips.get(ip)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "vni_id": self.vni_id,
            "vni_type": self.vni_type.value,
            "vlan_id": self.vlan_id,
            "vrf_name": self.vrf_name,
            "rd": self.rd,
            "rt_import": self.rt_import,
            "rt_export": self.rt_export,
            "anycast_gateway_ip": self.anycast_gateway_ip,
            "anycast_gateway_mac": self.anycast_gateway_mac,
            "mcast_group": self.mcast_group,
            "learned_macs": len(self.learned_macs),
            "learned_ips": len(self.learned_ips),
            "packets_encap": self.packets_encap,
            "packets_decap": self.packets_decap,
        }


class VNIManager:
    """
    Manages VNI allocation and configuration.

    Provides centralized management of VXLAN network identifiers
    including allocation, VLAN mapping, and VRF association.
    """

    def __init__(self):
        """Initialize VNI manager"""
        # VNI storage: {vni_id: VNI}
        self._vnis: Dict[int, VNI] = {}

        # Mappings
        self._vlan_to_vni: Dict[int, int] = {}
        self._vrf_to_vni: Dict[str, int] = {}

        # Available VNI pool
        self._vni_pool: Set[int] = set(range(1, 16777216))

        self.logger = logging.getLogger("VNIManager")

    def create_l2vni(
        self,
        vni_id: int,
        vlan_id: Optional[int] = None,
        rd: Optional[str] = None,
        rt_import: Optional[List[str]] = None,
        rt_export: Optional[List[str]] = None,
        anycast_gateway_ip: Optional[str] = None,
        anycast_gateway_mac: Optional[str] = None,
        mcast_group: Optional[str] = None,
    ) -> VNI:
        """
        Create an L2 VNI for bridging.

        Args:
            vni_id: VNI value
            vlan_id: Associated VLAN ID
            rd: Route Distinguisher for EVPN
            rt_import: Import Route Targets
            rt_export: Export Route Targets
            anycast_gateway_ip: Anycast gateway IP
            anycast_gateway_mac: Anycast gateway MAC
            mcast_group: Multicast group for BUM

        Returns:
            Created VNI
        """
        if vni_id in self._vnis:
            raise ValueError(f"VNI {vni_id} already exists")

        if vlan_id and vlan_id in self._vlan_to_vni:
            raise ValueError(f"VLAN {vlan_id} already mapped to VNI {self._vlan_to_vni[vlan_id]}")

        vni = VNI(
            vni_id=vni_id,
            vni_type=VNIType.L2VNI,
            vlan_id=vlan_id,
            rd=rd,
            rt_import=rt_import or [],
            rt_export=rt_export or [],
            anycast_gateway_ip=anycast_gateway_ip,
            anycast_gateway_mac=anycast_gateway_mac,
            mcast_group=mcast_group,
        )

        self._vnis[vni_id] = vni
        self._vni_pool.discard(vni_id)

        if vlan_id:
            self._vlan_to_vni[vlan_id] = vni_id

        self.logger.info(f"Created L2VNI {vni_id}" + (f" for VLAN {vlan_id}" if vlan_id else ""))

        return vni

    def create_l3vni(
        self,
        vni_id: int,
        vrf_name: str,
        rd: Optional[str] = None,
        rt_import: Optional[List[str]] = None,
        rt_export: Optional[List[str]] = None,
    ) -> VNI:
        """
        Create an L3 VNI for inter-VXLAN routing.

        Args:
            vni_id: VNI value
            vrf_name: VRF name
            rd: Route Distinguisher
            rt_import: Import Route Targets
            rt_export: Export Route Targets

        Returns:
            Created VNI
        """
        if vni_id in self._vnis:
            raise ValueError(f"VNI {vni_id} already exists")

        if vrf_name in self._vrf_to_vni:
            raise ValueError(f"VRF {vrf_name} already has L3VNI {self._vrf_to_vni[vrf_name]}")

        vni = VNI(
            vni_id=vni_id,
            vni_type=VNIType.L3VNI,
            vrf_name=vrf_name,
            rd=rd,
            rt_import=rt_import or [],
            rt_export=rt_export or [],
        )

        self._vnis[vni_id] = vni
        self._vni_pool.discard(vni_id)
        self._vrf_to_vni[vrf_name] = vni_id

        self.logger.info(f"Created L3VNI {vni_id} for VRF {vrf_name}")

        return vni

    def get_vni(self, vni_id: int) -> Optional[VNI]:
        """Get VNI by ID"""
        return self._vnis.get(vni_id)

    def get_vni_for_vlan(self, vlan_id: int) -> Optional[VNI]:
        """Get VNI mapped to VLAN"""
        vni_id = self._vlan_to_vni.get(vlan_id)
        return self._vnis.get(vni_id) if vni_id else None

    def get_vni_for_vrf(self, vrf_name: str) -> Optional[VNI]:
        """Get L3VNI for VRF"""
        vni_id = self._vrf_to_vni.get(vrf_name)
        return self._vnis.get(vni_id) if vni_id else None

    def delete_vni(self, vni_id: int) -> bool:
        """
        Delete a VNI.

        Args:
            vni_id: VNI to delete

        Returns:
            True if deleted
        """
        vni = self._vnis.get(vni_id)
        if not vni:
            return False

        # Clean up mappings
        if vni.vlan_id:
            self._vlan_to_vni.pop(vni.vlan_id, None)
        if vni.vrf_name:
            self._vrf_to_vni.pop(vni.vrf_name, None)

        del self._vnis[vni_id]
        self._vni_pool.add(vni_id)

        self.logger.info(f"Deleted VNI {vni_id}")
        return True

    def allocate_vni(self) -> int:
        """
        Allocate next available VNI.

        Returns:
            Allocated VNI ID
        """
        if not self._vni_pool:
            raise ValueError("No VNIs available")

        vni_id = min(self._vni_pool)
        self._vni_pool.discard(vni_id)
        return vni_id

    def release_vni(self, vni_id: int) -> None:
        """Release VNI back to pool"""
        if vni_id not in self._vnis:
            self._vni_pool.add(vni_id)

    def get_all_vnis(self) -> List[VNI]:
        """Get all configured VNIs"""
        return list(self._vnis.values())

    def get_l2vnis(self) -> List[VNI]:
        """Get all L2 VNIs"""
        return [v for v in self._vnis.values() if v.is_l2vni()]

    def get_l3vnis(self) -> List[VNI]:
        """Get all L3 VNIs"""
        return [v for v in self._vnis.values() if v.is_l3vni()]

    def get_statistics(self) -> Dict[str, Any]:
        """Get VNI manager statistics"""
        return {
            "total_vnis": len(self._vnis),
            "l2vnis": len(self.get_l2vnis()),
            "l3vnis": len(self.get_l3vnis()),
            "vlan_mappings": len(self._vlan_to_vni),
            "vrf_mappings": len(self._vrf_to_vni),
            "available_vnis": len(self._vni_pool),
        }
