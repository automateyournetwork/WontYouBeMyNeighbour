"""
Subnet Calculator MCP

Provides IPv4 and IPv6 subnet calculation tools for network agents.
Based on NAF_AC4 Lab02 MCP, extended with IPv6 support.

This is a FOUNDATIONAL MCP - included with every agent.
"""

import logging
import ipaddress as ipaddr
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger("SubnetMCP")


@dataclass
class SubnetConfig:
    """Configuration for subnet MCP"""
    max_host_preview: int = 10  # Cap host list for large subnets


class SubnetCalculator:
    """
    Subnet calculation engine supporting both IPv4 and IPv6.

    Provides:
    - Network address calculation
    - Broadcast address (IPv4) / last address (IPv6)
    - Usable host range
    - Previous/next subnet calculation
    - Address classification (private, global, multicast, etc.)
    """

    def __init__(self, config: Optional[SubnetConfig] = None):
        self.config = config or SubnetConfig()

    def calculate_ipv4(self, cidr: str) -> Dict[str, Any]:
        """
        Calculate IPv4 subnet details.

        Args:
            cidr: Network in CIDR notation, e.g. '192.168.1.0/24'

        Returns:
            Dictionary with comprehensive subnet information
        """
        logger.info(f"Calculating IPv4 subnet for: {cidr}")

        try:
            # Parse CIDR with non-strict mode (allows host bits)
            network = ipaddr.IPv4Network(cidr, strict=False)
            size = network.num_addresses
            base = int(network.network_address)

            # Calculate previous and next subnets
            prev_base = base - size
            next_base = base + size

            prev_sub = None
            next_sub = None

            try:
                if prev_base >= 0:
                    prev_sub = str(ipaddr.IPv4Network(
                        f"{ipaddr.IPv4Address(prev_base)}/{network.prefixlen}"
                    ))
            except:
                prev_sub = "N/A (underflow)"

            try:
                if next_base < 2**32:
                    next_sub = str(ipaddr.IPv4Network(
                        f"{ipaddr.IPv4Address(next_base)}/{network.prefixlen}"
                    ))
            except:
                next_sub = "N/A (overflow)"

            # Get usable hosts preview (capped)
            usable_hosts = []
            for i, ip in enumerate(network):
                if ip not in (network.network_address, network.broadcast_address):
                    usable_hosts.append(str(ip))
                    if len(usable_hosts) >= self.config.max_host_preview:
                        break

            # First and last usable
            hosts_list = list(network.hosts())
            first_usable = str(hosts_list[0]) if hosts_list else None
            last_usable = str(hosts_list[-1]) if hosts_list else None

            result = {
                "version": 4,
                "input_cidr": cidr,

                # Core subnet parameters
                "network_address": str(network.network_address),
                "broadcast_address": str(network.broadcast_address),
                "netmask": str(network.netmask),
                "wildcard_mask": str(network.hostmask),
                "prefix_length": network.prefixlen,
                "with_netmask": str(network.with_netmask),
                "with_hostmask": str(network.with_hostmask),

                # Host range details
                "num_addresses": network.num_addresses,
                "usable_hosts_count": max(0, network.num_addresses - 2),
                "usable_hosts_preview": usable_hosts,
                "first_usable": first_usable,
                "last_usable": last_usable,
                "address_range": f"{first_usable} - {last_usable}" if first_usable else "N/A",

                # Neighboring subnets
                "previous_subnet": prev_sub,
                "next_subnet": next_sub,

                # Bit-level info
                "host_bits": 32 - network.prefixlen,
                "network_bits": network.prefixlen,
                "total_bits": 32,

                # Address classification
                "is_private": network.is_private,
                "is_global": network.is_global,
                "is_link_local": network.is_link_local,
                "is_multicast": network.is_multicast,
                "is_loopback": network.is_loopback,
                "is_reserved": network.is_reserved,
                "is_unspecified": network.is_unspecified,

                # Classification label
                "classification": self._classify_ipv4(network),

                # Summary
                "summary": (
                    f"IPv4 {cidr} contains {network.num_addresses} total addresses "
                    f"with {max(0, network.num_addresses - 2)} usable hosts "
                    f"(/{network.prefixlen} prefix, {32 - network.prefixlen} host bits)."
                )
            }

            logger.info(f"IPv4 calculation complete: {network.num_addresses} addresses")
            return result

        except Exception as e:
            logger.error(f"IPv4 calculation error: {e}")
            return {"error": str(e), "version": 4, "input_cidr": cidr}

    def calculate_ipv6(self, cidr: str) -> Dict[str, Any]:
        """
        Calculate IPv6 subnet details.

        Args:
            cidr: Network in CIDR notation, e.g. '2001:db8::/32'

        Returns:
            Dictionary with comprehensive subnet information
        """
        logger.info(f"Calculating IPv6 subnet for: {cidr}")

        try:
            # Parse CIDR with non-strict mode
            network = ipaddr.IPv6Network(cidr, strict=False)
            size = network.num_addresses
            base = int(network.network_address)

            # Calculate previous and next subnets
            prev_base = base - size
            next_base = base + size

            prev_sub = None
            next_sub = None

            try:
                if prev_base >= 0:
                    prev_sub = str(ipaddr.IPv6Network(
                        f"{ipaddr.IPv6Address(prev_base)}/{network.prefixlen}"
                    ))
            except:
                prev_sub = "N/A (underflow)"

            try:
                if next_base < 2**128:
                    next_sub = str(ipaddr.IPv6Network(
                        f"{ipaddr.IPv6Address(next_base)}/{network.prefixlen}"
                    ))
            except:
                next_sub = "N/A (overflow)"

            # Get usable hosts preview (capped) - IPv6 doesn't have broadcast
            usable_hosts = []
            host_iter = network.hosts()
            for i in range(self.config.max_host_preview):
                try:
                    usable_hosts.append(str(next(host_iter)))
                except StopIteration:
                    break

            # First and last usable
            first_usable = str(network.network_address + 1) if network.num_addresses > 1 else None
            # For IPv6, last usable is network + num_addresses - 1
            last_addr = network.network_address + network.num_addresses - 1
            last_usable = str(last_addr) if network.num_addresses > 1 else None

            # Calculate usable count (IPv6 doesn't reserve network/broadcast like IPv4)
            # But typically first address is the router/subnet-router anycast
            usable_count = network.num_addresses - 1 if network.num_addresses > 0 else 0

            result = {
                "version": 6,
                "input_cidr": cidr,

                # Core subnet parameters
                "network_address": str(network.network_address),
                "last_address": str(last_addr),
                "prefix_length": network.prefixlen,
                "compressed": network.compressed,
                "exploded": network.exploded,

                # Host range details
                "num_addresses": network.num_addresses,
                "num_addresses_formatted": self._format_large_number(network.num_addresses),
                "usable_hosts_count": usable_count,
                "usable_hosts_preview": usable_hosts,
                "first_usable": first_usable,
                "last_usable": last_usable,
                "address_range": f"{first_usable} - {last_usable}" if first_usable else "N/A",

                # Neighboring subnets
                "previous_subnet": prev_sub,
                "next_subnet": next_sub,

                # Bit-level info
                "host_bits": 128 - network.prefixlen,
                "network_bits": network.prefixlen,
                "total_bits": 128,

                # Address classification
                "is_private": network.is_private,
                "is_global": network.is_global,
                "is_link_local": network.is_link_local,
                "is_multicast": network.is_multicast,
                "is_loopback": network.is_loopback,
                "is_reserved": network.is_reserved,
                "is_unspecified": network.is_unspecified,
                "is_site_local": network.is_site_local,

                # IPv6 specific
                "ipv4_mapped": str(network.network_address.ipv4_mapped) if network.network_address.ipv4_mapped else None,
                "sixtofour": str(network.network_address.sixtofour) if network.network_address.sixtofour else None,
                "teredo": network.network_address.teredo if hasattr(network.network_address, 'teredo') else None,

                # Classification label
                "classification": self._classify_ipv6(network),

                # Summary
                "summary": (
                    f"IPv6 {network.compressed} contains {self._format_large_number(network.num_addresses)} addresses "
                    f"(/{network.prefixlen} prefix, {128 - network.prefixlen} host bits)."
                )
            }

            logger.info(f"IPv6 calculation complete: {network.num_addresses} addresses")
            return result

        except Exception as e:
            logger.error(f"IPv6 calculation error: {e}")
            return {"error": str(e), "version": 6, "input_cidr": cidr}

    def calculate_auto(self, cidr: str) -> Dict[str, Any]:
        """
        Auto-detect IP version and calculate subnet.

        Args:
            cidr: Network in CIDR notation (IPv4 or IPv6)

        Returns:
            Subnet calculation result
        """
        cidr = cidr.strip()

        # Detect version
        if ':' in cidr:
            return self.calculate_ipv6(cidr)
        else:
            return self.calculate_ipv4(cidr)

    def analyze_ip(self, ip_address: str) -> Dict[str, Any]:
        """
        Analyze a single IP address (with or without prefix).

        Args:
            ip_address: IP address, optionally with CIDR prefix

        Returns:
            Analysis of the IP address
        """
        ip_address = ip_address.strip()

        try:
            # Check if it has a prefix
            if '/' in ip_address:
                # It's a CIDR, analyze as network
                return self.calculate_auto(ip_address)

            # Single IP - detect version and analyze
            if ':' in ip_address:
                ip = ipaddr.IPv6Address(ip_address)
                version = 6
            else:
                ip = ipaddr.IPv4Address(ip_address)
                version = 4

            result = {
                "version": version,
                "address": str(ip),
                "compressed": ip.compressed if version == 6 else str(ip),
                "exploded": ip.exploded if version == 6 else str(ip),
                "is_private": ip.is_private,
                "is_global": ip.is_global,
                "is_link_local": ip.is_link_local,
                "is_multicast": ip.is_multicast,
                "is_loopback": ip.is_loopback,
                "is_reserved": ip.is_reserved,
                "is_unspecified": ip.is_unspecified,
                "binary": bin(int(ip))[2:].zfill(128 if version == 6 else 32),
                "integer": int(ip),
                "reverse_pointer": ip.reverse_pointer,
            }

            if version == 6:
                result["is_site_local"] = ip.is_site_local
                result["ipv4_mapped"] = str(ip.ipv4_mapped) if ip.ipv4_mapped else None
                result["sixtofour"] = str(ip.sixtofour) if ip.sixtofour else None

            return result

        except Exception as e:
            return {"error": str(e), "input": ip_address}

    def _classify_ipv4(self, network: ipaddr.IPv4Network) -> str:
        """Get human-readable classification for IPv4 network"""
        if network.is_loopback:
            return "Loopback"
        elif network.is_link_local:
            return "Link-Local (APIPA)"
        elif network.is_multicast:
            return "Multicast"
        elif network.is_private:
            # Determine RFC1918 class
            first_octet = int(str(network.network_address).split('.')[0])
            if first_octet == 10:
                return "Private (RFC1918 Class A)"
            elif first_octet == 172:
                return "Private (RFC1918 Class B)"
            elif first_octet == 192:
                return "Private (RFC1918 Class C)"
            return "Private"
        elif network.is_global:
            return "Global Unicast"
        elif network.is_reserved:
            return "Reserved"
        return "Unknown"

    def _classify_ipv6(self, network: ipaddr.IPv6Network) -> str:
        """Get human-readable classification for IPv6 network"""
        if network.is_loopback:
            return "Loopback (::1)"
        elif network.is_link_local:
            return "Link-Local (fe80::/10)"
        elif network.is_multicast:
            return "Multicast (ff00::/8)"
        elif network.is_site_local:
            return "Site-Local (deprecated)"
        elif network.is_private:
            # Check for ULA
            first_byte = int(network.network_address) >> 120
            if first_byte in (0xfc, 0xfd):
                return "Unique Local Address (ULA fc00::/7)"
            return "Private"
        elif network.is_global:
            return "Global Unicast"
        elif network.is_reserved:
            return "Reserved"
        return "Unknown"

    def _format_large_number(self, num: int) -> str:
        """Format large numbers with readable suffixes"""
        if num >= 10**36:
            return f"{num / 10**36:.2f} undecillion"
        elif num >= 10**33:
            return f"{num / 10**33:.2f} decillion"
        elif num >= 10**30:
            return f"{num / 10**30:.2f} nonillion"
        elif num >= 10**27:
            return f"{num / 10**27:.2f} octillion"
        elif num >= 10**24:
            return f"{num / 10**24:.2f} septillion"
        elif num >= 10**21:
            return f"{num / 10**21:.2f} sextillion"
        elif num >= 10**18:
            return f"{num / 10**18:.2f} quintillion"
        elif num >= 10**15:
            return f"{num / 10**15:.2f} quadrillion"
        elif num >= 10**12:
            return f"{num / 10**12:.2f} trillion"
        elif num >= 10**9:
            return f"{num / 10**9:.2f} billion"
        elif num >= 10**6:
            return f"{num / 10**6:.2f} million"
        elif num >= 10**3:
            return f"{num:,}"
        return str(num)


