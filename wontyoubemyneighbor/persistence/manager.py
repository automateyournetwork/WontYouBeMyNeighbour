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
            storage_path: Base storage path (default: ~/.asi/storage)
        """
        self.storage_path = storage_path or get_default_storage_path()
        ensure_storage_dirs(self.storage_path)

        self.agents = AgentStore(self.storage_path)
        self.networks = NetworkStore(self.storage_path)

    # Agent operations

    def save_agent(self, agent: TOONAgent, backup: bool = True, enforce_mcps: bool = True) -> Path:
        """
        Save agent to storage

        Args:
            agent: Agent to save
            backup: Whether to create backup if file exists
            enforce_mcps: Whether to ensure mandatory MCPs are present (default: True)

        Returns:
            Path to saved file
        """
        if enforce_mcps:
            agent = ensure_mandatory_mcps(agent)
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


def save_agent(agent: TOONAgent, backup: bool = True, enforce_mcps: bool = True) -> Path:
    """Save agent using default manager (enforces mandatory MCPs by default)"""
    return get_manager().save_agent(agent, backup, enforce_mcps)


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


# Mandatory MCPs per spec (Quality Gate 2)
MANDATORY_MCP_TYPES = {"gait", "pyats", "rfc", "markmap", "prometheus", "grafana"}


def get_mandatory_mcps() -> List[TOONMCPConfig]:
    """
    Get the 4 mandatory MCPs that every agent must have.

    Per spec:
    - GAIT: Conversation tracking with audit UI
    - pyATS: Self-testing with AETest
    - RFC: Protocol knowledge base
    - Markmap: Real-time mind maps of agent state

    Returns:
        List of mandatory MCP configs (all enabled)
    """
    all_mcps = create_default_mcps()
    return [mcp for mcp in all_mcps if mcp.t in MANDATORY_MCP_TYPES]


def ensure_mandatory_mcps(agent: 'TOONAgent') -> 'TOONAgent':
    """
    Ensure agent has all 4 mandatory MCPs.

    If any mandatory MCP is missing, it will be added.

    Args:
        agent: Agent to validate/update

    Returns:
        Agent with all mandatory MCPs
    """
    # Get existing MCP types
    existing_types = {mcp.t for mcp in agent.mcps} if agent.mcps else set()

    # Find missing mandatory MCPs
    missing = MANDATORY_MCP_TYPES - existing_types

    if missing:
        # Get mandatory MCPs and add the missing ones
        mandatory = get_mandatory_mcps()
        for mcp in mandatory:
            if mcp.t in missing:
                if agent.mcps is None:
                    agent.mcps = []
                agent.mcps.append(mcp)

    return agent


def validate_agent_mcps(agent: 'TOONAgent') -> Dict[str, Any]:
    """
    Validate that agent has all required MCPs.

    Args:
        agent: Agent to validate

    Returns:
        Validation result dict with 'valid', 'missing', and 'message' keys
    """
    existing_types = {mcp.t for mcp in agent.mcps} if agent.mcps else set()
    missing = MANDATORY_MCP_TYPES - existing_types

    if missing:
        return {
            "valid": False,
            "missing": list(missing),
            "message": f"Agent is missing mandatory MCPs: {', '.join(sorted(missing))}"
        }

    return {
        "valid": True,
        "missing": [],
        "message": "Agent has all mandatory MCPs"
    }


# Optional MCPs that require configuration
OPTIONAL_MCP_TYPES = {"servicenow", "netbox", "slack", "github", "smtp"}


def get_optional_mcps() -> List[TOONMCPConfig]:
    """
    Get optional MCPs that can be configured.

    Optional MCPs include:
    - ServiceNow: ITSM integration
    - NetBox: DCIM/IPAM
    - Slack: Team notifications
    - GitHub: Version control

    Returns:
        List of optional MCP configs (all disabled by default)
    """
    all_mcps = create_default_mcps()
    return [mcp for mcp in all_mcps if mcp.t in OPTIONAL_MCP_TYPES]


def get_mcp_config_fields(mcp_type: str) -> List[Dict[str, Any]]:
    """
    Get configuration fields required for an MCP.

    Args:
        mcp_type: MCP type (servicenow, netbox, slack, github)

    Returns:
        List of config field definitions
    """
    all_mcps = create_default_mcps()
    for mcp in all_mcps:
        if mcp.t == mcp_type:
            return mcp.c.get("_config_fields", [])
    return []


def configure_optional_mcp(
    agent: 'TOONAgent',
    mcp_type: str,
    config: Dict[str, Any],
    enable: bool = True
) -> 'TOONAgent':
    """
    Configure an optional MCP on an agent.

    Args:
        agent: Agent to configure
        mcp_type: MCP type (servicenow, netbox, slack, github)
        config: Configuration values (e.g., API keys, URLs)
        enable: Whether to enable the MCP

    Returns:
        Updated agent
    """
    if mcp_type not in OPTIONAL_MCP_TYPES:
        raise ValueError(f"Invalid optional MCP type: {mcp_type}. Valid types: {OPTIONAL_MCP_TYPES}")

    # Find or create the MCP config
    mcp_found = False
    if agent.mcps:
        for mcp in agent.mcps:
            if mcp.t == mcp_type:
                # Update existing MCP
                mcp.e = enable
                # Merge config (preserving internal fields)
                internal_fields = {k: v for k, v in mcp.c.items() if k.startswith("_")}
                mcp.c = {**config, **internal_fields}
                mcp_found = True
                break

    if not mcp_found:
        # Add new MCP from defaults
        optional_mcps = get_optional_mcps()
        for default_mcp in optional_mcps:
            if default_mcp.t == mcp_type:
                # Create new MCP with provided config
                internal_fields = {k: v for k, v in default_mcp.c.items() if k.startswith("_")}
                new_mcp = TOONMCPConfig(
                    id=default_mcp.id,
                    t=default_mcp.t,
                    n=default_mcp.n,
                    d=default_mcp.d,
                    url=default_mcp.url,
                    c={**config, **internal_fields},
                    e=enable
                )
                if agent.mcps is None:
                    agent.mcps = []
                agent.mcps.append(new_mcp)
                break

    return agent


def enable_optional_mcp(agent: 'TOONAgent', mcp_type: str) -> 'TOONAgent':
    """
    Enable an optional MCP on an agent (if already configured).

    Args:
        agent: Agent to update
        mcp_type: MCP type to enable

    Returns:
        Updated agent
    """
    if agent.mcps:
        for mcp in agent.mcps:
            if mcp.t == mcp_type:
                mcp.e = True
                break
    return agent


def disable_optional_mcp(agent: 'TOONAgent', mcp_type: str) -> 'TOONAgent':
    """
    Disable an optional MCP on an agent.

    Args:
        agent: Agent to update
        mcp_type: MCP type to disable

    Returns:
        Updated agent
    """
    if agent.mcps:
        for mcp in agent.mcps:
            if mcp.t == mcp_type:
                mcp.e = False
                break
    return agent


def get_agent_mcp_status(agent: 'TOONAgent') -> Dict[str, Any]:
    """
    Get MCP status for an agent.

    Returns summary of mandatory and optional MCPs with their status.

    Args:
        agent: Agent to check

    Returns:
        Dictionary with MCP status information
    """
    mandatory_status = []
    optional_status = []

    if agent.mcps:
        for mcp in agent.mcps:
            status = {
                "id": mcp.id,
                "type": mcp.t,
                "name": mcp.n,
                "enabled": mcp.e,
                "requires_config": mcp.c.get("_requires_config", False),
                "has_config": bool({k: v for k, v in mcp.c.items() if not k.startswith("_")})
            }
            if mcp.t in MANDATORY_MCP_TYPES:
                mandatory_status.append(status)
            elif mcp.t in OPTIONAL_MCP_TYPES:
                optional_status.append(status)

    # Check for missing mandatory MCPs
    existing_mandatory = {s["type"] for s in mandatory_status}
    missing_mandatory = MANDATORY_MCP_TYPES - existing_mandatory

    return {
        "mandatory": {
            "complete": len(missing_mandatory) == 0,
            "missing": list(missing_mandatory),
            "mcps": mandatory_status
        },
        "optional": {
            "configured": [s for s in optional_status if s["has_config"]],
            "available": list(OPTIONAL_MCP_TYPES),
            "mcps": optional_status
        },
        "total_enabled": sum(1 for m in agent.mcps if m.e) if agent.mcps else 0,
        "total_configured": len(agent.mcps) if agent.mcps else 0
    }


# =============================================================================
# Custom MCP Import Functions (Quality Gate 9)
# =============================================================================

def validate_custom_mcp_json(json_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate custom MCP JSON structure.

    Expected JSON format:
    {
        "id": "my-custom-mcp",
        "name": "My Custom MCP",
        "description": "Description of the MCP",
        "url": "https://github.com/org/mcp-server",
        "config": {
            "key1": "value1",
            "key2": "value2"
        },
        "config_fields": [
            {"id": "field1", "label": "Field 1", "type": "text", "required": true},
            {"id": "field2", "label": "Field 2", "type": "password", "required": false}
        ],
        "enabled": true
    }

    Args:
        json_data: JSON data to validate

    Returns:
        Validation result with 'valid', 'errors', and 'normalized' keys
    """
    errors = []
    normalized = {}

    # Required fields
    if not json_data.get("id"):
        errors.append("Missing required field: 'id'")
    else:
        # Validate ID format (alphanumeric, hyphens, underscores)
        mcp_id = json_data["id"]
        if not isinstance(mcp_id, str) or not mcp_id.replace("-", "").replace("_", "").isalnum():
            errors.append("Invalid 'id': must be alphanumeric with hyphens/underscores only")
        else:
            normalized["id"] = mcp_id

    if not json_data.get("url"):
        errors.append("Missing required field: 'url'")
    else:
        url = json_data["url"]
        if not isinstance(url, str) or not (url.startswith("http://") or url.startswith("https://")):
            errors.append("Invalid 'url': must be a valid HTTP/HTTPS URL")
        else:
            normalized["url"] = url

    # Optional fields with defaults
    normalized["name"] = json_data.get("name", json_data.get("id", "Custom MCP"))
    normalized["description"] = json_data.get("description", "")

    # Validate config
    config = json_data.get("config", {})
    if not isinstance(config, dict):
        errors.append("Invalid 'config': must be a dictionary")
    else:
        normalized["config"] = config

    # Validate config_fields
    config_fields = json_data.get("config_fields", [])
    if not isinstance(config_fields, list):
        errors.append("Invalid 'config_fields': must be a list")
    else:
        validated_fields = []
        for i, field in enumerate(config_fields):
            if not isinstance(field, dict):
                errors.append(f"Invalid config_field at index {i}: must be a dictionary")
                continue
            if not field.get("id"):
                errors.append(f"Missing 'id' in config_field at index {i}")
                continue
            if not field.get("label"):
                errors.append(f"Missing 'label' in config_field at index {i}")
                continue
            validated_fields.append({
                "id": field["id"],
                "label": field["label"],
                "type": field.get("type", "text"),
                "required": field.get("required", False),
                "placeholder": field.get("placeholder", ""),
                "hint": field.get("hint", "")
            })
        normalized["config_fields"] = validated_fields

    # Enabled flag
    normalized["enabled"] = json_data.get("enabled", True)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "normalized": normalized if len(errors) == 0 else None
    }


