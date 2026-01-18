"""
BGP Path Attributes Tests

Tests for all BGP path attribute types
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import unittest
from bgp.attributes import *
from bgp.constants import *


class TestOriginAttribute(unittest.TestCase):
    """Test ORIGIN attribute"""

    def test_encode_decode_igp(self):
        attr = OriginAttribute(ORIGIN_IGP)
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertIsNotNone(decoded)
        self.assertIsInstance(decoded, OriginAttribute)
        self.assertEqual(decoded.origin, ORIGIN_IGP)

    def test_encode_decode_egp(self):
        attr = OriginAttribute(ORIGIN_EGP)
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertEqual(decoded.origin, ORIGIN_EGP)

    def test_encode_decode_incomplete(self):
        attr = OriginAttribute(ORIGIN_INCOMPLETE)
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertEqual(decoded.origin, ORIGIN_INCOMPLETE)


class TestASPathAttribute(unittest.TestCase):
    """Test AS_PATH attribute"""

    def test_encode_decode_empty(self):
        attr = ASPathAttribute([])
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertIsNotNone(decoded)
        self.assertEqual(len(decoded.segments), 0)

    def test_encode_decode_sequence(self):
        segments = [(AS_SEQUENCE, [65001, 65002, 65003])]
        attr = ASPathAttribute(segments)
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertEqual(len(decoded.segments), 1)
        self.assertEqual(decoded.segments[0][0], AS_SEQUENCE)
        self.assertEqual(decoded.segments[0][1], [65001, 65002, 65003])

    def test_prepend(self):
        segments = [(AS_SEQUENCE, [65002, 65003])]
        attr = ASPathAttribute(segments)
        attr.prepend(65001)

        self.assertEqual(attr.segments[0][1], [65001, 65002, 65003])

    def test_prepend_to_empty(self):
        attr = ASPathAttribute([])
        attr.prepend(65001)

        self.assertEqual(len(attr.segments), 1)
        self.assertEqual(attr.segments[0][0], AS_SEQUENCE)
        self.assertEqual(attr.segments[0][1], [65001])

    def test_length_sequence(self):
        segments = [(AS_SEQUENCE, [65001, 65002, 65003])]
        attr = ASPathAttribute(segments)
        self.assertEqual(attr.length(), 3)

    def test_length_set(self):
        segments = [(AS_SET, [65001, 65002, 65003])]
        attr = ASPathAttribute(segments)
        self.assertEqual(attr.length(), 1)  # AS_SET counts as 1

    def test_contains_as(self):
        segments = [(AS_SEQUENCE, [65001, 65002, 65003])]
        attr = ASPathAttribute(segments)
        self.assertTrue(attr.contains_as(65002))
        self.assertFalse(attr.contains_as(65999))


class TestNextHopAttribute(unittest.TestCase):
    """Test NEXT_HOP attribute"""

    def test_encode_decode(self):
        attr = NextHopAttribute("192.0.2.1")
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.next_hop, "192.0.2.1")


class TestMEDAttribute(unittest.TestCase):
    """Test MED attribute"""

    def test_encode_decode(self):
        attr = MEDAttribute(100)
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.med, 100)

    def test_large_value(self):
        attr = MEDAttribute(4294967295)  # Max 32-bit
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertEqual(decoded.med, 4294967295)


class TestLocalPrefAttribute(unittest.TestCase):
    """Test LOCAL_PREF attribute"""

    def test_encode_decode(self):
        attr = LocalPrefAttribute(200)
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.local_pref, 200)


class TestAtomicAggregateAttribute(unittest.TestCase):
    """Test ATOMIC_AGGREGATE attribute"""

    def test_encode_decode(self):
        attr = AtomicAggregateAttribute()
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertIsNotNone(decoded)
        self.assertIsInstance(decoded, AtomicAggregateAttribute)


class TestAggregatorAttribute(unittest.TestCase):
    """Test AGGREGATOR attribute"""

    def test_encode_decode(self):
        attr = AggregatorAttribute(65001, "192.0.2.1")
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.asn, 65001)
        self.assertEqual(decoded.router_id, "192.0.2.1")


class TestCommunitiesAttribute(unittest.TestCase):
    """Test COMMUNITIES attribute"""

    def test_encode_decode_empty(self):
        attr = CommunitiesAttribute([])
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertIsNotNone(decoded)
        self.assertEqual(len(decoded.communities), 0)

    def test_encode_decode_single(self):
        comm = (65001 << 16) | 100  # 65001:100
        attr = CommunitiesAttribute([comm])
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertEqual(len(decoded.communities), 1)
        self.assertEqual(decoded.communities[0], comm)

    def test_encode_decode_multiple(self):
        comms = [
            (65001 << 16) | 100,
            (65001 << 16) | 200,
            COMMUNITY_NO_EXPORT
        ]
        attr = CommunitiesAttribute(comms)
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertEqual(len(decoded.communities), 3)
        self.assertEqual(decoded.communities, comms)

    def test_add_remove(self):
        attr = CommunitiesAttribute([])
        comm = (65001 << 16) | 100

        attr.add(comm)
        self.assertTrue(attr.has(comm))

        attr.remove(comm)
        self.assertFalse(attr.has(comm))

    def test_well_known_community(self):
        attr = CommunitiesAttribute([COMMUNITY_NO_EXPORT])
        self.assertTrue(attr.has(COMMUNITY_NO_EXPORT))


class TestOriginatorIDAttribute(unittest.TestCase):
    """Test ORIGINATOR_ID attribute"""

    def test_encode_decode(self):
        attr = OriginatorIDAttribute("192.0.2.1")
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.originator_id, "192.0.2.1")


class TestClusterListAttribute(unittest.TestCase):
    """Test CLUSTER_LIST attribute"""

    def test_encode_decode_empty(self):
        attr = ClusterListAttribute([])
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertIsNotNone(decoded)
        self.assertEqual(len(decoded.cluster_list), 0)

    def test_encode_decode_single(self):
        attr = ClusterListAttribute(["192.0.2.1"])
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertEqual(len(decoded.cluster_list), 1)
        self.assertEqual(decoded.cluster_list[0], "192.0.2.1")

    def test_encode_decode_multiple(self):
        clusters = ["192.0.2.1", "192.0.2.2", "192.0.2.3"]
        attr = ClusterListAttribute(clusters)
        data = attr.encode()

        decoded, consumed = PathAttribute.decode(data)
        self.assertEqual(decoded.cluster_list, clusters)

    def test_prepend(self):
        attr = ClusterListAttribute(["192.0.2.2"])
        attr.prepend("192.0.2.1")

        self.assertEqual(attr.cluster_list[0], "192.0.2.1")
        self.assertEqual(attr.cluster_list[1], "192.0.2.2")

    def test_contains(self):
        attr = ClusterListAttribute(["192.0.2.1", "192.0.2.2"])
        self.assertTrue(attr.contains("192.0.2.1"))
        self.assertFalse(attr.contains("192.0.2.99"))


class TestMultipleAttributes(unittest.TestCase):
    """Test encoding/decoding multiple attributes together"""

    def test_encode_decode_multiple(self):
        attrs = {
            ATTR_ORIGIN: OriginAttribute(ORIGIN_IGP),
            ATTR_AS_PATH: ASPathAttribute([(AS_SEQUENCE, [65001, 65002])]),
            ATTR_NEXT_HOP: NextHopAttribute("192.0.2.1"),
            ATTR_LOCAL_PREF: LocalPrefAttribute(100),
            ATTR_MED: MEDAttribute(50)
        }

        data = encode_path_attributes(attrs)
        decoded = decode_path_attributes(data)

        self.assertEqual(len(decoded), 5)
        self.assertIn(ATTR_ORIGIN, decoded)
        self.assertIn(ATTR_AS_PATH, decoded)
        self.assertIn(ATTR_NEXT_HOP, decoded)
        self.assertIn(ATTR_LOCAL_PREF, decoded)
        self.assertIn(ATTR_MED, decoded)

        self.assertEqual(decoded[ATTR_ORIGIN].origin, ORIGIN_IGP)
        self.assertEqual(decoded[ATTR_NEXT_HOP].next_hop, "192.0.2.1")
        self.assertEqual(decoded[ATTR_LOCAL_PREF].local_pref, 100)


if __name__ == '__main__':
    unittest.main()
