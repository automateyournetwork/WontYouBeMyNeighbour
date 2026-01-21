"""
Consensus Engine for Distributed RubberBand Coordination

Implements consensus protocols for coordinated decision-making across
multiple RubberBand instances. Uses voting-based consensus for critical actions.
"""

from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import asyncio


class ConsensusType(str, Enum):
    """Types of consensus decisions"""
    ROUTE_INJECTION = "route_injection"
    METRIC_ADJUSTMENT = "metric_adjustment"
    GRACEFUL_SHUTDOWN = "graceful_shutdown"
    ANOMALY_RESPONSE = "anomaly_response"
    TOPOLOGY_CHANGE = "topology_change"


class VoteType(str, Enum):
    """Vote values"""
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


@dataclass
class ConsensusProposal:
    """Proposal for distributed consensus"""
    proposal_id: str
    proposer_id: str
    consensus_type: ConsensusType
    description: str
    parameters: Dict[str, Any]
    created_at: datetime
    expires_at: datetime
    required_votes: int = 2  # Minimum votes needed
    votes: Dict[str, VoteType] = None
    status: str = "pending"  # pending, approved, rejected, expired

    def __post_init__(self):
        if self.votes is None:
            self.votes = {}

    def add_vote(self, rubberband_id: str, vote: VoteType):
        """Add vote from RubberBand instance"""
        self.votes[rubberband_id] = vote

    def get_vote_counts(self) -> Dict[str, int]:
        """Get vote counts"""
        counts = {
            "approve": 0,
            "reject": 0,
            "abstain": 0
        }
        for vote in self.votes.values():
            counts[vote.value] += 1
        return counts

    def is_approved(self) -> bool:
        """Check if proposal is approved"""
        counts = self.get_vote_counts()
        return counts["approve"] >= self.required_votes and counts["reject"] == 0

    def is_rejected(self) -> bool:
        """Check if proposal is rejected"""
        counts = self.get_vote_counts()
        return counts["reject"] > 0

    def is_expired(self) -> bool:
        """Check if proposal has expired"""
        return datetime.utcnow() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "proposal_id": self.proposal_id,
            "proposer_id": self.proposer_id,
            "consensus_type": self.consensus_type.value,
            "description": self.description,
            "parameters": self.parameters,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "required_votes": self.required_votes,
            "votes": {k: v.value for k, v in self.votes.items()},
            "status": self.status,
            "vote_counts": self.get_vote_counts()
        }


