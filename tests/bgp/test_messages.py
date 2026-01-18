"""
BGP Message Encoding/Decoding Tests

Tests all BGP message types (OPEN, UPDATE, KEEPALIVE, NOTIFICATION, ROUTE-REFRESH)
per RFC 4271 Section 4.
"""

import struct
import pytest
from wontyoubemyneighbor.bgp.messages import *
from wontyoubemyneighbor.bgp.constants import *
from wontyoubemyneighbor.bgp.attributes import *
from wontyoubemyneighbor.bgp.capabilities import *


class TestBGPMessageHeader:
    """Test BGP message header encoding/decoding (RFC 4271 Section 4.1)"""

    def test_header_format(self):
        """Test header is 19 bytes with correct format"""
        msg = BGPKeepalive()
        data = msg.encode()

        assert len(data) == BGP_HEADER_SIZE
        assert data[0:16] == BGP_MARKER  # Marker is all 0xFF
        assert struct.unpack('!H', data[16:18])[0] == 19  # Length
        assert data[18] == MSG_KEEPALIVE  # Type

    def test_marker_validation(self):
        """Test invalid marker is rejected"""
        # Create message with bad marker
        bad_data = b'\x00' * 16 + struct.pack('!HB', 19, MSG_KEEPALIVE)
        msg = BGPMessage.decode(bad_data)
        assert msg is None

    def test_length_validation(self):
        """Test length validation"""
        # Too short
        short_data = BGP_MARKER + struct.pack('!HB', 10, MSG_KEEPALIVE)
        assert BGPMessage.decode(short_data) is None

        # Too long
        long_data = BGP_MARKER + struct.pack('!HB', 5000, MSG_KEEPALIVE)
        assert BGPMessage.decode(long_data) is None

    def test_message_type_dispatch(self):
        """Test message type dispatches to correct class"""
        # KEEPALIVE
        ka = BGPKeepalive()
        decoded = BGPMessage.decode(ka.encode())
        assert isinstance(decoded, BGPKeepalive)


class TestBGPOpen:
    """Test OPEN message encoding/decoding (RFC 4271 Section 4.2)"""

    def test_basic_open(self):
        """Test basic OPEN without capabilities"""
        msg = BGPOpen(
            my_as=65001,
            hold_time=90,
            bgp_identifier="192.0.2.1",
            capabilities=[]
        )

        data = msg.encode()
        decoded = BGPOpen.decode(data)

        assert decoded is not None
        assert decoded.version == BGP_VERSION
        assert decoded.my_as == 65001
        assert decoded.hold_time == 90
        assert decoded.bgp_identifier == "192.0.2.1"
        assert len(decoded.capabilities) == 0

    def test_open_with_capabilities(self):
        """Test OPEN with capabilities"""
        caps = [
            MultiprotocolCapability(afi=AFI_IPV4, safi=SAFI_UNICAST),
            RouteRefreshCapability(),
            FourOctetASCapability(asn=4200000000)
        ]

        msg = BGPOpen(
            my_as=23456,  # AS_TRANS for 4-byte AS
            hold_time=180,
            bgp_identifier="10.0.0.1",
            capabilities=caps
        )

        data = msg.encode()
        decoded = BGPOpen.decode(data)

        assert decoded is not None
        assert decoded.my_as == 23456
        assert decoded.hold_time == 180
        assert len(decoded.capabilities) == 3

    def test_open_version_validation(self):
        """Test BGP version must be 4"""
        msg = BGPOpen(
            my_as=65001,
            hold_time=90,
            bgp_identifier="192.0.2.1"
        )
        msg.version = 3  # Invalid
        data = msg.encode()

        # Decoding should work but version check happens at FSM level
        decoded = BGPOpen.decode(data)
        assert decoded.version == 3

    def test_open_hold_time_zero(self):
        """Test hold time can be 0 (no keepalives)"""
        msg = BGPOpen(
            my_as=65001,
            hold_time=0,
            bgp_identifier="192.0.2.1"
        )
        data = msg.encode()
        decoded = BGPOpen.decode(data)
        assert decoded.hold_time == 0

    def test_open_four_byte_as(self):
        """Test 4-byte AS number encoding"""
        caps = [FourOctetASCapability(asn=4200000000)]
        msg = BGPOpen(
            my_as=23456,  # AS_TRANS
            hold_time=90,
            bgp_identifier="192.0.2.1",
            capabilities=caps
        )

        data = msg.encode()
        decoded = BGPOpen.decode(data)

        # Find 4-byte AS capability
        four_byte_cap = next(
            (c for c in decoded.capabilities if isinstance(c, FourOctetASCapability)),
            None
        )
        assert four_byte_cap is not None
        assert four_byte_cap.asn == 4200000000


