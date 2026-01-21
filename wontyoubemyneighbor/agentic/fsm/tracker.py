"""
State Tracker - Tracks protocol state machine transitions

Tracks:
- OSPF neighbor states (Down -> Init -> 2-Way -> ExStart -> Exchange -> Loading -> Full)
- BGP FSM states (Idle -> Connect -> Active -> OpenSent -> OpenConfirm -> Established)
- IS-IS adjacency states (Down -> Initializing -> Up)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict

logger = logging.getLogger("StateTracker")


class StateMachineType(Enum):
    """Types of protocol state machines"""
    OSPF_NEIGHBOR = "ospf_neighbor"
    BGP_FSM = "bgp_fsm"
    ISIS_ADJACENCY = "isis_adjacency"
    LDP_SESSION = "ldp_session"
    BFD_SESSION = "bfd_session"


class OSPFNeighborState(Enum):
    """OSPF neighbor states (RFC 2328)"""
    DOWN = "Down"
    ATTEMPT = "Attempt"
    INIT = "Init"
    TWO_WAY = "2-Way"
    EXSTART = "ExStart"
    EXCHANGE = "Exchange"
    LOADING = "Loading"
    FULL = "Full"


class BGPState(Enum):
    """BGP FSM states (RFC 4271)"""
    IDLE = "Idle"
    CONNECT = "Connect"
    ACTIVE = "Active"
    OPEN_SENT = "OpenSent"
    OPEN_CONFIRM = "OpenConfirm"
    ESTABLISHED = "Established"


class ISISAdjacencyState(Enum):
    """IS-IS adjacency states"""
    DOWN = "Down"
    INITIALIZING = "Initializing"
    UP = "Up"


@dataclass
class ProtocolState:
    """
    Current state of a protocol instance

    Attributes:
        state_id: Unique identifier
        machine_type: Type of state machine
        instance_id: Protocol instance ID (e.g., neighbor router ID)
        agent_id: Agent this state belongs to
        current_state: Current state value
        previous_state: Previous state value
        state_entered_at: When current state was entered
        transition_count: Number of transitions
        is_stable: Whether state is considered stable
    """
    state_id: str
    machine_type: StateMachineType
    instance_id: str
    agent_id: str
    current_state: str
    previous_state: Optional[str] = None
    state_entered_at: datetime = field(default_factory=datetime.now)
    transition_count: int = 0
    is_stable: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def time_in_state(self) -> timedelta:
        """Calculate time spent in current state"""
        return datetime.now() - self.state_entered_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_id": self.state_id,
            "machine_type": self.machine_type.value,
            "instance_id": self.instance_id,
            "agent_id": self.agent_id,
            "current_state": self.current_state,
            "previous_state": self.previous_state,
            "state_entered_at": self.state_entered_at.isoformat(),
            "time_in_state_seconds": self.time_in_state.total_seconds(),
            "transition_count": self.transition_count,
            "is_stable": self.is_stable,
            "metadata": self.metadata
        }


@dataclass
class StateTransition:
    """
    Record of a state transition

    Attributes:
        transition_id: Unique identifier
        state_id: Related protocol state ID
        from_state: State before transition
        to_state: State after transition
        trigger: What triggered the transition
        timestamp: When transition occurred
        duration_ms: How long in previous state
    """
    transition_id: str
    state_id: str
    from_state: str
    to_state: str
    trigger: str
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "state_id": self.state_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "trigger": self.trigger,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "metadata": self.metadata
        }


class StateTracker:
    """
    Tracks protocol state machines and their transitions
    """

    def __init__(self, history_limit: int = 1000):
        """
        Initialize state tracker

        Args:
            history_limit: Maximum transitions to keep in history
        """
        self._states: Dict[str, ProtocolState] = {}
        self._transitions: List[StateTransition] = []
        self._history_limit = history_limit
        self._state_counter = 0
        self._transition_counter = 0

        # Define stable states for each protocol
        self._stable_states = {
            StateMachineType.OSPF_NEIGHBOR: {OSPFNeighborState.FULL.value, OSPFNeighborState.TWO_WAY.value},
            StateMachineType.BGP_FSM: {BGPState.ESTABLISHED.value},
            StateMachineType.ISIS_ADJACENCY: {ISISAdjacencyState.UP.value},
            StateMachineType.LDP_SESSION: {"Operational"},
            StateMachineType.BFD_SESSION: {"Up"}
        }

        # Define state order for visualization
        self._state_order = {
            StateMachineType.OSPF_NEIGHBOR: [
                OSPFNeighborState.DOWN.value,
                OSPFNeighborState.ATTEMPT.value,
                OSPFNeighborState.INIT.value,
                OSPFNeighborState.TWO_WAY.value,
                OSPFNeighborState.EXSTART.value,
                OSPFNeighborState.EXCHANGE.value,
                OSPFNeighborState.LOADING.value,
                OSPFNeighborState.FULL.value
            ],
            StateMachineType.BGP_FSM: [
                BGPState.IDLE.value,
                BGPState.CONNECT.value,
                BGPState.ACTIVE.value,
                BGPState.OPEN_SENT.value,
                BGPState.OPEN_CONFIRM.value,
                BGPState.ESTABLISHED.value
            ],
            StateMachineType.ISIS_ADJACENCY: [
                ISISAdjacencyState.DOWN.value,
                ISISAdjacencyState.INITIALIZING.value,
                ISISAdjacencyState.UP.value
            ]
        }

    def _generate_state_id(self) -> str:
        """Generate unique state ID"""
        self._state_counter += 1
        return f"state-{self._state_counter:06d}"

    def _generate_transition_id(self) -> str:
        """Generate unique transition ID"""
        self._transition_counter += 1
        return f"trans-{self._transition_counter:06d}"

    def register_state(
        self,
        machine_type: StateMachineType,
        instance_id: str,
        agent_id: str,
        initial_state: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ProtocolState:
        """
        Register a new protocol state machine instance

        Args:
            machine_type: Type of state machine
            instance_id: Instance identifier (e.g., neighbor router ID)
            agent_id: Agent this belongs to
            initial_state: Starting state
            metadata: Additional metadata

        Returns:
            Created ProtocolState
        """
        state_id = self._generate_state_id()
        stable_states = self._stable_states.get(machine_type, set())

        state = ProtocolState(
            state_id=state_id,
            machine_type=machine_type,
            instance_id=instance_id,
            agent_id=agent_id,
            current_state=initial_state,
            is_stable=initial_state in stable_states,
            metadata=metadata or {}
        )

        self._states[state_id] = state
        logger.info(f"Registered state machine: {machine_type.value} for {instance_id} on {agent_id}")
        return state

    def transition(
        self,
        state_id: str,
        new_state: str,
        trigger: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[StateTransition]:
        """
        Record a state transition

        Args:
            state_id: State machine ID
            new_state: New state value
            trigger: What caused the transition
            metadata: Additional metadata

        Returns:
            StateTransition record, or None if state not found
        """
        state = self._states.get(state_id)
        if not state:
            logger.warning(f"State not found: {state_id}")
            return None

        if state.current_state == new_state:
            return None  # No actual transition

        # Calculate time in previous state
        duration_ms = int(state.time_in_state.total_seconds() * 1000)

        # Create transition record
        transition = StateTransition(
            transition_id=self._generate_transition_id(),
            state_id=state_id,
            from_state=state.current_state,
            to_state=new_state,
            trigger=trigger,
            duration_ms=duration_ms,
            metadata=metadata or {}
        )

        # Update state
        state.previous_state = state.current_state
        state.current_state = new_state
        state.state_entered_at = datetime.now()
        state.transition_count += 1
        state.is_stable = new_state in self._stable_states.get(state.machine_type, set())

        # Store transition
        self._transitions.append(transition)
        if len(self._transitions) > self._history_limit:
            self._transitions = self._transitions[-self._history_limit:]

        logger.debug(f"Transition: {state.instance_id} {transition.from_state} -> {transition.to_state}")
        return transition

    def get_state(self, state_id: str) -> Optional[ProtocolState]:
        """Get a specific state by ID"""
        return self._states.get(state_id)

    def get_states_by_agent(self, agent_id: str) -> List[ProtocolState]:
        """Get all states for an agent"""
        return [s for s in self._states.values() if s.agent_id == agent_id]

    def get_states_by_type(self, machine_type: StateMachineType) -> List[ProtocolState]:
        """Get all states of a specific type"""
        return [s for s in self._states.values() if s.machine_type == machine_type]

    def get_unstable_states(self) -> List[ProtocolState]:
        """Get all states not in stable state"""
        return [s for s in self._states.values() if not s.is_stable]

    def get_transitions(
        self,
        state_id: Optional[str] = None,
        limit: int = 100
    ) -> List[StateTransition]:
        """
        Get transition history

        Args:
            state_id: Filter by state ID
            limit: Maximum transitions to return

        Returns:
            List of transitions
        """
        if state_id:
            filtered = [t for t in self._transitions if t.state_id == state_id]
            return filtered[-limit:]
        return self._transitions[-limit:]

    def get_recent_transitions(
        self,
        seconds: int = 60
    ) -> List[StateTransition]:
        """Get transitions from the last N seconds"""
        cutoff = datetime.now() - timedelta(seconds=seconds)
        return [t for t in self._transitions if t.timestamp > cutoff]

    def get_state_order(self, machine_type: StateMachineType) -> List[str]:
        """Get ordered list of states for a machine type"""
        return self._state_order.get(machine_type, [])

    def get_flapping_states(self, threshold: int = 5, window_seconds: int = 60) -> List[ProtocolState]:
        """
        Detect states that are flapping (rapid transitions)

        Args:
            threshold: Minimum transitions to be considered flapping
            window_seconds: Time window to check

        Returns:
            List of flapping states
        """
        cutoff = datetime.now() - timedelta(seconds=window_seconds)
        transition_counts: Dict[str, int] = defaultdict(int)

        for t in self._transitions:
            if t.timestamp > cutoff:
                transition_counts[t.state_id] += 1

        flapping = []
        for state_id, count in transition_counts.items():
            if count >= threshold:
                state = self._states.get(state_id)
                if state:
                    flapping.append(state)

        return flapping

    def get_convergence_status(self) -> Dict[str, Any]:
        """
        Get overall convergence status

        Returns:
            Convergence summary
        """
        total = len(self._states)
        stable = len([s for s in self._states.values() if s.is_stable])
        flapping = len(self.get_flapping_states())

        by_type: Dict[str, Dict[str, int]] = {}
        for state in self._states.values():
            type_key = state.machine_type.value
            if type_key not in by_type:
                by_type[type_key] = {"total": 0, "stable": 0}
            by_type[type_key]["total"] += 1
            if state.is_stable:
                by_type[type_key]["stable"] += 1

        return {
            "total_state_machines": total,
            "stable_count": stable,
            "unstable_count": total - stable,
            "flapping_count": flapping,
            "convergence_percent": (stable / total * 100) if total > 0 else 100,
            "by_protocol": by_type
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Get tracker statistics"""
        return {
            "total_states": len(self._states),
            "total_transitions": len(self._transitions),
            "stable_states": len([s for s in self._states.values() if s.is_stable]),
            "history_limit": self._history_limit
        }


# Global tracker instance
_global_tracker: Optional[StateTracker] = None


def get_state_tracker() -> StateTracker:
    """Get or create the global state tracker"""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = StateTracker()
    return _global_tracker
