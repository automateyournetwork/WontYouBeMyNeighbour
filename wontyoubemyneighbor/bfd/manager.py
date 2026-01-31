"""
BFD Manager - Multi-session management and protocol integration

Manages multiple BFD sessions and provides integration points
for OSPF, BGP, IS-IS, and other protocols.
"""

import asyncio
import socket
import logging
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Awaitable, Any
from datetime import datetime

from .session import BFDSession, BFDSessionConfig, BFDState, BFDSessionType
from .packet import BFDPacket, decode_bfd_packet
from .constants import (
    BFD_UDP_PORT,
    BFD_MULTIHOP_PORT,
    BFD_SINGLE_HOP_TTL,
    BFD_DSCP,
    MAX_SESSIONS_DEFAULT,
    DEFAULT_DETECT_MULT,
    DEFAULT_MIN_TX_INTERVAL,
    DEFAULT_MIN_RX_INTERVAL,
    FAST_MIN_TX_INTERVAL,
    FAST_MIN_RX_INTERVAL,
)

logger = logging.getLogger("BFD.Manager")


@dataclass
class BFDManagerConfig:
    """BFD Manager Configuration"""
    local_address: str = "0.0.0.0"
    max_sessions: int = MAX_SESSIONS_DEFAULT
    default_detect_mult: int = DEFAULT_DETECT_MULT
    default_min_tx: int = DEFAULT_MIN_TX_INTERVAL
    default_min_rx: int = DEFAULT_MIN_RX_INTERVAL
    enabled: bool = True

    # Protocol integration defaults
    ospf_enabled: bool = True
    ospf_min_tx: int = FAST_MIN_TX_INTERVAL  # 100ms for OSPF
    ospf_min_rx: int = FAST_MIN_RX_INTERVAL
    ospf_detect_mult: int = 3

    bgp_enabled: bool = True
    bgp_min_tx: int = FAST_MIN_TX_INTERVAL  # 100ms for BGP
    bgp_min_rx: int = FAST_MIN_RX_INTERVAL
    bgp_detect_mult: int = 3

    isis_enabled: bool = True
    isis_min_tx: int = FAST_MIN_TX_INTERVAL  # 100ms for IS-IS
    isis_min_rx: int = FAST_MIN_RX_INTERVAL
    isis_detect_mult: int = 3

    static_enabled: bool = True
    static_min_tx: int = DEFAULT_MIN_TX_INTERVAL  # 1s for static routes
    static_min_rx: int = DEFAULT_MIN_RX_INTERVAL
    static_detect_mult: int = 3


@dataclass
class BFDManagerStats:
    """BFD Manager Statistics"""
    total_sessions: int = 0
    up_sessions: int = 0
    down_sessions: int = 0
    packets_sent: int = 0
    packets_received: int = 0
    packets_dropped: int = 0
    state_changes: int = 0
    started_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_sessions": self.total_sessions,
            "up_sessions": self.up_sessions,
            "down_sessions": self.down_sessions,
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "packets_dropped": self.packets_dropped,
            "state_changes": self.state_changes,
            "started_at": self.started_at.isoformat() if self.started_at else None,
        }


