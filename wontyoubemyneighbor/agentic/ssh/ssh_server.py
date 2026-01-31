"""
SSH Server Implementation for ASI Agents

Provides SSH access to agent chat interfaces using asyncssh.
Allows users to connect via SSH and interact with agents using
both CLI commands and natural language queries.

IEEE/RFC Compliance:
- RFC 4251: SSH Protocol Architecture
- RFC 4252: SSH Authentication Protocol
- RFC 4253: SSH Transport Layer Protocol
- RFC 4254: SSH Connection Protocol
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class SSHAuthMethod(Enum):
    """SSH authentication methods"""
    PASSWORD = "password"
    PUBLIC_KEY = "publickey"
    KEYBOARD_INTERACTIVE = "keyboard-interactive"
    NONE = "none"


class SSHSessionState(Enum):
    """SSH session states"""
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    CONNECTED = "connected"
    ACTIVE = "active"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"


@dataclass
class SSHSession:
    """Represents an active SSH session"""
    session_id: str
    username: str
    remote_address: str
    remote_port: int
    auth_method: SSHAuthMethod
    state: SSHSessionState
    connected_at: datetime
    last_activity: datetime
    commands_executed: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    client_version: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "session_id": self.session_id,
            "username": self.username,
            "remote_address": self.remote_address,
            "remote_port": self.remote_port,
            "auth_method": self.auth_method.value,
            "state": self.state.value,
            "connected_at": self.connected_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "duration_seconds": (datetime.now() - self.connected_at).total_seconds(),
            "commands_executed": self.commands_executed,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "client_version": self.client_version
        }


@dataclass
class SSHConfig:
    """SSH server configuration"""
    port: int = 2200
    host: str = "0.0.0.0"
    host_keys: List[str] = field(default_factory=list)
    authorized_keys_file: Optional[str] = None
    password_auth: bool = True
    public_key_auth: bool = True
    default_username: str = "admin"
    default_password: str = "admin"  # Should be changed in production
    banner: Optional[str] = None
    idle_timeout: int = 300  # 5 minutes
    max_sessions: int = 10
    login_timeout: int = 30
    allow_agent_forwarding: bool = False
    log_sessions: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "port": self.port,
            "host": self.host,
            "password_auth": self.password_auth,
            "public_key_auth": self.public_key_auth,
            "idle_timeout": self.idle_timeout,
            "max_sessions": self.max_sessions,
            "login_timeout": self.login_timeout,
            "allow_agent_forwarding": self.allow_agent_forwarding,
            "log_sessions": self.log_sessions
        }


@dataclass
class SSHStatistics:
    """SSH server statistics"""
    total_connections: int = 0
    active_sessions: int = 0
    failed_auth_attempts: int = 0
    successful_logins: int = 0
    total_commands: int = 0
    total_bytes_sent: int = 0
    total_bytes_received: int = 0
    uptime_seconds: float = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "total_connections": self.total_connections,
            "active_sessions": self.active_sessions,
            "failed_auth_attempts": self.failed_auth_attempts,
            "successful_logins": self.successful_logins,
            "total_commands": self.total_commands,
            "total_bytes_sent": self.total_bytes_sent,
            "total_bytes_received": self.total_bytes_received,
            "uptime_seconds": self.uptime_seconds
        }


class SSHServerProcess:
    """
    SSH Server process handler.

    This class manages the SSH server for an agent, handling connections,
    authentication, and command processing. It integrates with the agent's
    chat interface to allow natural language interactions.
    """

    def __init__(
        self,
        agent_name: str,
        config: SSHConfig,
        chat_handler: Optional[Callable[[str], asyncio.Future]] = None
    ):
        """
        Initialize SSH server process.

        Args:
            agent_name: Name of the agent this server serves
            config: SSH server configuration
            chat_handler: Async function to process chat messages
        """
        self.agent_name = agent_name
        self.config = config
        self.chat_handler = chat_handler

        self._sessions: Dict[str, SSHSession] = {}
        self._server = None
        self._running = False
        self._started_at: Optional[datetime] = None
        self._statistics = SSHStatistics()

        # Command handlers for CLI-style commands
        self._cli_handlers: Dict[str, Callable] = {}
        self._setup_cli_handlers()

    def _setup_cli_handlers(self):
        """Setup CLI command handlers for vtysh-style commands"""
        self._cli_handlers = {
            "show": self._handle_show_command,
            "ping": self._handle_ping_command,
            "traceroute": self._handle_traceroute_command,
            "configure": self._handle_configure_command,
            "help": self._handle_help_command,
            "?": self._handle_help_command,
            "exit": self._handle_exit_command,
            "quit": self._handle_exit_command,
            "logout": self._handle_exit_command,
        }

    async def start(self) -> bool:
        """Start the SSH server"""
        if self._running:
            logger.warning(f"SSH server for {self.agent_name} already running")
            return False

        try:
            # Check if asyncssh is available
            try:
                import asyncssh
            except ImportError:
                logger.error("asyncssh not installed. Install with: pip install asyncssh")
                return False

            # Generate host key if not provided
            if not self.config.host_keys:
                key_path = f"/tmp/ssh_host_key_{self.agent_name}"
                if not os.path.exists(key_path):
                    key = asyncssh.generate_private_key('ssh-rsa', 2048)
                    key.write_private_key(key_path)
                    logger.info(f"Generated SSH host key at {key_path}")
                self.config.host_keys = [key_path]

            # Create SSH server
            self._server = await asyncssh.create_server(
                lambda: SSHServerProtocol(self),
                self.config.host,
                self.config.port,
                server_host_keys=self.config.host_keys,
                authorized_client_keys=self.config.authorized_keys_file,
                process_factory=self._create_process,
                login_timeout=self.config.login_timeout,
            )

            self._running = True
            self._started_at = datetime.now()

            logger.info(
                f"SSH server for {self.agent_name} started on "
                f"{self.config.host}:{self.config.port}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to start SSH server: {e}")
            return False

    async def stop(self):
        """Stop the SSH server"""
        if not self._running:
            return

        self._running = False

        # Close all active sessions
        for session_id in list(self._sessions.keys()):
            await self._close_session(session_id)

        # Close server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        logger.info(f"SSH server for {self.agent_name} stopped")

    def _create_process(self, process):
        """Factory for creating SSH process handlers"""
        return SSHProcessHandler(self, process)

    def validate_password(self, username: str, password: str) -> bool:
        """Validate username/password authentication"""
        if not self.config.password_auth:
            return False

        # Check against default credentials
        if username == self.config.default_username and password == self.config.default_password:
            return True

        # Could add support for additional users here
        return False

    def validate_public_key(self, username: str, key) -> bool:
        """Validate public key authentication"""
        if not self.config.public_key_auth:
            return False

        # Key validation is handled by asyncssh authorized_keys
        return True

    def create_session(
        self,
        username: str,
        remote_address: str,
        remote_port: int,
        auth_method: SSHAuthMethod,
        client_version: str = ""
    ) -> SSHSession:
        """Create a new SSH session"""
        if len(self._sessions) >= self.config.max_sessions:
            raise RuntimeError("Maximum sessions reached")

        session = SSHSession(
            session_id=str(uuid.uuid4())[:8],
            username=username,
            remote_address=remote_address,
            remote_port=remote_port,
            auth_method=auth_method,
            state=SSHSessionState.CONNECTED,
            connected_at=datetime.now(),
            last_activity=datetime.now(),
            client_version=client_version
        )

        self._sessions[session.session_id] = session
        self._statistics.total_connections += 1
        self._statistics.successful_logins += 1
        self._statistics.active_sessions = len(self._sessions)

        logger.info(
            f"SSH session {session.session_id} created for {username}@{remote_address}"
        )

        return session

    async def _close_session(self, session_id: str):
        """Close an SSH session"""
        if session_id in self._sessions:
            session = self._sessions[session_id]
            session.state = SSHSessionState.DISCONNECTED

            # Update statistics
            self._statistics.total_bytes_sent += session.bytes_sent
            self._statistics.total_bytes_received += session.bytes_received
            self._statistics.total_commands += session.commands_executed

            del self._sessions[session_id]
            self._statistics.active_sessions = len(self._sessions)

            logger.info(f"SSH session {session_id} closed")

    def get_session(self, session_id: str) -> Optional[SSHSession]:
        """Get a session by ID"""
        return self._sessions.get(session_id)

    def get_all_sessions(self) -> List[SSHSession]:
        """Get all active sessions"""
        return list(self._sessions.values())

    def get_statistics(self) -> SSHStatistics:
        """Get server statistics"""
        if self._started_at:
            self._statistics.uptime_seconds = (
                datetime.now() - self._started_at
            ).total_seconds()
        return self._statistics

    async def process_command(
        self,
        session: SSHSession,
        command: str
    ) -> Tuple[str, bool]:
        """
        Process a command from an SSH session.

        Args:
            session: The SSH session
            command: The command to process

        Returns:
            Tuple of (response_text, should_exit)
        """
        session.last_activity = datetime.now()
        session.commands_executed += 1
        command = command.strip()

        if not command:
            return "", False

        # Check for CLI commands first
        cmd_parts = command.split()
        cmd_name = cmd_parts[0].lower()

        if cmd_name in self._cli_handlers:
            return await self._cli_handlers[cmd_name](session, cmd_parts)

        # Otherwise, treat as natural language query to chat interface
        if self.chat_handler:
            try:
                response = await self.chat_handler(command)
                return response, False
            except Exception as e:
                logger.error(f"Chat handler error: {e}")
                return f"Error processing query: {e}", False
        else:
            return f"Unknown command: {cmd_name}. Type 'help' for available commands.", False

    async def _handle_show_command(
        self,
        session: SSHSession,
        cmd_parts: List[str]
    ) -> Tuple[str, bool]:
        """Handle 'show' commands"""
        if len(cmd_parts) < 2:
            return "Usage: show <command>\nAvailable: ip, version, session, help", False

        subcmd = cmd_parts[1].lower()

        if subcmd == "version":
            return f"ASI Agent: {self.agent_name}\nSSH Server Version: 1.0.0", False
        elif subcmd == "session":
            return (
                f"Session ID: {session.session_id}\n"
                f"Username: {session.username}\n"
                f"Connected: {session.connected_at.isoformat()}\n"
                f"Commands: {session.commands_executed}"
            ), False
        elif subcmd in ["ip", "route", "interface", "ospf", "bgp", "isis", "gre", "tunnel", "bfd"]:
            # Forward to chat handler for natural language processing
            if self.chat_handler:
                full_cmd = " ".join(cmd_parts)
                response = await self.chat_handler(f"show {full_cmd}")
                return response, False
            return f"show {subcmd} - forwarded to agent", False
        else:
            return f"Unknown show command: {subcmd}", False

    async def _handle_ping_command(
        self,
        session: SSHSession,
        cmd_parts: List[str]
    ) -> Tuple[str, bool]:
        """Handle 'ping' command"""
        if len(cmd_parts) < 2:
            return "Usage: ping <destination>", False

        destination = cmd_parts[1]

        # Forward to chat handler
        if self.chat_handler:
            response = await self.chat_handler(f"ping {destination}")
            return response, False

        return f"Pinging {destination}...", False

    async def _handle_traceroute_command(
        self,
        session: SSHSession,
        cmd_parts: List[str]
    ) -> Tuple[str, bool]:
        """Handle 'traceroute' command"""
        if len(cmd_parts) < 2:
            return "Usage: traceroute <destination>", False

        destination = cmd_parts[1]

        # Forward to chat handler
        if self.chat_handler:
            response = await self.chat_handler(f"traceroute {destination}")
            return response, False

        return f"Tracing route to {destination}...", False

    async def _handle_configure_command(
        self,
        session: SSHSession,
        cmd_parts: List[str]
    ) -> Tuple[str, bool]:
        """Handle 'configure' command"""
        if self.chat_handler:
            full_cmd = " ".join(cmd_parts)
            response = await self.chat_handler(full_cmd)
            return response, False

        return "Entering configuration mode...", False

    async def _handle_help_command(
        self,
        session: SSHSession,
        cmd_parts: List[str]
    ) -> Tuple[str, bool]:
        """Handle 'help' command"""
        help_text = f"""
