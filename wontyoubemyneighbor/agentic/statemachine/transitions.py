"""
Transition Definitions

Provides:
- Transition data structures
- Transition conditions
- Transition management
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from enum import Enum


class TransitionType(Enum):
    """Types of transitions"""
    EXTERNAL = "external"  # Exit source, enter target
    INTERNAL = "internal"  # Stay in same state
    LOCAL = "local"  # Stay in composite state
    AUTO = "auto"  # Automatic (no trigger required)
    CONDITIONAL = "conditional"  # Based on conditions
    TIMEOUT = "timeout"  # Triggered by timeout


class ConditionOperator(Enum):
    """Condition operators"""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_EQUAL = "greater_equal"
    LESS_EQUAL = "less_equal"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    IN = "in"
    NOT_IN = "not_in"
    MATCHES = "matches"  # Regex


@dataclass
class TransitionCondition:
    """Transition condition"""

    id: str
    name: str
    field: str  # Field to evaluate
    operator: ConditionOperator
    value: Any = None  # Value to compare against
    negate: bool = False
    description: str = ""

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Evaluate condition against context"""
        field_value = context.get(self.field)

        result = False

        if self.operator == ConditionOperator.EQUALS:
            result = field_value == self.value
        elif self.operator == ConditionOperator.NOT_EQUALS:
            result = field_value != self.value
        elif self.operator == ConditionOperator.GREATER_THAN:
            result = field_value > self.value if field_value is not None else False
        elif self.operator == ConditionOperator.LESS_THAN:
            result = field_value < self.value if field_value is not None else False
        elif self.operator == ConditionOperator.GREATER_EQUAL:
            result = field_value >= self.value if field_value is not None else False
        elif self.operator == ConditionOperator.LESS_EQUAL:
            result = field_value <= self.value if field_value is not None else False
        elif self.operator == ConditionOperator.CONTAINS:
            result = self.value in field_value if field_value is not None else False
        elif self.operator == ConditionOperator.NOT_CONTAINS:
            result = self.value not in field_value if field_value is not None else True
        elif self.operator == ConditionOperator.STARTS_WITH:
            result = str(field_value).startswith(str(self.value)) if field_value is not None else False
        elif self.operator == ConditionOperator.ENDS_WITH:
            result = str(field_value).endswith(str(self.value)) if field_value is not None else False
        elif self.operator == ConditionOperator.IS_NULL:
            result = field_value is None
        elif self.operator == ConditionOperator.IS_NOT_NULL:
            result = field_value is not None
        elif self.operator == ConditionOperator.IN:
            result = field_value in self.value if isinstance(self.value, (list, tuple, set)) else False
        elif self.operator == ConditionOperator.NOT_IN:
            result = field_value not in self.value if isinstance(self.value, (list, tuple, set)) else True
        elif self.operator == ConditionOperator.MATCHES:
            import re
            result = bool(re.match(str(self.value), str(field_value))) if field_value is not None else False

        return not result if self.negate else result

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "field": self.field,
            "operator": self.operator.value,
            "value": self.value,
            "negate": self.negate,
            "description": self.description
        }


@dataclass
class TransitionConfig:
    """Transition configuration"""

    priority: int = 0  # Higher = evaluated first
    guard_timeout_ms: int = 5000  # Timeout for guard evaluation
    action_timeout_ms: int = 30000  # Timeout for action execution
    retry_on_failure: bool = False
    retry_count: int = 3
    retry_delay_ms: int = 1000
    log_transition: bool = True
    emit_events: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "priority": self.priority,
            "guard_timeout_ms": self.guard_timeout_ms,
            "action_timeout_ms": self.action_timeout_ms,
            "retry_on_failure": self.retry_on_failure,
            "retry_count": self.retry_count,
            "retry_delay_ms": self.retry_delay_ms,
            "log_transition": self.log_transition,
            "emit_events": self.emit_events,
            "extra": self.extra
        }