class BFDManager:
    """
    BFD Session Manager

    Manages multiple BFD sessions and provides protocol integration.
    Handles UDP socket communication for BFD control packets.
    """

    def __init__(self, config: Optional[BFDManagerConfig] = None, agent_id: str = ""):
        """
        Initialize BFD manager

        Args:
            config: Manager configuration
            agent_id: Agent identifier for logging
        """
        self.config = config or BFDManagerConfig()
        self.agent_id = agent_id

        # Session management
        self._sessions: Dict[int, BFDSession] = {}  # discriminator -> session
        self._sessions_by_peer: Dict[str, BFDSession] = {}  # peer_ip -> session
        self._next_discriminator = random.randint(1, 0x7FFFFFFF)

        # Statistics
        self.stats = BFDManagerStats()

        # Protocol callbacks
        self._protocol_callbacks: Dict[str, Callable[[BFDSession, BFDState, BFDState], Awaitable[None]]] = {}

        # Socket
        self._socket: Optional[socket.socket] = None
        self._receive_task: Optional[asyncio.Task] = None

        # Running state
        self._running = False

        logger.info(f"[BFD] Manager initialized for {agent_id or 'local'}")

    @property
    def is_running(self) -> bool:
        """Check if manager is running"""
        return self._running

    @property
    def session_count(self) -> int:
        """Total number of sessions"""
        return len(self._sessions)

    @property
    def up_session_count(self) -> int:
        """Number of UP sessions"""
        return sum(1 for s in self._sessions.values() if s.is_up)

    async def start(self) -> None:
        """Start the BFD manager"""
        if self._running:
            logger.warning("[BFD] Manager already running")
            return

        if not self.config.enabled:
            logger.info("[BFD] Manager disabled by configuration")
            return

        try:
            # Create UDP socket
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Set TTL for single-hop BFD
            self._socket.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, BFD_SINGLE_HOP_TTL)

            # Set DSCP/TOS
            self._socket.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, BFD_DSCP << 2)

            # Bind to BFD port
            self._socket.bind((self.config.local_address, BFD_UDP_PORT))
            self._socket.setblocking(False)

            self._running = True
            self.stats.started_at = datetime.now()

            # Start receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())

            logger.info(f"[BFD] Manager started on {self.config.local_address}:{BFD_UDP_PORT}")

        except PermissionError:
            logger.warning(
                f"[BFD] Cannot bind to port {BFD_UDP_PORT} (requires root). "
                "BFD will run in simulation mode."
            )
            self._running = True
            self.stats.started_at = datetime.now()

        except Exception as e:
            logger.error(f"[BFD] Failed to start manager: {e}")
            raise

    async def stop(self) -> None:
        """Stop the BFD manager"""
        if not self._running:
            return

        self._running = False

        # Stop all sessions
        for session in list(self._sessions.values()):
            await session.stop()

        # Cancel receive task
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        # Close socket
        if self._socket:
            self._socket.close()
            self._socket = None

        logger.info("[BFD] Manager stopped")

    def _allocate_discriminator(self) -> int:
        """Allocate a unique session discriminator"""
        disc = self._next_discriminator
        self._next_discriminator += 1
        if self._next_discriminator > 0xFFFFFFFF:
            self._next_discriminator = 1
        return disc

    async def create_session(
        self,
        config: BFDSessionConfig
    ) -> BFDSession:
        """
        Create a new BFD session

        Args:
            config: Session configuration

        Returns:
            Created BFD session
        """
        # Check for existing session
        if config.remote_address in self._sessions_by_peer:
            logger.warning(f"[BFD] Session to {config.remote_address} already exists")
            return self._sessions_by_peer[config.remote_address]

        # Check max sessions
        if len(self._sessions) >= self.config.max_sessions:
            raise RuntimeError(f"Maximum sessions ({self.config.max_sessions}) reached")

        # Allocate discriminator
        discriminator = self._allocate_discriminator()

        # Create session
        session = BFDSession(
            config=config,
            local_discriminator=discriminator,
            send_callback=self._send_packet,
        )

        # Register state change callback
        session.register_state_change_callback(self._on_session_state_change)

        # Store session
        self._sessions[discriminator] = session
        self._sessions_by_peer[config.remote_address] = session
        self.stats.total_sessions += 1

        # Start session
        await session.start()

        logger.info(f"[BFD] Created session {discriminator} to {config.remote_address}")

        return session

    async def create_session_for_protocol(
        self,
        protocol: str,
        peer_address: str,
        local_address: str = "",
        interface: str = "",
    ) -> BFDSession:
        """
        Create a BFD session for a specific protocol with recommended timers

        Args:
            protocol: Protocol name (ospf, bgp, isis, static)
            peer_address: Peer IP address
            local_address: Local IP address
            interface: Interface name

        Returns:
            Created BFD session
        """
        protocol = protocol.lower()

        # Get protocol-specific settings
        if protocol == "ospf":
            if not self.config.ospf_enabled:
                raise RuntimeError("BFD for OSPF is disabled")
            min_tx = self.config.ospf_min_tx
            min_rx = self.config.ospf_min_rx
            detect_mult = self.config.ospf_detect_mult

        elif protocol == "bgp":
            if not self.config.bgp_enabled:
                raise RuntimeError("BFD for BGP is disabled")
            min_tx = self.config.bgp_min_tx
            min_rx = self.config.bgp_min_rx
            detect_mult = self.config.bgp_detect_mult

        elif protocol == "isis":
            if not self.config.isis_enabled:
                raise RuntimeError("BFD for IS-IS is disabled")
            min_tx = self.config.isis_min_tx
            min_rx = self.config.isis_min_rx
            detect_mult = self.config.isis_detect_mult

        elif protocol == "static":
            if not self.config.static_enabled:
                raise RuntimeError("BFD for static routes is disabled")
            min_tx = self.config.static_min_tx
            min_rx = self.config.static_min_rx
            detect_mult = self.config.static_detect_mult

        else:
            # Default settings
            min_tx = self.config.default_min_tx
            min_rx = self.config.default_min_rx
            detect_mult = self.config.default_detect_mult

        config = BFDSessionConfig(
            remote_address=peer_address,
            local_address=local_address,
            interface=interface,
            desired_min_tx=min_tx,
            required_min_rx=min_rx,
            detect_mult=detect_mult,
            client_protocol=protocol,
        )

        return await self.create_session(config)

    async def delete_session(self, peer_address: str) -> bool:
        """
        Delete a BFD session

        Args:
            peer_address: Peer IP address

        Returns:
            True if session was deleted
        """
        session = self._sessions_by_peer.get(peer_address)
        if not session:
            return False

        await session.stop()

        del self._sessions[session.local_discriminator]
        del self._sessions_by_peer[peer_address]

        logger.info(f"[BFD] Deleted session to {peer_address}")

        return True

    def get_session(self, peer_address: str) -> Optional[BFDSession]:
        """Get session by peer address"""
        return self._sessions_by_peer.get(peer_address)

    def get_session_by_discriminator(self, discriminator: int) -> Optional[BFDSession]:
        """Get session by discriminator"""
        return self._sessions.get(discriminator)

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all sessions"""
        return [s.to_dict() for s in self._sessions.values()]

    def register_protocol_callback(
        self,
        protocol: str,
        callback: Callable[[BFDSession, BFDState, BFDState], Awaitable[None]]
    ) -> None:
        """
        Register callback for protocol-specific state changes

        Args:
            protocol: Protocol name
            callback: Async callback (session, old_state, new_state)
        """
        self._protocol_callbacks[protocol.lower()] = callback
        logger.info(f"[BFD] Registered callback for {protocol}")

    async def _on_session_state_change(
        self,
        session: BFDSession,
        old_state: BFDState,
        new_state: BFDState
    ) -> None:
        """Handle session state changes"""
        self.stats.state_changes += 1

        # Update stats
        self.stats.up_sessions = self.up_session_count
        self.stats.down_sessions = len(self._sessions) - self.stats.up_sessions

        # Call protocol-specific callback
        protocol = session.config.client_protocol.lower()
        if protocol in self._protocol_callbacks:
            try:
                await self._protocol_callbacks[protocol](session, old_state, new_state)
            except Exception as e:
                logger.error(f"[BFD] Protocol callback error for {protocol}: {e}")

    async def _send_packet(self, data: bytes, remote_addr: str, port: int) -> None:
        """Send a BFD packet"""
        if not self._socket:
            # Simulation mode - just log
            logger.debug(f"[BFD] SIM: Send {len(data)} bytes to {remote_addr}:{port}")
            return

        try:
            loop = asyncio.get_event_loop()
            await loop.sock_sendto(self._socket, data, (remote_addr, port))
            self.stats.packets_sent += 1
        except Exception as e:
            logger.error(f"[BFD] Failed to send to {remote_addr}: {e}")

    async def _receive_loop(self) -> None:
        """Receive loop for BFD packets"""
        if not self._socket:
            return

        loop = asyncio.get_event_loop()

        while self._running:
            try:
                data, addr = await loop.sock_recvfrom(self._socket, 1024)
                source_ip = addr[0]
                self.stats.packets_received += 1

                # Decode packet
                packet = decode_bfd_packet(data)
                if not packet:
                    self.stats.packets_dropped += 1
                    continue

                # Find session by your_discriminator or source IP
                session = None
                if packet.your_discriminator != 0:
                    session = self._sessions.get(packet.your_discriminator)
                if not session:
                    session = self._sessions_by_peer.get(source_ip)

                if session:
                    await session.process_packet(packet, source_ip)
                else:
                    # Unknown session - could create one if passive mode
                    logger.debug(f"[BFD] Received packet from unknown peer {source_ip}")
                    self.stats.packets_dropped += 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[BFD] Receive error: {e}")
                await asyncio.sleep(0.1)

    def get_status(self) -> Dict[str, Any]:
        """Get manager status"""
        return {
            "enabled": self.config.enabled,
            "running": self._running,
            "local_address": self.config.local_address,
            "agent_id": self.agent_id,
            "sessions": self.list_sessions(),
            "statistics": self.stats.to_dict(),
            "protocol_integration": {
                "ospf": self.config.ospf_enabled,
                "bgp": self.config.bgp_enabled,
                "isis": self.config.isis_enabled,
                "static": self.config.static_enabled,
            }
        }


# Global BFD manager instance
_bfd_managers: Dict[str, BFDManager] = {}


def get_bfd_manager(agent_id: str = "default") -> BFDManager:
    """
    Get or create BFD manager for an agent

    Args:
        agent_id: Agent identifier

    Returns:
        BFD manager instance
    """
    if agent_id not in _bfd_managers:
        _bfd_managers[agent_id] = BFDManager(agent_id=agent_id)
    return _bfd_managers[agent_id]


def configure_bfd_manager(
    agent_id: str,
    config: BFDManagerConfig
) -> BFDManager:
    """
    Configure and return BFD manager for an agent

    Args:
        agent_id: Agent identifier
        config: Manager configuration

    Returns:
        Configured BFD manager
    """
    manager = BFDManager(config=config, agent_id=agent_id)
    _bfd_managers[agent_id] = manager
    return manager
