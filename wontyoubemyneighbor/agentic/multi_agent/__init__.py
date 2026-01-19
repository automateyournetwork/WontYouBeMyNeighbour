"""
Multi-Agent Coordination Layer

Enables Ralph-to-Ralph communication for distributed consensus and state sharing.
"""

from .gossip import GossipProtocol, GossipMessage
from .consensus import ConsensusEngine, ConsensusProposal

__all__ = [
    "GossipProtocol",
    "GossipMessage",
    "ConsensusEngine",
    "ConsensusProposal",
]