Welcome to {self.agent_name} SSH Interface

Available Commands:
  show version      - Show agent version
  show session      - Show current session info
  show ip route     - Show IP routing table
  show ip ospf      - Show OSPF information
  show ip bgp       - Show BGP information

  ping <dest>       - Ping a destination
  traceroute <dest> - Trace route to destination

  help, ?           - Show this help
  exit, quit        - Exit SSH session

Natural Language:
  You can also type natural language queries:
  - "Why can't I reach 10.0.0.1?"
  - "What routes do I have to the BGP network?"
  - "Show me my OSPF neighbors"
"""
        return help_text.strip(), False

    async def _handle_exit_command(
        self,
        session: SSHSession,
        cmd_parts: List[str]
    ) -> Tuple[str, bool]:
        """Handle exit commands"""
        return "Goodbye!\n", True


class SSHServerProtocol:
    """AsyncSSH server protocol handler"""

    def __init__(self, server: SSHServerProcess):
        self.server = server

    def connection_made(self, conn):
        """Called when connection is established"""
        self._conn = conn

    def password_auth_supported(self):
        """Return whether password auth is supported"""
        return self.server.config.password_auth

    def validate_password(self, username: str, password: str) -> bool:
        """Validate password authentication"""
        result = self.server.validate_password(username, password)
        if not result:
            self.server._statistics.failed_auth_attempts += 1
        return result

    def public_key_auth_supported(self):
        """Return whether public key auth is supported"""
        return self.server.config.public_key_auth

    def validate_public_key(self, username: str, key) -> bool:
        """Validate public key authentication"""
        return self.server.validate_public_key(username, key)

    def begin_auth(self, username: str):
        """Handle authentication start"""
        return True  # Allow authentication attempt


class SSHProcessHandler:
    """Handler for SSH process/shell sessions"""

    def __init__(self, server: SSHServerProcess, process):
        self.server = server
        self.process = process
        self.session: Optional[SSHSession] = None

    async def __call__(self, stdin, stdout, stderr):
        """Main process handler"""
        try:
            # Get connection info
            conn = self.process.get_extra_info('connection')
            peername = conn.get_extra_info('peername')
            remote_addr = peername[0] if peername else "unknown"
            remote_port = peername[1] if peername and len(peername) > 1 else 0

            # Create session
            self.session = self.server.create_session(
                username=self.process.get_extra_info('username', 'unknown'),
                remote_address=remote_addr,
                remote_port=remote_port,
                auth_method=SSHAuthMethod.PASSWORD,  # Could detect actual method
                client_version=""
            )

            # Send banner
            banner = self.server.config.banner or self._default_banner()
            stdout.write(banner)

            # Main command loop
            while True:
                # Send prompt
                prompt = f"{self.server.agent_name}> "
                stdout.write(prompt)

                # Read command
                try:
                    line = await stdin.readline()
                    if not line:
                        break

                    command = line.rstrip('\r\n')
                    self.session.bytes_received += len(line)

                    # Process command
                    response, should_exit = await self.server.process_command(
                        self.session, command
                    )

                    if response:
                        stdout.write(response + "\n")
                        self.session.bytes_sent += len(response) + 1

                    if should_exit:
                        break

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    stdout.write(f"Error: {e}\n")

        finally:
            # Cleanup session
            if self.session:
                await self.server._close_session(self.session.session_id)

    def _default_banner(self) -> str:
        """Generate default SSH banner"""
        return f"""