def import_custom_mcp(json_data: Dict[str, Any]) -> TOONMCPConfig:
    """
    Import a custom MCP from JSON data.

    Args:
        json_data: Validated JSON data for custom MCP

    Returns:
        TOONMCPConfig for the custom MCP

    Raises:
        ValueError: If validation fails
    """
    validation = validate_custom_mcp_json(json_data)
    if not validation["valid"]:
        raise ValueError(f"Invalid custom MCP JSON: {'; '.join(validation['errors'])}")

    data = validation["normalized"]

    # Build config with internal fields
    config = data.get("config", {}).copy()
    config["_config_fields"] = data.get("config_fields", [])
    config["_requires_config"] = len(data.get("config_fields", [])) > 0
    config["_custom"] = True  # Mark as custom MCP

    return TOONMCPConfig(
        id=data["id"],
        t="custom",  # Custom MCPs have type "custom"
        n=data["name"],
        d=data["description"],
        url=data["url"],
        c=config,
        e=data["enabled"]
    )


def add_custom_mcp_to_agent(agent: 'TOONAgent', json_data: Dict[str, Any]) -> 'TOONAgent':
    """
    Add a custom MCP to an agent from JSON data.

    Args:
        agent: Agent to update
        json_data: Custom MCP JSON data

    Returns:
        Updated agent with custom MCP added

    Raises:
        ValueError: If validation fails or MCP already exists
    """
    custom_mcp = import_custom_mcp(json_data)

    # Check for duplicate ID
    if agent.mcps:
        for existing in agent.mcps:
            if existing.id == custom_mcp.id:
                raise ValueError(f"MCP with ID '{custom_mcp.id}' already exists on agent")
    else:
        agent.mcps = []

    agent.mcps.append(custom_mcp)
    return agent