class TestBGPUpdate:
    """Test UPDATE message encoding/decoding (RFC 4271 Section 4.3)"""

    def test_empty_update(self):
        """Test UPDATE with no routes (end-of-RIB marker)"""
        msg = BGPUpdate(
            withdrawn_routes=[],
            path_attributes=[],
            nlri=[]
        )

        data = msg.encode()
        decoded = BGPUpdate.decode(data)

        assert decoded is not None
        assert len(decoded.withdrawn_routes) == 0
        assert len(decoded.path_attributes) == 0
        assert len(decoded.nlri) == 0

    def test_update_with_announcement(self):
        """Test UPDATE announcing routes"""
        # Path attributes
        attrs = [
            OriginAttribute(origin=ORIGIN_IGP),
            ASPathAttribute(segments=[(AS_SEQUENCE, [65001, 65002])]),
            NextHopAttribute(next_hop="192.0.2.1"),
            MEDAttribute(metric=100)
        ]

        # NLRI
        nlri = ["203.0.113.0/24", "198.51.100.0/24"]

        msg = BGPUpdate(
            withdrawn_routes=[],
            path_attributes=attrs,
            nlri=nlri
        )

        data = msg.encode()
        decoded = BGPUpdate.decode(data)

        assert decoded is not None
        assert len(decoded.nlri) == 2
        assert "203.0.113.0/24" in decoded.nlri
        assert "198.51.100.0/24" in decoded.nlri
        assert len(decoded.path_attributes) == 4

    def test_update_with_withdrawal(self):
        """Test UPDATE withdrawing routes"""
        withdrawn = ["203.0.113.0/24", "198.51.100.0/24"]

        msg = BGPUpdate(
            withdrawn_routes=withdrawn,
            path_attributes=[],
            nlri=[]
        )

        data = msg.encode()
        decoded = BGPUpdate.decode(data)

        assert decoded is not None
        assert len(decoded.withdrawn_routes) == 2
        assert "203.0.113.0/24" in decoded.withdrawn_routes

    def test_update_with_communities(self):
        """Test UPDATE with COMMUNITIES attribute"""
        attrs = [
            OriginAttribute(origin=ORIGIN_IGP),
            ASPathAttribute(segments=[(AS_SEQUENCE, [65001])]),
            NextHopAttribute(next_hop="192.0.2.1"),
            CommunitiesAttribute(communities=[
                0xFFFFFF01,  # NO_EXPORT
                (65001 << 16) | 100  # 65001:100
            ])
        ]

        msg = BGPUpdate(
            withdrawn_routes=[],
            path_attributes=attrs,
            nlri=["203.0.113.0/24"]
        )

        data = msg.encode()
        decoded = BGPUpdate.decode(data)

        # Find communities attribute
        comm_attr = next(
            (a for a in decoded.path_attributes if a.type_code == ATTR_COMMUNITIES),
            None
        )
        assert comm_attr is not None
        assert COMMUNITY_NO_EXPORT in comm_attr.communities

    def test_update_with_local_pref(self):
        """Test UPDATE with LOCAL_PREF (iBGP)"""
        attrs = [
            OriginAttribute(origin=ORIGIN_IGP),
            ASPathAttribute(segments=[(AS_SEQUENCE, [65001])]),
            NextHopAttribute(next_hop="192.0.2.1"),
            LocalPrefAttribute(local_pref=200)
        ]

        msg = BGPUpdate(
            withdrawn_routes=[],
            path_attributes=attrs,
            nlri=["203.0.113.0/24"]
        )

        data = msg.encode()
        decoded = BGPUpdate.decode(data)

        # Find LOCAL_PREF
        lp_attr = next(
            (a for a in decoded.path_attributes if a.type_code == ATTR_LOCAL_PREF),
            None
        )
        assert lp_attr is not None
        assert lp_attr.local_pref == 200


class TestBGPKeepalive:
    """Test KEEPALIVE message (RFC 4271 Section 4.4)"""

    def test_keepalive_encoding(self):
        """Test KEEPALIVE is just header"""
        msg = BGPKeepalive()
        data = msg.encode()

        assert len(data) == BGP_HEADER_SIZE
        assert data[18] == MSG_KEEPALIVE

    def test_keepalive_decoding(self):
        """Test KEEPALIVE decoding"""
        msg = BGPKeepalive()
        data = msg.encode()
        decoded = BGPKeepalive.decode(data)

        assert decoded is not None
        assert isinstance(decoded, BGPKeepalive)


