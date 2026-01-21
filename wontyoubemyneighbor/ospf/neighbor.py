"""
OSPF Neighbor State Machine
RFC 2328 Section 10 - The Neighbor Data Structure
RFC 2328 Section 10.3 - The Neighbor state machine
"""

import time
import logging
from typing import List, Optional
from lib.state_machine import StateMachine
from ospf.constants import (
    STATE_DOWN, STATE_ATTEMPT, STATE_INIT, STATE_2WAY,
    STATE_EXSTART, STATE_EXCHANGE, STATE_LOADING, STATE_FULL,
    STATE_NAMES, EVENT_HELLO_RECEIVED, EVENT_START, EVENT_2WAY_RECEIVED,
    EVENT_NEGOTIATION_DONE, EVENT_EXCHANGE_DONE, EVENT_LOADING_DONE,
    EVENT_KILL_NBR, EVENT_INACTIVITY_TIMER, EVENT_1WAY, EVENT_ADJ_OK
)

logger = logging.getLogger(__name__)


class OSPFNeighbor:
    """
    OSPF Neighbor with RFC 2328 compliant state machine
    """

    def __init__(self, router_id: str, ip_address: str, priority: int = 1, network_type: str = "broadcast"):
        """
        Initialize OSPF neighbor

        Args:
            router_id: Neighbor's router ID
            ip_address: Neighbor's IP address
            priority: Router priority for DR election
            network_type: Network type for adjacency decision
        """
        self.router_id = router_id
        self.ip_address = ip_address
        self.priority = priority
        self.network_type = network_type

        # Timestamps
        self.last_hello = time.time()
        self.created_at = time.time()

        # Database Description exchange state
        self.dd_sequence_number = 0
        self.last_received_dbd_packet = None
        self.is_master = False

        # DBD exchange completion tracking (RFC 2328 requires BOTH sides to finish)
        self.neighbor_dbd_complete = False  # True when neighbor sends M=0
        self.our_dbd_complete = False       # True when we send M=0

        # LSA lists (RFC 2328 Section 10)
        self.ls_request_list: List = []          # LSAs we need to request
        self.ls_retransmission_list: List = []   # LSAs awaiting ack
        self.db_summary_list: List = []          # LSAs to send in DBD

        # State machine
        self.fsm = StateMachine(STATE_DOWN, name=f"Neighbor-{router_id}")
        self._setup_state_machine()

        logger.info(f"Created neighbor {router_id} ({ip_address})")

    def _setup_state_machine(self):
        """
        Configure neighbor state machine per RFC 2328 Section 10.3
        """
        # Set state names
        for state, name in STATE_NAMES.items():
            self.fsm.set_state_name(state, name)

        # Transitions from Down
        self.fsm.add_transition(STATE_DOWN, EVENT_START, STATE_ATTEMPT)
        self.fsm.add_transition(STATE_DOWN, EVENT_HELLO_RECEIVED, STATE_INIT)

        # Transitions from Attempt (NBMA only, but include for completeness)
        self.fsm.add_transition(STATE_ATTEMPT, EVENT_HELLO_RECEIVED, STATE_INIT)

        # Transitions from Init
        self.fsm.add_transition(STATE_INIT, EVENT_2WAY_RECEIVED, STATE_2WAY)
        self.fsm.add_transition(STATE_INIT, EVENT_1WAY, STATE_INIT)

        # Transitions from 2-Way
        # Only transition to ExStart if ADJ_OK is triggered (decision made before triggering)
        self.fsm.add_transition(STATE_2WAY, EVENT_ADJ_OK, STATE_EXSTART)

        # Transitions from ExStart
        self.fsm.add_transition(STATE_EXSTART, EVENT_NEGOTIATION_DONE, STATE_EXCHANGE)

        # Transitions from Exchange
        self.fsm.add_transition(STATE_EXCHANGE, EVENT_EXCHANGE_DONE, STATE_LOADING)
        # BUGFIX: Removed duplicate transition to STATE_FULL - exchange_done() handles this by
        # triggering EVENT_LOADING_DONE immediately if ls_request_list is empty

        # Transitions from Loading
        self.fsm.add_transition(STATE_LOADING, EVENT_LOADING_DONE, STATE_FULL)

        # All states can go to Down or back to Init
        for state in [STATE_ATTEMPT, STATE_INIT, STATE_2WAY, STATE_EXSTART,
                     STATE_EXCHANGE, STATE_LOADING, STATE_FULL]:
            self.fsm.add_transition(state, EVENT_KILL_NBR, STATE_DOWN)
            self.fsm.add_transition(state, EVENT_INACTIVITY_TIMER, STATE_DOWN)
            self.fsm.add_transition(state, EVENT_1WAY, STATE_INIT)

    def handle_hello_received(self, bidirectional: bool = False):
        """
        Handle Hello packet reception

        Args:
            bidirectional: True if our router ID is in neighbor's Hello
        """
        self.last_hello = time.time()

        current_state = self.fsm.get_state()

        if current_state == STATE_DOWN:
            # First Hello received
            self.fsm.trigger(EVENT_HELLO_RECEIVED)

        elif current_state == STATE_INIT:
            if bidirectional:
                # We're in their neighbor list - bidirectional communication
                self.fsm.trigger(EVENT_2WAY_RECEIVED)
                # Check if we should form adjacency
                if self.should_form_adjacency():
                    self.fsm.trigger(EVENT_ADJ_OK)
            else:
                # Still one-way
                self.fsm.trigger(EVENT_1WAY)

        elif bidirectional and current_state >= STATE_2WAY:
            # Keep neighbor alive, already at 2-Way or higher
            pass
        elif not bidirectional and current_state >= STATE_2WAY:
            # Lost bidirectional communication
            logger.warning(f"Neighbor {self.router_id}: Lost bidirectional communication! "
                         f"Current state: {STATE_NAMES[current_state]}, triggering EVENT_1WAY")
            self.fsm.trigger(EVENT_1WAY)
            logger.warning(f"Neighbor {self.router_id}: After EVENT_1WAY, new state: {self.get_state_name()}")

    def should_form_adjacency(self) -> bool:
        """
        Determine if we should form adjacency with this neighbor
        RFC 2328 Section 10.4

        Returns:
            True if adjacency should be formed
        """
        from ospf.constants import NETWORK_TYPE_POINT_TO_POINT, NETWORK_TYPE_POINT_TO_MULTIPOINT

        # For point-to-point and point-to-multipoint networks, always form adjacency
        if self.network_type in [NETWORK_TYPE_POINT_TO_POINT, NETWORK_TYPE_POINT_TO_MULTIPOINT]:
            return True

        # For broadcast/NBMA, adjacency decision depends on DR/BDR election
        # This is typically decided by the agent based on DR/BDR status
        # For now, default to True (broadcast DR/BDR logic handled elsewhere)
        return True

    def start_database_exchange(self, our_router_id: str):
        """
        Start Database Description exchange (ExStart state)

        Args:
            our_router_id: Our router ID for master/slave determination
        """
        import struct
        import socket

        current_state = self.fsm.get_state()
        if current_state != STATE_EXSTART:
            logger.warning(f"Neighbor {self.router_id} not in ExStart state for DBD exchange")
            return

        # Determine master/slave based on router ID comparison (as 32-bit integers)
        # Router IDs are compared numerically, not lexicographically
        our_id_int = struct.unpack("!I", socket.inet_aton(our_router_id))[0]
        neighbor_id_int = struct.unpack("!I", socket.inet_aton(self.router_id))[0]

        if our_id_int > neighbor_id_int:
            self.is_master = True   # We are master (higher router ID)
            self.dd_sequence_number = int(time.time())
            logger.info(f"Neighbor {self.router_id}: We are MASTER (our ID {our_router_id} > neighbor ID {self.router_id})")
        else:
            self.is_master = False  # We are slave (lower router ID)
            logger.info(f"Neighbor {self.router_id}: We are SLAVE (our ID {our_router_id} < neighbor ID {self.router_id})")

    def handle_dbd_received(self, is_initial: bool = False):
        """
        Handle Database Description packet reception

        Args:
            is_initial: True if this is the initial DBD in ExStart
        """
        current_state = self.fsm.get_state()

        if current_state == STATE_EXSTART and is_initial:
            # Master/slave negotiation complete
            self.fsm.trigger(EVENT_NEGOTIATION_DONE)

        elif current_state == STATE_EXCHANGE:
            # Continue exchange
            # In real implementation, check if all LSA headers exchanged
            pass

    def exchange_done(self):
        """
        Signal that DBD exchange is complete
        """
        current_state = self.fsm.get_state()
        if current_state == STATE_EXCHANGE:
            if len(self.ls_request_list) == 0:
                # No LSAs to request, go straight to Full
                self.fsm.trigger(EVENT_EXCHANGE_DONE)
                self.fsm.trigger(EVENT_LOADING_DONE)  # Immediately to Full
            else:
                # Have LSAs to request, go to Loading
                self.fsm.trigger(EVENT_EXCHANGE_DONE)

    def mark_neighbor_dbd_complete(self):
        """Mark that neighbor has sent their final DBD (M=0)"""
        self.neighbor_dbd_complete = True
        logger.debug(f"Neighbor {self.router_id} DBD complete (M=0 received)")

    def mark_our_dbd_complete(self):
        """Mark that we have sent our final DBD (M=0)"""
        self.our_dbd_complete = True
        logger.debug(f"Our DBD complete for {self.router_id} (M=0 sent)")

    def is_exchange_complete(self) -> bool:
        """
        Check if DBD exchange is complete (both sides have finished)

        Returns:
            True if both we and neighbor have sent M=0
        """
        return self.neighbor_dbd_complete and self.our_dbd_complete

    def reset_exchange_state(self):
        """Reset exchange completion tracking (for state machine resets)"""
        self.neighbor_dbd_complete = False
        self.our_dbd_complete = False
        self.db_summary_list = []
        self.ls_request_list = []

    def loading_done(self):
        """
        Signal that all LSA requests have been satisfied
        """
        current_state = self.fsm.get_state()
        if current_state == STATE_LOADING:
            if len(self.ls_request_list) == 0:
                self.fsm.trigger(EVENT_LOADING_DONE)

    def kill(self):
        """
        Kill neighbor (bring down adjacency)
        """
        self.fsm.trigger(EVENT_KILL_NBR)

    def check_inactivity(self, dead_interval: int) -> bool:
        """
        Check if neighbor has been inactive too long

        Args:
            dead_interval: Dead interval in seconds

        Returns:
            True if neighbor timed out
        """
        time_since_hello = time.time() - self.last_hello

        if time_since_hello > dead_interval:
            logger.warning(f"Neighbor {self.router_id} inactive for {time_since_hello:.1f}s")
            self.fsm.trigger(EVENT_INACTIVITY_TIMER)
            return True

        return False

    def get_state(self) -> int:
        """
        Get current neighbor state

        Returns:
            Current state value
        """
        return self.fsm.get_state()

    def get_state_name(self) -> str:
        """
        Get current neighbor state name

        Returns:
            Human-readable state name
        """
        return self.fsm.get_state_name()

    def is_full(self) -> bool:
        """
        Check if neighbor is in Full state

        Returns:
            True if in Full state
        """
        return self.get_state() == STATE_FULL

    def is_at_least_2way(self) -> bool:
        """
        Check if neighbor is at least in 2-Way state

        Returns:
            True if state >= 2-Way
        """
        return self.get_state() >= STATE_2WAY

    def is_adjacent(self) -> bool:
        """
        Check if we have adjacency with neighbor (ExStart or higher)

        Returns:
            True if adjacent
        """
        return self.get_state() >= STATE_EXSTART

    def get_age(self) -> float:
        """
        Get neighbor age (time since creation)

        Returns:
            Age in seconds
        """
        return time.time() - self.created_at

    def __repr__(self) -> str:
        return (f"OSPFNeighbor(router_id={self.router_id}, "
                f"ip={self.ip_address}, "
                f"state={self.get_state_name()}, "
                f"priority={self.priority})")
