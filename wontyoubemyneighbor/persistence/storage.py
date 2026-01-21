"""
Storage Classes for TOON Persistence

Provides file-based storage backends for agents and networks.
Supports both individual files and directory-based organization.
"""

import os
import json
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from toon.models import TOONAgent, TOONNetwork
from toon.format import serialize, deserialize, save_to_file, load_from_file


def get_default_storage_path() -> Path:
    """
    Get the default storage path for TOON files

    Returns:
        Path to storage directory
    """
    # Check for environment variable first
    env_path = os.environ.get("ASI_STORAGE_PATH")
    if env_path:
        return Path(env_path)

    # Default to user's home directory
    home = Path.home()
    return home / ".asi" / "storage"


def ensure_storage_dirs(base_path: Optional[Path] = None) -> Dict[str, Path]:
    """
    Ensure storage directories exist

    Args:
        base_path: Base storage path (default: get_default_storage_path())

    Returns:
        Dict with paths for 'agents' and 'networks'
    """
    if base_path is None:
        base_path = get_default_storage_path()

    paths = {
        "agents": base_path / "saved_agents",
        "networks": base_path / "saved_networks",
        "backups": base_path / "backups"
    }

    for name, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)

    return paths


class AgentStore:
    """
    File-based storage for agent configurations

    Directory structure:
        saved_agents/
            agent_id.toon
            agent_id.toon.backup
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize agent store

        Args:
            storage_path: Path to agents directory
        """
        paths = ensure_storage_dirs(storage_path)
        self.path = paths["agents"]
        self.backup_path = paths["backups"]

    def save(self, agent: TOONAgent, backup: bool = True) -> Path:
        """
        Save agent to file

        Args:
            agent: Agent to save
            backup: Create backup of existing file

        Returns:
            Path to saved file
        """
        filename = f"{agent.id}.toon"
        filepath = self.path / filename

        # Create backup if file exists
        if backup and filepath.exists():
            backup_name = f"{agent.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.toon"
            shutil.copy(filepath, self.backup_path / backup_name)

        # Save agent
        save_to_file(agent, filepath)

        return filepath

    def load(self, agent_id: str) -> Optional[TOONAgent]:
        """
        Load agent from file

        Args:
            agent_id: Agent identifier

        Returns:
            TOONAgent or None if not found
        """
        filepath = self.path / f"{agent_id}.toon"

        if not filepath.exists():
            return None

        return load_from_file(filepath, TOONAgent)

    def delete(self, agent_id: str, backup: bool = True) -> bool:
        """
        Delete agent file

        Args:
            agent_id: Agent identifier
            backup: Move to backup instead of delete

        Returns:
            True if deleted
        """
        filepath = self.path / f"{agent_id}.toon"

        if not filepath.exists():
            return False

        if backup:
            backup_name = f"{agent_id}_deleted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.toon"
            shutil.move(filepath, self.backup_path / backup_name)
        else:
            filepath.unlink()

        return True

    def list(self) -> List[Dict[str, Any]]:
        """
        List all saved agents

        Returns:
            List of agent metadata dicts
        """
        agents = []

        for filepath in self.path.glob("*.toon"):
            try:
                agent = load_from_file(filepath, TOONAgent)
                agents.append({
                    "id": agent.id,
                    "name": agent.n,
                    "router_id": agent.r,
                    "version": agent.v,
                    "protocols": [p.p for p in agent.protos],
                    "interfaces": len(agent.ifs),
                    "mcps": len(agent.mcps),
                    "file": str(filepath),
                    "modified": datetime.fromtimestamp(filepath.stat().st_mtime).isoformat()
                })
            except Exception as e:
                agents.append({
                    "id": filepath.stem,
                    "error": str(e),
                    "file": str(filepath)
                })

        return agents

    def exists(self, agent_id: str) -> bool:
        """Check if agent exists"""
        return (self.path / f"{agent_id}.toon").exists()

    def get_backups(self, agent_id: str) -> List[Path]:
        """Get list of backup files for an agent"""
        return list(self.backup_path.glob(f"{agent_id}_*.toon"))