class TestBGPNotification:
    """Test NOTIFICATION message (RFC 4271 Section 4.5)"""

    def test_notification_basic(self):
        """Test basic NOTIFICATION"""
        msg = BGPNotification(
            error_code=ERR_UPDATE_MESSAGE,
            error_subcode=ERR_UPDATE_INVALID_NEXT_HOP,
            data=b""
        )

        data = msg.encode()
        decoded = BGPNotification.decode(data)

        assert decoded is not None
        assert decoded.error_code == ERR_UPDATE_MESSAGE
        assert decoded.error_subcode == ERR_UPDATE_INVALID_NEXT_HOP

    def test_notification_with_data(self):
        """Test NOTIFICATION with data field"""
        error_data = b"\x00\x01\x02\x03"
        msg = BGPNotification(
            error_code=ERR_OPEN_MESSAGE,
            error_subcode=ERR_OPEN_BAD_PEER_AS,
            data=error_data
        )

        data = msg.encode()
        decoded = BGPNotification.decode(data)

        assert decoded is not None
        assert decoded.data == error_data

    def test_notification_cease(self):
        """Test CEASE notification"""
        msg = BGPNotification(
            error_code=ERR_CEASE,
            error_subcode=ERR_CEASE_ADMIN_SHUTDOWN,
            data=b""
        )

        data = msg.encode()
        decoded = BGPNotification.decode(data)

        assert decoded.error_code == ERR_CEASE
        assert decoded.error_subcode == ERR_CEASE_ADMIN_SHUTDOWN


class TestBGPRouteRefresh:
    """Test ROUTE-REFRESH message (RFC 2918)"""

    def test_route_refresh_encoding(self):
        """Test ROUTE-REFRESH encoding"""
        msg = BGPRouteRefresh(
            afi=AFI_IPV4,
            safi=SAFI_UNICAST
        )

        data = msg.encode()
        decoded = BGPRouteRefresh.decode(data)

        assert decoded is not None
        assert decoded.afi == AFI_IPV4
        assert decoded.safi == SAFI_UNICAST

    def test_route_refresh_ipv6(self):
        """Test ROUTE-REFRESH for IPv6"""
        msg = BGPRouteRefresh(
            afi=AFI_IPV6,
            safi=SAFI_UNICAST
        )

        data = msg.encode()
        decoded = BGPRouteRefresh.decode(data)

        assert decoded.afi == AFI_IPV6


class TestMessageSizeConstraints:
    """Test message size constraints"""

    def test_max_message_size(self):
        """Test messages don't exceed max size"""
        # Create UPDATE with many prefixes
        nlri = [f"10.{i}.0.0/16" for i in range(100)]
        attrs = [
            OriginAttribute(origin=ORIGIN_IGP),
            ASPathAttribute(segments=[(AS_SEQUENCE, [65001])]),
            NextHopAttribute(next_hop="192.0.2.1")
        ]

        msg = BGPUpdate(
            withdrawn_routes=[],
            path_attributes=attrs,
            nlri=nlri
        )

        data = msg.encode()
        length = struct.unpack('!H', data[16:18])[0]

        assert length <= BGP_MAX_MESSAGE_SIZE


class TestRoundTripEncoding:
    """Test encode/decode round-trip consistency"""

    def test_open_roundtrip(self):
        """Test OPEN encode/decode preserves data"""
        original = BGPOpen(
            my_as=65001,
            hold_time=90,
            bgp_identifier="192.0.2.1",
            capabilities=[
                MultiprotocolCapability(AFI_IPV4, SAFI_UNICAST),
                RouteRefreshCapability()
            ]
        )

        data = original.encode()
        decoded = BGPOpen.decode(data)
        reencoded = decoded.encode()

        assert data == reencoded

    def test_update_roundtrip(self):
        """Test UPDATE encode/decode preserves data"""
        original = BGPUpdate(
            withdrawn_routes=["192.0.2.0/24"],
            path_attributes=[
                OriginAttribute(ORIGIN_IGP),
                ASPathAttribute(segments=[(AS_SEQUENCE, [65001, 65002])]),
                NextHopAttribute("192.0.2.1")
            ],
            nlri=["203.0.113.0/24"]
        )

        data = original.encode()
        decoded = BGPUpdate.decode(data)
        reencoded = decoded.encode()

        assert data == reencoded


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