def remove_custom_mcp_from_agent(agent: 'TOONAgent', mcp_id: str) -> 'TOONAgent':
    """
    Remove a custom MCP from an agent.

    Only custom MCPs can be removed. Mandatory MCPs cannot be removed.

    Args:
        agent: Agent to update
        mcp_id: ID of the custom MCP to remove

    Returns:
        Updated agent with custom MCP removed

    Raises:
        ValueError: If MCP is mandatory or not found
    """
    if not agent.mcps:
        raise ValueError(f"MCP '{mcp_id}' not found on agent")

    # Find the MCP
    found_mcp = None
    for mcp in agent.mcps:
        if mcp.id == mcp_id:
            found_mcp = mcp
            break

    if not found_mcp:
        raise ValueError(f"MCP '{mcp_id}' not found on agent")

    # Check if it's mandatory
    if found_mcp.t in MANDATORY_MCP_TYPES:
        raise ValueError(f"Cannot remove mandatory MCP '{mcp_id}' (type: {found_mcp.t})")

    # Remove the MCP
    agent.mcps = [m for m in agent.mcps if m.id != mcp_id]
    return agent


def list_custom_mcps(agent: 'TOONAgent') -> List[Dict[str, Any]]:
    """
    List all custom MCPs on an agent.

    Args:
        agent: Agent to check

    Returns:
        List of custom MCP information
    """
    custom_mcps = []
    if agent.mcps:
        for mcp in agent.mcps:
            if mcp.c.get("_custom", False) or mcp.t == "custom":
                custom_mcps.append({
                    "id": mcp.id,
                    "name": mcp.n,
                    "description": mcp.d,
                    "url": mcp.url,
                    "enabled": mcp.e,
                    "config_fields": mcp.c.get("_config_fields", []),
                    "has_config": bool({k: v for k, v in mcp.c.items() if not k.startswith("_")})
                })
    return custom_mcps


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
                    {"id": "api_token", "label": "API Token", "type": "password", "placeholder": "", "required": True, "hint": "NetBox API token (Admin > API Tokens)"},
                    {"id": "_separator_1", "type": "separator", "label": "Auto-Registration"},
                    {"id": "auto_register", "label": "Register Agent in NetBox", "type": "checkbox", "default": False, "hint": "Create device with interfaces, IPs, and protocol services in NetBox"},
                    {"id": "site_name", "label": "Site", "type": "text", "placeholder": "DC1", "required": False, "hint": "NetBox site name (required)", "depends_on": "auto_register"}
                ],
                "_requires_config": True,
                "_defaults": {
                    "manufacturer": "Agentic",
                    "device_type": "ASI Agent",
                    "platform": "ASI"
                }
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
        ),
        TOONMCPConfig(
            id="prometheus",
            t="prometheus",
            n="Prometheus",
            d="Agent metrics collection, visualization and alerting",
            url="https://github.com/pab1it0/prometheus-mcp-server",
            c={
                "auto_metrics": True,
                "_config_fields": [],  # Built-in metrics - no config needed
                "_requires_config": False
            },
            e=True  # Always enabled - provides agent metrics
        ),
        TOONMCPConfig(
            id="grafana",
            t="grafana",
            n="Grafana",
            d="Agent dashboard visualization and monitoring",
            url="https://github.com/grafana/mcp-grafana",
            c={
                "auto_dashboards": True,
                "_config_fields": [],  # Built-in dashboards - no config needed
                "_requires_config": False
            },
            e=True  # Always enabled - provides agent dashboards
        ),
        TOONMCPConfig(
            id="smtp",
            t="smtp",
            n="SMTP Email",
            d="Send email notifications and reports via SMTP",
            url="",  # Built-in capability
            c={
                "_config_fields": [
                    {"id": "smtp_server", "label": "SMTP Server", "type": "text", "placeholder": "smtp.gmail.com", "required": True, "hint": "SMTP server hostname"},
                    {"id": "smtp_port", "label": "SMTP Port", "type": "number", "placeholder": "587", "required": True, "hint": "587 for TLS, 465 for SSL"},
                    {"id": "smtp_username", "label": "Gmail Address", "type": "email", "placeholder": "", "required": True, "hint": "MUST match the account used to generate the App Password below"},
                    {"id": "smtp_password", "label": "App Password", "type": "password", "placeholder": "", "required": True, "hint": "16-character code from Google App Passwords (no spaces)"},
                    {"id": "smtp_use_tls", "label": "Use TLS", "type": "checkbox", "default": True, "required": False, "hint": "Recommended for port 587"}
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
