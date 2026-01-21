"""Tests for alert management module"""

import pytest
from agentic.alerts import (
    Alert, AlertSeverity, AlertStatus, AlertCategory, AlertConfig, AlertManager, get_alert_manager,
    NotificationChannel, ChannelType, ChannelStatus, ChannelConfig, ChannelManager, get_channel_manager,
    EscalationPolicy, EscalationLevel, EscalationTrigger, EscalationAction, EscalationManager, get_escalation_manager
)


class TestAlertManager:
    """Tests for AlertManager"""

    def test_create_alert(self):
        """Test alert creation"""
        manager = AlertManager()
        alert = manager.create_alert(
            name="Test Alert",
            description="Test description",
            severity=AlertSeverity.HIGH,
            category=AlertCategory.NETWORK,
            message="Test message"
        )
        assert alert.name == "Test Alert"
        assert alert.severity == AlertSeverity.HIGH
        assert alert.status == AlertStatus.ACTIVE

    def test_acknowledge_alert(self):
        """Test alert acknowledgment"""
        manager = AlertManager()
        alert = manager.create_alert(
            name="Test Alert",
            description="Test",
            severity=AlertSeverity.MEDIUM
        )

        assert manager.acknowledge_alert(alert.id, "test_user", "Acknowledged")
        assert alert.status == AlertStatus.ACKNOWLEDGED
        assert alert.acknowledged_by == "test_user"

    def test_resolve_alert(self):
        """Test alert resolution"""
        manager = AlertManager()
        alert = manager.create_alert(
            name="Test Alert",
            description="Test",
            severity=AlertSeverity.LOW
        )

        assert manager.resolve_alert(alert.id, "test_user", "Fixed")
        assert alert.status == AlertStatus.RESOLVED
        assert alert.resolved_by == "test_user"

    def test_suppress_alert(self):
        """Test alert suppression"""
        manager = AlertManager()
        alert = manager.create_alert(
            name="Test Alert",
            description="Test",
            severity=AlertSeverity.INFO
        )

        assert manager.suppress_alert(alert.id, minutes=30)
        assert alert.status == AlertStatus.SUPPRESSED
        assert alert.suppress_until is not None

    def test_escalate_alert(self):
        """Test alert escalation"""
        manager = AlertManager()
        alert = manager.create_alert(
            name="Test Alert",
            description="Test",
            severity=AlertSeverity.CRITICAL
        )

        assert manager.escalate_alert(alert.id, level=2)
        assert alert.escalation_level == 2
        assert alert.status == AlertStatus.ESCALATED

    def test_get_alerts_by_severity(self):
        """Test filtering alerts by severity"""
        manager = AlertManager()
        manager.create_alert("High 1", "Desc", AlertSeverity.HIGH)
        manager.create_alert("High 2", "Desc", AlertSeverity.HIGH)
        manager.create_alert("Low 1", "Desc", AlertSeverity.LOW)

        high_alerts = manager.get_alerts(severity=AlertSeverity.HIGH)
        assert len(high_alerts) == 2

    def test_bulk_acknowledge(self):
        """Test bulk acknowledgment"""
        manager = AlertManager()
        alert1 = manager.create_alert("Alert 1", "Desc", AlertSeverity.MEDIUM)
        alert2 = manager.create_alert("Alert 2", "Desc", AlertSeverity.MEDIUM)

        count = manager.bulk_acknowledge([alert1.id, alert2.id], "user")
        assert count == 2


class TestChannelManager:
    """Tests for ChannelManager"""

    def test_create_channel(self):
        """Test channel creation"""
        manager = ChannelManager()
        channel = manager.create_channel(
            name="Test Channel",
            channel_type=ChannelType.WEBHOOK,
            description="Test webhook channel"
        )
        assert channel.name == "Test Channel"
        assert channel.channel_type == ChannelType.WEBHOOK
        assert channel.status == ChannelStatus.ACTIVE

    def test_enable_disable_channel(self):
        """Test channel enable/disable"""
        manager = ChannelManager()
        channel = manager.create_channel("Test", ChannelType.LOG)

        assert manager.disable_channel(channel.id)
        assert channel.status == ChannelStatus.INACTIVE

        assert manager.enable_channel(channel.id)
        assert channel.status == ChannelStatus.ACTIVE


class TestEscalationManager:
    """Tests for EscalationManager"""

    def test_create_policy(self):
        """Test policy creation"""
        manager = EscalationManager()
        policy = manager.create_policy(
            name="Test Policy",
            description="Test escalation policy",
            severities=[AlertSeverity.CRITICAL, AlertSeverity.HIGH]
        )
        assert policy.name == "Test Policy"
        assert AlertSeverity.CRITICAL in policy.severities

    def test_builtin_policies_exist(self):
        """Test built-in policies are created"""
        manager = EscalationManager()
        assert len(manager.policies) >= 3  # At least 3 built-in policies

    def test_enable_disable_policy(self):
        """Test policy enable/disable"""
        manager = EscalationManager()
        policy = manager.create_policy("Test", "Description")

        assert manager.disable_policy(policy.id)
        assert not policy.enabled

        assert manager.enable_policy(policy.id)
        assert policy.enabled


class TestAlert:
    """Tests for Alert dataclass"""

    def test_is_flapping(self):
        """Test flapping detection"""
        alert = Alert(
            id="test-1",
            name="Test",
            description="Test",
            severity=AlertSeverity.HIGH
        )

        # Initially not flapping
        assert not alert.is_flapping()

        # Set high flap count
        alert.flap_count = 10
        assert alert.is_flapping()

    def test_should_notify(self):
        """Test notification logic"""
        alert = Alert(
            id="test-1",
            name="Test",
            description="Test",
            severity=AlertSeverity.HIGH
        )

        # Active alert should notify
        assert alert.should_notify()

        # Resolved alert should not notify
        alert.resolve()
        assert not alert.should_notify()

    def test_reactivate(self):
        """Test alert reactivation"""
        alert = Alert(
            id="test-1",
            name="Test",
            description="Test",
            severity=AlertSeverity.MEDIUM
        )
        alert.resolve()
        assert alert.status == AlertStatus.RESOLVED

        alert.reactivate("Issue returned")
        assert alert.status == AlertStatus.ACTIVE
        assert alert.flap_count == 1


class TestEscalationLevel:
    """Tests for EscalationLevel"""

    def test_to_dict(self):
        """Test serialization"""
        level = EscalationLevel(
            level=1,
            name="First Level",
            trigger=EscalationTrigger.TIME,
            trigger_minutes=15,
            actions=[EscalationAction.NOTIFY, EscalationAction.PAGE]
        )

        data = level.to_dict()
        assert data["level"] == 1
        assert data["name"] == "First Level"
        assert data["trigger"] == "time"
        assert "notify" in data["actions"]
