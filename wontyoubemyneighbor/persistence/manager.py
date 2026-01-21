"""
Persistence Manager

High-level persistence API for agents and networks.
Provides convenient functions for common operations.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

from toon.models import (
    TOONAgent, TOONNetwork, TOONInterface, TOONProtocolConfig,
    TOONMCPConfig, TOONRuntimeState, TOONTopology, TOONDockerConfig
)
from .storage import AgentStore, NetworkStore, get_default_storage_path, ensure_storage_dirs


class PersistenceManager:
    """
    Unified persistence manager for all storage operations

    Manages both agents and networks through a single interface.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize persistence manager

        Args:
            storage_path: Base storage path (default: ~/.rubberband/storage)
        """
        self.storage_path = storage_path or get_default_storage_path()
        ensure_storage_dirs(self.storage_path)

        self.agents = AgentStore(self.storage_path)
        self.networks = NetworkStore(self.storage_path)

    # Agent operations

    def save_agent(self, agent: TOONAgent, backup: bool = True) -> Path:
        """Save agent to storage"""
        return self.agents.save(agent, backup)

    def load_agent(self, agent_id: str) -> Optional[TOONAgent]:
        """Load agent from storage"""
        return self.agents.load(agent_id)

    def delete_agent(self, agent_id: str, backup: bool = True) -> bool:
        """Delete agent from storage"""
        return self.agents.delete(agent_id, backup)

    def list_agents(self) -> List[Dict[str, Any]]:
        """List all saved agents"""
        return self.agents.list()

    def agent_exists(self, agent_id: str) -> bool:
        """Check if agent exists"""
        return self.agents.exists(agent_id)

    # Network operations

    def save_network(self, network: TOONNetwork, backup: bool = True) -> Path:
        """Save network to storage"""
        return self.networks.save(network, backup)

    def load_network(self, network_id: str) -> Optional[TOONNetwork]:
        """Load network from storage"""
        return self.networks.load(network_id)

    def delete_network(self, network_id: str, backup: bool = True) -> bool:
        """Delete network from storage"""
        return self.networks.delete(network_id, backup)

    def list_networks(self) -> List[Dict[str, Any]]:
        """List all saved networks"""
        return self.networks.list()

    def network_exists(self, network_id: str) -> bool:
        """Check if network exists"""
        return self.networks.exists(network_id)

    # Cross-store operations

    def export_agent_from_network(self, network_id: str, agent_id: str) -> Optional[Path]:
        """Export an agent from a network to the agent library"""
        return self.networks.export_agent(network_id, agent_id, self.agents)

    def import_agent_to_network(self, network_id: str, agent_id: str) -> bool:
        """Import an agent from the agent library into a network"""
        return self.networks.import_agent(network_id, agent_id, self.agents)

    def clone_agent(self, source_id: str, new_id: str, new_name: Optional[str] = None) -> Optional[TOONAgent]:
        """
        Clone an existing agent with a new ID

        Args:
            source_id: Source agent ID
            new_id: New agent ID
            new_name: New name (optional, defaults to source name + " (Copy)")

        Returns:
            Cloned agent or None if source not found
        """
        source = self.load_agent(source_id)
        if not source:
            return None

        # Create clone with new ID
        clone_data = source.to_dict()
        clone_data["id"] = new_id
        clone_data["n"] = new_name or f"{source.n} (Copy)"
        clone_data["meta"]["cloned_from"] = source_id
        clone_data["meta"]["cloned_at"] = datetime.now().isoformat()

        # Remove runtime state from clone
        clone_data.pop("state", None)

        clone = TOONAgent.from_dict(clone_data)
        self.save_agent(clone)

        return clone

    def clone_network(self, source_id: str, new_id: str, new_name: Optional[str] = None) -> Optional[TOONNetwork]:
        """
        Clone an existing network with a new ID

        Args:
            source_id: Source network ID
            new_id: New network ID
            new_name: New name (optional)

        Returns:
            Cloned network or None if source not found
        """
        source = self.load_network(source_id)
        if not source:
            return None

        # Create clone with new ID
        clone_data = source.to_dict()
        clone_data["id"] = new_id
        clone_data["n"] = new_name or f"{source.n} (Copy)"
        clone_data["created"] = datetime.now().isoformat()
        clone_data["modified"] = datetime.now().isoformat()
        clone_data["meta"]["cloned_from"] = source_id

        # Update agent IDs to be unique in the new network
        for agent_data in clone_data.get("agents", []):
            old_id = agent_data["id"]
            agent_data["id"] = f"{new_id}-{old_id}"
            agent_data.pop("state", None)  # Remove runtime state

        # Update topology link references
        if clone_data.get("topo") and clone_data["topo"].get("links"):
            for link in clone_data["topo"]["links"]:
                link["a1"] = f"{new_id}-{link['a1']}"
                link["a2"] = f"{new_id}-{link['a2']}"

        clone = TOONNetwork.from_dict(clone_data)
        self.save_network(clone)

        return clone

    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics

        Returns:
            Dict with storage stats
        """
        agents = self.list_agents()
        networks = self.list_networks()

        total_size = 0
        for agent in agents:
            if "file" in agent and Path(agent["file"]).exists():
                total_size += Path(agent["file"]).stat().st_size
        for network in networks:
            if "file" in network and Path(network["file"]).exists():
                total_size += Path(network["file"]).stat().st_size

        return {
            "storage_path": str(self.storage_path),
            "agent_count": len(agents),
            "network_count": len(networks),
            "total_size_bytes": total_size,
            "total_size_kb": round(total_size / 1024, 2)
        }


