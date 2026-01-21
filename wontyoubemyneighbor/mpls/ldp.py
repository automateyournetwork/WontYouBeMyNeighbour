"""
LDP (Label Distribution Protocol) Implementation

Implements LDP control plane for MPLS label distribution
per RFC 5036.
"""

import asyncio
import logging
import socket
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Callable, Tuple
from datetime import datetime
from enum import Enum
from ipaddress import ip_address, ip_network

from .label import Label, LabelAllocator, MIN_LABEL, MAX_LABEL, LABEL_IMPLICIT_NULL
from .lfib import LFIB, LFIBEntry, LabelAction, NextHopType


# LDP Constants
LDP_PORT = 646                    # LDP Discovery and Session port
LDP_HELLO_INTERVAL = 5            # Default hello interval (seconds)
LDP_HOLD_TIME = 15                # Default hold time (seconds)
LDP_KEEPALIVE_INTERVAL = 60       # Keepalive interval (seconds)
LDP_SESSION_TIMEOUT = 180         # Session timeout (seconds)

# LDP Message Types
LDP_MSG_NOTIFICATION = 0x0001
LDP_MSG_HELLO = 0x0100
LDP_MSG_INIT = 0x0200
LDP_MSG_KEEPALIVE = 0x0201
LDP_MSG_ADDRESS = 0x0300
LDP_MSG_ADDRESS_WITHDRAW = 0x0301
LDP_MSG_LABEL_MAPPING = 0x0400
LDP_MSG_LABEL_REQUEST = 0x0401
LDP_MSG_LABEL_WITHDRAW = 0x0402
LDP_MSG_LABEL_RELEASE = 0x0403

# LDP TLV Types
LDP_TLV_FEC = 0x0100
LDP_TLV_ADDRESS_LIST = 0x0101
LDP_TLV_GENERIC_LABEL = 0x0200
LDP_TLV_ATM_LABEL = 0x0201
LDP_TLV_FRAME_RELAY_LABEL = 0x0202
LDP_TLV_STATUS = 0x0300
LDP_TLV_COMMON_HELLO_PARAMS = 0x0400
LDP_TLV_IPV4_TRANSPORT = 0x0401
LDP_TLV_CONFIGURATION_SEQUENCE = 0x0402
LDP_TLV_COMMON_SESSION_PARAMS = 0x0500

# FEC Types
FEC_WILDCARD = 0x01
FEC_PREFIX = 0x02


class LDPSessionState(Enum):
    """LDP Session States per RFC 5036"""
    NON_EXISTENT = 0
    INITIALIZED = 1
    OPENSENT = 2
    OPENREC = 3
    OPERATIONAL = 4


@dataclass
class FEC:
    """
    Forwarding Equivalence Class.

    A FEC identifies a set of packets that should receive
    the same forwarding treatment.
    """
    fec_type: int = FEC_PREFIX
    prefix: str = ""                  # IP prefix (e.g., "10.0.0.0/24")
    prefix_len: int = 0

    @classmethod
    def from_prefix(cls, prefix: str) -> 'FEC':
        """Create FEC from IP prefix string"""
        network = ip_network(prefix, strict=False)
        return cls(
            fec_type=FEC_PREFIX,
            prefix=str(network),
            prefix_len=network.prefixlen,
        )

    def __hash__(self):
        return hash((self.fec_type, self.prefix))

    def __eq__(self, other):
        if not isinstance(other, FEC):
            return False
        return self.fec_type == other.fec_type and self.prefix == other.prefix

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "prefix" if self.fec_type == FEC_PREFIX else "wildcard",
            "prefix": self.prefix,
        }


@dataclass
class LabelBinding:
    """
    Label binding for a FEC.

    Associates a label with a FEC for forwarding.
    """
    fec: FEC
    local_label: int                  # Label we assigned
    remote_label: Optional[int] = None  # Label from peer
    peer_id: Optional[str] = None     # LDP ID of peer
    next_hop: Optional[str] = None    # Next hop IP

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fec": self.fec.to_dict(),
            "local_label": self.local_label,
            "remote_label": self.remote_label,
            "peer_id": self.peer_id,
            "next_hop": self.next_hop,
        }


@dataclass
class LDPNeighbor:
    """
    LDP Neighbor discovered via Hello.
    """
    ldp_id: str                       # LDP Identifier (Router ID:0)
    transport_ip: str                 # Transport address
    interface: str                    # Discovery interface
    hold_time: int = LDP_HOLD_TIME
    last_hello: Optional[datetime] = None

    # Session info (if established)
    session_state: LDPSessionState = LDPSessionState.NON_EXISTENT
    addresses: List[str] = field(default_factory=list)

    def is_operational(self) -> bool:
        return self.session_state == LDPSessionState.OPERATIONAL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ldp_id": self.ldp_id,
            "transport_ip": self.transport_ip,
            "interface": self.interface,
            "hold_time": self.hold_time,
            "session_state": self.session_state.name,
        }


