"""
BGP Finite State Machine Tests

Tests for BGP FSM state transitions and timer handling
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import unittest
import asyncio
from bgp.fsm import BGPFSM, BGPEvent
from bgp.constants import *


class TestBGPFSMBasic(unittest.TestCase):
    """Test basic FSM operations"""

    def setUp(self):
        """Create FSM instance"""
        self.fsm = BGPFSM("192.0.2.1", 65001, 65002, hold_time=90, connect_retry_time=120)

    def test_initial_state(self):
        """Test FSM starts in Idle state"""
        self.assertEqual(self.fsm.get_state(), STATE_IDLE)
        self.assertEqual(self.fsm.get_state_name(), "Idle")

    def test_hold_time_negotiation(self):
        """Test hold time negotiation"""
        # Both non-zero: use minimum
        result = self.fsm.negotiate_hold_time(60)
        self.assertEqual(result, 60)
        self.assertEqual(self.fsm.negotiated_hold_time, 60)
        self.assertEqual(self.fsm.keepalive_time, 20)

        # Peer zero: use zero
        self.fsm.hold_time = 90
        result = self.fsm.negotiate_hold_time(0)
        self.assertEqual(result, 0)
        self.assertEqual(self.fsm.negotiated_hold_time, 0)

        # Local zero: use zero
        self.fsm.hold_time = 0
        result = self.fsm.negotiate_hold_time(90)
        self.assertEqual(result, 0)

        # Invalid (< 3): return -1
        self.fsm.hold_time = 90
        result = self.fsm.negotiate_hold_time(2)
        self.assertEqual(result, -1)


class TestBGPFSMTransitions(unittest.TestCase):
    """Test FSM state transitions"""

    def setUp(self):
        """Create FSM instance with callbacks"""
        self.fsm = BGPFSM("192.0.2.1", 65001, 65002, hold_time=90, connect_retry_time=1)

        # Track callback invocations
        self.state_changes = []
        self.open_sent = False
        self.keepalive_sent = False
        self.notification_sent = False
        self.tcp_connected = False
        self.tcp_disconnected = False
        self.established_called = False

        def on_state_change(old, new):
            self.state_changes.append((old, new))

        def on_send_open():
            self.open_sent = True

        def on_send_keepalive():
            self.keepalive_sent = True

        def on_send_notification(code, subcode):
            self.notification_sent = True

        def on_tcp_connect():
            self.tcp_connected = True

        def on_tcp_disconnect():
            self.tcp_disconnected = True

        def on_established():
            self.established_called = True

        self.fsm.on_state_change = on_state_change
        self.fsm.on_send_open = on_send_open
        self.fsm.on_send_keepalive = on_send_keepalive
        self.fsm.on_send_notification = on_send_notification
        self.fsm.on_tcp_connect = on_tcp_connect
        self.fsm.on_tcp_disconnect = on_tcp_disconnect
        self.fsm.on_established = on_established

    def test_idle_to_connect(self):
        """Test Idle -> Connect transition"""
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStart))

        self.assertEqual(self.fsm.get_state(), STATE_CONNECT)
        self.assertTrue(self.tcp_connected)
        self.assertEqual(len(self.state_changes), 1)
        self.assertEqual(self.state_changes[0], (STATE_IDLE, STATE_CONNECT))

    def test_connect_to_opensent(self):
        """Test Connect -> OpenSent transition"""
        # Go to Connect first
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStart))
        self.assertEqual(self.fsm.get_state(), STATE_CONNECT)

        # TCP connection confirmed
        asyncio.run(self.fsm.process_event(BGPEvent.TcpConnectionConfirmed))

        self.assertEqual(self.fsm.get_state(), STATE_OPENSENT)
        self.assertTrue(self.open_sent)

    def test_connect_to_active_on_failure(self):
        """Test Connect -> Active on TCP failure"""
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStart))
        asyncio.run(self.fsm.process_event(BGPEvent.TcpConnectionFails))

        self.assertEqual(self.fsm.get_state(), STATE_ACTIVE)

    def test_opensent_to_openconfirm(self):
        """Test OpenSent -> OpenConfirm transition"""
        # Get to OpenSent
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStart))
        asyncio.run(self.fsm.process_event(BGPEvent.TcpConnectionConfirmed))
        self.assertEqual(self.fsm.get_state(), STATE_OPENSENT)

        # Receive OPEN
        self.keepalive_sent = False
        asyncio.run(self.fsm.process_event(BGPEvent.BGPOpen))

        self.assertEqual(self.fsm.get_state(), STATE_OPENCONFIRM)
        self.assertTrue(self.keepalive_sent)

    def test_openconfirm_to_established(self):
        """Test OpenConfirm -> Established transition"""
        # Get to OpenConfirm
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStart))
        asyncio.run(self.fsm.process_event(BGPEvent.TcpConnectionConfirmed))
        asyncio.run(self.fsm.process_event(BGPEvent.BGPOpen))
        self.assertEqual(self.fsm.get_state(), STATE_OPENCONFIRM)

        # Receive KEEPALIVE
        asyncio.run(self.fsm.process_event(BGPEvent.KeepAliveMsg))

        self.assertEqual(self.fsm.get_state(), STATE_ESTABLISHED)
        self.assertTrue(self.established_called)

    def test_full_establishment_flow(self):
        """Test complete Idle -> Established flow"""
        # Idle -> Connect
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStart))
        self.assertEqual(self.fsm.get_state(), STATE_CONNECT)

        # Connect -> OpenSent
        asyncio.run(self.fsm.process_event(BGPEvent.TcpConnectionConfirmed))
        self.assertEqual(self.fsm.get_state(), STATE_OPENSENT)

        # OpenSent -> OpenConfirm
        asyncio.run(self.fsm.process_event(BGPEvent.BGPOpen))
        self.assertEqual(self.fsm.get_state(), STATE_OPENCONFIRM)

        # OpenConfirm -> Established
        asyncio.run(self.fsm.process_event(BGPEvent.KeepAliveMsg))
        self.assertEqual(self.fsm.get_state(), STATE_ESTABLISHED)

        # Verify all transitions recorded
        self.assertEqual(len(self.state_changes), 4)
        self.assertTrue(self.established_called)

    def test_manual_stop_from_established(self):
        """Test ManualStop from Established"""
        # Get to Established
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStart))
        asyncio.run(self.fsm.process_event(BGPEvent.TcpConnectionConfirmed))
        asyncio.run(self.fsm.process_event(BGPEvent.BGPOpen))
        asyncio.run(self.fsm.process_event(BGPEvent.KeepAliveMsg))
        self.assertEqual(self.fsm.get_state(), STATE_ESTABLISHED)

        # Manual stop
        self.notification_sent = False
        self.tcp_disconnected = False
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStop))

        self.assertEqual(self.fsm.get_state(), STATE_IDLE)
        self.assertTrue(self.notification_sent)
        self.assertTrue(self.tcp_disconnected)

    def test_hold_timer_expires(self):
        """Test hold timer expiration"""
        # Get to OpenSent
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStart))
        asyncio.run(self.fsm.process_event(BGPEvent.TcpConnectionConfirmed))
        self.assertEqual(self.fsm.get_state(), STATE_OPENSENT)

        # Hold timer expires
        self.notification_sent = False
        asyncio.run(self.fsm.process_event(BGPEvent.HoldTimer_Expires))

        self.assertEqual(self.fsm.get_state(), STATE_IDLE)
        self.assertTrue(self.notification_sent)

    def test_bgp_open_error(self):
        """Test BGP OPEN message error"""
        # Get to OpenSent
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStart))
        asyncio.run(self.fsm.process_event(BGPEvent.TcpConnectionConfirmed))
        self.assertEqual(self.fsm.get_state(), STATE_OPENSENT)

        # OPEN error
        self.notification_sent = False
        asyncio.run(self.fsm.process_event(BGPEvent.BGPOpenMsgErr))

        self.assertEqual(self.fsm.get_state(), STATE_IDLE)
        self.assertTrue(self.notification_sent)

    def test_tcp_connection_fails_from_opensent(self):
        """Test TCP connection failure from OpenSent"""
        # Get to OpenSent
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStart))
        asyncio.run(self.fsm.process_event(BGPEvent.TcpConnectionConfirmed))
        self.assertEqual(self.fsm.get_state(), STATE_OPENSENT)

        # TCP fails
        asyncio.run(self.fsm.process_event(BGPEvent.TcpConnectionFails))

        self.assertEqual(self.fsm.get_state(), STATE_ACTIVE)

    def test_notification_from_established(self):
        """Test receiving NOTIFICATION in Established"""
        # Get to Established
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStart))
        asyncio.run(self.fsm.process_event(BGPEvent.TcpConnectionConfirmed))
        asyncio.run(self.fsm.process_event(BGPEvent.BGPOpen))
        asyncio.run(self.fsm.process_event(BGPEvent.KeepAliveMsg))
        self.assertEqual(self.fsm.get_state(), STATE_ESTABLISHED)

        # Receive NOTIFICATION
        asyncio.run(self.fsm.process_event(BGPEvent.NotifMsg))

        self.assertEqual(self.fsm.get_state(), STATE_IDLE)


class TestBGPFSMTimers(unittest.TestCase):
    """Test FSM timer handling"""

    def setUp(self):
        """Create FSM with short timers for testing"""
        self.fsm = BGPFSM("192.0.2.1", 65001, 65002, hold_time=3, connect_retry_time=1)
        self.events_fired = []

        async def capture_event(event):
            self.events_fired.append(event)

        # Store original process_event
        self.original_process_event = self.fsm.process_event

    def test_connect_retry_timer_starts(self):
        """Test connect retry timer starts in Connect state"""
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStart))

        # Timer should be set
        self.assertIsNotNone(self.fsm._connect_retry_timer)

    def test_hold_timer_starts(self):
        """Test hold timer starts in OpenSent state"""
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStart))
        asyncio.run(self.fsm.process_event(BGPEvent.TcpConnectionConfirmed))

        # Hold timer should be set
        self.assertIsNotNone(self.fsm._hold_timer)

    def test_keepalive_timer_starts(self):
        """Test keepalive timer starts in OpenConfirm state"""
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStart))
        asyncio.run(self.fsm.process_event(BGPEvent.TcpConnectionConfirmed))
        asyncio.run(self.fsm.process_event(BGPEvent.BGPOpen))

        # Keepalive timer should be set
        self.assertIsNotNone(self.fsm._keepalive_timer)

    def test_timers_stop_on_manual_stop(self):
        """Test all timers stop on ManualStop"""
        # Get to Established with timers running
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStart))
        asyncio.run(self.fsm.process_event(BGPEvent.TcpConnectionConfirmed))
        asyncio.run(self.fsm.process_event(BGPEvent.BGPOpen))
        asyncio.run(self.fsm.process_event(BGPEvent.KeepAliveMsg))

        # Stop
        asyncio.run(self.fsm.process_event(BGPEvent.ManualStop))

        # All timers should be None
        self.assertIsNone(self.fsm._connect_retry_timer)
        self.assertIsNone(self.fsm._hold_timer)
        self.assertIsNone(self.fsm._keepalive_timer)


if __name__ == '__main__':
    unittest.main()
