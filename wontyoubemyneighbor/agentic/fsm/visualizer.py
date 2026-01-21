"""
FSM Visualizer - Generates visualization data for protocol state machines

Provides:
- State machine diagram generation
- Transition animation data
- State highlighting
- Interactive visualization support
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

from .tracker import (
    StateTracker,
    StateMachineType,
    ProtocolState,
    StateTransition,
    OSPFNeighborState,
    BGPState,
    ISISAdjacencyState
)

logger = logging.getLogger("FSMVisualizer")


@dataclass
class StateNode:
    """
    Visual node representing a state

    Attributes:
        node_id: Unique identifier
        state_name: State name
        label: Display label
        x: X position (0-100)
        y: Y position (0-100)
        is_current: Whether this is current state
        is_stable: Whether this is a stable/target state
        color: Node color
        size: Node size
    """
    node_id: str
    state_name: str
    label: str
    x: float
    y: float
    is_current: bool = False
    is_stable: bool = False
    color: str = "#4a90d9"
    size: int = 40

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.node_id,
            "state_name": self.state_name,
            "label": self.label,
            "x": self.x,
            "y": self.y,
            "is_current": self.is_current,
            "is_stable": self.is_stable,
            "color": self.color,
            "size": self.size
        }


@dataclass
class TransitionEdge:
    """
    Visual edge representing a transition

    Attributes:
        edge_id: Unique identifier
        from_state: Source state
        to_state: Target state
        label: Transition label/trigger
        is_active: Whether recently traversed
        color: Edge color
        width: Edge width
        animated: Whether to animate
    """
    edge_id: str
    from_state: str
    to_state: str
    label: str = ""
    is_active: bool = False
    color: str = "#666"
    width: int = 2
    animated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.edge_id,
            "source": self.from_state,
            "target": self.to_state,
            "label": self.label,
            "is_active": self.is_active,
            "color": self.color,
            "width": self.width,
            "animated": self.animated
        }


@dataclass
class FSMDiagram:
    """
    Complete FSM diagram data

    Attributes:
        diagram_id: Unique identifier
        machine_type: Type of state machine
        instance_id: Instance identifier
        agent_id: Agent identifier
        nodes: State nodes
        edges: Transition edges
        current_state: Current state name
        recent_transitions: Recent transitions for animation
        metadata: Additional diagram metadata
    """
    diagram_id: str
    machine_type: StateMachineType
    instance_id: str
    agent_id: str
    nodes: List[StateNode] = field(default_factory=list)
    edges: List[TransitionEdge] = field(default_factory=list)
    current_state: str = ""
    recent_transitions: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diagram_id": self.diagram_id,
            "machine_type": self.machine_type.value,
            "instance_id": self.instance_id,
            "agent_id": self.agent_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "current_state": self.current_state,
            "recent_transitions": self.recent_transitions,
            "metadata": self.metadata,
            "generated_at": self.generated_at.isoformat()
        }


class FSMVisualizer:
    """
    Generates visualization data for protocol state machines
    """

    def __init__(self, tracker: Optional[StateTracker] = None):
        """
        Initialize FSM visualizer

        Args:
            tracker: StateTracker instance (uses global if not provided)
        """
        self._tracker = tracker
        self._diagram_counter = 0

        # Color schemes for different protocols
        self._colors = {
            StateMachineType.OSPF_NEIGHBOR: {
                "stable": "#28a745",  # Green
                "transitioning": "#ffc107",  # Yellow
                "down": "#dc3545",  # Red
                "current": "#007bff",  # Blue
                "default": "#6c757d"  # Gray
            },
            StateMachineType.BGP_FSM: {
                "stable": "#28a745",
                "transitioning": "#17a2b8",  # Cyan
                "down": "#dc3545",
                "current": "#007bff",
                "default": "#6c757d"
            },
            StateMachineType.ISIS_ADJACENCY: {
                "stable": "#28a745",
                "transitioning": "#fd7e14",  # Orange
                "down": "#dc3545",
                "current": "#007bff",
                "default": "#6c757d"
            }
        }

        # State positions for each protocol (x, y coordinates 0-100)
        self._ospf_positions = {
            "Down": (10, 50),
            "Attempt": (25, 30),
            "Init": (25, 70),
            "2-Way": (40, 50),
            "ExStart": (55, 30),
            "Exchange": (55, 70),
            "Loading": (70, 50),
            "Full": (90, 50)
        }

        self._bgp_positions = {
            "Idle": (10, 50),
            "Connect": (30, 30),
            "Active": (30, 70),
            "OpenSent": (50, 50),
            "OpenConfirm": (70, 50),
            "Established": (90, 50)
        }

        self._isis_positions = {
            "Down": (20, 50),
            "Initializing": (50, 50),
            "Up": (80, 50)
        }

        # Valid transitions for each protocol
        self._ospf_transitions = [
            ("Down", "Init", "Hello Received"),
            ("Init", "2-Way", "2-Way Received"),
            ("2-Way", "ExStart", "Adj OK"),
            ("2-Way", "Down", "Kill Nbr"),
            ("ExStart", "Exchange", "Negotiation Done"),
            ("ExStart", "Down", "Kill Nbr"),
            ("Exchange", "Loading", "Exchange Done"),
            ("Exchange", "Down", "Kill Nbr"),
            ("Loading", "Full", "Loading Done"),
            ("Loading", "Down", "Kill Nbr"),
            ("Full", "Down", "Kill Nbr"),
            ("Full", "2-Way", "Adj OK?"),
            ("Down", "Attempt", "Start (NBMA)"),
            ("Attempt", "Init", "Hello Received"),
        ]

        self._bgp_transitions = [
            ("Idle", "Connect", "ManualStart"),
            ("Connect", "Active", "ConnRetryTimer"),
            ("Connect", "OpenSent", "TCP Established"),
            ("Active", "Connect", "ConnRetryTimer"),
            ("Active", "OpenSent", "TCP Established"),
            ("OpenSent", "OpenConfirm", "Open Received"),
            ("OpenSent", "Active", "TCP Fails"),
            ("OpenConfirm", "Established", "Keepalive Received"),
            ("OpenConfirm", "Idle", "Hold Timer"),
            ("Established", "Idle", "Error/Close"),
            ("Idle", "Idle", "ManualStop"),
            ("Connect", "Idle", "ManualStop"),
            ("Active", "Idle", "ManualStop"),
        ]

        self._isis_transitions = [
            ("Down", "Initializing", "Hello Received"),
            ("Initializing", "Up", "3-Way Handshake Complete"),
            ("Up", "Down", "Hold Timer Expired"),
            ("Initializing", "Down", "Hold Timer Expired"),
        ]

    @property
    def tracker(self) -> StateTracker:
        """Get tracker, using global if not set"""
        if self._tracker is None:
            from .tracker import get_state_tracker
            self._tracker = get_state_tracker()
        return self._tracker

    def _generate_diagram_id(self) -> str:
        """Generate unique diagram ID"""
        self._diagram_counter += 1
        return f"diagram-{self._diagram_counter:06d}"

    def generate_ospf_diagram(
        self,
        state: ProtocolState,
        recent_transitions: Optional[List[StateTransition]] = None
    ) -> FSMDiagram:
        """
        Generate OSPF neighbor state machine diagram

        Args:
            state: Current protocol state
            recent_transitions: Recent transitions for animation

        Returns:
            FSMDiagram for visualization
        """
        colors = self._colors[StateMachineType.OSPF_NEIGHBOR]
        stable_states = {"Full", "2-Way"}

        nodes = []
        for state_name, (x, y) in self._ospf_positions.items():
            is_current = state_name == state.current_state
            is_stable = state_name in stable_states

            if is_current:
                color = colors["current"]
            elif is_stable:
                color = colors["stable"]
            elif state_name == "Down":
                color = colors["down"]
            else:
                color = colors["transitioning"]

            nodes.append(StateNode(
                node_id=f"ospf-{state_name.lower().replace('-', '')}",
                state_name=state_name,
                label=state_name,
                x=x,
                y=y,
                is_current=is_current,
                is_stable=is_stable,
                color=color,
                size=50 if is_current else 40
            ))

        # Create edges
        edges = []
        recent_pairs = set()
        if recent_transitions:
            for t in recent_transitions[-5:]:  # Last 5 transitions
                recent_pairs.add((t.from_state, t.to_state))

        for from_state, to_state, label in self._ospf_transitions:
            is_active = (from_state, to_state) in recent_pairs
            edges.append(TransitionEdge(
                edge_id=f"ospf-{from_state.lower()}-{to_state.lower()}",
                from_state=f"ospf-{from_state.lower().replace('-', '')}",
                to_state=f"ospf-{to_state.lower().replace('-', '')}",
                label=label,
                is_active=is_active,
                color="#28a745" if is_active else "#666",
                width=3 if is_active else 2,
                animated=is_active
            ))

        return FSMDiagram(
            diagram_id=self._generate_diagram_id(),
            machine_type=StateMachineType.OSPF_NEIGHBOR,
            instance_id=state.instance_id,
            agent_id=state.agent_id,
            nodes=nodes,
            edges=edges,
            current_state=state.current_state,
            recent_transitions=[t.to_dict() for t in (recent_transitions or [])[-10:]],
            metadata={
                "neighbor_id": state.instance_id,
                "time_in_state": state.time_in_state.total_seconds(),
                "transition_count": state.transition_count
            }
        )

    def generate_bgp_diagram(
        self,
        state: ProtocolState,
        recent_transitions: Optional[List[StateTransition]] = None
    ) -> FSMDiagram:
        """
        Generate BGP FSM diagram

        Args:
            state: Current protocol state
            recent_transitions: Recent transitions for animation

        Returns:
            FSMDiagram for visualization
        """
        colors = self._colors[StateMachineType.BGP_FSM]
        stable_states = {"Established"}

        nodes = []
        for state_name, (x, y) in self._bgp_positions.items():
            is_current = state_name == state.current_state
            is_stable = state_name in stable_states

            if is_current:
                color = colors["current"]
            elif is_stable:
                color = colors["stable"]
            elif state_name == "Idle":
                color = colors["down"]
            else:
                color = colors["transitioning"]

            nodes.append(StateNode(
                node_id=f"bgp-{state_name.lower()}",
                state_name=state_name,
                label=state_name,
                x=x,
                y=y,
                is_current=is_current,
                is_stable=is_stable,
                color=color,
                size=50 if is_current else 40
            ))

        # Create edges
        edges = []
        recent_pairs = set()
        if recent_transitions:
            for t in recent_transitions[-5:]:
                recent_pairs.add((t.from_state, t.to_state))

        for from_state, to_state, label in self._bgp_transitions:
            is_active = (from_state, to_state) in recent_pairs
            edges.append(TransitionEdge(
                edge_id=f"bgp-{from_state.lower()}-{to_state.lower()}",
                from_state=f"bgp-{from_state.lower()}",
                to_state=f"bgp-{to_state.lower()}",
                label=label,
                is_active=is_active,
                color="#28a745" if is_active else "#666",
                width=3 if is_active else 2,
                animated=is_active
            ))

        return FSMDiagram(
            diagram_id=self._generate_diagram_id(),
            machine_type=StateMachineType.BGP_FSM,
            instance_id=state.instance_id,
            agent_id=state.agent_id,
            nodes=nodes,
            edges=edges,
            current_state=state.current_state,
            recent_transitions=[t.to_dict() for t in (recent_transitions or [])[-10:]],
            metadata={
                "peer_ip": state.instance_id,
                "time_in_state": state.time_in_state.total_seconds(),
                "transition_count": state.transition_count
            }
        )

    def generate_isis_diagram(
        self,
        state: ProtocolState,
        recent_transitions: Optional[List[StateTransition]] = None
    ) -> FSMDiagram:
        """
        Generate IS-IS adjacency state machine diagram

        Args:
            state: Current protocol state
            recent_transitions: Recent transitions for animation

        Returns:
            FSMDiagram for visualization
        """
        colors = self._colors[StateMachineType.ISIS_ADJACENCY]
        stable_states = {"Up"}

        nodes = []
        for state_name, (x, y) in self._isis_positions.items():
            is_current = state_name == state.current_state
            is_stable = state_name in stable_states

            if is_current:
                color = colors["current"]
            elif is_stable:
                color = colors["stable"]
            elif state_name == "Down":
                color = colors["down"]
            else:
                color = colors["transitioning"]

            nodes.append(StateNode(
                node_id=f"isis-{state_name.lower()}",
                state_name=state_name,
                label=state_name,
                x=x,
                y=y,
                is_current=is_current,
                is_stable=is_stable,
                color=color,
                size=50 if is_current else 40
            ))

        # Create edges
        edges = []
        recent_pairs = set()
        if recent_transitions:
            for t in recent_transitions[-5:]:
                recent_pairs.add((t.from_state, t.to_state))

        for from_state, to_state, label in self._isis_transitions:
            is_active = (from_state, to_state) in recent_pairs
            edges.append(TransitionEdge(
                edge_id=f"isis-{from_state.lower()}-{to_state.lower()}",
                from_state=f"isis-{from_state.lower()}",
                to_state=f"isis-{to_state.lower()}",
                label=label,
                is_active=is_active,
                color="#28a745" if is_active else "#666",
                width=3 if is_active else 2,
                animated=is_active
            ))

        return FSMDiagram(
            diagram_id=self._generate_diagram_id(),
            machine_type=StateMachineType.ISIS_ADJACENCY,
            instance_id=state.instance_id,
            agent_id=state.agent_id,
            nodes=nodes,
            edges=edges,
            current_state=state.current_state,
            recent_transitions=[t.to_dict() for t in (recent_transitions or [])[-10:]],
            metadata={
                "neighbor_id": state.instance_id,
                "time_in_state": state.time_in_state.total_seconds(),
                "transition_count": state.transition_count
            }
        )

    def generate_diagram(
        self,
        state: ProtocolState,
        recent_transitions: Optional[List[StateTransition]] = None
    ) -> FSMDiagram:
        """
        Generate appropriate diagram based on state machine type

        Args:
            state: Protocol state
            recent_transitions: Recent transitions

        Returns:
            FSMDiagram for visualization
        """
        if state.machine_type == StateMachineType.OSPF_NEIGHBOR:
            return self.generate_ospf_diagram(state, recent_transitions)
        elif state.machine_type == StateMachineType.BGP_FSM:
            return self.generate_bgp_diagram(state, recent_transitions)
        elif state.machine_type == StateMachineType.ISIS_ADJACENCY:
            return self.generate_isis_diagram(state, recent_transitions)
        else:
            # Generic diagram
            return self._generate_generic_diagram(state, recent_transitions)

    def _generate_generic_diagram(
        self,
        state: ProtocolState,
        recent_transitions: Optional[List[StateTransition]] = None
    ) -> FSMDiagram:
        """Generate a generic diagram for unknown state machine types"""
        nodes = [
            StateNode(
                node_id="generic-current",
                state_name=state.current_state,
                label=state.current_state,
                x=50,
                y=50,
                is_current=True,
                color="#007bff",
                size=60
            )
        ]

        if state.previous_state:
            nodes.append(StateNode(
                node_id="generic-previous",
                state_name=state.previous_state,
                label=state.previous_state,
                x=20,
                y=50,
                is_current=False,
                color="#6c757d",
                size=40
            ))

        return FSMDiagram(
            diagram_id=self._generate_diagram_id(),
            machine_type=state.machine_type,
            instance_id=state.instance_id,
            agent_id=state.agent_id,
            nodes=nodes,
            edges=[],
            current_state=state.current_state,
            recent_transitions=[t.to_dict() for t in (recent_transitions or [])[-10:]]
        )

    def generate_all_diagrams(
        self,
        agent_id: Optional[str] = None
    ) -> List[FSMDiagram]:
        """
        Generate diagrams for all tracked states

        Args:
            agent_id: Optional filter by agent

        Returns:
            List of FSMDiagrams
        """
        diagrams = []

        states = self.tracker.get_states_by_agent(agent_id) if agent_id else list(self.tracker._states.values())

        for state in states:
            transitions = self.tracker.get_transitions(state.state_id, limit=10)
            diagram = self.generate_diagram(state, transitions)
            diagrams.append(diagram)

        return diagrams

    def get_convergence_visualization(self) -> Dict[str, Any]:
        """
        Get visualization data for overall convergence status

        Returns:
            Convergence visualization data
        """
        status = self.tracker.get_convergence_status()

        # Generate summary nodes for each protocol
        protocol_nodes = []
        y_offset = 20
        for protocol, counts in status["by_protocol"].items():
            total = counts["total"]
            stable = counts["stable"]
            pct = (stable / total * 100) if total > 0 else 100

            color = "#28a745" if pct == 100 else "#ffc107" if pct >= 50 else "#dc3545"

            protocol_nodes.append({
                "protocol": protocol,
                "total": total,
                "stable": stable,
                "percentage": pct,
                "color": color,
                "y": y_offset
            })
            y_offset += 25

        return {
            "summary": status,
            "protocol_nodes": protocol_nodes,
            "flapping_count": status["flapping_count"],
            "overall_health": "healthy" if status["convergence_percent"] == 100 else
                            "converging" if status["convergence_percent"] >= 50 else "degraded"
        }


# Global visualizer instance
_global_visualizer: Optional[FSMVisualizer] = None


def get_fsm_visualizer() -> FSMVisualizer:
    """Get or create the global FSM visualizer"""
    global _global_visualizer
    if _global_visualizer is None:
        _global_visualizer = FSMVisualizer()
    return _global_visualizer
