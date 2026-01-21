"""
MCP (Model Context Protocol) Server Integrations

This module provides integrations with various MCP servers:
- RFC: IETF RFC standards reference and lookup
- GAIT: AI session tracking and context management (audit trails)
- Markmap: Network topology visualization (mind maps)
- pyATS: Network testing and validation

Each MCP server provides specialized capabilities that can be
queried by agents to enhance their decision-making.

The 4 Mandatory MCPs for every agent:
1. GAIT MCP - Complete audit trail of all interactions
2. pyATS MCP - Network state testing and validation
3. RFC MCP - Protocol standards knowledge base
4. Markmap MCP - Self-diagramming network visualization
"""

from .rfc_mcp import RFCClient, RFCLookup, RFCSearch, get_rfc_client
from .gait_mcp import (
    GAITClient,
    GAITCommit,
    GAITEventType,
    GAITActor,
    GAITMemoryItem,
    get_gait_client,
    init_gait_for_agent,
)
from .markmap_mcp import (
    MarkmapClient,
    MarkmapGenerator,
    MarkmapOptions,
    MarkmapTheme,
    AgentStateCollector,
    get_markmap_client,
)

__all__ = [
    # RFC MCP
    'RFCClient',
    'RFCLookup',
    'RFCSearch',
    'get_rfc_client',
    # GAIT MCP
    'GAITClient',
    'GAITCommit',
    'GAITEventType',
    'GAITActor',
    'GAITMemoryItem',
    'get_gait_client',
    'init_gait_for_agent',
    # Markmap MCP
    'MarkmapClient',
    'MarkmapGenerator',
    'MarkmapOptions',
    'MarkmapTheme',
    'AgentStateCollector',
    'get_markmap_client',
]
