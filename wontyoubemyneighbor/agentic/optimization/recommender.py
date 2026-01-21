"""
Optimization Recommender - Generates network optimization recommendations

Provides recommendations for:
- OSPF cost adjustments
- BGP policy changes
- VXLAN VNI allocation
- Load balancing strategies
- Traffic engineering
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger("OptimizationRecommender")


class RecommendationType(Enum):
    """Types of optimization recommendations"""
    # Routing Optimizations
    OSPF_COST_ADJUSTMENT = "ospf_cost_adjustment"
    BGP_POLICY_CHANGE = "bgp_policy_change"
    STATIC_ROUTE_ADD = "static_route_add"
    ROUTE_REDISTRIBUTION = "route_redistribution"

    # Load Balancing
    ECMP_ENABLE = "ecmp_enable"
    LOAD_BALANCE_ADJUST = "load_balance_adjust"

    # Traffic Engineering
    PATH_OPTIMIZATION = "path_optimization"
    QOS_ADJUSTMENT = "qos_adjustment"
    TRAFFIC_SHAPING = "traffic_shaping"

    # Capacity
    BANDWIDTH_UPGRADE = "bandwidth_upgrade"
    LINK_AGGREGATION = "link_aggregation"

    # VXLAN/EVPN
    VNI_REALLOCATION = "vni_reallocation"
    VTEP_OPTIMIZATION = "vtep_optimization"

    # Failover
    BACKUP_PATH_SETUP = "backup_path_setup"
    FAILOVER_TUNING = "failover_tuning"

    # General
    MONITORING_ENHANCEMENT = "monitoring_enhancement"
    CONFIGURATION_CLEANUP = "configuration_cleanup"


class RecommendationPriority(Enum):
    """Priority levels for recommendations"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class Recommendation:
    """
    Network optimization recommendation

    Attributes:
        recommendation_id: Unique identifier
        rec_type: Type of recommendation
        priority: Priority level
        title: Short title
        description: Detailed description
        affected_components: Agents/links affected
        current_state: Current configuration state
        proposed_change: Proposed configuration change
        expected_impact: Expected improvement
        risk_level: Implementation risk
        implementation_steps: Steps to implement
        rollback_steps: Steps to rollback
        estimated_improvement: Expected % improvement
    """
    recommendation_id: str
    rec_type: RecommendationType
    priority: RecommendationPriority
    title: str
    description: str
    affected_components: List[str] = field(default_factory=list)
    current_state: Dict[str, Any] = field(default_factory=dict)
    proposed_change: Dict[str, Any] = field(default_factory=dict)
    expected_impact: str = ""
    risk_level: str = "low"
    implementation_steps: List[str] = field(default_factory=list)
    rollback_steps: List[str] = field(default_factory=list)
    estimated_improvement: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    applied: bool = False
    applied_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "type": self.rec_type.value,
            "priority": self.priority.value,
            "title": self.title,
            "description": self.description,
            "affected_components": self.affected_components,
            "current_state": self.current_state,
            "proposed_change": self.proposed_change,
            "expected_impact": self.expected_impact,
            "risk_level": self.risk_level,
            "implementation_steps": self.implementation_steps,
            "rollback_steps": self.rollback_steps,
            "estimated_improvement": self.estimated_improvement,
            "created_at": self.created_at.isoformat(),
            "applied": self.applied,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None
        }


