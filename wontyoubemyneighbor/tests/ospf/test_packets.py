"""
Unit tests for OSPF packet creation and parsing
"""

import pytest
import struct
from ospf.packets import (
    OSPFHeader, OSPFHello, OSPFDBDescription, OSPFLSRequest,
    OSPFLSUpdate, OSPFLSAck, LSAHeader, RouterLSA, NetworkLSA,
    RouterLink, parse_ospf_packet, build_hello_packet, build_router_lsa,
    validate_ospf_checksum, validate_lsa_checksum
)
from ospf.constants import (
    OSPF_VERSION, HELLO_PACKET, DATABASE_DESCRIPTION,
    ROUTER_LSA, LINK_TYPE_STUB
)


class TestOSPFHeader:
    """Test OSPF Header packet creation and parsing"""

    def test_create_ospf_header(self):
        """Test creating OSPF header"""
        header = OSPFHeader(
            version=2,
            type=1,
            router_id="10.1.1.1",
            area_id="0.0.0.0"
        )

        assert header.version == 2
        assert header.type == 1
        assert header.router_id == "10.1.1.1"
        assert header.area_id == "0.0.0.0"

    def test_ospf_header_serialization(self):
        """Test OSPF header serialization to bytes"""
        header = OSPFHeader(
            version=2,
            type=1,
            router_id="10.1.1.1",
            area_id="0.0.0.0"
        )

        data = bytes(header)

        # Check minimum header size
        assert len(data) >= 24

        # Check version
        assert data[0] == 2

        # Check type
        assert data[1] == 1

    def test_ospf_header_parsing(self):
        """Test parsing OSPF header from bytes"""
        # Create and serialize
        original = OSPFHeader(
            version=2,
            type=1,
            router_id="10.1.1.1",
            area_id="0.0.0.0"
        )

        data = bytes(original)

        # Parse back
        parsed = OSPFHeader(data)

        assert parsed.version == 2
        assert parsed.type == 1
        assert parsed.router_id == "10.1.1.1"
        assert parsed.area_id == "0.0.0.0"

    def test_ospf_header_auto_length(self):
        """Test automatic length calculation"""
        header = OSPFHeader(
            version=2,
            type=1,
            router_id="10.1.1.1",
            area_id="0.0.0.0"
        )

        data = bytes(header)
        length = struct.unpack("!H", data[2:4])[0]

        # Header only should be 24 bytes
        assert length == 24

    def test_ospf_header_checksum(self):
        """Test automatic checksum calculation"""
        header = OSPFHeader(
            version=2,
            type=1,
            router_id="10.1.1.1",
            area_id="0.0.0.0"
        )

        data = bytes(header)
        checksum = struct.unpack("!H", data[12:14])[0]

        # Checksum should be non-zero
        assert checksum != 0


class TestOSPFHello:
    """Test OSPF Hello packet"""

    def test_create_hello_packet(self):
        """Test creating Hello packet"""
        hello = OSPFHello(
            network_mask="255.255.255.0",
            hello_interval=10,
            router_dead_interval=40,
            neighbors=["10.2.2.2", "10.3.3.3"]
        )

        assert hello.network_mask == "255.255.255.0"
        assert hello.hello_interval == 10
        assert hello.router_dead_interval == 40
        assert len(hello.neighbors) == 2

    def test_hello_with_header(self):
        """Test complete Hello packet with header"""
        header = OSPFHeader(
            type=HELLO_PACKET,
            router_id="10.1.1.1",
            area_id="0.0.0.0"
        )

        hello = OSPFHello(
            network_mask="255.255.255.0",
            neighbors=["10.2.2.2"]
        )

        packet = header / hello
        data = bytes(packet)

        # Should be header (24) + hello fields
        assert len(data) > 24

    def test_parse_hello_packet(self):
        """Test parsing complete Hello packet"""
        # Build
        packet = OSPFHeader(type=1, router_id="10.1.1.1", area_id="0.0.0.0") / \
                 OSPFHello(network_mask="255.255.255.0", neighbors=["10.2.2.2"])

        data = bytes(packet)

        # Parse
        parsed = OSPFHeader(data)

        assert parsed.type == 1
        assert parsed.router_id == "10.1.1.1"

        hello = parsed[OSPFHello]
        assert hello.network_mask == "255.255.255.0"
        assert "10.2.2.2" in hello.neighbors

    def test_build_hello_packet_utility(self):
        """Test build_hello_packet utility function"""
        data = build_hello_packet(
            router_id="10.1.1.1",
            area_id="0.0.0.0",
            network_mask="255.255.255.0",
            neighbors=["10.2.2.2"]
        )

        assert isinstance(data, bytes)
        assert len(data) > 24

        # Parse and verify
        parsed = OSPFHeader(data)
        assert parsed.type == 1
        assert parsed.router_id == "10.1.1.1"