class NetworkStore:
    """
    File-based storage for network configurations

    Directory structure:
        saved_networks/
            network_id.toon
            network_id.toon.backup
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize network store

        Args:
            storage_path: Path to networks directory
        """
        paths = ensure_storage_dirs(storage_path)
        self.path = paths["networks"]
        self.backup_path = paths["backups"]

    def save(self, network: TOONNetwork, backup: bool = True) -> Path:
        """
        Save network to file

        Args:
            network: Network to save
            backup: Create backup of existing file

        Returns:
            Path to saved file
        """
        # Update modified timestamp
        network.update_modified()

        filename = f"{network.id}.toon"
        filepath = self.path / filename

        # Create backup if file exists
        if backup and filepath.exists():
            backup_name = f"{network.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.toon"
            shutil.copy(filepath, self.backup_path / backup_name)

        # Save network
        save_to_file(network, filepath)

        return filepath

    def load(self, network_id: str) -> Optional[TOONNetwork]:
        """
        Load network from file

        Args:
            network_id: Network identifier

        Returns:
            TOONNetwork or None if not found
        """
        filepath = self.path / f"{network_id}.toon"

        if not filepath.exists():
            return None

        return load_from_file(filepath, TOONNetwork)

    def delete(self, network_id: str, backup: bool = True) -> bool:
        """
        Delete network file

        Args:
            network_id: Network identifier
            backup: Move to backup instead of delete

        Returns:
            True if deleted
        """
        filepath = self.path / f"{network_id}.toon"

        if not filepath.exists():
            return False

        if backup:
            backup_name = f"{network_id}_deleted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.toon"
            shutil.move(filepath, self.backup_path / backup_name)
        else:
            filepath.unlink()

        return True

    def list(self) -> List[Dict[str, Any]]:
        """
        List all saved networks

        Returns:
            List of network metadata dicts
        """
        networks = []

        for filepath in self.path.glob("*.toon"):
            try:
                network = load_from_file(filepath, TOONNetwork)
                networks.append({
                    "id": network.id,
                    "name": network.n,
                    "version": network.v,
                    "agents": len(network.agents),
                    "created": network.created,
                    "modified": network.modified,
                    "docker_network": network.docker.n if network.docker else None,
                    "file": str(filepath)
                })
            except Exception as e:
                networks.append({
                    "id": filepath.stem,
                    "error": str(e),
                    "file": str(filepath)
                })

        return networks

    def exists(self, network_id: str) -> bool:
        """Check if network exists"""
        return (self.path / f"{network_id}.toon").exists()

    def get_backups(self, network_id: str) -> List[Path]:
        """Get list of backup files for a network"""
        return list(self.backup_path.glob(f"{network_id}_*.toon"))

    def export_agent(self, network_id: str, agent_id: str, agent_store: AgentStore) -> Optional[Path]:
        """
        Export an agent from a network to the agent library

        Args:
            network_id: Network containing the agent
            agent_id: Agent to export
            agent_store: Destination agent store

        Returns:
            Path to exported agent file or None
        """
        network = self.load(network_id)
        if not network:
            return None

        agent = network.get_agent(agent_id)
        if not agent:
            return None

        return agent_store.save(agent)

    def import_agent(self, network_id: str, agent_id: str, agent_store: AgentStore) -> bool:
        """
        Import an agent from the agent library into a network

        Args:
            network_id: Target network
            agent_id: Agent to import
            agent_store: Source agent store

        Returns:
            True if successful
        """
        network = self.load(network_id)
        if not network:
            return False

        agent = agent_store.load(agent_id)
        if not agent:
            return False

        network.add_agent(agent)
        self.save(network)

        return True
