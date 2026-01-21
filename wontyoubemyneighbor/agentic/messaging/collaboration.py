"""
Collaboration Manager - Coordinated agent activities

Provides:
- Collaborative troubleshooting sessions
- Configuration change proposals and voting
- Network consensus mechanisms
- Distributed decision making
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Set
from collections import deque
import uuid

from .bus import MessageBus, Message, MessageType, MessagePriority, get_message_bus

logger = logging.getLogger("CollaborationManager")


class SessionStatus(Enum):
    """Troubleshooting session status"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CLOSED = "closed"


class VoteResult(Enum):
    """Vote result"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


@dataclass
class TroubleshootingSession:
    """
    Collaborative troubleshooting session

    Attributes:
        session_id: Unique session identifier
        initiator_id: Agent that started the session
        issue: Issue description
        participants: Agents involved in troubleshooting
        findings: Collected findings from participants
        recommendations: Suggested actions
        status: Session status
        created_at: Session creation time
        resolved_at: Resolution time
    """
    session_id: str
    initiator_id: str
    issue: str
    context: Dict[str, Any] = field(default_factory=dict)
    participants: Set[str] = field(default_factory=set)
    findings: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)  # agent_id -> [findings]
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    status: SessionStatus = SessionStatus.OPEN
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    resolution: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "initiator_id": self.initiator_id,
            "issue": self.issue,
            "context": self.context,
            "participants": list(self.participants),
            "findings": self.findings,
            "recommendations": self.recommendations,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution": self.resolution
        }

    def add_finding(self, agent_id: str, finding: Dict[str, Any]) -> None:
        """Add a finding from an agent"""
        if agent_id not in self.findings:
            self.findings[agent_id] = []
        self.findings[agent_id].append({
            **finding,
            "timestamp": datetime.now().isoformat()
        })
        self.participants.add(agent_id)

    def add_recommendation(self, agent_id: str, action: str, priority: str = "normal") -> None:
        """Add a recommendation"""
        self.recommendations.append({
            "agent_id": agent_id,
            "action": action,
            "priority": priority,
            "timestamp": datetime.now().isoformat()
        })


@dataclass
class ConfigChangeRequest:
    """
    Configuration change request for voting

    Attributes:
        request_id: Unique request identifier
        proposer_id: Agent proposing the change
        change_type: Type of configuration change
        target_agent: Agent to be modified (or "network" for network-wide)
        current_config: Current configuration
        proposed_config: Proposed configuration
        reason: Reason for the change
        votes: Collected votes
        required_votes: Number of votes required
        status: Voting status
    """
    request_id: str
    proposer_id: str
    change_type: str
    target_agent: str
    current_config: Dict[str, Any]
    proposed_config: Dict[str, Any]
    reason: str
    votes: Dict[str, 'ConsensusVote'] = field(default_factory=dict)
    required_votes: int = 2
    quorum_percentage: float = 0.5
    status: VoteResult = VoteResult.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    deadline: datetime = field(default_factory=lambda: datetime.now() + timedelta(minutes=5))
    executed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "proposer_id": self.proposer_id,
            "change_type": self.change_type,
            "target_agent": self.target_agent,
            "current_config": self.current_config,
            "proposed_config": self.proposed_config,
            "reason": self.reason,
            "votes": {k: v.to_dict() for k, v in self.votes.items()},
            "required_votes": self.required_votes,
            "quorum_percentage": self.quorum_percentage,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "deadline": self.deadline.isoformat(),
            "executed": self.executed
        }

    def add_vote(self, vote: 'ConsensusVote') -> None:
        """Add a vote"""
        self.votes[vote.voter_id] = vote

    def check_result(self, total_voters: int) -> VoteResult:
        """Check voting result"""
        if datetime.now() > self.deadline:
            self.status = VoteResult.TIMEOUT
            return self.status

        if len(self.votes) < self.required_votes:
            return VoteResult.PENDING

        quorum = int(total_voters * self.quorum_percentage)
        if len(self.votes) < quorum:
            return VoteResult.PENDING

        approve_count = sum(1 for v in self.votes.values() if v.approve)
        reject_count = len(self.votes) - approve_count

        if approve_count > reject_count:
            self.status = VoteResult.APPROVED
        else:
            self.status = VoteResult.REJECTED

        return self.status


@dataclass
class ConsensusVote:
    """
    Vote for a configuration change

    Attributes:
        voter_id: Voting agent ID
        request_id: Request being voted on
        approve: True for approve, False for reject
        reason: Reason for the vote
        timestamp: Vote timestamp
    """
    voter_id: str
    request_id: str
    approve: bool
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "voter_id": self.voter_id,
            "request_id": self.request_id,
            "approve": self.approve,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat()
        }


class CollaborationManager:
    """
    Manages collaborative activities between agents

    Coordinates troubleshooting, voting, and consensus.
    """

    def __init__(self, bus: Optional[MessageBus] = None, max_history: int = 100):
        """
        Initialize collaboration manager

        Args:
            bus: Message bus instance (uses global if not provided)
            max_history: Maximum history to retain
        """
        self.bus = bus or get_message_bus()
        self._sessions: Dict[str, TroubleshootingSession] = {}
        self._change_requests: Dict[str, ConfigChangeRequest] = {}
        self._session_history: deque = deque(maxlen=max_history)
        self._request_history: deque = deque(maxlen=max_history)

    # Troubleshooting sessions

    async def start_troubleshooting(
        self,
        initiator_id: str,
        issue: str,
        context: Dict[str, Any],
        invite_agents: Optional[List[str]] = None
    ) -> TroubleshootingSession:
        """
        Start a collaborative troubleshooting session

        Args:
            initiator_id: Agent starting the session
            issue: Issue description
            context: Additional context (affected routes, protocols, etc.)
            invite_agents: Specific agents to invite (None = broadcast)

        Returns:
            New troubleshooting session
        """
        session_id = f"ts-{uuid.uuid4().hex[:8]}"
        session = TroubleshootingSession(
            session_id=session_id,
            initiator_id=initiator_id,
            issue=issue,
            context=context,
            status=SessionStatus.OPEN
        )
        session.participants.add(initiator_id)

        self._sessions[session_id] = session

        # Send troubleshooting requests
        if invite_agents:
            for agent_id in invite_agents:
                await self.bus.request_troubleshoot(
                    sender_id=initiator_id,
                    recipient_id=agent_id,
                    issue=issue,
                    context={**context, "session_id": session_id}
                )
        else:
            # Broadcast to all
            message = Message.create(
                message_type=MessageType.TROUBLESHOOT_REQUEST,
                sender_id=initiator_id,
                payload={
                    "session_id": session_id,
                    "issue": issue,
                    "context": context
                },
                topic="troubleshooting"
            )
            await self.bus.send(message)

        logger.info(f"Troubleshooting session started: {session_id}")
        return session

    async def join_troubleshooting(
        self,
        session_id: str,
        agent_id: str
    ) -> Optional[TroubleshootingSession]:
        """Join an existing troubleshooting session"""
        if session_id not in self._sessions:
            return None

        session = self._sessions[session_id]
        session.participants.add(agent_id)
        session.status = SessionStatus.IN_PROGRESS

        logger.info(f"Agent {agent_id} joined session {session_id}")
        return session

    async def add_finding(
        self,
        session_id: str,
        agent_id: str,
        finding_type: str,
        description: str,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Add a finding to a troubleshooting session"""
        if session_id not in self._sessions:
            return False

        session = self._sessions[session_id]
        session.add_finding(agent_id, {
            "type": finding_type,
            "description": description,
            "data": data or {}
        })

        # Notify other participants
        message = Message.create(
            message_type=MessageType.TROUBLESHOOT_RESPONSE,
            sender_id=agent_id,
            payload={
                "session_id": session_id,
                "finding_type": finding_type,
                "description": description,
                "data": data
            },
            topic="troubleshooting"
        )
        await self.bus.send(message)

        return True

    async def add_recommendation(
        self,
        session_id: str,
        agent_id: str,
        action: str,
        priority: str = "normal"
    ) -> bool:
        """Add a recommendation to a troubleshooting session"""
        if session_id not in self._sessions:
            return False

        session = self._sessions[session_id]
        session.add_recommendation(agent_id, action, priority)
        return True

    async def resolve_troubleshooting(
        self,
        session_id: str,
        resolution: str
    ) -> Optional[TroubleshootingSession]:
        """Resolve and close a troubleshooting session"""
        if session_id not in self._sessions:
            return None

        session = self._sessions[session_id]
        session.status = SessionStatus.RESOLVED
        session.resolved_at = datetime.now()
        session.resolution = resolution

        # Archive
        self._session_history.append(session)
        del self._sessions[session_id]

        logger.info(f"Troubleshooting session resolved: {session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[TroubleshootingSession]:
        """Get a troubleshooting session"""
        return self._sessions.get(session_id)

    def list_sessions(self, status: Optional[SessionStatus] = None) -> List[TroubleshootingSession]:
        """List active troubleshooting sessions"""
        sessions = list(self._sessions.values())
        if status:
            sessions = [s for s in sessions if s.status == status]
        return sessions

    # Configuration voting

    async def propose_config_change(
        self,
        proposer_id: str,
        change_type: str,
        target_agent: str,
        current_config: Dict[str, Any],
        proposed_config: Dict[str, Any],
        reason: str,
        required_votes: int = 2,
        timeout_minutes: int = 5
    ) -> ConfigChangeRequest:
        """
        Propose a configuration change for voting

        Args:
            proposer_id: Agent proposing the change
            change_type: Type of change (ospf_metric, bgp_policy, etc.)
            target_agent: Agent to be modified
            current_config: Current configuration
            proposed_config: Proposed configuration
            reason: Reason for the change
            required_votes: Minimum votes required
            timeout_minutes: Voting timeout

        Returns:
            Configuration change request
        """
        request_id = f"cfg-{uuid.uuid4().hex[:8]}"
        request = ConfigChangeRequest(
            request_id=request_id,
            proposer_id=proposer_id,
            change_type=change_type,
            target_agent=target_agent,
            current_config=current_config,
            proposed_config=proposed_config,
            reason=reason,
            required_votes=required_votes,
            deadline=datetime.now() + timedelta(minutes=timeout_minutes)
        )

        self._change_requests[request_id] = request

        # Broadcast proposal
        message = Message.create(
            message_type=MessageType.CONFIG_PROPOSAL,
            sender_id=proposer_id,
            payload=request.to_dict(),
            topic="config_changes",
            priority=MessagePriority.HIGH
        )
        await self.bus.send(message)

        logger.info(f"Config change proposed: {request_id} by {proposer_id}")
        return request

    async def vote_on_change(
        self,
        request_id: str,
        voter_id: str,
        approve: bool,
        reason: str = ""
    ) -> Optional[VoteResult]:
        """
        Vote on a configuration change

        Args:
            request_id: Change request to vote on
            voter_id: Voting agent
            approve: True to approve, False to reject
            reason: Reason for vote

        Returns:
            Current vote result
        """
        if request_id not in self._change_requests:
            return None

        request = self._change_requests[request_id]

        if request.status != VoteResult.PENDING:
            return request.status

        vote = ConsensusVote(
            voter_id=voter_id,
            request_id=request_id,
            approve=approve,
            reason=reason
        )
        request.add_vote(vote)

        # Notify
        message = Message.create(
            message_type=MessageType.CONFIG_VOTE,
            sender_id=voter_id,
            payload={
                "request_id": request_id,
                "approve": approve,
                "reason": reason
            },
            topic="config_changes"
        )
        await self.bus.send(message)

        # Check result
        total_agents = len(self.bus._agents)
        result = request.check_result(total_agents)

        if result == VoteResult.APPROVED:
            await self._notify_approval(request)
        elif result == VoteResult.REJECTED:
            await self._notify_rejection(request)

        return result

    async def _notify_approval(self, request: ConfigChangeRequest) -> None:
        """Notify agents of approved change"""
        message = Message.create(
            message_type=MessageType.CONFIG_COMMIT,
            sender_id=request.proposer_id,
            payload={
                "request_id": request.request_id,
                "status": "approved",
                "target_agent": request.target_agent,
                "config": request.proposed_config
            },
            topic="config_changes",
            priority=MessagePriority.HIGH
        )
        await self.bus.send(message)
        logger.info(f"Config change approved: {request.request_id}")

    async def _notify_rejection(self, request: ConfigChangeRequest) -> None:
        """Notify agents of rejected change"""
        message = Message.create(
            message_type=MessageType.CONFIG_COMMIT,
            sender_id=request.proposer_id,
            payload={
                "request_id": request.request_id,
                "status": "rejected"
            },
            topic="config_changes"
        )
        await self.bus.send(message)
        logger.info(f"Config change rejected: {request.request_id}")

    def get_change_request(self, request_id: str) -> Optional[ConfigChangeRequest]:
        """Get a configuration change request"""
        return self._change_requests.get(request_id)

    def list_change_requests(self, status: Optional[VoteResult] = None) -> List[ConfigChangeRequest]:
        """List configuration change requests"""
        requests = list(self._change_requests.values())
        if status:
            requests = [r for r in requests if r.status == status]
        return requests

    # Statistics

    def get_statistics(self) -> Dict[str, Any]:
        """Get collaboration statistics"""
        return {
            "active_sessions": len(self._sessions),
            "session_history": len(self._session_history),
            "pending_changes": len([r for r in self._change_requests.values() if r.status == VoteResult.PENDING]),
            "approved_changes": len([r for r in self._change_requests.values() if r.status == VoteResult.APPROVED]),
            "rejected_changes": len([r for r in self._change_requests.values() if r.status == VoteResult.REJECTED]),
            "request_history": len(self._request_history)
        }


# Global collaboration manager instance
_global_collab: Optional[CollaborationManager] = None


def get_collaboration_manager() -> CollaborationManager:
    """Get or create the global collaboration manager"""
    global _global_collab
    if _global_collab is None:
        _global_collab = CollaborationManager()
    return _global_collab
