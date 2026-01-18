"""
BGP Message Encoding/Decoding Tests

Tests for all BGP message types: OPEN, UPDATE, KEEPALIVE, NOTIFICATION, ROUTE-REFRESH
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import unittest
import struct
import socket
from bgp.messages import (
    BGPMessage, BGPOpen, BGPKeepalive, BGPNotification,
    BGPUpdate, BGPRouteRefresh, BGPCapability
)
from bgp.constants import *


class TestBGPMessageHeader(unittest.TestCase):
    """Test BGP message header encoding/decoding"""

    def test_parse_valid_header(self):
        """Test parsing valid BGP header"""
        # Build KEEPALIVE (header only)
        data = BGP_MARKER + struct.pack('!HB', 19, MSG_KEEPALIVE)
        result = BGPMessage.parse_header(data)

        self.assertIsNotNone(result)
        msg_type, length, payload = result
        self.assertEqual(msg_type, MSG_KEEPALIVE)
        self.assertEqual(length, 19)
        self.assertEqual(len(payload), 0)

    def test_parse_invalid_marker(self):
        """Test parsing header with invalid marker"""
        data = b'\x00' * 16 + struct.pack('!HB', 19, MSG_KEEPALIVE)
        result = BGPMessage.parse_header(data)
        self.assertIsNone(result)

    def test_parse_invalid_length(self):
        """Test parsing header with invalid length"""
        # Length too small
        data = BGP_MARKER + struct.pack('!HB', 10, MSG_KEEPALIVE)
        result = BGPMessage.parse_header(data)
        self.assertIsNone(result)

        # Length too large
        data = BGP_MARKER + struct.pack('!HB', 5000, MSG_KEEPALIVE)
        result = BGPMessage.parse_header(data)
        self.assertIsNone(result)


class TestBGPCapability(unittest.TestCase):
    """Test BGP Capability encoding/decoding"""

    def test_multiprotocol_capability(self):
        """Test Multiprotocol capability (Code 1)"""
        cap = BGPCapability.encode_multiprotocol(AFI_IPV4, SAFI_UNICAST)
        self.assertEqual(cap.code, CAP_MULTIPROTOCOL)

        data = cap.encode()
        decoded_cap, consumed = BGPCapability.decode(data)

        self.assertIsNotNone(decoded_cap)
        self.assertEqual(decoded_cap.code, CAP_MULTIPROTOCOL)
        self.assertEqual(consumed, len(data))

    def test_route_refresh_capability(self):
        """Test Route Refresh capability (Code 2)"""
        cap = BGPCapability.encode_route_refresh()
        self.assertEqual(cap.code, CAP_ROUTE_REFRESH)
        self.assertEqual(len(cap.value), 0)

        data = cap.encode()
        decoded_cap, consumed = BGPCapability.decode(data)

        self.assertIsNotNone(decoded_cap)
        self.assertEqual(decoded_cap.code, CAP_ROUTE_REFRESH)

    def test_four_octet_as_capability(self):
        """Test 4-byte AS capability (Code 65)"""
        asn = 4200000000
        cap = BGPCapability.encode_four_octet_as(asn)
        self.assertEqual(cap.code, CAP_FOUR_OCTET_AS)

        data = cap.encode()
        decoded_cap, consumed = BGPCapability.decode(data)

        self.assertIsNotNone(decoded_cap)
        self.assertEqual(decoded_cap.code, CAP_FOUR_OCTET_AS)
        # Verify ASN value
        decoded_asn = struct.unpack('!I', decoded_cap.value)[0]
        self.assertEqual(decoded_asn, asn)

    def test_add_path_capability(self):
        """Test ADD-PATH capability (Code 69)"""
        cap = BGPCapability.encode_add_path(AFI_IPV4, SAFI_UNICAST, send=True, receive=True)
        self.assertEqual(cap.code, CAP_ADD_PATH)

        data = cap.encode()
        decoded_cap, consumed = BGPCapability.decode(data)

        self.assertIsNotNone(decoded_cap)
        self.assertEqual(decoded_cap.code, CAP_ADD_PATH)


class TestBGPOpen(unittest.TestCase):
    """Test BGP OPEN message encoding/decoding"""

    def test_encode_decode_basic(self):
        """Test basic OPEN message without capabilities"""
        open_msg = BGPOpen(
            version=BGP_VERSION,
            my_as=65001,
            hold_time=90,
            bgp_identifier="192.0.2.1",
            capabilities=[]
        )

        data = open_msg.encode()

        # Verify header
        self.assertEqual(data[0:16], BGP_MARKER)
        length = struct.unpack('!H', data[16:18])[0]
        msg_type = data[18]
        self.assertEqual(msg_type, MSG_OPEN)
        self.assertEqual(len(data), length)

        # Decode and verify
        decoded = BGPOpen.decode(data)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.version, BGP_VERSION)
        self.assertEqual(decoded.my_as, 65001)
        self.assertEqual(decoded.hold_time, 90)
        self.assertEqual(decoded.bgp_identifier, "192.0.2.1")
        self.assertEqual(len(decoded.capabilities), 0)

    def test_encode_decode_with_capabilities(self):
        """Test OPEN message with capabilities"""
        caps = [
            BGPCapability.encode_multiprotocol(AFI_IPV4, SAFI_UNICAST),
            BGPCapability.encode_route_refresh(),
            BGPCapability.encode_four_octet_as(4200000000)
        ]

        open_msg = BGPOpen(
            version=BGP_VERSION,
            my_as=65001,
            hold_time=180,
            bgp_identifier="10.0.0.1",
            capabilities=caps
        )

        data = open_msg.encode()
        decoded = BGPOpen.decode(data)

        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.version, BGP_VERSION)
        self.assertEqual(decoded.my_as, 65001)
        self.assertEqual(decoded.hold_time, 180)
        self.assertEqual(decoded.bgp_identifier, "10.0.0.1")
        self.assertEqual(len(decoded.capabilities), 3)

        # Verify capability codes
        cap_codes = [c.code for c in decoded.capabilities]
        self.assertIn(CAP_MULTIPROTOCOL, cap_codes)
        self.assertIn(CAP_ROUTE_REFRESH, cap_codes)
        self.assertIn(CAP_FOUR_OCTET_AS, cap_codes)

    def test_encode_large_as(self):
        """Test OPEN with AS > 65535 (should use AS_TRANS)"""
        open_msg = BGPOpen(
            version=BGP_VERSION,
            my_as=4200000000,
            hold_time=90,
            bgp_identifier="192.0.2.1",
            capabilities=[BGPCapability.encode_four_octet_as(4200000000)]
        )

        data = open_msg.encode()
        # Verify AS field is AS_TRANS (23456)
        payload = data[BGP_HEADER_SIZE:]
        as_field = struct.unpack('!H', payload[1:3])[0]
        self.assertEqual(as_field, AS_TRANS)


class TestBGPKeepalive(unittest.TestCase):
    """Test BGP KEEPALIVE message"""

    def test_encode_decode(self):
        """Test KEEPALIVE encoding/decoding"""
        keepalive = BGPKeepalive()
        data = keepalive.encode()

        # Verify it's exactly 19 bytes (header only)
        self.assertEqual(len(data), BGP_HEADER_SIZE)

        # Verify header
        self.assertEqual(data[0:16], BGP_MARKER)
        length = struct.unpack('!H', data[16:18])[0]
        msg_type = data[18]
        self.assertEqual(length, 19)
        self.assertEqual(msg_type, MSG_KEEPALIVE)

        # Decode
        decoded = BGPKeepalive.decode(data)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.msg_type, MSG_KEEPALIVE)


class TestBGPNotification(unittest.TestCase):
    """Test BGP NOTIFICATION message"""

    def test_encode_decode_basic(self):
        """Test NOTIFICATION without data"""
        notif = BGPNotification(
            error_code=ERR_HOLD_TIMER_EXPIRED,
            error_subcode=0
        )

        data = notif.encode()
        decoded = BGPNotification.decode(data)

        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.error_code, ERR_HOLD_TIMER_EXPIRED)
        self.assertEqual(decoded.error_subcode, 0)
        self.assertEqual(len(decoded.data), 0)

    def test_encode_decode_with_data(self):
        """Test NOTIFICATION with error data"""
        error_data = b'\x00\x01\x00\x02'
        notif = BGPNotification(
            error_code=ERR_UPDATE_MESSAGE,
            error_subcode=ERR_UPDATE_MALFORMED_ATTRIBUTE_LIST,
            data=error_data
        )

        data = notif.encode()
        decoded = BGPNotification.decode(data)

        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.error_code, ERR_UPDATE_MESSAGE)
        self.assertEqual(decoded.error_subcode, ERR_UPDATE_MALFORMED_ATTRIBUTE_LIST)
        self.assertEqual(decoded.data, error_data)

    def test_get_error_name(self):
        """Test error name lookup"""
        notif = BGPNotification(ERR_OPEN_MESSAGE, ERR_OPEN_BAD_PEER_AS)
        name = notif.get_error_name()
        self.assertEqual(name, "OPEN Message Error")


class TestBGPUpdate(unittest.TestCase):
    """Test BGP UPDATE message"""

    def test_encode_decode_empty(self):
        """Test empty UPDATE (End-of-RIB marker)"""
        update = BGPUpdate()
        data = update.encode()

        decoded = BGPUpdate.decode(data)
        self.assertIsNotNone(decoded)
        self.assertEqual(len(decoded.withdrawn_routes), 0)
        self.assertEqual(len(decoded.path_attributes), 0)
        self.assertEqual(len(decoded.nlri), 0)

    def test_encode_decode_with_attributes(self):
        """Test UPDATE with path attributes"""
        from bgp.attributes import (
            OriginAttribute, ASPathAttribute, NextHopAttribute,
            LocalPrefAttribute, ORIGIN_IGP, AS_SEQUENCE, ATTR_ORIGIN,
            ATTR_AS_PATH, ATTR_NEXT_HOP, ATTR_LOCAL_PREF
        )

        attrs = {
            ATTR_ORIGIN: OriginAttribute(ORIGIN_IGP),
            ATTR_AS_PATH: ASPathAttribute([(AS_SEQUENCE, [65001, 65002])]),
            ATTR_NEXT_HOP: NextHopAttribute("192.0.2.1"),
            ATTR_LOCAL_PREF: LocalPrefAttribute(100)
        }

        nlri = ["203.0.113.0/24"]
        update = BGPUpdate(nlri=nlri, path_attributes=attrs)

        data = update.encode()
        decoded = BGPUpdate.decode(data)

        self.assertIsNotNone(decoded)
        self.assertEqual(len(decoded.nlri), 1)
        self.assertIn("203.0.113.0/24", decoded.nlri)
        self.assertEqual(len(decoded.path_attributes), 4)
        self.assertIn(ATTR_ORIGIN, decoded.path_attributes)
        self.assertIn(ATTR_AS_PATH, decoded.path_attributes)
        self.assertIn(ATTR_NEXT_HOP, decoded.path_attributes)

    def test_encode_decode_prefixes(self):
        """Test prefix encoding/decoding"""
        # Test various prefix lengths
        prefixes = [
            "203.0.113.0/24",
            "192.0.2.0/24",
            "10.0.0.0/8",
            "172.16.0.0/12"
        ]

        data = BGPUpdate._encode_prefixes(prefixes)
        decoded_prefixes = BGPUpdate._decode_prefixes(data)

        self.assertEqual(len(decoded_prefixes), len(prefixes))
        for original, decoded in zip(prefixes, decoded_prefixes):
            self.assertEqual(original, decoded)

    def test_encode_decode_nlri(self):
        """Test UPDATE with NLRI"""
        nlri = ["203.0.113.0/24", "192.0.2.0/24"]
        update = BGPUpdate(nlri=nlri)

        data = update.encode()
        decoded = BGPUpdate.decode(data)

        self.assertIsNotNone(decoded)
        self.assertEqual(len(decoded.nlri), 2)
        self.assertIn("203.0.113.0/24", decoded.nlri)
        self.assertIn("192.0.2.0/24", decoded.nlri)

    def test_encode_decode_withdrawn(self):
        """Test UPDATE with withdrawn routes"""
        withdrawn = ["10.1.0.0/16", "10.2.0.0/16"]
        update = BGPUpdate(withdrawn_routes=withdrawn)

        data = update.encode()
        decoded = BGPUpdate.decode(data)

        self.assertIsNotNone(decoded)
        self.assertEqual(len(decoded.withdrawn_routes), 2)
        self.assertIn("10.1.0.0/16", decoded.withdrawn_routes)
        self.assertIn("10.2.0.0/16", decoded.withdrawn_routes)


class TestBGPRouteRefresh(unittest.TestCase):
    """Test BGP ROUTE-REFRESH message"""

    def test_encode_decode_ipv4_unicast(self):
        """Test ROUTE-REFRESH for IPv4 unicast"""
        rr = BGPRouteRefresh(AFI_IPV4, SAFI_UNICAST)
        data = rr.encode()

        decoded = BGPRouteRefresh.decode(data)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.afi, AFI_IPV4)
        self.assertEqual(decoded.safi, SAFI_UNICAST)

    def test_encode_decode_ipv6_unicast(self):
        """Test ROUTE-REFRESH for IPv6 unicast"""
        rr = BGPRouteRefresh(AFI_IPV6, SAFI_UNICAST)
        data = rr.encode()

        decoded = BGPRouteRefresh.decode(data)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.afi, AFI_IPV6)
        self.assertEqual(decoded.safi, SAFI_UNICAST)


class TestBGPMessageDispatch(unittest.TestCase):
    """Test BGPMessage.decode() dispatcher"""

    def test_dispatch_open(self):
        """Test dispatch to BGPOpen"""
        open_msg = BGPOpen(BGP_VERSION, 65001, 90, "192.0.2.1")
        data = open_msg.encode()

        decoded = BGPMessage.decode(data)
        self.assertIsInstance(decoded, BGPOpen)
        self.assertEqual(decoded.my_as, 65001)

    def test_dispatch_keepalive(self):
        """Test dispatch to BGPKeepalive"""
        keepalive = BGPKeepalive()
        data = keepalive.encode()

        decoded = BGPMessage.decode(data)
        self.assertIsInstance(decoded, BGPKeepalive)

    def test_dispatch_notification(self):
        """Test dispatch to BGPNotification"""
        notif = BGPNotification(ERR_CEASE, ERR_CEASE_ADMIN_SHUTDOWN)
        data = notif.encode()

        decoded = BGPMessage.decode(data)
        self.assertIsInstance(decoded, BGPNotification)
        self.assertEqual(decoded.error_code, ERR_CEASE)

    def test_dispatch_update(self):
        """Test dispatch to BGPUpdate"""
        update = BGPUpdate(nlri=["203.0.113.0/24"])
        data = update.encode()

        decoded = BGPMessage.decode(data)
        self.assertIsInstance(decoded, BGPUpdate)

    def test_dispatch_route_refresh(self):
        """Test dispatch to BGPRouteRefresh"""
        rr = BGPRouteRefresh(AFI_IPV4, SAFI_UNICAST)
        data = rr.encode()

        decoded = BGPMessage.decode(data)
        self.assertIsInstance(decoded, BGPRouteRefresh)


if __name__ == '__main__':
    unittest.main()
