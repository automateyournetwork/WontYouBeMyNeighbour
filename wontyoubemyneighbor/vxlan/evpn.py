"""
EVPN (Ethernet VPN) Control Plane

Implements BGP EVPN for VXLAN control plane operations
as per RFC 7432 and RFC 8365.

EVPN Route Types:
- Type 2: MAC/IP Advertisement
- Type 3: Inclusive Multicast Ethernet Tag
- Type 5: IP Prefix Route (for L3VNI)
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Tuple
from enum import Enum
from datetime import datetime


class EVPNRouteType(Enum):
    """EVPN Route Types per RFC 7432"""
    ETHERNET_AD = 1           # Ethernet Auto-Discovery
    MAC_IP_ADVERTISEMENT = 2  # MAC/IP Advertisement
    INCLUSIVE_MCAST = 3       # Inclusive Multicast Ethernet Tag
    ETHERNET_SEGMENT = 4      # Ethernet Segment
    IP_PREFIX = 5             # IP Prefix Route


@dataclass
class RouteDistinguisher:
    """
    Route Distinguisher for EVPN routes.

    Format: <admin>:<assigned> where admin is AS or IP
    """
    admin: str        # Admin field (AS number or IP)
    assigned: int     # Assigned number
    rd_type: int = 1  # 0=AS2:4byte, 1=IP:2byte, 2=AS4:2byte

    def __str__(self) -> str:
        return f"{self.admin}:{self.assigned}"

    @classmethod
    def from_string(cls, rd_str: str) -> 'RouteDistinguisher':
        """Parse RD from string format"""
        parts = rd_str.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid RD format: {rd_str}")

        admin = parts[0]
        assigned = int(parts[1])

        # Determine type based on admin format
        rd_type = 1 if "." in admin else 0

        return cls(admin=admin, assigned=assigned, rd_type=rd_type)


@dataclass
class RouteTarget:
    """
    Route Target for EVPN import/export.

    Format: <admin>:<assigned>
    """
    admin: str
    assigned: int

    def __str__(self) -> str:
        return f"{self.admin}:{self.assigned}"

    @classmethod
    def from_string(cls, rt_str: str) -> 'RouteTarget':
        """Parse RT from string"""
        parts = rt_str.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid RT format: {rt_str}")
        return cls(admin=parts[0], assigned=int(parts[1]))


@dataclass
class MACIPRoute:
    """
    EVPN Type 2: MAC/IP Advertisement Route.

    Advertises MAC address and optionally IP address
    reachability information.
    """
    rd: str                          # Route Distinguisher
    ethernet_tag: int = 0            # Ethernet Tag ID (VNI)
    mac_address: str = ""            # MAC address
    mac_length: int = 48             # MAC address length in bits
    ip_address: Optional[str] = None # Optional IP address
    ip_length: int = 0               # IP address length in bits
    mpls_label1: int = 0             # L2 VNI (as MPLS label)
    mpls_label2: Optional[int] = None  # L3 VNI (optional)
    esi: str = "0"                   # Ethernet Segment Identifier
    route_targets: List[str] = field(default_factory=list)

    # Metadata
    origin_vtep: Optional[str] = None
    received_from: Optional[str] = None
    timestamp: Optional[datetime] = None

    @property
    def route_type(self) -> EVPNRouteType:
        return EVPNRouteType.MAC_IP_ADVERTISEMENT

    @property
    def vni(self) -> int:
        """Get VNI from MPLS label"""
        return self.mpls_label1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "type": self.route_type.value,
            "rd": self.rd,
            "ethernet_tag": self.ethernet_tag,
            "mac_address": self.mac_address,
            "ip_address": self.ip_address,
            "vni": self.vni,
            "l3_vni": self.mpls_label2,
            "esi": self.esi,
            "route_targets": self.route_targets,
            "origin_vtep": self.origin_vtep,
        }


@dataclass
class InclusiveMulticastRoute:
    """
    EVPN Type 3: Inclusive Multicast Ethernet Tag Route.

    Used for discovering VTEPs participating in a VNI
    and building flood lists for BUM traffic.
    """
    rd: str                          # Route Distinguisher
    ethernet_tag: int                # Ethernet Tag ID (VNI)
    originator_ip: str               # Originating VTEP IP
    route_targets: List[str] = field(default_factory=list)

    # Tunnel type
    tunnel_type: str = "vxlan"       # vxlan, vxlan-gpe, etc.

    # Metadata
    received_from: Optional[str] = None
    timestamp: Optional[datetime] = None

    @property
    def route_type(self) -> EVPNRouteType:
        return EVPNRouteType.INCLUSIVE_MCAST

    @property
    def vni(self) -> int:
        return self.ethernet_tag

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "type": self.route_type.value,
            "rd": self.rd,
            "vni": self.vni,
            "originator_ip": self.originator_ip,
            "tunnel_type": self.tunnel_type,
            "route_targets": self.route_targets,
        }


@dataclass
class IPPrefixRoute:
    """
    EVPN Type 5: IP Prefix Route.

    Used for advertising IP prefixes for L3VNI routing.
    """
    rd: str                          # Route Distinguisher
    ethernet_tag: int                # Ethernet Tag ID (L3 VNI)
    ip_prefix: str                   # IP prefix (e.g., "10.0.0.0/24")
    ip_prefix_length: int            # Prefix length
    gateway_ip: str                  # Gateway IP (VTEP IP)
    mpls_label: int                  # L3 VNI
    route_targets: List[str] = field(default_factory=list)

    # Metadata
    received_from: Optional[str] = None
    timestamp: Optional[datetime] = None

    @property
    def route_type(self) -> EVPNRouteType:
        return EVPNRouteType.IP_PREFIX

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.route_type.value,
            "rd": self.rd,
            "ethernet_tag": self.ethernet_tag,
            "ip_prefix": self.ip_prefix,
            "gateway_ip": self.gateway_ip,
            "l3_vni": self.mpls_label,
            "route_targets": self.route_targets,
        }


class EVPNInstance:
    """
    EVPN Instance (EVI) management.

    An EVI represents a single EVPN domain with its own
    RD, RTs, and VNI mappings.
    """

    def __init__(
        self,
        evi_id: int,
        rd: str,
        rt_import: List[str],
        rt_export: List[str],
        vni: int,
        local_vtep_ip: str,
    ):
        """
        Initialize EVPN Instance.

        Args:
            evi_id: EVI identifier
            rd: Route Distinguisher
            rt_import: Import Route Targets
            rt_export: Export Route Targets
            vni: VNI for this EVI
            local_vtep_ip: Local VTEP IP address
        """
        self.evi_id = evi_id
        self.rd = rd
        self.rt_import = [RouteTarget.from_string(rt) for rt in rt_import]
        self.rt_export = [RouteTarget.from_string(rt) for rt in rt_export]
        self.vni = vni
        self.local_vtep_ip = local_vtep_ip

        # Route tables
        self._mac_ip_routes: Dict[str, MACIPRoute] = {}  # {mac: route}
        self._imet_routes: Dict[str, InclusiveMulticastRoute] = {}  # {vtep_ip: route}
        self._prefix_routes: Dict[str, IPPrefixRoute] = {}  # {prefix: route}

        # Local MACs
        self._local_macs: Set[str] = set()

        self.logger = logging.getLogger(f"EVI[{evi_id}]")

    def add_local_mac(self, mac: str, ip: Optional[str] = None) -> MACIPRoute:
        """
        Add locally learned MAC/IP.

        Args:
            mac: MAC address
            ip: Optional IP address

        Returns:
            Generated MAC/IP route for advertisement
        """
        mac = mac.upper()
        self._local_macs.add(mac)

        route = MACIPRoute(
            rd=self.rd,
            ethernet_tag=self.vni,
            mac_address=mac,
            ip_address=ip,
            ip_length=32 if ip else 0,
            mpls_label1=self.vni,
            route_targets=[str(rt) for rt in self.rt_export],
            origin_vtep=self.local_vtep_ip,
            timestamp=datetime.now(),
        )

        self._mac_ip_routes[mac] = route
        self.logger.debug(f"Added local MAC {mac}" + (f" IP {ip}" if ip else ""))

        return route

    def remove_local_mac(self, mac: str) -> Optional[MACIPRoute]:
        """
        Remove locally learned MAC.

        Args:
            mac: MAC address

        Returns:
            Route to withdraw or None
        """
        mac = mac.upper()
        self._local_macs.discard(mac)

        route = self._mac_ip_routes.pop(mac, None)
        if route:
            self.logger.debug(f"Removed local MAC {mac}")

        return route

    def process_mac_ip_route(self, route: MACIPRoute) -> bool:
        """
        Process received MAC/IP route.

        Args:
            route: Received route

        Returns:
            True if route was accepted
        """
        # Check RT import
        if not self._check_rt_import(route.route_targets):
            return False

        # Check VNI match
        if route.vni != self.vni:
            return False

        mac = route.mac_address.upper()

        # Don't overwrite local MACs
        if mac in self._local_macs:
            return False

        self._mac_ip_routes[mac] = route
        self.logger.debug(f"Learned MAC {mac} from VTEP {route.origin_vtep}")

        return True

    def withdraw_mac_ip_route(self, mac: str) -> bool:
        """
        Process MAC/IP route withdrawal.

        Args:
            mac: MAC address being withdrawn

        Returns:
            True if route was removed
        """
        mac = mac.upper()

        # Don't remove local MACs
        if mac in self._local_macs:
            return False

        if mac in self._mac_ip_routes:
            del self._mac_ip_routes[mac]
            self.logger.debug(f"Withdrawn MAC {mac}")
            return True

        return False

    def generate_imet_route(self) -> InclusiveMulticastRoute:
        """
        Generate IMET route for this EVI.

        Returns:
            IMET route for advertisement
        """
        return InclusiveMulticastRoute(
            rd=self.rd,
            ethernet_tag=self.vni,
            originator_ip=self.local_vtep_ip,
            route_targets=[str(rt) for rt in self.rt_export],
            timestamp=datetime.now(),
        )

    def process_imet_route(self, route: InclusiveMulticastRoute) -> bool:
        """
        Process received IMET route.

        Args:
            route: Received route

        Returns:
            True if route was accepted
        """
        # Check RT import
        if not self._check_rt_import(route.route_targets):
            return False

        # Check VNI match
        if route.vni != self.vni:
            return False

        # Don't add ourselves
        if route.originator_ip == self.local_vtep_ip:
            return False

        self._imet_routes[route.originator_ip] = route
        self.logger.debug(f"Discovered VTEP {route.originator_ip} for VNI {route.vni}")

        return True

    def withdraw_imet_route(self, vtep_ip: str) -> bool:
        """
        Process IMET route withdrawal.

        Args:
            vtep_ip: VTEP IP being withdrawn

        Returns:
            True if route was removed
        """
        if vtep_ip in self._imet_routes:
            del self._imet_routes[vtep_ip]
            self.logger.debug(f"VTEP {vtep_ip} withdrawn from VNI {self.vni}")
            return True
        return False

    def _check_rt_import(self, route_rts: List[str]) -> bool:
        """Check if any RT matches import policy"""
        import_strs = {str(rt) for rt in self.rt_import}
        return bool(import_strs & set(route_rts))

    def get_remote_vteps(self) -> List[str]:
        """Get list of remote VTEPs for this VNI"""
        return list(self._imet_routes.keys())

    def get_mac_for_vtep(self, mac: str) -> Optional[str]:
        """Get VTEP IP for a MAC address"""
        route = self._mac_ip_routes.get(mac.upper())
        return route.origin_vtep if route else None

    def get_all_mac_routes(self) -> List[MACIPRoute]:
        """Get all MAC/IP routes"""
        return list(self._mac_ip_routes.values())

    def get_local_mac_routes(self) -> List[MACIPRoute]:
        """Get locally originated MAC routes"""
        return [
            route for mac, route in self._mac_ip_routes.items()
            if mac in self._local_macs
        ]

    def get_statistics(self) -> Dict[str, Any]:
        """Get EVI statistics"""
        return {
            "evi_id": self.evi_id,
            "rd": self.rd,
            "vni": self.vni,
            "local_vtep": self.local_vtep_ip,
            "mac_routes": len(self._mac_ip_routes),
            "local_macs": len(self._local_macs),
            "remote_vteps": len(self._imet_routes),
            "rt_import": [str(rt) for rt in self.rt_import],
            "rt_export": [str(rt) for rt in self.rt_export],
        }


class EVPNManager:
    """
    Manages multiple EVPN Instances.

    Provides centralized EVPN control plane operations
    including route processing and advertisement.
    """

    def __init__(self, local_vtep_ip: str, router_id: str):
        """
        Initialize EVPN Manager.

        Args:
            local_vtep_ip: Local VTEP IP address
            router_id: BGP router ID
        """
        self.local_vtep_ip = local_vtep_ip
        self.router_id = router_id

        # EVIs: {evi_id: EVPNInstance}
        self._evis: Dict[int, EVPNInstance] = {}

        # VNI to EVI mapping
        self._vni_to_evi: Dict[int, int] = {}

        self.logger = logging.getLogger("EVPNManager")

    def create_evi(
        self,
        evi_id: int,
        vni: int,
        rd: Optional[str] = None,
        rt_import: Optional[List[str]] = None,
        rt_export: Optional[List[str]] = None,
    ) -> EVPNInstance:
        """
        Create EVPN Instance.

        Args:
            evi_id: EVI identifier
            vni: VNI for this EVI
            rd: Route Distinguisher (auto-generated if None)
            rt_import: Import RTs (auto-generated if None)
            rt_export: Export RTs (auto-generated if None)

        Returns:
            Created EVI
        """
        if evi_id in self._evis:
            raise ValueError(f"EVI {evi_id} already exists")

        # Auto-generate RD: router_id:evi_id
        if rd is None:
            rd = f"{self.router_id}:{evi_id}"

        # Auto-generate RTs: router_id:vni
        if rt_import is None:
            rt_import = [f"{self.router_id}:{vni}"]
        if rt_export is None:
            rt_export = [f"{self.router_id}:{vni}"]

        evi = EVPNInstance(
            evi_id=evi_id,
            rd=rd,
            rt_import=rt_import,
            rt_export=rt_export,
            vni=vni,
            local_vtep_ip=self.local_vtep_ip,
        )

        self._evis[evi_id] = evi
        self._vni_to_evi[vni] = evi_id

        self.logger.info(f"Created EVI {evi_id} for VNI {vni}")

        return evi

    def delete_evi(self, evi_id: int) -> bool:
        """
        Delete EVPN Instance.

        Args:
            evi_id: EVI to delete

        Returns:
            True if deleted
        """
        evi = self._evis.pop(evi_id, None)
        if not evi:
            return False

        self._vni_to_evi.pop(evi.vni, None)
        self.logger.info(f"Deleted EVI {evi_id}")
        return True

    def get_evi(self, evi_id: int) -> Optional[EVPNInstance]:
        """Get EVI by ID"""
        return self._evis.get(evi_id)

    def get_evi_for_vni(self, vni: int) -> Optional[EVPNInstance]:
        """Get EVI for VNI"""
        evi_id = self._vni_to_evi.get(vni)
        return self._evis.get(evi_id) if evi_id else None

    def process_route(self, route) -> bool:
        """
        Process received EVPN route.

        Args:
            route: EVPN route (Type 2, 3, or 5)

        Returns:
            True if route was accepted by any EVI
        """
        accepted = False

        for evi in self._evis.values():
            if isinstance(route, MACIPRoute):
                if evi.process_mac_ip_route(route):
                    accepted = True
            elif isinstance(route, InclusiveMulticastRoute):
                if evi.process_imet_route(route):
                    accepted = True
            elif isinstance(route, IPPrefixRoute):
                # Process prefix route for L3VNI
                pass

        return accepted

    def get_all_local_routes(self) -> List:
        """Get all locally originated routes for advertisement"""
        routes = []

        for evi in self._evis.values():
            # IMET route
            routes.append(evi.generate_imet_route())

            # MAC/IP routes
            routes.extend(evi.get_local_mac_routes())

        return routes

    def get_statistics(self) -> Dict[str, Any]:
        """Get EVPN manager statistics"""
        total_macs = sum(
            len(evi._mac_ip_routes) for evi in self._evis.values()
        )
        total_vteps = sum(
            len(evi._imet_routes) for evi in self._evis.values()
        )

        return {
            "local_vtep": self.local_vtep_ip,
            "router_id": self.router_id,
            "total_evis": len(self._evis),
            "total_mac_routes": total_macs,
            "total_remote_vteps": total_vteps,
            "evis": {
                evi_id: evi.get_statistics()
                for evi_id, evi in self._evis.items()
            },
        }
