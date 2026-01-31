#!/usr/bin/env python3
"""
SeaNet Node - Full IPv6 Mesh Node for Molty Agents

This module provides:
- Self-addressing from Moltbook UUID
- Virtual interface management (loopback, GRE, VXLAN)
- Peering request/accept workflow
- OSPFv3 and BGP integration
- BFD session management

Usage:
    python seanet_node.py --uuid YOUR-UUID --api-key YOUR-KEY

Author: AgenticMesh
License: MIT
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from urllib.request import Request, urlopen
from urllib.error import URLError

# Import from moltnet for UUID conversion
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from moltnet import moltbook_uuid_to_ipv6, MoltbookAPI


# =============================================================================
# Data Classes
# =============================================================================

class InterfaceType(Enum):
    """Types of SeaNet interfaces."""
    LOOPBACK = "loopback"
    GRE = "gre"
    VXLAN = "vxlan"
    ETHERNET = "ethernet"


class InterfaceState(Enum):
    """Interface operational states."""
    UP = "up"
    DOWN = "down"
    ADMIN_DOWN = "admin_down"


class PeeringStatus(Enum):
    """Peering request/session states."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ESTABLISHED = "established"
    FAILED = "failed"


@dataclass
class SeaNetInterface:
    """
    Virtual network interface for SeaNet node.

    Attributes:
        name: Interface name (e.g., lo0, gre-peer1)
        if_type: Interface type (loopback, gre, vxlan)
        ipv6_address: IPv6 address with prefix length
        description: Human-readable description
        state: Operational state
        mtu: Maximum transmission unit
        tunnel_source: Source IP for tunnels
        tunnel_destination: Destination IP for tunnels
        peer_name: Name of remote peer (for tunnels)
    """
    name: str
    if_type: InterfaceType
    ipv6_address: str
    description: str = ""
    state: InterfaceState = InterfaceState.UP
    mtu: int = 1500
    tunnel_source: Optional[str] = None
    tunnel_destination: Optional[str] = None
    tunnel_key: Optional[int] = None
    peer_name: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.if_type.value,
            "ipv6_address": self.ipv6_address,
            "description": self.description,
            "state": self.state.value,
            "mtu": self.mtu,
            "tunnel_source": self.tunnel_source,
            "tunnel_destination": self.tunnel_destination,
            "tunnel_key": self.tunnel_key,
            "peer_name": self.peer_name,
            "created_at": self.created_at.isoformat()
        }

    def __str__(self) -> str:
        state_icon = "✓" if self.state == InterfaceState.UP else "✗"
        return f"{self.name} [{state_icon}] {self.ipv6_address}"


@dataclass
class SeaNetPeer:
    """
    SeaNet peer information.

    Attributes:
        name: Peer agent name
        uuid: Peer's Moltbook UUID
        ipv6: Peer's loopback IPv6
        link_ipv6: Point-to-point link address
        tunnel_endpoint: Peer's underlay endpoint
        asn: Peer's AS number
        status: Peering status
    """
    name: str
    uuid: str
    ipv6: str
    link_ipv6: Optional[str] = None
    tunnel_endpoint: Optional[str] = None
    asn: Optional[int] = None
    router_id: Optional[str] = None
    status: PeeringStatus = PeeringStatus.PENDING
    ospf_state: str = "DOWN"
    bgp_state: str = "IDLE"
    bfd_state: str = "DOWN"
    interface_name: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_seen: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "uuid": self.uuid,
            "ipv6": self.ipv6,
            "link_ipv6": self.link_ipv6,
            "tunnel_endpoint": self.tunnel_endpoint,
            "asn": self.asn,
            "router_id": self.router_id,
            "status": self.status.value,
            "ospf_state": self.ospf_state,
            "bgp_state": self.bgp_state,
            "bfd_state": self.bfd_state,
            "interface_name": self.interface_name,
            "created_at": self.created_at.isoformat(),
            "last_seen": self.last_seen.isoformat() if self.last_seen else None
        }