================================================================================
  ASI Agent: {self.server.agent_name}

  Welcome to the Agent SSH Interface.
  Type 'help' or '?' for available commands.
  You can also use natural language queries.
================================================================================

"""


class SSHServer:
    """
    High-level SSH Server manager for ASI agents.

    This class provides a simple interface to create and manage
    SSH servers for agents.
    """

    def __init__(
        self,
        agent_name: str,
        config: Optional[SSHConfig] = None,
        chat_handler: Optional[Callable[[str], asyncio.Future]] = None
    ):
        """
        Initialize SSH server.

        Args:
            agent_name: Name of the agent
            config: SSH configuration (uses defaults if not provided)
            chat_handler: Async function to handle chat messages
        """
        self.agent_name = agent_name
        self.config = config or SSHConfig()
        self._process = SSHServerProcess(agent_name, self.config, chat_handler)

    async def start(self) -> bool:
        """Start the SSH server"""
        return await self._process.start()

    async def stop(self):
        """Stop the SSH server"""
        await self._process.stop()

    @property
    def running(self) -> bool:
        """Check if server is running"""
        return self._process._running

    def get_statistics(self) -> Dict[str, Any]:
        """Get server statistics"""
        return self._process.get_statistics().to_dict()

    def get_sessions(self) -> List[Dict[str, Any]]:
        """Get all active sessions"""
        return [s.to_dict() for s in self._process.get_all_sessions()]

    def get_config(self) -> Dict[str, Any]:
        """Get server configuration"""
        return self.config.to_dict()


# Global SSH server instances (one per agent)
_ssh_servers: Dict[str, SSHServer] = {}


def get_ssh_server(agent_name: str) -> Optional[SSHServer]:
    """Get SSH server for an agent"""
    return _ssh_servers.get(agent_name)


async def start_ssh_server(
    agent_name: str,
    port: int = 2200,
    chat_handler: Optional[Callable[[str], asyncio.Future]] = None,
    **config_kwargs
) -> SSHServer:
    """
    Start SSH server for an agent.

    Args:
        agent_name: Name of the agent
        port: SSH port number
        chat_handler: Async function to handle chat messages
        **config_kwargs: Additional SSHConfig parameters

    Returns:
        SSHServer instance
    """
    if agent_name in _ssh_servers:
        return _ssh_servers[agent_name]

    config = SSHConfig(port=port, **config_kwargs)
    server = SSHServer(agent_name, config, chat_handler)

    if await server.start():
        _ssh_servers[agent_name] = server
        logger.info(f"SSH server started for {agent_name} on port {port}")
    else:
        raise RuntimeError(f"Failed to start SSH server for {agent_name}")

    return server


async def stop_ssh_server(agent_name: str):
    """Stop SSH server for an agent"""
    if agent_name in _ssh_servers:
        server = _ssh_servers.pop(agent_name)
        await server.stop()
        logger.info(f"SSH server stopped for {agent_name}")


def get_ssh_statistics(agent_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Get SSH statistics.

    Args:
        agent_name: Get stats for specific agent, or all if None

    Returns:
        Statistics dictionary
    """
    if agent_name:
        server = _ssh_servers.get(agent_name)
        if server:
            return server.get_statistics()
        return {}

    # Return stats for all servers
    return {
        name: server.get_statistics()
        for name, server in _ssh_servers.items()
    }


def list_active_sessions(agent_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List active SSH sessions.

    Args:
        agent_name: Get sessions for specific agent, or all if None

    Returns:
        List of session dictionaries
    """
    if agent_name:
        server = _ssh_servers.get(agent_name)
        if server:
            return server.get_sessions()
        return []

    # Return sessions for all servers
    all_sessions = []
    for name, server in _ssh_servers.items():
        sessions = server.get_sessions()
        for session in sessions:
            session["agent_name"] = name
        all_sessions.extend(sessions)
    return all_sessions
