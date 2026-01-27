"""
MCP External Access Module for ASI Networks

Provides MCP (Model Context Protocol) server endpoints for external tools
to connect and interact with the ASI network and individual agents.

Features:
- Network-level MCP server for global operations
- Per-agent MCP server for agent-specific operations
- Authentication via API keys
- Rate limiting and access control
- Comprehensive tool/function exposure

Usage:
    from agentic.mcp_external import (
        MCPExternalServer, MCPExternalConfig,
        start_mcp_server, stop_mcp_server
    )

    # Start network-level MCP server
    server = await start_mcp_server(
        server_type="network",
        port=3000,
        api_key="your-api-key"
    )

    # Start agent-level MCP server
    agent_server = await start_mcp_server(
        server_type="agent",
        agent_name="router-1",
        port=3001
    )
"""

from .mcp_server import (
    MCPExternalServer,
    MCPExternalConfig,
    MCPConnection,
    MCPTool,
    MCPToolParameter,
    ServerType,
    ConnectionState,
    get_mcp_server,
    start_mcp_server,
    stop_mcp_server,
    get_mcp_statistics,
    list_mcp_connections,
    list_available_tools,
)

__all__ = [
    "MCPExternalServer",
    "MCPExternalConfig",
    "MCPConnection",
    "MCPTool",
    "MCPToolParameter",
    "ServerType",
    "ConnectionState",
    "get_mcp_server",
    "start_mcp_server",
    "stop_mcp_server",
    "get_mcp_statistics",
    "list_mcp_connections",
    "list_available_tools",
]
