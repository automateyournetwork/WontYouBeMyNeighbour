"""
Orchestrator Module for Multi-Agent Network Management

Provides Docker-based orchestration for:
- Agent container creation and lifecycle
- Network creation and configuration
- Health monitoring and status tracking
- Container cleanup and recovery
"""

from .docker_manager import (
    DockerManager,
    DockerNotAvailableError,
    ContainerInfo,
    NetworkInfo,
    check_docker_available,
    get_docker_client
)

from .agent_launcher import (
    AgentLauncher,
    AgentContainer,
    launch_agent,
    stop_agent,
    get_agent_status,
    get_agent_logs
)

from .network_orchestrator import (
    NetworkOrchestrator,
    launch_network,
    stop_network,
    get_network_status
)

__all__ = [
    "DockerManager",
    "DockerNotAvailableError",
    "ContainerInfo",
    "NetworkInfo",
    "check_docker_available",
    "get_docker_client",
    "AgentLauncher",
    "AgentContainer",
    "launch_agent",
    "stop_agent",
    "get_agent_status",
    "get_agent_logs",
    "NetworkOrchestrator",
    "launch_network",
    "stop_network",
    "get_network_status"
]
