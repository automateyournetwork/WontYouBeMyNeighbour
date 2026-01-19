"""
Protocol Integration Layer

Bridges the agentic layer with native OSPF and BGP protocol implementations.
"""

from .bridge import AgenticBridge
from .ospf_connector import OSPFConnector
from .bgp_connector import BGPConnector

__all__ = [
    "AgenticBridge",
    "OSPFConnector",
    "BGPConnector",
]
