"""
MCP External Server Implementation for ASI Networks

Provides Model Context Protocol (MCP) server endpoints that allow
external tools like Claude Desktop, GitHub Copilot, and custom AI
agents to connect and interact with the ASI network.

MCP Protocol:
- JSON-RPC 2.0 based communication
- Tool/function discovery and invocation
- Resource access (network topology, agent state)
- Prompt templates for common operations
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import hashlib
import secrets

logger = logging.getLogger(__name__)


class ServerType(Enum):
    """MCP server types"""
    NETWORK = "network"  # Network-wide operations
    AGENT = "agent"      # Per-agent operations


class ConnectionState(Enum):
    """MCP connection states"""
    CONNECTING = "connecting"
    INITIALIZING = "initializing"
    READY = "ready"
    ACTIVE = "active"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass
class MCPToolParameter:
    """MCP tool parameter definition"""
    name: str
    param_type: str  # string, number, boolean, array, object
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to MCP schema format"""
        schema = {
            "type": self.param_type,
            "description": self.description
        }
        if self.enum:
            schema["enum"] = self.enum
        if self.default is not None:
            schema["default"] = self.default
        return schema


@dataclass
class MCPTool:
    """MCP tool definition"""
    name: str
    description: str
    parameters: List[MCPToolParameter] = field(default_factory=list)
    handler: Optional[Callable] = None
    category: str = "general"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to MCP tool format"""
        properties = {}
        required = []
        for param in self.parameters:
            properties[param.name] = param.to_dict()
            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }


@dataclass
class MCPConnection:
    """Represents an active MCP connection"""
    connection_id: str
    client_name: str
    client_version: str
    remote_address: str
    state: ConnectionState
    connected_at: datetime
    last_activity: datetime
    requests_count: int = 0
    tools_called: int = 0
    api_key_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "connection_id": self.connection_id,
            "client_name": self.client_name,
            "client_version": self.client_version,
            "remote_address": self.remote_address,
            "state": self.state.value,
            "connected_at": self.connected_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "duration_seconds": (datetime.now() - self.connected_at).total_seconds(),
            "requests_count": self.requests_count,
            "tools_called": self.tools_called
        }


@dataclass
class MCPExternalConfig:
    """MCP external server configuration"""
    port: int = 3000
    host: str = "0.0.0.0"
    server_type: ServerType = ServerType.NETWORK
    agent_name: Optional[str] = None
    api_key: Optional[str] = None
    require_auth: bool = True
    max_connections: int = 50
    rate_limit: int = 100  # requests per minute
    allowed_origins: List[str] = field(default_factory=lambda: ["*"])
    enable_resources: bool = True
    enable_prompts: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "port": self.port,
            "host": self.host,
            "server_type": self.server_type.value,
            "agent_name": self.agent_name,
            "require_auth": self.require_auth,
            "max_connections": self.max_connections,
            "rate_limit": self.rate_limit,
            "enable_resources": self.enable_resources,
            "enable_prompts": self.enable_prompts
        }


@dataclass
class MCPStatistics:
    """MCP server statistics"""
    total_connections: int = 0
    active_connections: int = 0
    total_requests: int = 0
    tool_invocations: int = 0
    resource_accesses: int = 0
    auth_failures: int = 0
    rate_limited: int = 0
    uptime_seconds: float = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "total_connections": self.total_connections,
            "active_connections": self.active_connections,
            "total_requests": self.total_requests,
            "tool_invocations": self.tool_invocations,
            "resource_accesses": self.resource_accesses,
            "auth_failures": self.auth_failures,
            "rate_limited": self.rate_limited,
            "uptime_seconds": self.uptime_seconds
        }


class MCPExternalServer:
    """
    MCP External Server for ASI Networks.

    Provides Model Context Protocol server that external tools can connect to.
    Supports both network-level and agent-level operations.
    """

    # MCP Protocol version
    PROTOCOL_VERSION = "2024-11-05"

    def __init__(
        self,
        config: Optional[MCPExternalConfig] = None,
        network_handler: Optional[Callable] = None,
        agent_handler: Optional[Callable] = None
    ):
        """
        Initialize MCP external server.

        Args:
            config: Server configuration
            network_handler: Handler for network-level operations
            agent_handler: Handler for agent-level operations
        """
        self.config = config or MCPExternalConfig()
        self.network_handler = network_handler
        self.agent_handler = agent_handler

        self._connections: Dict[str, MCPConnection] = {}
        self._tools: Dict[str, MCPTool] = {}
        self._running = False
        self._started_at: Optional[datetime] = None
        self._statistics = MCPStatistics()
        self._rate_limits: Dict[str, List[datetime]] = {}  # IP -> request times

        # Setup tools based on server type
        self._setup_tools()

    def _setup_tools(self):
        """Setup available MCP tools based on server type"""
        if self.config.server_type == ServerType.NETWORK:
            self._setup_network_tools()
        else:
            self._setup_agent_tools()

    def _setup_network_tools(self):
        """Setup network-level tools"""
        self._tools = {
            # Topology tools
            "get_topology": MCPTool(
                name="get_topology",
                description="Get the complete network topology including all agents and their connections",
                parameters=[],
                category="topology"
            ),
            "get_agents": MCPTool(
                name="get_agents",
                description="List all agents in the network with their status and protocols",
                parameters=[
                    MCPToolParameter("protocol", "string", "Filter by protocol (ospf, bgp, isis)", False),
                    MCPToolParameter("status", "string", "Filter by status (up, down)", False)
                ],
                category="topology"
            ),
            "get_agent_details": MCPTool(
                name="get_agent_details",
                description="Get detailed information about a specific agent",
                parameters=[
                    MCPToolParameter("agent_name", "string", "Name of the agent")
                ],
                category="topology"
            ),

            # Routing tools
            "get_routes": MCPTool(
                name="get_routes",
                description="Get routing table from an agent or all agents",
                parameters=[
                    MCPToolParameter("agent_name", "string", "Agent name (optional for all)", False),
                    MCPToolParameter("protocol", "string", "Filter by protocol (ospf, bgp, static)", False),
                    MCPToolParameter("prefix", "string", "Filter by prefix", False)
                ],
                category="routing"
            ),
            "get_neighbors": MCPTool(
                name="get_neighbors",
                description="Get protocol neighbors (OSPF, BGP, ISIS)",
                parameters=[
                    MCPToolParameter("agent_name", "string", "Agent name (optional for all)", False),
                    MCPToolParameter("protocol", "string", "Protocol type (ospf, bgp, isis)", False)
                ],
                category="routing"
            ),

            # Network operations
            "ping": MCPTool(
                name="ping",
                description="Ping from one agent to a destination",
                parameters=[
                    MCPToolParameter("source_agent", "string", "Source agent name"),
                    MCPToolParameter("destination", "string", "Destination IP or hostname"),
                    MCPToolParameter("count", "number", "Number of pings", False, 4)
                ],
                category="operations"
            ),
            "traceroute": MCPTool(
                name="traceroute",
                description="Traceroute from one agent to a destination",
                parameters=[
                    MCPToolParameter("source_agent", "string", "Source agent name"),
                    MCPToolParameter("destination", "string", "Destination IP or hostname")
                ],
                category="operations"
            ),

            # Testing tools
            "run_tests": MCPTool(
                name="run_tests",
                description="Run pyATS tests on agents",
                parameters=[
                    MCPToolParameter("agent_name", "string", "Agent name (optional for all)", False),
                    MCPToolParameter("test_type", "string", "Test type (connectivity, protocol, full)", False, "connectivity")
                ],
                category="testing"
            ),
            "get_test_results": MCPTool(
                name="get_test_results",
                description="Get test results from previous runs",
                parameters=[
                    MCPToolParameter("agent_name", "string", "Agent name (optional for all)", False),
                    MCPToolParameter("limit", "number", "Number of results", False, 10)
                ],
                category="testing"
            ),

            # Chat/Query tools
            "ask_network": MCPTool(
                name="ask_network",
                description="Ask a natural language question about the network",
                parameters=[
                    MCPToolParameter("question", "string", "Your question about the network")
                ],
                category="chat"
            ),
            "analyze_issue": MCPTool(
                name="analyze_issue",
                description="Analyze a network issue and get recommendations",
                parameters=[
                    MCPToolParameter("description", "string", "Description of the issue"),
                    MCPToolParameter("affected_agents", "array", "List of affected agent names", False)
                ],
                category="chat"
            ),

            # Metrics tools
            "get_metrics": MCPTool(
                name="get_metrics",
                description="Get Prometheus metrics from agents",
                parameters=[
                    MCPToolParameter("agent_name", "string", "Agent name (optional for all)", False),
                    MCPToolParameter("metric_name", "string", "Specific metric name", False)
                ],
                category="metrics"
            ),

            # Configuration tools
            "get_config": MCPTool(
                name="get_config",
                description="Get configuration from an agent",
                parameters=[
                    MCPToolParameter("agent_name", "string", "Agent name"),
                    MCPToolParameter("section", "string", "Config section (interfaces, routing, system)", False)
                ],
                category="config"
            )
        }

    def _setup_agent_tools(self):
        """Setup agent-level tools"""
        agent = self.config.agent_name or "agent"
        self._tools = {
            # Agent-specific tools
            "get_status": MCPTool(
                name="get_status",
                description=f"Get status of {agent}",
                parameters=[],
                category="status"
            ),
            "get_interfaces": MCPTool(
                name="get_interfaces",
                description=f"Get interface information from {agent}",
                parameters=[
                    MCPToolParameter("interface_name", "string", "Specific interface", False)
                ],
                category="interfaces"
            ),
            "get_routing_table": MCPTool(
                name="get_routing_table",
                description=f"Get routing table from {agent}",
                parameters=[
                    MCPToolParameter("protocol", "string", "Filter by protocol", False),
                    MCPToolParameter("prefix", "string", "Filter by prefix", False)
                ],
                category="routing"
            ),
            "get_protocol_neighbors": MCPTool(
                name="get_protocol_neighbors",
                description=f"Get protocol neighbors from {agent}",
                parameters=[
                    MCPToolParameter("protocol", "string", "Protocol (ospf, bgp, isis)", False)
                ],
                category="routing"
            ),
            "ping": MCPTool(
                name="ping",
                description=f"Ping from {agent} to a destination",
                parameters=[
                    MCPToolParameter("destination", "string", "Destination IP or hostname"),
                    MCPToolParameter("count", "number", "Number of pings", False, 4)
                ],
                category="operations"
            ),
            "traceroute": MCPTool(
                name="traceroute",
                description=f"Traceroute from {agent}",
                parameters=[
                    MCPToolParameter("destination", "string", "Destination IP or hostname")
                ],
                category="operations"
            ),
            "ask_agent": MCPTool(
                name="ask_agent",
                description=f"Ask {agent} a natural language question",
                parameters=[
                    MCPToolParameter("question", "string", "Your question")
                ],
                category="chat"
            ),
            "run_command": MCPTool(
                name="run_command",
                description=f"Run a CLI command on {agent}",
                parameters=[
                    MCPToolParameter("command", "string", "CLI command to run")
                ],
                category="operations"
            ),
            "get_logs": MCPTool(
                name="get_logs",
                description=f"Get logs from {agent}",
                parameters=[
                    MCPToolParameter("level", "string", "Log level filter", False),
                    MCPToolParameter("limit", "number", "Number of entries", False, 100)
                ],
                category="logs"
            ),
            "get_metrics": MCPTool(
                name="get_metrics",
                description=f"Get metrics from {agent}",
                parameters=[
                    MCPToolParameter("metric_name", "string", "Specific metric", False)
                ],
                category="metrics"
            ),
            "send_email": MCPTool(
                name="send_email",
                description=f"Send an email from {agent} (requires SMTP configuration)",
                parameters=[
                    MCPToolParameter("to", "string", "Recipient email address"),
                    MCPToolParameter("subject", "string", "Email subject"),
                    MCPToolParameter("body", "string", "Email body content")
                ],
                category="notifications"
            )
        }

    async def start(self) -> bool:
        """Start the MCP server"""
        if self._running:
            logger.warning(f"MCP server already running on port {self.config.port}")
            return False

        self._running = True
        self._started_at = datetime.now()

        server_desc = f"{self.config.server_type.value}"
        if self.config.agent_name:
            server_desc += f" ({self.config.agent_name})"

        logger.info(
            f"MCP external server started: {server_desc} on port {self.config.port}"
        )
        return True

    async def stop(self):
        """Stop the MCP server"""
        if not self._running:
            return

        self._running = False

        # Close all connections
        for conn_id in list(self._connections.keys()):
            await self._close_connection(conn_id)

        logger.info(f"MCP external server stopped on port {self.config.port}")

    @property
    def running(self) -> bool:
        """Check if server is running"""
        return self._running

    def validate_api_key(self, api_key: str) -> bool:
        """Validate API key"""
        if not self.config.require_auth:
            return True
        if not self.config.api_key:
            return True
        return secrets.compare_digest(api_key, self.config.api_key)

    def check_rate_limit(self, client_ip: str) -> bool:
        """Check if client is rate limited"""
        now = datetime.now()
        cutoff = now.timestamp() - 60  # 1 minute window

        if client_ip not in self._rate_limits:
            self._rate_limits[client_ip] = []

        # Clean old entries
        self._rate_limits[client_ip] = [
            t for t in self._rate_limits[client_ip]
            if t.timestamp() > cutoff
        ]

        if len(self._rate_limits[client_ip]) >= self.config.rate_limit:
            self._statistics.rate_limited += 1
            return False

        self._rate_limits[client_ip].append(now)
        return True

    def create_connection(
        self,
        client_name: str,
        client_version: str,
        remote_address: str,
        api_key: str = ""
    ) -> MCPConnection:
        """Create a new MCP connection"""
        if len(self._connections) >= self.config.max_connections:
            raise RuntimeError("Maximum connections reached")

        if self.config.require_auth and not self.validate_api_key(api_key):
            self._statistics.auth_failures += 1
            raise RuntimeError("Invalid API key")

        connection = MCPConnection(
            connection_id=str(uuid.uuid4())[:8],
            client_name=client_name,
            client_version=client_version,
            remote_address=remote_address,
            state=ConnectionState.READY,
            connected_at=datetime.now(),
            last_activity=datetime.now(),
            api_key_hash=hashlib.sha256(api_key.encode()).hexdigest()[:16] if api_key else ""
        )

        self._connections[connection.connection_id] = connection
        self._statistics.total_connections += 1
        self._statistics.active_connections = len(self._connections)

        logger.info(f"MCP connection {connection.connection_id} from {client_name}")
        return connection

    async def _close_connection(self, connection_id: str):
        """Close an MCP connection"""
        if connection_id in self._connections:
            del self._connections[connection_id]
            self._statistics.active_connections = len(self._connections)
            logger.info(f"MCP connection {connection_id} closed")

    async def handle_request(
        self,
        connection: MCPConnection,
        request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle an MCP JSON-RPC request.

        Args:
            connection: The MCP connection
            request: JSON-RPC request

        Returns:
            JSON-RPC response
        """
        connection.last_activity = datetime.now()
        connection.requests_count += 1
        self._statistics.total_requests += 1

        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")

        try:
            if method == "initialize":
                return await self._handle_initialize(request_id, params)
            elif method == "tools/list":
                return await self._handle_tools_list(request_id)
            elif method == "tools/call":
                connection.tools_called += 1
                self._statistics.tool_invocations += 1
                return await self._handle_tools_call(request_id, params)
            elif method == "resources/list":
                return await self._handle_resources_list(request_id)
            elif method == "resources/read":
                self._statistics.resource_accesses += 1
                return await self._handle_resources_read(request_id, params)
            elif method == "prompts/list":
                return await self._handle_prompts_list(request_id)
            elif method == "prompts/get":
                return await self._handle_prompts_get(request_id, params)
            else:
                return self._error_response(request_id, -32601, f"Method not found: {method}")

        except Exception as e:
            logger.error(f"MCP request error: {e}")
            return self._error_response(request_id, -32603, str(e))

    async def _handle_initialize(
        self,
        request_id: Any,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle initialize request"""
        client_info = params.get("clientInfo", {})

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": True},
                    "resources": {"subscribe": False, "listChanged": True} if self.config.enable_resources else None,
                    "prompts": {"listChanged": True} if self.config.enable_prompts else None
                },
                "serverInfo": {
                    "name": f"ASI Network MCP Server ({self.config.server_type.value})",
                    "version": "1.0.0"
                }
            }
        }

    async def _handle_tools_list(self, request_id: Any) -> Dict[str, Any]:
        """Handle tools/list request"""
        tools = [tool.to_dict() for tool in self._tools.values()]

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": tools
            }
        }

    async def _handle_tools_call(
        self,
        request_id: Any,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle tools/call request"""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in self._tools:
            return self._error_response(request_id, -32602, f"Unknown tool: {tool_name}")

        tool = self._tools[tool_name]

        # Execute tool
        try:
            if tool.handler:
                result = await tool.handler(**arguments)
            elif self.config.server_type == ServerType.NETWORK and self.network_handler:
                result = await self.network_handler(tool_name, arguments)
            elif self.config.server_type == ServerType.AGENT and self.agent_handler:
                result = await self.agent_handler(tool_name, arguments)
            else:
                result = {"message": f"Tool {tool_name} executed", "arguments": arguments}

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result)
                        }
                    ]
                }
            }

        except Exception as e:
            return self._error_response(request_id, -32603, f"Tool execution error: {e}")

    async def _handle_resources_list(self, request_id: Any) -> Dict[str, Any]:
        """Handle resources/list request"""
        if not self.config.enable_resources:
            return self._error_response(request_id, -32601, "Resources not enabled")

        resources = []
        if self.config.server_type == ServerType.NETWORK:
            resources = [
                {
                    "uri": "asi://network/topology",
                    "name": "Network Topology",
                    "description": "Complete network topology",
                    "mimeType": "application/json"
                },
                {
                    "uri": "asi://network/agents",
                    "name": "Agents List",
                    "description": "List of all network agents",
                    "mimeType": "application/json"
                },
                {
                    "uri": "asi://network/routes",
                    "name": "Routing Tables",
                    "description": "Aggregated routing information",
                    "mimeType": "application/json"
                }
            ]
        else:
            agent = self.config.agent_name
            resources = [
                {
                    "uri": f"asi://agent/{agent}/status",
                    "name": f"{agent} Status",
                    "description": f"Current status of {agent}",
                    "mimeType": "application/json"
                },
                {
                    "uri": f"asi://agent/{agent}/interfaces",
                    "name": f"{agent} Interfaces",
                    "description": f"Interface information for {agent}",
                    "mimeType": "application/json"
                },
                {
                    "uri": f"asi://agent/{agent}/routes",
                    "name": f"{agent} Routes",
                    "description": f"Routing table for {agent}",
                    "mimeType": "application/json"
                }
            ]

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "resources": resources
            }
        }

    async def _handle_resources_read(
        self,
        request_id: Any,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle resources/read request"""
        if not self.config.enable_resources:
            return self._error_response(request_id, -32601, "Resources not enabled")

        uri = params.get("uri", "")

        # Parse URI and fetch resource
        # For now, return placeholder data
        content = {"uri": uri, "data": "Resource data would be fetched here"}

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(content, indent=2)
                    }
                ]
            }
        }

    async def _handle_prompts_list(self, request_id: Any) -> Dict[str, Any]:
        """Handle prompts/list request"""
        if not self.config.enable_prompts:
            return self._error_response(request_id, -32601, "Prompts not enabled")

        prompts = [
            {
                "name": "troubleshoot",
                "description": "Troubleshoot a network issue",
                "arguments": [
                    {"name": "issue", "description": "Description of the issue", "required": True}
                ]
            },
            {
                "name": "configure_protocol",
                "description": "Get help configuring a routing protocol",
                "arguments": [
                    {"name": "protocol", "description": "Protocol name (ospf, bgp, isis)", "required": True},
                    {"name": "requirements", "description": "Configuration requirements", "required": False}
                ]
            },
            {
                "name": "analyze_topology",
                "description": "Analyze the network topology",
                "arguments": []
            },
            {
                "name": "health_check",
                "description": "Perform a network health check",
                "arguments": [
                    {"name": "scope", "description": "Scope: full, agents, connectivity", "required": False}
                ]
            }
        ]

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "prompts": prompts
            }
        }

    async def _handle_prompts_get(
        self,
        request_id: Any,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle prompts/get request"""
        if not self.config.enable_prompts:
            return self._error_response(request_id, -32601, "Prompts not enabled")

        prompt_name = params.get("name", "")
        arguments = params.get("arguments", {})

        # Generate prompt messages based on template
        messages = []
        if prompt_name == "troubleshoot":
            issue = arguments.get("issue", "unspecified issue")
            messages = [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"I'm experiencing a network issue: {issue}\n\nPlease help me troubleshoot this by:\n1. Checking relevant agent status\n2. Analyzing routing tables\n3. Testing connectivity\n4. Providing recommendations"
                    }
                }
            ]
        elif prompt_name == "analyze_topology":
            messages = [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": "Please analyze the current network topology and provide:\n1. Summary of all agents and their roles\n2. Protocol status (OSPF, BGP, etc.)\n3. Connectivity between agents\n4. Any potential issues or recommendations"
                    }
                }
            ]
        else:
            messages = [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"Execute prompt: {prompt_name} with arguments: {arguments}"
                    }
                }
            ]

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "description": f"Prompt: {prompt_name}",
                "messages": messages
            }
        }

    def _error_response(
        self,
        request_id: Any,
        code: int,
        message: str
    ) -> Dict[str, Any]:
        """Generate JSON-RPC error response"""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message
            }
        }

    def get_statistics(self) -> MCPStatistics:
        """Get server statistics"""
        if self._started_at:
            self._statistics.uptime_seconds = (
                datetime.now() - self._started_at
            ).total_seconds()
        return self._statistics

    def get_connections(self) -> List[Dict[str, Any]]:
        """Get all active connections"""
        return [c.to_dict() for c in self._connections.values()]

    def get_tools(self) -> List[Dict[str, Any]]:
        """Get all available tools"""
        return [t.to_dict() for t in self._tools.values()]

    def get_config(self) -> Dict[str, Any]:
        """Get server configuration"""
        return self.config.to_dict()


