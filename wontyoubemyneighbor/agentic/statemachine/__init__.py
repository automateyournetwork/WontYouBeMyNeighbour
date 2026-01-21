"""
State Machine Framework

Provides:
- State definitions
- Transition management
- State machine execution
- Event-driven state changes
"""

from .states import (
    State,
    StateType,
    StateConfig,
    StateManager,
    get_state_manager
)
from .transitions import (
    Transition,
    TransitionType,
    TransitionConfig,
    TransitionCondition,
    ConditionOperator,
    TransitionManager,
    get_transition_manager
)
from .machine import (
    StateMachine,
    StateMachineConfig,
    StateMachineInstance,
    StateMachineManager,
    MachineStatus,
    get_state_machine_manager
)

__all__ = [
    # States
    "State",
    "StateType",
    "StateConfig",
    "StateManager",
    "get_state_manager",
    # Transitions
    "Transition",
    "TransitionType",
    "TransitionConfig",
    "TransitionCondition",
    "ConditionOperator",
    "TransitionManager",
    "get_transition_manager",
    # Machine
    "StateMachine",
    "StateMachineConfig",
    "StateMachineInstance",
    "StateMachineManager",
    "MachineStatus",
    "get_state_machine_manager"
]
