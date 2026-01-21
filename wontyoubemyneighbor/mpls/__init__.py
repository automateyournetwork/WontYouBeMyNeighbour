"""
MPLS (Multi-Protocol Label Switching) Implementation

Implements MPLS forwarding plane and LDP (Label Distribution Protocol)
control plane as per RFC 3031 and RFC 5036.

Components:
- Label switching and forwarding
- LDP session management
- Label binding and distribution
- LFIB (Label Forwarding Information Base)
"""

from .label import Label, LabelStack, LabelAction
from .lfib import LFIB, LFIBEntry
from .ldp import LDPSession, LDPSpeaker, FEC
from .forwarding import MPLSForwarder

__all__ = [
    'Label',
    'LabelStack',
    'LabelAction',
    'LFIB',
    'LFIBEntry',
    'LDPSession',
    'LDPSpeaker',
    'FEC',
    'MPLSForwarder',
]