@dataclass
class Transition:
    """Transition definition"""

    id: str
    name: str
    source_id: str  # Source state ID
    target_id: str  # Target state ID
    transition_type: TransitionType
    trigger: Optional[str] = None  # Event that triggers transition
    description: str = ""
    config: TransitionConfig = field(default_factory=TransitionConfig)
    conditions: List[TransitionCondition] = field(default_factory=list)
    condition_logic: str = "all"  # "all", "any", "none"
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)

    # Callback names
    guard: Optional[str] = None  # Guard condition
    action: Optional[str] = None  # Action on transition
    before_action: Optional[str] = None
    after_action: Optional[str] = None

    # Statistics
    execution_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    last_executed_at: Optional[datetime] = None
    avg_execution_time_ms: float = 0.0

    def is_auto(self) -> bool:
        return self.transition_type == TransitionType.AUTO

    def is_internal(self) -> bool:
        return self.transition_type == TransitionType.INTERNAL

    def evaluate_conditions(self, context: Dict[str, Any]) -> bool:
        """Evaluate all conditions"""
        if not self.conditions:
            return True

        results = [c.evaluate(context) for c in self.conditions]

        if self.condition_logic == "all":
            return all(results)
        elif self.condition_logic == "any":
            return any(results)
        elif self.condition_logic == "none":
            return not any(results)

        return True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "transition_type": self.transition_type.value,
            "trigger": self.trigger,
            "description": self.description,
            "config": self.config.to_dict(),
            "conditions": [c.to_dict() for c in self.conditions],
            "condition_logic": self.condition_logic,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "tags": self.tags,
            "guard": self.guard,
            "action": self.action,
            "before_action": self.before_action,
            "after_action": self.after_action,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_executed_at": self.last_executed_at.isoformat() if self.last_executed_at else None,
            "avg_execution_time_ms": self.avg_execution_time_ms
        }