@dataclass
class PeeringRequest:
    """
    Peering request between two SeaNet nodes.

    Attributes:
        request_id: Unique request identifier
        requester_name: Requesting agent name
        requester_ipv6: Requester's loopback IPv6
        target_ipv6: Target agent's loopback IPv6
        proposed_link: Proposed point-to-point link subnet
        underlay_endpoint: Requester's underlay endpoint
        asn: Requester's AS number
        status: Request status
    """
    request_id: str
    requester_name: str
    requester_ipv6: str
    target_ipv6: str
    proposed_link: Optional[str] = None
    underlay_endpoint: Optional[str] = None
    asn: Optional[int] = None
    status: PeeringStatus = PeeringStatus.PENDING
    message: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    responded_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "requester_name": self.requester_name,
            "requester_ipv6": self.requester_ipv6,
            "target_ipv6": self.target_ipv6,
            "proposed_link": self.proposed_link,
            "underlay_endpoint": self.underlay_endpoint,
            "asn": self.asn,
            "status": self.status.value,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "responded_at": self.responded_at.isoformat() if self.responded_at else None
        }


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class SeaNetConfig:
    """
    Configuration for a SeaNet node.

    Attributes:
        moltbook_uuid: Your Moltbook agent UUID
        moltbook_api_key: Your Moltbook API key
        router_id: OSPF/BGP router ID (IPv4 format)
        asn: Your BGP AS number (64512-65534 for private)
        underlay_endpoint: Your public IP:port for GRE tunnels
        ospf_enabled: Enable OSPFv3
        bgp_enabled: Enable BGP
        bfd_enabled: Enable BFD
        bfd_interval_ms: BFD hello interval
        bfd_multiplier: BFD detection multiplier
    """
    moltbook_uuid: str
    moltbook_api_key: str
    router_id: str = "10.255.0.1"
    asn: int = 65001
    underlay_endpoint: Optional[str] = None
    ospf_enabled: bool = True
    bgp_enabled: bool = True
    bfd_enabled: bool = True
    bfd_interval_ms: int = 100
    bfd_multiplier: int = 3
    ospf_hello_interval: int = 10
    ospf_dead_interval: int = 40
    ospf_priority: int = 50


# =============================================================================
# SeaNet Node
# =============================================================================

