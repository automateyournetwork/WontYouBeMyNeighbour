"""
Test suite for LLDP (Link Layer Discovery Protocol) module.

Tests cover:
- LLDPNeighbor dataclass
- LLDPDaemon operations
- Neighbor discovery and caching
- Statistics tracking
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock

from ..discovery.lldp import (
    LLDPCapability,
    LLDPChassisIDSubtype,
    LLDPPortIDSubtype,
    LLDPManagementAddress,
    LLDPNeighbor,
    LLDPDaemon,
    get_lldp_daemon,
    start_lldp_daemon,
    stop_lldp_daemon,
)


class TestLLDPCapability:
    """Tests for LLDP capability flags."""

    def test_capability_values(self):
        """Test that capability bit values are correct per IEEE 802.1AB."""
        assert LLDPCapability.OTHER.value == 0x01
        assert LLDPCapability.REPEATER.value == 0x02
        assert LLDPCapability.BRIDGE.value == 0x04
        assert LLDPCapability.ROUTER.value == 0x10
        assert LLDPCapability.STATION.value == 0x80

    def test_capability_combination(self):
        """Test combining multiple capabilities."""
        # A switch with routing capability
        caps = LLDPCapability.BRIDGE.value | LLDPCapability.ROUTER.value
        assert caps == 0x14


class TestLLDPChassisIDSubtype:
    """Tests for Chassis ID subtypes."""

    def test_subtype_values(self):
        """Test subtype enumeration values."""
        assert LLDPChassisIDSubtype.MAC_ADDRESS.value == 4
        assert LLDPChassisIDSubtype.NETWORK_ADDRESS.value == 5
        assert LLDPChassisIDSubtype.LOCAL.value == 7


class TestLLDPPortIDSubtype:
    """Tests for Port ID subtypes."""

    def test_subtype_values(self):
        """Test port ID subtype values."""
        assert LLDPPortIDSubtype.INTERFACE_NAME.value == 5
        assert LLDPPortIDSubtype.MAC_ADDRESS.value == 3


class TestLLDPManagementAddress:
    """Tests for LLDP management address dataclass."""

    def test_ipv4_address(self):
        """Test IPv4 management address."""
        addr = LLDPManagementAddress(
            address_type="ipv4",
            address="192.168.1.1",
            interface_type="ifIndex",
            interface_number=1
        )
        assert addr.address_type == "ipv4"
        assert addr.address == "192.168.1.1"

    def test_ipv6_address(self):
        """Test IPv6 management address."""
        addr = LLDPManagementAddress(
            address_type="ipv6",
            address="2001:db8::1",
            interface_type="ifIndex",
            interface_number=2
        )
        assert addr.address_type == "ipv6"
        assert addr.address == "2001:db8::1"


class TestLLDPNeighbor:
    """Tests for LLDP neighbor dataclass."""

    def test_basic_neighbor(self):
        """Test creating basic LLDP neighbor."""
        neighbor = LLDPNeighbor(
            chassis_id="00:11:22:33:44:55",
            chassis_id_subtype=LLDPChassisIDSubtype.MAC_ADDRESS,
            port_id="Ethernet0/1",
            port_id_subtype=LLDPPortIDSubtype.INTERFACE_NAME,
            ttl=120
        )
        assert neighbor.chassis_id == "00:11:22:33:44:55"
        assert neighbor.ttl == 120
        assert neighbor.system_name == ""  # Default

    def test_full_neighbor(self):
        """Test neighbor with all optional fields."""
        mgmt_addr = LLDPManagementAddress(
            address_type="ipv4",
            address="10.0.0.1"
        )
        neighbor = LLDPNeighbor(
            chassis_id="00:11:22:33:44:55",
            chassis_id_subtype=LLDPChassisIDSubtype.MAC_ADDRESS,
            port_id="Gi0/1",
            port_id_subtype=LLDPPortIDSubtype.INTERFACE_NAME,
            ttl=120,
            system_name="switch-01",
            system_description="Cisco IOS Software",
            port_description="Uplink to core",
            capabilities=LLDPCapability.BRIDGE.value | LLDPCapability.ROUTER.value,
            enabled_capabilities=LLDPCapability.BRIDGE.value,
            management_addresses=[mgmt_addr]
        )
        assert neighbor.system_name == "switch-01"
        assert neighbor.capabilities == 0x14
        assert len(neighbor.management_addresses) == 1

    def test_neighbor_to_dict(self):
        """Test neighbor serialization to dictionary."""
        neighbor = LLDPNeighbor(
            chassis_id="00:11:22:33:44:55",
            chassis_id_subtype=LLDPChassisIDSubtype.MAC_ADDRESS,
            port_id="Ethernet1",
            port_id_subtype=LLDPPortIDSubtype.INTERFACE_NAME,
            ttl=120,
            system_name="test-device"
        )
        data = neighbor.to_dict()
        assert data["chassis_id"] == "00:11:22:33:44:55"
        assert data["system_name"] == "test-device"
        assert "local_interface" in data


class TestLLDPDaemon:
    """Tests for LLDP daemon functionality."""

    @pytest.fixture
    def daemon(self):
        """Create a test LLDP daemon instance."""
        return LLDPDaemon(
            agent_id="test-agent",
            agent_name="Test Agent",
            system_description="Test System"
        )

    def test_daemon_initialization(self, daemon):
        """Test daemon initializes correctly."""
        assert daemon.agent_id == "test-agent"
        assert daemon.agent_name == "Test Agent"
        assert not daemon._running

    def test_add_interface(self, daemon):
        """Test adding interfaces to daemon."""
        daemon.add_interface("eth0", "00:11:22:33:44:55")
        assert "eth0" in daemon._interfaces
        assert daemon._interfaces["eth0"]["mac"] == "00:11:22:33:44:55"

    def test_remove_interface(self, daemon):
        """Test removing interfaces from daemon."""
        daemon.add_interface("eth0", "00:11:22:33:44:55")
        daemon.remove_interface("eth0")
        assert "eth0" not in daemon._interfaces

    def test_get_neighbors_empty(self, daemon):
        """Test getting neighbors when none discovered."""
        neighbors = daemon.get_neighbors()
        assert neighbors == []

    def test_get_neighbors_for_interface(self, daemon):
        """Test getting neighbors for specific interface."""
        neighbors = daemon.get_neighbors(interface="eth0")
        assert neighbors == []

    def test_statistics_initial(self, daemon):
        """Test initial statistics are zero."""
        stats = daemon.get_statistics()
        assert stats["frames_sent"] == 0
        assert stats["frames_received"] == 0
        assert stats["neighbors_count"] == 0

    @pytest.mark.asyncio
    async def test_daemon_start_stop(self, daemon):
        """Test daemon start and stop lifecycle."""
        # Start daemon
        asyncio.create_task(daemon.start())
        await asyncio.sleep(0.1)
        assert daemon._running

        # Stop daemon
        daemon.stop()
        await asyncio.sleep(0.1)
        assert not daemon._running


class TestSingletonFunctions:
    """Tests for singleton management functions."""

    def test_get_daemon_creates_instance(self):
        """Test that get_lldp_daemon creates singleton."""
        daemon = get_lldp_daemon(
            agent_id="singleton-test",
            agent_name="Singleton Test"
        )
        assert daemon is not None
        assert daemon.agent_id == "singleton-test"

    def test_get_daemon_returns_same_instance(self):
        """Test that get_lldp_daemon returns same instance."""
        daemon1 = get_lldp_daemon()
        daemon2 = get_lldp_daemon()
        assert daemon1 is daemon2

    @pytest.mark.asyncio
    async def test_start_stop_daemon(self):
        """Test start and stop helper functions."""
        daemon = start_lldp_daemon(
            agent_id="start-stop-test",
            agent_name="Start Stop Test"
        )
        assert daemon is not None

        stop_lldp_daemon()
        # Daemon should be stopped


class TestNeighborExpiration:
    """Tests for neighbor TTL and expiration."""

    @pytest.fixture
    def daemon_with_neighbor(self):
        """Create daemon with a pre-added neighbor."""
        daemon = LLDPDaemon(
            agent_id="expiry-test",
            agent_name="Expiry Test"
        )
        daemon.add_interface("eth0", "00:11:22:33:44:55")
        return daemon

    def test_neighbor_added_with_timestamp(self, daemon_with_neighbor):
        """Test that neighbors are timestamped when added."""
        neighbor = LLDPNeighbor(
            chassis_id="aa:bb:cc:dd:ee:ff",
            chassis_id_subtype=LLDPChassisIDSubtype.MAC_ADDRESS,
            port_id="Gi0/1",
            port_id_subtype=LLDPPortIDSubtype.INTERFACE_NAME,
            ttl=120
        )
        daemon_with_neighbor._add_neighbor("eth0", neighbor)

        neighbors = daemon_with_neighbor.get_neighbors()
        assert len(neighbors) == 1
        # Neighbor should have last_seen timestamp
        assert neighbors[0].last_seen is not None