class TestOSPFDBDescription:
    """Test OSPF Database Description packet"""

    def test_create_dbd_packet(self):
        """Test creating DBD packet"""
        dbd = OSPFDBDescription(
            interface_mtu=1500,
            dd_sequence=12345
        )

        assert dbd.interface_mtu == 1500
        assert dbd.dd_sequence == 12345

    def test_dbd_flags(self):
        """Test DBD flag methods"""
        dbd = OSPFDBDescription()

        # Set flags
        dbd.set_flags(init=True, more=True, master=True)

        assert dbd.has_init() is True
        assert dbd.has_more() is True
        assert dbd.is_master() is True

        # Clear flags
        dbd.set_flags(init=False, more=False, master=False)

        assert dbd.has_init() is False
        assert dbd.has_more() is False
        assert dbd.is_master() is False

    def test_dbd_master_only(self):
        """Test setting only master flag"""
        dbd = OSPFDBDescription()
        dbd.set_flags(master=True)

        assert dbd.is_master() is True
        assert dbd.has_init() is False
        assert dbd.has_more() is False


class TestLSAHeader:
    """Test LSA Header"""

    def test_create_lsa_header(self):
        """Test creating LSA header"""
        header = LSAHeader(
            ls_age=0,
            ls_type=ROUTER_LSA,
            link_state_id="10.1.1.1",
            advertising_router="10.1.1.1",
            ls_sequence_number=0x80000001
        )

        assert header.ls_age == 0
        assert header.ls_type == 1
        assert header.link_state_id == "10.1.1.1"
        assert header.advertising_router == "10.1.1.1"
        assert header.ls_sequence_number == 0x80000001

    def test_lsa_header_size(self):
        """Test LSA header is 20 bytes"""
        header = LSAHeader(
            link_state_id="10.1.1.1",
            advertising_router="10.1.1.1"
        )

        data = bytes(header)

        # LSA header should be 20 bytes
        assert len(data) == 20

    def test_lsa_header_auto_length(self):
        """Test automatic length calculation"""
        header = LSAHeader(
            link_state_id="10.1.1.1",
            advertising_router="10.1.1.1"
        )

        data = bytes(header)
        length = struct.unpack("!H", data[18:20])[0]

        # Header only should be 20 bytes
        assert length == 20


class TestRouterLSA:
    """Test Router LSA"""

    def test_create_router_lsa(self):
        """Test creating Router LSA"""
        link = RouterLink(
            link_id="10.1.1.1",
            link_data="255.255.255.255",
            link_type=LINK_TYPE_STUB,
            metric=1
        )

        lsa = RouterLSA(
            v_bit=0,
            e_bit=0,
            b_bit=0,
            links=[link]
        )

        assert len(lsa.links) == 1
        assert lsa.links[0].link_type == LINK_TYPE_STUB

    def test_router_lsa_auto_num_links(self):
        """Test automatic link count calculation"""
        links = [
            RouterLink(link_id="10.1.1.1", link_data="255.255.255.255", link_type=3),
            RouterLink(link_id="10.2.2.2", link_data="255.255.255.255", link_type=3)
        ]

        lsa = RouterLSA(links=links)
        data = bytes(lsa)

        # Extract num_links field (bytes 2-4)
        num_links = struct.unpack("!H", data[2:4])[0]

        assert num_links == 2

    def test_complete_router_lsa_with_header(self):
        """Test complete Router LSA with header"""
        # Create link
        link = RouterLink(
            link_id="10.1.1.1",
            link_data="255.255.255.255",
            link_type=LINK_TYPE_STUB,
            metric=1
        )

        # Create LSA body
        lsa_body = RouterLSA(links=[link])

        # Create LSA header
        lsa_header = LSAHeader(
            ls_type=ROUTER_LSA,
            link_state_id="10.1.1.1",
            advertising_router="10.1.1.1"
        )

        # Combine
        packet = lsa_header / lsa_body
        data = bytes(packet)

        # Should be header (20) + body
        assert len(data) > 20

    def test_build_router_lsa_utility(self):
        """Test build_router_lsa utility function"""
        links = [
            {
                'link_id': '10.1.1.1',
                'link_data': '255.255.255.255',
                'link_type': LINK_TYPE_STUB,
                'metric': 1
            }
        ]

        data = build_router_lsa(
            router_id="10.1.1.1",
            links=links
        )

        assert isinstance(data, bytes)
        assert len(data) > 20


