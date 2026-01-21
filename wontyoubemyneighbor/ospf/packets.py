"""
OSPF Packet Definitions using Scapy
RFC 2328 compliant packet structures
"""

from scapy.all import Packet, bind_layers
from scapy.fields import (
    ByteField, ByteEnumField, ShortField, ShortEnumField, IntField, IntEnumField, IPField,
    XShortField, XLongField, FieldListField, PacketListField,
    BitField, X3BytesField, StrFixedLenField
)
import struct
from typing import Optional

from .constants import (
    OSPF_VERSION, PACKET_TYPES, AUTH_TYPE_NAMES,
    LSA_TYPE_NAMES, LINK_TYPE_NAMES
)


# ============================================================================
# Helper Functions
# ============================================================================

def ospf_checksum(data: bytes) -> int:
    """
    Calculate OSPF checksum (standard IP checksum, RFC 905)
    Excludes authentication field (last 8 bytes of OSPF header)
    """
    # Create checksum data excluding auth field
    if len(data) < 24:
        return 0

    # Header without checksum and without auth
    checksum_data = data[:12] + b'\x00\x00' + data[14:16]

    # Add payload after header
    if len(data) > 24:
        checksum_data += data[24:]

    # Pad if odd length
    if len(checksum_data) % 2:
        checksum_data += b'\x00'

    # Calculate sum
    s = sum(struct.unpack('!%dH' % (len(checksum_data) // 2), checksum_data))
    s = (s >> 16) + (s & 0xffff)
    s += s >> 16

    return ~s & 0xffff


def fletcher_checksum(data: bytes, offset: int = 2) -> int:
    """
    Calculate OSPF LSA Fletcher-16 checksum per RFC 2328 Appendix B

    Direct port from FRRouting's ospfd/ospf_lsa.c fletcher_checksum() function.

    Args:
        data: LSA bytes with age=0 and checksum=0
        offset: Offset to start (2 to skip age field)

    Returns:
        16-bit Fletcher checksum
    """
    # Checksum goes at bytes 16-17 (LS Checksum field in LSA header)
    CHECKSUM_OFFSET = 16

    c0 = 0
    c1 = 0

    # Calculate C0 and C1 over the entire buffer starting from offset
    for i in range(offset, len(data)):
        c0 = c0 + data[i]
        c1 = c1 + c0

    c0 = c0 % 255
    c1 = c1 % 255

    # Calculate position of checksum in buffer from our starting offset
    # Checksum is at byte 16, we start at byte 2 (offset), so position is 14
    p = CHECKSUM_OFFSET - offset  # Should be 14 for offset=2

    # Number of bytes in the packet from our offset
    l = len(data) - offset

    # Calculate x and y per ISO 8473
    x = (((l - p - 1) * c0 - c1) % 255)
    if x <= 0:
        x = x + 255

    y = 510 - c0 - x
    if y > 255:
        y = y - 255
    if y <= 0:
        y = y + 255

    # Checksum is x in MSB, y in LSB
    checksum = (x << 8) + y

    return checksum


# ============================================================================
# OSPF Header (24 bytes) - Common to all OSPF packets
# ============================================================================

class OSPFHeader(Packet):
    """
    OSPF Header - RFC 2328 Section A.3.1
    24 bytes, present in all OSPF packets
    """
    name = "OSPF Header"
    fields_desc = [
        ByteField("version", OSPF_VERSION),
        ByteEnumField("type", 1, PACKET_TYPES),
        ShortField("len", None),  # Auto-calculated
        IPField("router_id", "0.0.0.0"),
        IPField("area_id", "0.0.0.0"),
        XShortField("chksum", None),  # Auto-calculated
        ShortEnumField("auth_type", 0, AUTH_TYPE_NAMES),
        XLongField("auth_data", 0)
    ]

    def post_build(self, p, pay):
        """Auto-calculate length and checksum if not provided"""
        # Calculate length
        if self.len is None:
            length = len(p) + len(pay)
            p = p[:2] + struct.pack("!H", length) + p[4:]

        # Calculate checksum
        if self.chksum is None:
            # Temporarily set checksum to 0
            p = p[:12] + b'\x00\x00' + p[14:]
            # Calculate over entire packet
            ck = ospf_checksum(p + pay)
            p = p[:12] + struct.pack("!H", ck) + p[14:]

        return p + pay


# ============================================================================
# Hello Packet (Type 1) - RFC 2328 Section A.3.2
# ============================================================================

class OSPFHello(Packet):
    """
    OSPF Hello Packet - RFC 2328 Section A.3.2
    Used for neighbor discovery and maintenance
    """
    name = "OSPF Hello"
    fields_desc = [
        IPField("network_mask", "255.255.255.0"),
        ShortField("hello_interval", 10),
        ByteField("options", 0x02),  # E-bit set by default
        ByteField("router_priority", 1),
        IntField("router_dead_interval", 40),
        IPField("designated_router", "0.0.0.0"),
        IPField("backup_designated_router", "0.0.0.0"),
        FieldListField("neighbors", [], IPField("", "0.0.0.0"))
    ]


# ============================================================================
# Database Description Packet (Type 2) - RFC 2328 Section A.3.3
# ============================================================================

class OSPFDBDescription(Packet):
    """
    OSPF Database Description Packet - RFC 2328 Section A.3.3
    Used during adjacency formation to exchange LSDB summaries
    """
    name = "OSPF Database Description"
    fields_desc = [
        ShortField("interface_mtu", 1500),
        ByteField("options", 0x02),
        ByteField("flags", 0x00),  # I, M, MS bits
        IntField("dd_sequence", 0)
        # LSA headers will be added as payload
    ]

    def has_init(self) -> bool:
        """Check if Init bit is set"""
        return bool(self.flags & 0x04)

    def has_more(self) -> bool:
        """Check if More bit is set"""
        return bool(self.flags & 0x02)

    def is_master(self) -> bool:
        """Check if Master/Slave bit is set (1 = Master)"""
        return bool(self.flags & 0x01)

    def set_flags(self, init: bool = False, more: bool = False, master: bool = False):
        """Set DBD flags"""
        self.flags = (int(init) << 2) | (int(more) << 1) | int(master)


# ============================================================================
# Link State Request (Type 3) - RFC 2328 Section A.3.4
# ============================================================================

class LSRequest(Packet):
    """
    Single LS Request entry
    """
    name = "LS Request"
    fields_desc = [
        IntEnumField("ls_type", 1, LSA_TYPE_NAMES),
        IPField("link_state_id", "0.0.0.0"),
        IPField("advertising_router", "0.0.0.0")
    ]


class OSPFLSRequest(Packet):
    """
    OSPF Link State Request Packet - RFC 2328 Section A.3.4
    Request specific LSAs from neighbor
    """
    name = "OSPF Link State Request"
    fields_desc = [
        PacketListField("requests", [], LSRequest)
    ]


# ============================================================================
# Link State Update (Type 4) - RFC 2328 Section A.3.5
# ============================================================================

class OSPFLSUpdate(Packet):
    """
    OSPF Link State Update Packet - RFC 2328 Section A.3.5
    Contains full LSAs (flooding)
    """
    name = "OSPF Link State Update"
    fields_desc = [
        IntField("num_lsas", None)  # Auto-calculated
        # LSAs will be added as payload
    ]

    def post_build(self, p, pay):
        """Auto-calculate number of LSAs if not provided"""
        if self.num_lsas is None:
            # Count LSAs in payload (this is simplified)
            # In real implementation, would count LSA packets
            num = 0
            p = struct.pack("!I", num) + p[4:]
        return p + pay


# ============================================================================
# Link State Acknowledgment (Type 5) - RFC 2328 Section A.3.6
# ============================================================================

class OSPFLSAck(Packet):
    """
    OSPF Link State Acknowledgment Packet - RFC 2328 Section A.3.6
    Acknowledge receipt of LSAs (contains LSA headers only)
    """
    name = "OSPF Link State Acknowledgment"
    fields_desc = []
    # LSA headers will be added as payload


# ============================================================================
# LSA Header (20 bytes) - RFC 2328 Section A.4.1
# ============================================================================

class LSAHeader(Packet):
    """
    LSA Header - RFC 2328 Section A.4.1
    20 bytes, common to all LSA types
    """
    name = "LSA Header"
    fields_desc = [
        ShortField("ls_age", 0),
        ByteField("options", 0x02),
        ByteEnumField("ls_type", 1, LSA_TYPE_NAMES),
        IPField("link_state_id", "0.0.0.0"),
        IPField("advertising_router", "0.0.0.0"),
        IntField("ls_sequence_number", 0x80000001),
        XShortField("ls_checksum", None),  # Auto-calculated
        ShortField("length", None)  # Auto-calculated
    ]

    def post_build(self, p, pay):
        """Auto-calculate length and checksum if not provided"""
        # Calculate length
        if self.length is None:
            length = len(p) + len(pay)
            p = p[:18] + struct.pack("!H", length) + p[20:]

        # Calculate checksum (Fletcher)
        if self.ls_checksum is None:
            # Set age to 0 for checksum calculation
            temp_data = b'\x00\x00' + p[2:16] + b'\x00\x00' + p[18:]
            temp_data += pay
            ck = fletcher_checksum(temp_data, offset=2)
            p = p[:16] + struct.pack("!H", ck) + p[18:]

        return p + pay


# ============================================================================
# Router LSA (Type 1) - RFC 2328 Section A.4.2
# ============================================================================

class RouterLink(Packet):
    """
    Single router link in Router LSA
    """
    name = "Router Link"
    fields_desc = [
        IPField("link_id", "0.0.0.0"),
        IPField("link_data", "0.0.0.0"),
        ByteEnumField("link_type", 3, LINK_TYPE_NAMES),
        ByteField("num_tos", 0),
        ShortField("metric", 1)
    ]


class RouterLSA(Packet):
    """
    Router LSA - RFC 2328 Section A.4.2
    Describes router's links and state
    """
    name = "Router LSA"
    fields_desc = [
        BitField("reserved1", 0, 5),
        BitField("v_bit", 0, 1),  # Virtual link endpoint
        BitField("e_bit", 0, 1),  # AS boundary router
        BitField("b_bit", 0, 1),  # Area border router
        ByteField("reserved2", 0),
        ShortField("num_links", None),  # Auto-calculated
        PacketListField("links", [], RouterLink,
                       count_from=lambda pkt: pkt.num_links)
    ]

    def post_build(self, p, pay):
        """Auto-calculate number of links if not provided"""
        if self.num_links is None:
            num = len(self.links)
            p = p[:2] + struct.pack("!H", num) + p[4:]
        return p + pay


# ============================================================================
# Network LSA (Type 2) - RFC 2328 Section A.4.3
# ============================================================================

class NetworkLSA(Packet):
    """
    Network LSA - RFC 2328 Section A.4.3
    Generated by DR for multi-access networks
    """
    name = "Network LSA"
    fields_desc = [
        IPField("network_mask", "255.255.255.0"),
        FieldListField("attached_routers", [], IPField("", "0.0.0.0"))
    ]


# ============================================================================
# Summary LSA (Type 3/4) - RFC 2328 Section A.4.4
# ============================================================================

class SummaryLSA(Packet):
    """
    Summary LSA - RFC 2328 Section A.4.4
    Type 3: IP network summary
    Type 4: ASBR summary
    """
    name = "Summary LSA"
    fields_desc = [
        IPField("network_mask", "255.255.255.0"),
        ByteField("reserved", 0),
        X3BytesField("metric", 1)
    ]


# ============================================================================
# AS External LSA (Type 5) - RFC 2328 Section A.4.5
# ============================================================================

class ASExternalLSA(Packet):
    """
    AS External LSA - RFC 2328 Section A.4.5
    Describes routes to external destinations
    """
    name = "AS External LSA"
    fields_desc = [
        IPField("network_mask", "255.255.255.0"),
        BitField("e_bit", 0, 1),  # External metric type
        BitField("reserved", 0, 7),
        X3BytesField("metric", 1),
        IPField("forwarding_address", "0.0.0.0"),
        IntField("external_route_tag", 0)
    ]


# ============================================================================
# NSSA External LSA (Type 7) - RFC 3101
# ============================================================================

class NSSAExternalLSA(Packet):
    """
    NSSA External LSA - RFC 3101
    Used in Not-So-Stubby Areas to carry external routes.
    Same format as AS External LSA but only flooded within the NSSA.
    Converted to Type 5 at the NSSA ABR.
    """
    name = "NSSA External LSA"
    fields_desc = [
        IPField("network_mask", "255.255.255.0"),
        BitField("e_bit", 0, 1),  # External metric type (E1=0, E2=1)
        BitField("reserved", 0, 7),
        X3BytesField("metric", 1),
        IPField("forwarding_address", "0.0.0.0"),
        IntField("external_route_tag", 0)
    ]


# ============================================================================
# Bind Layers
# ============================================================================

# Bind OSPF packet types to OSPF header
bind_layers(OSPFHeader, OSPFHello, type=1)
bind_layers(OSPFHeader, OSPFDBDescription, type=2)
bind_layers(OSPFHeader, OSPFLSRequest, type=3)
bind_layers(OSPFHeader, OSPFLSUpdate, type=4)
bind_layers(OSPFHeader, OSPFLSAck, type=5)

# Bind LSA types to LSA header
bind_layers(LSAHeader, RouterLSA, ls_type=1)
bind_layers(LSAHeader, NetworkLSA, ls_type=2)
bind_layers(LSAHeader, SummaryLSA, ls_type=3)
bind_layers(LSAHeader, SummaryLSA, ls_type=4)
bind_layers(LSAHeader, ASExternalLSA, ls_type=5)
bind_layers(LSAHeader, NSSAExternalLSA, ls_type=7)


# ============================================================================
# Utility Functions
# ============================================================================

def parse_ospf_packet(data: bytes) -> Optional[OSPFHeader]:
    """
    Parse raw bytes into OSPF packet

    Args:
        data: Raw packet bytes

    Returns:
        OSPFHeader packet object or None if invalid
    """
    try:
        return OSPFHeader(data)
    except Exception as e:
        return None


def build_hello_packet(router_id: str, area_id: str,
                      network_mask: str = "255.255.255.0",
                      neighbors: list = None) -> bytes:
    """
    Build a Hello packet

    Args:
        router_id: Router ID
        area_id: Area ID
        network_mask: Network mask
        neighbors: List of neighbor router IDs

    Returns:
        Packet as bytes
    """
    if neighbors is None:
        neighbors = []

    header = OSPFHeader(
        type=1,
        router_id=router_id,
        area_id=area_id,
        auth_type=0
    )

    hello = OSPFHello(
        network_mask=network_mask,
        hello_interval=10,
        router_dead_interval=40,
        neighbors=neighbors
    )

    packet = header / hello
    return bytes(packet)


def build_router_lsa(router_id: str, links: list) -> tuple:
    """
    Build a Router LSA

    Args:
        router_id: Router ID
        links: List of dicts with link information

    Returns:
        Tuple of (LSAHeader, RouterLSA) as bytes
    """
    # Build router links
    router_links = []
    for link in links:
        router_link = RouterLink(
            link_id=link.get('link_id', '0.0.0.0'),
            link_data=link.get('link_data', '0.0.0.0'),
            link_type=link.get('link_type', 3),
            metric=link.get('metric', 1)
        )
        router_links.append(router_link)

    # Build Router LSA
    lsa_body = RouterLSA(
        v_bit=0,
        e_bit=0,
        b_bit=0,
        links=router_links
    )

    # Build LSA Header
    lsa_header = LSAHeader(
        ls_age=0,
        ls_type=1,
        link_state_id=router_id,
        advertising_router=router_id,
        ls_sequence_number=0x80000001
    )

    packet = lsa_header / lsa_body
    return bytes(packet)


# ============================================================================
# Validation Functions
# ============================================================================

def validate_ospf_checksum(packet: OSPFHeader) -> bool:
    """
    Validate OSPF packet checksum

    Args:
        packet: OSPF packet

    Returns:
        True if checksum is valid
    """
    data = bytes(packet)
    stored_checksum = struct.unpack("!H", data[12:14])[0]

    # Calculate checksum with field zeroed
    temp_data = data[:12] + b'\x00\x00' + data[14:]
    calculated_checksum = ospf_checksum(temp_data)

    return stored_checksum == calculated_checksum


def validate_lsa_checksum(lsa_header: LSAHeader) -> bool:
    """
    Validate LSA checksum

    Args:
        lsa_header: LSA header packet

    Returns:
        True if checksum is valid
    """
    data = bytes(lsa_header)
    stored_checksum = struct.unpack("!H", data[16:18])[0]

    # Calculate checksum with age=0 and checksum=0
    temp_data = b'\x00\x00' + data[2:16] + b'\x00\x00' + data[18:]
    calculated_checksum = fletcher_checksum(temp_data, offset=2)

    return stored_checksum == calculated_checksum
