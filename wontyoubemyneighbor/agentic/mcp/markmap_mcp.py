"""
Markmap MCP Client - Self-Diagramming Network Visualization

Provides integration with the Markmap MCP server for generating interactive
mind map visualizations of agent network state.

Features:
- Real-time network state visualization
- Interactive expandable/collapsible nodes
- Protocol state diagrams
- Network topology mind maps
"""

import asyncio
import logging
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime

logger = logging.getLogger("MARKMAP_MCP")


class MarkmapTheme(Enum):
    """Available mind map themes"""
    DEFAULT = "default"
    DARK = "dark"
    COLORFUL = "colorful"
    MINIMAL = "minimal"


@dataclass
class MarkmapOptions:
    """Rendering options for mind maps"""
    color_freeze_level: int = 6
    duration: int = 500
    max_width: int = 0
    pan: bool = True
    zoom: bool = True
    theme: MarkmapTheme = MarkmapTheme.DARK

    def to_dict(self) -> Dict[str, Any]:
        return {
            "colorFreezeLevel": self.color_freeze_level,
            "duration": self.duration,
            "maxWidth": self.max_width,
            "pan": self.pan,
            "zoom": self.zoom,
            "theme": self.theme.value,
        }


@dataclass
class MarkmapNode:
    """Node in a mind map tree"""
    text: str
    level: int
    children: List["MarkmapNode"] = field(default_factory=list)
    collapsed: bool = False
    color: Optional[str] = None

    def to_markdown(self, indent: int = 0) -> str:
        """Convert node to markdown format"""
        prefix = "#" * max(1, self.level)
        lines = [f"{prefix} {self.text}"]
        for child in self.children:
            lines.append(child.to_markdown(indent + 1))
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "level": self.level,
            "children": [c.to_dict() for c in self.children],
            "collapsed": self.collapsed,
            "color": self.color,
        }


