"""
BGP Path Attributes (RFC 4271 Section 5)

This module implements all BGP path attributes including:
- Well-known mandatory: ORIGIN, AS_PATH, NEXT_HOP
- Well-known discretionary: LOCAL_PREF, ATOMIC_AGGREGATE
- Optional transitive: AGGREGATOR, COMMUNITIES
- Optional non-transitive: MED, ORIGINATOR_ID, CLUSTER_LIST
- Multiprotocol: MP_REACH_NLRI, MP_UNREACH_NLRI
"""

import struct
import socket
from typing import Optional, List, Tuple, Any
from abc import ABC, abstractmethod

from .constants import *


class PathAttribute(ABC):
    """
    Base class for BGP path attributes (RFC 4271 Section 5)

    Attribute format:
    - Flags (1 byte): Optional, Transitive, Partial, Extended
    - Type Code (1 byte)
    - Length (1 or 2 bytes): Extended length if flag bit set
    - Value (variable)
    """

    def __init__(self, type_code: int, flags: int, value: bytes = b''):
        self.type_code = type_code
        self.flags = flags
        self.value = value

    @abstractmethod
    def encode_value(self) -> bytes:
        """Encode attribute-specific value"""
        pass

    @abstractmethod
    def decode_value(self, data: bytes) -> bool:
        """Decode attribute-specific value, return True if successful"""
        pass

    def encode(self) -> bytes:
        """
        Encode attribute to wire format

        Returns:
            Encoded attribute bytes
        """
        value = self.encode_value()
        length = len(value)

        # Check if extended length needed (length > 255)
        if length > 255:
            flags = self.flags | ATTR_FLAG_EXTENDED
            return struct.pack('!BBH', flags, self.type_code, length) + value
        else:
            flags = self.flags & ~ATTR_FLAG_EXTENDED
            return struct.pack('!BBB', flags, self.type_code, length) + value

    @staticmethod
    def decode(data: bytes) -> Tuple[Optional['PathAttribute'], int]:
        """
        Decode path attribute from bytes

        Args:
            data: Attribute bytes

        Returns:
            (PathAttribute instance, bytes_consumed) or (None, 0)
        """
        if len(data) < 3:
            return (None, 0)

        flags = data[0]
        type_code = data[1]

        # Check for extended length
        if flags & ATTR_FLAG_EXTENDED:
            if len(data) < 4:
                return (None, 0)
            length = struct.unpack('!H', data[2:4])[0]
            value_offset = 4
        else:
            length = data[2]
            value_offset = 3

        if len(data) < value_offset + length:
            return (None, 0)

        value = data[value_offset:value_offset + length]

        # Dispatch to specific attribute class
        attr = AttributeFactory.create(type_code, flags, value)
        if attr and attr.decode_value(value):
            return (attr, value_offset + length)
        else:
            return (None, 0)


class OriginAttribute(PathAttribute):
    """
    ORIGIN Attribute (Type 1, RFC 4271 Section 5.1.1)

    Well-known mandatory attribute
    Values: IGP (0), EGP (1), INCOMPLETE (2)
    """

    def __init__(self, origin: int):
        # Well-known mandatory: Transitive, not optional
        flags = ATTR_FLAG_TRANSITIVE
        super().__init__(ATTR_ORIGIN, flags)
        self.origin = origin

    def encode_value(self) -> bytes:
        return struct.pack('!B', self.origin)

    def decode_value(self, data: bytes) -> bool:
        if len(data) != 1:
            return False
        self.origin = data[0]
        if self.origin not in (ORIGIN_IGP, ORIGIN_EGP, ORIGIN_INCOMPLETE):
            return False
        return True

    def __repr__(self) -> str:
        return f"ORIGIN({ORIGIN_NAMES.get(self.origin, self.origin)})"


