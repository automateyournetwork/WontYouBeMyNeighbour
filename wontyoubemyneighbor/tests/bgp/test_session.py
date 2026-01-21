"""
Tests for BGP session management

Tests BGPSession, BGPAgent, and BGPSpeaker classes.
"""

import unittest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from bgp.session import BGPSession, BGPSessionConfig
from bgp.agent import BGPAgent
from bgp.speaker import BGPSpeaker
from bgp.messages import BGPOpen, BGPKeepalive, BGPUpdate, BGPNotification, BGPCapability
from bgp.rib import BGPRoute
from bgp.attributes import OriginAttribute, ASPathAttribute, NextHopAttribute
from bgp.constants import *


class TestBGPSessionConfig(unittest.TestCase):
    """Test BGPSessionConfig"""

    def test_basic_config(self):
        """Test basic session configuration"""
        config = BGPSessionConfig(
            local_as=65001,
            local_router_id="192.0.2.1",
            local_ip="192.0.2.1",
            peer_as=65002,
            peer_ip="192.0.2.2"
        )

        self.assertEqual(config.local_as, 65001)
        self.assertEqual(config.peer_as, 65002)
        self.assertEqual(config.local_router_id, "192.0.2.1")
        self.assertEqual(config.peer_ip, "192.0.2.2")
        self.assertEqual(config.hold_time, 180)
        self.assertEqual(config.keepalive_time, 60)
        self.assertFalse(config.passive)

    def test_ibgp_config(self):
        """Test iBGP session configuration"""
        config = BGPSessionConfig(
            local_as=65001,
            local_router_id="192.0.2.1",
            local_ip="192.0.2.1",
            peer_as=65001,  # Same AS = iBGP
            peer_ip="192.0.2.2",
            route_reflector_client=True
        )

        self.assertEqual(config.local_as, config.peer_as)
        self.assertTrue(config.route_reflector_client)

    def test_passive_config(self):
        """Test passive mode configuration"""
        config = BGPSessionConfig(
            local_as=65001,
            local_router_id="192.0.2.1",
            local_ip="192.0.2.1",
            peer_as=65002,
            peer_ip="192.0.2.2",
            passive=True
        )

        self.assertTrue(config.passive)


class TestBGPSession(unittest.TestCase):
    """Test BGPSession class"""

    def setUp(self):
        """Set up test session"""
        self.config = BGPSessionConfig(
            local_as=65001,
            local_router_id="192.0.2.1",
            local_ip="192.0.2.1",
            peer_as=65002,
            peer_ip="192.0.2.2"
        )
        self.session = BGPSession(self.config)

    def test_session_initialization(self):
        """Test session initialization"""
        self.assertEqual(self.session.config.local_as, 65001)
        self.assertEqual(self.session.config.peer_as, 65002)
        self.assertIsNotNone(self.session.fsm)
        self.assertIsNotNone(self.session.capabilities)
        self.assertIsNotNone(self.session.adj_rib_in)
        self.assertIsNotNone(self.session.adj_rib_out)

    def test_session_id(self):
        """Test session ID generation"""
        expected_id = f"192.0.2.1:179-192.0.2.2:179"
        self.assertEqual(self.session.session_id, expected_id)

    def test_capability_configuration(self):
        """Test capability configuration"""
        self.session._configure_capabilities()

        # Should have 4-byte AS and route refresh in local_capabilities dict
        local_caps = self.session.capabilities.local_capabilities
        self.assertIn(CAP_FOUR_OCTET_AS, local_caps)
        self.assertIn(CAP_ROUTE_REFRESH, local_caps)

        # Multiprotocol capabilities are stored separately as (AFI, SAFI) tuples
        mp_caps = self.session.capabilities.multiprotocol_capabilities
        self.assertIn((AFI_IPV4, SAFI_UNICAST), mp_caps)

    def test_is_established(self):
        """Test is_established check"""
        # Initially not established
        self.assertFalse(self.session.is_established())

        # Set FSM to established
        self.session.fsm.state = STATE_ESTABLISHED
        self.assertTrue(self.session.is_established())

    def test_statistics(self):
        """Test statistics collection"""
        stats = self.session.get_statistics()

        self.assertIn('messages_sent', stats)
        self.assertIn('messages_received', stats)
        self.assertIn('routes_received', stats)
        self.assertIn('fsm_state', stats)
        self.assertEqual(stats['messages_sent'], 0)
        self.assertEqual(stats['messages_received'], 0)

    def test_build_route_from_update(self):
        """Test building BGPRoute from UPDATE message"""
        # _build_route_from_update expects a dict of {type_code: attribute_object}
        attributes = {
            ATTR_ORIGIN: OriginAttribute(ORIGIN_IGP),
            ATTR_AS_PATH: ASPathAttribute([(AS_SEQUENCE, [65002, 65003])]),
            ATTR_NEXT_HOP: NextHopAttribute("192.0.2.2")
        }

        route = self.session._build_route_from_update("203.0.113.0/24", attributes)

        self.assertIsNotNone(route)
        self.assertEqual(route.prefix, "203.0.113.0/24")
        self.assertEqual(route.prefix_len, 24)
        self.assertEqual(route.peer_id, self.session.peer_id)
        self.assertIn(ATTR_ORIGIN, route.path_attributes)
        self.assertIn(ATTR_AS_PATH, route.path_attributes)
        self.assertIn(ATTR_NEXT_HOP, route.path_attributes)