# Module-level convenience functions using default manager
_default_manager: Optional[PersistenceManager] = None


def get_manager() -> PersistenceManager:
    """Get or create default persistence manager"""
    global _default_manager
    if _default_manager is None:
        _default_manager = PersistenceManager()
    return _default_manager


def save_agent(agent: TOONAgent, backup: bool = True) -> Path:
    """Save agent using default manager"""
    return get_manager().save_agent(agent, backup)


def load_agent(agent_id: str) -> Optional[TOONAgent]:
    """Load agent using default manager"""
    return get_manager().load_agent(agent_id)


def delete_agent(agent_id: str, backup: bool = True) -> bool:
    """Delete agent using default manager"""
    return get_manager().delete_agent(agent_id, backup)


def list_agents() -> List[Dict[str, Any]]:
    """List agents using default manager"""
    return get_manager().list_agents()


def save_network(network: TOONNetwork, backup: bool = True) -> Path:
    """Save network using default manager"""
    return get_manager().save_network(network, backup)


def load_network(network_id: str) -> Optional[TOONNetwork]:
    """Load network using default manager"""
    return get_manager().load_network(network_id)


def delete_network(network_id: str, backup: bool = True) -> bool:
    """Delete network using default manager"""
    return get_manager().delete_network(network_id, backup)


def list_networks() -> List[Dict[str, Any]]:
    """List networks using default manager"""
    return get_manager().list_networks()


# Utility functions for state capture

def capture_agent_state(
    agent: TOONAgent,
    ospf_data: Optional[Dict] = None,
    bgp_data: Optional[Dict] = None
) -> TOONAgent:
    """
    Capture current runtime state for an agent

    Args:
        agent: Agent to update
        ospf_data: OSPF state data (neighbors, LSDB, routes)
        bgp_data: BGP state data (peers, RIB)

    Returns:
        Agent with updated state
    """
    state = TOONRuntimeState.capture_now()

    if ospf_data:
        state.nbrs = ospf_data.get("neighbors", [])
        state.lsdb = ospf_data.get("lsdb", [])
        if ospf_data.get("routes"):
            state.rib.extend([
                {"protocol": "ospf", **r} for r in ospf_data["routes"]
            ])

    if bgp_data:
        state.peers = bgp_data.get("peers", [])
        if bgp_data.get("routes"):
            state.rib.extend([
                {"protocol": "bgp", **r} for r in bgp_data["routes"]
            ])

    agent.state = state
    return agent


