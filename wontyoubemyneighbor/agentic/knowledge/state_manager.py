"""
Network State Manager

Tracks real-time OSPF and BGP state, serializes for LLM context injection,
and provides snapshots for time-series analysis.
"""

import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import json
import copy


@dataclass
class NetworkSnapshot:
    """Point-in-time snapshot of network state"""
    timestamp: datetime
    ospf_state: Dict[str, Any]
    bgp_state: Dict[str, Any]
    routing_table: List[Dict[str, Any]]
    interface_stats: Dict[str, Any]
    metrics: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "ospf_state": self.ospf_state,
            "bgp_state": self.bgp_state,
            "routing_table": self.routing_table,
            "interface_stats": self.interface_stats,
            "metrics": self.metrics
        }

    def to_json(self) -> str:
        """Serialize to JSON"""
        return json.dumps(self.to_dict(), indent=2)


class NetworkStateManager:
    """
    Manages network state for agentic reasoning.

    Responsibilities:
    - Track OSPF state (neighbors, LSDB, areas)
    - Track BGP state (peers, RIB, attributes)
    - Serialize state for LLM context
    - Maintain snapshots for time-series analysis
    - Compute network metrics
    """

    def __init__(self, snapshot_retention: int = 100):
        self.ospf_interface = None
        self.bgp_speaker = None
        self.isis_speaker = None
        self.ospfv3_speaker = None
        self.snapshot_retention = snapshot_retention
        self.snapshots: List[NetworkSnapshot] = []

        # Current state caches
        self._current_ospf_state: Dict[str, Any] = {}
        self._current_bgp_state: Dict[str, Any] = {}

        # Extended data from dashboard tabs (LLDP, NetBox, tests, etc.)
        self._extended_data: Dict[str, Any] = {}
        self._current_isis_state: Dict[str, Any] = {}
        self._current_routing_table: List[Dict[str, Any]] = []
        self._interface_stats: Dict[str, Any] = {}

        # Full interface configuration (from agent config)
        self._interfaces: List[Dict[str, Any]] = []

        # Lock for thread-safe state access
        self._state_lock = asyncio.Lock()

    def get_ospf_state(self) -> Dict[str, Any]:
        """Thread-safe accessor for OSPF state (returns a copy)"""
        return copy.deepcopy(self._current_ospf_state)

    def get_bgp_state(self) -> Dict[str, Any]:
        """Thread-safe accessor for BGP state (returns a copy)"""
        return copy.deepcopy(self._current_bgp_state)

    def get_isis_state(self) -> Dict[str, Any]:
        """Thread-safe accessor for IS-IS state (returns a copy)"""
        return copy.deepcopy(self._current_isis_state)

    def get_routing_table(self) -> List[Dict[str, Any]]:
        """Thread-safe accessor for routing table (returns a copy)"""
        return copy.deepcopy(self._current_routing_table)

    def get_interfaces(self) -> List[Dict[str, Any]]:
        """Thread-safe accessor for interfaces (returns a copy)"""
        return copy.deepcopy(self._interfaces)

    def set_protocol_handlers(self, ospf_interface=None, bgp_speaker=None,
                              isis_speaker=None, ospfv3_speaker=None):
        """Inject protocol handlers (preserves existing values)"""
        if ospf_interface is not None:
            self.ospf_interface = ospf_interface
        if bgp_speaker is not None:
            self.bgp_speaker = bgp_speaker
        if isis_speaker is not None:
            self.isis_speaker = isis_speaker
        if ospfv3_speaker is not None:
            self.ospfv3_speaker = ospfv3_speaker

    def set_interfaces(self, interfaces: List[Dict[str, Any]]):
        """Set full interface configuration from agent config"""
        self._interfaces = interfaces

    async def update_state(self):
        """
        Update current network state from protocol handlers.

        Should be called periodically (e.g., every 10 seconds).
        """
        if self.ospf_interface:
            self._current_ospf_state = await self._get_ospf_state()

        if self.bgp_speaker:
            self._current_bgp_state = await self._get_bgp_state()

        if self.isis_speaker:
            self._current_isis_state = await self._get_isis_state()

        self._current_routing_table = await self._get_routing_table()

    async def _get_isis_state(self) -> Dict[str, Any]:
        """Extract IS-IS state from speaker"""
        if not self.isis_speaker:
            return {}

        try:
            # Get adjacencies
            adjacencies = []
            if hasattr(self.isis_speaker, 'adjacencies'):
                for adj in self.isis_speaker.adjacencies.values():
                    adjacencies.append({
                        "system_id": adj.neighbor_system_id,
                        "state": adj.state.name if hasattr(adj.state, 'name') else str(adj.state),
                        "level": adj.level,
                        "interface": adj.interface_name
                    })

            # Get LSDB stats
            lsdb_stats = {}
            if hasattr(self.isis_speaker, 'dual_lsdb'):
                if self.isis_speaker.dual_lsdb.l1_lsdb:
                    lsdb_stats['l1_lsps'] = len(self.isis_speaker.dual_lsdb.l1_lsdb.lsps)
                if self.isis_speaker.dual_lsdb.l2_lsdb:
                    lsdb_stats['l2_lsps'] = len(self.isis_speaker.dual_lsdb.l2_lsdb.lsps)

            # Get route count
            route_count = 0
            if hasattr(self.isis_speaker, 'spf_calculator'):
                routes = self.isis_speaker.spf_calculator.get_combined_routing_table()
                route_count = len(routes)

            return {
                "system_id": getattr(self.isis_speaker, 'system_id', 'N/A'),
                "adjacencies": adjacencies,
                "adjacency_count": len(adjacencies),
                "lsdb": lsdb_stats,
                "route_count": route_count
            }
        except Exception:
            return {}

    async def _get_ospf_state(self) -> Dict[str, Any]:
        """Extract OSPF state from interface"""
        if not self.ospf_interface:
            return {}

        # Gather neighbor state
        neighbors = []
        for neighbor in self.ospf_interface.neighbors.values():
            neighbors.append({
                "neighbor_id": neighbor.router_id,
                "state": neighbor.get_state_name(),
                "address": neighbor.ip_address,
                "priority": neighbor.priority,
                "state_changes": getattr(neighbor, "state_changes", 0)
            })

        # Gather LSDB state
        lsdb_summary = {
            "router_lsas": 0,
            "network_lsas": 0,
            "summary_lsas": 0,
            "external_lsas": 0,
            "total_lsas": 0
        }

        if hasattr(self.ospf_interface, "lsdb"):
            # LSDB is a LinkStateDatabase object, use get_all_lsas()
            for lsa in self.ospf_interface.lsdb.get_all_lsas():
                lsdb_summary["total_lsas"] += 1
                lsa_type = lsa.header.ls_type
                if lsa_type == 1:
                    lsdb_summary["router_lsas"] += 1
                elif lsa_type == 2:
                    lsdb_summary["network_lsas"] += 1
                elif lsa_type == 3:
                    lsdb_summary["summary_lsas"] += 1
                elif lsa_type == 5:
                    lsdb_summary["external_lsas"] += 1

        return {
            "router_id": self.ospf_interface.router_id,
            "area_id": getattr(self.ospf_interface, "area_id", "0.0.0.0"),
            "interface_name": getattr(self.ospf_interface, "interface", ""),
            "neighbors": neighbors,
            "neighbor_count": len(neighbors),
            "full_neighbors": sum(1 for n in neighbors if n["state"] == "Full"),
            "lsdb": lsdb_summary
        }

    async def _get_bgp_state(self) -> Dict[str, Any]:
        """Extract BGP state from speaker"""
        if not self.bgp_speaker:
            return {}

        # Gather peer state
        peers = []
        for peer in self.bgp_speaker.agent.sessions.values():
            peers.append({
                "peer": str(peer.config.peer_ip),
                "peer_as": peer.config.peer_as,
                "state": peer.fsm.get_state_name(),
                "local_addr": str(peer.config.local_ip),
                "is_ibgp": peer.config.peer_as == self.bgp_speaker.local_as,
                "uptime": getattr(peer, "uptime", 0),
                "message_stats": getattr(peer, "message_stats", {})
            })

        # Gather RIB statistics
        rib_stats = {
            "total_routes": self.bgp_speaker.agent.loc_rib.size(),
            "ipv4_routes": 0,
            "ipv6_routes": 0
        }

        # Count IPv4 vs IPv6 routes
        for route in self.bgp_speaker.agent.loc_rib.get_all_routes():
            # Check if prefix contains ':' for IPv6
            if ':' in route.prefix:
                rib_stats["ipv6_routes"] += 1
            else:
                rib_stats["ipv4_routes"] += 1

        return {
            "local_as": self.bgp_speaker.local_as,
            "router_id": str(self.bgp_speaker.router_id),
            "peers": peers,
            "peer_count": len(peers),
            "established_peers": sum(1 for p in peers if p["state"] == "Established"),
            "route_count": rib_stats["total_routes"],
            "rib_stats": rib_stats
        }

    async def _get_routing_table(self) -> List[Dict[str, Any]]:
        """Get current routing table (combined OSPF + BGP)"""
        routes = []

        # OSPF routes from SPF calculator
        if self.ospf_interface:
            try:
                if hasattr(self.ospf_interface, 'spf_calc') and self.ospf_interface.spf_calc:
                    ospf_routes = self.ospf_interface.spf_calc.routing_table
                    for prefix, route_entry in ospf_routes.items():
                        routes.append({
                            "network": prefix,
                            "next_hop": route_entry.next_hop or "direct",
                            "protocol": "ospf",
                            "cost": route_entry.cost,
                            "path": route_entry.path if hasattr(route_entry, 'path') else []
                        })
            except Exception:
                pass

        # BGP routes from Loc-RIB
        if self.bgp_speaker:
            try:
                all_routes = self.bgp_speaker.agent.loc_rib.get_all_routes()
                for route in all_routes:
                    # Extract AS path
                    as_path = []
                    if route.has_attribute(2):  # ATTR_AS_PATH
                        as_path_attr = route.get_attribute(2)
                        if hasattr(as_path_attr, 'as_list'):
                            as_path = as_path_attr.as_list()

                    routes.append({
                        "network": route.prefix,
                        "next_hop": route.next_hop or "",
                        "protocol": "bgp",
                        "as_path": as_path,
                        "source": route.source
                    })
            except Exception:
                pass

        # IS-IS routes from SPF calculator
        if self.isis_speaker:
            try:
                if hasattr(self.isis_speaker, 'spf_calculator'):
                    isis_routes = self.isis_speaker.spf_calculator.get_combined_routing_table()
                    for prefix, route in isis_routes.items():
                        routes.append({
                            "network": prefix,
                            "next_hop": route.next_hop or "direct",
                            "protocol": "isis",
                            "cost": route.metric,
                            "level": route.level,
                            "route_type": getattr(route, 'route_type', 'internal')
                        })
                elif hasattr(self.isis_speaker, 'get_routes'):
                    for route in self.isis_speaker.get_routes():
                        routes.append({
                            "network": route.prefix,
                            "next_hop": route.next_hop or "direct",
                            "protocol": "isis",
                            "cost": route.metric,
                            "level": route.level
                        })
            except Exception:
                pass

        return routes

    def create_snapshot(self) -> NetworkSnapshot:
        """
        Create a point-in-time snapshot of network state.

        Returns NetworkSnapshot that can be serialized.
        """
        # Compute metrics
        metrics = self._compute_metrics()

        snapshot = NetworkSnapshot(
            timestamp=datetime.utcnow(),
            ospf_state=self._current_ospf_state.copy(),
            bgp_state=self._current_bgp_state.copy(),
            routing_table=self._current_routing_table.copy(),
            interface_stats=self._interface_stats.copy(),
            metrics=metrics
        )

        # Store snapshot
        self.snapshots.append(snapshot)

        # Maintain retention limit
        if len(self.snapshots) > self.snapshot_retention:
            self.snapshots = self.snapshots[-self.snapshot_retention:]

        return snapshot

    def _compute_metrics(self) -> Dict[str, float]:
        """Compute network health metrics"""
        metrics = {
            "ospf_neighbor_stability": 1.0,
            "bgp_peer_stability": 1.0,
            "route_count": len(self._current_routing_table),
            "health_score": 100.0
        }

        # OSPF neighbor stability
        if self._current_ospf_state:
            neighbors = self._current_ospf_state.get("neighbors", [])
            if neighbors:
                full_count = sum(1 for n in neighbors if n["state"] == "Full")
                metrics["ospf_neighbor_stability"] = full_count / len(neighbors)

        # BGP peer stability
        if self._current_bgp_state:
            peers = self._current_bgp_state.get("peers", [])
            if peers:
                established_count = sum(1 for p in peers if p["state"] == "Established")
                metrics["bgp_peer_stability"] = established_count / len(peers)

        # Overall health score
        metrics["health_score"] = (
            metrics["ospf_neighbor_stability"] * 50 +
            metrics["bgp_peer_stability"] * 50
        )

        return metrics

    def get_llm_context(self) -> Dict[str, Any]:
        """
        Get network state formatted for LLM context injection.

        Returns structured data optimized for LLM understanding.
        """
        return {
            "interfaces": self._interfaces,
            "ospf": self._current_ospf_state,
            "bgp": self._current_bgp_state,
            "isis": self._current_isis_state,
            "routes": self._current_routing_table,
            "metrics": self._compute_metrics(),
            # Extended data from dashboard tabs (populated by set_extended_data)
            "lldp": self._extended_data.get("lldp", {}),
            "lacp": self._extended_data.get("lacp", {}),
            "netbox": self._extended_data.get("netbox", {}),
            "test_results": self._extended_data.get("test_results", []),
            "prometheus_metrics": self._extended_data.get("prometheus_metrics", {}),
        }

    def set_extended_data(self, key: str, data: Any):
        """
        Store extended data from dashboard tabs for LLM context.

        Called by API endpoints to cache data that the LLM can access.
        """
        if not hasattr(self, '_extended_data'):
            self._extended_data = {}
        self._extended_data[key] = data
        logger.debug(f"Extended data updated: {key}")

    def get_extended_data(self, key: str) -> Any:
        """Get extended data by key"""
        if not hasattr(self, '_extended_data'):
            self._extended_data = {}
        return self._extended_data.get(key)

    def get_state_summary(self) -> str:
        """
        Get human-readable state summary.

        Returns formatted string suitable for display or LLM context.
        """
        lines = []
        lines.append("Network State Summary")
        lines.append("=" * 50)

        # Interfaces summary
        if self._interfaces:
            lines.append(f"\nInterfaces ({len(self._interfaces)} total):")
            for iface in self._interfaces:
                name = iface.get('name', iface.get('id', 'unknown'))
                iface_type = iface.get('type', 'eth')
                addrs = iface.get('addresses', [])
                status = iface.get('status', 'up')
                type_names = {'eth': 'Ethernet', 'lo': 'Loopback', 'vlan': 'VLAN', 'tun': 'Tunnel'}
                type_display = type_names.get(iface_type, iface_type)
                addr_str = ', '.join(addrs) if addrs else 'No IP'
                lines.append(f"  {name} ({type_display}): {addr_str} [{status}]")

        # OSPF summary
        if self._current_ospf_state:
            ospf = self._current_ospf_state
            lines.append(f"\nOSPF:")
            lines.append(f"  Router ID: {ospf.get('router_id', 'N/A')}")
            lines.append(f"  Area: {ospf.get('area_id', 'N/A')}")
            lines.append(f"  Interface: {ospf.get('interface_name', 'N/A')}")
            lines.append(f"  Neighbors: {ospf.get('full_neighbors', 0)}/{ospf.get('neighbor_count', 0)} Full")
            lsdb = ospf.get('lsdb', {})
            lines.append(f"  LSAs: {lsdb.get('total_lsas', 0)} total ({lsdb.get('router_lsas', 0)} router)")

        # BGP summary
        if self._current_bgp_state:
            bgp = self._current_bgp_state
            lines.append(f"\nBGP:")
            lines.append(f"  Router ID: {bgp.get('router_id', 'N/A')}")
            lines.append(f"  Local AS: {bgp.get('local_as', 'N/A')}")
            lines.append(f"  Peers: {bgp.get('established_peers', 0)}/{bgp.get('peer_count', 0)} Established")
            rib = bgp.get('rib_stats', {})
            lines.append(f"  Routes: {rib.get('total_routes', 0)} total ({rib.get('ipv4_routes', 0)} IPv4, {rib.get('ipv6_routes', 0)} IPv6)")

        # Metrics
        metrics = self._compute_metrics()
        lines.append(f"\nHealth:")
        lines.append(f"  Overall Score: {metrics['health_score']:.1f}/100")
        lines.append(f"  OSPF Stability: {metrics['ospf_neighbor_stability']*100:.0f}%")
        lines.append(f"  BGP Stability: {metrics['bgp_peer_stability']*100:.0f}%")

        return "\n".join(lines)

    def get_snapshot_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent snapshot history"""
        recent = self.snapshots[-limit:]
        return [s.to_dict() for s in recent]

    def detect_state_changes(self) -> List[str]:
        """
        Detect significant state changes since last snapshot.

        Returns list of change descriptions.
        """
        if len(self.snapshots) < 2:
            return []

        current = self.snapshots[-1]
        previous = self.snapshots[-2]
        changes = []

        # Check OSPF neighbor changes
        current_ospf_neighbors = set(
            n["neighbor_id"] for n in current.ospf_state.get("neighbors", [])
        )
        previous_ospf_neighbors = set(
            n["neighbor_id"] for n in previous.ospf_state.get("neighbors", [])
        )

        new_neighbors = current_ospf_neighbors - previous_ospf_neighbors
        lost_neighbors = previous_ospf_neighbors - current_ospf_neighbors

        for neighbor_id in new_neighbors:
            changes.append(f"OSPF neighbor {neighbor_id} added")
        for neighbor_id in lost_neighbors:
            changes.append(f"OSPF neighbor {neighbor_id} lost")

        # Check BGP peer changes
        current_bgp_peers = set(
            p["peer"] for p in current.bgp_state.get("peers", [])
        )
        previous_bgp_peers = set(
            p["peer"] for p in previous.bgp_state.get("peers", [])
        )

        new_peers = current_bgp_peers - previous_bgp_peers
        lost_peers = previous_bgp_peers - current_bgp_peers

        for peer in new_peers:
            changes.append(f"BGP peer {peer} added")
        for peer in lost_peers:
            changes.append(f"BGP peer {peer} lost")

        # Check route count change
        route_delta = len(current.routing_table) - len(previous.routing_table)
        if abs(route_delta) > 10:
            changes.append(f"Route count changed by {route_delta:+d}")

        return changes

    def export_state(self, filepath: str):
        """Export current state to JSON file"""
        state = {
            "timestamp": datetime.utcnow().isoformat(),
            "ospf": self._current_ospf_state,
            "bgp": self._current_bgp_state,
            "routing_table": self._current_routing_table,
            "metrics": self._compute_metrics(),
            "snapshot_count": len(self.snapshots)
        }

        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2)