class TestBGPAgent(unittest.TestCase):
    """Test BGPAgent class"""

    def setUp(self):
        """Set up test agent"""
        self.agent = BGPAgent(
            local_as=65001,
            router_id="192.0.2.1"
        )

    def test_agent_initialization(self):
        """Test agent initialization"""
        self.assertEqual(self.agent.local_as, 65001)
        self.assertEqual(self.agent.router_id, "192.0.2.1")
        self.assertIsNotNone(self.agent.loc_rib)
        self.assertIsNotNone(self.agent.best_path_selector)
        self.assertIsNotNone(self.agent.policy_engine)
        self.assertEqual(len(self.agent.sessions), 0)

    def test_add_peer(self):
        """Test adding peer"""
        config = BGPSessionConfig(
            local_as=65001,
            local_router_id="192.0.2.1",
            local_ip="192.0.2.1",
            peer_as=65002,
            peer_ip="192.0.2.2"
        )

        session = self.agent.add_peer(config)

        self.assertIsNotNone(session)
        self.assertIn("192.0.2.2", self.agent.sessions)
        self.assertEqual(len(self.agent.sessions), 1)
        self.assertIs(session.loc_rib, self.agent.loc_rib)

    def test_remove_peer(self):
        """Test removing peer"""
        config = BGPSessionConfig(
            local_as=65001,
            local_router_id="192.0.2.1",
            local_ip="192.0.2.1",
            peer_as=65002,
            peer_ip="192.0.2.2"
        )

        self.agent.add_peer(config)
        self.assertEqual(len(self.agent.sessions), 1)

        self.agent.remove_peer("192.0.2.2")
        self.assertEqual(len(self.agent.sessions), 0)

    def test_enable_route_reflection(self):
        """Test enabling route reflection"""
        self.assertIsNone(self.agent.route_reflector)

        self.agent.enable_route_reflection()

        self.assertIsNotNone(self.agent.route_reflector)
        self.assertEqual(self.agent.route_reflector.cluster_id, "192.0.2.1")
        self.assertEqual(self.agent.route_reflector.router_id, "192.0.2.1")

    def test_enable_route_reflection_with_cluster_id(self):
        """Test enabling route reflection with custom cluster ID"""
        self.agent.enable_route_reflection(cluster_id="10.0.0.1")

        self.assertIsNotNone(self.agent.route_reflector)
        self.assertEqual(self.agent.route_reflector.cluster_id, "10.0.0.1")

    def test_get_statistics(self):
        """Test statistics collection"""
        stats = self.agent.get_statistics()

        self.assertEqual(stats['local_as'], 65001)
        self.assertEqual(stats['router_id'], "192.0.2.1")
        self.assertEqual(stats['total_peers'], 0)
        self.assertEqual(stats['established_peers'], 0)
        self.assertEqual(stats['loc_rib_routes'], 0)
        self.assertIn('peers', stats)

    def test_should_advertise_to_peer_ebgp(self):
        """Test route advertisement rules for eBGP"""
        # Add eBGP peer
        config = BGPSessionConfig(
            local_as=65001,
            local_router_id="192.0.2.1",
            local_ip="192.0.2.1",
            peer_as=65002,
            peer_ip="192.0.2.2"
        )
        session = self.agent.add_peer(config)

        # Create route from different peer
        route = BGPRoute(
            prefix="203.0.113.0/24",
            prefix_len=24,
            path_attributes={},
            peer_id="192.0.2.3",
            peer_ip="192.0.2.3"
        )

        # Should advertise (eBGP advertises all routes)
        self.assertTrue(self.agent._should_advertise_to_peer(route, session))

    def test_should_not_advertise_back_to_source(self):
        """Test not advertising route back to source"""
        config = BGPSessionConfig(
            local_as=65001,
            local_router_id="192.0.2.1",
            local_ip="192.0.2.1",
            peer_as=65002,
            peer_ip="192.0.2.2"
        )
        session = self.agent.add_peer(config)

        # Create route from same peer
        route = BGPRoute(
            prefix="203.0.113.0/24",
            prefix_len=24,
            path_attributes={},
            peer_id="192.0.2.2",
            peer_ip="192.0.2.2"
        )

        # Should not advertise back to source
        self.assertFalse(self.agent._should_advertise_to_peer(route, session))