def create_default_mcps() -> List[TOONMCPConfig]:
    """
    Create default MCP configurations

    Returns:
        List of default MCP configs
    """
    return [
        TOONMCPConfig(
            id="gait",
            t="gait",
            n="GAIT",
            d="AI session tracking and context management",
            url="https://github.com/automateyournetwork/gait_mcp",
            c={
                "tracking": True,
                "_config_fields": [],  # No additional config needed
                "_requires_config": False
            },
            e=True
        ),
        TOONMCPConfig(
            id="markmap",
            t="markmap",
            n="Markmap",
            d="Network topology visualization as mind maps",
            url="https://github.com/automateyournetwork/markmap_mcp",
            c={
                "refresh_interval": 1,
                "_config_fields": [],  # No additional config needed
                "_requires_config": False
            },
            e=True
        ),
        TOONMCPConfig(
            id="pyats",
            t="pyats",
            n="pyATS",
            d="Cisco pyATS network testing and validation (runs locally on agent)",
            url="https://github.com/automateyournetwork/pyATS_MCP",
            c={
                "auto_test": True,
                "_config_fields": [],  # No config needed - runs locally on agent
                "_requires_config": False
            },
            e=True
        ),
        TOONMCPConfig(
            id="servicenow",
            t="servicenow",
            n="ServiceNow",
            d="ITSM integration for incident management",
            url="https://github.com/echelon-ai-labs/servicenow-mcp",
            c={
                "auto_ticket": False,
                "_config_fields": [
                    {"id": "instance_url", "label": "Instance URL", "type": "url", "placeholder": "https://your-instance.service-now.com", "required": True, "hint": "Your ServiceNow instance URL"},
                    {"id": "username", "label": "Username", "type": "text", "placeholder": "admin", "required": True, "hint": "ServiceNow username"},
                    {"id": "password", "label": "Password", "type": "password", "placeholder": "", "required": True, "hint": "ServiceNow password"}
                ],
                "_requires_config": True
            },
            e=False  # Disabled by default - needs config
        ),
        TOONMCPConfig(
            id="netbox",
            t="netbox",
            n="NetBox",
            d="Network source of truth (DCIM/IPAM)",
            url="https://github.com/netboxlabs/netbox-mcp-server",
            c={
                "_config_fields": [
                    {"id": "netbox_url", "label": "NetBox URL", "type": "url", "placeholder": "https://netbox.example.com", "required": True, "hint": "Your NetBox instance URL"},
                    {"id": "api_token", "label": "API Token", "type": "password", "placeholder": "", "required": True, "hint": "NetBox API token (Admin > API Tokens)"}
                ],
                "_requires_config": True
            },
            e=False  # Disabled by default - needs config
        ),
        TOONMCPConfig(
            id="rfc",
            t="rfc",
            n="RFC",
            d="IETF RFC standards reference and lookup",
            url="https://github.com/mjpitz/mcp-rfc",
            c={
                "_config_fields": [],  # No additional config needed
                "_requires_config": False
            },
            e=True
        ),
        TOONMCPConfig(
            id="slack",
            t="slack",
            n="Slack",
            d="Team notifications and collaboration",
            url="https://docs.slack.dev/ai/mcp-server/",
            c={
                "_config_fields": [
                    {"id": "bot_token", "label": "Bot Token", "type": "password", "placeholder": "xoxb-...", "required": True, "hint": "Slack Bot OAuth Token (starts with xoxb-)"},
                    {"id": "default_channel", "label": "Default Channel", "type": "text", "placeholder": "#network-alerts", "required": False, "hint": "Optional: Default channel for notifications"}
                ],
                "_requires_config": True
            },
            e=False  # Disabled by default - needs config
        ),
        TOONMCPConfig(
            id="github",
            t="github",
            n="GitHub",
            d="Version control and repository management",
            url="https://github.com/github/github-mcp-server",
            c={
                "_config_fields": [
                    {"id": "personal_access_token", "label": "Personal Access Token", "type": "password", "placeholder": "ghp_...", "required": True, "hint": "GitHub PAT with repo access (Settings > Developer settings > PAT)"},
                    {"id": "default_repo", "label": "Default Repository", "type": "text", "placeholder": "owner/repo", "required": False, "hint": "Optional: Default repository (owner/repo format)"}
                ],
                "_requires_config": True
            },
            e=False  # Disabled by default - needs config
        )
    ]


