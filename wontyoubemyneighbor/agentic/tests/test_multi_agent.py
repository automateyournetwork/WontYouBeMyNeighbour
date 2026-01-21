"""
Tests for Multi-Agent Coordination
"""

import pytest
import asyncio
from datetime import datetime, timedelta

from ..multi_agent.gossip import GossipProtocol, GossipMessage, MessageType
from ..multi_agent.consensus import ConsensusEngine, ConsensusType, VoteType, ConsensusProposal


class TestGossipProtocol:
    """Test GossipProtocol"""

    def test_initialization(self):
        gossip = GossipProtocol(rubberband_id="rubberband-1", fanout=2)
        assert gossip.rubberband_id == "rubberband-1"
        assert gossip.fanout == 2
        assert len(gossip.peers) == 0

    def test_register_peer(self):
        gossip = GossipProtocol(rubberband_id="rubberband-1")
        gossip.register_peer("rubberband-2", "192.168.1.2", 8080)

        assert "rubberband-2" in gossip.peers
        assert gossip.peers["rubberband-2"]["address"] == "192.168.1.2"

    def test_create_message(self):
        gossip = GossipProtocol(rubberband_id="rubberband-1")

        msg = gossip.create_message(
            MessageType.STATE_UPDATE,
            payload={"status": "healthy"}
        )

        assert msg.sender_id == "rubberband-1"
        assert msg.message_type == MessageType.STATE_UPDATE
        assert msg.ttl == 3
        assert "rubberband-1" in msg.seen_by

    @pytest.mark.asyncio
    async def test_receive_new_message(self):
        gossip = GossipProtocol(rubberband_id="rubberband-2")

        msg = GossipMessage(
            message_id="test123",
            message_type=MessageType.HEALTH_CHECK,
            sender_id="rubberband-1",
            timestamp=datetime.utcnow(),
            payload={"status": "alive"},
            ttl=2
        )

        is_new = await gossip.receive_message(msg)
        assert is_new
        assert "test123" in gossip.seen_messages

    @pytest.mark.asyncio
    async def test_receive_duplicate_message(self):
        gossip = GossipProtocol(rubberband_id="rubberband-2")

        msg = GossipMessage(
            message_id="test123",
            message_type=MessageType.HEALTH_CHECK,
            sender_id="rubberband-1",
            timestamp=datetime.utcnow(),
            payload={"status": "alive"},
            ttl=2
        )

        # First time
        is_new = await gossip.receive_message(msg)
        assert is_new

        # Second time (duplicate)
        is_new = await gossip.receive_message(msg)
        assert not is_new

    @pytest.mark.asyncio
    async def test_ttl_expiration(self):
        gossip = GossipProtocol(rubberband_id="rubberband-2")

        msg = GossipMessage(
            message_id="test123",
            message_type=MessageType.HEALTH_CHECK,
            sender_id="rubberband-1",
            timestamp=datetime.utcnow(),
            payload={"status": "alive"},
            ttl=0  # Expired
        )

        is_new = await gossip.receive_message(msg)
        assert not is_new

    def test_get_statistics(self):
        gossip = GossipProtocol(rubberband_id="rubberband-1")
        gossip.register_peer("rubberband-2", "192.168.1.2")

        stats = gossip.get_statistics()
        assert stats["rubberband_id"] == "rubberband-1"
        assert stats["peers"] == 1
        assert "messages_seen" in stats


class TestConsensusEngine:
    """Test ConsensusEngine"""

    def test_initialization(self):
        consensus = ConsensusEngine(rubberband_id="rubberband-1")
        assert consensus.rubberband_id == "rubberband-1"
        assert len(consensus.proposals) == 0

    def test_create_proposal(self):
        consensus = ConsensusEngine(rubberband_id="rubberband-1")

        proposal = consensus.create_proposal(
            consensus_type=ConsensusType.METRIC_ADJUSTMENT,
            description="Increase cost on eth0",
            parameters={"interface": "eth0", "proposed_metric": 20},
            required_votes=2
        )

        assert proposal.proposer_id == "rubberband-1"
        assert proposal.consensus_type == ConsensusType.METRIC_ADJUSTMENT
        assert proposal.required_votes == 2
        assert proposal.status == "pending"

    def test_vote_on_proposal(self):
        consensus = ConsensusEngine(rubberband_id="rubberband-1")

        proposal = consensus.create_proposal(
            consensus_type=ConsensusType.METRIC_ADJUSTMENT,
            description="Test",
            parameters={},
            required_votes=2
        )

        # Vote
        success = consensus.vote(proposal.proposal_id, VoteType.APPROVE)
        assert success
        assert "rubberband-1" in proposal.votes

    def test_proposal_approval(self):
        consensus = ConsensusEngine(rubberband_id="rubberband-1")

        proposal = consensus.create_proposal(
            consensus_type=ConsensusType.METRIC_ADJUSTMENT,
            description="Test",
            parameters={},
            required_votes=2
        )

        # Vote from rubberband-1
        consensus.vote(proposal.proposal_id, VoteType.APPROVE)

        # Vote from rubberband-2
        consensus.receive_vote(proposal.proposal_id, "rubberband-2", "approve")

        # Check if approved
        assert proposal.is_approved()
        assert proposal.status == "approved"

    def test_proposal_rejection(self):
        consensus = ConsensusEngine(rubberband_id="rubberband-1")

        proposal = consensus.create_proposal(
            consensus_type=ConsensusType.GRACEFUL_SHUTDOWN,
            description="Shutdown BGP",
            parameters={},
            required_votes=2
        )

        # Reject vote
        consensus.vote(proposal.proposal_id, VoteType.REJECT, "Too dangerous")

        assert proposal.is_rejected()
        assert proposal.status == "rejected"

    def test_proposal_expiration(self):
        consensus = ConsensusEngine(rubberband_id="rubberband-1", proposal_timeout=1)

        proposal = consensus.create_proposal(
            consensus_type=ConsensusType.METRIC_ADJUSTMENT,
            description="Test",
            parameters={},
            required_votes=2
        )

        # Manually expire
        proposal.expires_at = datetime.utcnow() - timedelta(seconds=10)

        assert proposal.is_expired()

    def test_get_statistics(self):
        consensus = ConsensusEngine(rubberband_id="rubberband-1")

        # Create proposals
        for i in range(3):
            consensus.create_proposal(
                consensus_type=ConsensusType.METRIC_ADJUSTMENT,
                description=f"Proposal {i}",
                parameters={},
                required_votes=2
            )

        stats = consensus.get_statistics()
        assert stats["rubberband_id"] == "rubberband-1"
        assert stats["active_proposals"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