class ConsensusEngine:
    """
    Distributed consensus engine for RubberBand instances.

    Coordinates decision-making across multiple RubberBand instances using
    voting-based consensus.

    Features:
    - Proposal creation and voting
    - Timeout-based expiration
    - Quorum requirements
    - Automatic status tracking
    """

    def __init__(
        self,
        rubberband_id: str,
        gossip_protocol=None,
        proposal_timeout: int = 60  # seconds
    ):
        self.rubberband_id = rubberband_id
        self.gossip = gossip_protocol
        self.proposal_timeout = proposal_timeout

        # Active proposals
        self.proposals: Dict[str, ConsensusProposal] = {}

        # Completed proposals
        self.completed_proposals: List[ConsensusProposal] = []

        # Auto-vote rules (LLM-based in future)
        self.auto_vote_enabled = False

    def create_proposal(
        self,
        consensus_type: ConsensusType,
        description: str,
        parameters: Dict[str, Any],
        required_votes: int = 2
    ) -> ConsensusProposal:
        """
        Create new consensus proposal.

        The proposal will be broadcast via gossip protocol.
        """
        import hashlib

        # Generate proposal ID
        proposal_data = f"{self.rubberband_id}{datetime.utcnow().isoformat()}{description}"
        proposal_id = hashlib.sha256(proposal_data.encode()).hexdigest()[:16]

        proposal = ConsensusProposal(
            proposal_id=proposal_id,
            proposer_id=self.rubberband_id,
            consensus_type=consensus_type,
            description=description,
            parameters=parameters,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=self.proposal_timeout),
            required_votes=required_votes
        )

        # Store proposal
        self.proposals[proposal_id] = proposal

        # Broadcast via gossip
        if self.gossip:
            from .gossip import MessageType
            message = self.gossip.create_message(
                MessageType.CONSENSUS_REQUEST,
                payload=proposal.to_dict()
            )
            asyncio.create_task(self.gossip.broadcast(message))

        return proposal

    def receive_proposal(self, proposal_data: Dict[str, Any]) -> ConsensusProposal:
        """
        Receive proposal from another RubberBand instance.

        Returns the proposal object.
        """
        proposal = ConsensusProposal(
            proposal_id=proposal_data["proposal_id"],
            proposer_id=proposal_data["proposer_id"],
            consensus_type=ConsensusType(proposal_data["consensus_type"]),
            description=proposal_data["description"],
            parameters=proposal_data["parameters"],
            created_at=datetime.fromisoformat(proposal_data["created_at"]),
            expires_at=datetime.fromisoformat(proposal_data["expires_at"]),
            required_votes=proposal_data["required_votes"],
            votes={k: VoteType(v) for k, v in proposal_data.get("votes", {}).items()}
        )

        # Store if not already known
        if proposal.proposal_id not in self.proposals:
            self.proposals[proposal.proposal_id] = proposal

            # Auto-vote if enabled
            if self.auto_vote_enabled:
                vote = self._evaluate_proposal(proposal)
                self.vote(proposal.proposal_id, vote)

        return proposal

    def vote(
        self,
        proposal_id: str,
        vote: VoteType,
        reason: Optional[str] = None
    ) -> bool:
        """
        Vote on a proposal.

        Returns True if vote was recorded, False otherwise.
        """
        if proposal_id not in self.proposals:
            return False

        proposal = self.proposals[proposal_id]

        # Check if expired
        if proposal.is_expired():
            proposal.status = "expired"
            return False

        # Add vote
        proposal.add_vote(self.rubberband_id, vote)

        # Broadcast vote via gossip
        if self.gossip:
            from .gossip import MessageType
            message = self.gossip.create_message(
                MessageType.CONSENSUS_VOTE,
                payload={
                    "proposal_id": proposal_id,
                    "voter_id": self.rubberband_id,
                    "vote": vote.value,
                    "reason": reason
                }
            )
            asyncio.create_task(self.gossip.broadcast(message))

        # Update status
        self._update_proposal_status(proposal)

        return True

    def receive_vote(
        self,
        proposal_id: str,
        voter_id: str,
        vote: str
    ):
        """Receive vote from another RubberBand instance"""
        if proposal_id not in self.proposals:
            return

        proposal = self.proposals[proposal_id]
        proposal.add_vote(voter_id, VoteType(vote))

        # Update status
        self._update_proposal_status(proposal)

    def _update_proposal_status(self, proposal: ConsensusProposal):
        """Update proposal status based on votes"""
        if proposal.is_expired():
            proposal.status = "expired"
            self._complete_proposal(proposal)
        elif proposal.is_rejected():
            proposal.status = "rejected"
            self._complete_proposal(proposal)
        elif proposal.is_approved():
            proposal.status = "approved"
            self._complete_proposal(proposal)

    def _complete_proposal(self, proposal: ConsensusProposal):
        """Move proposal to completed list"""
        if proposal.proposal_id in self.proposals:
            del self.proposals[proposal.proposal_id]
            self.completed_proposals.append(proposal)

            # Keep only recent completed proposals
            if len(self.completed_proposals) > 100:
                self.completed_proposals = self.completed_proposals[-100:]

    def _evaluate_proposal(self, proposal: ConsensusProposal) -> VoteType:
        """
        Automatically evaluate proposal and return vote.

        In future, this would use LLM reasoning.
        For now, uses simple heuristics.
        """
        # Default: approve safe actions, reject dangerous ones
        if proposal.consensus_type == ConsensusType.GRACEFUL_SHUTDOWN:
            return VoteType.REJECT  # Requires manual approval

        elif proposal.consensus_type == ConsensusType.METRIC_ADJUSTMENT:
            # Check if adjustment is reasonable
            metric = proposal.parameters.get("proposed_metric", 0)
            if metric < 1 or metric > 65535:
                return VoteType.REJECT
            return VoteType.APPROVE

        elif proposal.consensus_type == ConsensusType.ANOMALY_RESPONSE:
            # Approve anomaly responses
            return VoteType.APPROVE

        else:
            # Default: abstain on unknown
            return VoteType.ABSTAIN

    def get_active_proposals(self) -> List[Dict[str, Any]]:
        """Get all active proposals"""
        return [p.to_dict() for p in self.proposals.values()]

    def get_proposal_status(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Get status of specific proposal"""
        if proposal_id in self.proposals:
            return self.proposals[proposal_id].to_dict()

        # Check completed
        for proposal in self.completed_proposals:
            if proposal.proposal_id == proposal_id:
                return proposal.to_dict()

        return None

    def cleanup_expired(self):
        """Remove expired proposals"""
        expired = [
            pid for pid, proposal in self.proposals.items()
            if proposal.is_expired()
        ]

        for pid in expired:
            proposal = self.proposals[pid]
            proposal.status = "expired"
            self._complete_proposal(proposal)

    def get_statistics(self) -> Dict[str, Any]:
        """Get consensus engine statistics"""
        return {
            "rubberband_id": self.rubberband_id,
            "active_proposals": len(self.proposals),
            "completed_proposals": len(self.completed_proposals),
            "auto_vote_enabled": self.auto_vote_enabled
        }

    def enable_auto_vote(self):
        """Enable automatic voting on proposals"""
        self.auto_vote_enabled = True

    def disable_auto_vote(self):
        """Disable automatic voting"""
        self.auto_vote_enabled = False