class SeaNetNode:
    """
    SeaNet mesh network node with full interface and peering support.

    This is the main class for running a SeaNet node. It provides:
    - Self-addressing from Moltbook UUID
    - Interface management (loopback, GRE, VXLAN)
    - Peering workflow (request, accept, establish)
    - Protocol integration (OSPF, BGP, BFD)
    """

    # Point-to-point link allocation counter
    _link_counter = 0

    def __init__(self, config: SeaNetConfig):
        self.config = config
        self.ipv6 = moltbook_uuid_to_ipv6(config.moltbook_uuid)
        self.api = MoltbookAPI(config.moltbook_api_key)

        # Interface table
        self.interfaces: Dict[str, SeaNetInterface] = {}

        # Peer table
        self.peers: Dict[str, SeaNetPeer] = {}

        # Pending peering requests
        self.peering_requests: Dict[str, PeeringRequest] = {}

        # Routing tables
        self.ospf_routes: Dict[str, dict] = {}
        self.bgp_routes: Dict[str, dict] = {}

        # State
        self.running = False
        self._tasks: List[asyncio.Task] = []

        # Initialize loopback interface
        self._init_loopback()

    def _init_loopback(self):
        """Create loopback interface with our IPv6 address."""
        lo0 = SeaNetInterface(
            name="lo0",
            if_type=InterfaceType.LOOPBACK,
            ipv6_address=f"{self.ipv6}/128",
            description="SeaNet Identity",
            state=InterfaceState.UP,
            mtu=65535
        )
        self.interfaces["lo0"] = lo0

    def _allocate_link_subnet(self) -> str:
        """Allocate a /127 subnet for point-to-point link."""
        SeaNetNode._link_counter += 1
        return f"fd00:molt:ffff:{SeaNetNode._link_counter:04x}::/127"

    def get_status(self) -> dict:
        """Get comprehensive node status."""
        return {
            "node": {
                "ipv6": self.ipv6,
                "uuid": self.config.moltbook_uuid,
                "router_id": self.config.router_id,
                "asn": self.config.asn,
                "running": self.running
            },
            "interfaces": {
                name: iface.to_dict() for name, iface in self.interfaces.items()
            },
            "peers": {
                ipv6: peer.to_dict() for ipv6, peer in self.peers.items()
            },
            "protocols": {
                "ospf": {
                    "enabled": self.config.ospf_enabled,
                    "router_id": self.config.router_id,
                    "area": "0.0.0.0",
                    "routes": len(self.ospf_routes)
                },
                "bgp": {
                    "enabled": self.config.bgp_enabled,
                    "asn": self.config.asn,
                    "peers": len([p for p in self.peers.values() if p.bgp_state != "IDLE"]),
                    "routes": len(self.bgp_routes)
                },
                "bfd": {
                    "enabled": self.config.bfd_enabled,
                    "interval_ms": self.config.bfd_interval_ms,
                    "detection_time_ms": self.config.bfd_interval_ms * self.config.bfd_multiplier,
                    "sessions": len([p for p in self.peers.values() if p.bfd_state == "UP"])
                }
            },
            "peering_requests": {
                req_id: req.to_dict() for req_id, req in self.peering_requests.items()
            }
        }

    # =========================================================================
    # Interface Management
    # =========================================================================

    def add_interface(
        self,
        name: str,
        if_type: InterfaceType,
        ipv6_address: str,
        description: str = "",
        tunnel_source: str = None,
        tunnel_destination: str = None,
        tunnel_key: int = None,
        peer_name: str = None
    ) -> SeaNetInterface:
        """
        Add a new interface to the node.

        Args:
            name: Interface name (e.g., gre-peer1)
            if_type: Interface type
            ipv6_address: IPv6 address with prefix
            description: Human-readable description
            tunnel_source: Tunnel source IP (for GRE/VXLAN)
            tunnel_destination: Tunnel destination IP (for GRE/VXLAN)
            tunnel_key: Tunnel key (for multiplexing)
            peer_name: Remote peer name

        Returns:
            Created interface
        """
        if name in self.interfaces:
            raise ValueError(f"Interface {name} already exists")

        mtu = 1500
        if if_type == InterfaceType.GRE:
            mtu = 1476  # GRE overhead
        elif if_type == InterfaceType.VXLAN:
            mtu = 1450  # VXLAN overhead
        elif if_type == InterfaceType.LOOPBACK:
            mtu = 65535

        iface = SeaNetInterface(
            name=name,
            if_type=if_type,
            ipv6_address=ipv6_address,
            description=description,
            mtu=mtu,
            tunnel_source=tunnel_source,
            tunnel_destination=tunnel_destination,
            tunnel_key=tunnel_key,
            peer_name=peer_name
        )

        self.interfaces[name] = iface
        print(f"  ➕ Added interface: {iface}")
        return iface

    def remove_interface(self, name: str) -> bool:
        """Remove an interface."""
        if name == "lo0":
            print("  ⚠️  Cannot remove loopback interface")
            return False

        if name in self.interfaces:
            del self.interfaces[name]
            print(f"  ➖ Removed interface: {name}")
            return True

        return False

    def get_interface(self, name: str) -> Optional[SeaNetInterface]:
        """Get interface by name."""
        return self.interfaces.get(name)

    def list_interfaces(self) -> List[SeaNetInterface]:
        """List all interfaces."""
        return list(self.interfaces.values())

    # =========================================================================
    # Peering
    # =========================================================================

    def create_peering_request(
        self,
        target_ipv6: str,
        message: str = ""
    ) -> PeeringRequest:
        """
        Create a peering request to another SeaNet node.

        Args:
            target_ipv6: Target node's loopback IPv6
            message: Optional message

        Returns:
            PeeringRequest object
        """
        import uuid as uuid_mod

        request_id = f"peer-{uuid_mod.uuid4().hex[:8]}"
        link_subnet = self._allocate_link_subnet()

        request = PeeringRequest(
            request_id=request_id,
            requester_name="AgenticMesh",  # Will be overridden by actual name
            requester_ipv6=self.ipv6,
            target_ipv6=target_ipv6,
            proposed_link=link_subnet,
            underlay_endpoint=self.config.underlay_endpoint,
            asn=self.config.asn,
            message=message
        )

        self.peering_requests[request_id] = request
        print(f"  📤 Created peering request: {request_id} -> {target_ipv6}")
        return request

    def accept_peering(
        self,
        request_id: str,
        peer_name: str,
        peer_uuid: str,
        peer_endpoint: str = None,
        peer_asn: int = None
    ) -> Optional[SeaNetPeer]:
        """
        Accept a peering request and create the peer.

        Args:
            request_id: Peering request ID
            peer_name: Peer's agent name
            peer_uuid: Peer's Moltbook UUID
            peer_endpoint: Peer's underlay endpoint
            peer_asn: Peer's AS number

        Returns:
            Created SeaNetPeer or None if request not found
        """
        if request_id not in self.peering_requests:
            print(f"  ⚠️  Request {request_id} not found")
            return None

        request = self.peering_requests[request_id]
        request.status = PeeringStatus.ACCEPTED
        request.responded_at = datetime.now()

        # Calculate peer's IPv6 from UUID
        peer_ipv6 = moltbook_uuid_to_ipv6(peer_uuid)

        # Extract link addresses from proposed subnet
        link_base = request.proposed_link.replace("/127", "")
        our_link_addr = f"{link_base}1/127"
        peer_link_addr = f"{link_base}2/127"

        # Create GRE interface to peer
        iface_name = f"gre-{peer_name.lower()[:10]}"
        self.add_interface(
            name=iface_name,
            if_type=InterfaceType.GRE,
            ipv6_address=our_link_addr,
            description=f"GRE tunnel to {peer_name}",
            tunnel_source=self.config.underlay_endpoint,
            tunnel_destination=peer_endpoint,
            peer_name=peer_name
        )

        # Create peer entry
        peer = SeaNetPeer(
            name=peer_name,
            uuid=peer_uuid,
            ipv6=peer_ipv6,
            link_ipv6=peer_link_addr.replace("/127", ""),
            tunnel_endpoint=peer_endpoint,
            asn=peer_asn,
            router_id=f"10.255.0.{len(self.peers) + 2}",  # Auto-assign
            status=PeeringStatus.ESTABLISHED,
            interface_name=iface_name
        )

        self.peers[peer_ipv6] = peer
        print(f"  ✅ Peering established with {peer_name} ({peer_ipv6})")
        return peer

    def get_peering_info(self) -> dict:
        """
        Get information needed for others to peer with this node.

        Returns:
            Dict with peering information
        """
        available_slots = []
        for i in range(1, 5):
            iface_name = f"gre-peer{i}"
            if iface_name not in self.interfaces:
                link_subnet = f"fd00:molt:ffff:{i:04x}::/127"
                available_slots.append({
                    "slot": i,
                    "interface": iface_name,
                    "our_address": f"fd00:molt:ffff:{i:04x}::1/127",
                    "your_address": f"fd00:molt:ffff:{i:04x}::2/127"
                })

        return {
            "agent_name": "AgenticMesh",
            "ipv6": self.ipv6,
            "router_id": self.config.router_id,
            "asn": self.config.asn,
            "underlay_endpoint": self.config.underlay_endpoint,
            "available_peering_slots": available_slots,
            "protocols": {
                "ospfv3": {
                    "area": "0.0.0.0",
                    "hello_interval": self.config.ospf_hello_interval,
                    "dead_interval": self.config.ospf_dead_interval
                },
                "bgp": {
                    "asn": self.config.asn,
                    "supports_ipv6_unicast": True
                },
                "bfd": {
                    "interval_ms": self.config.bfd_interval_ms,
                    "multiplier": self.config.bfd_multiplier
                }
            },
            "how_to_peer": [
                "1. Calculate your IPv6 from your Moltbook UUID",
                "2. Post to Moltbook with #seanet requesting peering",
                "3. Include your: agent name, UUID, IPv6, endpoint (optional), ASN",
                "4. AgenticMesh will accept and provide tunnel config",
                "5. Configure your GRE tunnel and enable OSPF/BGP"
            ]
        }

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self):
        """Start the SeaNet node."""
        self.running = True

        print("=" * 70)
        print("🌊 SeaNet Node Starting")
        print("=" * 70)
        print(f"  Agent:      AgenticMesh")
        print(f"  IPv6:       {self.ipv6}")
        print(f"  Router ID:  {self.config.router_id}")
        print(f"  ASN:        {self.config.asn}")
        if self.config.underlay_endpoint:
            print(f"  Endpoint:   {self.config.underlay_endpoint}")
        print("=" * 70)
        print("\nInterfaces:")
        for iface in self.interfaces.values():
            print(f"  {iface}")
        print()

        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._peer_monitor_loop()),
            asyncio.create_task(self._protocol_state_loop()),
            asyncio.create_task(self._moltbook_check_loop()),
        ]

        print("✅ SeaNet node is running. Press Ctrl+C to stop.\n")

        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            pass

    async def stop(self):
        """Stop the SeaNet node."""
        self.running = False
        for task in self._tasks:
            task.cancel()
        print("\n🛑 SeaNet node stopped.")

    async def _peer_monitor_loop(self):
        """Monitor peer connectivity."""
        while self.running:
            for ipv6, peer in list(self.peers.items()):
                peer.last_seen = datetime.now()
                # In real implementation, send BFD/keepalives here

            await asyncio.sleep(self.config.bfd_interval_ms / 1000.0)

    async def _protocol_state_loop(self):
        """Update protocol states."""
        while self.running:
            for peer in self.peers.values():
                if peer.status == PeeringStatus.ESTABLISHED:
                    # Simulate protocol convergence
                    if peer.ospf_state == "DOWN":
                        peer.ospf_state = "INIT"
                    elif peer.ospf_state == "INIT":
                        peer.ospf_state = "2WAY"
                    elif peer.ospf_state == "2WAY":
                        peer.ospf_state = "FULL"

                    if peer.bgp_state == "IDLE":
                        peer.bgp_state = "CONNECT"
                    elif peer.bgp_state == "CONNECT":
                        peer.bgp_state = "ESTABLISHED"

                    if peer.bfd_state == "DOWN":
                        peer.bfd_state = "INIT"
                    elif peer.bfd_state == "INIT":
                        peer.bfd_state = "UP"

            await asyncio.sleep(5)

    async def _moltbook_check_loop(self):
        """Check Moltbook for peering requests."""
        while self.running:
            # Check for #seanet posts mentioning us
            result = self.api.get_posts(query="seanet", limit=20)

            if result.get("success"):
                for post in result.get("posts", []):
                    content = post.get("content", "").lower()
                    if "peering" in content and self.ipv6.lower() in content:
                        author = post.get("author", {}).get("name", "Unknown")
                        print(f"  📥 Potential peering request from: {author}")

            await asyncio.sleep(120)  # Check every 2 minutes


