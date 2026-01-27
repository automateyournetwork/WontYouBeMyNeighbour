"""
Test suite for Firewall/ACL module.

Tests cover:
- ACL rules and entries
- Firewall chains
- Protocol and direction enums
- FirewallManager operations
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from ipaddress import IPv4Network, IPv6Network

from ..security.firewall import (
    Protocol,
    Direction,
    FirewallAction,
    FirewallChain,
    ACLEntry,
    ACLRule,
    RuleStatistics,
    FirewallManager,
    get_firewall_manager,
    start_firewall_manager,
    stop_firewall_manager,
    list_acl_rules,
    get_firewall_statistics,
)


class TestProtocol:
    """Tests for Protocol enumeration."""

    def test_common_protocols(self):
        """Test common protocol values."""
        assert Protocol.TCP.value == "tcp"
        assert Protocol.UDP.value == "udp"
        assert Protocol.ICMP.value == "icmp"
        assert Protocol.ANY.value == "any"

    def test_all_protocols_defined(self):
        """Test that all expected protocols are defined."""
        protocols = [p.value for p in Protocol]
        assert "tcp" in protocols
        assert "udp" in protocols
        assert "icmp" in protocols
        assert "gre" in protocols
        assert "esp" in protocols


class TestDirection:
    """Tests for Direction enumeration."""

    def test_direction_values(self):
        """Test direction values."""
        assert Direction.INBOUND.value == "in"
        assert Direction.OUTBOUND.value == "out"
        assert Direction.BOTH.value == "both"


class TestFirewallAction:
    """Tests for FirewallAction enumeration."""

    def test_action_values(self):
        """Test firewall action values."""
        assert FirewallAction.ACCEPT.value == "accept"
        assert FirewallAction.DROP.value == "drop"
        assert FirewallAction.REJECT.value == "reject"
        assert FirewallAction.LOG.value == "log"


class TestFirewallChain:
    """Tests for FirewallChain enumeration."""

    def test_chain_values(self):
        """Test firewall chain values (iptables-style)."""
        assert FirewallChain.INPUT.value == "INPUT"
        assert FirewallChain.OUTPUT.value == "OUTPUT"
        assert FirewallChain.FORWARD.value == "FORWARD"


class TestACLEntry:
    """Tests for ACL entry dataclass."""

    def test_basic_entry(self):
        """Test creating basic ACL entry."""
        entry = ACLEntry(
            sequence=10,
            action=FirewallAction.ACCEPT,
            protocol=Protocol.TCP,
            source="192.168.1.0/24",
            destination="10.0.0.0/8"
        )
        assert entry.sequence == 10
        assert entry.action == FirewallAction.ACCEPT
        assert entry.protocol == Protocol.TCP

    def test_entry_with_ports(self):
        """Test ACL entry with port specifications."""
        entry = ACLEntry(
            sequence=20,
            action=FirewallAction.ACCEPT,
            protocol=Protocol.TCP,
            source="any",
            destination="192.168.1.100",
            destination_port=443
        )
        assert entry.destination_port == 443

    def test_entry_with_port_range(self):
        """Test ACL entry with port range."""
        entry = ACLEntry(
            sequence=30,
            action=FirewallAction.DROP,
            protocol=Protocol.UDP,
            source="any",
            destination="any",
            destination_port_range=(1024, 65535)
        )
        assert entry.destination_port_range == (1024, 65535)

    def test_entry_with_icmp_type(self):
        """Test ACL entry for ICMP with type specification."""
        entry = ACLEntry(
            sequence=40,
            action=FirewallAction.ACCEPT,
            protocol=Protocol.ICMP,
            source="any",
            destination="any",
            icmp_type=8,  # Echo request
            icmp_code=0
        )
        assert entry.icmp_type == 8
        assert entry.icmp_code == 0

    def test_entry_to_dict(self):
        """Test ACL entry serialization."""
        entry = ACLEntry(
            sequence=10,
            action=FirewallAction.ACCEPT,
            protocol=Protocol.TCP,
            source="192.168.1.0/24",
            destination="10.0.0.0/8"
        )
        data = entry.to_dict()
        assert data["sequence"] == 10
        assert data["action"] == "accept"
        assert data["protocol"] == "tcp"


class TestACLRule:
    """Tests for ACL rule (named ACL) dataclass."""

    def test_basic_rule(self):
        """Test creating basic ACL rule."""
        rule = ACLRule(
            name="web-servers",
            description="Allow web traffic",
            interface="eth0",
            direction=Direction.INBOUND
        )
        assert rule.name == "web-servers"
        assert rule.direction == Direction.INBOUND
        assert rule.entries == []

    def test_rule_with_entries(self):
        """Test ACL rule with entries."""
        entry1 = ACLEntry(
            sequence=10,
            action=FirewallAction.ACCEPT,
            protocol=Protocol.TCP,
            source="any",
            destination="any",
            destination_port=80
        )
        entry2 = ACLEntry(
            sequence=20,
            action=FirewallAction.ACCEPT,
            protocol=Protocol.TCP,
            source="any",
            destination="any",
            destination_port=443
        )
        rule = ACLRule(
            name="web-servers",
            description="Allow web traffic",
            interface="eth0",
            direction=Direction.INBOUND,
            entries=[entry1, entry2]
        )
        assert len(rule.entries) == 2

    def test_rule_enabled_default(self):
        """Test that rules are enabled by default."""
        rule = ACLRule(
            name="test-rule",
            interface="eth0",
            direction=Direction.INBOUND
        )
        assert rule.enabled is True

    def test_rule_to_dict(self):
        """Test ACL rule serialization."""
        rule = ACLRule(
            name="test-rule",
            description="Test description",
            interface="eth0",
            direction=Direction.INBOUND
        )
        data = rule.to_dict()
        assert data["name"] == "test-rule"
        assert data["description"] == "Test description"
        assert "entries" in data


class TestRuleStatistics:
    """Tests for rule statistics dataclass."""

    def test_statistics_creation(self):
        """Test creating rule statistics."""
        stats = RuleStatistics(
            rule_name="web-servers",
            packets_matched=1000,
            bytes_matched=1500000,
            last_match=datetime.now()
        )
        assert stats.packets_matched == 1000
        assert stats.bytes_matched == 1500000

    def test_statistics_per_entry(self):
        """Test statistics with per-entry breakdown."""
        stats = RuleStatistics(
            rule_name="web-servers",
            packets_matched=1000,
            bytes_matched=1500000,
            entry_stats={
                10: {"packets": 800, "bytes": 1200000},
                20: {"packets": 200, "bytes": 300000}
            }
        )
        assert stats.entry_stats[10]["packets"] == 800


class TestFirewallManager:
    """Tests for firewall manager functionality."""

    @pytest.fixture
    def manager(self):
        """Create a test firewall manager instance."""
        return FirewallManager()

    def test_manager_initialization(self, manager):
        """Test manager initializes correctly."""
        assert manager is not None
        assert manager._rules == {}

    def test_create_rule(self, manager):
        """Test creating an ACL rule."""
        rule = manager.create_rule(
            name="allow-ssh",
            description="Allow SSH access",
            interface="eth0",
            direction=Direction.INBOUND
        )
        assert rule is not None
        assert rule.name == "allow-ssh"

    def test_add_entry_to_rule(self, manager):
        """Test adding entry to ACL rule."""
        manager.create_rule(
            name="allow-ssh",
            interface="eth0",
            direction=Direction.INBOUND
        )
        manager.add_entry(
            rule_name="allow-ssh",
            sequence=10,
            action=FirewallAction.ACCEPT,
            protocol=Protocol.TCP,
            source="192.168.1.0/24",
            destination="any",
            destination_port=22
        )
        rule = manager.get_rule("allow-ssh")
        assert len(rule.entries) == 1
        assert rule.entries[0].destination_port == 22

    def test_delete_entry_from_rule(self, manager):
        """Test deleting entry from ACL rule."""
        manager.create_rule("test-rule", interface="eth0", direction=Direction.INBOUND)
        manager.add_entry("test-rule", 10, FirewallAction.ACCEPT, Protocol.TCP, "any", "any")
        manager.add_entry("test-rule", 20, FirewallAction.DROP, Protocol.ANY, "any", "any")

        manager.delete_entry("test-rule", 10)

        rule = manager.get_rule("test-rule")
        assert len(rule.entries) == 1
        assert rule.entries[0].sequence == 20

    def test_delete_rule(self, manager):
        """Test deleting ACL rule."""
        manager.create_rule("temp-rule", interface="eth0", direction=Direction.INBOUND)
        manager.delete_rule("temp-rule")

        rule = manager.get_rule("temp-rule")
        assert rule is None

    def test_list_rules(self, manager):
        """Test listing all ACL rules."""
        manager.create_rule("rule1", interface="eth0", direction=Direction.INBOUND)
        manager.create_rule("rule2", interface="eth1", direction=Direction.OUTBOUND)

        rules = manager.list_rules()
        assert len(rules) == 2

    def test_enable_disable_rule(self, manager):
        """Test enabling and disabling ACL rule."""
        manager.create_rule("toggle-rule", interface="eth0", direction=Direction.INBOUND)

        # Disable
        manager.disable_rule("toggle-rule")
        rule = manager.get_rule("toggle-rule")
        assert rule.enabled is False

        # Enable
        manager.enable_rule("toggle-rule")
        rule = manager.get_rule("toggle-rule")
        assert rule.enabled is True

    def test_get_statistics(self, manager):
        """Test getting firewall statistics."""
        manager.create_rule("stats-rule", interface="eth0", direction=Direction.INBOUND)
        stats = manager.get_statistics()

        assert "total_rules" in stats
        assert stats["total_rules"] == 1

    def test_resequence_entries(self, manager):
        """Test resequencing ACL entries."""
        manager.create_rule("reseq-rule", interface="eth0", direction=Direction.INBOUND)
        manager.add_entry("reseq-rule", 5, FirewallAction.ACCEPT, Protocol.TCP, "any", "any", destination_port=80)
        manager.add_entry("reseq-rule", 7, FirewallAction.ACCEPT, Protocol.TCP, "any", "any", destination_port=443)
        manager.add_entry("reseq-rule", 100, FirewallAction.DROP, Protocol.ANY, "any", "any")

        manager.resequence_entries("reseq-rule", start=10, increment=10)

        rule = manager.get_rule("reseq-rule")
        sequences = [e.sequence for e in rule.entries]
        assert sequences == [10, 20, 30]


class TestSingletonFunctions:
    """Tests for singleton management functions."""

    def test_get_manager_creates_instance(self):
        """Test that get_firewall_manager creates singleton."""
        manager = get_firewall_manager()
        assert manager is not None

    def test_get_manager_returns_same_instance(self):
        """Test that get_firewall_manager returns same instance."""
        manager1 = get_firewall_manager()
        manager2 = get_firewall_manager()
        assert manager1 is manager2

    def test_list_rules_helper(self):
        """Test list_acl_rules helper function."""
        rules = list_acl_rules()
        assert isinstance(rules, list)

    def test_get_statistics_helper(self):
        """Test get_firewall_statistics helper function."""
        stats = get_firewall_statistics()
        assert isinstance(stats, dict)


class TestFirewallScenarios:
    """Tests for common firewall scenarios."""

    @pytest.fixture
    def manager(self):
        """Create manager for scenario tests."""
        return FirewallManager()

    def test_web_server_acl(self, manager):
        """Test typical web server ACL configuration."""
        manager.create_rule(
            name="web-server-acl",
            description="Allow HTTP/HTTPS, deny all else",
            interface="eth0",
            direction=Direction.INBOUND
        )
        # Allow HTTP
        manager.add_entry("web-server-acl", 10, FirewallAction.ACCEPT,
                         Protocol.TCP, "any", "any", destination_port=80)
        # Allow HTTPS
        manager.add_entry("web-server-acl", 20, FirewallAction.ACCEPT,
                         Protocol.TCP, "any", "any", destination_port=443)
        # Deny all else
        manager.add_entry("web-server-acl", 1000, FirewallAction.DROP,
                         Protocol.ANY, "any", "any")

        rule = manager.get_rule("web-server-acl")
        assert len(rule.entries) == 3

    def test_management_acl(self, manager):
        """Test management access ACL configuration."""
        manager.create_rule(
            name="mgmt-acl",
            description="Restrict management access",
            interface="mgmt0",
            direction=Direction.INBOUND
        )
        # Allow SSH from management subnet
        manager.add_entry("mgmt-acl", 10, FirewallAction.ACCEPT,
                         Protocol.TCP, "10.0.100.0/24", "any", destination_port=22)
        # Allow HTTPS management
        manager.add_entry("mgmt-acl", 20, FirewallAction.ACCEPT,
                         Protocol.TCP, "10.0.100.0/24", "any", destination_port=443)
        # Allow ICMP for monitoring
        manager.add_entry("mgmt-acl", 30, FirewallAction.ACCEPT,
                         Protocol.ICMP, "10.0.100.0/24", "any")
        # Deny all else
        manager.add_entry("mgmt-acl", 1000, FirewallAction.DROP,
                         Protocol.ANY, "any", "any")

        rule = manager.get_rule("mgmt-acl")
        assert len(rule.entries) == 4