class AgentStateCollector:
    """
    Collects network state data from an agent for mind map generation

    Gathers information about:
    - Agent identity (hostname, router ID, protocols)
    - Interfaces (IP, state, neighbors)
    - Routing table
    - Protocol state (OSPF, BGP, etc.)
    - Health metrics
    """

    def __init__(self, agent_config: Dict[str, Any]):
        """
        Initialize state collector

        Args:
            agent_config: Agent TOON configuration
        """
        self.agent_config = agent_config
        self.agent_id = agent_config.get("id", "unknown")
        self.router_id = agent_config.get("r", "0.0.0.0")
        self.interfaces = agent_config.get("ifs", [])
        self.protocols = agent_config.get("protos", [])

    async def collect_state(self) -> Dict[str, Any]:
        """
        Collect current network state

        Returns:
            Dictionary containing all state information
        """
        state = {
            "identity": await self._collect_identity(),
            "interfaces": await self._collect_interfaces(),
            "routing": await self._collect_routing(),
            "health": await self._collect_health(),
        }

        # Add protocol-specific state
        for proto in self.protocols:
            proto_type = proto.get("p", "").lower()
            if proto_type in ["ospf", "ospfv3"]:
                state["ospf"] = await self._collect_ospf_state()
            elif proto_type in ["ibgp", "ebgp"]:
                state["bgp"] = await self._collect_bgp_state()
            elif proto_type == "isis":
                state["isis"] = await self._collect_isis_state()
            elif proto_type == "mpls":
                state["mpls"] = await self._collect_mpls_state()
            elif proto_type in ["vxlan", "evpn"]:
                state["vxlan"] = await self._collect_vxlan_state()

        # Check for GRE interfaces (not in protocols, but in interfaces)
        gre_interfaces = [i for i in self.interfaces if i.get("t") == "gre"]
        if gre_interfaces:
            state["gre"] = await self._collect_gre_state(gre_interfaces)

        # Always try to collect BFD state (runs alongside any protocol)
        bfd_state = await self._collect_bfd_state()
        if bfd_state.get("enabled"):
            state["bfd"] = bfd_state

        return state

    async def _collect_identity(self) -> Dict[str, Any]:
        """Collect agent identity information"""
        protocols = []
        for proto in self.protocols:
            p = proto.get("p", "")
            if p:
                protocols.append(p.upper())

        return {
            "hostname": self.agent_id,
            "router_id": self.router_id,
            "protocols": protocols,
            "as_number": self._get_as_number(),
        }

    def _get_as_number(self) -> Optional[int]:
        """Extract AS number from BGP config"""
        for proto in self.protocols:
            if proto.get("p") in ["ibgp", "ebgp"]:
                return proto.get("as")
        return None

    async def _collect_interfaces(self) -> List[Dict[str, Any]]:
        """Collect interface information"""
        interfaces = []
        for intf in self.interfaces:
            interfaces.append({
                "name": intf.get("n", "unknown"),
                "ip": intf.get("ip", "N/A"),
                "state": "UP",  # Simulated
                "mtu": intf.get("mtu", 1500),
                "neighbor": intf.get("peer"),
            })
        return interfaces

    async def _collect_routing(self) -> Dict[str, Any]:
        """Collect routing table information"""
        # In production, this would query FRR via vtysh
        return {
            "total_routes": 10,  # Simulated
            "connected": 3,
            "ospf": 5,
            "bgp": 2,
            "static": 0,
        }

    async def _collect_health(self) -> Dict[str, Any]:
        """Collect health metrics"""
        import random
        return {
            "cpu_percent": random.randint(5, 30),
            "memory_percent": random.randint(20, 60),
            "uptime_seconds": random.randint(3600, 86400),
            "last_test_status": "passed",
        }

    async def _collect_ospf_state(self) -> Dict[str, Any]:
        """Collect OSPF protocol state"""
        ospf_config = None
        for proto in self.protocols:
            if proto.get("p") in ["ospf", "ospfv3"]:
                ospf_config = proto
                break

        if not ospf_config:
            return {}

        return {
            "enabled": True,
            "router_id": ospf_config.get("r", self.router_id),
            "area": ospf_config.get("a", "0.0.0.0"),
            "neighbors": self._get_ospf_neighbors(ospf_config),
            "lsdb_summary": {
                "router_lsas": 3,
                "network_lsas": 1,
                "summary_lsas": 5,
            },
        }

    def _get_ospf_neighbors(self, ospf_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract OSPF neighbor info from config"""
        neighbors = []
        for intf in self.interfaces:
            if intf.get("peer"):
                neighbors.append({
                    "neighbor_id": intf.get("peer"),
                    "interface": intf.get("n"),
                    "state": "FULL",
                    "role": "DR" if len(neighbors) == 0 else "DROther",
                })
        return neighbors

    async def _collect_bgp_state(self) -> Dict[str, Any]:
        """Collect BGP protocol state"""
        bgp_config = None
        for proto in self.protocols:
            if proto.get("p") in ["ibgp", "ebgp"]:
                bgp_config = proto
                break

        if not bgp_config:
            return {}

        peers = []
        for neighbor in bgp_config.get("nbrs", []):
            peers.append({
                "peer_ip": neighbor.get("ip"),
                "remote_as": neighbor.get("as"),
                "state": "Established",
                "prefixes_received": 10,
                "prefixes_sent": 5,
                "uptime": "2h 30m",
            })

        return {
            "enabled": True,
            "local_as": bgp_config.get("as"),
            "router_id": bgp_config.get("r", self.router_id),
            "peers": peers,
        }

    async def _collect_isis_state(self) -> Dict[str, Any]:
        """Collect IS-IS protocol state"""
        return {
            "enabled": True,
            "system_id": self.router_id.replace(".", ""),
            "area": "49.0001",
            "adjacencies": [],
        }

    async def _collect_mpls_state(self) -> Dict[str, Any]:
        """Collect MPLS state"""
        return {
            "enabled": True,
            "ldp_enabled": True,
            "label_range": "16-1048575",
            "neighbors": [],
        }

    async def _collect_vxlan_state(self) -> Dict[str, Any]:
        """Collect VXLAN/EVPN state"""
        return {
            "enabled": True,
            "vtep_ip": self.router_id,
            "vnis": [],
            "remote_vteps": [],
        }

    async def _collect_gre_state(self, gre_interfaces: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Collect GRE tunnel state"""
        tunnels = []
        for iface in gre_interfaces:
            tun_config = iface.get("tun", {})
            tunnels.append({
                "name": iface.get("n", iface.get("id")),
                "local_ip": tun_config.get("src", ""),
                "remote_ip": tun_config.get("dst", ""),
                "tunnel_ip": iface.get("a", ["N/A"])[0] if iface.get("a") else "N/A",
                "key": tun_config.get("key"),
                "mtu": iface.get("mtu", 1400),
                "state": iface.get("s", "up"),
                "keepalive": tun_config.get("ka", 10),
                "checksum": tun_config.get("csum", False),
                "sequence": tun_config.get("seq", False),
            })

        return {
            "enabled": True,
            "tunnel_count": len(tunnels),
            "tunnels": tunnels,
        }

    async def _collect_bfd_state(self) -> Dict[str, Any]:
        """Collect BFD session state"""
        try:
            from bfd import get_bfd_manager
            agent_id = self.agent_config.get("id", "local")
            manager = get_bfd_manager(agent_id)

            if manager and manager.is_running:
                sessions = []
                for session in manager.list_sessions():
                    sessions.append({
                        "peer_address": session.get("remote_address", ""),
                        "state": session.get("state", "DOWN"),
                        "remote_state": session.get("remote_state", "DOWN"),
                        "protocol": session.get("client_protocol", ""),
                        "local_discriminator": session.get("local_discriminator", 0),
                        "remote_discriminator": session.get("remote_discriminator", 0),
                        "detect_mult": session.get("detect_mult", 3),
                        "detection_time_ms": session.get("detection_time_ms", 0),
                        "tx_interval_us": session.get("desired_min_tx_us", 100000),
                        "rx_interval_us": session.get("required_min_rx_us", 100000),
                        "is_up": session.get("is_up", False),
                        "packets_sent": session.get("statistics", {}).get("packets_sent", 0),
                        "packets_received": session.get("statistics", {}).get("packets_received", 0),
                    })

                return {
                    "enabled": True,
                    "running": manager.is_running,
                    "session_count": manager.session_count,
                    "up_count": manager.up_session_count,
                    "sessions": sessions,
                    "statistics": manager.stats.to_dict() if hasattr(manager, 'stats') else {},
                }
            else:
                return {"enabled": False}
        except ImportError:
            return {"enabled": False, "error": "BFD module not available"}
        except Exception as e:
            logger.warning(f"Failed to collect BFD state: {e}")
            return {"enabled": False, "error": str(e)}


class MarkmapGenerator:
    """
    Generates Markmap mind maps from network state

    Creates hierarchical markdown that Markmap can render as
    an interactive mind map visualization.
    """

    def __init__(self, options: Optional[MarkmapOptions] = None):
        """
        Initialize generator

        Args:
            options: Rendering options
        """
        self.options = options or MarkmapOptions()

    def generate_agent_mindmap(
        self,
        agent_state: Dict[str, Any]
    ) -> str:
        """
        Generate a mind map for a single agent

        Args:
            agent_state: Agent state dictionary from collector

        Returns:
            Markdown string for Markmap rendering
        """
        identity = agent_state.get("identity", {})
        hostname = identity.get("hostname", "Unknown")
        router_id = identity.get("router_id", "0.0.0.0")

        lines = [
            f"# Agent: {hostname} ({router_id})",
            "",
            "## Identity",
            f"- **Hostname:** {hostname}",
            f"- **Router ID:** {router_id}",
        ]

        # AS Number (if BGP)
        as_num = identity.get("as_number")
        if as_num:
            lines.append(f"- **AS Number:** {as_num}")

        # Protocols
        protocols = identity.get("protocols", [])
        if protocols:
            lines.append(f"- **Protocols:** {', '.join(protocols)}")

        # Interfaces
        lines.extend(["", "## Interfaces"])
        for intf in agent_state.get("interfaces", []):
            lines.append(f"### {intf['name']}")
            lines.append(f"- IP: {intf.get('ip', 'N/A')}")
            lines.append(f"- State: {intf.get('state', 'Unknown')}")
            if intf.get("neighbor"):
                lines.append(f"- Neighbor: {intf['neighbor']}")
            lines.append(f"- MTU: {intf.get('mtu', 1500)}")

        # Routing Table
        routing = agent_state.get("routing", {})
        if routing:
            lines.extend(["", "## Routing Table (RIB)"])
            lines.append(f"- **Total Routes:** {routing.get('total_routes', 0)}")
            lines.append(f"- Connected: {routing.get('connected', 0)}")
            lines.append(f"- OSPF: {routing.get('ospf', 0)}")
            lines.append(f"- BGP: {routing.get('bgp', 0)}")
            lines.append(f"- Static: {routing.get('static', 0)}")

        # OSPF State
        ospf = agent_state.get("ospf", {})
        if ospf.get("enabled"):
            lines.extend(["", "## OSPF State"])
            lines.append(f"- **Router ID:** {ospf.get('router_id')}")
            lines.append(f"- **Area:** {ospf.get('area', '0.0.0.0')}")

            lines.append("### Neighbors")
            for nbr in ospf.get("neighbors", []):
                lines.append(f"#### {nbr.get('neighbor_id', 'Unknown')}")
                lines.append(f"- Interface: {nbr.get('interface')}")
                lines.append(f"- State: {nbr.get('state')}")
                lines.append(f"- Role: {nbr.get('role')}")

            lsdb = ospf.get("lsdb_summary", {})
            if lsdb:
                lines.append("### LSDB Summary")
                lines.append(f"- Router LSAs: {lsdb.get('router_lsas', 0)}")
                lines.append(f"- Network LSAs: {lsdb.get('network_lsas', 0)}")
                lines.append(f"- Summary LSAs: {lsdb.get('summary_lsas', 0)}")

        # BGP State
        bgp = agent_state.get("bgp", {})
        if bgp.get("enabled"):
            lines.extend(["", "## BGP State"])
            lines.append(f"- **Local AS:** {bgp.get('local_as')}")
            lines.append(f"- **Router ID:** {bgp.get('router_id')}")

            lines.append("### Peers")
            for peer in bgp.get("peers", []):
                lines.append(f"#### {peer.get('peer_ip', 'Unknown')}")
                lines.append(f"- Remote AS: {peer.get('remote_as')}")
                lines.append(f"- State: {peer.get('state')}")
                lines.append(f"- Prefixes Received: {peer.get('prefixes_received', 0)}")
                lines.append(f"- Prefixes Sent: {peer.get('prefixes_sent', 0)}")
                lines.append(f"- Uptime: {peer.get('uptime', 'N/A')}")

        # GRE State
        gre = agent_state.get("gre", {})
        if gre.get("enabled"):
            lines.extend(["", "## GRE Tunnels"])
            lines.append(f"- **Tunnel Count:** {gre.get('tunnel_count', 0)}")

            lines.append("### Tunnel Details")
            for tunnel in gre.get("tunnels", []):
                lines.append(f"#### {tunnel.get('name', 'Unknown')}")
                lines.append(f"- Local IP: {tunnel.get('local_ip', 'N/A')}")
                lines.append(f"- Remote IP: {tunnel.get('remote_ip', 'N/A')}")
                lines.append(f"- Tunnel IP: {tunnel.get('tunnel_ip', 'N/A')}")
                if tunnel.get('key'):
                    lines.append(f"- GRE Key: {tunnel.get('key')}")
                lines.append(f"- MTU: {tunnel.get('mtu', 1400)}")
                lines.append(f"- State: {tunnel.get('state', 'unknown').upper()}")
                lines.append(f"- Keepalive: {tunnel.get('keepalive', 10)}s")
                features = []
                if tunnel.get('checksum'):
                    features.append("Checksum")
                if tunnel.get('sequence'):
                    features.append("Sequence")
                if features:
                    lines.append(f"- Features: {', '.join(features)}")

        # BFD State
        bfd = agent_state.get("bfd", {})
        if bfd.get("enabled"):
            lines.extend(["", "## BFD Sessions"])
            lines.append(f"- **Session Count:** {bfd.get('session_count', 0)}")
            lines.append(f"- **Sessions Up:** {bfd.get('up_count', 0)}")

            lines.append("### Session Details")
            for session in bfd.get("sessions", []):
                peer = session.get('peer_address', 'Unknown')
                state = session.get('state', 'DOWN')
                state_icon = "✓" if session.get('is_up') else "✗"
                lines.append(f"#### {state_icon} {peer}")
                lines.append(f"- State: {state}")
                protocol = session.get('protocol', '')
                if protocol:
                    lines.append(f"- Protocol: {protocol.upper()}")
                lines.append(f"- Detection Time: {session.get('detection_time_ms', 0):.1f}ms")
                lines.append(f"- Multiplier: {session.get('detect_mult', 3)}")
                tx_ms = session.get('tx_interval_us', 100000) / 1000
                rx_ms = session.get('rx_interval_us', 100000) / 1000
                lines.append(f"- TX/RX Interval: {tx_ms:.0f}ms / {rx_ms:.0f}ms")
                lines.append(f"- Packets: {session.get('packets_sent', 0)} TX / {session.get('packets_received', 0)} RX")

        # Health
        health = agent_state.get("health", {})
        if health:
            lines.extend(["", "## Health & Resources"])
            lines.append(f"- **CPU Usage:** {health.get('cpu_percent', 0)}%")
            lines.append(f"- **Memory:** {health.get('memory_percent', 0)}%")

            uptime_sec = health.get("uptime_seconds", 0)
            hours = uptime_sec // 3600
            minutes = (uptime_sec % 3600) // 60
            lines.append(f"- **Uptime:** {hours}h {minutes}m")

            last_test = health.get("last_test_status", "unknown")
            test_icon = "✓" if last_test == "passed" else "✗"
            lines.append(f"- **Last Test:** {test_icon} {last_test}")

        return "\n".join(lines)

    def generate_network_mindmap(
        self,
        agents: List[Dict[str, Any]],
        topology_name: str = "Network Topology"
    ) -> str:
        """
        Generate a network-wide mind map showing all agents

        Args:
            agents: List of agent state dictionaries
            topology_name: Name for the topology

        Returns:
            Markdown string for Markmap rendering
        """
        lines = [
            f"# {topology_name}",
            "",
            f"- **Total Agents:** {len(agents)}",
        ]

        # Group by protocol
        ospf_agents = []
        bgp_agents = []
        other_agents = []

        for agent in agents:
            identity = agent.get("identity", {})
            protocols = identity.get("protocols", [])

            if "OSPF" in protocols or "OSPFv3" in protocols:
                ospf_agents.append(agent)
            elif "iBGP" in protocols or "eBGP" in protocols:
                bgp_agents.append(agent)
            else:
                other_agents.append(agent)

        # OSPF Domain
        if ospf_agents:
            lines.extend(["", "## OSPF Domain"])
            for agent in ospf_agents:
                identity = agent.get("identity", {})
                ospf = agent.get("ospf", {})
                lines.append(f"### {identity.get('hostname')} ({identity.get('router_id')})")
                lines.append(f"- Area: {ospf.get('area', '0.0.0.0')}")
                lines.append(f"- Neighbors: {len(ospf.get('neighbors', []))}")

        # BGP Domain
        if bgp_agents:
            lines.extend(["", "## BGP Domain"])
            for agent in bgp_agents:
                identity = agent.get("identity", {})
                bgp = agent.get("bgp", {})
                lines.append(f"### AS {bgp.get('local_as', '?')} - {identity.get('hostname')}")
                lines.append(f"- Router ID: {identity.get('router_id')}")
                lines.append(f"- Peers: {len(bgp.get('peers', []))}")

        # Other Agents
        if other_agents:
            lines.extend(["", "## Other Agents"])
            for agent in other_agents:
                identity = agent.get("identity", {})
                lines.append(f"### {identity.get('hostname')}")
                lines.append(f"- Router ID: {identity.get('router_id')}")

        return "\n".join(lines)

    def generate_diff_mindmap(
        self,
        old_state: Dict[str, Any],
        new_state: Dict[str, Any]
    ) -> str:
        """
        Generate a diff mind map showing changes between states

        Args:
            old_state: Previous state
            new_state: Current state

        Returns:
            Markdown string highlighting changes
        """
        identity = new_state.get("identity", {})
        hostname = identity.get("hostname", "Unknown")

        lines = [
            f"# State Changes: {hostname}",
            "",
            "## Changes Detected",
        ]

        # Compare interfaces
        old_intfs = {i.get("name"): i for i in old_state.get("interfaces", [])}
        new_intfs = {i.get("name"): i for i in new_state.get("interfaces", [])}

        for name, new_intf in new_intfs.items():
            old_intf = old_intfs.get(name)
            if not old_intf:
                lines.append(f"### + Interface Added: {name}")
                lines.append(f"- IP: {new_intf.get('ip')}")
            elif old_intf.get("state") != new_intf.get("state"):
                lines.append(f"### ~ Interface State Changed: {name}")
                lines.append(f"- {old_intf.get('state')} -> {new_intf.get('state')}")

        for name in old_intfs:
            if name not in new_intfs:
                lines.append(f"### - Interface Removed: {name}")

        # Compare OSPF neighbors
        old_ospf = old_state.get("ospf", {})
        new_ospf = new_state.get("ospf", {})

        old_nbrs = {n.get("neighbor_id"): n for n in old_ospf.get("neighbors", [])}
        new_nbrs = {n.get("neighbor_id"): n for n in new_ospf.get("neighbors", [])}

        for nbr_id, new_nbr in new_nbrs.items():
            old_nbr = old_nbrs.get(nbr_id)
            if not old_nbr:
                lines.append(f"### + OSPF Neighbor Up: {nbr_id}")
                lines.append(f"- State: {new_nbr.get('state')}")
            elif old_nbr.get("state") != new_nbr.get("state"):
                lines.append(f"### ~ OSPF State Change: {nbr_id}")
                lines.append(f"- {old_nbr.get('state')} -> {new_nbr.get('state')}")

        for nbr_id in old_nbrs:
            if nbr_id not in new_nbrs:
                lines.append(f"### - OSPF Neighbor Down: {nbr_id}")

        # Compare BGP peers
        old_bgp = old_state.get("bgp", {})
        new_bgp = new_state.get("bgp", {})

        old_peers = {p.get("peer_ip"): p for p in old_bgp.get("peers", [])}
        new_peers = {p.get("peer_ip"): p for p in new_bgp.get("peers", [])}

        for peer_ip, new_peer in new_peers.items():
            old_peer = old_peers.get(peer_ip)
            if not old_peer:
                lines.append(f"### + BGP Peer Up: {peer_ip}")
                lines.append(f"- Remote AS: {new_peer.get('remote_as')}")
            elif old_peer.get("state") != new_peer.get("state"):
                lines.append(f"### ~ BGP State Change: {peer_ip}")
                lines.append(f"- {old_peer.get('state')} -> {new_peer.get('state')}")

        for peer_ip in old_peers:
            if peer_ip not in new_peers:
                lines.append(f"### - BGP Peer Down: {peer_ip}")

        if len(lines) == 4:  # Only header, no changes
            lines.append("- No changes detected")

        return "\n".join(lines)


class MarkmapClient:
    """
    Markmap MCP Client for network visualization

    Provides methods to:
    - Collect agent network state
    - Generate mind map markdown
    - Render to SVG (via MCP server)
    """

    def __init__(self, mcp_url: Optional[str] = None):
        """
        Initialize Markmap client

        Args:
            mcp_url: Optional URL to Markmap MCP server
        """
        self.mcp_url = mcp_url
        self.generator = MarkmapGenerator()
        self._state_cache: Dict[str, Dict[str, Any]] = {}

    async def generate_agent_mindmap(
        self,
        agent_config: Dict[str, Any],
        options: Optional[MarkmapOptions] = None
    ) -> Dict[str, Any]:
        """
        Generate a mind map for an agent

        Args:
            agent_config: Agent TOON configuration
            options: Optional rendering options

        Returns:
            Dictionary with markdown and rendering info
        """
        collector = AgentStateCollector(agent_config)
        state = await collector.collect_state()

        # Cache state for diff comparison
        agent_id = agent_config.get("id", "unknown")
        old_state = self._state_cache.get(agent_id)
        self._state_cache[agent_id] = state

        markdown = self.generator.generate_agent_mindmap(state)

        result = {
            "agent_id": agent_id,
            "timestamp": datetime.now().isoformat(),
            "markdown": markdown,
            "state": state,
            "options": (options or self.generator.options).to_dict(),
        }

        # Include diff if we have previous state
        if old_state:
            diff_markdown = self.generator.generate_diff_mindmap(old_state, state)
            result["diff_markdown"] = diff_markdown

        return result

    async def generate_network_mindmap(
        self,
        agent_configs: List[Dict[str, Any]],
        topology_name: str = "Network Topology"
    ) -> Dict[str, Any]:
        """
        Generate a network-wide mind map

        Args:
            agent_configs: List of agent TOON configurations
            topology_name: Name for the topology

        Returns:
            Dictionary with markdown and rendering info
        """
        agents_state = []
        for config in agent_configs:
            collector = AgentStateCollector(config)
            state = await collector.collect_state()
            agents_state.append(state)

        markdown = self.generator.generate_network_mindmap(agents_state, topology_name)

        return {
            "topology_name": topology_name,
            "timestamp": datetime.now().isoformat(),
            "agent_count": len(agent_configs),
            "markdown": markdown,
            "options": self.generator.options.to_dict(),
        }

    def get_cached_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached state for an agent

        Args:
            agent_id: Agent identifier

        Returns:
            Cached state or None
        """
        return self._state_cache.get(agent_id)

    def clear_cache(self, agent_id: Optional[str] = None) -> None:
        """
        Clear state cache

        Args:
            agent_id: Optional specific agent to clear (clears all if None)
        """
        if agent_id:
            self._state_cache.pop(agent_id, None)
        else:
            self._state_cache.clear()


# Global Markmap client instance
_markmap_client: Optional[MarkmapClient] = None


def get_markmap_client() -> MarkmapClient:
    """Get or create the global Markmap client instance"""
    global _markmap_client
    if _markmap_client is None:
        _markmap_client = MarkmapClient()
    return _markmap_client
