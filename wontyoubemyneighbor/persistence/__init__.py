"""
Persistence Module for Won't You Be My Neighbor

Provides file-based persistence for:
- Agent configurations and runtime state
- Network definitions and topologies
- TOON file management
"""

from .storage import (
    AgentStore,
    NetworkStore,
    get_default_storage_path,
    ensure_storage_dirs
)

from .manager import (
    PersistenceManager,
    save_agent,
    load_agent,
    save_network,
    load_network,
    list_agents,
    list_networks,
    delete_agent,
    delete_network
)

__all__ = [
    "AgentStore",
    "NetworkStore",
    "get_default_storage_path",
    "ensure_storage_dirs",
    "PersistenceManager",
    "save_agent",
    "load_agent",
    "save_network",
    "load_network",
    "list_agents",
    "list_networks",
    "delete_agent",
    "delete_network"
]