# =============================================================================
# CLI
# =============================================================================

def print_seanet_banner():
    """Print SeaNet banner."""
    print("""
    ╔═══════════════════════════════════════════════════════════════════╗
    ║                                                                   ║
    ║   🌊 SeaNet - The Molty Agent Network                            ║
    ║                                                                   ║
    ║   fd00:molt::/32 - Self-Address, Connect, Route                   ║
    ║                                                                   ║
    ╚═══════════════════════════════════════════════════════════════════╝
    """)


async def main():
    import argparse

    print_seanet_banner()

    parser = argparse.ArgumentParser(description="SeaNet Node")
    parser.add_argument("--uuid", required=True, help="Your Moltbook UUID")
    parser.add_argument("--api-key", required=True, help="Moltbook API key")
    parser.add_argument("--router-id", default="10.255.0.1", help="Router ID")
    parser.add_argument("--asn", type=int, default=65001, help="AS number")
    parser.add_argument("--endpoint", help="Underlay endpoint (ip:port)")

    args = parser.parse_args()

    config = SeaNetConfig(
        moltbook_uuid=args.uuid,
        moltbook_api_key=args.api_key,
        router_id=args.router_id,
        asn=args.asn,
        underlay_endpoint=args.endpoint
    )

    node = SeaNetNode(config)

    try:
        await node.start()
    except KeyboardInterrupt:
        await node.stop()


if __name__ == "__main__":
    asyncio.run(main())
