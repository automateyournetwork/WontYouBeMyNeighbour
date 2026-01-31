"""
Remediation Engine - Automatic remediation of network issues

Provides:
- Pre-defined remediation actions
- Action execution with safety checks
- Rollback capability
- Action history and audit trail
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Awaitable
from collections import deque

logger = logging.getLogger("RemediationEngine")


class ActionStatus(Enum):
    """Remediation action status"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


@dataclass
class RemediationAction:
    """
    Remediation action definition

    Attributes:
        action_id: Unique action identifier
        name: Action name
        description: Action description
        event_types: Event types this action handles
        protocol: Applicable protocol
        severity_threshold: Minimum severity to trigger
        auto_execute: Whether to execute automatically
        cooldown_seconds: Minimum time between executions
    """
    action_id: str
    name: str
    description: str
    event_types: List[str]
    protocol: str
    severity_threshold: int = 5
    auto_execute: bool = True
    cooldown_seconds: int = 60


@dataclass
class ActionResult:
    """
    Result of a remediation action

    Attributes:
        action_id: Action that was executed
        timestamp: Execution time
        status: Execution status
        event_type: Triggering event type
        agent_id: Affected agent
        peer_id: Affected peer (if applicable)
        details: Execution details
        error: Error message (if failed)
        rollback_available: Whether rollback is available
    """
    action_id: str
    timestamp: datetime
    status: ActionStatus
    event_type: str
    agent_id: str
    peer_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    rollback_available: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "event_type": self.event_type,
            "agent_id": self.agent_id,
            "peer_id": self.peer_id,
            "details": self.details,
            "error": self.error,
            "rollback_available": self.rollback_available,
        }


