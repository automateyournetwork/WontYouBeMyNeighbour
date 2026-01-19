"""
Action Executor

Executes autonomous network actions with safety checks and approval workflows.
Bridges the reasoning engine with actual OSPF/BGP protocol operations.
"""

from enum import Enum
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import asyncio

from .safety import SafetyConstraints, SafetyViolation


class ActionStatus(str, Enum):
    """Status of action execution"""
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class ActionResult:
    """Result of action execution"""
    action_id: str
    action_type: str
    status: ActionStatus
    parameters: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    safety_violation: Optional[SafetyViolation] = None
    timestamp: Optional[datetime] = None
    execution_time_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "status": self.status.value,
            "parameters": self.parameters,
            "result": self.result,
            "error": self.error,
            "safety_violation": {
                "type": self.safety_violation.violation_type.value,
                "severity": self.safety_violation.severity,
                "message": self.safety_violation.message
            } if self.safety_violation else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "execution_time_ms": self.execution_time_ms
        }


class ActionExecutor:
    """
    Executes network actions with safety constraints.

    Handles:
    - Safety validation
    - Human approval workflow
    - Action execution
    - Rollback on failure
    - Audit logging
    """

    def __init__(
        self,
        safety_constraints: Optional[SafetyConstraints] = None,
        approval_callback: Optional[Callable] = None
    ):
        self.safety = safety_constraints or SafetyConstraints()
        self.approval_callback = approval_callback
        self.pending_actions: Dict[str, ActionResult] = {}
        self.completed_actions: list[ActionResult] = []
        self._action_counter = 0

        # Protocol handlers (to be injected)
        self.ospf_interface = None
        self.bgp_speaker = None

    def set_protocol_handlers(self, ospf_interface=None, bgp_speaker=None):
        """Inject protocol handlers for actual network operations"""
        self.ospf_interface = ospf_interface
        self.bgp_speaker = bgp_speaker

    async def execute_action(
        self,
        action_type: str,
        parameters: Dict[str, Any],
        skip_safety: bool = False
    ) -> ActionResult:
        """
        Execute a network action with safety checks.

        Args:
            action_type: Type of action (metric_adjustment, route_injection, etc.)
            parameters: Action-specific parameters
            skip_safety: Skip safety checks (dangerous, use only for testing)

        Returns:
            ActionResult with status and outcome
        """
        # Generate action ID
        self._action_counter += 1
        action_id = f"action_{self._action_counter:04d}"

        # Create action result
        action_result = ActionResult(
            action_id=action_id,
            action_type=action_type,
            status=ActionStatus.PENDING_APPROVAL,
            parameters=parameters,
            timestamp=datetime.utcnow()
        )

        # Safety validation
        if not skip_safety:
            if not self.safety.is_action_allowed(action_type, parameters):
                # Get specific violation
                violation = self._get_safety_violation(action_type, parameters)
                action_result.safety_violation = violation
                action_result.status = ActionStatus.BLOCKED
                action_result.error = violation.message if violation else "Action requires approval"

                # Request human approval if callback provided
                if self.approval_callback and violation and not violation.action_blocked:
                    self.pending_actions[action_id] = action_result
                    approved = await self.approval_callback(action_result)
                    if approved:
                        action_result.status = ActionStatus.APPROVED
                    else:
                        action_result.status = ActionStatus.REJECTED
                        self.completed_actions.append(action_result)
                        return action_result
                else:
                    self.completed_actions.append(action_result)
                    return action_result

        # Execute action
        action_result.status = ActionStatus.EXECUTING
        start_time = asyncio.get_event_loop().time()

        try:
            if action_type == "metric_adjustment":
                result = await self._execute_metric_adjustment(parameters)
            elif action_type == "route_injection":
                result = await self._execute_route_injection(parameters)
            elif action_type == "graceful_shutdown":
                result = await self._execute_graceful_shutdown(parameters)
            elif action_type == "query_neighbors":
                result = await self._execute_query_neighbors(parameters)
            elif action_type == "query_routes":
                result = await self._execute_query_routes(parameters)
            else:
                raise ValueError(f"Unknown action type: {action_type}")

            action_result.status = ActionStatus.COMPLETED
            action_result.result = result

        except Exception as e:
            action_result.status = ActionStatus.FAILED
            action_result.error = str(e)

        # Record execution time
        end_time = asyncio.get_event_loop().time()
        action_result.execution_time_ms = (end_time - start_time) * 1000

        # Record in safety history
        self.safety.record_action({
            "type": action_type,
            "action_id": action_id,
            **parameters
        })

        self.completed_actions.append(action_result)
        return action_result

    def _get_safety_violation(
        self,
        action_type: str,
        parameters: Dict[str, Any]
    ) -> Optional[SafetyViolation]:
        """Get safety violation for action type"""
        if action_type == "metric_adjustment":
            return self.safety.validate_metric_adjustment(
                interface=parameters.get("interface"),
                current_metric=parameters.get("current_metric", 0),
                proposed_metric=parameters.get("proposed_metric", 0)
            )
        elif action_type == "route_injection":
            return self.safety.validate_route_injection(
                network=parameters.get("network"),
                protocol=parameters.get("protocol", "bgp")
            )
        elif action_type == "graceful_shutdown":
            return self.safety.validate_graceful_shutdown(
                protocol=parameters.get("protocol"),
                scope=parameters.get("scope", "all")
            )
        return None

    async def _execute_metric_adjustment(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute OSPF metric adjustment"""
        interface = params["interface"]
        new_metric = params["proposed_metric"]

        if not self.ospf_interface:
            raise RuntimeError("OSPF interface not configured")

        # In real implementation, this would update OSPF interface cost
        # For now, return simulated result
        return {
            "interface": interface,
            "old_metric": params.get("current_metric", 0),
            "new_metric": new_metric,
            "message": f"Updated OSPF cost on {interface} to {new_metric}"
        }

    async def _execute_route_injection(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute route injection (BGP/OSPF)"""
        network = params["network"]
        protocol = params.get("protocol", "bgp")

        if protocol == "bgp" and not self.bgp_speaker:
            raise RuntimeError("BGP speaker not configured")
        elif protocol == "ospf" and not self.ospf_interface:
            raise RuntimeError("OSPF interface not configured")

        # In real implementation, this would inject route into protocol
        return {
            "network": network,
            "protocol": protocol,
            "message": f"Injected route {network} into {protocol.upper()}"
        }

    async def _execute_graceful_shutdown(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute graceful protocol shutdown"""
        protocol = params["protocol"]
        scope = params.get("scope", "all")

        # In real implementation, this would initiate graceful shutdown
        return {
            "protocol": protocol,
            "scope": scope,
            "message": f"Initiated graceful shutdown of {protocol} ({scope})"
        }

    async def _execute_query_neighbors(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Query OSPF/BGP neighbors"""
        protocol = params.get("protocol", "ospf")

        if protocol == "ospf" and self.ospf_interface:
            # Get OSPF neighbors from interface
            neighbors = []
            for neighbor in self.ospf_interface.neighbors.values():
                neighbors.append({
                    "neighbor_id": neighbor.neighbor_id,
                    "state": neighbor.state,
                    "address": neighbor.address
                })
            return {"protocol": "ospf", "neighbors": neighbors}

        elif protocol == "bgp" and self.bgp_speaker:
            # Get BGP peers
            peers = []
            for peer in self.bgp_speaker.agent.sessions.values():
                peers.append({
                    "peer": str(peer.peer_addr),
                    "as": peer.peer_as,
                    "state": peer.state
                })
            return {"protocol": "bgp", "peers": peers}

        return {"protocol": protocol, "neighbors": []}

    async def _execute_query_routes(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Query routing table"""
        destination = params.get("destination")

        # In real implementation, query actual routing table
        routes = []

        if self.bgp_speaker:
            # Get BGP routes
            for route_key, route_info in self.bgp_speaker.rib.items():
                if destination is None or route_key[0] == destination:
                    routes.append({
                        "network": route_key[0],
                        "next_hop": str(route_info.get("next_hop", "")),
                        "protocol": "bgp",
                        "as_path": route_info.get("as_path", [])
                    })

        return {"routes": routes, "count": len(routes)}

    def get_pending_actions(self) -> list[ActionResult]:
        """Get list of actions pending approval"""
        return list(self.pending_actions.values())

    def approve_action(self, action_id: str) -> bool:
        """Approve a pending action"""
        if action_id in self.pending_actions:
            action = self.pending_actions.pop(action_id)
            action.status = ActionStatus.APPROVED
            # Re-execute with approval
            asyncio.create_task(self.execute_action(
                action.action_type,
                action.parameters,
                skip_safety=True
            ))
            return True
        return False

    def reject_action(self, action_id: str, reason: str = "User rejected") -> bool:
        """Reject a pending action"""
        if action_id in self.pending_actions:
            action = self.pending_actions.pop(action_id)
            action.status = ActionStatus.REJECTED
            action.error = reason
            self.completed_actions.append(action)
            return True
        return False

    def get_action_history(self, limit: int = 50) -> list[Dict[str, Any]]:
        """Get recent action history"""
        recent = self.completed_actions[-limit:]
        return [action.to_dict() for action in recent]