class ASPathAttribute(PathAttribute):
    """
    AS_PATH Attribute (Type 2, RFC 4271 Section 5.1.2)

    Well-known mandatory attribute
    Contains AS_SEQUENCE and/or AS_SET segments
    """

    def __init__(self, segments: List[Tuple[int, List[int]]] = None):
        # Well-known mandatory: Transitive, not optional
        flags = ATTR_FLAG_TRANSITIVE
        super().__init__(ATTR_AS_PATH, flags)
        # segments: List of (segment_type, [ASNs])
        self.segments = segments or []

    def encode_value(self) -> bytes:
        data = b''
        for seg_type, as_list in self.segments:
            data += struct.pack('!BB', seg_type, len(as_list))
            for asn in as_list:
                data += struct.pack('!H', asn if asn <= 65535 else AS_TRANS)
        return data

    def decode_value(self, data: bytes) -> bool:
        self.segments = []
        offset = 0

        while offset < len(data):
            if offset + 2 > len(data):
                return False

            seg_type = data[offset]
            seg_len = data[offset + 1]
            offset += 2

            if offset + seg_len * 2 > len(data):
                return False

            as_list = []
            for i in range(seg_len):
                asn = struct.unpack('!H', data[offset:offset+2])[0]
                as_list.append(asn)
                offset += 2

            self.segments.append((seg_type, as_list))

        return True

    def prepend(self, asn: int) -> None:
        """
        Prepend AS number to AS_PATH (RFC 4271 Section 5.1.2)

        Adds ASN to beginning of first AS_SEQUENCE, or creates new AS_SEQUENCE
        """
        if self.segments and self.segments[0][0] == AS_SEQUENCE:
            # Prepend to existing AS_SEQUENCE
            seg_type, as_list = self.segments[0]
            as_list.insert(0, asn)
        else:
            # Create new AS_SEQUENCE at beginning
            self.segments.insert(0, (AS_SEQUENCE, [asn]))

    def length(self) -> int:
        """
        Calculate AS_PATH length for best path selection

        AS_SET counts as 1, AS_SEQUENCE counts each AS
        """
        total = 0
        for seg_type, as_list in self.segments:
            if seg_type == AS_SET:
                total += 1
            else:  # AS_SEQUENCE
                total += len(as_list)
        return total

    def contains_as(self, asn: int) -> bool:
        """Check if AS_PATH contains specific AS number"""
        for seg_type, as_list in self.segments:
            if asn in as_list:
                return True
        return False

    def __repr__(self) -> str:
        parts = []
        for seg_type, as_list in self.segments:
            if seg_type == AS_SET:
                parts.append("{" + " ".join(str(a) for a in as_list) + "}")
            else:
                parts.append(" ".join(str(a) for a in as_list))
        return f"AS_PATH({' '.join(parts)})"


class NextHopAttribute(PathAttribute):
    """
    NEXT_HOP Attribute (Type 3, RFC 4271 Section 5.1.3)

    Well-known mandatory attribute (for IPv4)
    Contains IPv4 address of next hop
    """

    def __init__(self, next_hop: str):
        # Well-known mandatory: Transitive, not optional
        flags = ATTR_FLAG_TRANSITIVE
        super().__init__(ATTR_NEXT_HOP, flags)
        self.next_hop = next_hop  # IPv4 address string

    def encode_value(self) -> bytes:
        return socket.inet_aton(self.next_hop)

    def decode_value(self, data: bytes) -> bool:
        if len(data) != 4:
            return False
        self.next_hop = socket.inet_ntoa(data)
        return True

    def __repr__(self) -> str:
        return f"NEXT_HOP({self.next_hop})"


class MEDAttribute(PathAttribute):
    """
    MULTI_EXIT_DISC (MED) Attribute (Type 4, RFC 4271 Section 5.1.4)

    Optional non-transitive attribute
    32-bit metric, lower is better
    """

    def __init__(self, med: int):
        # Optional non-transitive
        flags = ATTR_FLAG_OPTIONAL
        super().__init__(ATTR_MED, flags)
        self.med = med

    def encode_value(self) -> bytes:
        return struct.pack('!I', self.med)

    def decode_value(self, data: bytes) -> bool:
        if len(data) != 4:
            return False
        self.med = struct.unpack('!I', data)[0]
        return True

    def __repr__(self) -> str:
        return f"MED({self.med})"


class LocalPrefAttribute(PathAttribute):
    """
    LOCAL_PREF Attribute (Type 5, RFC 4271 Section 5.1.5)

    Well-known discretionary attribute (iBGP only)
    32-bit preference, higher is better
    """

    def __init__(self, local_pref: int):
        # Well-known discretionary: Transitive, not optional
        flags = ATTR_FLAG_TRANSITIVE
        super().__init__(ATTR_LOCAL_PREF, flags)
        self.local_pref = local_pref

    def encode_value(self) -> bytes:
        return struct.pack('!I', self.local_pref)

    def decode_value(self, data: bytes) -> bool:
        if len(data) != 4:
            return False
        self.local_pref = struct.unpack('!I', data)[0]
        return True

    def __repr__(self) -> str:
        return f"LOCAL_PREF({self.local_pref})"


