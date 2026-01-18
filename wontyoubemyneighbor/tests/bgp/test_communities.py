"""
BGP Communities Utilities Tests
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import unittest
from bgp.communities import *
from bgp.constants import *


class TestCommunityParsing(unittest.TestCase):
    """Test community parsing"""

    def test_parse_community_standard(self):
        """Test parsing standard AS:Value format"""
        comm = parse_community("65001:100")
        self.assertIsNotNone(comm)
        self.assertEqual(comm, (65001 << 16) | 100)

    def test_parse_community_wellknown(self):
        """Test parsing well-known community names"""
        self.assertEqual(parse_community("NO_EXPORT"), COMMUNITY_NO_EXPORT)
        self.assertEqual(parse_community("NO_ADVERTISE"), COMMUNITY_NO_ADVERTISE)
        self.assertEqual(parse_community("NO_EXPORT_SUBCONFED"), COMMUNITY_NO_EXPORT_SUBCONFED)
        self.assertEqual(parse_community("NOPEER"), COMMUNITY_NOPEER)

    def test_parse_community_invalid(self):
        """Test parsing invalid communities"""
        self.assertIsNone(parse_community("invalid"))
        self.assertIsNone(parse_community("65001"))
        self.assertIsNone(parse_community("65001:"))
        self.assertIsNone(parse_community(":100"))
        self.assertIsNone(parse_community("99999:100"))  # AS too large


class TestCommunityFormatting(unittest.TestCase):
    """Test community formatting"""

    def test_format_community_standard(self):
        """Test formatting standard community"""
        comm = (65001 << 16) | 100
        self.assertEqual(format_community(comm), "65001:100")

    def test_format_community_wellknown(self):
        """Test formatting well-known communities"""
        self.assertEqual(format_community(COMMUNITY_NO_EXPORT), "NO_EXPORT")
        self.assertEqual(format_community(COMMUNITY_NO_ADVERTISE), "NO_ADVERTISE")

    def test_roundtrip(self):
        """Test parse/format round-trip"""
        original = "65001:100"
        comm = parse_community(original)
        formatted = format_community(comm)
        self.assertEqual(original, formatted)


class TestCommunityList(unittest.TestCase):
    """Test community list operations"""

    def test_parse_community_list(self):
        """Test parsing comma-separated community list"""
        comms = parse_community_list("65001:100,65001:200,NO_EXPORT")
        self.assertEqual(len(comms), 3)
        self.assertIn((65001 << 16) | 100, comms)
        self.assertIn((65001 << 16) | 200, comms)
        self.assertIn(COMMUNITY_NO_EXPORT, comms)

    def test_format_community_list(self):
        """Test formatting community list"""
        comms = [(65001 << 16) | 100, (65001 << 16) | 200, COMMUNITY_NO_EXPORT]
        formatted = format_community_list(comms)
        self.assertIn("65001:100", formatted)
        self.assertIn("65001:200", formatted)
        self.assertIn("NO_EXPORT", formatted)


class TestWellKnownCommunities(unittest.TestCase):
    """Test well-known community checks"""

    def test_is_well_known(self):
        """Test is_well_known()"""
        self.assertTrue(is_well_known(COMMUNITY_NO_EXPORT))
        self.assertTrue(is_well_known(COMMUNITY_NO_ADVERTISE))
        self.assertFalse(is_well_known((65001 << 16) | 100))

    def test_has_no_export(self):
        """Test has_no_export()"""
        comms = [(65001 << 16) | 100, COMMUNITY_NO_EXPORT]
        self.assertTrue(has_no_export(comms))

        comms = [(65001 << 16) | 100, (65001 << 16) | 200]
        self.assertFalse(has_no_export(comms))

    def test_has_no_advertise(self):
        """Test has_no_advertise()"""
        comms = [(65001 << 16) | 100, COMMUNITY_NO_ADVERTISE]
        self.assertTrue(has_no_advertise(comms))

    def test_filter_well_known(self):
        """Test filtering well-known communities"""
        comms = [(65001 << 16) | 100, COMMUNITY_NO_EXPORT, (65001 << 16) | 200]
        filtered = filter_well_known(comms)
        self.assertEqual(len(filtered), 2)
        self.assertNotIn(COMMUNITY_NO_EXPORT, filtered)


class TestCommunityMatching(unittest.TestCase):
    """Test community regex matching"""

    def test_matches_regex_exact(self):
        """Test exact match"""
        comm = parse_community("65001:100")
        self.assertTrue(matches_regex(comm, "65001:100"))
        self.assertFalse(matches_regex(comm, "65001:200"))

    def test_matches_regex_wildcard_value(self):
        """Test wildcard value match"""
        comm = parse_community("65001:100")
        self.assertTrue(matches_regex(comm, "65001:*"))
        self.assertFalse(matches_regex(comm, "65002:*"))

    def test_matches_regex_wildcard_as(self):
        """Test wildcard AS match"""
        comm = parse_community("65001:100")
        self.assertTrue(matches_regex(comm, "*:100"))
        self.assertFalse(matches_regex(comm, "*:200"))

    def test_matches_any(self):
        """Test matches_any()"""
        comm = parse_community("65001:100")
        self.assertTrue(matches_any(comm, ["65001:*", "65002:*"]))
        self.assertTrue(matches_any(comm, ["*:100"]))
        self.assertFalse(matches_any(comm, ["65002:*", "65003:*"]))


class TestCommunityExtraction(unittest.TestCase):
    """Test extracting AS and value from community"""

    def test_extract_as(self):
        """Test extracting AS number"""
        comm = parse_community("65001:100")
        self.assertEqual(extract_as(comm), 65001)

    def test_extract_value(self):
        """Test extracting value"""
        comm = parse_community("65001:100")
        self.assertEqual(extract_value(comm), 100)

    def test_create_community(self):
        """Test creating community"""
        comm = create_community(65001, 100)
        self.assertIsNotNone(comm)
        self.assertEqual(extract_as(comm), 65001)
        self.assertEqual(extract_value(comm), 100)

    def test_create_community_invalid(self):
        """Test creating invalid community"""
        self.assertIsNone(create_community(99999, 100))  # AS too large
        self.assertIsNone(create_community(65001, 99999))  # Value too large


class TestCommunitySorting(unittest.TestCase):
    """Test community sorting"""

    def test_sort_communities(self):
        """Test sorting communities"""
        comms = [
            (65002 << 16) | 200,
            COMMUNITY_NO_EXPORT,
            (65001 << 16) | 100,
            COMMUNITY_NO_ADVERTISE,
            (65001 << 16) | 50
        ]

        sorted_comms = sort_communities(comms)

        # Well-known should come first
        self.assertTrue(is_well_known(sorted_comms[0]))
        self.assertTrue(is_well_known(sorted_comms[1]))

        # Regular communities should be sorted
        self.assertFalse(is_well_known(sorted_comms[2]))
        self.assertFalse(is_well_known(sorted_comms[3]))
        self.assertFalse(is_well_known(sorted_comms[4]))


if __name__ == '__main__':
    unittest.main()
