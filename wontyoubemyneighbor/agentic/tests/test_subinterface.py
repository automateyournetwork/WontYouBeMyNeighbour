"""
Test suite for Subinterface/VLAN management module.

Tests cover:
- Subinterface dataclass
- Physical interface handling
- 802.1Q encapsulation
- Interface states and statistics
- SubinterfaceManager operations
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from ..interfaces.subinterface import (
    InterfaceState,
    EncapsulationType,
    InterfaceStatistics,
    PhysicalInterface,
    Subinterface,
    SubinterfaceManager,
    get_subinterface_manager,
    start_subinterface_manager,
    stop_subinterface_manager,
    list_subinterfaces,
    get_subinterface_statistics,
)


class TestInterfaceState:
    """Tests for interface state enumeration."""

    def test_state_values(self):
        """Test interface state values."""
        assert InterfaceState.UP.value == "up"
        assert InterfaceState.DOWN.value == "down"
        assert InterfaceState.ADMIN_DOWN.value == "admin_down"
        assert InterfaceState.TESTING.value == "testing"


class TestEncapsulationType:
    """Tests for encapsulation type enumeration."""

    def test_encapsulation_values(self):
        """Test encapsulation type values."""
        assert EncapsulationType.DOT1Q.value == "802.1Q"
        assert EncapsulationType.QINQ.value == "QinQ"
        assert EncapsulationType.NONE.value == "none"


class TestInterfaceStatistics:
    """Tests for interface statistics dataclass."""

    def test_statistics_creation(self):
        """Test creating interface statistics."""
        stats = InterfaceStatistics(
            rx_packets=1000000,
            tx_packets=800000,
            rx_bytes=1500000000,
            tx_bytes=1200000000,
            rx_errors=5,
            tx_errors=2,
            rx_dropped=10,
            tx_dropped=3
        )
        assert stats.rx_packets == 1000000
        assert stats.tx_packets == 800000

    def test_statistics_defaults(self):
        """Test statistics with default values."""
        stats = InterfaceStatistics()
        assert stats.rx_packets == 0
        assert stats.tx_packets == 0
        assert stats.rx_errors == 0

    def test_statistics_to_dict(self):
        """Test statistics serialization."""
        stats = InterfaceStatistics(rx_packets=100, tx_packets=200)
        data = stats.to_dict()
        assert data["rx_packets"] == 100
        assert data["tx_packets"] == 200


class TestPhysicalInterface:
    """Tests for physical interface dataclass."""

    def test_basic_interface(self):
        """Test creating basic physical interface."""
        iface = PhysicalInterface(
            name="eth0",
            mac_address="00:11:22:33:44:55",
            mtu=1500
        )
        assert iface.name == "eth0"
        assert iface.mac_address == "00:11:22:33:44:55"
        assert iface.state == InterfaceState.DOWN  # Default

    def test_interface_with_state(self):
        """Test interface with explicit state."""
        iface = PhysicalInterface(
            name="eth0",
            mac_address="00:11:22:33:44:55",
            mtu=1500,
            state=InterfaceState.UP,
            speed=1000,  # 1 Gbps
            duplex="full"
        )
        assert iface.state == InterfaceState.UP
        assert iface.speed == 1000
        assert iface.duplex == "full"

    def test_interface_with_subinterfaces(self):
        """Test physical interface with subinterface list."""
        iface = PhysicalInterface(
            name="eth0",
            mac_address="00:11:22:33:44:55",
            mtu=1500,
            subinterface_ids=[100, 200, 300]
        )
        assert len(iface.subinterface_ids) == 3

    def test_interface_to_dict(self):
        """Test interface serialization."""
        iface = PhysicalInterface(
            name="eth0",
            mac_address="00:11:22:33:44:55",
            mtu=1500
        )
        data = iface.to_dict()
        assert data["name"] == "eth0"
        assert data["mac_address"] == "00:11:22:33:44:55"


class TestSubinterface:
    """Tests for subinterface/VLAN dataclass."""

    def test_basic_subinterface(self):
        """Test creating basic subinterface."""
        subif = Subinterface(
            name="eth0.100",
            parent_interface="eth0",
            vlan_id=100,
            encapsulation=EncapsulationType.DOT1Q
        )
        assert subif.name == "eth0.100"
        assert subif.vlan_id == 100
        assert subif.encapsulation == EncapsulationType.DOT1Q

    def test_subinterface_with_ip(self):
        """Test subinterface with IP address."""
        subif = Subinterface(
            name="eth0.100",
            parent_interface="eth0",
            vlan_id=100,
            encapsulation=EncapsulationType.DOT1Q,
            ipv4_address="192.168.100.1",
            ipv4_prefix_length=24
        )
        assert subif.ipv4_address == "192.168.100.1"
        assert subif.ipv4_prefix_length == 24

    def test_subinterface_with_ipv6(self):
        """Test subinterface with IPv6 address."""
        subif = Subinterface(
            name="eth0.100",
            parent_interface="eth0",
            vlan_id=100,
            encapsulation=EncapsulationType.DOT1Q,
            ipv6_address="2001:db8:100::1",
            ipv6_prefix_length=64
        )
        assert subif.ipv6_address == "2001:db8:100::1"
        assert subif.ipv6_prefix_length == 64

    def test_subinterface_dual_stack(self):
        """Test subinterface with both IPv4 and IPv6."""
        subif = Subinterface(
            name="eth0.100",
            parent_interface="eth0",
            vlan_id=100,
            encapsulation=EncapsulationType.DOT1Q,
            ipv4_address="192.168.100.1",
            ipv4_prefix_length=24,
            ipv6_address="2001:db8:100::1",
            ipv6_prefix_length=64
        )
        assert subif.ipv4_address is not None
        assert subif.ipv6_address is not None

    def test_qinq_subinterface(self):
        """Test QinQ (double-tagged) subinterface."""
        subif = Subinterface(
            name="eth0.100.200",
            parent_interface="eth0",
            vlan_id=200,
            outer_vlan_id=100,
            encapsulation=EncapsulationType.QINQ
        )
        assert subif.encapsulation == EncapsulationType.QINQ
        assert subif.outer_vlan_id == 100
        assert subif.vlan_id == 200

    def test_subinterface_description(self):
        """Test subinterface with description."""
        subif = Subinterface(
            name="eth0.100",
            parent_interface="eth0",
            vlan_id=100,
            encapsulation=EncapsulationType.DOT1Q,
            description="Customer VLAN 100 - Production"
        )
        assert "Production" in subif.description

    def test_subinterface_to_dict(self):
        """Test subinterface serialization."""
        subif = Subinterface(
            name="eth0.100",
            parent_interface="eth0",
            vlan_id=100,
            encapsulation=EncapsulationType.DOT1Q,
            ipv4_address="192.168.100.1",
            ipv4_prefix_length=24
        )
        data = subif.to_dict()
        assert data["name"] == "eth0.100"
        assert data["vlan_id"] == 100
        assert data["ipv4_address"] == "192.168.100.1"


class TestSubinterfaceManager:
    """Tests for subinterface manager functionality."""

    @pytest.fixture
    def manager(self):
        """Create a test subinterface manager instance."""
        mgr = SubinterfaceManager()
        # Add a physical interface to work with
        mgr.add_physical_interface(
            name="eth0",
            mac_address="00:11:22:33:44:55",
            mtu=1500
        )
        return mgr

    def test_manager_initialization(self, manager):
        """Test manager initializes correctly."""
        assert manager is not None

    def test_add_physical_interface(self, manager):
        """Test adding physical interface."""
        manager.add_physical_interface(
            name="eth1",
            mac_address="00:11:22:33:44:56",
            mtu=9000
        )
        iface = manager.get_physical_interface("eth1")
        assert iface is not None
        assert iface.mtu == 9000

    def test_create_subinterface(self, manager):
        """Test creating subinterface."""
        subif = manager.create_subinterface(
            parent="eth0",
            vlan_id=100,
            ipv4_address="192.168.100.1",
            ipv4_prefix_length=24
        )
        assert subif is not None
        assert subif.vlan_id == 100

    def test_create_subinterface_auto_name(self, manager):
        """Test subinterface auto-naming."""
        subif = manager.create_subinterface(
            parent="eth0",
            vlan_id=200
        )
        assert subif.name == "eth0.200"

    def test_create_multiple_subinterfaces(self, manager):
        """Test creating multiple subinterfaces on same parent."""
        subif1 = manager.create_subinterface(parent="eth0", vlan_id=100)
        subif2 = manager.create_subinterface(parent="eth0", vlan_id=200)
        subif3 = manager.create_subinterface(parent="eth0", vlan_id=300)

        subifs = manager.list_subinterfaces(parent="eth0")
        assert len(subifs) == 3

    def test_delete_subinterface(self, manager):
        """Test deleting subinterface."""
        manager.create_subinterface(parent="eth0", vlan_id=100)
        manager.delete_subinterface("eth0.100")

        subif = manager.get_subinterface("eth0.100")
        assert subif is None

    def test_modify_subinterface_ip(self, manager):
        """Test modifying subinterface IP address."""
        manager.create_subinterface(
            parent="eth0",
            vlan_id=100,
            ipv4_address="192.168.100.1",
            ipv4_prefix_length=24
        )
        manager.update_subinterface(
            name="eth0.100",
            ipv4_address="192.168.100.254",
            ipv4_prefix_length=24
        )
        subif = manager.get_subinterface("eth0.100")
        assert subif.ipv4_address == "192.168.100.254"

    def test_enable_disable_subinterface(self, manager):
        """Test enabling and disabling subinterface."""
        manager.create_subinterface(parent="eth0", vlan_id=100)

        # Disable
        manager.set_subinterface_state("eth0.100", InterfaceState.ADMIN_DOWN)
        subif = manager.get_subinterface("eth0.100")
        assert subif.state == InterfaceState.ADMIN_DOWN

        # Enable
        manager.set_subinterface_state("eth0.100", InterfaceState.UP)
        subif = manager.get_subinterface("eth0.100")
        assert subif.state == InterfaceState.UP

    def test_list_all_subinterfaces(self, manager):
        """Test listing all subinterfaces."""
        manager.create_subinterface(parent="eth0", vlan_id=100)
        manager.create_subinterface(parent="eth0", vlan_id=200)

        all_subifs = manager.list_subinterfaces()
        assert len(all_subifs) == 2

    def test_get_statistics(self, manager):
        """Test getting manager statistics."""
        manager.create_subinterface(parent="eth0", vlan_id=100)
        manager.create_subinterface(parent="eth0", vlan_id=200)

        stats = manager.get_statistics()
        assert "physical_interfaces" in stats
        assert "subinterfaces" in stats
        assert stats["subinterfaces"] == 2


class TestSingletonFunctions:
    """Tests for singleton management functions."""

    def test_get_manager_creates_instance(self):
        """Test that get_subinterface_manager creates singleton."""
        manager = get_subinterface_manager()
        assert manager is not None

    def test_get_manager_returns_same_instance(self):
        """Test that get_subinterface_manager returns same instance."""
        manager1 = get_subinterface_manager()
        manager2 = get_subinterface_manager()
        assert manager1 is manager2

    def test_list_helper(self):
        """Test list_subinterfaces helper function."""
        subifs = list_subinterfaces()
        assert isinstance(subifs, list)

    def test_statistics_helper(self):
        """Test get_subinterface_statistics helper function."""
        stats = get_subinterface_statistics()
        assert isinstance(stats, dict)


class TestVLANScenarios:
    """Tests for common VLAN scenarios."""

    @pytest.fixture
    def manager(self):
        """Create manager for scenario tests."""
        mgr = SubinterfaceManager()
        mgr.add_physical_interface("eth0", "00:11:22:33:44:55", 1500)
        mgr.add_physical_interface("eth1", "00:11:22:33:44:56", 1500)
        return mgr

    def test_router_on_a_stick(self, manager):
        """Test router-on-a-stick configuration."""
        # Multiple VLANs on single physical interface
        manager.create_subinterface(
            parent="eth0",
            vlan_id=10,
            ipv4_address="192.168.10.1",
            ipv4_prefix_length=24,
            description="VLAN 10 - Users"
        )
        manager.create_subinterface(
            parent="eth0",
            vlan_id=20,
            ipv4_address="192.168.20.1",
            ipv4_prefix_length=24,
            description="VLAN 20 - Servers"
        )
        manager.create_subinterface(
            parent="eth0",
            vlan_id=30,
            ipv4_address="192.168.30.1",
            ipv4_prefix_length=24,
            description="VLAN 30 - Management"
        )

        subifs = manager.list_subinterfaces(parent="eth0")
        assert len(subifs) == 3

    def test_trunk_link(self, manager):
        """Test trunk link with matching VLANs on both ends."""
        # Same VLANs on two physical interfaces (simulating trunk)
        for vlan in [100, 200, 300]:
            manager.create_subinterface(parent="eth0", vlan_id=vlan)
            manager.create_subinterface(parent="eth1", vlan_id=vlan)

        eth0_subifs = manager.list_subinterfaces(parent="eth0")
        eth1_subifs = manager.list_subinterfaces(parent="eth1")

        assert len(eth0_subifs) == 3
        assert len(eth1_subifs) == 3

    def test_native_vlan(self, manager):
        """Test native VLAN (untagged traffic)."""
        # Native VLAN uses parent interface directly
        # Tagged VLANs use subinterfaces
        manager.create_subinterface(
            parent="eth0",
            vlan_id=10,
            description="Tagged VLAN 10"
        )
        # VLAN 1 would typically be native (untagged)
        # This is represented by the parent interface eth0 itself
        parent = manager.get_physical_interface("eth0")
        assert parent is not None