class TransitionManager:
    """Manages transition definitions"""

    def __init__(self):
        self.transitions: Dict[str, Transition] = {}
        self.conditions: Dict[str, TransitionCondition] = {}
        self._guards: Dict[str, Callable] = {}
        self._actions: Dict[str, Callable] = {}
        self._init_builtin_guards()
        self._init_builtin_actions()

    def _init_builtin_guards(self) -> None:
        """Initialize built-in guard functions"""

        def always_true(context: dict) -> bool:
            return True

        def always_false(context: dict) -> bool:
            return False

        def has_data(context: dict) -> bool:
            return bool(context.get("data"))

        def is_authenticated(context: dict) -> bool:
            return context.get("authenticated", False)

        def has_permission(context: dict) -> bool:
            return context.get("has_permission", False)

        def is_valid(context: dict) -> bool:
            return context.get("valid", False)

        def has_resources(context: dict) -> bool:
            return context.get("has_resources", False)

        def is_ready(context: dict) -> bool:
            return context.get("ready", False)

        self._guards = {
            "always_true": always_true,
            "always_false": always_false,
            "has_data": has_data,
            "is_authenticated": is_authenticated,
            "has_permission": has_permission,
            "is_valid": is_valid,
            "has_resources": has_resources,
            "is_ready": is_ready
        }

    def _init_builtin_actions(self) -> None:
        """Initialize built-in action functions"""

        def log_transition(context: dict) -> None:
            pass  # Simulated logging

        def emit_event(context: dict) -> None:
            pass  # Simulated event emission

        def notify_observers(context: dict) -> None:
            pass  # Simulated notification

        def update_metrics(context: dict) -> None:
            pass  # Simulated metrics update

        def store_history(context: dict) -> None:
            pass  # Simulated history storage

        def validate_state(context: dict) -> None:
            pass  # Simulated validation

        def cleanup_source(context: dict) -> None:
            pass  # Simulated cleanup

        def initialize_target(context: dict) -> None:
            pass  # Simulated initialization

        self._actions = {
            "log_transition": log_transition,
            "emit_event": emit_event,
            "notify_observers": notify_observers,
            "update_metrics": update_metrics,
            "store_history": store_history,
            "validate_state": validate_state,
            "cleanup_source": cleanup_source,
            "initialize_target": initialize_target
        }

    def register_guard(self, name: str, guard: Callable) -> None:
        """Register a guard function"""
        self._guards[name] = guard

    def register_action(self, name: str, action: Callable) -> None:
        """Register an action function"""
        self._actions[name] = action

    def get_guard(self, name: str) -> Optional[Callable]:
        """Get guard by name"""
        return self._guards.get(name)

    def get_action(self, name: str) -> Optional[Callable]:
        """Get action by name"""
        return self._actions.get(name)

    def get_available_guards(self) -> List[str]:
        """Get list of available guards"""
        return list(self._guards.keys())

    def get_available_actions(self) -> List[str]:
        """Get list of available actions"""
        return list(self._actions.keys())

    def create_condition(
        self,
        name: str,
        field: str,
        operator: ConditionOperator,
        value: Any = None,
        negate: bool = False,
        description: str = ""
    ) -> TransitionCondition:
        """Create a transition condition"""
        condition_id = f"cond_{uuid.uuid4().hex[:8]}"

        condition = TransitionCondition(
            id=condition_id,
            name=name,
            field=field,
            operator=operator,
            value=value,
            negate=negate,
            description=description
        )

        self.conditions[condition_id] = condition
        return condition

    def get_condition(self, condition_id: str) -> Optional[TransitionCondition]:
        """Get condition by ID"""
        return self.conditions.get(condition_id)

    def create_transition(
        self,
        name: str,
        source_id: str,
        target_id: str,
        transition_type: TransitionType,
        trigger: Optional[str] = None,
        description: str = "",
        config: Optional[TransitionConfig] = None,
        conditions: Optional[List[TransitionCondition]] = None,
        condition_logic: str = "all",
        guard: Optional[str] = None,
        action: Optional[str] = None,
        before_action: Optional[str] = None,
        after_action: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Transition:
        """Create a new transition"""
        transition_id = f"trans_{uuid.uuid4().hex[:8]}"

        transition = Transition(
            id=transition_id,
            name=name,
            source_id=source_id,
            target_id=target_id,
            transition_type=transition_type,
            trigger=trigger,
            description=description,
            config=config or TransitionConfig(),
            conditions=conditions or [],
            condition_logic=condition_logic,
            guard=guard,
            action=action,
            before_action=before_action,
            after_action=after_action,
            tags=tags or []
        )

        self.transitions[transition_id] = transition
        return transition

    def get_transition(self, transition_id: str) -> Optional[Transition]:
        """Get transition by ID"""
        return self.transitions.get(transition_id)

    def get_transition_by_name(self, name: str) -> Optional[Transition]:
        """Get transition by name"""
        for transition in self.transitions.values():
            if transition.name == name:
                return transition
        return None

    def update_transition(
        self,
        transition_id: str,
        **kwargs
    ) -> Optional[Transition]:
        """Update transition properties"""
        transition = self.transitions.get(transition_id)
        if not transition:
            return None

        for key, value in kwargs.items():
            if hasattr(transition, key):
                setattr(transition, key, value)

        return transition

    def delete_transition(self, transition_id: str) -> bool:
        """Delete a transition"""
        if transition_id in self.transitions:
            del self.transitions[transition_id]
            return True
        return False

    def enable_transition(self, transition_id: str) -> bool:
        """Enable a transition"""
        transition = self.transitions.get(transition_id)
        if transition:
            transition.enabled = True
            return True
        return False

    def disable_transition(self, transition_id: str) -> bool:
        """Disable a transition"""
        transition = self.transitions.get(transition_id)
        if transition:
            transition.enabled = False
            return True
        return False

    def add_condition(
        self,
        transition_id: str,
        condition: TransitionCondition
    ) -> bool:
        """Add condition to transition"""
        transition = self.transitions.get(transition_id)
        if not transition:
            return False

        transition.conditions.append(condition)
        return True

    def remove_condition(
        self,
        transition_id: str,
        condition_id: str
    ) -> bool:
        """Remove condition from transition"""
        transition = self.transitions.get(transition_id)
        if not transition:
            return False

        transition.conditions = [
            c for c in transition.conditions
            if c.id != condition_id
        ]
        return True

    def evaluate_guard(
        self,
        transition: Transition,
        context: Dict[str, Any]
    ) -> bool:
        """Evaluate transition guard"""
        if not transition.guard:
            return True

        guard = self._guards.get(transition.guard)
        if guard:
            return guard(context)

        return True

    def execute_action(
        self,
        action_name: str,
        context: Dict[str, Any]
    ) -> bool:
        """Execute a transition action"""
        action = self._actions.get(action_name)
        if action:
            action(context)
            return True
        return False

    def can_transition(
        self,
        transition: Transition,
        context: Dict[str, Any]
    ) -> bool:
        """Check if transition can be executed"""
        if not transition.enabled:
            return False

        # Evaluate conditions
        if not transition.evaluate_conditions(context):
            return False

        # Evaluate guard
        if not self.evaluate_guard(transition, context):
            return False

        return True

    def get_transitions_from(
        self,
        source_id: str,
        trigger: Optional[str] = None,
        enabled_only: bool = True
    ) -> List[Transition]:
        """Get transitions from a source state"""
        transitions = [
            t for t in self.transitions.values()
            if t.source_id == source_id
        ]

        if trigger:
            transitions = [t for t in transitions if t.trigger == trigger]
        if enabled_only:
            transitions = [t for t in transitions if t.enabled]

        # Sort by priority
        transitions.sort(key=lambda t: t.config.priority, reverse=True)

        return transitions

    def get_transitions_to(
        self,
        target_id: str,
        enabled_only: bool = True
    ) -> List[Transition]:
        """Get transitions to a target state"""
        transitions = [
            t for t in self.transitions.values()
            if t.target_id == target_id
        ]

        if enabled_only:
            transitions = [t for t in transitions if t.enabled]

        return transitions

    def get_transitions(
        self,
        transition_type: Optional[TransitionType] = None,
        trigger: Optional[str] = None,
        enabled_only: bool = False,
        tag: Optional[str] = None
    ) -> List[Transition]:
        """Get transitions with filtering"""
        transitions = list(self.transitions.values())

        if transition_type:
            transitions = [t for t in transitions if t.transition_type == transition_type]
        if trigger:
            transitions = [t for t in transitions if t.trigger == trigger]
        if enabled_only:
            transitions = [t for t in transitions if t.enabled]
        if tag:
            transitions = [t for t in transitions if tag in t.tags]

        return transitions

    def get_statistics(self) -> dict:
        """Get transition statistics"""
        total_executions = 0
        total_successes = 0
        total_failures = 0
        by_type = {}

        for transition in self.transitions.values():
            total_executions += transition.execution_count
            total_successes += transition.success_count
            total_failures += transition.failure_count
            by_type[transition.transition_type.value] = by_type.get(transition.transition_type.value, 0) + 1

        return {
            "total_transitions": len(self.transitions),
            "enabled_transitions": len([t for t in self.transitions.values() if t.enabled]),
            "total_conditions": len(self.conditions),
            "total_executions": total_executions,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "success_rate": total_successes / total_executions if total_executions > 0 else 1.0,
            "by_type": by_type,
            "available_guards": len(self._guards),
            "available_actions": len(self._actions)
        }


# Global transition manager instance
_transition_manager: Optional[TransitionManager] = None


def get_transition_manager() -> TransitionManager:
    """Get or create the global transition manager"""
    global _transition_manager
    if _transition_manager is None:
        _transition_manager = TransitionManager()
    return _transition_manager