class AtomicAggregateAttribute(PathAttribute):
    """
    ATOMIC_AGGREGATE Attribute (Type 6, RFC 4271 Section 5.1.6)

    Well-known discretionary attribute
    Zero-length attribute (flag only)
    """

    def __init__(self):
        # Well-known discretionary: Transitive, not optional
        flags = ATTR_FLAG_TRANSITIVE
        super().__init__(ATTR_ATOMIC_AGGREGATE, flags)

    def encode_value(self) -> bytes:
        return b''

    def decode_value(self, data: bytes) -> bool:
        return len(data) == 0

    def __repr__(self) -> str:
        return "ATOMIC_AGGREGATE"


class AggregatorAttribute(PathAttribute):
    """
    AGGREGATOR Attribute (Type 7, RFC 4271 Section 5.1.7)

    Optional transitive attribute
    Contains AS number and Router ID of aggregator
    """

    def __init__(self, asn: int, router_id: str):
        # Optional transitive
        flags = ATTR_FLAG_OPTIONAL | ATTR_FLAG_TRANSITIVE
        super().__init__(ATTR_AGGREGATOR, flags)
        self.asn = asn
        self.router_id = router_id  # IPv4 address string

    def encode_value(self) -> bytes:
        asn_bytes = struct.pack('!H', self.asn if self.asn <= 65535 else AS_TRANS)
        router_id_bytes = socket.inet_aton(self.router_id)
        return asn_bytes + router_id_bytes

    def decode_value(self, data: bytes) -> bool:
        if len(data) != 6:
            return False
        self.asn = struct.unpack('!H', data[0:2])[0]
        self.router_id = socket.inet_ntoa(data[2:6])
        return True

    def __repr__(self) -> str:
        return f"AGGREGATOR(AS{self.asn}, {self.router_id})"


class CommunitiesAttribute(PathAttribute):
    """
    COMMUNITIES Attribute (Type 8, RFC 1997)

    Optional transitive attribute
    Set of 32-bit community values
    Format: AS:Value (16 bits each)
    """

    def __init__(self, communities: List[int] = None):
        # Optional transitive
        flags = ATTR_FLAG_OPTIONAL | ATTR_FLAG_TRANSITIVE
        super().__init__(ATTR_COMMUNITIES, flags)
        self.communities = communities or []

    def encode_value(self) -> bytes:
        data = b''
        for comm in self.communities:
            data += struct.pack('!I', comm)
        return data

    def decode_value(self, data: bytes) -> bool:
        if len(data) % 4 != 0:
            return False

        self.communities = []
        for i in range(0, len(data), 4):
            comm = struct.unpack('!I', data[i:i+4])[0]
            self.communities.append(comm)

        return True

    def add(self, community: int) -> None:
        """Add community if not already present"""
        if community not in self.communities:
            self.communities.append(community)

    def remove(self, community: int) -> None:
        """Remove community if present"""
        if community in self.communities:
            self.communities.remove(community)

    def has(self, community: int) -> bool:
        """Check if community is present"""
        return community in self.communities

    def __repr__(self) -> str:
        comm_strs = []
        for comm in self.communities:
            if comm in WELL_KNOWN_COMMUNITIES:
                comm_strs.append(WELL_KNOWN_COMMUNITIES[comm])
            else:
                # Format as AS:Value
                asn = (comm >> 16) & 0xFFFF
                val = comm & 0xFFFF
                comm_strs.append(f"{asn}:{val}")
        return f"COMMUNITIES({', '.join(comm_strs)})"


class OriginatorIDAttribute(PathAttribute):
    """
    ORIGINATOR_ID Attribute (Type 9, RFC 4456)

    Optional non-transitive attribute for route reflection
    Contains Router ID of route originator (for loop prevention)
    """

    def __init__(self, originator_id: str):
        # Optional non-transitive
        flags = ATTR_FLAG_OPTIONAL
        super().__init__(ATTR_ORIGINATOR_ID, flags)
        self.originator_id = originator_id  # IPv4 address string

    def encode_value(self) -> bytes:
        return socket.inet_aton(self.originator_id)

    def decode_value(self, data: bytes) -> bool:
        if len(data) != 4:
            return False
        self.originator_id = socket.inet_ntoa(data)
        return True

    def __repr__(self) -> str:
        return f"ORIGINATOR_ID({self.originator_id})"