class TestNetworkLSA:
    """Test Network LSA"""

    def test_create_network_lsa(self):
        """Test creating Network LSA"""
        lsa = NetworkLSA(
            network_mask="255.255.255.0",
            attached_routers=["10.1.1.1", "10.2.2.2"]
        )

        assert lsa.network_mask == "255.255.255.0"
        assert len(lsa.attached_routers) == 2


class TestChecksums:
    """Test checksum calculation and validation"""

    def test_ospf_checksum_validation(self):
        """Test OSPF checksum validation"""
        packet = OSPFHeader(
            type=HELLO_PACKET,
            router_id="10.1.1.1",
            area_id="0.0.0.0"
        ) / OSPFHello()

        # Build packet (checksum auto-calculated)
        data = bytes(packet)

        # Parse and validate
        parsed = OSPFHeader(data)
        assert validate_ospf_checksum(parsed) is True

    def test_lsa_checksum_validation(self):
        """Test LSA checksum validation"""
        lsa = LSAHeader(
            ls_type=ROUTER_LSA,
            link_state_id="10.1.1.1",
            advertising_router="10.1.1.1"
        )

        # Build LSA (checksum auto-calculated)
        data = bytes(lsa)

        # Parse and validate
        parsed = LSAHeader(data)
        assert validate_lsa_checksum(parsed) is True


class TestPacketParsing:
    """Test packet parsing utility"""

    def test_parse_ospf_packet_valid(self):
        """Test parsing valid OSPF packet"""
        original = OSPFHeader(
            type=HELLO_PACKET,
            router_id="10.1.1.1",
            area_id="0.0.0.0"
        ) / OSPFHello()

        data = bytes(original)

        parsed = parse_ospf_packet(data)

        assert parsed is not None
        assert parsed.type == HELLO_PACKET
        assert parsed.router_id == "10.1.1.1"

    def test_parse_ospf_packet_invalid(self):
        """Test parsing invalid data returns None"""
        invalid_data = b"invalid packet data"

        parsed = parse_ospf_packet(invalid_data)

        # Should return None for invalid data
        assert parsed is None


class TestPacketIntegration:
    """Integration tests for complete packet workflows"""

    def test_hello_roundtrip(self):
        """Test Hello packet build -> serialize -> parse -> validate"""
        # Build
        original = OSPFHeader(
            type=HELLO_PACKET,
            router_id="10.1.1.1",
            area_id="0.0.0.0"
        ) / OSPFHello(
            network_mask="255.255.255.0",
            neighbors=["10.2.2.2", "10.3.3.3"]
        )

        # Serialize
        data = bytes(original)

        # Parse
        parsed = OSPFHeader(data)

        # Validate
        assert parsed.type == HELLO_PACKET
        assert parsed.router_id == "10.1.1.1"
        assert validate_ospf_checksum(parsed) is True

        hello = parsed[OSPFHello]
        assert hello.network_mask == "255.255.255.0"
        assert len(hello.neighbors) == 2

    def test_dbd_roundtrip(self):
        """Test DBD packet build -> serialize -> parse"""
        # Build
        original = OSPFHeader(
            type=DATABASE_DESCRIPTION,
            router_id="10.1.1.1",
            area_id="0.0.0.0"
        ) / OSPFDBDescription(
            interface_mtu=1500,
            dd_sequence=12345
        )

        original[OSPFDBDescription].set_flags(init=True, more=True, master=True)

        # Serialize
        data = bytes(original)

        # Parse
        parsed = OSPFHeader(data)

        # Validate
        assert parsed.type == DATABASE_DESCRIPTION
        dbd = parsed[OSPFDBDescription]
        assert dbd.interface_mtu == 1500
        assert dbd.dd_sequence == 12345
        assert dbd.has_init() is True
        assert dbd.has_more() is True
        assert dbd.is_master() is True

    def test_router_lsa_roundtrip(self):
        """Test Router LSA build -> serialize -> parse"""
        # Build
        link = RouterLink(
            link_id="10.1.1.1",
            link_data="255.255.255.255",
            link_type=LINK_TYPE_STUB,
            metric=1
        )

        lsa_body = RouterLSA(links=[link])

        lsa_header = LSAHeader(
            ls_type=ROUTER_LSA,
            link_state_id="10.1.1.1",
            advertising_router="10.1.1.1",
            ls_sequence_number=0x80000001
        )

        original = lsa_header / lsa_body

        # Serialize
        data = bytes(original)

        # Parse
        parsed = LSAHeader(data)

        # Validate
        assert parsed.ls_type == ROUTER_LSA
        assert parsed.link_state_id == "10.1.1.1"
        assert parsed.ls_sequence_number == 0x80000001
        assert validate_lsa_checksum(parsed) is True

        router_lsa = parsed[RouterLSA]
        assert len(router_lsa.links) == 1
        assert router_lsa.links[0].link_type == LINK_TYPE_STUB


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
