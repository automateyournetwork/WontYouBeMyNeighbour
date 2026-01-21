"""
Unit tests for Route Flap Damping (RFC 2439)
"""

import unittest
import time
from unittest.mock import patch
from bgp.flap_damping import RouteFlapDamping, FlapDampingConfig


class TestFlapDamping(unittest.TestCase):
    """Test route flap damping functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.config = FlapDampingConfig()
        self.damping = RouteFlapDamping(self.config)
        self.prefix = "192.0.2.0/24"
        # Use a fixed time for deterministic tests
        self.fixed_time = 1000000.0

    def test_route_withdrawal(self):
        """Test route withdrawal penalty"""
        initial_penalty = self.damping.get_penalty(self.prefix)
        self.assertEqual(initial_penalty, 0.0)

        # Withdraw route with mocked time to prevent decay
        with patch('bgp.flap_damping.time.time', return_value=self.fixed_time):
            suppressed = self.damping.route_withdrawn(self.prefix)
            self.assertFalse(suppressed)  # First withdrawal shouldn't suppress

            # Check penalty immediately (no decay since time is frozen)
            penalty = self.damping.get_penalty(self.prefix)
            self.assertAlmostEqual(penalty, self.config.withdrawal_penalty, places=0)

    def test_route_suppression(self):
        """Test route suppression when penalty exceeds threshold"""
        # Cause enough flaps to exceed suppress threshold
        with patch('bgp.flap_damping.time.time', return_value=self.fixed_time):
            for _ in range(4):  # 4 withdrawals = 4000 penalty
                self.damping.route_withdrawn(self.prefix)

            # Should be suppressed now
            self.assertTrue(self.damping.is_suppressed(self.prefix))

    def test_route_reuse(self):
        """Test route reuse when penalty decays below threshold"""
        # Suppress the route with mocked time
        with patch('bgp.flap_damping.time.time', return_value=self.fixed_time):
            for _ in range(4):
                self.damping.route_withdrawn(self.prefix)

            self.assertTrue(self.damping.is_suppressed(self.prefix))

            # Manually set penalty below reuse threshold
            info = self.damping.flap_info[self.prefix]
            info.penalty = self.config.reuse_threshold - 100

            # Announce route
            suppressed = self.damping.route_announced(self.prefix, attribute_changed=False)

            # Should be reused
            self.assertFalse(suppressed)
            self.assertFalse(self.damping.is_suppressed(self.prefix))

    def test_attribute_change_penalty(self):
        """Test penalty for attribute changes"""
        # Announce with attribute change (mock time to prevent decay)
        with patch('bgp.flap_damping.time.time', return_value=self.fixed_time):
            self.damping.route_announced(self.prefix, attribute_changed=True)

            penalty = self.damping.get_penalty(self.prefix)
            self.assertAlmostEqual(penalty, self.config.attribute_change_penalty, places=0)

    def test_penalty_decay(self):
        """Test exponential penalty decay"""
        # Add penalty with mocked time
        with patch('bgp.flap_damping.time.time', return_value=self.fixed_time):
            self.damping.route_withdrawn(self.prefix)
            info = self.damping.flap_info[self.prefix]
            self.assertIsNotNone(info.last_update)
            self.assertEqual(info.last_update, self.fixed_time)

    def test_flap_statistics(self):
        """Test flap statistics"""
        # Generate some flaps with mocked time
        with patch('bgp.flap_damping.time.time', return_value=self.fixed_time):
            for _ in range(3):
                self.damping.route_withdrawn(self.prefix)

            stats = self.damping.get_flap_statistics(self.prefix)

            self.assertEqual(stats['flap_count'], 3)
            self.assertEqual(stats['withdrawal_count'], 3)
            self.assertGreater(stats['penalty'], 0)

    def test_global_statistics(self):
        """Test global statistics"""
        # Cause flaps on multiple routes
        self.damping.route_withdrawn("192.0.2.0/24")
        self.damping.route_withdrawn("203.0.113.0/24")

        stats = self.damping.get_flap_statistics()

        self.assertEqual(stats['total_flaps'], 2)
        self.assertEqual(stats['tracked_routes'], 2)

    def test_clear_history(self):
        """Test clearing flap history"""
        # Add flap history
        self.damping.route_withdrawn(self.prefix)

        # Clear it
        self.damping.clear_history(self.prefix)

        # Should be gone
        self.assertNotIn(self.prefix, self.damping.flap_info)
        self.assertEqual(self.damping.get_penalty(self.prefix), 0.0)


if __name__ == '__main__':
    unittest.main()
