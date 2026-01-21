"""
Agent Messaging Module - Agent-to-Agent Communication

Provides:
- Message bus for inter-agent communication
- Collaborative troubleshooting
- Routing information sharing
- Coordinated configuration changes
- Network consensus mechanisms
"""

from .bus import (
    MessageBus,
    Message,
    MessageType,
    MessagePriority
)
from .collaboration import (
    CollaborationManager,
    TroubleshootingSession,
    ConfigChangeRequest,
    ConsensusVote
)

__all__ = [
    'MessageBus',
    'Message',
    'MessageType',
    'MessagePriority',
    'CollaborationManager',
    'TroubleshootingSession',
    'ConfigChangeRequest',
    'ConsensusVote'
]
