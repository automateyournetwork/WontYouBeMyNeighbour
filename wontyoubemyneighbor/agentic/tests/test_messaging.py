"""
Test suite for Agent Messaging module.

Tests cover:
- Message dataclass and types
- MessageBus operations
- CollaborationManager
- Troubleshooting sessions
- Consensus mechanisms
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock

from ..messaging.bus import (
    MessageBus,
    Message,
    MessageType,
    MessagePriority,
)
from ..messaging.collaboration import (
    CollaborationManager,
    TroubleshootingSession,
    ConfigChangeRequest,
    ConsensusVote,
)


class TestMessageType:
    """Tests for message type enumeration."""

    def test_message_types(self):
        """Test message type values."""
        assert MessageType.ROUTING_UPDATE.value == "routing_update"
        assert MessageType.TOPOLOGY_CHANGE.value == "topology_change"
        assert MessageType.CONFIG_SYNC.value == "config_sync"
        assert MessageType.HEARTBEAT.value == "heartbeat"
        assert MessageType.ALERT.value == "alert"


class TestMessagePriority:
    """Tests for message priority enumeration."""

    def test_priority_values(self):
        """Test priority levels."""
        assert MessagePriority.LOW.value < MessagePriority.NORMAL.value
        assert MessagePriority.NORMAL.value < MessagePriority.HIGH.value
        assert MessagePriority.HIGH.value < MessagePriority.CRITICAL.value

    def test_priority_ordering(self):
        """Test that priorities can be compared."""
        assert MessagePriority.LOW.value == 1
        assert MessagePriority.CRITICAL.value == 4


class TestMessage:
    """Tests for Message dataclass."""

    def test_basic_message(self):
        """Test creating basic message."""
        msg = Message(
            msg_type=MessageType.HEARTBEAT,
            sender="agent-01",
            content={"status": "alive"}
        )
        assert msg.msg_type == MessageType.HEARTBEAT
        assert msg.sender == "agent-01"
        assert msg.priority == MessagePriority.NORMAL  # Default

    def test_message_with_recipient(self):
        """Test message with specific recipient."""
        msg = Message(
            msg_type=MessageType.CONFIG_SYNC,
            sender="agent-01",
            recipient="agent-02",
            content={"config": "data"}
        )
        assert msg.recipient == "agent-02"

    def test_message_with_priority(self):
        """Test message with explicit priority."""
        msg = Message(
            msg_type=MessageType.ALERT,
            sender="agent-01",
            content={"alert": "critical"},
            priority=MessagePriority.CRITICAL
        )
        assert msg.priority == MessagePriority.CRITICAL

    def test_message_timestamp(self):
        """Test message has timestamp."""
        msg = Message(
            msg_type=MessageType.HEARTBEAT,
            sender="agent-01",
            content={}
        )
        assert msg.timestamp is not None

    def test_message_id_generation(self):
        """Test message ID is generated."""
        msg1 = Message(
            msg_type=MessageType.HEARTBEAT,
            sender="agent-01",
            content={}
        )
        msg2 = Message(
            msg_type=MessageType.HEARTBEAT,
            sender="agent-01",
            content={}
        )
        assert msg1.id != msg2.id

    def test_message_to_dict(self):
        """Test message serialization."""
        msg = Message(
            msg_type=MessageType.ROUTING_UPDATE,
            sender="agent-01",
            content={"routes": []}
        )
        data = msg.to_dict()
        assert data["msg_type"] == "routing_update"
        assert data["sender"] == "agent-01"
        assert "id" in data


class TestMessageBus:
    """Tests for MessageBus functionality."""

    @pytest.fixture
    def bus(self):
        """Create a test message bus instance."""
        return MessageBus()

    def test_bus_initialization(self, bus):
        """Test bus initializes correctly."""
        assert bus is not None
        assert bus._running is False

    def test_subscribe(self, bus):
        """Test subscribing to message types."""
        callback = Mock()
        bus.subscribe(MessageType.HEARTBEAT, callback)

        assert MessageType.HEARTBEAT in bus._subscribers
        assert callback in bus._subscribers[MessageType.HEARTBEAT]

    def test_unsubscribe(self, bus):
        """Test unsubscribing from message types."""
        callback = Mock()
        bus.subscribe(MessageType.HEARTBEAT, callback)
        bus.unsubscribe(MessageType.HEARTBEAT, callback)

        assert callback not in bus._subscribers.get(MessageType.HEARTBEAT, [])

    def test_publish_message(self, bus):
        """Test publishing a message."""
        callback = Mock()
        bus.subscribe(MessageType.HEARTBEAT, callback)

        msg = Message(
            msg_type=MessageType.HEARTBEAT,
            sender="agent-01",
            content={"status": "alive"}
        )
        bus.publish(msg)

        callback.assert_called_once_with(msg)

    def test_publish_to_multiple_subscribers(self, bus):
        """Test publishing to multiple subscribers."""
        callback1 = Mock()
        callback2 = Mock()
        bus.subscribe(MessageType.ALERT, callback1)
        bus.subscribe(MessageType.ALERT, callback2)

        msg = Message(
            msg_type=MessageType.ALERT,
            sender="agent-01",
            content={"alert": "test"}
        )
        bus.publish(msg)

        callback1.assert_called_once()
        callback2.assert_called_once()

    def test_publish_no_subscribers(self, bus):
        """Test publishing with no subscribers doesn't error."""
        msg = Message(
            msg_type=MessageType.HEARTBEAT,
            sender="agent-01",
            content={}
        )
        # Should not raise
        bus.publish(msg)

    def test_message_queue(self, bus):
        """Test message queue functionality."""
        msg = Message(
            msg_type=MessageType.ROUTING_UPDATE,
            sender="agent-01",
            content={"routes": []}
        )
        bus.queue_message(msg)

        assert len(bus._queue) == 1

    def test_get_statistics(self, bus):
        """Test getting bus statistics."""
        stats = bus.get_statistics()

        assert "messages_published" in stats
        assert "messages_queued" in stats
        assert "subscribers" in stats


