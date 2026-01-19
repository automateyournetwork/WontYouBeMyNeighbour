"""
Decision Engine

Makes intelligent routing decisions based on network state analysis.
Provides explainability for all decisions made by Ralph.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import ipaddress


@dataclass
class Decision:
    """Represents a routing or network decision"""

    decision_type: str  # "route_selection", "metric_adjustment", "peer_selection", etc.
    action: str  # Human-readable description
    rationale: str  # Detailed explanation
    confidence: float  # 0.0 - 1.0
    alternatives: List[str]  # Other options considered
    timestamp: datetime
    parameters: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "decision_type": self.decision_type,
            "action": self.action,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "alternatives": self.alternatives,
            "timestamp": self.timestamp.isoformat(),
            "parameters": self.parameters
        }


class DecisionEngine:
    """
    Agentic decision-making engine for network operations.

    Makes intelligent decisions about:
    - Route selection and preference
    - Metric adjustments
    - Anomaly response
    - Multi-path routing
    - Peer selection
    """

    def __init__(self, llm_interface=None):
        self.llm = llm_interface
        self.decision_history: List[Decision] = []

    async def select_best_route(
        self,
        destination: str,
        candidates: List[Dict[str, Any]],
        criteria: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[str, Any], Decision]:
        """
        Select best route from candidates with explanation.

        Args:
            destination: Destination network (e.g., "10.0.0.0/24")
            candidates: List of candidate routes with attributes
            criteria: Optional decision criteria (prefer_low_latency, etc.)

        Returns:
            (selected_route, decision_object)
        """
        if not candidates:
            raise ValueError("No candidate routes provided")

        # Default criteria
        criteria = criteria or {
            "prefer_shortest_as_path": True,
            "prefer_lowest_med": True,
            "prefer_ebgp_over_ibgp": True,
            "prefer_lowest_igp_metric": True
        }

        # Score each candidate
        scored_routes = []
        for route in candidates:
            score = self._score_route(route, criteria)
            scored_routes.append((route, score))

        # Sort by score (highest first)
        scored_routes.sort(key=lambda x: x[1], reverse=True)
        best_route, best_score = scored_routes[0]

        # Build rationale
        rationale_parts = [
            f"Selected route to {destination} via {best_route.get('next_hop', 'unknown')}",
            f"Score: {best_score:.2f}",
            "",
            "Decision factors:"
        ]

        if "as_path" in best_route:
            rationale_parts.append(f"- AS Path length: {len(best_route['as_path'])}")
        if "med" in best_route:
            rationale_parts.append(f"- MED: {best_route['med']}")
        if "local_pref" in best_route:
            rationale_parts.append(f"- Local Preference: {best_route['local_pref']}")
        if "metric" in best_route:
            rationale_parts.append(f"- IGP Metric: {best_route['metric']}")

        # Alternatives
        alternatives = [
            f"Route via {r[0].get('next_hop', 'unknown')} (score: {r[1]:.2f})"
            for r in scored_routes[1:4]  # Top 3 alternatives
        ]

        decision = Decision(
            decision_type="route_selection",
            action=f"Use route via {best_route.get('next_hop', 'unknown')}",
            rationale="\n".join(rationale_parts),
            confidence=best_score / 100.0,  # Normalize to 0-1
            alternatives=alternatives,
            timestamp=datetime.utcnow(),
            parameters={
                "destination": destination,
                "selected_route": best_route,
                "criteria": criteria
            }
        )

        self.decision_history.append(decision)
        return best_route, decision

    def _score_route(self, route: Dict[str, Any], criteria: Dict[str, Any]) -> float:
        """
        Score a route based on criteria.

        Higher score = better route.
        """
        score = 50.0  # Base score

        # AS Path length (shorter is better)
        if "as_path" in route and criteria.get("prefer_shortest_as_path"):
            as_path_len = len(route["as_path"])
            score += max(0, 20 - as_path_len * 2)  # Penalize long paths

        # MED (lower is better)
        if "med" in route and criteria.get("prefer_lowest_med"):
            med = route["med"]
            score += max(0, 20 - med / 10)  # Penalize high MED

        # Local Preference (higher is better)
        if "local_pref" in route:
            local_pref = route["local_pref"]
            score += (local_pref - 100) / 10  # Default is 100

        # eBGP over iBGP
        if "ibgp" in route and criteria.get("prefer_ebgp_over_ibgp"):
            if not route["ibgp"]:
                score += 15  # Bonus for eBGP

        # IGP metric (lower is better)
        if "metric" in route and criteria.get("prefer_lowest_igp_metric"):
            metric = route["metric"]
            score += max(0, 20 - metric / 5)

        return score

    async def detect_anomalies(
        self,
        network_state: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Detect network anomalies from current state.

        Returns list of anomalies with severity and recommended actions.
        """
        anomalies = []

        # Check OSPF neighbors
        if "ospf" in network_state:
            ospf = network_state["ospf"]
            neighbors = ospf.get("neighbors", [])

            # Detect flapping neighbors
            for neighbor in neighbors:
                if neighbor.get("state_changes", 0) > 5:
                    anomalies.append({
                        "type": "neighbor_flapping",
                        "severity": "high",
                        "protocol": "ospf",
                        "neighbor": neighbor.get("neighbor_id"),
                        "description": f"Neighbor {neighbor.get('neighbor_id')} has flapped {neighbor.get('state_changes')} times",
                        "recommendation": "Check interface stability and MTU settings"
                    })

        # Check BGP peers
        if "bgp" in network_state:
            bgp = network_state["bgp"]
            peers = bgp.get("peers", [])

            for peer in peers:
                # Peer down
                if peer.get("state") != "Established":
                    anomalies.append({
                        "type": "peer_down",
                        "severity": "critical",
                        "protocol": "bgp",
                        "peer": peer.get("peer"),
                        "description": f"BGP peer {peer.get('peer')} is {peer.get('state')}",
                        "recommendation": "Check connectivity and peer configuration"
                    })

                # High prefix count
                if peer.get("prefix_count", 0) > 10000:
                    anomalies.append({
                        "type": "high_prefix_count",
                        "severity": "warning",
                        "protocol": "bgp",
                        "peer": peer.get("peer"),
                        "description": f"Peer {peer.get('peer')} is advertising {peer.get('prefix_count')} prefixes",
                        "recommendation": "Consider applying prefix limit"
                    })

        # Check for routing loops
        if "routes" in network_state:
            routes = network_state["routes"]
            # Simple check: same prefix with different next-hops
            prefix_next_hops = {}
            for route in routes:
                prefix = route.get("network")
                nh = route.get("next_hop")
                if prefix in prefix_next_hops:
                    prefix_next_hops[prefix].append(nh)
                else:
                    prefix_next_hops[prefix] = [nh]

            for prefix, next_hops in prefix_next_hops.items():
                if len(next_hops) > 3:
                    anomalies.append({
                        "type": "multiple_paths",
                        "severity": "info",
                        "description": f"Prefix {prefix} has {len(next_hops)} next-hops",
                        "recommendation": "This might indicate ECMP or potential routing instability"
                    })

        return anomalies

    async def suggest_metric_adjustment(
        self,
        interface: str,
        current_metric: int,
        utilization: float,
        network_state: Dict[str, Any]
    ) -> Decision:
        """
        Suggest OSPF metric adjustment based on utilization.

        Args:
            interface: Interface name
            current_metric: Current OSPF cost
            utilization: Current utilization (0.0 - 1.0)
            network_state: Full network state for context

        Returns:
            Decision object with suggested adjustment
        """
        suggested_metric = current_metric

        # High utilization: increase metric to discourage use
        if utilization > 0.8:
            suggested_metric = int(current_metric * 1.5)
            rationale = f"Interface {interface} is {utilization*100:.0f}% utilized. Increasing metric from {current_metric} to {suggested_metric} to reduce load."
            confidence = 0.85

        # Low utilization: decrease metric to encourage use
        elif utilization < 0.2 and current_metric > 10:
            suggested_metric = max(10, int(current_metric * 0.7))
            rationale = f"Interface {interface} is only {utilization*100:.0f}% utilized. Decreasing metric from {current_metric} to {suggested_metric} to attract more traffic."
            confidence = 0.75

        # Optimal utilization
        else:
            rationale = f"Interface {interface} utilization ({utilization*100:.0f}%) is optimal. No metric adjustment needed."
            confidence = 0.9

        decision = Decision(
            decision_type="metric_adjustment",
            action=f"Adjust OSPF cost on {interface} to {suggested_metric}" if suggested_metric != current_metric else "No change",
            rationale=rationale,
            confidence=confidence,
            alternatives=[
                f"Keep current metric: {current_metric}",
                f"Aggressive adjustment: {int(current_metric * 2) if utilization > 0.8 else int(current_metric * 0.5)}"
            ],
            timestamp=datetime.utcnow(),
            parameters={
                "interface": interface,
                "current_metric": current_metric,
                "suggested_metric": suggested_metric,
                "utilization": utilization
            }
        )

        self.decision_history.append(decision)
        return decision

    def explain_last_decision(self) -> Optional[str]:
        """Get explanation of the most recent decision"""
        if not self.decision_history:
            return "No decisions made yet."

        last_decision = self.decision_history[-1]
        explanation = [
            f"Decision Type: {last_decision.decision_type}",
            f"Action: {last_decision.action}",
            f"Confidence: {last_decision.confidence*100:.0f}%",
            "",
            "Rationale:",
            last_decision.rationale,
        ]

        if last_decision.alternatives:
            explanation.append("")
            explanation.append("Alternatives considered:")
            for alt in last_decision.alternatives:
                explanation.append(f"- {alt}")

        return "\n".join(explanation)

    def get_decision_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent decision history"""
        recent = self.decision_history[-limit:]
        return [d.to_dict() for d in recent]
