"""
Multi-Vendor Network Simulation Manager

Simulates different network equipment vendors with their specific:
- CLI syntax and commands
- Default behaviors
- Protocol implementations
- Operational characteristics
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class VendorCapability(Enum):
    """Vendor capability flags."""
    # Routing protocols
    OSPF = "ospf"
    OSPFV3 = "ospfv3"
    BGP = "bgp"
    ISIS = "isis"
    RIP = "rip"
    EIGRP = "eigrp"

    # Switching
    VLAN = "vlan"
    STP = "stp"
    RSTP = "rstp"
    MSTP = "mstp"
    LACP = "lacp"
    LLDP = "lldp"

    # MPLS/VPN
    MPLS = "mpls"
    MPLS_TE = "mpls_te"
    L3VPN = "l3vpn"
    L2VPN = "l2vpn"
    EVPN = "evpn"
    VXLAN = "vxlan"

    # Security
    ACL = "acl"
    FIREWALL = "firewall"
    IPSEC = "ipsec"
    MACSEC = "macsec"

    # Management
    NETCONF = "netconf"
    RESTCONF = "restconf"
    SNMP = "snmp"
    STREAMING_TELEMETRY = "streaming_telemetry"

    # High Availability
    VRRP = "vrrp"
    HSRP = "hsrp"
    BFD = "bfd"
    NSF = "nsf"
    SSO = "sso"

    # Segment Routing
    SR_MPLS = "sr_mpls"
    SRV6 = "srv6"


@dataclass
class CLISyntax:
    """CLI syntax definition for a vendor."""
    # Basic commands
    show_version: str = "show version"
    show_interfaces: str = "show interfaces"
    show_ip_route: str = "show ip route"
    show_ipv6_route: str = "show ipv6 route"
    show_running_config: str = "show running-config"

    # OSPF commands
    show_ospf_neighbors: str = "show ip ospf neighbor"
    show_ospf_routes: str = "show ip ospf route"
    show_ospf_database: str = "show ip ospf database"

    # BGP commands
    show_bgp_summary: str = "show ip bgp summary"
    show_bgp_neighbors: str = "show ip bgp neighbors"
    show_bgp_routes: str = "show ip bgp"

    # Interface commands
    interface_config: str = "interface {interface}"
    ip_address: str = "ip address {ip} {mask}"
    ipv6_address: str = "ipv6 address {ip}/{prefix}"
    shutdown: str = "shutdown"
    no_shutdown: str = "no shutdown"

    # Routing config
    router_ospf: str = "router ospf {process}"
    router_bgp: str = "router bgp {asn}"
    network_statement: str = "network {prefix} area {area}"

    # Config mode
    config_mode: str = "configure terminal"
    exit_config: str = "end"
    commit: str = ""  # Some vendors need explicit commit

    # Prompts
    exec_prompt: str = ">"
    privileged_prompt: str = "#"
    config_prompt: str = "(config)#"

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary."""
        return {
            "show_version": self.show_version,
            "show_interfaces": self.show_interfaces,
            "show_ip_route": self.show_ip_route,
            "show_ipv6_route": self.show_ipv6_route,
            "show_running_config": self.show_running_config,
            "show_ospf_neighbors": self.show_ospf_neighbors,
            "show_ospf_routes": self.show_ospf_routes,
            "show_ospf_database": self.show_ospf_database,
            "show_bgp_summary": self.show_bgp_summary,
            "show_bgp_neighbors": self.show_bgp_neighbors,
            "show_bgp_routes": self.show_bgp_routes,
            "interface_config": self.interface_config,
            "ip_address": self.ip_address,
            "ipv6_address": self.ipv6_address,
            "shutdown": self.shutdown,
            "no_shutdown": self.no_shutdown,
            "router_ospf": self.router_ospf,
            "router_bgp": self.router_bgp,
            "network_statement": self.network_statement,
            "config_mode": self.config_mode,
            "exit_config": self.exit_config,
            "commit": self.commit,
            "exec_prompt": self.exec_prompt,
            "privileged_prompt": self.privileged_prompt,
            "config_prompt": self.config_prompt,
        }