class TestConsensusVote:
    """Tests for consensus vote dataclass."""

    def test_vote_creation(self):
        """Test creating consensus vote."""
        vote = ConsensusVote(
            voter_id="agent-01",
            session_id="session-123",
            decision=True,
            reason="Configuration looks correct"
        )
        assert vote.voter_id == "agent-01"
        assert vote.decision is True

    def test_vote_rejection(self):
        """Test rejection vote."""
        vote = ConsensusVote(
            voter_id="agent-02",
            session_id="session-123",
            decision=False,
            reason="Conflicts with existing policy"
        )
        assert vote.decision is False


class TestConfigChangeRequest:
    """Tests for configuration change request dataclass."""

    def test_change_request_creation(self):
        """Test creating config change request."""
        request = ConfigChangeRequest(
            requester_id="agent-01",
            target_agents=["agent-02", "agent-03"],
            change_type="interface_config",
            change_data={"interface": "eth0", "mtu": 9000}
        )
        assert request.requester_id == "agent-01"
        assert len(request.target_agents) == 2

    def test_change_request_single_target(self):
        """Test request with single target."""
        request = ConfigChangeRequest(
            requester_id="agent-01",
            target_agents=["agent-02"],
            change_type="routing_policy",
            change_data={"policy": "new_policy"}
        )
        assert len(request.target_agents) == 1


class TestTroubleshootingSession:
    """Tests for troubleshooting session dataclass."""

    def test_session_creation(self):
        """Test creating troubleshooting session."""
        session = TroubleshootingSession(
            session_id="ts-001",
            initiator="agent-01",
            participants=["agent-01", "agent-02", "agent-03"],
            issue_description="Intermittent packet loss on link"
        )
        assert session.session_id == "ts-001"
        assert len(session.participants) == 3

    def test_session_status(self):
        """Test session status tracking."""
        session = TroubleshootingSession(
            session_id="ts-001",
            initiator="agent-01",
            participants=["agent-01"],
            issue_description="Test issue"
        )
        assert session.status == "active"  # Default

    def test_session_findings(self):
        """Test adding findings to session."""
        session = TroubleshootingSession(
            session_id="ts-001",
            initiator="agent-01",
            participants=["agent-01"],
            issue_description="Test issue",
            findings=["Finding 1", "Finding 2"]
        )
        assert len(session.findings) == 2


