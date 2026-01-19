"""
Network State Manager

Tracks real-time OSPF and BGP state, serializes for LLM context injection,
and provides snapshots for time-series analysis.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import json


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
        self.snapshot_retention = snapshot_retention
        self.snapshots: List[NetworkSnapshot] = []

        # Current state caches
        self._current_ospf_state: Dict[str, Any] = {}
        self._current_bgp_state: Dict[str, Any] = {}
        self._current_routing_table: List[Dict[str, Any]] = []
        self._interface_stats: Dict[str, Any] = {}

    def set_protocol_handlers(self, ospf_interface=None, bgp_speaker=None):
        """Inject OSPF and BGP protocol handlers"""
        self.ospf_interface = ospf_interface
        self.bgp_speaker = bgp_speaker

    async def update_state(self):
        """
        Update current network state from protocol handlers.

        Should be called periodically (e.g., every 10 seconds).
        """
        if self.ospf_interface:
            self._current_ospf_state = await self._get_ospf_state()

        if self.bgp_speaker:
            self._current_bgp_state = await self._get_bgp_state()

        self._current_routing_table = await self._get_routing_table()

    async def _get_ospf_state(self) -> Dict[str, Any]:
        """Extract OSPF state from interface"""
        if not self.ospf_interface:
            return {}

        # Gather neighbor state
        neighbors = []
        for neighbor in self.ospf_interface.neighbors.values():
            neighbors.append({
                "neighbor_id": neighbor.neighbor_id,
                "state": neighbor.state,
                "address": neighbor.address,
                "priority": neighbor.priority,
                "dr": neighbor.dr,
                "bdr": neighbor.bdr,
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
            for lsa in self.ospf_interface.lsdb.values():
                lsdb_summary["total_lsas"] += 1
                lsa_type = lsa.get("type", 0)
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
            "interface_name": self.ospf_interface.interface_name,
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
        for peer in self.bgp_speaker.peers.values():
            peers.append({
                "peer": str(peer.peer_addr),
                "peer_as": peer.peer_as,
                "state": peer.state,
                "local_addr": str(getattr(peer, "local_addr", "")),
                "is_ibgp": peer.peer_as == self.bgp_speaker.local_as,
                "uptime": getattr(peer, "uptime", 0),
                "message_stats": getattr(peer, "message_stats", {})
            })

        # Gather RIB statistics
        rib_stats = {
            "total_routes": len(self.bgp_speaker.rib) if hasattr(self.bgp_speaker, "rib") else 0,
            "ipv4_routes": 0,
            "ipv6_routes": 0
        }

        if hasattr(self.bgp_speaker, "rib"):
            for route_key in self.bgp_speaker.rib.keys():
                # route_key is (prefix, prefix_len, afi, safi)
                afi = route_key[2] if len(route_key) > 2 else 1
                if afi == 1:
                    rib_stats["ipv4_routes"] += 1
                elif afi == 2:
                    rib_stats["ipv6_routes"] += 1

        return {
            "local_as": self.bgp_speaker.local_as,
            "router_id": str(self.bgp_speaker.router_id),
            "peers": peers,
            "peer_count": len(peers),
            "established_peers": sum(1 for p in peers if p["state"] == "Established"),
            "rib_stats": rib_stats
        }

    async def _get_routing_table(self) -> List[Dict[str, Any]]:
        """Get current routing table (combined OSPF + BGP)"""
        routes = []

        # BGP routes
        if self.bgp_speaker and hasattr(self.bgp_speaker, "rib"):
            for route_key, route_info in self.bgp_speaker.rib.items():
                prefix, prefix_len = route_key[0], route_key[1]
                routes.append({
                    "network": f"{prefix}/{prefix_len}",
                    "next_hop": str(route_info.get("next_hop", "")),
                    "protocol": "bgp",
                    "as_path": route_info.get("as_path", []),
                    "local_pref": route_info.get("local_pref", 100),
                    "med": route_info.get("med", 0)
                })

        # OSPF routes (would come from LSDB calculation)
        # Simplified for now

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
            "ospf": self._current_ospf_state,
            "bgp": self._current_bgp_state,
            "routes": self._current_routing_table,
            "metrics": self._compute_metrics()
        }

    def get_state_summary(self) -> str:
        """
        Get human-readable state summary.

        Returns formatted string suitable for display or LLM context.
        """
        lines = []
        lines.append("Network State Summary")
        lines.append("=" * 50)

        # OSPF summary
        if self._current_ospf_state:
            ospf = self._current_ospf_state
            lines.append(f"\nOSPF:")
            lines.append(f"  Router ID: {ospf.get('router_id', 'N/A')}")
            lines.append(f"  Neighbors: {ospf.get('full_neighbors', 0)}/{ospf.get('neighbor_count', 0)} Full")
            lsdb = ospf.get('lsdb', {})
            lines.append(f"  LSAs: {lsdb.get('total_lsas', 0)} total")

        # BGP summary
        if self._current_bgp_state:
            bgp = self._current_bgp_state
            lines.append(f"\nBGP:")
            lines.append(f"  Local AS: {bgp.get('local_as', 'N/A')}")
            lines.append(f"  Peers: {bgp.get('established_peers', 0)}/{bgp.get('peer_count', 0)} Established")
            rib = bgp.get('rib_stats', {})
            lines.append(f"  Routes: {rib.get('total_routes', 0)} total")

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
