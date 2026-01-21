"""
Safety Constraints

Enforces safety rules for autonomous network actions.
Prevents RubberBand from making dangerous changes without human approval.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum


class ViolationType(str, Enum):
    """Types of safety violations"""
    METRIC_OUT_OF_RANGE = "metric_out_of_range"
    CRITICAL_INTERFACE = "critical_interface"
    ROUTE_COUNT_LIMIT = "route_count_limit"
    FREQUENT_CHANGES = "frequent_changes"
    NETWORK_DISRUPTION = "network_disruption"
    UNAUTHORIZED_ACTION = "unauthorized_action"


@dataclass
class SafetyViolation:
    """Represents a safety constraint violation"""
    violation_type: ViolationType
    severity: str  # "info", "warning", "critical"
    message: str
    action_blocked: bool
    parameters: Dict[str, Any]


class SafetyConstraints:
    """
    Enforces safety constraints on network actions.

    Prevents:
    - Metrics outside reasonable range
    - Changes to critical interfaces
    - Too many route injections
    - Too frequent changes
    - Actions that could cause network disruption
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or self._default_config()
        self.action_history: List[Dict[str, Any]] = []

    def _default_config(self) -> Dict[str, Any]:
        """Default safety configuration"""
        return {
            "metric_range": {
                "min": 1,
                "max": 65535
            },
            "critical_interfaces": [],  # Interfaces that require approval
            "max_route_injections": 100,  # Max routes RubberBand can inject
            "min_change_interval": 60,  # Seconds between changes to same resource
            "require_approval_for": [
                "graceful_shutdown",
                "route_injection",
                "metric_change_large"  # >50% change
            ],
            "autonomous_mode": False  # If False, all actions require approval
        }

    def validate_metric_adjustment(
        self,
        interface: str,
        current_metric: int,
        proposed_metric: int
    ) -> Optional[SafetyViolation]:
        """
        Validate OSPF metric adjustment.

        Returns SafetyViolation if constraints violated, None otherwise.
        """
        # Check range
        if proposed_metric < self.config["metric_range"]["min"]:
            return SafetyViolation(
                violation_type=ViolationType.METRIC_OUT_OF_RANGE,
                severity="critical",
                message=f"Proposed metric {proposed_metric} is below minimum {self.config['metric_range']['min']}",
                action_blocked=True,
                parameters={"interface": interface, "proposed_metric": proposed_metric}
            )

        if proposed_metric > self.config["metric_range"]["max"]:
            return SafetyViolation(
                violation_type=ViolationType.METRIC_OUT_OF_RANGE,
                severity="critical",
                message=f"Proposed metric {proposed_metric} exceeds maximum {self.config['metric_range']['max']}",
                action_blocked=True,
                parameters={"interface": interface, "proposed_metric": proposed_metric}
            )

        # Check critical interface
        if interface in self.config["critical_interfaces"]:
            return SafetyViolation(
                violation_type=ViolationType.CRITICAL_INTERFACE,
                severity="warning",
                message=f"Interface {interface} is critical and requires human approval",
                action_blocked=not self.config["autonomous_mode"],
                parameters={"interface": interface}
            )

        # Check large change (>50%)
        if current_metric > 0:
            change_pct = abs(proposed_metric - current_metric) / current_metric
            if change_pct > 0.5:
                return SafetyViolation(
                    violation_type=ViolationType.NETWORK_DISRUPTION,
                    severity="warning",
                    message=f"Metric change of {change_pct*100:.0f}% may cause traffic shift. Human approval recommended.",
                    action_blocked=not self.config["autonomous_mode"],
                    parameters={
                        "interface": interface,
                        "current_metric": current_metric,
                        "proposed_metric": proposed_metric,
                        "change_percent": change_pct
                    }
                )

        # Check recent changes to same interface
        recent_changes = [
            action for action in self.action_history
            if action.get("interface") == interface
            and action.get("type") == "metric_adjustment"
        ]

        if recent_changes:
            import time
            last_change_time = recent_changes[-1].get("timestamp", 0)
            time_since_last = time.time() - last_change_time
            if time_since_last < self.config["min_change_interval"]:
                return SafetyViolation(
                    violation_type=ViolationType.FREQUENT_CHANGES,
                    severity="warning",
                    message=f"Interface {interface} was adjusted {int(time_since_last)}s ago. Min interval: {self.config['min_change_interval']}s",
                    action_blocked=True,
                    parameters={
                        "interface": interface,
                        "time_since_last": time_since_last
                    }
                )

        return None

    def validate_route_injection(
        self,
        network: str,
        protocol: str = "bgp"
    ) -> Optional[SafetyViolation]:
        """Validate route injection"""
        # Count injected routes
        injected_routes = [
            action for action in self.action_history
            if action.get("type") == "route_injection"
        ]

        if len(injected_routes) >= self.config["max_route_injections"]:
            return SafetyViolation(
                violation_type=ViolationType.ROUTE_COUNT_LIMIT,
                severity="critical",
                message=f"Route injection limit reached: {len(injected_routes)}/{self.config['max_route_injections']}",
                action_blocked=True,
                parameters={"network": network, "protocol": protocol}
            )

        # Route injection always requires approval in default config
        if "route_injection" in self.config["require_approval_for"]:
            return SafetyViolation(
                violation_type=ViolationType.UNAUTHORIZED_ACTION,
                severity="info",
                message=f"Route injection requires human approval per policy",
                action_blocked=not self.config["autonomous_mode"],
                parameters={"network": network, "protocol": protocol}
            )

        return None

    def validate_graceful_shutdown(
        self,
        protocol: str,
        scope: str = "all"  # "all", "peer", "interface"
    ) -> Optional[SafetyViolation]:
        """Validate graceful shutdown"""
        # Graceful shutdown always requires approval
        return SafetyViolation(
            violation_type=ViolationType.NETWORK_DISRUPTION,
            severity="critical",
            message=f"Graceful shutdown of {protocol} ({scope}) requires human approval",
            action_blocked=True,
            parameters={"protocol": protocol, "scope": scope}
        )

    def record_action(self, action: Dict[str, Any]):
        """Record action in history for rate limiting"""
        import time
        action["timestamp"] = time.time()
        self.action_history.append(action)

        # Keep only recent history (last 1000 actions)
        if len(self.action_history) > 1000:
            self.action_history = self.action_history[-1000:]

    def set_autonomous_mode(self, enabled: bool):
        """Enable/disable autonomous mode"""
        self.config["autonomous_mode"] = enabled

    def add_critical_interface(self, interface: str):
        """Mark interface as critical (requires approval)"""
        if interface not in self.config["critical_interfaces"]:
            self.config["critical_interfaces"].append(interface)

    def is_action_allowed(self, action_type: str, parameters: Dict[str, Any]) -> bool:
        """
        Check if action is allowed without human approval.

        Returns True if autonomous, False if requires approval.
        Read-only query actions are always allowed.
        """
        # Read-only query actions are always allowed (they don't modify network state)
        read_only_actions = {
            "query_neighbors",
            "query_routes",
            "query_status",
            "query_rib",
            "query_bgp_peer",
            "query_lsa",
            "query_route",
            "query_neighbor",
            "analyze_topology",
            "analyze_path",
            "detect_anomaly",
            "explain_decision",
        }

        if action_type in read_only_actions:
            return True

        if not self.config["autonomous_mode"]:
            return False

        # Validate based on action type
        if action_type == "metric_adjustment":
            violation = self.validate_metric_adjustment(
                interface=parameters.get("interface"),
                current_metric=parameters.get("current_metric", 0),
                proposed_metric=parameters.get("proposed_metric", 0)
            )
        elif action_type == "route_injection":
            violation = self.validate_route_injection(
                network=parameters.get("network"),
                protocol=parameters.get("protocol", "bgp")
            )
        elif action_type == "graceful_shutdown":
            violation = self.validate_graceful_shutdown(
                protocol=parameters.get("protocol"),
                scope=parameters.get("scope", "all")
            )
        else:
            # Unknown action type requires approval
            return False

        # If no violation or not action_blocked, allow
        return violation is None or not violation.action_blocked