# Global MCP server instances
_mcp_servers: Dict[str, MCPExternalServer] = {}


def get_mcp_server(server_id: str) -> Optional[MCPExternalServer]:
    """Get MCP server by ID"""
    return _mcp_servers.get(server_id)


async def start_mcp_server(
    server_type: str = "network",
    agent_name: Optional[str] = None,
    port: int = 3000,
    api_key: Optional[str] = None,
    network_handler: Optional[Callable] = None,
    agent_handler: Optional[Callable] = None,
    **config_kwargs
) -> MCPExternalServer:
    """
    Start MCP external server.

    Args:
        server_type: "network" or "agent"
        agent_name: Agent name (required for agent type)
        port: Server port
        api_key: API key for authentication
        network_handler: Handler for network operations
        agent_handler: Handler for agent operations
        **config_kwargs: Additional MCPExternalConfig parameters

    Returns:
        MCPExternalServer instance
    """
    server_id = f"{server_type}:{agent_name or 'global'}:{port}"

    if server_id in _mcp_servers:
        return _mcp_servers[server_id]

    config = MCPExternalConfig(
        port=port,
        server_type=ServerType(server_type),
        agent_name=agent_name,
        api_key=api_key,
        **config_kwargs
    )

    server = MCPExternalServer(config, network_handler, agent_handler)

    if await server.start():
        _mcp_servers[server_id] = server
        logger.info(f"MCP server started: {server_id}")
    else:
        raise RuntimeError(f"Failed to start MCP server: {server_id}")

    return server


async def stop_mcp_server(server_id: str):
    """Stop MCP server by ID"""
    if server_id in _mcp_servers:
        server = _mcp_servers.pop(server_id)
        await server.stop()
        logger.info(f"MCP server stopped: {server_id}")


def get_mcp_statistics(server_id: Optional[str] = None) -> Dict[str, Any]:
    """Get MCP statistics"""
    if server_id:
        server = _mcp_servers.get(server_id)
        if server:
            return server.get_statistics().to_dict()
        return {}

    return {
        sid: server.get_statistics().to_dict()
        for sid, server in _mcp_servers.items()
    }


def list_mcp_connections(server_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List active MCP connections"""
    if server_id:
        server = _mcp_servers.get(server_id)
        if server:
            return server.get_connections()
        return []

    all_connections = []
    for sid, server in _mcp_servers.items():
        connections = server.get_connections()
        for conn in connections:
            conn["server_id"] = sid
        all_connections.extend(connections)
    return all_connections


def list_available_tools(server_id: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """List available MCP tools"""
    if server_id:
        server = _mcp_servers.get(server_id)
        if server:
            return {server_id: server.get_tools()}
        return {}

    return {
        sid: server.get_tools()
        for sid, server in _mcp_servers.items()
    }