class TestCollaborationManager:
    """Tests for collaboration manager functionality."""

    @pytest.fixture
    def manager(self):
        """Create a test collaboration manager."""
        return CollaborationManager(agent_id="agent-01")

    def test_manager_initialization(self, manager):
        """Test manager initializes correctly."""
        assert manager.agent_id == "agent-01"

    def test_start_troubleshooting_session(self, manager):
        """Test starting troubleshooting session."""
        session = manager.start_troubleshooting(
            participants=["agent-02", "agent-03"],
            issue="Network connectivity issue"
        )
        assert session is not None
        assert "agent-01" in session.participants  # Initiator included

    def test_join_troubleshooting_session(self, manager):
        """Test joining existing session."""
        session = manager.start_troubleshooting(
            participants=["agent-02"],
            issue="Test issue"
        )
        result = manager.join_session(session.session_id)
        assert result is True

    def test_add_finding(self, manager):
        """Test adding finding to session."""
        session = manager.start_troubleshooting(
            participants=["agent-02"],
            issue="Test issue"
        )
        manager.add_finding(
            session_id=session.session_id,
            finding="Discovered CRC errors on eth0"
        )
        updated = manager.get_session(session.session_id)
        assert len(updated.findings) == 1

    def test_propose_config_change(self, manager):
        """Test proposing configuration change."""
        request = manager.propose_config_change(
            targets=["agent-02", "agent-03"],
            change_type="mtu_update",
            change_data={"mtu": 9000}
        )
        assert request is not None

    def test_vote_on_change(self, manager):
        """Test voting on config change."""
        request = manager.propose_config_change(
            targets=["agent-02"],
            change_type="test_change",
            change_data={}
        )
        vote = manager.vote_on_change(
            request_id=request.id,
            approve=True,
            reason="Approved for testing"
        )
        assert vote.decision is True

    def test_close_session(self, manager):
        """Test closing troubleshooting session."""
        session = manager.start_troubleshooting(
            participants=["agent-02"],
            issue="Test issue"
        )
        manager.close_session(
            session_id=session.session_id,
            resolution="Issue resolved - replaced faulty cable"
        )
        updated = manager.get_session(session.session_id)
        assert updated.status == "closed"

    def test_list_active_sessions(self, manager):
        """Test listing active sessions."""
        manager.start_troubleshooting(participants=["agent-02"], issue="Issue 1")
        manager.start_troubleshooting(participants=["agent-03"], issue="Issue 2")

        sessions = manager.list_sessions(status="active")
        assert len(sessions) == 2


class TestCollaborativeScenarios:
    """Tests for collaborative troubleshooting scenarios."""

    @pytest.fixture
    def agents(self):
        """Create multiple collaboration managers."""
        return [
            CollaborationManager(agent_id="agent-01"),
            CollaborationManager(agent_id="agent-02"),
            CollaborationManager(agent_id="agent-03"),
        ]

    def test_multi_agent_troubleshooting(self, agents):
        """Test multi-agent troubleshooting workflow."""
        agent1, agent2, agent3 = agents

        # Agent 1 starts session
        session = agent1.start_troubleshooting(
            participants=["agent-02", "agent-03"],
            issue="High latency between sites"
        )

        # Each agent adds findings
        agent1.add_finding(session.session_id, "No packet drops on local interfaces")
        # In reality, agent2 and agent3 would have their own manager instances

        # Close with resolution
        agent1.close_session(
            session.session_id,
            resolution="Identified congestion on WAN link"
        )

        final = agent1.get_session(session.session_id)
        assert final.status == "closed"
        assert len(final.findings) >= 1

    def test_consensus_based_config_change(self, agents):
        """Test consensus-based configuration change."""
        agent1, agent2, agent3 = agents

        # Agent 1 proposes change
        request = agent1.propose_config_change(
            targets=["agent-02", "agent-03"],
            change_type="routing_policy",
            change_data={"policy": "prefer_path_a"}
        )

        # Simulate voting (in reality, this would be across network)
        vote1 = agent1.vote_on_change(request.id, approve=True, reason="Agree")
        # Other agents would vote through their own managers

        assert request is not None
        assert vote1.decision is True
