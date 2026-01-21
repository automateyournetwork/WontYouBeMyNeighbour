"""
What-If Simulator - Simulates network changes and failures

Provides:
- Link failure simulation
- Node failure simulation
- Configuration change simulation
- Traffic shift analysis
- Convergence prediction
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Tuple
from copy import deepcopy
import uuid

logger = logging.getLogger("WhatIfSimulator")


class ScenarioType(Enum):
    """Types of what-if scenarios"""
    # Failure scenarios
    LINK_FAILURE = "link_failure"
    NODE_FAILURE = "node_failure"
    MULTI_LINK_FAILURE = "multi_link_failure"
    MULTI_NODE_FAILURE = "multi_node_failure"

    # Configuration changes
    OSPF_COST_CHANGE = "ospf_cost_change"
    BGP_POLICY_CHANGE = "bgp_policy_change"
    ROUTE_ADD = "route_add"
    ROUTE_REMOVE = "route_remove"

    # Capacity changes
    BANDWIDTH_CHANGE = "bandwidth_change"
    NEW_LINK = "new_link"
    LINK_REMOVAL = "link_removal"

    # Traffic changes
    TRAFFIC_SHIFT = "traffic_shift"
    TRAFFIC_SPIKE = "traffic_spike"

    # Protocol changes
    PROTOCOL_ENABLE = "protocol_enable"
    PROTOCOL_DISABLE = "protocol_disable"

    # Maintenance
    MAINTENANCE_WINDOW = "maintenance_window"


class ImpactLevel(Enum):
    """Impact severity level"""
    NONE = "none"
    MINIMAL = "minimal"
    MODERATE = "moderate"
    SIGNIFICANT = "significant"
    SEVERE = "severe"
    CATASTROPHIC = "catastrophic"


@dataclass
class Scenario:
    """
    What-if scenario definition

    Attributes:
        scenario_id: Unique identifier
        scenario_type: Type of scenario
        name: Human-readable name
        description: Detailed description
        parameters: Scenario-specific parameters
        created_at: When scenario was created
    """
    scenario_id: str
    scenario_type: ScenarioType
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_type": self.scenario_type.value,
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class SimulationResult:
    """
    Result of a what-if simulation

    Attributes:
        result_id: Unique identifier
        scenario: The simulated scenario
        impact_level: Overall impact severity
        affected_nodes: Nodes affected by the change
        affected_links: Links affected by the change
        traffic_redistribution: How traffic would be redistributed
        convergence_time_ms: Estimated convergence time
        reachability_impact: Prefixes that lose reachability
        alternate_paths: Alternate paths that would be used
        warnings: Warning messages
        recommendations: Suggested actions
        simulation_time: Time to run simulation
        simulated_at: When simulation was run
    """
    result_id: str
    scenario: Scenario
    impact_level: ImpactLevel
    affected_nodes: List[str] = field(default_factory=list)
    affected_links: List[str] = field(default_factory=list)
    traffic_redistribution: Dict[str, Any] = field(default_factory=dict)
    convergence_time_ms: int = 0
    reachability_impact: List[str] = field(default_factory=list)
    alternate_paths: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    simulation_time_ms: float = 0
    simulated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id,
            "scenario": self.scenario.to_dict(),
            "impact_level": self.impact_level.value,
            "affected_nodes": self.affected_nodes,
            "affected_links": self.affected_links,
            "traffic_redistribution": self.traffic_redistribution,
            "convergence_time_ms": self.convergence_time_ms,
            "reachability_impact": self.reachability_impact,
            "alternate_paths": self.alternate_paths,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
            "simulation_time_ms": self.simulation_time_ms,
            "simulated_at": self.simulated_at.isoformat()
        }


class WhatIfSimulator:
    """
    Simulates what-if scenarios for network planning
    """

    def __init__(self):
        """Initialize the what-if simulator"""
        self._scenarios: List[Scenario] = []
        self._results: List[SimulationResult] = []
        self._scenario_counter = 0
        self._result_counter = 0

        # Network state (loaded from actual network or provided)
        self._topology: Dict[str, Any] = {"nodes": [], "links": []}
        self._routing_table: Dict[str, List[Dict[str, Any]]] = {}
        self._ospf_state: Dict[str, Any] = {}
        self._bgp_state: Dict[str, Any] = {}

    def _generate_scenario_id(self) -> str:
        """Generate unique scenario ID"""
        self._scenario_counter += 1
        return f"scenario-{self._scenario_counter:06d}"

    def _generate_result_id(self) -> str:
        """Generate unique result ID"""
        self._result_counter += 1
        return f"result-{self._result_counter:06d}"

    def load_topology(self, topology: Dict[str, Any]) -> None:
        """
        Load network topology for simulation

        Args:
            topology: Network topology with nodes and links
        """
        self._topology = deepcopy(topology)
        logger.info(f"Loaded topology with {len(topology.get('nodes', []))} nodes "
                   f"and {len(topology.get('links', []))} links")

    def load_routing_table(self, routing_table: Dict[str, List[Dict[str, Any]]]) -> None:
        """Load routing table for simulation"""
        self._routing_table = deepcopy(routing_table)

    def load_ospf_state(self, ospf_state: Dict[str, Any]) -> None:
        """Load OSPF state for simulation"""
        self._ospf_state = deepcopy(ospf_state)

    def load_bgp_state(self, bgp_state: Dict[str, Any]) -> None:
        """Load BGP state for simulation"""
        self._bgp_state = deepcopy(bgp_state)

    def create_scenario(
        self,
        scenario_type: ScenarioType,
        name: str,
        description: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Scenario:
        """
        Create a new what-if scenario

        Args:
            scenario_type: Type of scenario
            name: Human-readable name
            description: Detailed description
            parameters: Scenario-specific parameters

        Returns:
            Created Scenario
        """
        scenario = Scenario(
            scenario_id=self._generate_scenario_id(),
            scenario_type=scenario_type,
            name=name,
            description=description,
            parameters=parameters or {}
        )
        self._scenarios.append(scenario)
        logger.info(f"Created scenario: {scenario.name}")
        return scenario

    def simulate(self, scenario: Scenario) -> SimulationResult:
        """
        Run a what-if simulation

        Args:
            scenario: Scenario to simulate

        Returns:
            SimulationResult with impact analysis
        """
        start_time = datetime.now()

        # Create working copy of topology
        sim_topology = deepcopy(self._topology)

        # Run appropriate simulation based on type
        if scenario.scenario_type == ScenarioType.LINK_FAILURE:
            result = self._simulate_link_failure(scenario, sim_topology)
        elif scenario.scenario_type == ScenarioType.NODE_FAILURE:
            result = self._simulate_node_failure(scenario, sim_topology)
        elif scenario.scenario_type == ScenarioType.MULTI_LINK_FAILURE:
            result = self._simulate_multi_link_failure(scenario, sim_topology)
        elif scenario.scenario_type == ScenarioType.MULTI_NODE_FAILURE:
            result = self._simulate_multi_node_failure(scenario, sim_topology)
        elif scenario.scenario_type == ScenarioType.OSPF_COST_CHANGE:
            result = self._simulate_ospf_cost_change(scenario, sim_topology)
        elif scenario.scenario_type == ScenarioType.BGP_POLICY_CHANGE:
            result = self._simulate_bgp_policy_change(scenario, sim_topology)
        elif scenario.scenario_type == ScenarioType.NEW_LINK:
            result = self._simulate_new_link(scenario, sim_topology)
        elif scenario.scenario_type == ScenarioType.LINK_REMOVAL:
            result = self._simulate_link_removal(scenario, sim_topology)
        elif scenario.scenario_type == ScenarioType.TRAFFIC_SPIKE:
            result = self._simulate_traffic_spike(scenario, sim_topology)
        elif scenario.scenario_type == ScenarioType.MAINTENANCE_WINDOW:
            result = self._simulate_maintenance(scenario, sim_topology)
        else:
            result = self._simulate_generic(scenario, sim_topology)

        # Calculate simulation time
        end_time = datetime.now()
        result.simulation_time_ms = (end_time - start_time).total_seconds() * 1000

        self._results.append(result)
        logger.info(f"Simulation complete: {scenario.name} - Impact: {result.impact_level.value}")
        return result

    def _simulate_link_failure(
        self,
        scenario: Scenario,
        topology: Dict[str, Any]
    ) -> SimulationResult:
        """Simulate a link failure"""
        link_id = scenario.parameters.get("link_id")
        source = scenario.parameters.get("source")
        target = scenario.parameters.get("target")

        affected_nodes = []
        affected_links = [link_id] if link_id else []
        reachability_impact = []
        alternate_paths = []
        warnings = []
        recommendations = []

        # Find the link
        link = None
        for l in topology.get("links", []):
            lid = l.get("id", f"{l.get('source')}-{l.get('target')}")
            if lid == link_id or (l.get("source") == source and l.get("target") == target):
                link = l
                if not link_id:
                    affected_links = [lid]
                break

        if not link:
            return SimulationResult(
                result_id=self._generate_result_id(),
                scenario=scenario,
                impact_level=ImpactLevel.NONE,
                warnings=["Link not found in topology"]
            )

        # Determine affected nodes
        affected_nodes = [link.get("source"), link.get("target")]

        # Find alternate paths
        alt_paths = self._find_alternate_paths(
            topology,
            link.get("source"),
            link.get("target"),
            exclude_links=[link]
        )

        # Calculate impact based on alternate paths
        if alt_paths:
            impact_level = ImpactLevel.MODERATE
            alternate_paths = alt_paths
            recommendations.append(
                f"Traffic will reroute via: {alt_paths[0].get('path', [])}"
            )
        else:
            impact_level = ImpactLevel.SEVERE
            reachability_impact.append(f"No alternate path between {link.get('source')} and {link.get('target')}")
            warnings.append("Connectivity will be lost between affected nodes")
            recommendations.append("Consider adding redundant links for resilience")

        # Estimate convergence time
        convergence_time = self._estimate_convergence_time(
            scenario.scenario_type,
            len(affected_nodes),
            has_alternate=bool(alt_paths)
        )

        # Traffic redistribution
        traffic_redistribution = {}
        if alt_paths:
            for path in alt_paths:
                for link_in_path in path.get("links", []):
                    traffic_redistribution[link_in_path] = {
                        "increase": 100 / len(alt_paths),  # Distributed load
                        "source": link_id
                    }

        return SimulationResult(
            result_id=self._generate_result_id(),
            scenario=scenario,
            impact_level=impact_level,
            affected_nodes=affected_nodes,
            affected_links=affected_links,
            traffic_redistribution=traffic_redistribution,
            convergence_time_ms=convergence_time,
            reachability_impact=reachability_impact,
            alternate_paths=alternate_paths,
            warnings=warnings,
            recommendations=recommendations
        )

    def _simulate_node_failure(
        self,
        scenario: Scenario,
        topology: Dict[str, Any]
    ) -> SimulationResult:
        """Simulate a node failure"""
        node_id = scenario.parameters.get("node_id")

        # Find all links connected to this node
        affected_links = []
        connected_nodes = set()
        for link in topology.get("links", []):
            if link.get("source") == node_id or link.get("target") == node_id:
                link_id = link.get("id", f"{link.get('source')}-{link.get('target')}")
                affected_links.append(link_id)
                if link.get("source") == node_id:
                    connected_nodes.add(link.get("target"))
                else:
                    connected_nodes.add(link.get("source"))

        affected_nodes = [node_id] + list(connected_nodes)
        warnings = []
        recommendations = []
        reachability_impact = []

        # Determine impact based on node role
        node_role = self._determine_node_role(topology, node_id)
        if node_role == "spine" or node_role == "core":
            impact_level = ImpactLevel.SEVERE
            warnings.append(f"Critical {node_role} node failure will affect multiple paths")
            recommendations.append("Consider graceful shutdown and traffic drain before maintenance")
        elif len(connected_nodes) > 3:
            impact_level = ImpactLevel.SIGNIFICANT
            warnings.append(f"Well-connected node with {len(connected_nodes)} neighbors")
        else:
            impact_level = ImpactLevel.MODERATE

        # Check for alternate paths between connected nodes
        for i, n1 in enumerate(list(connected_nodes)):
            for n2 in list(connected_nodes)[i+1:]:
                alt_paths = self._find_alternate_paths(topology, n1, n2, exclude_nodes=[node_id])
                if not alt_paths:
                    reachability_impact.append(f"Connectivity lost between {n1} and {n2}")
                    impact_level = ImpactLevel.CATASTROPHIC

        # Estimate convergence
        convergence_time = self._estimate_convergence_time(
            scenario.scenario_type,
            len(affected_nodes),
            has_alternate=bool(reachability_impact) == False
        )

        return SimulationResult(
            result_id=self._generate_result_id(),
            scenario=scenario,
            impact_level=impact_level,
            affected_nodes=affected_nodes,
            affected_links=affected_links,
            convergence_time_ms=convergence_time,
            reachability_impact=reachability_impact,
            warnings=warnings,
            recommendations=recommendations
        )

    def _simulate_multi_link_failure(
        self,
        scenario: Scenario,
        topology: Dict[str, Any]
    ) -> SimulationResult:
        """Simulate multiple link failures"""
        link_ids = scenario.parameters.get("link_ids", [])

        all_affected_nodes = set()
        all_affected_links = list(link_ids)
        warnings = []
        recommendations = []
        reachability_impact = []

        # Process each link
        for link in topology.get("links", []):
            link_id = link.get("id", f"{link.get('source')}-{link.get('target')}")
            if link_id in link_ids:
                all_affected_nodes.add(link.get("source"))
                all_affected_nodes.add(link.get("target"))

        # Check for severe impact patterns
        if len(all_affected_links) >= 3:
            impact_level = ImpactLevel.SEVERE
            warnings.append("Multiple simultaneous failures detected - possible correlated failure")
        else:
            impact_level = ImpactLevel.SIGNIFICANT

        recommendations.append("Review failure correlation - consider diverse routing paths")

        convergence_time = self._estimate_convergence_time(
            scenario.scenario_type,
            len(all_affected_nodes),
            has_alternate=True
        ) * len(all_affected_links)  # More failures = longer convergence

        return SimulationResult(
            result_id=self._generate_result_id(),
            scenario=scenario,
            impact_level=impact_level,
            affected_nodes=list(all_affected_nodes),
            affected_links=all_affected_links,
            convergence_time_ms=convergence_time,
            reachability_impact=reachability_impact,
            warnings=warnings,
            recommendations=recommendations
        )

    def _simulate_multi_node_failure(
        self,
        scenario: Scenario,
        topology: Dict[str, Any]
    ) -> SimulationResult:
        """Simulate multiple node failures"""
        node_ids = scenario.parameters.get("node_ids", [])

        all_affected_links = []
        warnings = [f"Simulating failure of {len(node_ids)} nodes simultaneously"]
        recommendations = []

        # Find all affected links
        for link in topology.get("links", []):
            if link.get("source") in node_ids or link.get("target") in node_ids:
                link_id = link.get("id", f"{link.get('source')}-{link.get('target')}")
                all_affected_links.append(link_id)

        # Multi-node failure is usually severe
        impact_level = ImpactLevel.CATASTROPHIC if len(node_ids) > 2 else ImpactLevel.SEVERE
        recommendations.append("Review failure domain isolation")
        recommendations.append("Consider geographic/rack diversity")

        convergence_time = self._estimate_convergence_time(
            scenario.scenario_type,
            len(node_ids) * 3,  # Assume average of 3 neighbors per node
            has_alternate=False
        )

        return SimulationResult(
            result_id=self._generate_result_id(),
            scenario=scenario,
            impact_level=impact_level,
            affected_nodes=list(node_ids),
            affected_links=all_affected_links,
            convergence_time_ms=convergence_time,
            warnings=warnings,
            recommendations=recommendations
        )

    def _simulate_ospf_cost_change(
        self,
        scenario: Scenario,
        topology: Dict[str, Any]
    ) -> SimulationResult:
        """Simulate OSPF cost change"""
        link_id = scenario.parameters.get("link_id")
        new_cost = scenario.parameters.get("new_cost", 10)
        old_cost = scenario.parameters.get("old_cost", 10)

        affected_links = [link_id]
        warnings = []
        recommendations = []
        traffic_redistribution = {}

        # Cost increase = traffic moves away
        if new_cost > old_cost:
            traffic_redistribution[link_id] = {
                "change": "decrease",
                "reason": f"Cost increased from {old_cost} to {new_cost}"
            }
            impact_level = ImpactLevel.MODERATE
            recommendations.append("Monitor other links for increased utilization")
        else:
            traffic_redistribution[link_id] = {
                "change": "increase",
                "reason": f"Cost decreased from {old_cost} to {new_cost}"
            }
            impact_level = ImpactLevel.MINIMAL
            recommendations.append("Monitor this link for potential congestion")

        # OSPF changes are generally quick to converge
        convergence_time = 500  # ~500ms for SPF recalculation

        return SimulationResult(
            result_id=self._generate_result_id(),
            scenario=scenario,
            impact_level=impact_level,
            affected_links=affected_links,
            traffic_redistribution=traffic_redistribution,
            convergence_time_ms=convergence_time,
            warnings=warnings,
            recommendations=recommendations
        )

    def _simulate_bgp_policy_change(
        self,
        scenario: Scenario,
        topology: Dict[str, Any]
    ) -> SimulationResult:
        """Simulate BGP policy change"""
        policy_type = scenario.parameters.get("policy_type", "local_pref")
        peer = scenario.parameters.get("peer")
        new_value = scenario.parameters.get("new_value")
        old_value = scenario.parameters.get("old_value")

        affected_nodes = [peer] if peer else []
        warnings = []
        recommendations = []
        traffic_redistribution = {}

        if policy_type == "local_pref":
            if new_value > old_value:
                impact_level = ImpactLevel.MODERATE
                recommendations.append(f"Traffic will prefer paths via {peer}")
            else:
                impact_level = ImpactLevel.MODERATE
                recommendations.append(f"Traffic will avoid paths via {peer}")
        elif policy_type == "as_path_prepend":
            impact_level = ImpactLevel.MINIMAL
            recommendations.append("Outbound traffic patterns may change for remote ASes")
        else:
            impact_level = ImpactLevel.MINIMAL

        # BGP takes longer to converge
        convergence_time = 3000  # ~3 seconds for BGP updates

        return SimulationResult(
            result_id=self._generate_result_id(),
            scenario=scenario,
            impact_level=impact_level,
            affected_nodes=affected_nodes,
            traffic_redistribution=traffic_redistribution,
            convergence_time_ms=convergence_time,
            warnings=warnings,
            recommendations=recommendations
        )

    def _simulate_new_link(
        self,
        scenario: Scenario,
        topology: Dict[str, Any]
    ) -> SimulationResult:
        """Simulate adding a new link"""
        source = scenario.parameters.get("source")
        target = scenario.parameters.get("target")
        bandwidth = scenario.parameters.get("bandwidth", 1000000000)

        affected_nodes = [source, target]
        recommendations = []

        # New link is generally positive
        impact_level = ImpactLevel.MINIMAL
        recommendations.append("New redundancy path available")
        recommendations.append("Consider enabling ECMP for load balancing")

        # Quick convergence for new link
        convergence_time = 1000

        return SimulationResult(
            result_id=self._generate_result_id(),
            scenario=scenario,
            impact_level=impact_level,
            affected_nodes=affected_nodes,
            convergence_time_ms=convergence_time,
            recommendations=recommendations
        )

    def _simulate_link_removal(
        self,
        scenario: Scenario,
        topology: Dict[str, Any]
    ) -> SimulationResult:
        """Simulate removing a link (planned)"""
        # Similar to link failure but with planned convergence
        result = self._simulate_link_failure(scenario, topology)
        result.recommendations.insert(0, "Perform graceful shutdown to minimize impact")
        result.convergence_time_ms = int(result.convergence_time_ms * 0.5)  # Planned is faster
        return result

    def _simulate_traffic_spike(
        self,
        scenario: Scenario,
        topology: Dict[str, Any]
    ) -> SimulationResult:
        """Simulate traffic spike"""
        link_id = scenario.parameters.get("link_id")
        increase_percent = scenario.parameters.get("increase_percent", 50)
        current_utilization = scenario.parameters.get("current_utilization", 50)

        warnings = []
        recommendations = []

        new_utilization = current_utilization + increase_percent
        if new_utilization > 95:
            impact_level = ImpactLevel.SEVERE
            warnings.append(f"Link will be at {new_utilization}% utilization - potential packet loss")
            recommendations.append("Enable QoS to protect critical traffic")
            recommendations.append("Consider traffic engineering to shift some flows")
        elif new_utilization > 80:
            impact_level = ImpactLevel.MODERATE
            warnings.append(f"Link will be at {new_utilization}% utilization")
            recommendations.append("Monitor for packet loss during spike")
        else:
            impact_level = ImpactLevel.MINIMAL

        return SimulationResult(
            result_id=self._generate_result_id(),
            scenario=scenario,
            impact_level=impact_level,
            affected_links=[link_id],
            traffic_redistribution={
                link_id: {"new_utilization": new_utilization, "increase": increase_percent}
            },
            warnings=warnings,
            recommendations=recommendations
        )

    def _simulate_maintenance(
        self,
        scenario: Scenario,
        topology: Dict[str, Any]
    ) -> SimulationResult:
        """Simulate maintenance window"""
        nodes = scenario.parameters.get("nodes", [])
        links = scenario.parameters.get("links", [])
        duration_minutes = scenario.parameters.get("duration_minutes", 60)

        warnings = []
        recommendations = []

        # Simulate impact of taking nodes/links offline
        if nodes:
            recommendations.append(f"Gracefully drain traffic from {', '.join(nodes)} before maintenance")
        if links:
            recommendations.append(f"Verify alternate paths exist before taking down {len(links)} links")

        impact_level = ImpactLevel.MODERATE
        recommendations.append("Schedule maintenance during low-traffic period")
        recommendations.append(f"Estimated maintenance window: {duration_minutes} minutes")

        return SimulationResult(
            result_id=self._generate_result_id(),
            scenario=scenario,
            impact_level=impact_level,
            affected_nodes=nodes,
            affected_links=links,
            warnings=warnings,
            recommendations=recommendations
        )

    def _simulate_generic(
        self,
        scenario: Scenario,
        topology: Dict[str, Any]
    ) -> SimulationResult:
        """Generic simulation for unsupported types"""
        return SimulationResult(
            result_id=self._generate_result_id(),
            scenario=scenario,
            impact_level=ImpactLevel.MINIMAL,
            warnings=["Generic simulation - detailed analysis not available"],
            recommendations=["Review scenario parameters for specific analysis"]
        )

    def _find_alternate_paths(
        self,
        topology: Dict[str, Any],
        source: str,
        target: str,
        exclude_links: Optional[List[Dict]] = None,
        exclude_nodes: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Find alternate paths between two nodes"""
        exclude_links = exclude_links or []
        exclude_nodes = exclude_nodes or []

        # Build adjacency list excluding specified links/nodes
        adj: Dict[str, List[Tuple[str, str]]] = {}
        for link in topology.get("links", []):
            if link in exclude_links:
                continue
            src = link.get("source")
            dst = link.get("target")
            if src in exclude_nodes or dst in exclude_nodes:
                continue

            link_id = link.get("id", f"{src}-{dst}")
            if src not in adj:
                adj[src] = []
            if dst not in adj:
                adj[dst] = []
            adj[src].append((dst, link_id))
            adj[dst].append((src, link_id))

        # BFS to find paths
        if source not in adj or target not in adj:
            return []

        paths = []
        visited = {source}
        queue = [(source, [source], [])]

        while queue and len(paths) < 3:  # Find up to 3 alternate paths
            current, path, links = queue.pop(0)
            if current == target:
                paths.append({
                    "path": path,
                    "links": links,
                    "hop_count": len(path) - 1
                })
                continue

            for neighbor, link_id in adj.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor], links + [link_id]))

        return paths

    def _determine_node_role(self, topology: Dict[str, Any], node_id: str) -> str:
        """Determine the role of a node based on connectivity"""
        connection_count = 0
        for link in topology.get("links", []):
            if link.get("source") == node_id or link.get("target") == node_id:
                connection_count += 1

        # Look for naming hints
        node_lower = node_id.lower()
        if "spine" in node_lower:
            return "spine"
        elif "core" in node_lower:
            return "core"
        elif "leaf" in node_lower:
            return "leaf"
        elif "edge" in node_lower:
            return "edge"
        elif connection_count >= 4:
            return "core"
        else:
            return "access"

    def _estimate_convergence_time(
        self,
        scenario_type: ScenarioType,
        affected_count: int,
        has_alternate: bool
    ) -> int:
        """Estimate convergence time in milliseconds"""
        # Base times by scenario type
        base_times = {
            ScenarioType.LINK_FAILURE: 1000,
            ScenarioType.NODE_FAILURE: 2000,
            ScenarioType.MULTI_LINK_FAILURE: 3000,
            ScenarioType.MULTI_NODE_FAILURE: 5000,
            ScenarioType.OSPF_COST_CHANGE: 500,
            ScenarioType.BGP_POLICY_CHANGE: 3000,
            ScenarioType.NEW_LINK: 1000,
            ScenarioType.LINK_REMOVAL: 1500,
            ScenarioType.TRAFFIC_SPIKE: 0,
            ScenarioType.MAINTENANCE_WINDOW: 2000,
        }

        base = base_times.get(scenario_type, 1000)

        # Scale by affected count
        base += affected_count * 100

        # Longer if no alternate path
        if not has_alternate:
            base *= 2

        return base

    def get_scenarios(self, limit: int = 50) -> List[Scenario]:
        """Get scenario history"""
        return self._scenarios[-limit:]

    def get_results(self, limit: int = 50) -> List[SimulationResult]:
        """Get simulation results"""
        return self._results[-limit:]

    def get_scenario(self, scenario_id: str) -> Optional[Scenario]:
        """Get a specific scenario by ID"""
        for s in self._scenarios:
            if s.scenario_id == scenario_id:
                return s
        return None

    def get_result(self, result_id: str) -> Optional[SimulationResult]:
        """Get a specific result by ID"""
        for r in self._results:
            if r.result_id == result_id:
                return r
        return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get simulator statistics"""
        impact_counts = {}
        for r in self._results:
            level = r.impact_level.value
            impact_counts[level] = impact_counts.get(level, 0) + 1

        return {
            "total_scenarios": len(self._scenarios),
            "total_simulations": len(self._results),
            "topology_nodes": len(self._topology.get("nodes", [])),
            "topology_links": len(self._topology.get("links", [])),
            "impact_distribution": impact_counts
        }


# Global simulator instance
_global_simulator: Optional[WhatIfSimulator] = None


def get_whatif_simulator() -> WhatIfSimulator:
    """Get or create the global what-if simulator"""
    global _global_simulator
    if _global_simulator is None:
        _global_simulator = WhatIfSimulator()
    return _global_simulator
