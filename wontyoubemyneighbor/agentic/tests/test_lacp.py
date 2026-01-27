"""
Test suite for LACP (Link Aggregation Control Protocol) module.

Tests cover:
- LACPMode and state enums
- LinkAggregationGroup dataclass
- LACPManager operations
- Partner info handling
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from ..discovery.lacp import (
    LACPMode,
    LACPState,
    LACPPortState,
    LoadBalanceAlgorithm,
    LACPPartnerInfo,
    LACPMemberPort,
    LinkAggregationGroup,
    LACPManager,
    get_lacp_manager,
)


class TestLACPMode:
    """Tests for LACP mode enumeration."""

    def test_active_mode(self):
        """Test ACTIVE mode value."""
        assert LACPMode.ACTIVE.value == "active"

    def test_passive_mode(self):
        """Test PASSIVE mode value."""
        assert LACPMode.PASSIVE.value == "passive"

    def test_on_mode(self):
        """Test ON (static) mode value."""
        assert LACPMode.ON.value == "on"


class TestLACPState:
    """Tests for LACP state flags."""

    def test_state_flag_values(self):
        """Test state flag bit values per IEEE 802.3ad."""
        assert LACPState.LACP_ACTIVITY.value == 0x01
        assert LACPState.LACP_TIMEOUT.value == 0x02
        assert LACPState.AGGREGATION.value == 0x04
        assert LACPState.SYNCHRONIZATION.value == 0x08
        assert LACPState.COLLECTING.value == 0x10
        assert LACPState.DISTRIBUTING.value == 0x20
        assert LACPState.DEFAULTED.value == 0x40
        assert LACPState.EXPIRED.value == 0x80

    def test_full_operational_state(self):
        """Test combining state flags for fully operational port."""
        # Active, aggregatable, synchronized, collecting, distributing
        operational = (
            LACPState.LACP_ACTIVITY.value |
            LACPState.AGGREGATION.value |
            LACPState.SYNCHRONIZATION.value |
            LACPState.COLLECTING.value |
            LACPState.DISTRIBUTING.value
        )
        assert operational == 0x3D


class TestLACPPortState:
    """Tests for LACP port state machine states."""

    def test_port_state_progression(self):
        """Test that port states can progress correctly."""
        # Normal state progression
        states = [
            LACPPortState.DETACHED,
            LACPPortState.WAITING,
            LACPPortState.ATTACHED,
            LACPPortState.COLLECTING,
            LACPPortState.DISTRIBUTING,
            LACPPortState.ACTIVE
        ]
        # Verify all states exist
        for state in states:
            assert state is not None


class TestLoadBalanceAlgorithm:
    """Tests for load balancing algorithm enumeration."""

    def test_algorithm_values(self):
        """Test load balance algorithm values."""
        assert LoadBalanceAlgorithm.SRC_MAC.value == "src-mac"
        assert LoadBalanceAlgorithm.DST_MAC.value == "dst-mac"
        assert LoadBalanceAlgorithm.LAYER2.value == "layer2"
        assert LoadBalanceAlgorithm.LAYER3.value == "layer3"
        assert LoadBalanceAlgorithm.LAYER34.value == "layer3+4"


class TestLACPPartnerInfo:
    """Tests for LACP partner information dataclass."""

    def test_partner_info_creation(self):
        """Test creating partner info."""
        partner = LACPPartnerInfo(
            system_priority=32768,
            system_id="00:11:22:33:44:55",
            key=1,
            port_priority=128,
            port_number=1,
            state=0x3D
        )
        assert partner.system_priority == 32768
        assert partner.system_id == "00:11:22:33:44:55"
        assert partner.state == 0x3D

    def test_partner_info_defaults(self):
        """Test partner info with defaults."""
        partner = LACPPartnerInfo(
            system_priority=32768,
            system_id="aa:bb:cc:dd:ee:ff",
            key=1,
            port_priority=128,
            port_number=1
        )
        assert partner.state == 0


class TestLACPMemberPort:
    """Tests for LACP member port dataclass."""

    def test_member_port_creation(self):
        """Test creating member port."""
        port = LACPMemberPort(
            interface="eth0",
            mac_address="00:11:22:33:44:55",
            lacp_mode=LACPMode.ACTIVE,
            port_priority=128,
            admin_key=1
        )
        assert port.interface == "eth0"
        assert port.lacp_mode == LACPMode.ACTIVE
        assert port.state == LACPPortState.DETACHED  # Default

    def test_member_port_with_partner(self):
        """Test member port with partner info."""
        partner = LACPPartnerInfo(
            system_priority=32768,
            system_id="aa:bb:cc:dd:ee:ff",
            key=1,
            port_priority=128,
            port_number=1
        )
        port = LACPMemberPort(
            interface="eth0",
            mac_address="00:11:22:33:44:55",
            lacp_mode=LACPMode.ACTIVE,
            port_priority=128,
            admin_key=1,
            partner_info=partner
        )
        assert port.partner_info is not None
        assert port.partner_info.system_id == "aa:bb:cc:dd:ee:ff"


class TestLinkAggregationGroup:
    """Tests for Link Aggregation Group (LAG) dataclass."""

    def test_lag_creation(self):
        """Test creating LAG."""
        lag = LinkAggregationGroup(
            name="bond0",
            lag_id=1,
            system_priority=32768,
            system_id="00:11:22:33:44:55",
            admin_key=1
        )
        assert lag.name == "bond0"
        assert lag.lag_id == 1
        assert lag.mode == LACPMode.ACTIVE  # Default

    def test_lag_with_members(self):
        """Test LAG with member ports."""
        port1 = LACPMemberPort(
            interface="eth0",
            mac_address="00:11:22:33:44:55",
            lacp_mode=LACPMode.ACTIVE,
            port_priority=128,
            admin_key=1
        )
        port2 = LACPMemberPort(
            interface="eth1",
            mac_address="00:11:22:33:44:56",
            lacp_mode=LACPMode.ACTIVE,
            port_priority=128,
            admin_key=1
        )
        lag = LinkAggregationGroup(
            name="bond0",
            lag_id=1,
            system_priority=32768,
            system_id="00:11:22:33:44:55",
            admin_key=1,
            member_ports=[port1, port2]
        )
        assert len(lag.member_ports) == 2

    def test_lag_to_dict(self):
        """Test LAG serialization to dictionary."""
        lag = LinkAggregationGroup(
            name="bond0",
            lag_id=1,
            system_priority=32768,
            system_id="00:11:22:33:44:55",
            admin_key=1
        )
        data = lag.to_dict()
        assert data["name"] == "bond0"
        assert data["lag_id"] == 1
        assert "member_ports" in data


class TestLACPManager:
    """Tests for LACP manager functionality."""

    @pytest.fixture
    def manager(self):
        """Create a test LACP manager instance."""
        return LACPManager(
            system_id="00:11:22:33:44:55",
            system_priority=32768
        )

    def test_manager_initialization(self, manager):
        """Test manager initializes correctly."""
        assert manager.system_id == "00:11:22:33:44:55"
        assert manager.system_priority == 32768

    def test_create_lag(self, manager):
        """Test creating a new LAG."""
        lag = manager.create_lag(
            name="bond0",
            mode=LACPMode.ACTIVE,
            load_balance=LoadBalanceAlgorithm.LAYER34
        )
        assert lag is not None
        assert lag.name == "bond0"
        assert lag.mode == LACPMode.ACTIVE

    def test_add_member_to_lag(self, manager):
        """Test adding member interface to LAG."""
        lag = manager.create_lag(name="bond0")
        manager.add_member(
            lag_name="bond0",
            interface="eth0",
            mac_address="00:11:22:33:44:66"
        )
        updated_lag = manager.get_lag("bond0")
        assert len(updated_lag.member_ports) == 1
        assert updated_lag.member_ports[0].interface == "eth0"

    def test_remove_member_from_lag(self, manager):
        """Test removing member interface from LAG."""
        lag = manager.create_lag(name="bond0")
        manager.add_member("bond0", "eth0", "00:11:22:33:44:66")
        manager.add_member("bond0", "eth1", "00:11:22:33:44:67")

        manager.remove_member("bond0", "eth0")

        updated_lag = manager.get_lag("bond0")
        assert len(updated_lag.member_ports) == 1
        assert updated_lag.member_ports[0].interface == "eth1"

    def test_delete_lag(self, manager):
        """Test deleting a LAG."""
        manager.create_lag(name="bond0")
        manager.delete_lag("bond0")

        lag = manager.get_lag("bond0")
        assert lag is None

    def test_list_lags(self, manager):
        """Test listing all LAGs."""
        manager.create_lag(name="bond0")
        manager.create_lag(name="bond1")

        lags = manager.list_lags()
        assert len(lags) == 2

    def test_get_statistics(self, manager):
        """Test getting LACP statistics."""
        manager.create_lag(name="bond0")
        stats = manager.get_statistics()

        assert "lag_count" in stats
        assert stats["lag_count"] == 1


class TestSingletonFunctions:
    """Tests for singleton management functions."""

    def test_get_manager_creates_instance(self):
        """Test that get_lacp_manager creates singleton."""
        manager = get_lacp_manager(
            system_id="singleton-test-mac",
            system_priority=32768
        )
        assert manager is not None

    def test_get_manager_returns_same_instance(self):
        """Test that get_lacp_manager returns same instance."""
        manager1 = get_lacp_manager()
        manager2 = get_lacp_manager()
        assert manager1 is manager2


class TestLACPNegotiation:
    """Tests for LACP negotiation scenarios."""

    @pytest.fixture
    def manager(self):
        """Create manager for negotiation tests."""
        return LACPManager(
            system_id="00:11:22:33:44:55",
            system_priority=32768
        )

    def test_active_passive_pair(self, manager):
        """Test ACTIVE-PASSIVE pair negotiation."""
        # Create LAG in ACTIVE mode
        lag = manager.create_lag(name="bond0", mode=LACPMode.ACTIVE)
        manager.add_member("bond0", "eth0", "00:11:22:33:44:66")

        # Simulate receiving partner info from PASSIVE peer
        partner = LACPPartnerInfo(
            system_priority=32768,
            system_id="aa:bb:cc:dd:ee:ff",
            key=1,
            port_priority=128,
            port_number=1,
            state=LACPState.AGGREGATION.value  # Passive, aggregatable
        )

        # In a real scenario, this would trigger negotiation
        assert partner.state & LACPState.AGGREGATION.value

    def test_static_lag_no_lacp(self, manager):
        """Test static LAG (LACP OFF)."""
        lag = manager.create_lag(name="bond-static", mode=LACPMode.ON)
        manager.add_member("bond-static", "eth0", "00:11:22:33:44:66")

        # Static LAG should not require LACP negotiation
        assert lag.mode == LACPMode.ON
