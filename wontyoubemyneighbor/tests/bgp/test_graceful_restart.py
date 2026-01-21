"""
Unit tests for BGP Graceful Restart (RFC 4724)
"""

import unittest
import asyncio
import time
from unittest.mock import patch, MagicMock, AsyncMock
from bgp.graceful_restart import GracefulRestartManager, RestartState
from bgp.rib import BGPRoute
from bgp.constants import AFI_IPV4, SAFI_UNICAST


class TestGracefulRestart(unittest.TestCase):
    """Test graceful restart functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.gr_mgr = GracefulRestartManager(router_id="10.0.1.1")
        self.peer_ip = "192.0.2.1"

        # Create sample routes
        self.routes = {
            "192.0.2.0/24": BGPRoute(
                prefix="192.0.2.0/24",
                prefix_len=24,
                path_attributes={},
                peer_id="10.0.1.2",
                peer_ip=self.peer_ip
            ),
            "203.0.113.0/24": BGPRoute(
                prefix="203.0.113.0/24",
                prefix_len=24,
                path_attributes={},
                peer_id="10.0.1.2",
                peer_ip=self.peer_ip
            )
        }

    def test_peer_session_down(self):
        """Test handling peer session down"""
        # Mock the async timer to avoid event loop issues
        with patch.object(self.gr_mgr, '_start_restart_timer'):
            # Session goes down
            self.gr_mgr.peer_session_down(self.peer_ip, self.routes, restart_time=120)

            # Check state
            self.assertEqual(self.gr_mgr.peer_states[self.peer_ip], RestartState.HELPER)
            self.assertEqual(len(self.gr_mgr.stale_routes[self.peer_ip]), 2)

            # Check routes marked stale
            for route in self.routes.values():
                self.assertTrue(route.stale)

    def test_peer_session_up(self):
        """Test handling peer session coming up"""
        # Mock the async timer to avoid event loop issues
        with patch.object(self.gr_mgr, '_start_restart_timer'):
            # Setup: session down
            self.gr_mgr.peer_session_down(self.peer_ip, self.routes)

        # Session comes back up
        self.gr_mgr.peer_session_up(self.peer_ip, supports_graceful_restart=True)

        # Timer should be cancelled (none running because we mocked it)
        self.assertNotIn(self.peer_ip, self.gr_mgr.restart_timers)

    def test_route_refreshed(self):
        """Test marking route as refreshed"""
        # Mock the async timer to avoid event loop issues
        with patch.object(self.gr_mgr, '_start_restart_timer'):
            # Setup: session down with stale routes
            self.gr_mgr.peer_session_down(self.peer_ip, self.routes)

        # Refresh one route
        self.gr_mgr.route_refreshed(self.peer_ip, "192.0.2.0/24")

        # Check stale routes updated
        stale_routes = self.gr_mgr.stale_routes[self.peer_ip]
        self.assertNotIn("192.0.2.0/24", stale_routes)
        self.assertIn("203.0.113.0/24", stale_routes)

    def test_end_of_rib(self):
        """Test End-of-RIB handling"""
        # Mock the async timer to avoid event loop issues
        with patch.object(self.gr_mgr, '_start_restart_timer'):
            # Setup: session down, then up
            self.gr_mgr.peer_session_down(self.peer_ip, self.routes)

        self.gr_mgr.peer_session_up(self.peer_ip, supports_graceful_restart=True)

        # Refresh one route
        self.gr_mgr.route_refreshed(self.peer_ip, "192.0.2.0/24")

        # Receive End-of-RIB
        to_remove = self.gr_mgr.handle_end_of_rib(self.peer_ip, AFI_IPV4, SAFI_UNICAST)

        # Only non-refreshed route should be removed
        self.assertEqual(len(to_remove), 1)
        self.assertIn("203.0.113.0/24", to_remove)
        self.assertNotIn("192.0.2.0/24", to_remove)

        # State should be NORMAL
        self.assertEqual(self.gr_mgr.peer_states[self.peer_ip], RestartState.NORMAL)

    def test_is_peer_restarting(self):
        """Test checking if peer is restarting"""
        # Initially not restarting
        self.assertFalse(self.gr_mgr.is_peer_restarting(self.peer_ip))

        # Mock the async timer to avoid event loop issues
        with patch.object(self.gr_mgr, '_start_restart_timer'):
            # Session goes down
            self.gr_mgr.peer_session_down(self.peer_ip, self.routes)

        # Now restarting
        self.assertTrue(self.gr_mgr.is_peer_restarting(self.peer_ip))

    def test_get_stale_route_count(self):
        """Test getting stale route count"""
        # Initially zero
        self.assertEqual(self.gr_mgr.get_stale_route_count(self.peer_ip), 0)

        # Mock the async timer to avoid event loop issues
        with patch.object(self.gr_mgr, '_start_restart_timer'):
            # Session goes down
            self.gr_mgr.peer_session_down(self.peer_ip, self.routes)

        # Should have 2 stale routes
        self.assertEqual(self.gr_mgr.get_stale_route_count(self.peer_ip), 2)

    def test_cleanup_peer(self):
        """Test peer cleanup"""
        # Mock the async timer to avoid event loop issues
        with patch.object(self.gr_mgr, '_start_restart_timer'):
            # Setup: session down
            self.gr_mgr.peer_session_down(self.peer_ip, self.routes)

        # Cleanup
        self.gr_mgr.cleanup_peer(self.peer_ip)

        # Everything should be cleared
        self.assertNotIn(self.peer_ip, self.gr_mgr.stale_routes)
        self.assertNotIn(self.peer_ip, self.gr_mgr.peer_states)
        self.assertNotIn(self.peer_ip, self.gr_mgr.restart_timers)

    def test_statistics(self):
        """Test statistics"""
        stats = self.gr_mgr.get_statistics()

        self.assertIn('total_stale_routes', stats)
        self.assertIn('restarting_peers', stats)
        self.assertEqual(stats['total_stale_routes'], 0)
        self.assertEqual(stats['restarting_peers'], 0)

        # Mock the async timer to avoid event loop issues
        with patch.object(self.gr_mgr, '_start_restart_timer'):
            # Add stale routes
            self.gr_mgr.peer_session_down(self.peer_ip, self.routes)

        stats = self.gr_mgr.get_statistics()
        self.assertEqual(stats['total_stale_routes'], 2)
        self.assertEqual(stats['restarting_peers'], 1)


if __name__ == '__main__':
    unittest.main()
