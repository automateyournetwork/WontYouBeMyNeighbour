"""
State Machine Execution

Provides:
- State machine definitions
- State machine instances
- State machine execution
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from enum import Enum

from .states import State, StateType, StateManager, get_state_manager
from .transitions import Transition, TransitionType, TransitionManager, get_transition_manager


class MachineStatus(Enum):
    """State machine status"""
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


@dataclass
class StateMachineConfig:
    """State machine configuration"""

    max_transitions: int = 1000  # Max transitions per run
    timeout_seconds: int = 3600  # 1 hour default
    allow_auto_transitions: bool = True
    track_history: bool = True
    history_size: int = 100
    validate_transitions: bool = True
    emit_events: bool = True
    persist_state: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "max_transitions": self.max_transitions,
            "timeout_seconds": self.timeout_seconds,
            "allow_auto_transitions": self.allow_auto_transitions,
            "track_history": self.track_history,
            "history_size": self.history_size,
            "validate_transitions": self.validate_transitions,
            "emit_events": self.emit_events,
            "persist_state": self.persist_state,
            "extra": self.extra
        }


@dataclass
class StateMachineInstance:
    """State machine instance (runtime)"""

    id: str
    machine_id: str
    name: str
    current_state_id: Optional[str] = None
    status: MachineStatus = MachineStatus.CREATED
    context: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    transition_count: int = 0
    last_transition_at: Optional[datetime] = None
    error: Optional[str] = None

    def is_running(self) -> bool:
        return self.status == MachineStatus.RUNNING

    def is_completed(self) -> bool:
        return self.status in (MachineStatus.COMPLETED, MachineStatus.FAILED, MachineStatus.TERMINATED)

    def add_history_entry(
        self,
        state_id: str,
        transition_id: Optional[str] = None,
        event: Optional[str] = None
    ) -> None:
        """Add entry to history"""
        entry = {
            "state_id": state_id,
            "transition_id": transition_id,
            "event": event,
            "timestamp": datetime.now().isoformat(),
            "context_snapshot": dict(self.context)
        }
        self.history.append(entry)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "machine_id": self.machine_id,
            "name": self.name,
            "current_state_id": self.current_state_id,
            "status": self.status.value,
            "context": self.context,
            "history": self.history[-10:],  # Last 10 entries
            "history_size": len(self.history),
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "transition_count": self.transition_count,
            "last_transition_at": self.last_transition_at.isoformat() if self.last_transition_at else None,
            "error": self.error
        }


@dataclass
class StateMachine:
    """State machine definition"""

    id: str
    name: str
    description: str = ""
    config: StateMachineConfig = field(default_factory=StateMachineConfig)
    initial_state_id: Optional[str] = None
    state_ids: List[str] = field(default_factory=list)
    transition_ids: List[str] = field(default_factory=list)
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Statistics
    instance_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    avg_completion_time_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "config": self.config.to_dict(),
            "initial_state_id": self.initial_state_id,
            "state_ids": self.state_ids,
            "transition_ids": self.transition_ids,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "version": self.version,
            "tags": self.tags,
            "metadata": self.metadata,
            "instance_count": self.instance_count,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "avg_completion_time_seconds": self.avg_completion_time_seconds
        }


class StateMachineManager:
    """Manages state machines"""

    def __init__(self):
        self.machines: Dict[str, StateMachine] = {}
        self.instances: Dict[str, StateMachineInstance] = {}
        self._state_manager = get_state_manager()
        self._transition_manager = get_transition_manager()
        self._init_builtin_machines()

    def _init_builtin_machines(self) -> None:
        """Initialize built-in state machines"""

        # OSPF Adjacency State Machine
        ospf_machine = self._create_ospf_machine()
        self.machines[ospf_machine.id] = ospf_machine

        # BGP Peer State Machine
        bgp_machine = self._create_bgp_machine()
        self.machines[bgp_machine.id] = bgp_machine

        # IS-IS Adjacency State Machine
        isis_machine = self._create_isis_machine()
        self.machines[isis_machine.id] = isis_machine

        # Generic Workflow State Machine
        workflow_machine = self._create_workflow_machine()
        self.machines[workflow_machine.id] = workflow_machine

    def _create_ospf_machine(self) -> StateMachine:
        """Create OSPF adjacency state machine"""
        machine_id = "sm_ospf_adj"

        # Create states
        down = self._state_manager.create_state("Down", StateType.INITIAL, "OSPF Down state")
        attempt = self._state_manager.create_state("Attempt", StateType.NORMAL, "Attempting adjacency")
        init = self._state_manager.create_state("Init", StateType.NORMAL, "Neighbor seen")
        two_way = self._state_manager.create_state("2-Way", StateType.NORMAL, "Bidirectional communication")
        exstart = self._state_manager.create_state("ExStart", StateType.NORMAL, "Master/Slave negotiation")
        exchange = self._state_manager.create_state("Exchange", StateType.NORMAL, "DBD exchange")
        loading = self._state_manager.create_state("Loading", StateType.NORMAL, "LSA exchange")
        full = self._state_manager.create_state("Full", StateType.FINAL, "Fully adjacent")

        state_ids = [down.id, attempt.id, init.id, two_way.id, exstart.id, exchange.id, loading.id, full.id]

        # Create transitions
        transitions = []
        t1 = self._transition_manager.create_transition("hello_received", down.id, init.id, TransitionType.EXTERNAL, "HelloReceived")
        t2 = self._transition_manager.create_transition("2way_received", init.id, two_way.id, TransitionType.EXTERNAL, "2WayReceived")
        t3 = self._transition_manager.create_transition("adj_ok", two_way.id, exstart.id, TransitionType.EXTERNAL, "AdjOK")
        t4 = self._transition_manager.create_transition("neg_done", exstart.id, exchange.id, TransitionType.EXTERNAL, "NegotiationDone")
        t5 = self._transition_manager.create_transition("exch_done", exchange.id, loading.id, TransitionType.EXTERNAL, "ExchangeDone")
        t6 = self._transition_manager.create_transition("load_done", loading.id, full.id, TransitionType.EXTERNAL, "LoadingDone")
        transitions = [t1, t2, t3, t4, t5, t6]

        return StateMachine(
            id=machine_id,
            name="OSPF Adjacency",
            description="OSPF neighbor adjacency state machine (RFC 2328)",
            initial_state_id=down.id,
            state_ids=state_ids,
            transition_ids=[t.id for t in transitions],
            tags=["ospf", "protocol", "adjacency"]
        )

    def _create_bgp_machine(self) -> StateMachine:
        """Create BGP peer state machine"""
        machine_id = "sm_bgp_peer"

        # Create states
        idle = self._state_manager.create_state("Idle", StateType.INITIAL, "BGP Idle state")
        connect = self._state_manager.create_state("Connect", StateType.NORMAL, "TCP connection attempt")
        active = self._state_manager.create_state("Active", StateType.NORMAL, "Listening for connections")
        opensent = self._state_manager.create_state("OpenSent", StateType.NORMAL, "OPEN message sent")
        openconfirm = self._state_manager.create_state("OpenConfirm", StateType.NORMAL, "Waiting for KEEPALIVE")
        established = self._state_manager.create_state("Established", StateType.FINAL, "BGP session established")

        state_ids = [idle.id, connect.id, active.id, opensent.id, openconfirm.id, established.id]

        # Create transitions
        transitions = []
        t1 = self._transition_manager.create_transition("start", idle.id, connect.id, TransitionType.EXTERNAL, "ManualStart")
        t2 = self._transition_manager.create_transition("tcp_established", connect.id, opensent.id, TransitionType.EXTERNAL, "TcpConnectionConfirmed")
        t3 = self._transition_manager.create_transition("open_received", opensent.id, openconfirm.id, TransitionType.EXTERNAL, "BGPOpen")
        t4 = self._transition_manager.create_transition("keepalive", openconfirm.id, established.id, TransitionType.EXTERNAL, "KeepAliveMsg")
        transitions = [t1, t2, t3, t4]

        return StateMachine(
            id=machine_id,
            name="BGP Peer",
            description="BGP peer state machine (RFC 4271)",
            initial_state_id=idle.id,
            state_ids=state_ids,
            transition_ids=[t.id for t in transitions],
            tags=["bgp", "protocol", "peer"]
        )

    def _create_isis_machine(self) -> StateMachine:
        """Create IS-IS adjacency state machine"""
        machine_id = "sm_isis_adj"

        # Create states
        down = self._state_manager.create_state("Down", StateType.INITIAL, "IS-IS Down state")
        initializing = self._state_manager.create_state("Initializing", StateType.NORMAL, "Hello exchange starting")
        up = self._state_manager.create_state("Up", StateType.FINAL, "Adjacency established")

        state_ids = [down.id, initializing.id, up.id]

        # Create transitions
        transitions = []
        t1 = self._transition_manager.create_transition("iih_received", down.id, initializing.id, TransitionType.EXTERNAL, "IIHReceived")
        t2 = self._transition_manager.create_transition("adj_3way", initializing.id, up.id, TransitionType.EXTERNAL, "3WayHandshake")
        transitions = [t1, t2]

        return StateMachine(
            id=machine_id,
            name="IS-IS Adjacency",
            description="IS-IS adjacency state machine (RFC 5303)",
            initial_state_id=down.id,
            state_ids=state_ids,
            transition_ids=[t.id for t in transitions],
            tags=["isis", "protocol", "adjacency"]
        )

    def _create_workflow_machine(self) -> StateMachine:
        """Create generic workflow state machine"""
        machine_id = "sm_workflow"

        # Create states
        pending = self._state_manager.create_state("Pending", StateType.INITIAL, "Workflow pending")
        running = self._state_manager.create_state("Running", StateType.NORMAL, "Workflow executing")
        paused = self._state_manager.create_state("Paused", StateType.NORMAL, "Workflow paused")
        completed = self._state_manager.create_state("Completed", StateType.FINAL, "Workflow completed")
        failed = self._state_manager.create_state("Failed", StateType.FINAL, "Workflow failed")
        cancelled = self._state_manager.create_state("Cancelled", StateType.FINAL, "Workflow cancelled")

        state_ids = [pending.id, running.id, paused.id, completed.id, failed.id, cancelled.id]

        # Create transitions
        transitions = []
        t1 = self._transition_manager.create_transition("start", pending.id, running.id, TransitionType.EXTERNAL, "Start")
        t2 = self._transition_manager.create_transition("pause", running.id, paused.id, TransitionType.EXTERNAL, "Pause")
        t3 = self._transition_manager.create_transition("resume", paused.id, running.id, TransitionType.EXTERNAL, "Resume")
        t4 = self._transition_manager.create_transition("complete", running.id, completed.id, TransitionType.EXTERNAL, "Complete")
        t5 = self._transition_manager.create_transition("fail", running.id, failed.id, TransitionType.EXTERNAL, "Fail")
        t6 = self._transition_manager.create_transition("cancel", pending.id, cancelled.id, TransitionType.EXTERNAL, "Cancel")
        t7 = self._transition_manager.create_transition("cancel_running", running.id, cancelled.id, TransitionType.EXTERNAL, "Cancel")
        t8 = self._transition_manager.create_transition("cancel_paused", paused.id, cancelled.id, TransitionType.EXTERNAL, "Cancel")
        transitions = [t1, t2, t3, t4, t5, t6, t7, t8]

        return StateMachine(
            id=machine_id,
            name="Workflow",
            description="Generic workflow state machine",
            initial_state_id=pending.id,
            state_ids=state_ids,
            transition_ids=[t.id for t in transitions],
            tags=["workflow", "generic"]
        )

    def create_machine(
        self,
        name: str,
        description: str = "",
        config: Optional[StateMachineConfig] = None,
        initial_state_id: Optional[str] = None,
        state_ids: Optional[List[str]] = None,
        transition_ids: Optional[List[str]] = None,
        version: str = "1.0.0",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> StateMachine:
        """Create a new state machine"""
        machine_id = f"sm_{uuid.uuid4().hex[:8]}"

        machine = StateMachine(
            id=machine_id,
            name=name,
            description=description,
            config=config or StateMachineConfig(),
            initial_state_id=initial_state_id,
            state_ids=state_ids or [],
            transition_ids=transition_ids or [],
            version=version,
            tags=tags or [],
            metadata=metadata or {}
        )

        self.machines[machine_id] = machine
        return machine

    def get_machine(self, machine_id: str) -> Optional[StateMachine]:
        """Get machine by ID"""
        return self.machines.get(machine_id)

    def get_machine_by_name(self, name: str) -> Optional[StateMachine]:
        """Get machine by name"""
        for machine in self.machines.values():
            if machine.name == name:
                return machine
        return None

    def update_machine(
        self,
        machine_id: str,
        **kwargs
    ) -> Optional[StateMachine]:
        """Update machine properties"""
        machine = self.machines.get(machine_id)
        if not machine:
            return None

        for key, value in kwargs.items():
            if hasattr(machine, key):
                setattr(machine, key, value)

        return machine

    def delete_machine(self, machine_id: str) -> bool:
        """Delete a machine"""
        if machine_id in self.machines:
            del self.machines[machine_id]
            return True
        return False

    def add_state(
        self,
        machine_id: str,
        state_id: str
    ) -> bool:
        """Add state to machine"""
        machine = self.machines.get(machine_id)
        if not machine:
            return False

        if state_id not in machine.state_ids:
            machine.state_ids.append(state_id)

        return True

    def remove_state(
        self,
        machine_id: str,
        state_id: str
    ) -> bool:
        """Remove state from machine"""
        machine = self.machines.get(machine_id)
        if not machine:
            return False

        if state_id in machine.state_ids:
            machine.state_ids.remove(state_id)

        return True

    def add_transition(
        self,
        machine_id: str,
        transition_id: str
    ) -> bool:
        """Add transition to machine"""
        machine = self.machines.get(machine_id)
        if not machine:
            return False

        if transition_id not in machine.transition_ids:
            machine.transition_ids.append(transition_id)

        return True

    def remove_transition(
        self,
        machine_id: str,
        transition_id: str
    ) -> bool:
        """Remove transition from machine"""
        machine = self.machines.get(machine_id)
        if not machine:
            return False

        if transition_id in machine.transition_ids:
            machine.transition_ids.remove(transition_id)

        return True

    def create_instance(
        self,
        machine_id: str,
        name: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[StateMachineInstance]:
        """Create a new machine instance"""
        machine = self.machines.get(machine_id)
        if not machine:
            return None

        instance_id = f"smi_{uuid.uuid4().hex[:8]}"

        instance = StateMachineInstance(
            id=instance_id,
            machine_id=machine_id,
            name=name,
            current_state_id=machine.initial_state_id,
            context=context or {}
        )

        self.instances[instance_id] = instance
        machine.instance_count += 1

        return instance

    def get_instance(self, instance_id: str) -> Optional[StateMachineInstance]:
        """Get instance by ID"""
        return self.instances.get(instance_id)

    def start_instance(self, instance_id: str) -> bool:
        """Start a machine instance"""
        instance = self.instances.get(instance_id)
        if not instance or instance.status != MachineStatus.CREATED:
            return False

        instance.status = MachineStatus.RUNNING
        instance.started_at = datetime.now()

        # Enter initial state
        if instance.current_state_id:
            self._state_manager.enter_state(instance.current_state_id, instance.context)
            instance.add_history_entry(instance.current_state_id, event="start")

        return True

    def pause_instance(self, instance_id: str) -> bool:
        """Pause a machine instance"""
        instance = self.instances.get(instance_id)
        if not instance or instance.status != MachineStatus.RUNNING:
            return False

        instance.status = MachineStatus.PAUSED
        return True

    def resume_instance(self, instance_id: str) -> bool:
        """Resume a paused instance"""
        instance = self.instances.get(instance_id)
        if not instance or instance.status != MachineStatus.PAUSED:
            return False

        instance.status = MachineStatus.RUNNING
        return True

    def stop_instance(self, instance_id: str) -> bool:
        """Stop a machine instance"""
        instance = self.instances.get(instance_id)
        if not instance or instance.is_completed():
            return False

        instance.status = MachineStatus.STOPPED
        instance.completed_at = datetime.now()
        return True

    def terminate_instance(self, instance_id: str, error: Optional[str] = None) -> bool:
        """Terminate a machine instance"""
        instance = self.instances.get(instance_id)
        if not instance:
            return False

        instance.status = MachineStatus.TERMINATED
        instance.completed_at = datetime.now()
        instance.error = error
        return True

    def send_event(
        self,
        instance_id: str,
        event: str,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send event to machine instance"""
        instance = self.instances.get(instance_id)
        if not instance or not instance.is_running():
            return False

        machine = self.machines.get(instance.machine_id)
        if not machine:
            return False

        # Update context with event data
        if data:
            instance.context.update(data)

        # Find matching transition
        transitions = self._transition_manager.get_transitions_from(
            instance.current_state_id,
            trigger=event,
            enabled_only=True
        )

        for transition in transitions:
            if self._transition_manager.can_transition(transition, instance.context):
                return self._execute_transition(instance, transition, event)

        return False

    def _execute_transition(
        self,
        instance: StateMachineInstance,
        transition: Transition,
        event: str
    ) -> bool:
        """Execute a transition"""
        # Exit current state
        if instance.current_state_id:
            self._state_manager.exit_state(instance.current_state_id, instance.context)

        # Execute before action
        if transition.before_action:
            self._transition_manager.execute_action(transition.before_action, instance.context)

        # Execute main action
        if transition.action:
            self._transition_manager.execute_action(transition.action, instance.context)

        # Update current state
        old_state_id = instance.current_state_id
        instance.current_state_id = transition.target_id

        # Enter new state
        self._state_manager.enter_state(instance.current_state_id, instance.context)

        # Execute after action
        if transition.after_action:
            self._transition_manager.execute_action(transition.after_action, instance.context)

        # Update statistics
        instance.transition_count += 1
        instance.last_transition_at = datetime.now()
        transition.execution_count += 1
        transition.success_count += 1
        transition.last_executed_at = datetime.now()

        # Add to history
        instance.add_history_entry(instance.current_state_id, transition.id, event)

        # Check if reached final state
        state = self._state_manager.get_state(instance.current_state_id)
        if state and state.is_final():
            instance.status = MachineStatus.COMPLETED
            instance.completed_at = datetime.now()
            machine = self.machines.get(instance.machine_id)
            if machine:
                machine.completed_count += 1

        return True

    def get_current_state(self, instance_id: str) -> Optional[State]:
        """Get current state of instance"""
        instance = self.instances.get(instance_id)
        if not instance or not instance.current_state_id:
            return None

        return self._state_manager.get_state(instance.current_state_id)

    def get_available_transitions(
        self,
        instance_id: str
    ) -> List[Transition]:
        """Get available transitions for instance"""
        instance = self.instances.get(instance_id)
        if not instance or not instance.current_state_id:
            return []

        return self._transition_manager.get_transitions_from(
            instance.current_state_id,
            enabled_only=True
        )

    def get_machine_states(self, machine_id: str) -> List[State]:
        """Get all states in a machine"""
        machine = self.machines.get(machine_id)
        if not machine:
            return []

        return [
            self._state_manager.get_state(sid)
            for sid in machine.state_ids
            if self._state_manager.get_state(sid)
        ]

    def get_machine_transitions(self, machine_id: str) -> List[Transition]:
        """Get all transitions in a machine"""
        machine = self.machines.get(machine_id)
        if not machine:
            return []

        return [
            self._transition_manager.get_transition(tid)
            for tid in machine.transition_ids
            if self._transition_manager.get_transition(tid)
        ]

    def get_machines(
        self,
        enabled_only: bool = False,
        tag: Optional[str] = None
    ) -> List[StateMachine]:
        """Get machines with filtering"""
        machines = list(self.machines.values())

        if enabled_only:
            machines = [m for m in machines if m.enabled]
        if tag:
            machines = [m for m in machines if tag in m.tags]

        return machines

    def get_instances(
        self,
        machine_id: Optional[str] = None,
        status: Optional[MachineStatus] = None
    ) -> List[StateMachineInstance]:
        """Get instances with filtering"""
        instances = list(self.instances.values())

        if machine_id:
            instances = [i for i in instances if i.machine_id == machine_id]
        if status:
            instances = [i for i in instances if i.status == status]

        return instances

    def get_statistics(self) -> dict:
        """Get state machine statistics"""
        total_instances = len(self.instances)
        running_instances = len([i for i in self.instances.values() if i.is_running()])
        completed_instances = len([i for i in self.instances.values() if i.is_completed()])

        return {
            "total_machines": len(self.machines),
            "enabled_machines": len([m for m in self.machines.values() if m.enabled]),
            "total_instances": total_instances,
            "running_instances": running_instances,
            "completed_instances": completed_instances,
            "builtin_machines": 4,
            "state_manager_stats": self._state_manager.get_statistics(),
            "transition_manager_stats": self._transition_manager.get_statistics()
        }


# Global state machine manager instance
_state_machine_manager: Optional[StateMachineManager] = None


def get_state_machine_manager() -> StateMachineManager:
    """Get or create the global state machine manager"""
    global _state_machine_manager
    if _state_machine_manager is None:
        _state_machine_manager = StateMachineManager()
    return _state_machine_manager