class RemediationEngine:
    """
    Automatic remediation engine

    Executes remediation actions in response to health events.
    """

    def __init__(self, max_history: int = 1000, dry_run: bool = False):
        """
        Initialize remediation engine

        Args:
            max_history: Maximum action history to retain
            dry_run: If True, log actions but don't execute
        """
        self.dry_run = dry_run
        self._actions: Dict[str, RemediationAction] = {}
        self._history: deque = deque(maxlen=max_history)
        self._last_execution: Dict[str, datetime] = {}  # action_id -> last execution time
        self._handlers: Dict[str, Callable[[str, str, Optional[str]], Awaitable[Dict[str, Any]]]] = {}

        # Register default actions
        self._register_default_actions()

    def _register_default_actions(self) -> None:
        """Register default remediation actions"""
        # OSPF actions
        self.register_action(RemediationAction(
            action_id="ospf_reset_adjacency",
            name="Reset OSPF Adjacency",
            description="Clear and reset OSPF adjacency with neighbor",
            event_types=["ospf_adjacency_down", "ospf_neighbor_lost"],
            protocol="ospf",
            severity_threshold=7,
            auto_execute=True,
            cooldown_seconds=120
        ))

        self.register_action(RemediationAction(
            action_id="ospf_clear_lsdb",
            name="Clear OSPF LSDB",
            description="Clear OSPF link-state database for area",
            event_types=["ospf_adjacency_degraded"],
            protocol="ospf",
            severity_threshold=5,
            auto_execute=False,  # Requires manual approval
            cooldown_seconds=300
        ))

        # BGP actions
        self.register_action(RemediationAction(
            action_id="bgp_soft_reset",
            name="BGP Soft Reset",
            description="Perform soft reset of BGP session",
            event_types=["bgp_peer_down", "bgp_peer_transitioning"],
            protocol="bgp",
            severity_threshold=6,
            auto_execute=True,
            cooldown_seconds=60
        ))

        self.register_action(RemediationAction(
            action_id="bgp_hard_reset",
            name="BGP Hard Reset",
            description="Perform hard reset of BGP session",
            event_types=["bgp_peer_down"],
            protocol="bgp",
            severity_threshold=9,
            auto_execute=False,  # Requires manual approval
            cooldown_seconds=180
        ))

        self.register_action(RemediationAction(
            action_id="bgp_enable_dampening",
            name="Enable BGP Route Dampening",
            description="Enable route flap dampening for peer",
            event_types=["bgp_peer_flapping"],
            protocol="bgp",
            severity_threshold=7,
            auto_execute=True,
            cooldown_seconds=600
        ))

        # IS-IS actions
        self.register_action(RemediationAction(
            action_id="isis_reset_adjacency",
            name="Reset IS-IS Adjacency",
            description="Clear and reset IS-IS adjacency",
            event_types=["isis_adjacency_down"],
            protocol="isis",
            severity_threshold=7,
            auto_execute=True,
            cooldown_seconds=120
        ))

        # Generic actions
        self.register_action(RemediationAction(
            action_id="interface_bounce",
            name="Interface Bounce",
            description="Administratively bounce interface",
            event_types=["ospf_adjacency_down", "bgp_peer_down", "isis_adjacency_down", "gre_tunnel_down", "bfd_session_down"],
            protocol="any",
            severity_threshold=8,
            auto_execute=False,  # Requires manual approval
            cooldown_seconds=300
        ))

        # GRE tunnel remediation
        self.register_action(RemediationAction(
            action_id="gre_tunnel_restart",
            name="GRE Tunnel Restart",
            description="Restart GRE tunnel endpoint",
            event_types=["gre_tunnel_down", "gre_keepalive_timeout"],
            protocol="gre",
            severity_threshold=7,
            auto_execute=True,
            cooldown_seconds=60
        ))

        # BFD session remediation
        self.register_action(RemediationAction(
            action_id="bfd_session_reset",
            name="BFD Session Reset",
            description="Reset BFD session to peer",
            event_types=["bfd_session_down", "bfd_detection_timeout"],
            protocol="bfd",
            severity_threshold=7,
            auto_execute=True,
            cooldown_seconds=30
        ))

        # BFD protocol notification
        self.register_action(RemediationAction(
            action_id="bfd_notify_protocol",
            name="BFD Notify Protocol",
            description="Notify client protocol of BFD failure for fast convergence",
            event_types=["bfd_session_down"],
            protocol="bfd",
            severity_threshold=8,
            auto_execute=True,
            cooldown_seconds=10
        ))

    def register_action(self, action: RemediationAction) -> None:
        """Register a remediation action"""
        self._actions[action.action_id] = action

    def register_handler(
        self,
        action_id: str,
        handler: Callable[[str, str, Optional[str]], Awaitable[Dict[str, Any]]]
    ) -> None:
        """
        Register execution handler for an action

        Args:
            action_id: Action ID
            handler: Async function(event_type, agent_id, peer_id) -> result dict
        """
        self._handlers[action_id] = handler

    def get_action(self, action_id: str) -> Optional[RemediationAction]:
        """Get action by ID"""
        return self._actions.get(action_id)

    def list_actions(self, protocol: Optional[str] = None) -> List[RemediationAction]:
        """
        List registered actions

        Args:
            protocol: Filter by protocol (optional)

        Returns:
            List of actions
        """
        actions = list(self._actions.values())
        if protocol:
            actions = [a for a in actions if a.protocol in [protocol, "any"]]
        return actions

    def _check_cooldown(self, action_id: str) -> bool:
        """Check if action is in cooldown period"""
        if action_id not in self._last_execution:
            return True

        action = self._actions.get(action_id)
        if not action:
            return True

        elapsed = (datetime.now() - self._last_execution[action_id]).total_seconds()
        return elapsed >= action.cooldown_seconds

    def find_applicable_actions(
        self,
        event_type: str,
        protocol: str,
        severity: int
    ) -> List[RemediationAction]:
        """
        Find actions applicable to an event

        Args:
            event_type: Event type
            protocol: Protocol
            severity: Event severity (1-10)

        Returns:
            List of applicable actions
        """
        applicable = []
        for action in self._actions.values():
            if event_type in action.event_types:
                if action.protocol in [protocol, "any"]:
                    if severity >= action.severity_threshold:
                        if self._check_cooldown(action.action_id):
                            applicable.append(action)
        return applicable

    async def execute_action(
        self,
        action_id: str,
        event_type: str,
        agent_id: str,
        peer_id: Optional[str] = None
    ) -> ActionResult:
        """
        Execute a remediation action

        Args:
            action_id: Action to execute
            event_type: Triggering event type
            agent_id: Agent to remediate
            peer_id: Peer/neighbor ID (optional)

        Returns:
            ActionResult with execution details
        """
        action = self._actions.get(action_id)
        if not action:
            return ActionResult(
                action_id=action_id,
                timestamp=datetime.now(),
                status=ActionStatus.FAILED,
                event_type=event_type,
                agent_id=agent_id,
                peer_id=peer_id,
                error=f"Unknown action: {action_id}"
            )

        # Check cooldown
        if not self._check_cooldown(action_id):
            return ActionResult(
                action_id=action_id,
                timestamp=datetime.now(),
                status=ActionStatus.SKIPPED,
                event_type=event_type,
                agent_id=agent_id,
                peer_id=peer_id,
                details={"reason": "Action in cooldown period"}
            )

        # Dry run mode
        if self.dry_run:
            logger.info(f"[DRY RUN] Would execute: {action.name} on {agent_id}/{peer_id}")
            result = ActionResult(
                action_id=action_id,
                timestamp=datetime.now(),
                status=ActionStatus.SUCCESS,
                event_type=event_type,
                agent_id=agent_id,
                peer_id=peer_id,
                details={"dry_run": True, "action_name": action.name}
            )
            self._history.append(result)
            return result

        # Execute handler if registered
        handler = self._handlers.get(action_id)
        if handler:
            try:
                logger.info(f"Executing remediation: {action.name} on {agent_id}/{peer_id}")
                exec_result = await handler(event_type, agent_id, peer_id)

                self._last_execution[action_id] = datetime.now()

                result = ActionResult(
                    action_id=action_id,
                    timestamp=datetime.now(),
                    status=ActionStatus.SUCCESS if exec_result.get("success", True) else ActionStatus.FAILED,
                    event_type=event_type,
                    agent_id=agent_id,
                    peer_id=peer_id,
                    details=exec_result,
                    rollback_available=exec_result.get("rollback_available", False)
                )
                self._history.append(result)
                return result

            except Exception as e:
                logger.error(f"Remediation failed: {action.name} - {e}")
                result = ActionResult(
                    action_id=action_id,
                    timestamp=datetime.now(),
                    status=ActionStatus.FAILED,
                    event_type=event_type,
                    agent_id=agent_id,
                    peer_id=peer_id,
                    error=str(e)
                )
                self._history.append(result)
                return result
        else:
            # No handler - simulate success
            logger.info(f"Simulating remediation: {action.name} on {agent_id}/{peer_id}")
            self._last_execution[action_id] = datetime.now()

            result = ActionResult(
                action_id=action_id,
                timestamp=datetime.now(),
                status=ActionStatus.SUCCESS,
                event_type=event_type,
                agent_id=agent_id,
                peer_id=peer_id,
                details={"simulated": True, "action_name": action.name}
            )
            self._history.append(result)
            return result

    async def handle_event(
        self,
        event_type: str,
        protocol: str,
        agent_id: str,
        peer_id: Optional[str] = None,
        severity: int = 5
    ) -> List[ActionResult]:
        """
        Handle a health event and execute applicable auto-remediation

        Args:
            event_type: Event type
            protocol: Protocol
            agent_id: Agent ID
            peer_id: Peer ID (optional)
            severity: Event severity

        Returns:
            List of action results
        """
        results = []
        applicable = self.find_applicable_actions(event_type, protocol, severity)

        for action in applicable:
            if action.auto_execute:
                result = await self.execute_action(
                    action.action_id, event_type, agent_id, peer_id
                )
                results.append(result)

        return results

    def get_history(self, limit: int = 100, status: Optional[ActionStatus] = None) -> List[ActionResult]:
        """
        Get action history

        Args:
            limit: Maximum results to return
            status: Filter by status (optional)

        Returns:
            List of action results
        """
        history = list(self._history)[-limit:]
        if status:
            history = [r for r in history if r.status == status]
        return history

    def get_statistics(self) -> Dict[str, Any]:
        """Get remediation statistics"""
        status_counts = {}
        for result in self._history:
            status_name = result.status.value
            status_counts[status_name] = status_counts.get(status_name, 0) + 1

        return {
            "total_actions": len(self._history),
            "actions_by_status": status_counts,
            "registered_actions": len(self._actions),
            "registered_handlers": len(self._handlers),
            "dry_run_mode": self.dry_run,
        }