@dataclass
class VendorProfile:
    """Behavioral profile for a vendor."""
    # Timing characteristics
    boot_time_seconds: int = 30          # Time to boot
    ospf_default_dead_interval: int = 40  # OSPF dead timer
    ospf_default_hello_interval: int = 10
    bgp_default_hold_time: int = 180
    bgp_default_keepalive: int = 60

    # Default settings
    default_mtu: int = 1500
    default_ospf_cost: int = 10
    default_bgp_med: int = 0

    # Behavior quirks
    auto_cost_reference_bandwidth: int = 100  # Mbps
    supports_ipv6_default: bool = True
    requires_enable_password: bool = True
    config_commit_required: bool = False
    case_sensitive_commands: bool = False

    # Memory/CPU simulation
    max_routes: int = 100000
    max_bgp_peers: int = 100
    max_ospf_neighbors: int = 50

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "boot_time_seconds": self.boot_time_seconds,
            "ospf_default_dead_interval": self.ospf_default_dead_interval,
            "ospf_default_hello_interval": self.ospf_default_hello_interval,
            "bgp_default_hold_time": self.bgp_default_hold_time,
            "bgp_default_keepalive": self.bgp_default_keepalive,
            "default_mtu": self.default_mtu,
            "default_ospf_cost": self.default_ospf_cost,
            "default_bgp_med": self.default_bgp_med,
            "auto_cost_reference_bandwidth": self.auto_cost_reference_bandwidth,
            "supports_ipv6_default": self.supports_ipv6_default,
            "requires_enable_password": self.requires_enable_password,
            "config_commit_required": self.config_commit_required,
            "case_sensitive_commands": self.case_sensitive_commands,
            "max_routes": self.max_routes,
            "max_bgp_peers": self.max_bgp_peers,
            "max_ospf_neighbors": self.max_ospf_neighbors,
        }


@dataclass
class Vendor:
    """A network equipment vendor definition."""
    vendor_id: str
    name: str
    display_name: str
    description: str = ""
    logo_url: str = ""
    capabilities: Set[VendorCapability] = field(default_factory=set)
    cli_syntax: CLISyntax = field(default_factory=CLISyntax)
    profile: VendorProfile = field(default_factory=VendorProfile)
    os_name: str = ""       # e.g., "IOS", "NX-OS", "Junos"
    os_version: str = ""    # e.g., "15.1", "10.2", "21.4"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "vendor_id": self.vendor_id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "logo_url": self.logo_url,
            "capabilities": [c.value for c in self.capabilities],
            "cli_syntax": self.cli_syntax.to_dict(),
            "profile": self.profile.to_dict(),
            "os_name": self.os_name,
            "os_version": self.os_version,
        }

    def has_capability(self, capability: VendorCapability) -> bool:
        """Check if vendor supports a capability."""
        return capability in self.capabilities

    def get_command(self, command_type: str, **kwargs) -> str:
        """Get vendor-specific command with substitution."""
        cmd_template = getattr(self.cli_syntax, command_type, None)
        if cmd_template is None:
            return f"# Unknown command: {command_type}"
        return cmd_template.format(**kwargs) if kwargs else cmd_template