class LDPSession:
    """
    LDP Session with a peer.

    Manages the TCP session and label exchange with a single LDP peer.
    """

    def __init__(
        self,
        local_id: str,
        peer_id: str,
        peer_ip: str,
        local_ip: str,
    ):
        """
        Initialize LDP session.

        Args:
            local_id: Local LDP identifier
            peer_id: Peer LDP identifier
            peer_ip: Peer transport IP
            local_ip: Local transport IP
        """
        self.local_id = local_id
        self.peer_id = peer_id
        self.peer_ip = peer_ip
        self.local_ip = local_ip

        self.state = LDPSessionState.NON_EXISTENT

        # TCP connection
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None

        # Peer's addresses
        self.peer_addresses: List[str] = []

        # Label bindings: {FEC: LabelBinding}
        self._bindings: Dict[FEC, LabelBinding] = {}

        # Keepalive timer
        self._keepalive_task: Optional[asyncio.Task] = None

        # Callbacks
        self.on_binding_received: Optional[Callable[[FEC, int], None]] = None
        self.on_session_up: Optional[Callable[[], None]] = None
        self.on_session_down: Optional[Callable[[], None]] = None

        self.logger = logging.getLogger(f"LDPSession[{peer_id}]")

    async def start(self) -> bool:
        """
        Start LDP session (initiate TCP connection).

        Returns:
            True if session established
        """
        self.logger.info(f"Starting session with {self.peer_id} ({self.peer_ip})")

        try:
            # Determine who initiates (higher IP initiates)
            if ip_address(self.local_ip) > ip_address(self.peer_ip):
                # We initiate
                self._reader, self._writer = await asyncio.open_connection(
                    self.peer_ip, LDP_PORT
                )
                self.logger.debug(f"Connected to {self.peer_ip}:{LDP_PORT}")
            else:
                # Wait for peer to connect
                self.logger.debug("Waiting for peer to initiate connection")
                return False  # Will be called when peer connects

            self.state = LDPSessionState.INITIALIZED

            # Send Init message
            await self._send_init()
            self.state = LDPSessionState.OPENSENT

            # Start message receive loop
            asyncio.create_task(self._receive_loop())

            return True

        except Exception as e:
            self.logger.error(f"Failed to start session: {e}")
            self.state = LDPSessionState.NON_EXISTENT
            return False

    async def accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """
        Accept incoming session.

        Args:
            reader: Stream reader
            writer: Stream writer
        """
        self._reader = reader
        self._writer = writer
        self.state = LDPSessionState.INITIALIZED

        # Start message receive loop
        asyncio.create_task(self._receive_loop())

    async def stop(self) -> None:
        """Stop LDP session"""
        self.logger.info(f"Stopping session with {self.peer_id}")

        old_state = self.state
        self.state = LDPSessionState.NON_EXISTENT

        if self._keepalive_task:
            self._keepalive_task.cancel()

        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except (OSError, ConnectionError) as e:
                self.logger.debug(f"Error closing writer: {e}")

        if old_state == LDPSessionState.OPERATIONAL and self.on_session_down:
            self.on_session_down()

    async def _send_init(self) -> None:
        """Send LDP Initialization message"""
        # Simplified - just mark as sent
        self.logger.debug("Sent Init message")

    async def send_label_mapping(self, fec: FEC, label: int) -> None:
        """
        Send Label Mapping message.

        Args:
            fec: FEC for the binding
            label: Local label
        """
        if self.state != LDPSessionState.OPERATIONAL:
            return

        # Build and send Label Mapping message
        self.logger.debug(f"Sent Label Mapping: {fec.prefix} -> {label}")

    async def send_label_withdraw(self, fec: FEC) -> None:
        """
        Send Label Withdraw message.

        Args:
            fec: FEC being withdrawn
        """
        if self.state != LDPSessionState.OPERATIONAL:
            return

        self.logger.debug(f"Sent Label Withdraw: {fec.prefix}")

    async def _receive_loop(self) -> None:
        """Message receive loop"""
        while self.state != LDPSessionState.NON_EXISTENT:
            try:
                if not self._reader:
                    break

                # Read message (simplified)
                data = await self._reader.read(1024)
                if not data:
                    break

                # Process message
                await self._process_message(data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in receive loop: {e}")
                break

        await self.stop()

    async def _process_message(self, data: bytes) -> None:
        """Process received LDP message"""
        # Simplified message processing
        if len(data) < 4:
            return

        msg_type = struct.unpack("!H", data[0:2])[0]

        if msg_type == LDP_MSG_INIT:
            await self._handle_init(data)
        elif msg_type == LDP_MSG_KEEPALIVE:
            await self._handle_keepalive(data)
        elif msg_type == LDP_MSG_LABEL_MAPPING:
            await self._handle_label_mapping(data)
        elif msg_type == LDP_MSG_LABEL_WITHDRAW:
            await self._handle_label_withdraw(data)

    async def _handle_init(self, data: bytes) -> None:
        """Handle Init message"""
        self.logger.debug("Received Init message")

        if self.state == LDPSessionState.OPENSENT:
            # Send Init back and transition to operational
            await self._send_init()
            self.state = LDPSessionState.OPERATIONAL
            self.logger.info(f"Session OPERATIONAL with {self.peer_id}")

            # Start keepalive
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())

            if self.on_session_up:
                self.on_session_up()

        elif self.state == LDPSessionState.INITIALIZED:
            # Send Init and wait for theirs
            await self._send_init()
            self.state = LDPSessionState.OPENSENT

    async def _handle_keepalive(self, data: bytes) -> None:
        """Handle Keepalive message"""
        self.logger.debug("Received Keepalive")

    async def _handle_label_mapping(self, data: bytes) -> None:
        """Handle Label Mapping message"""
        # Parse FEC and label from message (simplified)
        # In real implementation, parse TLVs

        self.logger.debug("Received Label Mapping")

        if self.on_binding_received:
            # Would extract actual FEC and label from message
            pass

    async def _handle_label_withdraw(self, data: bytes) -> None:
        """Handle Label Withdraw message"""
        self.logger.debug("Received Label Withdraw")

    async def _keepalive_loop(self) -> None:
        """Send periodic keepalives"""
        while self.state == LDPSessionState.OPERATIONAL:
            try:
                await asyncio.sleep(LDP_KEEPALIVE_INTERVAL)

                if self._writer and self.state == LDPSessionState.OPERATIONAL:
                    # Send keepalive
                    self.logger.debug("Sent Keepalive")

            except asyncio.CancelledError:
                break

    def add_binding(self, fec: FEC, local_label: int, remote_label: Optional[int] = None) -> None:
        """Add label binding"""
        binding = LabelBinding(
            fec=fec,
            local_label=local_label,
            remote_label=remote_label,
            peer_id=self.peer_id,
            next_hop=self.peer_ip,
        )
        self._bindings[fec] = binding

    def get_binding(self, fec: FEC) -> Optional[LabelBinding]:
        """Get binding for FEC"""
        return self._bindings.get(fec)

    def remove_binding(self, fec: FEC) -> Optional[LabelBinding]:
        """Remove binding for FEC"""
        return self._bindings.pop(fec, None)


