"""
BFD - Bidirectional Forwarding Detection (RFC 5880, 5881, 5882)

Provides fast failure detection for network protocols.
BFD establishes sessions between peers and detects failures
in the forwarding path within milliseconds.

Features:
- Asynchronous mode with configurable timers
- Integration with OSPF, BGP, IS-IS
- Demand mode support
- Echo function support
- Multi-hop BFD (RFC 5883)

Usage:
    from bfd import BFDManager, BFDSessionConfig

    manager = BFDManager(local_address="10.0.0.1")
    await manager.start()

    # Create session to peer
    config = BFDSessionConfig(
        remote_address="10.0.0.2",
        desired_min_tx=100000,  # 100ms
        required_min_rx=100000,
        detect_mult=3
    )
    session = await manager.create_session(config)
"""

from .session import (
    BFDState,
    BFDDiagnostic,
    BFDSessionConfig,
    BFDSession,
    BFDSessionStats,
)
from .manager import BFDManager, get_bfd_manager, configure_bfd_manager
from .packet import BFDPacket, encode_bfd_packet, decode_bfd_packet
from .constants import (
    BFD_UDP_PORT,
    BFD_ECHO_PORT,
    BFD_MULTIHOP_PORT,
    BFD_VERSION,
    DEFAULT_DETECT_MULT,
    DEFAULT_MIN_TX_INTERVAL,
    DEFAULT_MIN_RX_INTERVAL,
)

__all__ = [
    # Session
    "BFDState",
    "BFDDiagnostic",
    "BFDSessionConfig",
    "BFDSession",
    "BFDSessionStats",
    # Manager
    "BFDManager",
    "get_bfd_manager",
    "configure_bfd_manager",
    # Packet
    "BFDPacket",
    "encode_bfd_packet",
    "decode_bfd_packet",
    # Constants
    "BFD_UDP_PORT",
    "BFD_ECHO_PORT",
    "BFD_MULTIHOP_PORT",
    "BFD_VERSION",
    "DEFAULT_DETECT_MULT",
    "DEFAULT_MIN_TX_INTERVAL",
    "DEFAULT_MIN_RX_INTERVAL",
]