class OptimizationRecommender:
    """
    Generates network optimization recommendations based on analysis
    """

    def __init__(self):
        """Initialize the optimization recommender"""
        self._recommendations: List[Recommendation] = []
        self._recommendation_counter = 0

        # Optimization thresholds
        self._high_utilization_threshold = 80.0
        self._imbalance_threshold = 30.0
        self._latency_threshold = 50.0
        self._suboptimal_cost_threshold = 20  # % deviation from optimal

    def _generate_recommendation_id(self) -> str:
        """Generate unique recommendation ID"""
        self._recommendation_counter += 1
        return f"rec-{self._recommendation_counter:06d}"

    def analyze_ospf_costs(
        self,
        topology: Dict[str, Any],
        traffic_data: Dict[str, Any]
    ) -> List[Recommendation]:
        """
        Analyze OSPF costs and recommend adjustments

        Args:
            topology: Network topology with link costs
            traffic_data: Traffic utilization data

        Returns:
            List of OSPF cost recommendations
        """
        recommendations = []

        links = topology.get("links", [])
        for link in links:
            link_id = link.get("id", f"{link.get('source')}-{link.get('target')}")
            current_cost = link.get("ospf_cost", 10)
            bandwidth = link.get("bandwidth", 1000000000)
            utilization = traffic_data.get(link_id, {}).get("utilization", 0)

            # Calculate optimal cost based on bandwidth
            # Reference cost = 10^8 / bandwidth (Cisco default)
            optimal_cost = max(1, int(100000000 / bandwidth))

            # Check if cost needs adjustment
            if current_cost != optimal_cost:
                deviation = abs(current_cost - optimal_cost) / optimal_cost * 100
                if deviation > self._suboptimal_cost_threshold:
                    rec = Recommendation(
                        recommendation_id=self._generate_recommendation_id(),
                        rec_type=RecommendationType.OSPF_COST_ADJUSTMENT,
                        priority=RecommendationPriority.MEDIUM,
                        title=f"Adjust OSPF cost on {link_id}",
                        description=f"OSPF cost of {current_cost} does not reflect actual bandwidth. "
                                   f"Recommended cost based on bandwidth: {optimal_cost}",
                        affected_components=[link.get("source"), link.get("target")],
                        current_state={"ospf_cost": current_cost, "bandwidth": bandwidth},
                        proposed_change={"ospf_cost": optimal_cost},
                        expected_impact="Better path selection reflecting actual link capacities",
                        risk_level="low",
                        implementation_steps=[
                            f"Enter OSPF configuration mode on {link.get('source')}",
                            f"Set interface cost to {optimal_cost}",
                            f"Repeat on {link.get('target')}",
                            "Verify OSPF reconvergence"
                        ],
                        rollback_steps=[
                            f"Restore interface cost to {current_cost} on both ends"
                        ],
                        estimated_improvement=10.0
                    )
                    recommendations.append(rec)
                    self._recommendations.append(rec)

            # Check for overutilized links that could benefit from cost increase
            if utilization > self._high_utilization_threshold:
                rec = Recommendation(
                    recommendation_id=self._generate_recommendation_id(),
                    rec_type=RecommendationType.OSPF_COST_ADJUSTMENT,
                    priority=RecommendationPriority.HIGH,
                    title=f"Increase OSPF cost to reduce load on {link_id}",
                    description=f"Link {link_id} is at {utilization:.1f}% utilization. "
                               f"Increasing OSPF cost can redirect traffic to alternate paths.",
                    affected_components=[link.get("source"), link.get("target")],
                    current_state={"ospf_cost": current_cost, "utilization": utilization},
                    proposed_change={"ospf_cost": current_cost * 2},
                    expected_impact="Reduced load on congested link through traffic redistribution",
                    risk_level="medium",
                    implementation_steps=[
                        "Verify alternate paths exist",
                        f"Increase OSPF cost to {current_cost * 2}",
                        "Monitor traffic redistribution",
                        "Verify no connectivity loss"
                    ],
                    rollback_steps=[
                        f"Restore OSPF cost to {current_cost}"
                    ],
                    estimated_improvement=min(30.0, utilization - 70)
                )
                recommendations.append(rec)
                self._recommendations.append(rec)

        return recommendations

    def analyze_bgp_policies(
        self,
        bgp_config: Dict[str, Any],
        traffic_data: Dict[str, Any]
    ) -> List[Recommendation]:
        """
        Analyze BGP policies and recommend optimizations

        Args:
            bgp_config: BGP configuration with policies
            traffic_data: Traffic flow data

        Returns:
            List of BGP policy recommendations
        """
        recommendations = []

        peers = bgp_config.get("peers", [])
        for peer in peers:
            peer_ip = peer.get("ip")
            peer_as = peer.get("remote_as")
            local_pref = peer.get("local_preference", 100)
            weight = peer.get("weight", 0)

            # Check for multiple paths to same destination with unbalanced load
            prefixes = peer.get("received_prefixes", [])
            for prefix in prefixes:
                utilization = traffic_data.get(prefix, {}).get("utilization", 0)

                if utilization > self._high_utilization_threshold:
                    rec = Recommendation(
                        recommendation_id=self._generate_recommendation_id(),
                        rec_type=RecommendationType.BGP_POLICY_CHANGE,
                        priority=RecommendationPriority.HIGH,
                        title=f"Adjust BGP local-pref for {prefix} via {peer_ip}",
                        description=f"Traffic to {prefix} via {peer_ip} is congested ({utilization:.1f}%). "
                                   f"Lower local-pref to prefer alternate paths.",
                        affected_components=[peer_ip],
                        current_state={
                            "local_preference": local_pref,
                            "peer": peer_ip,
                            "utilization": utilization
                        },
                        proposed_change={"local_preference": local_pref - 10},
                        expected_impact="Traffic distributed to less congested paths",
                        risk_level="medium",
                        implementation_steps=[
                            f"Create route-map to match prefix {prefix}",
                            f"Set local-preference to {local_pref - 10}",
                            "Apply to peer",
                            "Verify route selection changes"
                        ],
                        rollback_steps=[
                            f"Remove route-map or restore local-pref to {local_pref}"
                        ],
                        estimated_improvement=20.0
                    )
                    recommendations.append(rec)
                    self._recommendations.append(rec)

        # Check for missing route-reflector client config in large iBGP mesh
        ibgp_peers = [p for p in peers if p.get("peer_type") == "ibgp"]
        if len(ibgp_peers) > 4:
            rec = Recommendation(
                recommendation_id=self._generate_recommendation_id(),
                rec_type=RecommendationType.BGP_POLICY_CHANGE,
                priority=RecommendationPriority.MEDIUM,
                title="Consider BGP Route Reflector deployment",
                description=f"Large iBGP mesh with {len(ibgp_peers)} peers detected. "
                           f"Route reflector can reduce BGP session overhead.",
                affected_components=[p.get("ip") for p in ibgp_peers],
                current_state={"ibgp_peers": len(ibgp_peers)},
                proposed_change={"route_reflector": True, "clients": ibgp_peers[:3]},
                expected_impact="Reduced iBGP session count and update traffic",
                risk_level="high",
                implementation_steps=[
                    "Identify route reflector candidates (spine/core)",
                    "Configure RR and RR clients",
                    "Remove full mesh iBGP sessions",
                    "Verify route propagation"
                ],
                rollback_steps=[
                    "Restore full mesh iBGP if issues occur"
                ],
                estimated_improvement=15.0
            )
            recommendations.append(rec)
            self._recommendations.append(rec)

        return recommendations

    def analyze_load_balancing(
        self,
        topology: Dict[str, Any],
        traffic_data: Dict[str, Any]
    ) -> List[Recommendation]:
        """
        Analyze load balancing opportunities

        Args:
            topology: Network topology
            traffic_data: Traffic utilization data

        Returns:
            List of load balancing recommendations
        """
        recommendations = []

        # Find parallel links (same source/dest)
        link_groups: Dict[Tuple[str, str], List[Dict]] = {}
        for link in topology.get("links", []):
            key = (link.get("source"), link.get("target"))
            if key not in link_groups:
                link_groups[key] = []
            link_groups[key].append(link)

        # Check for ECMP opportunities
        for (src, dst), links in link_groups.items():
            if len(links) < 2:
                continue

            utils = []
            for link in links:
                link_id = link.get("id", f"{src}-{dst}")
                util = traffic_data.get(link_id, {}).get("utilization", 0)
                utils.append(util)

            if not utils:
                continue

            max_util = max(utils)
            min_util = min(utils)
            imbalance = max_util - min_util

            if imbalance > self._imbalance_threshold:
                rec = Recommendation(
                    recommendation_id=self._generate_recommendation_id(),
                    rec_type=RecommendationType.ECMP_ENABLE,
                    priority=RecommendationPriority.HIGH,
                    title=f"Enable ECMP load balancing between {src} and {dst}",
                    description=f"Multiple links exist but traffic is imbalanced ({imbalance:.1f}% difference). "
                               f"Enable ECMP for better distribution.",
                    affected_components=[src, dst],
                    current_state={
                        "link_count": len(links),
                        "utilizations": utils,
                        "imbalance": imbalance
                    },
                    proposed_change={"ecmp_enabled": True, "max_paths": len(links)},
                    expected_impact=f"Traffic balanced across {len(links)} paths, reducing peak utilization",
                    risk_level="low",
                    implementation_steps=[
                        "Enable ECMP in routing protocol (OSPF/BGP)",
                        "Verify equal-cost paths exist",
                        "Configure per-flow load balancing",
                        "Monitor traffic distribution"
                    ],
                    rollback_steps=[
                        "Disable ECMP and return to single-path routing"
                    ],
                    estimated_improvement=min(25.0, imbalance * 0.7)
                )
                recommendations.append(rec)
                self._recommendations.append(rec)

        return recommendations

    def analyze_vxlan_optimization(
        self,
        vxlan_config: Dict[str, Any],
        traffic_data: Dict[str, Any]
    ) -> List[Recommendation]:
        """
        Analyze VXLAN/EVPN configuration and recommend optimizations

        Args:
            vxlan_config: VXLAN configuration
            traffic_data: Traffic data

        Returns:
            List of VXLAN optimization recommendations
        """
        recommendations = []

        vnis = vxlan_config.get("vnis", [])
        vteps = vxlan_config.get("vteps", [])

        # Check for VNI consolidation opportunities
        if len(vnis) > 50:
            low_traffic_vnis = []
            for vni in vnis:
                vni_id = vni.get("vni_id")
                traffic = traffic_data.get(f"vni-{vni_id}", {}).get("bytes", 0)
                if traffic < 1000000:  # Less than 1MB
                    low_traffic_vnis.append(vni_id)

            if len(low_traffic_vnis) > 10:
                rec = Recommendation(
                    recommendation_id=self._generate_recommendation_id(),
                    rec_type=RecommendationType.VNI_REALLOCATION,
                    priority=RecommendationPriority.LOW,
                    title="Consolidate low-traffic VNIs",
                    description=f"Found {len(low_traffic_vnis)} VNIs with minimal traffic. "
                               f"Consider consolidating to reduce control plane overhead.",
                    affected_components=[f"vni-{v}" for v in low_traffic_vnis[:5]],
                    current_state={"total_vnis": len(vnis), "low_traffic_vnis": len(low_traffic_vnis)},
                    proposed_change={"consolidate_vnis": True},
                    expected_impact="Reduced EVPN control plane traffic and memory usage",
                    risk_level="medium",
                    implementation_steps=[
                        "Identify tenants using low-traffic VNIs",
                        "Plan VNI migration",
                        "Update VLAN-to-VNI mappings",
                        "Migrate workloads",
                        "Remove old VNIs"
                    ],
                    rollback_steps=[
                        "Restore original VNI configuration if issues arise"
                    ],
                    estimated_improvement=10.0
                )
                recommendations.append(rec)
                self._recommendations.append(rec)

        # Check for VTEP optimization
        if len(vteps) > 2:
            # Check for ingress replication vs multicast
            rec = Recommendation(
                recommendation_id=self._generate_recommendation_id(),
                rec_type=RecommendationType.VTEP_OPTIMIZATION,
                priority=RecommendationPriority.MEDIUM,
                title="Evaluate multicast for BUM traffic",
                description=f"With {len(vteps)} VTEPs, multicast may be more efficient "
                           f"than ingress replication for BUM traffic.",
                affected_components=[v.get("ip") for v in vteps],
                current_state={"vtep_count": len(vteps)},
                proposed_change={"bum_handling": "multicast"},
                expected_impact="Reduced BUM traffic replication overhead",
                risk_level="high",
                implementation_steps=[
                    "Verify multicast infrastructure available",
                    "Configure PIM on underlay",
                    "Configure multicast group for VXLAN",
                    "Update VTEP configuration",
                    "Verify BUM forwarding"
                ],
                rollback_steps=[
                    "Revert to ingress replication"
                ],
                estimated_improvement=15.0
            )
            recommendations.append(rec)
            self._recommendations.append(rec)

        return recommendations

    def generate_all_recommendations(
        self,
        topology: Dict[str, Any],
        traffic_data: Dict[str, Any],
        bgp_config: Optional[Dict[str, Any]] = None,
        vxlan_config: Optional[Dict[str, Any]] = None
    ) -> List[Recommendation]:
        """
        Generate all optimization recommendations

        Args:
            topology: Network topology
            traffic_data: Traffic utilization data
            bgp_config: Optional BGP configuration
            vxlan_config: Optional VXLAN configuration

        Returns:
            Combined list of all recommendations
        """
        all_recs = []

        # OSPF analysis
        ospf_recs = self.analyze_ospf_costs(topology, traffic_data)
        all_recs.extend(ospf_recs)

        # BGP analysis
        if bgp_config:
            bgp_recs = self.analyze_bgp_policies(bgp_config, traffic_data)
            all_recs.extend(bgp_recs)

        # Load balancing analysis
        lb_recs = self.analyze_load_balancing(topology, traffic_data)
        all_recs.extend(lb_recs)

        # VXLAN analysis
        if vxlan_config:
            vxlan_recs = self.analyze_vxlan_optimization(vxlan_config, traffic_data)
            all_recs.extend(vxlan_recs)

        # Sort by priority
        priority_order = {
            RecommendationPriority.CRITICAL: 0,
            RecommendationPriority.HIGH: 1,
            RecommendationPriority.MEDIUM: 2,
            RecommendationPriority.LOW: 3,
            RecommendationPriority.INFO: 4
        }
        all_recs.sort(key=lambda r: priority_order.get(r.priority, 5))

        return all_recs

    def get_recommendations(
        self,
        priority: Optional[RecommendationPriority] = None,
        rec_type: Optional[RecommendationType] = None,
        applied: Optional[bool] = None,
        limit: int = 50
    ) -> List[Recommendation]:
        """
        Get recommendations with optional filtering

        Args:
            priority: Filter by priority
            rec_type: Filter by type
            applied: Filter by applied status
            limit: Maximum number to return

        Returns:
            Filtered list of recommendations
        """
        results = self._recommendations

        if priority:
            results = [r for r in results if r.priority == priority]
        if rec_type:
            results = [r for r in results if r.rec_type == rec_type]
        if applied is not None:
            results = [r for r in results if r.applied == applied]

        return results[-limit:]

    def mark_applied(self, recommendation_id: str) -> bool:
        """Mark a recommendation as applied"""
        for rec in self._recommendations:
            if rec.recommendation_id == recommendation_id:
                rec.applied = True
                rec.applied_at = datetime.now()
                logger.info(f"Marked recommendation {recommendation_id} as applied")
                return True
        return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get recommender statistics"""
        by_priority = {}
        by_type = {}

        for rec in self._recommendations:
            p = rec.priority.value
            t = rec.rec_type.value
            by_priority[p] = by_priority.get(p, 0) + 1
            by_type[t] = by_type.get(t, 0) + 1

        return {
            "total_recommendations": len(self._recommendations),
            "pending": len([r for r in self._recommendations if not r.applied]),
            "applied": len([r for r in self._recommendations if r.applied]),
            "by_priority": by_priority,
            "by_type": by_type
        }


# Global recommender instance
_global_recommender: Optional[OptimizationRecommender] = None


def get_optimization_recommender() -> OptimizationRecommender:
    """Get or create the global optimization recommender"""
    global _global_recommender
    if _global_recommender is None:
        _global_recommender = OptimizationRecommender()
    return _global_recommender