class ClusterListAttribute(PathAttribute):
    """
    CLUSTER_LIST Attribute (Type 10, RFC 4456)

    Optional non-transitive attribute for route reflection
    Contains list of cluster IDs (for loop prevention)
    """

    def __init__(self, cluster_list: List[str] = None):
        # Optional non-transitive
        flags = ATTR_FLAG_OPTIONAL
        super().__init__(ATTR_CLUSTER_LIST, flags)
        self.cluster_list = cluster_list or []  # List of IPv4 address strings

    def encode_value(self) -> bytes:
        data = b''
        for cluster_id in self.cluster_list:
            data += socket.inet_aton(cluster_id)
        return data

    def decode_value(self, data: bytes) -> bool:
        if len(data) % 4 != 0:
            return False

        self.cluster_list = []
        for i in range(0, len(data), 4):
            cluster_id = socket.inet_ntoa(data[i:i+4])
            self.cluster_list.append(cluster_id)

        return True

    def prepend(self, cluster_id: str) -> None:
        """Prepend cluster ID to list"""
        self.cluster_list.insert(0, cluster_id)

    def contains(self, cluster_id: str) -> bool:
        """Check if cluster ID is in list (loop detection)"""
        return cluster_id in self.cluster_list

    def __repr__(self) -> str:
        return f"CLUSTER_LIST({', '.join(self.cluster_list)})"


class AttributeFactory:
    """Factory for creating path attribute instances"""

    @staticmethod
    def create(type_code: int, flags: int, value: bytes) -> Optional[PathAttribute]:
        """
        Create path attribute instance based on type code

        Args:
            type_code: Attribute type code
            flags: Attribute flags
            value: Attribute value bytes

        Returns:
            PathAttribute instance or None
        """
        attr_classes = {
            ATTR_ORIGIN: OriginAttribute,
            ATTR_AS_PATH: ASPathAttribute,
            ATTR_NEXT_HOP: NextHopAttribute,
            ATTR_MED: MEDAttribute,
            ATTR_LOCAL_PREF: LocalPrefAttribute,
            ATTR_ATOMIC_AGGREGATE: AtomicAggregateAttribute,
            ATTR_AGGREGATOR: AggregatorAttribute,
            ATTR_COMMUNITIES: CommunitiesAttribute,
            ATTR_ORIGINATOR_ID: OriginatorIDAttribute,
            ATTR_CLUSTER_LIST: ClusterListAttribute,
        }

        attr_class = attr_classes.get(type_code)
        if not attr_class:
            # Unknown attribute type
            return None

        # Create instance with dummy values
        if type_code == ATTR_ORIGIN:
            attr = OriginAttribute(ORIGIN_IGP)
        elif type_code == ATTR_AS_PATH:
            attr = ASPathAttribute()
        elif type_code == ATTR_NEXT_HOP:
            attr = NextHopAttribute("0.0.0.0")
        elif type_code == ATTR_MED:
            attr = MEDAttribute(0)
        elif type_code == ATTR_LOCAL_PREF:
            attr = LocalPrefAttribute(100)
        elif type_code == ATTR_ATOMIC_AGGREGATE:
            attr = AtomicAggregateAttribute()
        elif type_code == ATTR_AGGREGATOR:
            attr = AggregatorAttribute(0, "0.0.0.0")
        elif type_code == ATTR_COMMUNITIES:
            attr = CommunitiesAttribute()
        elif type_code == ATTR_ORIGINATOR_ID:
            attr = OriginatorIDAttribute("0.0.0.0")
        elif type_code == ATTR_CLUSTER_LIST:
            attr = ClusterListAttribute()
        else:
            return None

        # Override flags with actual flags from wire
        attr.flags = flags

        return attr


def encode_path_attributes(attributes: dict) -> bytes:
    """
    Encode dictionary of path attributes to wire format

    Args:
        attributes: Dict mapping type_code to PathAttribute

    Returns:
        Encoded attributes bytes
    """
    data = b''
    for attr in attributes.values():
        data += attr.encode()
    return data


def decode_path_attributes(data: bytes) -> dict:
    """
    Decode path attributes from wire format

    Args:
        data: Attributes bytes

    Returns:
        Dict mapping type_code to PathAttribute
    """
    attributes = {}
    offset = 0

    while offset < len(data):
        attr, consumed = PathAttribute.decode(data[offset:])
        if attr:
            attributes[attr.type_code] = attr
            offset += consumed
        else:
            # Failed to decode attribute
            break

    return attributes
