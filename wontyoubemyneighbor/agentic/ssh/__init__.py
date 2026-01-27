"""
SSH Server Module for ASI Agents

Provides SSH access to agent chat interfaces, allowing users to connect
via SSH and interact with agents using natural language commands.

Features:
- SSH server per agent with configurable ports
- Key-based and password authentication
- Integration with agent chat/LLM interface
- Session logging via GAIT
- Support for vtysh-style CLI commands
- Natural language query support

Usage:
    from agentic.ssh import SSHServer, SSHConfig, start_ssh_server

    # Create and start SSH server for an agent
    config = SSHConfig(
        port=2201,
        host_keys=["/path/to/host_key"],
        authorized_keys=["/path/to/authorized_keys"]
    )
    server = SSHServer(agent_name="router-1", config=config)
    await server.start()
"""

from .ssh_server import (
    SSHServer,
    SSHConfig,
    SSHSession,
    SSHAuthMethod,
    SSHSessionState,
    get_ssh_server,
    start_ssh_server,
    stop_ssh_server,
    get_ssh_statistics,
    list_active_sessions,
)

__all__ = [
    "SSHServer",
    "SSHConfig",
    "SSHSession",
    "SSHAuthMethod",
    "SSHSessionState",
    "get_ssh_server",
    "start_ssh_server",
    "stop_ssh_server",
    "get_ssh_statistics",
    "list_active_sessions",
]