class LDPSpeaker:
    """
    LDP Speaker - Main protocol engine.

    Manages LDP discovery, sessions, and label distribution.
    """

    def __init__(
        self,
        router_id: str,
        transport_ip: Optional[str] = None,
        label_range: Tuple[int, int] = (MIN_LABEL, MAX_LABEL),
    ):
        """
        Initialize LDP speaker.

        Args:
            router_id: Router ID (used as LDP ID)
            transport_ip: Transport address (defaults to router_id)
            label_range: Label allocation range
        """
        self.router_id = router_id
        self.ldp_id = f"{router_id}:0"
        self.transport_ip = transport_ip or router_id

        # Label allocator
        self.label_allocator = LabelAllocator(label_range[0], label_range[1])

        # LFIB
        self.lfib = LFIB()

        # Neighbors: {ldp_id: LDPNeighbor}
        self._neighbors: Dict[str, LDPNeighbor] = {}

        # Sessions: {ldp_id: LDPSession}
        self._sessions: Dict[str, LDPSession] = {}

        # Local bindings: {FEC: local_label}
        self._local_bindings: Dict[FEC, int] = {}

        # Interfaces enabled for LDP
        self._interfaces: Set[str] = set()

        # Tasks
        self._hello_task: Optional[asyncio.Task] = None
        self._listen_task: Optional[asyncio.Task] = None
        self._server: Optional[asyncio.Server] = None

        # Running state
        self.running = False

        self.logger = logging.getLogger(f"LDP[{router_id}]")

    def enable_interface(self, interface: str) -> None:
        """Enable LDP on interface"""
        self._interfaces.add(interface)
        self.logger.info(f"LDP enabled on {interface}")

    def disable_interface(self, interface: str) -> None:
        """Disable LDP on interface"""
        self._interfaces.discard(interface)

    async def start(self) -> None:
        """Start LDP speaker"""
        self.logger.info(f"Starting LDP speaker ID {self.ldp_id}")
        self.running = True

        # Start TCP listener for incoming sessions
        try:
            self._server = await asyncio.start_server(
                self._handle_connection,
                self.transport_ip,
                LDP_PORT
            )
            self.logger.info(f"Listening for LDP sessions on {self.transport_ip}:{LDP_PORT}")
        except Exception as e:
            self.logger.warning(f"Could not start LDP listener: {e}")

        # Start hello transmission
        self._hello_task = asyncio.create_task(self._hello_loop())

        self.logger.info("LDP speaker started")

    async def stop(self) -> None:
        """Stop LDP speaker"""
        self.logger.info("Stopping LDP speaker")
        self.running = False

        # Stop tasks
        if self._hello_task:
            self._hello_task.cancel()

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # Stop all sessions
        for session in list(self._sessions.values()):
            await session.stop()

        self.logger.info("LDP speaker stopped")

    async def _hello_loop(self) -> None:
        """Send periodic Hello messages"""
        while self.running:
            try:
                await asyncio.sleep(LDP_HELLO_INTERVAL)

                for interface in self._interfaces:
                    self._send_hello(interface)

                # Check neighbor timeouts
                self._check_neighbor_timeouts()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in hello loop: {e}")

    def _send_hello(self, interface: str) -> None:
        """Send Hello on interface"""
        # Would send multicast Hello to 224.0.0.2
        self.logger.debug(f"Sent Hello on {interface}")

    def _check_neighbor_timeouts(self) -> None:
        """Check for timed-out neighbors"""
        now = datetime.now()

        for ldp_id, neighbor in list(self._neighbors.items()):
            if neighbor.last_hello:
                elapsed = (now - neighbor.last_hello).total_seconds()
                if elapsed > neighbor.hold_time:
                    self.logger.warning(f"Neighbor {ldp_id} timed out")
                    asyncio.create_task(self._remove_neighbor(ldp_id))

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ) -> None:
        """Handle incoming TCP connection"""
        peer_addr = writer.get_extra_info('peername')
        if not peer_addr:
            self.logger.warning("Could not get peer address from connection")
            writer.close()
            return
        peer_ip = peer_addr[0]

        self.logger.info(f"Incoming LDP connection from {peer_ip}")

        # Find neighbor for this IP
        neighbor = None
        for n in self._neighbors.values():
            if n.transport_ip == peer_ip:
                neighbor = n
                break

        if not neighbor:
            self.logger.warning(f"No neighbor found for {peer_ip}")
            writer.close()
            return

        # Create or update session
        session = self._sessions.get(neighbor.ldp_id)
        if session:
            await session.accept(reader, writer)
        else:
            session = LDPSession(
                local_id=self.ldp_id,
                peer_id=neighbor.ldp_id,
                peer_ip=peer_ip,
                local_ip=self.transport_ip,
            )
            self._setup_session_callbacks(session)
            self._sessions[neighbor.ldp_id] = session
            await session.accept(reader, writer)

    def _setup_session_callbacks(self, session: LDPSession) -> None:
        """Setup callbacks for session"""
        session.on_session_up = lambda: self._on_session_up(session)
        session.on_session_down = lambda: self._on_session_down(session)
        session.on_binding_received = lambda fec, label: self._on_binding_received(
            session, fec, label
        )

    def _on_session_up(self, session: LDPSession) -> None:
        """Handle session becoming operational"""
        self.logger.info(f"Session UP with {session.peer_id}")

        # Send all local bindings
        for fec, label in self._local_bindings.items():
            asyncio.create_task(session.send_label_mapping(fec, label))

    def _on_session_down(self, session: LDPSession) -> None:
        """Handle session going down"""
        self.logger.info(f"Session DOWN with {session.peer_id}")

        # Remove bindings learned from this peer
        for fec in list(self._local_bindings.keys()):
            binding = session.get_binding(fec)
            if binding and binding.remote_label:
                # Remove from LFIB
                self.lfib.remove(binding.local_label)

    def _on_binding_received(self, session: LDPSession, fec: FEC, remote_label: int) -> None:
        """Handle received label binding"""
        self.logger.debug(f"Received binding from {session.peer_id}: {fec.prefix} -> {remote_label}")

        # Get or allocate local label
        local_label = self._local_bindings.get(fec)
        if local_label is None:
            local_label = self.label_allocator.allocate(f"FEC:{fec.prefix}")
            self._local_bindings[fec] = local_label

        # Update session binding
        session.add_binding(fec, local_label, remote_label)

        # Install LFIB entry
        entry = LFIBEntry(
            in_label=local_label,
            action=LabelAction.SWAP,
            out_labels=[remote_label],
            next_hop_type=NextHopType.IP_NEXTHOP,
            next_hop_ip=session.peer_ip,
            fec_prefix=fec.prefix,
            owner="ldp",
        )
        self.lfib.install(entry)

    async def _remove_neighbor(self, ldp_id: str) -> None:
        """Remove neighbor and its session"""
        neighbor = self._neighbors.pop(ldp_id, None)
        session = self._sessions.pop(ldp_id, None)

        if session:
            await session.stop()

    def receive_hello(
        self,
        interface: str,
        source_ip: str,
        ldp_id: str,
        hold_time: int,
        transport_ip: str,
    ) -> Optional[LDPNeighbor]:
        """
        Process received Hello message.

        Args:
            interface: Interface received on
            source_ip: Source IP of Hello
            ldp_id: Peer's LDP ID
            hold_time: Hold time from Hello
            transport_ip: Transport address from Hello

        Returns:
            LDP neighbor
        """
        if interface not in self._interfaces:
            return None

        neighbor = self._neighbors.get(ldp_id)

        if neighbor is None:
            neighbor = LDPNeighbor(
                ldp_id=ldp_id,
                transport_ip=transport_ip,
                interface=interface,
                hold_time=hold_time,
            )
            self._neighbors[ldp_id] = neighbor
            self.logger.info(f"New LDP neighbor: {ldp_id} via {interface}")

            # Initiate session
            asyncio.create_task(self._initiate_session(neighbor))

        neighbor.last_hello = datetime.now()
        neighbor.hold_time = hold_time

        return neighbor

    async def _initiate_session(self, neighbor: LDPNeighbor) -> None:
        """Initiate session with neighbor"""
        if neighbor.ldp_id in self._sessions:
            return

        session = LDPSession(
            local_id=self.ldp_id,
            peer_id=neighbor.ldp_id,
            peer_ip=neighbor.transport_ip,
            local_ip=self.transport_ip,
        )
        self._setup_session_callbacks(session)
        self._sessions[neighbor.ldp_id] = session

        await session.start()

    def advertise_fec(self, prefix: str) -> int:
        """
        Advertise FEC to all peers.

        Args:
            prefix: IP prefix to advertise

        Returns:
            Allocated local label
        """
        fec = FEC.from_prefix(prefix)

        # Allocate label if not already
        if fec not in self._local_bindings:
            label = self.label_allocator.allocate(f"FEC:{prefix}")
            self._local_bindings[fec] = label
        else:
            label = self._local_bindings[fec]

        # Send to all operational sessions
        for session in self._sessions.values():
            if session.state == LDPSessionState.OPERATIONAL:
                asyncio.create_task(session.send_label_mapping(fec, label))

        return label

    def withdraw_fec(self, prefix: str) -> None:
        """
        Withdraw FEC from all peers.

        Args:
            prefix: IP prefix to withdraw
        """
        fec = FEC.from_prefix(prefix)

        label = self._local_bindings.pop(fec, None)
        if label:
            self.label_allocator.release(label)

        # Send withdraw to all sessions
        for session in self._sessions.values():
            if session.state == LDPSessionState.OPERATIONAL:
                asyncio.create_task(session.send_label_withdraw(fec))

    def get_neighbors(self) -> List[LDPNeighbor]:
        """Get all LDP neighbors"""
        return list(self._neighbors.values())

    def get_sessions(self) -> List[LDPSession]:
        """Get all LDP sessions"""
        return list(self._sessions.values())

    def get_statistics(self) -> Dict[str, Any]:
        """Get LDP speaker statistics"""
        operational = sum(
            1 for s in self._sessions.values()
            if s.state == LDPSessionState.OPERATIONAL
        )

        return {
            "ldp_id": self.ldp_id,
            "transport_ip": self.transport_ip,
            "running": self.running,
            "interfaces": list(self._interfaces),
            "neighbors": len(self._neighbors),
            "sessions_total": len(self._sessions),
            "sessions_operational": operational,
            "local_bindings": len(self._local_bindings),
            "lfib_entries": self.lfib.get_entry_count(),
            "labels_allocated": self.label_allocator.get_allocation_count(),
        }