class VendorManager:
    """
    Multi-vendor simulation manager.

    Provides vendor profiles, CLI syntax, and behavioral characteristics
    for simulating different network equipment manufacturers.
    """

    # Singleton instance
    _instance: Optional["VendorManager"] = None

    def __new__(cls) -> "VendorManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._vendors: Dict[str, Vendor] = {}

        # Register built-in vendors
        self._register_default_vendors()

        logger.info(f"VendorManager initialized with {len(self._vendors)} vendors")

    def _register_default_vendors(self):
        """Register default vendor profiles."""

        # Cisco IOS/IOS-XE
        cisco_ios = Vendor(
            vendor_id="cisco-ios",
            name="cisco",
            display_name="Cisco IOS",
            description="Cisco IOS and IOS-XE based routers and switches",
            os_name="IOS-XE",
            os_version="17.6",
            capabilities={
                VendorCapability.OSPF, VendorCapability.OSPFV3,
                VendorCapability.BGP, VendorCapability.ISIS,
                VendorCapability.EIGRP, VendorCapability.RIP,
                VendorCapability.VLAN, VendorCapability.STP,
                VendorCapability.RSTP, VendorCapability.LACP,
                VendorCapability.LLDP, VendorCapability.MPLS,
                VendorCapability.L3VPN, VendorCapability.ACL,
                VendorCapability.VRRP, VendorCapability.HSRP,
                VendorCapability.BFD, VendorCapability.NETCONF,
                VendorCapability.RESTCONF, VendorCapability.SNMP,
            },
            cli_syntax=CLISyntax(
                show_version="show version",
                show_interfaces="show ip interface brief",
                show_ip_route="show ip route",
                show_ipv6_route="show ipv6 route",
                show_running_config="show running-config",
                show_ospf_neighbors="show ip ospf neighbor",
                show_ospf_routes="show ip ospf route",
                show_ospf_database="show ip ospf database",
                show_bgp_summary="show ip bgp summary",
                show_bgp_neighbors="show ip bgp neighbors",
                show_bgp_routes="show ip bgp",
                interface_config="interface {interface}",
                ip_address="ip address {ip} {mask}",
                ipv6_address="ipv6 address {ip}/{prefix}",
                shutdown="shutdown",
                no_shutdown="no shutdown",
                router_ospf="router ospf {process}",
                router_bgp="router bgp {asn}",
                network_statement="network {prefix} area {area}",
                config_mode="configure terminal",
                exit_config="end",
                commit="",
                exec_prompt=">",
                privileged_prompt="#",
                config_prompt="(config)#",
            ),
            profile=VendorProfile(
                boot_time_seconds=60,
                ospf_default_dead_interval=40,
                ospf_default_hello_interval=10,
                bgp_default_hold_time=180,
                bgp_default_keepalive=60,
                auto_cost_reference_bandwidth=100,
                requires_enable_password=True,
                config_commit_required=False,
            ),
        )
        self._vendors["cisco-ios"] = cisco_ios

        # Cisco NX-OS
        cisco_nxos = Vendor(
            vendor_id="cisco-nxos",
            name="cisco",
            display_name="Cisco NX-OS",
            description="Cisco Nexus data center switches",
            os_name="NX-OS",
            os_version="10.2",
            capabilities={
                VendorCapability.OSPF, VendorCapability.OSPFV3,
                VendorCapability.BGP, VendorCapability.ISIS,
                VendorCapability.VLAN, VendorCapability.STP,
                VendorCapability.RSTP, VendorCapability.LACP,
                VendorCapability.LLDP, VendorCapability.VXLAN,
                VendorCapability.EVPN, VendorCapability.ACL,
                VendorCapability.VRRP, VendorCapability.BFD,
                VendorCapability.NETCONF, VendorCapability.RESTCONF,
                VendorCapability.SNMP, VendorCapability.STREAMING_TELEMETRY,
            },
            cli_syntax=CLISyntax(
                show_version="show version",
                show_interfaces="show interface brief",
                show_ip_route="show ip route",
                show_ipv6_route="show ipv6 route",
                show_running_config="show running-config",
                show_ospf_neighbors="show ip ospf neighbors",
                show_ospf_routes="show ip ospf route",
                show_ospf_database="show ip ospf database",
                show_bgp_summary="show bgp ipv4 unicast summary",
                show_bgp_neighbors="show bgp ipv4 unicast neighbors",
                show_bgp_routes="show bgp ipv4 unicast",
                interface_config="interface {interface}",
                ip_address="ip address {ip}/{prefix}",
                ipv6_address="ipv6 address {ip}/{prefix}",
                shutdown="shutdown",
                no_shutdown="no shutdown",
                router_ospf="router ospf {process}",
                router_bgp="router bgp {asn}",
                network_statement="network {prefix} area {area}",
                config_mode="configure terminal",
                exit_config="end",
                commit="",
                exec_prompt=">",
                privileged_prompt="#",
                config_prompt="(config)#",
            ),
            profile=VendorProfile(
                boot_time_seconds=120,
                ospf_default_dead_interval=40,
                auto_cost_reference_bandwidth=40000,  # 40 Gbps reference
                requires_enable_password=False,
                config_commit_required=False,
                max_routes=500000,
                max_bgp_peers=500,
            ),
        )
        self._vendors["cisco-nxos"] = cisco_nxos

        # Juniper Junos
        juniper_junos = Vendor(
            vendor_id="juniper-junos",
            name="juniper",
            display_name="Juniper Junos",
            description="Juniper Networks routers and switches",
            os_name="Junos",
            os_version="22.4R1",
            capabilities={
                VendorCapability.OSPF, VendorCapability.OSPFV3,
                VendorCapability.BGP, VendorCapability.ISIS,
                VendorCapability.RIP, VendorCapability.VLAN,
                VendorCapability.RSTP, VendorCapability.LACP,
                VendorCapability.LLDP, VendorCapability.MPLS,
                VendorCapability.MPLS_TE, VendorCapability.L3VPN,
                VendorCapability.L2VPN, VendorCapability.EVPN,
                VendorCapability.ACL, VendorCapability.FIREWALL,
                VendorCapability.VRRP, VendorCapability.BFD,
                VendorCapability.NSF, VendorCapability.NETCONF,
                VendorCapability.RESTCONF, VendorCapability.SNMP,
                VendorCapability.SR_MPLS, VendorCapability.SRV6,
            },
            cli_syntax=CLISyntax(
                show_version="show version",
                show_interfaces="show interfaces terse",
                show_ip_route="show route",
                show_ipv6_route="show route table inet6.0",
                show_running_config="show configuration",
                show_ospf_neighbors="show ospf neighbor",
                show_ospf_routes="show ospf route",
                show_ospf_database="show ospf database",
                show_bgp_summary="show bgp summary",
                show_bgp_neighbors="show bgp neighbor",
                show_bgp_routes="show route protocol bgp",
                interface_config="set interfaces {interface}",
                ip_address="set interfaces {interface} unit 0 family inet address {ip}/{prefix}",
                ipv6_address="set interfaces {interface} unit 0 family inet6 address {ip}/{prefix}",
                shutdown="set interfaces {interface} disable",
                no_shutdown="delete interfaces {interface} disable",
                router_ospf="set protocols ospf",
                router_bgp="set protocols bgp group {group}",
                network_statement="set protocols ospf area {area} interface {interface}",
                config_mode="configure",
                exit_config="exit",
                commit="commit",
                exec_prompt=">",
                privileged_prompt=">",
                config_prompt="#",
            ),
            profile=VendorProfile(
                boot_time_seconds=90,
                ospf_default_dead_interval=40,
                ospf_default_hello_interval=10,
                bgp_default_hold_time=90,
                bgp_default_keepalive=30,
                auto_cost_reference_bandwidth=100,
                requires_enable_password=False,
                config_commit_required=True,
                case_sensitive_commands=True,
            ),
        )
        self._vendors["juniper-junos"] = juniper_junos

        # Arista EOS
        arista_eos = Vendor(
            vendor_id="arista-eos",
            name="arista",
            display_name="Arista EOS",
            description="Arista Networks data center switches",
            os_name="EOS",
            os_version="4.28",
            capabilities={
                VendorCapability.OSPF, VendorCapability.OSPFV3,
                VendorCapability.BGP, VendorCapability.ISIS,
                VendorCapability.VLAN, VendorCapability.STP,
                VendorCapability.RSTP, VendorCapability.MSTP,
                VendorCapability.LACP, VendorCapability.LLDP,
                VendorCapability.VXLAN, VendorCapability.EVPN,
                VendorCapability.MPLS, VendorCapability.ACL,
                VendorCapability.VRRP, VendorCapability.BFD,
                VendorCapability.NETCONF, VendorCapability.RESTCONF,
                VendorCapability.SNMP, VendorCapability.STREAMING_TELEMETRY,
            },
            cli_syntax=CLISyntax(
                show_version="show version",
                show_interfaces="show interfaces status",
                show_ip_route="show ip route",
                show_ipv6_route="show ipv6 route",
                show_running_config="show running-config",
                show_ospf_neighbors="show ip ospf neighbor",
                show_ospf_routes="show ip ospf route",
                show_ospf_database="show ip ospf database",
                show_bgp_summary="show ip bgp summary",
                show_bgp_neighbors="show ip bgp neighbors",
                show_bgp_routes="show ip bgp",
                interface_config="interface {interface}",
                ip_address="ip address {ip}/{prefix}",
                ipv6_address="ipv6 address {ip}/{prefix}",
                shutdown="shutdown",
                no_shutdown="no shutdown",
                router_ospf="router ospf {process}",
                router_bgp="router bgp {asn}",
                network_statement="network {prefix} area {area}",
                config_mode="configure",
                exit_config="end",
                commit="",
                exec_prompt=">",
                privileged_prompt="#",
                config_prompt="(config)#",
            ),
            profile=VendorProfile(
                boot_time_seconds=45,
                ospf_default_dead_interval=40,
                auto_cost_reference_bandwidth=100000,  # 100 Gbps
                requires_enable_password=False,
                config_commit_required=False,
                max_routes=256000,
                max_bgp_peers=1000,
            ),
        )
        self._vendors["arista-eos"] = arista_eos

        # Nokia SR OS
        nokia_sros = Vendor(
            vendor_id="nokia-sros",
            name="nokia",
            display_name="Nokia SR OS",
            description="Nokia Service Router Operating System",
            os_name="SR OS",
            os_version="22.10",
            capabilities={
                VendorCapability.OSPF, VendorCapability.OSPFV3,
                VendorCapability.BGP, VendorCapability.ISIS,
                VendorCapability.RIP, VendorCapability.MPLS,
                VendorCapability.MPLS_TE, VendorCapability.L3VPN,
                VendorCapability.L2VPN, VendorCapability.EVPN,
                VendorCapability.VXLAN, VendorCapability.ACL,
                VendorCapability.FIREWALL, VendorCapability.VRRP,
                VendorCapability.BFD, VendorCapability.NSF,
                VendorCapability.NETCONF, VendorCapability.SNMP,
                VendorCapability.STREAMING_TELEMETRY,
                VendorCapability.SR_MPLS, VendorCapability.SRV6,
            },
            cli_syntax=CLISyntax(
                show_version="show version",
                show_interfaces="show port",
                show_ip_route="show router route-table",
                show_ipv6_route="show router route-table ipv6",
                show_running_config="admin display-config",
                show_ospf_neighbors="show router ospf neighbor",
                show_ospf_routes="show router ospf routes",
                show_ospf_database="show router ospf database",
                show_bgp_summary="show router bgp summary",
                show_bgp_neighbors="show router bgp neighbor",
                show_bgp_routes="show router bgp routes",
                interface_config="configure port {interface}",
                ip_address="configure router interface {interface} address {ip}/{prefix}",
                ipv6_address="configure router interface {interface} ipv6 address {ip}/{prefix}",
                shutdown="configure port {interface} shutdown",
                no_shutdown="configure port {interface} no shutdown",
                router_ospf="configure router ospf {process}",
                router_bgp="configure router bgp",
                network_statement="configure router ospf {process} area {area} interface {interface}",
                config_mode="configure",
                exit_config="exit all",
                commit="commit",
                exec_prompt="A:",
                privileged_prompt="A:",
                config_prompt="*A:",
            ),
            profile=VendorProfile(
                boot_time_seconds=120,
                ospf_default_dead_interval=40,
                bgp_default_hold_time=90,
                auto_cost_reference_bandwidth=100000,
                requires_enable_password=False,
                config_commit_required=True,
                max_routes=10000000,  # Service provider scale
                max_bgp_peers=4000,
            ),
        )
        self._vendors["nokia-sros"] = nokia_sros

        # Generic/FRRouting (default)
        frrouting = Vendor(
            vendor_id="frrouting",
            name="frrouting",
            display_name="FRRouting",
            description="Open source routing suite (default)",
            os_name="FRRouting",
            os_version="8.5",
            capabilities={
                VendorCapability.OSPF, VendorCapability.OSPFV3,
                VendorCapability.BGP, VendorCapability.ISIS,
                VendorCapability.RIP, VendorCapability.VLAN,
                VendorCapability.LACP, VendorCapability.LLDP,
                VendorCapability.MPLS, VendorCapability.L3VPN,
                VendorCapability.EVPN, VendorCapability.BFD,
                VendorCapability.VRRP, VendorCapability.SR_MPLS,
            },
            cli_syntax=CLISyntax(
                show_version="show version",
                show_interfaces="show interface",
                show_ip_route="show ip route",
                show_ipv6_route="show ipv6 route",
                show_running_config="show running-config",
                show_ospf_neighbors="show ip ospf neighbor",
                show_ospf_routes="show ip ospf route",
                show_ospf_database="show ip ospf database",
                show_bgp_summary="show ip bgp summary",
                show_bgp_neighbors="show ip bgp neighbors",
                show_bgp_routes="show ip bgp",
                interface_config="interface {interface}",
                ip_address="ip address {ip}/{prefix}",
                ipv6_address="ipv6 address {ip}/{prefix}",
                shutdown="shutdown",
                no_shutdown="no shutdown",
                router_ospf="router ospf",
                router_bgp="router bgp {asn}",
                network_statement="network {prefix} area {area}",
                config_mode="configure terminal",
                exit_config="end",
                commit="",
                exec_prompt=">",
                privileged_prompt="#",
                config_prompt="(config)#",
            ),
            profile=VendorProfile(
                boot_time_seconds=10,
                ospf_default_dead_interval=40,
                ospf_default_hello_interval=10,
                bgp_default_hold_time=180,
                bgp_default_keepalive=60,
                auto_cost_reference_bandwidth=100,
                requires_enable_password=False,
                config_commit_required=False,
            ),
        )
        self._vendors["frrouting"] = frrouting

    # ==== Vendor Management ====

    def get_vendor(self, vendor_id: str) -> Optional[Vendor]:
        """Get a vendor by ID."""
        return self._vendors.get(vendor_id)

    def list_vendors(self) -> List[Vendor]:
        """List all available vendors."""
        return list(self._vendors.values())

    def register_vendor(self, vendor: Vendor) -> bool:
        """Register a custom vendor."""
        if vendor.vendor_id in self._vendors:
            logger.warning(f"Vendor already exists: {vendor.vendor_id}")
            return False

        self._vendors[vendor.vendor_id] = vendor
        logger.info(f"Registered vendor: {vendor.display_name}")
        return True

    def get_vendors_by_capability(self, capability: VendorCapability) -> List[Vendor]:
        """Get vendors that support a specific capability."""
        return [v for v in self._vendors.values() if v.has_capability(capability)]

    def get_cli_syntax(self, vendor_id: str) -> Optional[CLISyntax]:
        """Get CLI syntax for a vendor."""
        vendor = self._vendors.get(vendor_id)
        return vendor.cli_syntax if vendor else None

    def get_profile(self, vendor_id: str) -> Optional[VendorProfile]:
        """Get behavioral profile for a vendor."""
        vendor = self._vendors.get(vendor_id)
        return vendor.profile if vendor else None

    def translate_command(
        self,
        command: str,
        from_vendor: str,
        to_vendor: str,
    ) -> Optional[str]:
        """
        Translate a command from one vendor's syntax to another.

        This is a best-effort translation for common commands.
        """
        from_v = self._vendors.get(from_vendor)
        to_v = self._vendors.get(to_vendor)

        if not from_v or not to_v:
            return None

        # Build reverse mapping from commands to command types
        from_syntax = from_v.cli_syntax.to_dict()
        to_syntax = to_v.cli_syntax.to_dict()

        # Find matching command type
        for cmd_type, cmd_value in from_syntax.items():
            if command.lower().startswith(cmd_value.lower().split()[0]):
                return to_syntax.get(cmd_type)

        return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get vendor manager statistics."""
        capability_counts = {}
        for vendor in self._vendors.values():
            for cap in vendor.capabilities:
                capability_counts[cap.value] = capability_counts.get(cap.value, 0) + 1

        return {
            "total_vendors": len(self._vendors),
            "vendors": [v.display_name for v in self._vendors.values()],
            "capabilities_supported": capability_counts,
        }


# Singleton accessor
def get_vendor_manager() -> VendorManager:
    """Get the vendor manager instance."""
    return VendorManager()


# Convenience functions
def get_vendor(vendor_id: str) -> Optional[Vendor]:
    """Get a vendor by ID."""
    manager = get_vendor_manager()
    return manager.get_vendor(vendor_id)


def list_vendors() -> List[Dict[str, Any]]:
    """List all vendors as dictionaries."""
    manager = get_vendor_manager()
    return [v.to_dict() for v in manager.list_vendors()]


def get_cli_syntax(vendor_id: str) -> Optional[Dict[str, str]]:
    """Get CLI syntax for a vendor."""
    manager = get_vendor_manager()
    syntax = manager.get_cli_syntax(vendor_id)
    return syntax.to_dict() if syntax else None
