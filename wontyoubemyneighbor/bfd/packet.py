"""
BFD Packet - RFC 5880 Section 4

BFD Control Packet Format:
    0                   1                   2                   3
    0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |Vers |  Diag   |Sta|P|F|C|A|D|M|  Detect Mult  |    Length     |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |                       My Discriminator                        |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |                      Your Discriminator                       |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |                    Desired Min TX Interval                    |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |                   Required Min RX Interval                    |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |                 Required Min Echo RX Interval                 |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
"""

import struct
import logging
from dataclasses import dataclass
from typing import Optional
from enum import IntEnum

from .constants import BFD_VERSION, BFD_HEADER_LEN

logger = logging.getLogger("BFD.Packet")


class BFDState(IntEnum):
    """BFD session state (RFC 5880 Section 4.1)"""
    ADMIN_DOWN = 0
    DOWN = 1
    INIT = 2
    UP = 3


class BFDDiagnostic(IntEnum):
    """BFD diagnostic codes (RFC 5880 Section 4.1)"""
    NO_DIAGNOSTIC = 0
    CONTROL_DETECTION_EXPIRED = 1
    ECHO_FUNCTION_FAILED = 2
    NEIGHBOR_SIGNALED_DOWN = 3
    FORWARDING_PLANE_RESET = 4
    PATH_DOWN = 5
    CONCATENATED_PATH_DOWN = 6
    ADMIN_DOWN = 7
    REVERSE_CONCATENATED_PATH_DOWN = 8


@dataclass
class BFDPacket:
    """
    BFD Control Packet

    Attributes:
        version: Protocol version (must be 1)
        diagnostic: Diagnostic code
        state: Session state
        poll: Poll flag
        final: Final flag
        control_plane_independent: C flag
        authentication_present: A flag
        demand_mode: D flag
        multipoint: M flag (reserved)
        detect_mult: Detection time multiplier
        my_discriminator: Local discriminator
        your_discriminator: Remote discriminator
        desired_min_tx: Desired min TX interval (microseconds)
        required_min_rx: Required min RX interval (microseconds)
        required_min_echo_rx: Required min echo RX interval (microseconds)
    """
    version: int = BFD_VERSION
    diagnostic: BFDDiagnostic = BFDDiagnostic.NO_DIAGNOSTIC
    state: BFDState = BFDState.DOWN
    poll: bool = False
    final: bool = False
    control_plane_independent: bool = False
    authentication_present: bool = False
    demand_mode: bool = False
    multipoint: bool = False
    detect_mult: int = 3
    my_discriminator: int = 0
    your_discriminator: int = 0
    desired_min_tx: int = 1000000
    required_min_rx: int = 1000000
    required_min_echo_rx: int = 0
    length: int = BFD_HEADER_LEN

    def to_dict(self):
        return {
            "version": self.version,
            "diagnostic": self.diagnostic.name,
            "state": self.state.name,
            "poll": self.poll,
            "final": self.final,
            "control_plane_independent": self.control_plane_independent,
            "authentication_present": self.authentication_present,
            "demand_mode": self.demand_mode,
            "multipoint": self.multipoint,
            "detect_mult": self.detect_mult,
            "my_discriminator": self.my_discriminator,
            "your_discriminator": self.your_discriminator,
            "desired_min_tx_us": self.desired_min_tx,
            "required_min_rx_us": self.required_min_rx,
            "required_min_echo_rx_us": self.required_min_echo_rx,
        }


def encode_bfd_packet(packet: BFDPacket) -> bytes:
    """
    Encode a BFD packet to bytes

    Args:
        packet: BFD packet to encode

    Returns:
        Encoded packet bytes
    """
    # Byte 0: Version (3 bits) + Diagnostic (5 bits)
    byte0 = ((packet.version & 0x07) << 5) | (int(packet.diagnostic) & 0x1F)

    # Byte 1: State (2 bits) + Flags (6 bits)
    byte1 = ((int(packet.state) & 0x03) << 6)
    if packet.poll:
        byte1 |= 0x20
    if packet.final:
        byte1 |= 0x10
    if packet.control_plane_independent:
        byte1 |= 0x08
    if packet.authentication_present:
        byte1 |= 0x04
    if packet.demand_mode:
        byte1 |= 0x02
    if packet.multipoint:
        byte1 |= 0x01

    # Pack the header
    header = struct.pack(
        "!BBBBI III",
        byte0,
        byte1,
        packet.detect_mult & 0xFF,
        packet.length & 0xFF,
        packet.my_discriminator,
        packet.your_discriminator,
        packet.desired_min_tx,
        packet.required_min_rx,
        packet.required_min_echo_rx,
    )

    return header


def decode_bfd_packet(data: bytes) -> Optional[BFDPacket]:
    """
    Decode a BFD packet from bytes

    Args:
        data: Raw packet bytes

    Returns:
        Decoded BFDPacket or None if invalid
    """
    if len(data) < BFD_HEADER_LEN:
        logger.warning(f"BFD packet too short: {len(data)} bytes")
        return None

    try:
        # Unpack header
        byte0, byte1, detect_mult, length, my_disc, your_disc, \
            desired_min_tx, required_min_rx, required_min_echo_rx = struct.unpack(
                "!BBBBI III", data[:24]
            )

        # Parse byte 0
        version = (byte0 >> 5) & 0x07
        diagnostic = byte0 & 0x1F

        # Verify version
        if version != BFD_VERSION:
            logger.warning(f"Invalid BFD version: {version}")
            return None

        # Parse byte 1
        state = (byte1 >> 6) & 0x03
        poll = bool(byte1 & 0x20)
        final = bool(byte1 & 0x10)
        cpi = bool(byte1 & 0x08)
        auth = bool(byte1 & 0x04)
        demand = bool(byte1 & 0x02)
        multipoint = bool(byte1 & 0x01)

        return BFDPacket(
            version=version,
            diagnostic=BFDDiagnostic(diagnostic),
            state=BFDState(state),
            poll=poll,
            final=final,
            control_plane_independent=cpi,
            authentication_present=auth,
            demand_mode=demand,
            multipoint=multipoint,
            detect_mult=detect_mult,
            length=length,
            my_discriminator=my_disc,
            your_discriminator=your_disc,
            desired_min_tx=desired_min_tx,
            required_min_rx=required_min_rx,
            required_min_echo_rx=required_min_echo_rx,
        )

    except (struct.error, ValueError) as e:
        logger.error(f"Failed to decode BFD packet: {e}")
        return None
