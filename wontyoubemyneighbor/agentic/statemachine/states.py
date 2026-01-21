"""
State Definitions

Provides:
- State data structures
- State configuration
- State management
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from enum import Enum


class StateType(Enum):
    """Types of states"""
    INITIAL = "initial"  # Starting state
    NORMAL = "normal"  # Regular state
    FINAL = "final"  # End state
    COMPOSITE = "composite"  # Contains sub-states
    HISTORY = "history"  # Remember last active sub-state
    PARALLEL = "parallel"  # Multiple active sub-states
    CHOICE = "choice"  # Decision point
    JUNCTION = "junction"  # Merge point


@dataclass
class StateConfig:
    """State configuration"""

    timeout_seconds: int = 0  # 0 = no timeout
    max_retries: int = 3
    retry_delay_seconds: int = 1
    on_enter_hooks: List[str] = field(default_factory=list)
    on_exit_hooks: List[str] = field(default_factory=list)
    on_timeout_hooks: List[str] = field(default_factory=list)
    allowed_events: List[str] = field(default_factory=list)
    blocked_events: List[str] = field(default_factory=list)
    data_schema: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "retry_delay_seconds": self.retry_delay_seconds,
            "on_enter_hooks": self.on_enter_hooks,
            "on_exit_hooks": self.on_exit_hooks,
            "on_timeout_hooks": self.on_timeout_hooks,
            "allowed_events": self.allowed_events,
            "blocked_events": self.blocked_events,
            "data_schema": self.data_schema,
            "extra": self.extra
        }


@dataclass
class State:
    """State definition"""

    id: str
    name: str
    state_type: StateType
    description: str = ""
    config: StateConfig = field(default_factory=StateConfig)
    parent_id: Optional[str] = None  # For composite states
    child_ids: List[str] = field(default_factory=list)  # Sub-states
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)

    # Callbacks (stored as names for serialization)
    on_enter: Optional[str] = None
    on_exit: Optional[str] = None
    on_activity: Optional[str] = None

    # Statistics
    entry_count: int = 0
    exit_count: int = 0
    total_time_seconds: float = 0.0
    last_entered_at: Optional[datetime] = None
    last_exited_at: Optional[datetime] = None

    def is_initial(self) -> bool:
        return self.state_type == StateType.INITIAL

    def is_final(self) -> bool:
        return self.state_type == StateType.FINAL

    def is_composite(self) -> bool:
        return self.state_type == StateType.COMPOSITE

    def has_parent(self) -> bool:
        return self.parent_id is not None

    def has_children(self) -> bool:
        return len(self.child_ids) > 0

    def allows_event(self, event: str) -> bool:
        """Check if state allows an event"""
        if self.config.blocked_events and event in self.config.blocked_events:
            return False
        if self.config.allowed_events and event not in self.config.allowed_events:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "state_type": self.state_type.value,
            "description": self.description,
            "config": self.config.to_dict(),
            "parent_id": self.parent_id,
            "child_ids": self.child_ids,
            "data": self.data,
            "created_at": self.created_at.isoformat(),
            "tags": self.tags,
            "on_enter": self.on_enter,
            "on_exit": self.on_exit,
            "on_activity": self.on_activity,
            "entry_count": self.entry_count,
            "exit_count": self.exit_count,
            "total_time_seconds": self.total_time_seconds,
            "last_entered_at": self.last_entered_at.isoformat() if self.last_entered_at else None,
            "last_exited_at": self.last_exited_at.isoformat() if self.last_exited_at else None
        }


class StateManager:
    """Manages state definitions"""

    def __init__(self):
        self.states: Dict[str, State] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._init_builtin_callbacks()

    def _init_builtin_callbacks(self) -> None:
        """Initialize built-in state callbacks"""

        def log_enter(state: State, context: dict) -> None:
            """Log state entry"""
            pass  # Simulated logging

        def log_exit(state: State, context: dict) -> None:
            """Log state exit"""
            pass  # Simulated logging

        def validate_data(state: State, context: dict) -> bool:
            """Validate state data against schema"""
            return True  # Simulated validation

        def emit_event(state: State, context: dict) -> None:
            """Emit state change event"""
            pass  # Simulated event emission

        def store_history(state: State, context: dict) -> None:
            """Store state in history"""
            pass  # Simulated history storage

        def notify_observers(state: State, context: dict) -> None:
            """Notify state observers"""
            pass  # Simulated notification

        def checkpoint_state(state: State, context: dict) -> None:
            """Create state checkpoint"""
            pass  # Simulated checkpoint

        def cleanup_resources(state: State, context: dict) -> None:
            """Clean up state resources"""
            pass  # Simulated cleanup

        self._callbacks = {
            "log_enter": log_enter,
            "log_exit": log_exit,
            "validate_data": validate_data,
            "emit_event": emit_event,
            "store_history": store_history,
            "notify_observers": notify_observers,
            "checkpoint_state": checkpoint_state,
            "cleanup_resources": cleanup_resources
        }

    def register_callback(self, name: str, callback: Callable) -> None:
        """Register a state callback"""
        self._callbacks[name] = callback

    def get_callback(self, name: str) -> Optional[Callable]:
        """Get callback by name"""
        return self._callbacks.get(name)

    def get_available_callbacks(self) -> List[str]:
        """Get list of available callbacks"""
        return list(self._callbacks.keys())

    def create_state(
        self,
        name: str,
        state_type: StateType,
        description: str = "",
        config: Optional[StateConfig] = None,
        parent_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        on_enter: Optional[str] = None,
        on_exit: Optional[str] = None,
        on_activity: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> State:
        """Create a new state"""
        state_id = f"state_{uuid.uuid4().hex[:8]}"

        state = State(
            id=state_id,
            name=name,
            state_type=state_type,
            description=description,
            config=config or StateConfig(),
            parent_id=parent_id,
            data=data or {},
            on_enter=on_enter,
            on_exit=on_exit,
            on_activity=on_activity,
            tags=tags or []
        )

        self.states[state_id] = state

        # Add to parent's children if applicable
        if parent_id and parent_id in self.states:
            self.states[parent_id].child_ids.append(state_id)

        return state

    def get_state(self, state_id: str) -> Optional[State]:
        """Get state by ID"""
        return self.states.get(state_id)

    def get_state_by_name(self, name: str) -> Optional[State]:
        """Get state by name"""
        for state in self.states.values():
            if state.name == name:
                return state
        return None

    def update_state(
        self,
        state_id: str,
        **kwargs
    ) -> Optional[State]:
        """Update state properties"""
        state = self.states.get(state_id)
        if not state:
            return None

        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)

        return state

    def delete_state(self, state_id: str) -> bool:
        """Delete a state"""
        state = self.states.get(state_id)
        if not state:
            return False

        # Remove from parent's children
        if state.parent_id and state.parent_id in self.states:
            parent = self.states[state.parent_id]
            if state_id in parent.child_ids:
                parent.child_ids.remove(state_id)

        # Delete children recursively
        for child_id in state.child_ids[:]:
            self.delete_state(child_id)

        del self.states[state_id]
        return True

    def add_child_state(
        self,
        parent_id: str,
        child_id: str
    ) -> bool:
        """Add a child state to a parent"""
        parent = self.states.get(parent_id)
        child = self.states.get(child_id)

        if not parent or not child:
            return False

        if child_id not in parent.child_ids:
            parent.child_ids.append(child_id)
        child.parent_id = parent_id

        return True

    def remove_child_state(
        self,
        parent_id: str,
        child_id: str
    ) -> bool:
        """Remove a child state from a parent"""
        parent = self.states.get(parent_id)
        child = self.states.get(child_id)

        if not parent or not child:
            return False

        if child_id in parent.child_ids:
            parent.child_ids.remove(child_id)
        child.parent_id = None

        return True

    def execute_callback(
        self,
        callback_name: str,
        state: State,
        context: Dict[str, Any]
    ) -> Any:
        """Execute a state callback"""
        callback = self._callbacks.get(callback_name)
        if callback:
            return callback(state, context)
        return None

    def enter_state(
        self,
        state_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Execute state entry logic"""
        state = self.states.get(state_id)
        if not state:
            return False

        context = context or {}
        state.entry_count += 1
        state.last_entered_at = datetime.now()

        # Execute on_enter callback
        if state.on_enter:
            self.execute_callback(state.on_enter, state, context)

        # Execute enter hooks
        for hook in state.config.on_enter_hooks:
            self.execute_callback(hook, state, context)

        return True

    def exit_state(
        self,
        state_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Execute state exit logic"""
        state = self.states.get(state_id)
        if not state:
            return False

        context = context or {}
        state.exit_count += 1
        state.last_exited_at = datetime.now()

        # Calculate time in state
        if state.last_entered_at:
            duration = (datetime.now() - state.last_entered_at).total_seconds()
            state.total_time_seconds += duration

        # Execute on_exit callback
        if state.on_exit:
            self.execute_callback(state.on_exit, state, context)

        # Execute exit hooks
        for hook in state.config.on_exit_hooks:
            self.execute_callback(hook, state, context)

        return True

    def get_states(
        self,
        state_type: Optional[StateType] = None,
        parent_id: Optional[str] = None,
        tag: Optional[str] = None
    ) -> List[State]:
        """Get states with filtering"""
        states = list(self.states.values())

        if state_type:
            states = [s for s in states if s.state_type == state_type]
        if parent_id is not None:
            states = [s for s in states if s.parent_id == parent_id]
        if tag:
            states = [s for s in states if tag in s.tags]

        return states

    def get_initial_states(self) -> List[State]:
        """Get all initial states"""
        return [s for s in self.states.values() if s.is_initial()]

    def get_final_states(self) -> List[State]:
        """Get all final states"""
        return [s for s in self.states.values() if s.is_final()]

    def get_statistics(self) -> dict:
        """Get state statistics"""
        total_entries = 0
        total_exits = 0
        total_time = 0.0
        by_type = {}

        for state in self.states.values():
            total_entries += state.entry_count
            total_exits += state.exit_count
            total_time += state.total_time_seconds
            by_type[state.state_type.value] = by_type.get(state.state_type.value, 0) + 1

        return {
            "total_states": len(self.states),
            "initial_states": len(self.get_initial_states()),
            "final_states": len(self.get_final_states()),
            "total_entries": total_entries,
            "total_exits": total_exits,
            "total_time_seconds": total_time,
            "by_type": by_type,
            "available_callbacks": len(self._callbacks)
        }


# Global state manager instance
_state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    """Get or create the global state manager"""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager
