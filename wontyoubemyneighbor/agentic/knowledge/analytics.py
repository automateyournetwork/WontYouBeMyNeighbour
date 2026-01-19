"""
Network Analytics

Provides time-series analysis, trend detection, and predictive insights
based on network state snapshots.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import statistics


class NetworkAnalytics:
    """
    Analyzes network state over time to detect trends and anomalies.

    Capabilities:
    - Neighbor/peer stability analysis
    - Route churn detection
    - Performance trend analysis
    - Predictive failure detection
    """

    def __init__(self, state_manager):
        self.state_manager = state_manager

    def analyze_neighbor_stability(
        self,
        protocol: str = "ospf",
        time_window_minutes: int = 60
    ) -> Dict[str, Any]:
        """
        Analyze neighbor/peer stability over time window.

        Args:
            protocol: "ospf" or "bgp"
            time_window_minutes: Time window for analysis

        Returns:
            Stability metrics and flapping detection
        """
        snapshots = self._get_snapshots_in_window(time_window_minutes)
        if len(snapshots) < 2:
            return {"error": "Insufficient snapshots for analysis"}

        if protocol == "ospf":
            return self._analyze_ospf_neighbors(snapshots)
        elif protocol == "bgp":
            return self._analyze_bgp_peers(snapshots)
        else:
            return {"error": f"Unknown protocol: {protocol}"}

    def _analyze_ospf_neighbors(self, snapshots: List) -> Dict[str, Any]:
        """Analyze OSPF neighbor stability"""
        # Track neighbor state changes
        neighbor_history: Dict[str, List[str]] = {}

        for snapshot in snapshots:
            neighbors = snapshot.ospf_state.get("neighbors", [])
            for neighbor in neighbors:
                neighbor_id = neighbor["neighbor_id"]
                state = neighbor["state"]

                if neighbor_id not in neighbor_history:
                    neighbor_history[neighbor_id] = []
                neighbor_history[neighbor_id].append(state)

        # Detect flapping
        flapping_neighbors = []
        stable_neighbors = []

        for neighbor_id, states in neighbor_history.items():
            state_changes = sum(1 for i in range(1, len(states)) if states[i] != states[i-1])

            if state_changes > 3:
                flapping_neighbors.append({
                    "neighbor_id": neighbor_id,
                    "state_changes": state_changes,
                    "current_state": states[-1] if states else "Unknown"
                })
            else:
                stable_neighbors.append(neighbor_id)

        stability_score = len(stable_neighbors) / len(neighbor_history) if neighbor_history else 1.0

        return {
            "protocol": "ospf",
            "total_neighbors": len(neighbor_history),
            "stable_neighbors": len(stable_neighbors),
            "flapping_neighbors": flapping_neighbors,
            "stability_score": stability_score,
            "time_window_minutes": len(snapshots)
        }

    def _analyze_bgp_peers(self, snapshots: List) -> Dict[str, Any]:
        """Analyze BGP peer stability"""
        peer_history: Dict[str, List[str]] = {}

        for snapshot in snapshots:
            peers = snapshot.bgp_state.get("peers", [])
            for peer in peers:
                peer_addr = peer["peer"]
                state = peer["state"]

                if peer_addr not in peer_history:
                    peer_history[peer_addr] = []
                peer_history[peer_addr].append(state)

        # Detect flapping
        flapping_peers = []
        stable_peers = []

        for peer_addr, states in peer_history.items():
            state_changes = sum(1 for i in range(1, len(states)) if states[i] != states[i-1])

            if state_changes > 2:
                flapping_peers.append({
                    "peer": peer_addr,
                    "state_changes": state_changes,
                    "current_state": states[-1] if states else "Unknown"
                })
            else:
                stable_peers.append(peer_addr)

        stability_score = len(stable_peers) / len(peer_history) if peer_history else 1.0

        return {
            "protocol": "bgp",
            "total_peers": len(peer_history),
            "stable_peers": len(stable_peers),
            "flapping_peers": flapping_peers,
            "stability_score": stability_score,
            "time_window_minutes": len(snapshots)
        }

    def analyze_route_churn(
        self,
        time_window_minutes: int = 60
    ) -> Dict[str, Any]:
        """
        Analyze route churn (additions/removals) over time.

        High churn indicates instability.
        """
        snapshots = self._get_snapshots_in_window(time_window_minutes)
        if len(snapshots) < 2:
            return {"error": "Insufficient snapshots for analysis"}

        route_counts = [len(s.routing_table) for s in snapshots]
        route_changes = [
            abs(route_counts[i] - route_counts[i-1])
            for i in range(1, len(route_counts))
        ]

        return {
            "min_routes": min(route_counts),
            "max_routes": max(route_counts),
            "current_routes": route_counts[-1],
            "avg_routes": statistics.mean(route_counts),
            "total_churn": sum(route_changes),
            "avg_churn_per_snapshot": statistics.mean(route_changes) if route_changes else 0,
            "max_single_change": max(route_changes) if route_changes else 0,
            "stability": "stable" if max(route_changes) < 10 else "unstable"
        }

    def analyze_health_trend(
        self,
        time_window_minutes: int = 60
    ) -> Dict[str, Any]:
        """
        Analyze overall health score trend.

        Returns trend direction and prediction.
        """
        snapshots = self._get_snapshots_in_window(time_window_minutes)
        if len(snapshots) < 3:
            return {"error": "Insufficient snapshots for trend analysis"}

        health_scores = [s.metrics.get("health_score", 0) for s in snapshots]

        # Simple linear trend
        trend = self._calculate_trend(health_scores)

        # Predict next value
        if trend != 0:
            predicted_next = health_scores[-1] + trend
        else:
            predicted_next = health_scores[-1]

        return {
            "current_health": health_scores[-1],
            "avg_health": statistics.mean(health_scores),
            "min_health": min(health_scores),
            "max_health": max(health_scores),
            "trend": "improving" if trend > 0.5 else "degrading" if trend < -0.5 else "stable",
            "trend_value": trend,
            "predicted_next": max(0, min(100, predicted_next)),
            "samples": len(health_scores)
        }

    def predict_neighbor_failure(
        self,
        protocol: str = "ospf"
    ) -> List[Dict[str, Any]]:
        """
        Predict potential neighbor/peer failures based on patterns.

        Returns list of neighbors/peers at risk.
        """
        snapshots = self._get_snapshots_in_window(30)  # Last 30 minutes
        if len(snapshots) < 5:
            return []

        at_risk = []

        if protocol == "ospf":
            # Check for neighbors with increasing state changes
            for snapshot in snapshots[-3:]:
                neighbors = snapshot.ospf_state.get("neighbors", [])
                for neighbor in neighbors:
                    state_changes = neighbor.get("state_changes", 0)
                    if state_changes > 5:
                        at_risk.append({
                            "protocol": "ospf",
                            "neighbor_id": neighbor["neighbor_id"],
                            "state_changes": state_changes,
                            "current_state": neighbor["state"],
                            "risk_level": "high" if state_changes > 10 else "medium",
                            "recommendation": "Monitor for flapping, check interface stability"
                        })

        elif protocol == "bgp":
            # Check for peers with frequent state changes
            for snapshot in snapshots[-3:]:
                peers = snapshot.bgp_state.get("peers", [])
                for peer in peers:
                    if peer["state"] != "Established":
                        at_risk.append({
                            "protocol": "bgp",
                            "peer": peer["peer"],
                            "current_state": peer["state"],
                            "risk_level": "high",
                            "recommendation": "Peer not established, check connectivity"
                        })

        return at_risk

    def _get_snapshots_in_window(
        self,
        time_window_minutes: int
    ) -> List:
        """Get snapshots within time window"""
        if not self.state_manager.snapshots:
            return []

        cutoff_time = datetime.utcnow() - timedelta(minutes=time_window_minutes)
        return [
            s for s in self.state_manager.snapshots
            if s.timestamp >= cutoff_time
        ]

    def _calculate_trend(self, values: List[float]) -> float:
        """
        Calculate simple linear trend.

        Returns slope (positive = increasing, negative = decreasing).
        """
        if len(values) < 2:
            return 0.0

        n = len(values)
        x = list(range(n))

        # Simple linear regression
        x_mean = statistics.mean(x)
        y_mean = statistics.mean(values)

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        return numerator / denominator

    def generate_report(self) -> str:
        """
        Generate comprehensive analytics report.

        Returns formatted string with all analyses.
        """
        lines = []
        lines.append("Network Analytics Report")
        lines.append("=" * 60)
        lines.append(f"Generated: {datetime.utcnow().isoformat()}")
        lines.append("")

        # OSPF neighbor stability
        ospf_analysis = self.analyze_neighbor_stability(protocol="ospf", time_window_minutes=30)
        if "error" not in ospf_analysis:
            lines.append("OSPF Neighbor Stability (30 min):")
            lines.append(f"  Total neighbors: {ospf_analysis['total_neighbors']}")
            lines.append(f"  Stable: {ospf_analysis['stable_neighbors']}")
            lines.append(f"  Stability score: {ospf_analysis['stability_score']*100:.1f}%")
            if ospf_analysis['flapping_neighbors']:
                lines.append(f"  Flapping neighbors: {len(ospf_analysis['flapping_neighbors'])}")

        lines.append("")

        # BGP peer stability
        bgp_analysis = self.analyze_neighbor_stability(protocol="bgp", time_window_minutes=30)
        if "error" not in bgp_analysis:
            lines.append("BGP Peer Stability (30 min):")
            lines.append(f"  Total peers: {bgp_analysis['total_peers']}")
            lines.append(f"  Stable: {bgp_analysis['stable_peers']}")
            lines.append(f"  Stability score: {bgp_analysis['stability_score']*100:.1f}%")
            if bgp_analysis['flapping_peers']:
                lines.append(f"  Flapping peers: {len(bgp_analysis['flapping_peers'])}")

        lines.append("")

        # Route churn
        churn_analysis = self.analyze_route_churn(time_window_minutes=30)
        if "error" not in churn_analysis:
            lines.append("Route Churn (30 min):")
            lines.append(f"  Current routes: {churn_analysis['current_routes']}")
            lines.append(f"  Avg churn per snapshot: {churn_analysis['avg_churn_per_snapshot']:.1f}")
            lines.append(f"  Stability: {churn_analysis['stability']}")

        lines.append("")

        # Health trend
        health_trend = self.analyze_health_trend(time_window_minutes=30)
        if "error" not in health_trend:
            lines.append("Health Trend (30 min):")
            lines.append(f"  Current: {health_trend['current_health']:.1f}/100")
            lines.append(f"  Trend: {health_trend['trend']}")
            lines.append(f"  Predicted next: {health_trend['predicted_next']:.1f}/100")

        return "\n".join(lines)