# Singleton instance
_calculator: Optional[SubnetCalculator] = None


def get_calculator() -> SubnetCalculator:
    """Get or create subnet calculator singleton"""
    global _calculator
    if _calculator is None:
        _calculator = SubnetCalculator()
    return _calculator


# === MCP Tool Functions (for LLM integration) ===

async def subnet_calculator_ipv4(cidr: str) -> Dict[str, Any]:
    """
    MCP Tool: Calculate IPv4 subnet details.

    Args:
        cidr: Network in CIDR notation, e.g. '192.168.1.0/24'

    Returns:
        Comprehensive subnet information
    """
    calc = get_calculator()
    return calc.calculate_ipv4(cidr)


async def subnet_calculator_ipv6(cidr: str) -> Dict[str, Any]:
    """
    MCP Tool: Calculate IPv6 subnet details.

    Args:
        cidr: Network in CIDR notation, e.g. '2001:db8::/32'

    Returns:
        Comprehensive subnet information
    """
    calc = get_calculator()
    return calc.calculate_ipv6(cidr)


async def subnet_calculator_auto(cidr: str) -> Dict[str, Any]:
    """
    MCP Tool: Auto-detect IP version and calculate subnet.

    Args:
        cidr: Network in CIDR notation (IPv4 or IPv6)

    Returns:
        Subnet calculation result
    """
    calc = get_calculator()
    return calc.calculate_auto(cidr)


