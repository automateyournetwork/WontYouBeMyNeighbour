"""
Network Differ for State Comparison

Compares two network states (snapshots) and generates
a detailed diff showing what changed between them.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
import difflib

logger = logging.getLogger(__name__)


class DiffType(Enum):
    """Type of difference."""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


class DiffCategory(Enum):
    """Category of network change."""
    ROUTE = "route"
    NEIGHBOR = "neighbor"
    INTERFACE = "interface"
    PROTOCOL = "protocol"
    AGENT = "agent"
    CONFIG = "config"
    TOPOLOGY = "topology"


@dataclass
class DiffItem:
    """A single difference item."""
    diff_id: str
    diff_type: DiffType
    category: DiffCategory
    agent_id: Optional[str] = None
    key: str = ""
    old_value: Any = None
    new_value: Any = None
    description: str = ""
    impact: str = "low"  # low, medium, high, critical

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "diff_id": self.diff_id,
            "diff_type": self.diff_type.value,
            "category": self.category.value,
            "agent_id": self.agent_id,
            "key": self.key,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "description": self.description,
            "impact": self.impact,
        }


@dataclass
class DiffResult:
    """Result of comparing two network states."""
    diff_id: str
    timestamp: datetime
    before_snapshot_id: str
    after_snapshot_id: str
    before_timestamp: str
    after_timestamp: str
    items: List[DiffItem] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "diff_id": self.diff_id,
            "timestamp": self.timestamp.isoformat(),
            "before_snapshot_id": self.before_snapshot_id,
            "after_snapshot_id": self.after_snapshot_id,
            "before_timestamp": self.before_timestamp,
            "after_timestamp": self.after_timestamp,
            "items": [item.to_dict() for item in self.items],
            "summary": self.summary,
            "total_changes": len(self.items),
            "has_changes": len(self.items) > 0,
        }


class NetworkDiffer:
    """
    Network state differ.

    Compares two network snapshots and generates detailed
    diff results showing what changed.
    """

    # Singleton instance
    _instance: Optional["NetworkDiffer"] = None

    def __new__(cls) -> "NetworkDiffer":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._diff_counter = 0
        self._diff_history: List[DiffResult] = []
        self._max_history = 50

        logger.info("NetworkDiffer initialized")

    def _generate_diff_id(self) -> str:
        """Generate unique diff ID."""
        self._diff_counter += 1
        return f"diff-{self._diff_counter:06d}"

    def _generate_item_id(self, index: int) -> str:
        """Generate unique diff item ID."""
        return f"item-{self._diff_counter:06d}-{index:04d}"

    def compare_snapshots(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
    ) -> DiffResult:
        """
        Compare two network snapshots.

        Args:
            before: The earlier snapshot (dict from NetworkSnapshot.to_dict())
            after: The later snapshot (dict from NetworkSnapshot.to_dict())

        Returns:
            DiffResult with all detected changes
        """
        diff_id = self._generate_diff_id()
        items: List[DiffItem] = []
        item_index = 0

        # Compare agents
        agent_items, item_index = self._compare_agents(
            before.get("agents", {}),
            after.get("agents", {}),
            item_index,
        )
        items.extend(agent_items)

        # Compare topology
        topology_items, item_index = self._compare_topology(
            before.get("topology", {}),
            after.get("topology", {}),
            item_index,
        )
        items.extend(topology_items)

        # Compare routes
        route_items, item_index = self._compare_routes(
            before.get("routes", {}),
            after.get("routes", {}),
            item_index,
        )
        items.extend(route_items)

        # Compare neighbors
        neighbor_items, item_index = self._compare_neighbors(
            before.get("neighbors", {}),
            after.get("neighbors", {}),
            item_index,
        )
        items.extend(neighbor_items)

        # Compare protocols
        protocol_items, item_index = self._compare_protocols(
            before.get("protocols", {}),
            after.get("protocols", {}),
            item_index,
        )
        items.extend(protocol_items)

        # Calculate summary
        summary = self._calculate_summary(items)

        result = DiffResult(
            diff_id=diff_id,
            timestamp=datetime.now(),
            before_snapshot_id=before.get("snapshot_id", "unknown"),
            after_snapshot_id=after.get("snapshot_id", "unknown"),
            before_timestamp=before.get("timestamp", ""),
            after_timestamp=after.get("timestamp", ""),
            items=items,
            summary=summary,
        )

        # Store in history
        self._diff_history.append(result)
        if len(self._diff_history) > self._max_history:
            self._diff_history.pop(0)

        logger.info(f"Generated diff {diff_id}: {len(items)} changes")
        return result

    def _compare_agents(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        start_index: int,
    ) -> Tuple[List[DiffItem], int]:
        """Compare agent states."""
        items = []
        index = start_index

        before_ids = set(before.keys())
        after_ids = set(after.keys())

        # Added agents
        for agent_id in after_ids - before_ids:
            items.append(DiffItem(
                diff_id=self._generate_item_id(index),
                diff_type=DiffType.ADDED,
                category=DiffCategory.AGENT,
                agent_id=agent_id,
                key=f"agent:{agent_id}",
                new_value=after[agent_id],
                description=f"Agent '{agent_id}' added",
                impact="high",
            ))
            index += 1

        # Removed agents
        for agent_id in before_ids - after_ids:
            items.append(DiffItem(
                diff_id=self._generate_item_id(index),
                diff_type=DiffType.REMOVED,
                category=DiffCategory.AGENT,
                agent_id=agent_id,
                key=f"agent:{agent_id}",
                old_value=before[agent_id],
                description=f"Agent '{agent_id}' removed",
                impact="high",
            ))
            index += 1

        # Modified agents
        for agent_id in before_ids & after_ids:
            before_agent = before[agent_id]
            after_agent = after[agent_id]

            # Check status change
            if before_agent.get("status") != after_agent.get("status"):
                items.append(DiffItem(
                    diff_id=self._generate_item_id(index),
                    diff_type=DiffType.MODIFIED,
                    category=DiffCategory.AGENT,
                    agent_id=agent_id,
                    key=f"agent:{agent_id}:status",
                    old_value=before_agent.get("status"),
                    new_value=after_agent.get("status"),
                    description=f"Agent '{agent_id}' status changed: {before_agent.get('status')} → {after_agent.get('status')}",
                    impact="medium" if after_agent.get("status") == "running" else "high",
                ))
                index += 1

            # Check CPU change (significant)
            before_cpu = before_agent.get("cpu_percent", 0)
            after_cpu = after_agent.get("cpu_percent", 0)
            if abs(before_cpu - after_cpu) > 20:
                items.append(DiffItem(
                    diff_id=self._generate_item_id(index),
                    diff_type=DiffType.MODIFIED,
                    category=DiffCategory.AGENT,
                    agent_id=agent_id,
                    key=f"agent:{agent_id}:cpu",
                    old_value=before_cpu,
                    new_value=after_cpu,
                    description=f"Agent '{agent_id}' CPU changed: {before_cpu}% → {after_cpu}%",
                    impact="low" if after_cpu < 80 else "medium",
                ))
                index += 1

        return items, index

    def _compare_topology(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        start_index: int,
    ) -> Tuple[List[DiffItem], int]:
        """Compare topology changes."""
        items = []
        index = start_index

        # Compare nodes
        before_nodes = {n.get("id"): n for n in before.get("nodes", [])}
        after_nodes = {n.get("id"): n for n in after.get("nodes", [])}

        # Added nodes
        for node_id in set(after_nodes.keys()) - set(before_nodes.keys()):
            items.append(DiffItem(
                diff_id=self._generate_item_id(index),
                diff_type=DiffType.ADDED,
                category=DiffCategory.TOPOLOGY,
                key=f"node:{node_id}",
                new_value=after_nodes[node_id],
                description=f"Node '{node_id}' added to topology",
                impact="medium",
            ))
            index += 1

        # Removed nodes
        for node_id in set(before_nodes.keys()) - set(after_nodes.keys()):
            items.append(DiffItem(
                diff_id=self._generate_item_id(index),
                diff_type=DiffType.REMOVED,
                category=DiffCategory.TOPOLOGY,
                key=f"node:{node_id}",
                old_value=before_nodes[node_id],
                description=f"Node '{node_id}' removed from topology",
                impact="high",
            ))
            index += 1

        # Compare links
        before_links = {f"{l.get('source')}-{l.get('target')}": l for l in before.get("links", [])}
        after_links = {f"{l.get('source')}-{l.get('target')}": l for l in after.get("links", [])}

        # Added links
        for link_id in set(after_links.keys()) - set(before_links.keys()):
            items.append(DiffItem(
                diff_id=self._generate_item_id(index),
                diff_type=DiffType.ADDED,
                category=DiffCategory.TOPOLOGY,
                key=f"link:{link_id}",
                new_value=after_links[link_id],
                description=f"Link '{link_id}' added",
                impact="medium",
            ))
            index += 1

        # Removed links
        for link_id in set(before_links.keys()) - set(after_links.keys()):
            items.append(DiffItem(
                diff_id=self._generate_item_id(index),
                diff_type=DiffType.REMOVED,
                category=DiffCategory.TOPOLOGY,
                key=f"link:{link_id}",
                old_value=before_links[link_id],
                description=f"Link '{link_id}' removed",
                impact="high",
            ))
            index += 1

        # Link status changes
        for link_id in set(before_links.keys()) & set(after_links.keys()):
            if before_links[link_id].get("status") != after_links[link_id].get("status"):
                items.append(DiffItem(
                    diff_id=self._generate_item_id(index),
                    diff_type=DiffType.MODIFIED,
                    category=DiffCategory.TOPOLOGY,
                    key=f"link:{link_id}:status",
                    old_value=before_links[link_id].get("status"),
                    new_value=after_links[link_id].get("status"),
                    description=f"Link '{link_id}' status: {before_links[link_id].get('status')} → {after_links[link_id].get('status')}",
                    impact="high" if after_links[link_id].get("status") != "up" else "medium",
                ))
                index += 1

        return items, index

    def _compare_routes(
        self,
        before: Dict[str, List],
        after: Dict[str, List],
        start_index: int,
    ) -> Tuple[List[DiffItem], int]:
        """Compare routing tables."""
        items = []
        index = start_index

        all_agents = set(before.keys()) | set(after.keys())

        for agent_id in all_agents:
            before_routes = {r.get("prefix"): r for r in before.get(agent_id, [])}
            after_routes = {r.get("prefix"): r for r in after.get(agent_id, [])}

            # Added routes
            for prefix in set(after_routes.keys()) - set(before_routes.keys()):
                route = after_routes[prefix]
                items.append(DiffItem(
                    diff_id=self._generate_item_id(index),
                    diff_type=DiffType.ADDED,
                    category=DiffCategory.ROUTE,
                    agent_id=agent_id,
                    key=f"route:{agent_id}:{prefix}",
                    new_value=route,
                    description=f"Route {prefix} added via {route.get('next_hop')} ({route.get('protocol')})",
                    impact="low",
                ))
                index += 1

            # Removed routes
            for prefix in set(before_routes.keys()) - set(after_routes.keys()):
                route = before_routes[prefix]
                items.append(DiffItem(
                    diff_id=self._generate_item_id(index),
                    diff_type=DiffType.REMOVED,
                    category=DiffCategory.ROUTE,
                    agent_id=agent_id,
                    key=f"route:{agent_id}:{prefix}",
                    old_value=route,
                    description=f"Route {prefix} removed (was via {route.get('next_hop')})",
                    impact="medium",
                ))
                index += 1

            # Modified routes (next-hop or metric changed)
            for prefix in set(before_routes.keys()) & set(after_routes.keys()):
                before_route = before_routes[prefix]
                after_route = after_routes[prefix]

                if before_route.get("next_hop") != after_route.get("next_hop"):
                    items.append(DiffItem(
                        diff_id=self._generate_item_id(index),
                        diff_type=DiffType.MODIFIED,
                        category=DiffCategory.ROUTE,
                        agent_id=agent_id,
                        key=f"route:{agent_id}:{prefix}:next_hop",
                        old_value=before_route.get("next_hop"),
                        new_value=after_route.get("next_hop"),
                        description=f"Route {prefix} next-hop changed: {before_route.get('next_hop')} → {after_route.get('next_hop')}",
                        impact="medium",
                    ))
                    index += 1

        return items, index

    def _compare_neighbors(
        self,
        before: Dict[str, List],
        after: Dict[str, List],
        start_index: int,
    ) -> Tuple[List[DiffItem], int]:
        """Compare neighbor relationships."""
        items = []
        index = start_index

        all_agents = set(before.keys()) | set(after.keys())

        for agent_id in all_agents:
            before_nbrs = {n.get("neighbor"): n for n in before.get(agent_id, [])}
            after_nbrs = {n.get("neighbor"): n for n in after.get(agent_id, [])}

            # Added neighbors
            for nbr_id in set(after_nbrs.keys()) - set(before_nbrs.keys()):
                nbr = after_nbrs[nbr_id]
                items.append(DiffItem(
                    diff_id=self._generate_item_id(index),
                    diff_type=DiffType.ADDED,
                    category=DiffCategory.NEIGHBOR,
                    agent_id=agent_id,
                    key=f"neighbor:{agent_id}:{nbr_id}",
                    new_value=nbr,
                    description=f"Neighbor {nbr_id} established ({nbr.get('protocol')} - {nbr.get('state')})",
                    impact="medium",
                ))
                index += 1

            # Removed neighbors
            for nbr_id in set(before_nbrs.keys()) - set(after_nbrs.keys()):
                nbr = before_nbrs[nbr_id]
                items.append(DiffItem(
                    diff_id=self._generate_item_id(index),
                    diff_type=DiffType.REMOVED,
                    category=DiffCategory.NEIGHBOR,
                    agent_id=agent_id,
                    key=f"neighbor:{agent_id}:{nbr_id}",
                    old_value=nbr,
                    description=f"Neighbor {nbr_id} lost ({nbr.get('protocol')})",
                    impact="high",
                ))
                index += 1

            # State changes
            for nbr_id in set(before_nbrs.keys()) & set(after_nbrs.keys()):
                before_nbr = before_nbrs[nbr_id]
                after_nbr = after_nbrs[nbr_id]

                if before_nbr.get("state") != after_nbr.get("state"):
                    items.append(DiffItem(
                        diff_id=self._generate_item_id(index),
                        diff_type=DiffType.MODIFIED,
                        category=DiffCategory.NEIGHBOR,
                        agent_id=agent_id,
                        key=f"neighbor:{agent_id}:{nbr_id}:state",
                        old_value=before_nbr.get("state"),
                        new_value=after_nbr.get("state"),
                        description=f"Neighbor {nbr_id} state: {before_nbr.get('state')} → {after_nbr.get('state')}",
                        impact="medium" if after_nbr.get("state") == "FULL" else "high",
                    ))
                    index += 1

        return items, index

    def _compare_protocols(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        start_index: int,
    ) -> Tuple[List[DiffItem], int]:
        """Compare protocol states."""
        items = []
        index = start_index

        all_protocols = set(before.keys()) | set(after.keys())

        for protocol in all_protocols:
            before_proto = before.get(protocol, {})
            after_proto = after.get(protocol, {})

            if not before_proto and after_proto:
                items.append(DiffItem(
                    diff_id=self._generate_item_id(index),
                    diff_type=DiffType.ADDED,
                    category=DiffCategory.PROTOCOL,
                    key=f"protocol:{protocol}",
                    new_value=after_proto,
                    description=f"Protocol {protocol.upper()} enabled",
                    impact="high",
                ))
                index += 1

            elif before_proto and not after_proto:
                items.append(DiffItem(
                    diff_id=self._generate_item_id(index),
                    diff_type=DiffType.REMOVED,
                    category=DiffCategory.PROTOCOL,
                    key=f"protocol:{protocol}",
                    old_value=before_proto,
                    description=f"Protocol {protocol.upper()} disabled",
                    impact="high",
                ))
                index += 1

            else:
                # Check specific metrics
                for metric in ["neighbors", "peers", "lsdb_size", "spf_runs"]:
                    before_val = before_proto.get(metric)
                    after_val = after_proto.get(metric)

                    if before_val is not None and after_val is not None:
                        if before_val != after_val:
                            items.append(DiffItem(
                                diff_id=self._generate_item_id(index),
                                diff_type=DiffType.MODIFIED,
                                category=DiffCategory.PROTOCOL,
                                key=f"protocol:{protocol}:{metric}",
                                old_value=before_val,
                                new_value=after_val,
                                description=f"{protocol.upper()} {metric}: {before_val} → {after_val}",
                                impact="low",
                            ))
                            index += 1

        return items, index

    def _calculate_summary(self, items: List[DiffItem]) -> Dict[str, int]:
        """Calculate diff summary."""
        summary = {
            "total": len(items),
            "added": 0,
            "removed": 0,
            "modified": 0,
            "by_category": {},
            "by_impact": {"low": 0, "medium": 0, "high": 0, "critical": 0},
        }

        for item in items:
            if item.diff_type == DiffType.ADDED:
                summary["added"] += 1
            elif item.diff_type == DiffType.REMOVED:
                summary["removed"] += 1
            elif item.diff_type == DiffType.MODIFIED:
                summary["modified"] += 1

            cat = item.category.value
            summary["by_category"][cat] = summary["by_category"].get(cat, 0) + 1
            summary["by_impact"][item.impact] += 1

        return summary

    def compare_configs(
        self,
        before_config: str,
        after_config: str,
        context_lines: int = 3,
    ) -> Dict[str, Any]:
        """
        Compare two configuration strings.

        Returns a unified diff format result.
        """
        before_lines = before_config.splitlines(keepends=True)
        after_lines = after_config.splitlines(keepends=True)

        diff = list(difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile="before",
            tofile="after",
            n=context_lines,
        ))

        changes = []
        for line in diff:
            if line.startswith('+') and not line.startswith('+++'):
                changes.append({"type": "added", "line": line[1:].rstrip()})
            elif line.startswith('-') and not line.startswith('---'):
                changes.append({"type": "removed", "line": line[1:].rstrip()})

        return {
            "diff_text": "".join(diff),
            "changes": changes,
            "lines_added": len([c for c in changes if c["type"] == "added"]),
            "lines_removed": len([c for c in changes if c["type"] == "removed"]),
            "has_changes": len(changes) > 0,
        }

    def get_diff_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent diff history."""
        return [d.to_dict() for d in self._diff_history[-limit:]]

    def get_statistics(self) -> Dict[str, Any]:
        """Get differ statistics."""
        return {
            "total_diffs": len(self._diff_history),
            "total_changes": sum(len(d.items) for d in self._diff_history),
        }


# Singleton accessor
def get_network_differ() -> NetworkDiffer:
    """Get the network differ instance."""
    return NetworkDiffer()


# Convenience functions
def compare_snapshots(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two snapshots and return diff result."""
    result = get_network_differ().compare_snapshots(before, after)
    return result.to_dict()


def compare_configs(before_config: str, after_config: str) -> Dict[str, Any]:
    """Compare two configuration strings."""
    return get_network_differ().compare_configs(before_config, after_config)


def get_diff_summary(diff_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract summary from diff result."""
    return diff_result.get("summary", {})