class TestBGPSpeaker(unittest.TestCase):
    """Test BGPSpeaker class"""

    def setUp(self):
        """Set up test speaker"""
        self.speaker = BGPSpeaker(
            local_as=65001,
            router_id="192.0.2.1",
            log_level="ERROR"  # Suppress logs during tests
        )

    def test_speaker_initialization(self):
        """Test speaker initialization"""
        self.assertEqual(self.speaker.local_as, 65001)
        self.assertEqual(self.speaker.router_id, "192.0.2.1")
        self.assertIsNotNone(self.speaker.agent)
        self.assertEqual(len(self.speaker.peer_configs), 0)

    def test_add_peer(self):
        """Test adding peer to speaker"""
        self.speaker.add_peer(
            peer_ip="192.0.2.2",
            peer_as=65002
        )

        self.assertIn("192.0.2.2", self.speaker.peer_configs)
        self.assertEqual(len(self.speaker.peer_configs), 1)
        self.assertIn("192.0.2.2", self.speaker.agent.sessions)

    def test_add_multiple_peers(self):
        """Test adding multiple peers"""
        self.speaker.add_peer(peer_ip="192.0.2.2", peer_as=65002)
        self.speaker.add_peer(peer_ip="192.0.2.3", peer_as=65003)
        self.speaker.add_peer(peer_ip="192.0.2.4", peer_as=65001, passive=True)

        self.assertEqual(len(self.speaker.peer_configs), 3)

    def test_remove_peer(self):
        """Test removing peer"""
        self.speaker.add_peer(peer_ip="192.0.2.2", peer_as=65002)
        self.assertEqual(len(self.speaker.peer_configs), 1)

        self.speaker.remove_peer("192.0.2.2")
        self.assertEqual(len(self.speaker.peer_configs), 0)

    def test_enable_route_reflection(self):
        """Test enabling route reflection"""
        self.speaker.enable_route_reflection()
        self.assertIsNotNone(self.speaker.agent.route_reflector)

    def test_get_all_peers(self):
        """Test getting all peer IPs"""
        self.speaker.add_peer(peer_ip="192.0.2.2", peer_as=65002)
        self.speaker.add_peer(peer_ip="192.0.2.3", peer_as=65003)

        peers = self.speaker.get_all_peers()
        self.assertEqual(len(peers), 2)
        self.assertIn("192.0.2.2", peers)
        self.assertIn("192.0.2.3", peers)

    def test_get_established_peers(self):
        """Test getting established peers"""
        self.speaker.add_peer(peer_ip="192.0.2.2", peer_as=65002)

        # Initially no established peers
        established = self.speaker.get_established_peers()
        self.assertEqual(len(established), 0)

        # Set session to established
        session = self.speaker.agent.sessions["192.0.2.2"]
        session.fsm.state = STATE_ESTABLISHED

        established = self.speaker.get_established_peers()
        self.assertEqual(len(established), 1)
        self.assertIn("192.0.2.2", established)

    def test_is_established(self):
        """Test checking if peer is established"""
        self.speaker.add_peer(peer_ip="192.0.2.2", peer_as=65002)

        # Initially not established
        self.assertFalse(self.speaker.is_established("192.0.2.2"))

        # Set to established
        session = self.speaker.agent.sessions["192.0.2.2"]
        session.fsm.state = STATE_ESTABLISHED

        self.assertTrue(self.speaker.is_established("192.0.2.2"))

    def test_get_routes(self):
        """Test getting routes"""
        # Initially no routes
        routes = self.speaker.get_routes()
        self.assertEqual(len(routes), 0)

        # Add route to Loc-RIB
        route = BGPRoute(
            prefix="203.0.113.0/24",
            prefix_len=24,
            path_attributes={},
            peer_id="192.0.2.2",
            peer_ip="192.0.2.2"
        )
        self.speaker.agent.loc_rib.install_route(route)

        routes = self.speaker.get_routes()
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0].prefix, "203.0.113.0/24")

    def test_get_route(self):
        """Test getting specific route"""
        # No route initially
        route = self.speaker.get_route("203.0.113.0/24")
        self.assertIsNone(route)

        # Add route
        test_route = BGPRoute(
            prefix="203.0.113.0/24",
            prefix_len=24,
            path_attributes={},
            peer_id="192.0.2.2",
            peer_ip="192.0.2.2"
        )
        self.speaker.agent.loc_rib.install_route(test_route)

        route = self.speaker.get_route("203.0.113.0/24")
        self.assertIsNotNone(route)
        self.assertEqual(route.prefix, "203.0.113.0/24")


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestBGPSessionConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestBGPSession))
    suite.addTests(loader.loadTestsFromTestCase(TestBGPAgent))
    suite.addTests(loader.loadTestsFromTestCase(TestBGPSpeaker))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == '__main__':
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
