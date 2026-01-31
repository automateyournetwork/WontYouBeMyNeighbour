"""
BFD Session - RFC 5880 Section 6

Implements the BFD state machine and session management.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable, Dict, Any
from enum import Enum
from datetime import datetime

from .packet import BFDPacket, BFDState, BFDDiagnostic, encode_bfd_packet
from .constants import (
    DEFAULT_DETECT_MULT,
    DEFAULT_MIN_TX_INTERVAL,
    DEFAULT_MIN_RX_INTERVAL,
    MIN_TX_INTERVAL_FLOOR,
    MIN_RX_INTERVAL_FLOOR,
)

logger = logging.getLogger("BFD.Session")

# Re-export from packet for convenience
__all__ = [
    "BFDState",
    "BFDDiagnostic",
    "BFDSessionConfig",
    "BFDSession",
    "BFDSessionStats",
]


class BFDSessionType(Enum):
    """BFD session type"""
    SINGLE_HOP = "single_hop"
    MULTI_HOP = "multi_hop"
    ECHO = "echo"


@dataclass
class BFDSessionConfig:
    """
    BFD Session Configuration

    Attributes:
        remote_address: Peer IP address
        local_address: Local IP address (optional, auto-detect)
        interface: Interface name for single-hop
        desired_min_tx: Desired minimum TX interval (microseconds)
        required_min_rx: Required minimum RX interval (microseconds)
        detect_mult: Detection time multiplier
        session_type: Single-hop, multi-hop, or echo
        passive: If True, don't initiate - wait for peer
        demand_mode: Enable demand mode
        echo_mode: Enable echo function
        client_protocol: Protocol using BFD (ospf, bgp, isis, static)
    """
    remote_address: str
    local_address: str = ""
    interface: str = ""
    desired_min_tx: int = DEFAULT_MIN_TX_INTERVAL
    required_min_rx: int = DEFAULT_MIN_RX_INTERVAL
    detect_mult: int = DEFAULT_DETECT_MULT
    session_type: BFDSessionType = BFDSessionType.SINGLE_HOP
    passive: bool = False
    demand_mode: bool = False
    echo_mode: bool = False
    client_protocol: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "remote_address": self.remote_address,
            "local_address": self.local_address,
            "interface": self.interface,
            "desired_min_tx_us": self.desired_min_tx,
            "required_min_rx_us": self.required_min_rx,
            "detect_mult": self.detect_mult,
            "session_type": self.session_type.value,
            "passive": self.passive,
            "demand_mode": self.demand_mode,
            "echo_mode": self.echo_mode,
            "client_protocol": self.client_protocol,
        }


@dataclass
class BFDSessionStats:
    """BFD Session Statistics"""
    packets_sent: int = 0
    packets_received: int = 0
    packets_dropped: int = 0
    up_transitions: int = 0
    down_transitions: int = 0
    last_state_change: Optional[datetime] = None
    last_packet_sent: Optional[datetime] = None
    last_packet_received: Optional[datetime] = None
    session_uptime_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "packets_dropped": self.packets_dropped,
            "up_transitions": self.up_transitions,
            "down_transitions": self.down_transitions,
            "last_state_change": self.last_state_change.isoformat() if self.last_state_change else None,
            "last_packet_sent": self.last_packet_sent.isoformat() if self.last_packet_sent else None,
            "last_packet_received": self.last_packet_received.isoformat() if self.last_packet_received else None,
            "session_uptime_seconds": round(self.session_uptime_seconds, 3),
        }


class BFDSession:
    """
    BFD Session State Machine

    Implements RFC 5880 Section 6.8 state machine.

    States:
    - AdminDown: Session is administratively disabled
    - Down: Session is down, looking for peer
    - Init: Session detected peer, waiting for UP
    - Up: Session is established
    """

    def __init__(
        self,
        config: BFDSessionConfig,
        local_discriminator: int,
        send_callback: Callable[[bytes, str, int], Awaitable[None]],
    ):
        """
        Initialize BFD session

        Args:
            config: Session configuration
            local_discriminator: Unique local session identifier
            send_callback: Async callback to send packets
        """
        self.config = config
        self.local_discriminator = local_discriminator
        self._send_callback = send_callback

        # Session state
        self._state = BFDState.DOWN
        self._remote_state = BFDState.DOWN
        self._diagnostic = BFDDiagnostic.NO_DIAGNOSTIC
        self._remote_discriminator = 0

        # Negotiated intervals
        self._local_desired_min_tx = config.desired_min_tx
        self._local_required_min_rx = config.required_min_rx
        self._remote_min_rx = 1  # Start with minimum
        self._negotiated_tx_interval = config.desired_min_tx

        # Demand mode
        self._demand_mode_active = False
        self._poll_sequence = False

        # Timers
        self._detection_time = 0
        self._last_rx_time = 0.0
        self._tx_task: Optional[asyncio.Task] = None
        self._detect_task: Optional[asyncio.Task] = None

        # Statistics
        self.stats = BFDSessionStats()

        # Callbacks for state changes
        self._state_change_callbacks: list = []

        # Running flag
        self._running = False

        logger.info(
            f"[BFD] Created session {local_discriminator} to {config.remote_address} "
            f"(TX={config.desired_min_tx}us, RX={config.required_min_rx}us, mult={config.detect_mult})"
        )

    @property
    def state(self) -> BFDState:
        """Current session state"""
        return self._state

    @property
    def remote_discriminator(self) -> int:
        """Remote session discriminator"""
        return self._remote_discriminator

    @property
    def is_up(self) -> bool:
        """Check if session is UP"""
        return self._state == BFDState.UP

    @property
    def detection_time_ms(self) -> float:
        """Detection time in milliseconds"""
        return self._detection_time / 1000.0

    def register_state_change_callback(
        self,
        callback: Callable[["BFDSession", BFDState, BFDState], Awaitable[None]]
    ) -> None:
        """Register callback for state changes"""
        self._state_change_callbacks.append(callback)

    async def start(self) -> None:
        """Start the BFD session"""
        if self._running:
            return

        self._running = True
        self._last_rx_time = time.time()

        # Start TX task (unless passive)
        if not self.config.passive:
            self._tx_task = asyncio.create_task(self._tx_loop())

        # Start detection task
        self._detect_task = asyncio.create_task(self._detection_loop())

        logger.info(f"[BFD] Session {self.local_discriminator} started")

    async def stop(self) -> None:
        """Stop the BFD session"""
        if not self._running:
            return

        self._running = False

        # Cancel tasks
        if self._tx_task:
            self._tx_task.cancel()
            try:
                await self._tx_task
            except asyncio.CancelledError:
                pass

        if self._detect_task:
            self._detect_task.cancel()
            try:
                await self._detect_task
            except asyncio.CancelledError:
                pass

        logger.info(f"[BFD] Session {self.local_discriminator} stopped")

    async def admin_down(self) -> None:
        """Administratively disable the session"""
        await self._set_state(BFDState.ADMIN_DOWN, BFDDiagnostic.ADMIN_DOWN)

    async def admin_up(self) -> None:
        """Administratively enable the session"""
        if self._state == BFDState.ADMIN_DOWN:
            await self._set_state(BFDState.DOWN, BFDDiagnostic.NO_DIAGNOSTIC)

    async def process_packet(self, packet: BFDPacket, source_addr: str) -> None:
        """
        Process a received BFD packet

        Implements RFC 5880 Section 6.8.6

        Args:
            packet: Received BFD packet
            source_addr: Source IP address
        """
        self._last_rx_time = time.time()
        self.stats.packets_received += 1
        self.stats.last_packet_received = datetime.now()

        # Validate packet
        if not self._validate_packet(packet):
            self.stats.packets_dropped += 1
            return

        # Store remote state
        self._remote_state = packet.state
        self._remote_discriminator = packet.my_discriminator

        # Update remote RX capability
        if packet.required_min_rx > 0:
            self._remote_min_rx = packet.required_min_rx
            self._update_tx_interval()

        # Calculate detection time
        self._detection_time = packet.detect_mult * max(
            packet.desired_min_tx,
            self._local_required_min_rx
        )

        # Handle poll/final
        if packet.poll:
            await self._send_packet(final=True)

        if packet.final and self._poll_sequence:
            self._poll_sequence = False

        # State machine transitions (RFC 5880 Section 6.8.6)
        await self._process_state_machine(packet)

    def _validate_packet(self, packet: BFDPacket) -> bool:
        """Validate received BFD packet per RFC 5880 Section 6.8.6"""
        # Check version
        if packet.version != 1:
            logger.debug(f"[BFD] Invalid version: {packet.version}")
            return False

        # Check detect_mult
        if packet.detect_mult == 0:
            logger.debug("[BFD] Invalid detect_mult: 0")
            return False

        # Check multipoint (must be 0)
        if packet.multipoint:
            logger.debug("[BFD] Multipoint not supported")
            return False

        # Check my_discriminator
        if packet.my_discriminator == 0:
            logger.debug("[BFD] Invalid my_discriminator: 0")
            return False

        # Check your_discriminator if session exists
        if self._remote_discriminator != 0:
            if packet.your_discriminator == 0:
                logger.debug("[BFD] Expected your_discriminator")
                return False
            if packet.your_discriminator != self.local_discriminator:
                logger.debug(
                    f"[BFD] Discriminator mismatch: {packet.your_discriminator} != {self.local_discriminator}"
                )
                return False

        return True

    async def _process_state_machine(self, packet: BFDPacket) -> None:
        """
        Process state machine based on received packet

        RFC 5880 Section 6.8.6 State Machine
        """
        if self._state == BFDState.ADMIN_DOWN:
            return

        if self._state == BFDState.DOWN:
            if packet.state == BFDState.DOWN:
                await self._set_state(BFDState.INIT)
            elif packet.state == BFDState.INIT:
                await self._set_state(BFDState.UP)

        elif self._state == BFDState.INIT:
            if packet.state in [BFDState.INIT, BFDState.UP]:
                await self._set_state(BFDState.UP)

        elif self._state == BFDState.UP:
            if packet.state == BFDState.DOWN:
                await self._set_state(
                    BFDState.DOWN,
                    BFDDiagnostic.NEIGHBOR_SIGNALED_DOWN
                )

    async def _set_state(
        self,
        new_state: BFDState,
        diagnostic: BFDDiagnostic = BFDDiagnostic.NO_DIAGNOSTIC
    ) -> None:
        """Set session state and trigger callbacks"""
        if new_state == self._state:
            return

        old_state = self._state
        self._state = new_state
        self._diagnostic = diagnostic
        self.stats.last_state_change = datetime.now()

        if new_state == BFDState.UP:
            self.stats.up_transitions += 1
        elif old_state == BFDState.UP:
            self.stats.down_transitions += 1
            self.stats.session_uptime_seconds = 0.0

        logger.info(
            f"[BFD] Session {self.local_discriminator} state: {old_state.name} -> {new_state.name}"
        )

        # Trigger callbacks
        for callback in self._state_change_callbacks:
            try:
                await callback(self, old_state, new_state)
            except Exception as e:
                logger.error(f"[BFD] State change callback error: {e}")

    def _update_tx_interval(self) -> None:
        """Update negotiated TX interval"""
        self._negotiated_tx_interval = max(
            self._local_desired_min_tx,
            self._remote_min_rx
        )

    async def _tx_loop(self) -> None:
        """Transmit loop - send periodic BFD packets"""
        while self._running:
            try:
                # Calculate jitter (RFC 5880 Section 6.8.7)
                # TX interval with 0-25% jitter
                import random
                jitter = random.uniform(0.75, 1.0)
                interval_us = self._negotiated_tx_interval * jitter

                # Wait for interval
                await asyncio.sleep(interval_us / 1_000_000)

                # Send packet
                if self._running and self._state != BFDState.ADMIN_DOWN:
                    await self._send_packet()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[BFD] TX loop error: {e}")
                await asyncio.sleep(1)

    async def _detection_loop(self) -> None:
        """Detection loop - check for session timeout"""
        while self._running:
            try:
                # Check detection time
                if self._state == BFDState.UP:
                    elapsed = (time.time() - self._last_rx_time) * 1_000_000  # to microseconds

                    if elapsed > self._detection_time:
                        logger.warning(
                            f"[BFD] Session {self.local_discriminator} detection timeout "
                            f"({elapsed/1000:.1f}ms > {self._detection_time/1000:.1f}ms)"
                        )
                        await self._set_state(
                            BFDState.DOWN,
                            BFDDiagnostic.CONTROL_DETECTION_EXPIRED
                        )

                    # Update uptime
                    if self.stats.last_state_change:
                        self.stats.session_uptime_seconds = (
                            datetime.now() - self.stats.last_state_change
                        ).total_seconds()

                # Sleep for 1/3 of detection time or 100ms, whichever is smaller
                check_interval = min(
                    self._detection_time / 3_000_000 if self._detection_time > 0 else 0.1,
                    0.1
                )
                await asyncio.sleep(max(check_interval, 0.01))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[BFD] Detection loop error: {e}")
                await asyncio.sleep(1)

    async def _send_packet(self, final: bool = False) -> None:
        """Send a BFD control packet"""
        packet = BFDPacket(
            version=1,
            diagnostic=self._diagnostic,
            state=self._state,
            poll=self._poll_sequence and not final,
            final=final,
            control_plane_independent=False,
            authentication_present=False,
            demand_mode=self._demand_mode_active,
            multipoint=False,
            detect_mult=self.config.detect_mult,
            my_discriminator=self.local_discriminator,
            your_discriminator=self._remote_discriminator,
            desired_min_tx=self._local_desired_min_tx,
            required_min_rx=self._local_required_min_rx,
            required_min_echo_rx=0,
        )

        data = encode_bfd_packet(packet)

        try:
            from .constants import BFD_UDP_PORT, BFD_MULTIHOP_PORT

            port = (
                BFD_MULTIHOP_PORT
                if self.config.session_type == BFDSessionType.MULTI_HOP
                else BFD_UDP_PORT
            )

            await self._send_callback(data, self.config.remote_address, port)

            self.stats.packets_sent += 1
            self.stats.last_packet_sent = datetime.now()

        except Exception as e:
            logger.error(f"[BFD] Failed to send packet: {e}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary"""
        return {
            "local_discriminator": self.local_discriminator,
            "remote_discriminator": self._remote_discriminator,
            "state": self._state.name,
            "remote_state": self._remote_state.name,
            "diagnostic": self._diagnostic.name,
            "remote_address": self.config.remote_address,
            "local_address": self.config.local_address,
            "interface": self.config.interface,
            "session_type": self.config.session_type.value,
            "client_protocol": self.config.client_protocol,
            "detect_mult": self.config.detect_mult,
            "desired_min_tx_us": self._local_desired_min_tx,
            "required_min_rx_us": self._local_required_min_rx,
            "negotiated_tx_us": self._negotiated_tx_interval,
            "detection_time_ms": self.detection_time_ms,
            "is_up": self.is_up,
            "statistics": self.stats.to_dict(),
        }
