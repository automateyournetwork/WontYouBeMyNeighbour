"""
Impact Analyzer - Analyzes impact of network changes

Provides:
- Path impact analysis
- Recovery time estimation
- Service impact assessment
- Rollback analysis
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Set
from copy import deepcopy

logger = logging.getLogger("ImpactAnalyzer")


class RecoveryStrategy(Enum):
    """Recovery strategy types"""
    FAST_REROUTE = "fast_reroute"
    IGP_CONVERGENCE = "igp_convergence"
    BGP_CONVERGENCE = "bgp_convergence"
    GRACEFUL_RESTART = "graceful_restart"
    MANUAL_INTERVENTION = "manual_intervention"


@dataclass
class AffectedPath:
    """
    Path affected by a network change

    Attributes:
        path_id: Unique identifier
        source: Source node
        destination: Destination node
        current_path: Current path before change
        alternate_path: Path after change (if available)
        service_impact: Services using this path
        traffic_volume: Estimated traffic volume
        priority: Path priority/importance
    """
    path_id: str
    source: str
    destination: str
    current_path: List[str]
    alternate_path: Optional[List[str]] = None
    service_impact: List[str] = field(default_factory=list)
    traffic_volume: float = 0.0
    priority: str = "normal"

    @property
    def has_alternate(self) -> bool:
        """Check if alternate path exists"""
        return self.alternate_path is not None and len(self.alternate_path) > 0

    @property
    def path_length_change(self) -> int:
        """Calculate change in path length"""
        if not self.alternate_path:
            return 0
        return len(self.alternate_path) - len(self.current_path)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path_id": self.path_id,
            "source": self.source,
            "destination": self.destination,
            "current_path": self.current_path,
            "alternate_path": self.alternate_path,
            "has_alternate": self.has_alternate,
            "path_length_change": self.path_length_change,
            "service_impact": self.service_impact,
            "traffic_volume": self.traffic_volume,
            "priority": self.priority
        }


@dataclass
class RecoveryEstimate:
    """
    Recovery time estimate

    Attributes:
        estimate_id: Unique identifier
        strategy: Recovery strategy
        estimated_time_ms: Estimated recovery time
        confidence: Confidence level (0-1)
        factors: Factors affecting the estimate
        best_case_ms: Best case recovery time
        worst_case_ms: Worst case recovery time
    """
    estimate_id: str
    strategy: RecoveryStrategy
    estimated_time_ms: int
    confidence: float = 0.8
    factors: List[str] = field(default_factory=list)
    best_case_ms: int = 0
    worst_case_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "estimate_id": self.estimate_id,
            "strategy": self.strategy.value,
            "estimated_time_ms": self.estimated_time_ms,
            "confidence": self.confidence,
            "factors": self.factors,
            "best_case_ms": self.best_case_ms,
            "worst_case_ms": self.worst_case_ms
        }


@dataclass
class ImpactReport:
    """
    Comprehensive impact analysis report

    Attributes:
        report_id: Unique identifier
        change_description: Description of the change
        affected_paths: Paths affected by the change
        recovery_estimate: Recovery time estimate
        service_impact: Services affected
        traffic_impact: Traffic statistics
        risk_score: Overall risk score (0-100)
        mitigation_options: Available mitigations
        rollback_available: Whether rollback is possible
        rollback_steps: Steps to rollback
        generated_at: When report was generated
    """
    report_id: str
    change_description: str
    affected_paths: List[AffectedPath] = field(default_factory=list)
    recovery_estimate: Optional[RecoveryEstimate] = None
    service_impact: Dict[str, str] = field(default_factory=dict)
    traffic_impact: Dict[str, Any] = field(default_factory=dict)
    risk_score: int = 0
    mitigation_options: List[str] = field(default_factory=list)
    rollback_available: bool = True
    rollback_steps: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "change_description": self.change_description,
            "affected_paths": [p.to_dict() for p in self.affected_paths],
            "recovery_estimate": self.recovery_estimate.to_dict() if self.recovery_estimate else None,
            "service_impact": self.service_impact,
            "traffic_impact": self.traffic_impact,
            "risk_score": self.risk_score,
            "mitigation_options": self.mitigation_options,
            "rollback_available": self.rollback_available,
            "rollback_steps": self.rollback_steps,
            "generated_at": self.generated_at.isoformat()
        }


class ImpactAnalyzer:
    """
    Analyzes the impact of network changes
    """

    def __init__(self):
        """Initialize the impact analyzer"""
        self._reports: List[ImpactReport] = []
        self._report_counter = 0
        self._path_counter = 0
        self._estimate_counter = 0

        # Service definitions (service name -> required paths)
        self._services: Dict[str, Dict[str, Any]] = {}

        # Traffic flow definitions
        self._traffic_flows: Dict[str, Dict[str, Any]] = {}

    def _generate_report_id(self) -> str:
        """Generate unique report ID"""
        self._report_counter += 1
        return f"report-{self._report_counter:06d}"

    def _generate_path_id(self) -> str:
        """Generate unique path ID"""
        self._path_counter += 1
        return f"path-{self._path_counter:06d}"

    def _generate_estimate_id(self) -> str:
        """Generate unique estimate ID"""
        self._estimate_counter += 1
        return f"estimate-{self._estimate_counter:06d}"

    def register_service(
        self,
        name: str,
        source: str,
        destination: str,
        priority: str = "normal",
        requirements: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Register a service for impact tracking

        Args:
            name: Service name
            source: Source node
            destination: Destination node
            priority: Service priority (critical, high, normal, low)
            requirements: Service requirements (latency, bandwidth, etc.)
        """
        self._services[name] = {
            "source": source,
            "destination": destination,
            "priority": priority,
            "requirements": requirements or {}
        }
        logger.info(f"Registered service: {name}")

    def register_traffic_flow(
        self,
        flow_id: str,
        source: str,
        destination: str,
        volume_mbps: float,
        protocol: str = "tcp"
    ) -> None:
        """
        Register a traffic flow for impact analysis

        Args:
            flow_id: Flow identifier
            source: Source node
            destination: Destination node
            volume_mbps: Traffic volume in Mbps
            protocol: Protocol (tcp, udp, etc.)
        """
        self._traffic_flows[flow_id] = {
            "source": source,
            "destination": destination,
            "volume_mbps": volume_mbps,
            "protocol": protocol
        }

    def analyze_link_impact(
        self,
        topology: Dict[str, Any],
        link_source: str,
        link_target: str
    ) -> ImpactReport:
        """
        Analyze impact of a link change

        Args:
            topology: Network topology
            link_source: Link source node
            link_target: Link target node

        Returns:
            ImpactReport with full analysis
        """
        report = ImpactReport(
            report_id=self._generate_report_id(),
            change_description=f"Link change between {link_source} and {link_target}"
        )

        # Find affected paths
        affected_paths = self._find_affected_paths(
            topology,
            [(link_source, link_target)]
        )
        report.affected_paths = affected_paths

        # Analyze service impact
        for service_name, service in self._services.items():
            for path in affected_paths:
                if (path.source == service["source"] and
                    path.destination == service["destination"]):
                    if not path.has_alternate:
                        report.service_impact[service_name] = "complete_outage"
                    else:
                        report.service_impact[service_name] = "degraded"

        # Estimate recovery time
        report.recovery_estimate = self._estimate_recovery(
            len(affected_paths),
            any(not p.has_alternate for p in affected_paths)
        )

        # Calculate traffic impact
        report.traffic_impact = self._calculate_traffic_impact(affected_paths)

        # Calculate risk score
        report.risk_score = self._calculate_risk_score(report)

        # Generate mitigation options
        report.mitigation_options = self._generate_mitigations(report)

        # Rollback steps
        report.rollback_steps = [
            "Restore link configuration",
            "Verify adjacency re-establishment",
            "Confirm route convergence",
            "Validate service recovery"
        ]

        self._reports.append(report)
        return report

    def analyze_node_impact(
        self,
        topology: Dict[str, Any],
        node_id: str
    ) -> ImpactReport:
        """
        Analyze impact of a node change

        Args:
            topology: Network topology
            node_id: Node identifier

        Returns:
            ImpactReport with full analysis
        """
        report = ImpactReport(
            report_id=self._generate_report_id(),
            change_description=f"Node change for {node_id}"
        )

        # Find all links connected to this node
        affected_links = []
        for link in topology.get("links", []):
            if link.get("source") == node_id or link.get("target") == node_id:
                src = link.get("source")
                dst = link.get("target")
                affected_links.append((src, dst))

        # Find affected paths
        affected_paths = self._find_affected_paths(
            topology,
            affected_links,
            excluded_nodes=[node_id]
        )
        report.affected_paths = affected_paths

        # Service impact
        for service_name, service in self._services.items():
            if service["source"] == node_id or service["destination"] == node_id:
                report.service_impact[service_name] = "complete_outage"
            else:
                for path in affected_paths:
                    if (path.source == service["source"] and
                        path.destination == service["destination"]):
                        if not path.has_alternate:
                            report.service_impact[service_name] = "complete_outage"
                        else:
                            report.service_impact[service_name] = "degraded"

        # Recovery estimate (node recovery takes longer)
        report.recovery_estimate = self._estimate_recovery(
            len(affected_paths) * 2,  # More impact for node
            any(not p.has_alternate for p in affected_paths),
            is_node_failure=True
        )

        # Traffic impact
        report.traffic_impact = self._calculate_traffic_impact(affected_paths)

        # Risk score
        report.risk_score = self._calculate_risk_score(report)

        # Mitigations
        report.mitigation_options = self._generate_mitigations(report)

        # Rollback steps for node
        report.rollback_steps = [
            "Restore node to operational state",
            "Re-establish all protocol adjacencies",
            "Verify route convergence on all protocols",
            "Confirm service recovery",
            "Validate traffic flow restoration"
        ]

        self._reports.append(report)
        return report

    def analyze_config_change_impact(
        self,
        topology: Dict[str, Any],
        change_type: str,
        parameters: Dict[str, Any]
    ) -> ImpactReport:
        """
        Analyze impact of a configuration change

        Args:
            topology: Network topology
            change_type: Type of configuration change
            parameters: Change parameters

        Returns:
            ImpactReport with full analysis
        """
        report = ImpactReport(
            report_id=self._generate_report_id(),
            change_description=f"Configuration change: {change_type}"
        )

        # Configuration changes typically have lower impact
        report.risk_score = 30  # Base score

        if change_type == "ospf_cost":
            link_id = parameters.get("link_id")
            old_cost = parameters.get("old_cost", 10)
            new_cost = parameters.get("new_cost", 10)

            if new_cost > old_cost * 2:
                report.risk_score = 50
                report.mitigation_options.append(
                    "Consider gradual cost increase to minimize traffic shift"
                )

        elif change_type == "bgp_local_pref":
            report.risk_score = 40
            report.mitigation_options.append(
                "Test in lab environment before production"
            )
            report.mitigation_options.append(
                "Apply during maintenance window"
            )

        elif change_type == "route_policy":
            report.risk_score = 60
            report.mitigation_options.append(
                "Validate policy syntax before applying"
            )
            report.mitigation_options.append(
                "Use soft-reconfiguration for testing"
            )

        # Recovery estimate for config changes
        report.recovery_estimate = RecoveryEstimate(
            estimate_id=self._generate_estimate_id(),
            strategy=RecoveryStrategy.IGP_CONVERGENCE,
            estimated_time_ms=1000,
            confidence=0.9,
            factors=["Configuration change - quick convergence expected"],
            best_case_ms=500,
            worst_case_ms=2000
        )

        # Rollback for config change
        report.rollback_steps = [
            f"Revert {change_type} configuration to previous value",
            "Verify protocol reconvergence",
            "Confirm service restoration"
        ]

        self._reports.append(report)
        return report

    def _find_affected_paths(
        self,
        topology: Dict[str, Any],
        affected_links: List[tuple],
        excluded_nodes: Optional[List[str]] = None
    ) -> List[AffectedPath]:
        """Find paths affected by link/node changes"""
        affected_paths = []
        excluded_nodes = excluded_nodes or []

        # Build graph
        adj: Dict[str, Set[str]] = {}
        for link in topology.get("links", []):
            src = link.get("source")
            dst = link.get("target")
            if src not in adj:
                adj[src] = set()
            if dst not in adj:
                adj[dst] = set()
            adj[src].add(dst)
            adj[dst].add(src)

        # Check each service
        for service_name, service in self._services.items():
            source = service["source"]
            destination = service["destination"]

            # Find current path
            current_path = self._find_path(adj, source, destination, [])
            if not current_path:
                continue

            # Check if path uses affected links
            uses_affected = False
            for i in range(len(current_path) - 1):
                link = (current_path[i], current_path[i+1])
                reverse_link = (current_path[i+1], current_path[i])
                if link in affected_links or reverse_link in affected_links:
                    uses_affected = True
                    break

            # Also check for excluded nodes in path
            for node in current_path:
                if node in excluded_nodes:
                    uses_affected = True
                    break

            if uses_affected:
                # Find alternate path excluding affected links/nodes
                modified_adj = deepcopy(adj)

                # Remove affected links
                for src, dst in affected_links:
                    if src in modified_adj and dst in modified_adj[src]:
                        modified_adj[src].discard(dst)
                    if dst in modified_adj and src in modified_adj[dst]:
                        modified_adj[dst].discard(src)

                # Remove excluded nodes
                for node in excluded_nodes:
                    if node in modified_adj:
                        for neighbor in modified_adj[node]:
                            modified_adj[neighbor].discard(node)
                        del modified_adj[node]

                alternate_path = self._find_path(modified_adj, source, destination, [])

                affected_paths.append(AffectedPath(
                    path_id=self._generate_path_id(),
                    source=source,
                    destination=destination,
                    current_path=current_path,
                    alternate_path=alternate_path,
                    service_impact=[service_name],
                    traffic_volume=self._get_flow_volume(source, destination),
                    priority=service["priority"]
                ))

        return affected_paths

    def _find_path(
        self,
        adj: Dict[str, Set[str]],
        source: str,
        destination: str,
        excluded: List[str]
    ) -> Optional[List[str]]:
        """Find a path between two nodes using BFS"""
        if source not in adj or destination not in adj:
            return None

        visited = set(excluded)
        visited.add(source)
        queue = [(source, [source])]

        while queue:
            current, path = queue.pop(0)
            if current == destination:
                return path

            for neighbor in adj.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return None

    def _get_flow_volume(self, source: str, destination: str) -> float:
        """Get traffic volume between two nodes"""
        for flow in self._traffic_flows.values():
            if flow["source"] == source and flow["destination"] == destination:
                return flow["volume_mbps"]
        return 0.0

    def _estimate_recovery(
        self,
        affected_count: int,
        has_unreachable: bool,
        is_node_failure: bool = False
    ) -> RecoveryEstimate:
        """Estimate recovery time"""
        # Base recovery time
        if is_node_failure:
            base_ms = 5000  # Node failures take longer
            strategy = RecoveryStrategy.IGP_CONVERGENCE
        else:
            base_ms = 2000
            strategy = RecoveryStrategy.FAST_REROUTE

        # Scale by affected count
        estimated_ms = base_ms + (affected_count * 200)

        # If unreachable, need manual intervention
        if has_unreachable:
            estimated_ms *= 2
            strategy = RecoveryStrategy.MANUAL_INTERVENTION

        factors = []
        if is_node_failure:
            factors.append("Node failure requires full reconvergence")
        if has_unreachable:
            factors.append("Some destinations become unreachable")
        if affected_count > 5:
            factors.append(f"Large number of affected paths ({affected_count})")

        return RecoveryEstimate(
            estimate_id=self._generate_estimate_id(),
            strategy=strategy,
            estimated_time_ms=estimated_ms,
            confidence=0.7 if has_unreachable else 0.85,
            factors=factors,
            best_case_ms=int(estimated_ms * 0.5),
            worst_case_ms=int(estimated_ms * 2)
        )

    def _calculate_traffic_impact(
        self,
        affected_paths: List[AffectedPath]
    ) -> Dict[str, Any]:
        """Calculate traffic statistics for affected paths"""
        total_volume = sum(p.traffic_volume for p in affected_paths)
        rerouted_volume = sum(p.traffic_volume for p in affected_paths if p.has_alternate)
        lost_volume = sum(p.traffic_volume for p in affected_paths if not p.has_alternate)

        return {
            "total_affected_mbps": total_volume,
            "rerouted_mbps": rerouted_volume,
            "lost_mbps": lost_volume,
            "affected_path_count": len(affected_paths),
            "paths_with_alternate": sum(1 for p in affected_paths if p.has_alternate),
            "paths_without_alternate": sum(1 for p in affected_paths if not p.has_alternate)
        }

    def _calculate_risk_score(self, report: ImpactReport) -> int:
        """Calculate overall risk score (0-100)"""
        score = 0

        # Impact based on affected paths
        path_count = len(report.affected_paths)
        score += min(30, path_count * 5)

        # Impact based on services
        for service, impact in report.service_impact.items():
            service_info = self._services.get(service, {})
            priority = service_info.get("priority", "normal")

            if impact == "complete_outage":
                if priority == "critical":
                    score += 30
                elif priority == "high":
                    score += 20
                else:
                    score += 10
            elif impact == "degraded":
                if priority == "critical":
                    score += 15
                elif priority == "high":
                    score += 10
                else:
                    score += 5

        # Impact based on recovery time
        if report.recovery_estimate:
            if report.recovery_estimate.estimated_time_ms > 10000:
                score += 20
            elif report.recovery_estimate.estimated_time_ms > 5000:
                score += 10

        # Cap at 100
        return min(100, score)

    def _generate_mitigations(self, report: ImpactReport) -> List[str]:
        """Generate mitigation options"""
        mitigations = []

        # General mitigations
        mitigations.append("Perform change during low-traffic period")

        if report.risk_score > 70:
            mitigations.append("Consider phased rollout")
            mitigations.append("Have rollback plan ready")
            mitigations.append("Notify NOC before change")

        if any(not p.has_alternate for p in report.affected_paths):
            mitigations.append("Add redundant paths before making change")
            mitigations.append("Consider traffic drain to minimize impact")

        if "complete_outage" in report.service_impact.values():
            mitigations.append("Notify affected service owners")
            mitigations.append("Schedule maintenance window")

        return mitigations

    def get_reports(self, limit: int = 50) -> List[ImpactReport]:
        """Get impact report history"""
        return self._reports[-limit:]

    def get_report(self, report_id: str) -> Optional[ImpactReport]:
        """Get specific report by ID"""
        for r in self._reports:
            if r.report_id == report_id:
                return r
        return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get analyzer statistics"""
        return {
            "total_reports": len(self._reports),
            "registered_services": len(self._services),
            "registered_flows": len(self._traffic_flows),
            "avg_risk_score": sum(r.risk_score for r in self._reports) / len(self._reports) if self._reports else 0
        }


# Global analyzer instance
_global_analyzer: Optional[ImpactAnalyzer] = None


def get_impact_analyzer() -> ImpactAnalyzer:
    """Get or create the global impact analyzer"""
    global _global_analyzer
    if _global_analyzer is None:
        _global_analyzer = ImpactAnalyzer()
    return _global_analyzer
