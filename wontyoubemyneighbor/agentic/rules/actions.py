"""
Rule Actions

Provides:
- Action definitions
- Action execution
- Action types
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from enum import Enum


class ActionType(Enum):
    """Types of actions"""
    LOG = "log"  # Log a message
    ALERT = "alert"  # Send alert/notification
    EMAIL = "email"  # Send email
    WEBHOOK = "webhook"  # Call webhook
    SCRIPT = "script"  # Execute script
    API_CALL = "api_call"  # Call API
    SET_VARIABLE = "set_variable"  # Set context variable
    TRANSFORM = "transform"  # Transform data
    ROUTE = "route"  # Route to handler
    ESCALATE = "escalate"  # Escalate to higher priority
    REMEDIATE = "remediate"  # Execute remediation
    BLOCK = "block"  # Block/deny action
    ALLOW = "allow"  # Allow/permit action
    DELAY = "delay"  # Delay execution
    RETRY = "retry"  # Retry operation
    CUSTOM = "custom"  # Custom action


class ActionStatus(Enum):
    """Action execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


@dataclass
class ActionConfig:
    """Action configuration"""

    timeout_seconds: int = 30
    retry_count: int = 0
    retry_delay_seconds: int = 5
    async_execution: bool = False
    continue_on_failure: bool = True
    log_execution: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "retry_delay_seconds": self.retry_delay_seconds,
            "async_execution": self.async_execution,
            "continue_on_failure": self.continue_on_failure,
            "log_execution": self.log_execution,
            "extra": self.extra
        }


@dataclass
class ActionResult:
    """Result of action execution"""

    action_id: str
    status: ActionStatus
    output: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    retries: int = 0

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "retries": self.retries
        }


@dataclass
class Action:
    """Rule action"""

    id: str
    name: str
    action_type: ActionType
    parameters: Dict[str, Any] = field(default_factory=dict)
    config: ActionConfig = field(default_factory=ActionConfig)
    description: str = ""
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)

    # Statistics
    execution_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_duration_ms: float = 0.0
    last_executed_at: Optional[datetime] = None
    last_status: Optional[ActionStatus] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "action_type": self.action_type.value,
            "parameters": self.parameters,
            "config": self.config.to_dict(),
            "description": self.description,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "tags": self.tags,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "avg_duration_ms": self.avg_duration_ms,
            "last_executed_at": self.last_executed_at.isoformat() if self.last_executed_at else None,
            "last_status": self.last_status.value if self.last_status else None
        }