async def ip_analyzer(ip_address: str) -> Dict[str, Any]:
    """
    MCP Tool: Analyze a single IP address.

    Args:
        ip_address: IP address (IPv4 or IPv6), optionally with CIDR prefix

    Returns:
        IP address analysis
    """
    calc = get_calculator()
    return calc.analyze_ip(ip_address)


# Tool definitions for LLM
SUBNET_TOOLS = [
    {
        "name": "subnet_calculator_ipv4",
        "description": "Calculate IPv4 subnet details including network address, broadcast, usable hosts, and neighboring subnets",
        "parameters": {
            "type": "object",
            "properties": {
                "cidr": {
                    "type": "string",
                    "description": "IPv4 network in CIDR notation, e.g. '192.168.1.0/24'"
                }
            },
            "required": ["cidr"]
        },
        "function": subnet_calculator_ipv4
    },
    {
        "name": "subnet_calculator_ipv6",
        "description": "Calculate IPv6 subnet details including network address, host count, and neighboring subnets",
        "parameters": {
            "type": "object",
            "properties": {
                "cidr": {
                    "type": "string",
                    "description": "IPv6 network in CIDR notation, e.g. '2001:db8::/32'"
                }
            },
            "required": ["cidr"]
        },
        "function": subnet_calculator_ipv6
    },
    {
        "name": "subnet_calculator",
        "description": "Auto-detect IP version and calculate subnet details. Works with both IPv4 and IPv6.",
        "parameters": {
            "type": "object",
            "properties": {
                "cidr": {
                    "type": "string",
                    "description": "Network in CIDR notation (IPv4 or IPv6)"
                }
            },
            "required": ["cidr"]
        },
        "function": subnet_calculator_auto
    },
    {
        "name": "ip_analyzer",
        "description": "Analyze a single IP address to determine its type, classification, and properties",
        "parameters": {
            "type": "object",
            "properties": {
                "ip_address": {
                    "type": "string",
                    "description": "IP address to analyze (IPv4 or IPv6)"
                }
            },
            "required": ["ip_address"]
        },
        "function": ip_analyzer
    }
]