def create_agent_template(
    agent_id: str,
    name: str,
    router_id: str,
    protocol: str = "ospf",
    include_mcps: bool = True
) -> TOONAgent:
    """
    Create a new agent from template

    Args:
        agent_id: Agent identifier
        name: Display name
        router_id: Router ID
        protocol: Primary protocol (ospf, ibgp, ebgp)
        include_mcps: Include default MCPs

    Returns:
        New TOONAgent
    """
    # Create default interface
    interfaces = [
        TOONInterface(
            id="eth0",
            n="eth0",
            t="eth",
            a=[],  # Will be configured later
            s="up"
        ),
        TOONInterface(
            id="lo0",
            n="lo0",
            t="lo",
            a=[f"{router_id}/32"],
            s="up"
        )
    ]

    # Create protocol config
    protos = []
    if protocol in ["ospf", "ospfv3"]:
        protos.append(TOONProtocolConfig(
            p=protocol,
            r=router_id,
            a="0.0.0.0"
        ))
    elif protocol in ["ibgp", "ebgp"]:
        protos.append(TOONProtocolConfig(
            p=protocol,
            r=router_id,
            asn=65001 if protocol == "ibgp" else 65002
        ))

    return TOONAgent(
        id=agent_id,
        n=name,
        r=router_id,
        ifs=interfaces,
        protos=protos,
        mcps=create_default_mcps() if include_mcps else [],
        meta={"template": True, "created": datetime.now().isoformat()}
    )


def create_network_template(
    network_id: str,
    name: str,
    subnet: str = "172.20.0.0/16",
    agent_count: int = 2
) -> TOONNetwork:
    """
    Create a new network from template

    Args:
        network_id: Network identifier
        name: Display name
        subnet: Docker network subnet
        agent_count: Number of agents to create

    Returns:
        New TOONNetwork
    """
    # Create Docker config
    docker = TOONDockerConfig(
        n=network_id,
        driver="bridge",
        subnet=subnet
    )

    # Create agents
    agents = []
    links = []

    for i in range(agent_count):
        agent_id = f"r{i+1}"
        router_id = f"10.0.0.{i+1}"
        ip_addr = f"172.20.0.{i+2}/24"

        agent = create_agent_template(
            agent_id=agent_id,
            name=f"Router {i+1}",
            router_id=router_id,
            protocol="ospf"
        )
        # Set interface IP
        agent.ifs[0].a = [ip_addr]

        agents.append(agent)

        # Create links between adjacent agents
        if i > 0:
            links.append({
                "id": f"link-{i}",
                "a1": f"r{i}",
                "i1": "eth0",
                "a2": f"r{i+1}",
                "i2": "eth0"
            })

    # Create topology
    from toon.models import TOONLink
    topo = TOONTopology(
        links=[TOONLink.from_dict(l) for l in links]
    )

    return TOONNetwork(
        id=network_id,
        n=name,
        docker=docker,
        agents=agents,
        topo=topo,
        mcps=create_default_mcps(),
        meta={"template": True}
    )