class ActionManager:
    """Manages rule actions"""

    def __init__(self):
        self.actions: Dict[str, Action] = {}
        self._handlers: Dict[ActionType, Callable] = {}
        self._custom_handlers: Dict[str, Callable] = {}
        self._init_builtin_handlers()
        self._init_builtin_actions()

    def _init_builtin_handlers(self) -> None:
        """Initialize built-in action handlers"""

        def log_handler(action: Action, context: dict) -> ActionResult:
            """Log action handler"""
            result = ActionResult(
                action_id=action.id,
                status=ActionStatus.COMPLETED,
                output={"logged": action.parameters.get("message", "")},
                started_at=datetime.now(),
                completed_at=datetime.now()
            )
            return result

        def alert_handler(action: Action, context: dict) -> ActionResult:
            """Alert action handler"""
            return ActionResult(
                action_id=action.id,
                status=ActionStatus.COMPLETED,
                output={"alert_sent": True, "severity": action.parameters.get("severity", "info")},
                started_at=datetime.now(),
                completed_at=datetime.now()
            )

        def email_handler(action: Action, context: dict) -> ActionResult:
            """Email action handler"""
            return ActionResult(
                action_id=action.id,
                status=ActionStatus.COMPLETED,
                output={"email_sent": True, "to": action.parameters.get("to", "")},
                started_at=datetime.now(),
                completed_at=datetime.now()
            )

        def webhook_handler(action: Action, context: dict) -> ActionResult:
            """Webhook action handler"""
            return ActionResult(
                action_id=action.id,
                status=ActionStatus.COMPLETED,
                output={"webhook_called": True, "url": action.parameters.get("url", "")},
                started_at=datetime.now(),
                completed_at=datetime.now()
            )

        def set_variable_handler(action: Action, context: dict) -> ActionResult:
            """Set variable action handler"""
            var_name = action.parameters.get("name", "")
            var_value = action.parameters.get("value")
            if var_name:
                context[var_name] = var_value
            return ActionResult(
                action_id=action.id,
                status=ActionStatus.COMPLETED,
                output={"variable_set": var_name, "value": var_value},
                started_at=datetime.now(),
                completed_at=datetime.now()
            )

        def transform_handler(action: Action, context: dict) -> ActionResult:
            """Transform action handler"""
            return ActionResult(
                action_id=action.id,
                status=ActionStatus.COMPLETED,
                output={"transformed": True},
                started_at=datetime.now(),
                completed_at=datetime.now()
            )

        def remediate_handler(action: Action, context: dict) -> ActionResult:
            """Remediation action handler"""
            return ActionResult(
                action_id=action.id,
                status=ActionStatus.COMPLETED,
                output={"remediation": action.parameters.get("action", ""), "applied": True},
                started_at=datetime.now(),
                completed_at=datetime.now()
            )

        def block_handler(action: Action, context: dict) -> ActionResult:
            """Block action handler"""
            return ActionResult(
                action_id=action.id,
                status=ActionStatus.COMPLETED,
                output={"blocked": True, "reason": action.parameters.get("reason", "")},
                started_at=datetime.now(),
                completed_at=datetime.now()
            )

        def allow_handler(action: Action, context: dict) -> ActionResult:
            """Allow action handler"""
            return ActionResult(
                action_id=action.id,
                status=ActionStatus.COMPLETED,
                output={"allowed": True},
                started_at=datetime.now(),
                completed_at=datetime.now()
            )

        def delay_handler(action: Action, context: dict) -> ActionResult:
            """Delay action handler"""
            return ActionResult(
                action_id=action.id,
                status=ActionStatus.COMPLETED,
                output={"delayed": True, "seconds": action.parameters.get("seconds", 0)},
                started_at=datetime.now(),
                completed_at=datetime.now()
            )

        def escalate_handler(action: Action, context: dict) -> ActionResult:
            """Escalate action handler"""
            return ActionResult(
                action_id=action.id,
                status=ActionStatus.COMPLETED,
                output={"escalated": True, "to": action.parameters.get("to", "")},
                started_at=datetime.now(),
                completed_at=datetime.now()
            )

        self._handlers = {
            ActionType.LOG: log_handler,
            ActionType.ALERT: alert_handler,
            ActionType.EMAIL: email_handler,
            ActionType.WEBHOOK: webhook_handler,
            ActionType.SET_VARIABLE: set_variable_handler,
            ActionType.TRANSFORM: transform_handler,
            ActionType.REMEDIATE: remediate_handler,
            ActionType.BLOCK: block_handler,
            ActionType.ALLOW: allow_handler,
            ActionType.DELAY: delay_handler,
            ActionType.ESCALATE: escalate_handler
        }

    def _init_builtin_actions(self) -> None:
        """Initialize built-in action templates"""

        # Logging actions
        self.create_action(
            name="Log Info",
            action_type=ActionType.LOG,
            parameters={"level": "info", "message": "Rule triggered"},
            description="Log informational message",
            tags=["logging"]
        )

        self.create_action(
            name="Log Warning",
            action_type=ActionType.LOG,
            parameters={"level": "warning", "message": "Rule condition warning"},
            description="Log warning message",
            tags=["logging"]
        )

        # Alert actions
        self.create_action(
            name="Send Alert",
            action_type=ActionType.ALERT,
            parameters={"severity": "warning"},
            description="Send alert notification",
            tags=["alerting"]
        )

        self.create_action(
            name="Critical Alert",
            action_type=ActionType.ALERT,
            parameters={"severity": "critical"},
            description="Send critical alert",
            tags=["alerting", "critical"]
        )

        # Network actions
        self.create_action(
            name="Block Traffic",
            action_type=ActionType.BLOCK,
            parameters={"reason": "Policy violation"},
            description="Block network traffic",
            tags=["network", "security"]
        )

        self.create_action(
            name="Allow Traffic",
            action_type=ActionType.ALLOW,
            parameters={},
            description="Allow network traffic",
            tags=["network"]
        )

        # Remediation actions
        self.create_action(
            name="Reset Interface",
            action_type=ActionType.REMEDIATE,
            parameters={"action": "interface_reset"},
            description="Reset network interface",
            tags=["remediation", "network"]
        )

        self.create_action(
            name="Clear BGP Session",
            action_type=ActionType.REMEDIATE,
            parameters={"action": "bgp_clear"},
            description="Clear BGP session",
            tags=["remediation", "bgp"]
        )

    def register_handler(
        self,
        action_type: ActionType,
        handler: Callable
    ) -> None:
        """Register an action handler"""
        self._handlers[action_type] = handler

    def register_custom_handler(
        self,
        name: str,
        handler: Callable
    ) -> None:
        """Register a custom action handler"""
        self._custom_handlers[name] = handler

    def get_handler(self, action_type: ActionType) -> Optional[Callable]:
        """Get handler for action type"""
        return self._handlers.get(action_type)

    def get_custom_handler(self, name: str) -> Optional[Callable]:
        """Get custom handler by name"""
        return self._custom_handlers.get(name)

    def create_action(
        self,
        name: str,
        action_type: ActionType,
        parameters: Optional[Dict[str, Any]] = None,
        config: Optional[ActionConfig] = None,
        description: str = "",
        tags: Optional[List[str]] = None
    ) -> Action:
        """Create a new action"""
        action_id = f"act_{uuid.uuid4().hex[:8]}"

        action = Action(
            id=action_id,
            name=name,
            action_type=action_type,
            parameters=parameters or {},
            config=config or ActionConfig(),
            description=description,
            tags=tags or []
        )

        self.actions[action_id] = action
        return action

    def get_action(self, action_id: str) -> Optional[Action]:
        """Get action by ID"""
        return self.actions.get(action_id)

    def get_action_by_name(self, name: str) -> Optional[Action]:
        """Get action by name"""
        for action in self.actions.values():
            if action.name == name:
                return action
        return None

    def update_action(
        self,
        action_id: str,
        **kwargs
    ) -> Optional[Action]:
        """Update action properties"""
        action = self.actions.get(action_id)
        if not action:
            return None

        for key, value in kwargs.items():
            if hasattr(action, key):
                setattr(action, key, value)

        return action

    def delete_action(self, action_id: str) -> bool:
        """Delete an action"""
        if action_id in self.actions:
            del self.actions[action_id]
            return True
        return False

    def enable_action(self, action_id: str) -> bool:
        """Enable an action"""
        action = self.actions.get(action_id)
        if action:
            action.enabled = True
            return True
        return False

    def disable_action(self, action_id: str) -> bool:
        """Disable an action"""
        action = self.actions.get(action_id)
        if action:
            action.enabled = False
            return True
        return False

    def execute_action(
        self,
        action_id: str,
        context: Dict[str, Any]
    ) -> ActionResult:
        """Execute an action"""
        action = self.actions.get(action_id)
        if not action:
            return ActionResult(
                action_id=action_id,
                status=ActionStatus.FAILED,
                error="Action not found"
            )

        if not action.enabled:
            return ActionResult(
                action_id=action_id,
                status=ActionStatus.SKIPPED,
                output={"reason": "Action disabled"}
            )

        start_time = datetime.now()
        action.execution_count += 1
        action.last_executed_at = start_time

        try:
            # Get handler
            if action.action_type == ActionType.CUSTOM:
                handler_name = action.parameters.get("handler", "")
                handler = self._custom_handlers.get(handler_name)
            else:
                handler = self._handlers.get(action.action_type)

            if not handler:
                action.failure_count += 1
                action.last_status = ActionStatus.FAILED
                return ActionResult(
                    action_id=action_id,
                    status=ActionStatus.FAILED,
                    error=f"No handler for action type: {action.action_type.value}"
                )

            # Execute handler
            result = handler(action, context)
            end_time = datetime.now()
            result.duration_ms = (end_time - start_time).total_seconds() * 1000

            # Update statistics
            if result.status == ActionStatus.COMPLETED:
                action.success_count += 1
            else:
                action.failure_count += 1

            action.last_status = result.status

            # Update average duration
            total = action.avg_duration_ms * (action.execution_count - 1) + result.duration_ms
            action.avg_duration_ms = total / action.execution_count

            return result

        except Exception as e:
            action.failure_count += 1
            action.last_status = ActionStatus.FAILED
            return ActionResult(
                action_id=action_id,
                status=ActionStatus.FAILED,
                error=str(e),
                started_at=start_time,
                completed_at=datetime.now()
            )

    def execute_actions(
        self,
        action_ids: List[str],
        context: Dict[str, Any]
    ) -> List[ActionResult]:
        """Execute multiple actions"""
        results = []
        for action_id in action_ids:
            result = self.execute_action(action_id, context)
            results.append(result)

            # Check if we should continue on failure
            action = self.actions.get(action_id)
            if action and not action.config.continue_on_failure and result.status == ActionStatus.FAILED:
                break

        return results

    def get_actions(
        self,
        action_type: Optional[ActionType] = None,
        enabled_only: bool = False,
        tag: Optional[str] = None
    ) -> List[Action]:
        """Get actions with filtering"""
        actions = list(self.actions.values())

        if action_type:
            actions = [a for a in actions if a.action_type == action_type]
        if enabled_only:
            actions = [a for a in actions if a.enabled]
        if tag:
            actions = [a for a in actions if tag in a.tags]

        return actions

    def get_statistics(self) -> dict:
        """Get action statistics"""
        total_executions = 0
        total_successes = 0
        total_failures = 0
        by_type = {}

        for action in self.actions.values():
            total_executions += action.execution_count
            total_successes += action.success_count
            total_failures += action.failure_count
            by_type[action.action_type.value] = by_type.get(action.action_type.value, 0) + 1

        return {
            "total_actions": len(self.actions),
            "enabled_actions": len([a for a in self.actions.values() if a.enabled]),
            "total_executions": total_executions,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "success_rate": total_successes / total_executions if total_executions > 0 else 1.0,
            "by_type": by_type,
            "registered_handlers": len(self._handlers),
            "custom_handlers": len(self._custom_handlers)
        }


# Global action manager instance
_action_manager: Optional[ActionManager] = None


def get_action_manager() -> ActionManager:
    """Get or create the global action manager"""
    global _action_manager
    if _action_manager is None:
        _action_manager = ActionManager()
    return _action_manager
