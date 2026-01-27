"""
Network Builder Wizard API

FastAPI endpoints for the multi-step network builder wizard:
- Step 1: Docker Network Configuration
- Step 2: MCP Server Selection
- Step 3: Agent Builder
- Step 4: Network Type & Configuration
- Step 5: Topology & Links
- Step 6: LLM Provider Configuration
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import asyncio
import signal
import os

from toon.models import (
    TOONNetwork, TOONAgent, TOONInterface, TOONProtocolConfig,
    TOONMCPConfig, TOONTopology, TOONLink, TOONDockerConfig
)
from persistence.manager import (
    PersistenceManager, list_agents, list_networks,
    save_agent, load_agent, save_network, load_network,
    create_agent_template, create_network_template, create_default_mcps,
    get_mandatory_mcps, ensure_mandatory_mcps, validate_agent_mcps,
    MANDATORY_MCP_TYPES, OPTIONAL_MCP_TYPES,
    get_optional_mcps, get_mcp_config_fields, configure_optional_mcp,
    enable_optional_mcp, disable_optional_mcp, get_agent_mcp_status,
    validate_custom_mcp_json, import_custom_mcp, add_custom_mcp_to_agent,
    remove_custom_mcp_from_agent, list_custom_mcps
)
from orchestrator.docker_manager import check_docker_available, DockerManager
from orchestrator.network_orchestrator import NetworkOrchestrator, get_orchestrator

logger = logging.getLogger("WizardAPI")

# Create router
router = APIRouter(prefix="/api/wizard", tags=["wizard"])

# Pydantic models for API requests/responses

class DockerNetworkConfig(BaseModel):
    """Docker network configuration"""
    name: str = Field(..., min_length=1, max_length=64)
    # Accept both IPv4 (172.20.0.0/16) and IPv6 (fd00:d0c:1::/64) subnets
    subnet: Optional[str] = Field(None)
    gateway: Optional[str] = None
    driver: str = "bridge"
    enable_ipv6: Optional[bool] = False


class MCPSelection(BaseModel):
    """MCP server selection"""
    selected: List[str] = Field(default_factory=list)
    custom: List[Dict[str, Any]] = Field(default_factory=list)


class AgentConfig(BaseModel):
    """Agent configuration"""
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    router_id: str
    protocol: str = Field(..., pattern=r"^(ospf|ospfv3|ibgp|ebgp|isis|mpls|ldp|vxlan|evpn|dhcp|dns)$")  # Primary protocol
    protocols: List[Dict[str, Any]] = Field(default_factory=list)  # All protocols
    interfaces: List[Dict[str, Any]] = Field(default_factory=list)
    protocol_config: Dict[str, Any] = Field(default_factory=dict)
    from_template: Optional[str] = None


class NetworkTypeConfig(BaseModel):
    """Network type and configuration"""
    mode: str = Field(..., pattern=r"^(manual|chat|toon_file)$")
    toon_content: Optional[str] = None
    chat_prompt: Optional[str] = None


class LinkConfig(BaseModel):
    """Link configuration"""
    id: str
    agent1_id: str
    interface1: str
    agent2_id: str
    interface2: str
    link_type: str = "ethernet"
    cost: int = 10


class TopologyConfig(BaseModel):
    """Topology configuration"""
    links: List[LinkConfig] = Field(default_factory=list)
    auto_generate: bool = False


class LLMConfig(BaseModel):
    """LLM provider configuration"""
    provider: str = Field("claude", pattern=r"^(claude|openai|gemini)$")
    api_key: Optional[str] = None


class OverlayConfig(BaseModel):
    """ASI IPv6 Overlay Network configuration (Layer 2)"""
    enabled: bool = True
    subnet: str = "fd00:a510::/48"
    enable_nd: bool = True  # Neighbor Discovery
    enable_routes: bool = True  # Kernel route installation


class DockerIPv6Config(BaseModel):
    """Docker IPv6 network configuration (Layer 1)"""
    enabled: bool = False
    subnet: Optional[str] = "fd00:d0c:1::/64"
    gateway: Optional[str] = "fd00:d0c:1::1"


class NetworkFoundationConfig(BaseModel):
    """
    3-Layer Network Foundation Configuration

    Layer 1: Docker Network (container connectivity)
    Layer 2: ASI Overlay (IPv6 agent mesh) - auto-configured
    Layer 3: Underlay (user-defined routing topology)
    """
    underlay_protocol: str = Field("ipv6", pattern=r"^(ipv4|ipv6|dual)$")
    overlay: OverlayConfig = Field(default_factory=OverlayConfig)
    docker_ipv6: DockerIPv6Config = Field(default_factory=DockerIPv6Config)


class WizardState(BaseModel):
    """Complete wizard state"""
    step: int = 1
    docker_config: Optional[DockerNetworkConfig] = None
    mcp_selection: Optional[MCPSelection] = None
    agents: List[AgentConfig] = Field(default_factory=list)
    network_type: Optional[NetworkTypeConfig] = None
    network_foundation: Optional[NetworkFoundationConfig] = None  # 3-layer architecture
    topology: Optional[TopologyConfig] = None
    llm_config: Optional[LLMConfig] = None


class LaunchRequest(BaseModel):
    """Network launch request"""
    network_id: str
    api_keys: Dict[str, str] = Field(default_factory=dict)


class NLAgentRequest(BaseModel):
    """Natural language agent description"""
    description: str = Field(..., min_length=10)
    agent_id: str = Field(..., min_length=1)
    agent_name: Optional[str] = None


# In-memory wizard sessions with thread-safe lock
_wizard_sessions: Dict[str, WizardState] = {}
_wizard_sessions_lock = asyncio.Lock()


# Endpoints

@router.get("/check-docker")
async def check_docker():
    """Check if Docker is available"""
    available, message = check_docker_available()
    return {
        "available": available,
        "message": message
    }


@router.get("/libraries/agents")
async def get_agent_library():
    """Get saved agent templates"""
    return list_agents()


@router.get("/libraries/networks")
async def get_network_library():
    """Get saved networks"""
    return list_networks()


@router.post("/session/{session_id}/import-network")
async def import_network_template(session_id: str, network_data: Dict[str, Any]):
    """
    Import a full network template into the wizard session.
    This populates all wizard steps from the template.
    """
    if session_id not in _wizard_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _wizard_sessions[session_id]

    try:
        # Import Docker config
        if "docker" in network_data:
            docker = network_data["docker"]
            session.docker_config = DockerNetworkConfig(
                name=docker.get("n", network_data.get("id", "imported-network")),
                subnet=docker.get("subnet"),
                gateway=docker.get("gw"),
                driver=docker.get("driver", "bridge")
            )

        # Import agents
        session.agents = []
        for agent_data in network_data.get("agents", []):
            # Extract protocols
            protocols = []
            for proto in agent_data.get("protos", []):
                protocols.append(proto)

            # Build agent config
            agent_config = AgentConfig(
                id=agent_data["id"],
                name=agent_data.get("n", agent_data["id"]),
                router_id=agent_data.get("r", "1.1.1.1"),
                protocol=protocols[0]["p"] if protocols else "ospf",
                protocols=protocols,
                interfaces=agent_data.get("ifs", []),
                protocol_config=protocols[0] if protocols else {}
            )
            session.agents.append(agent_config)

        # Import topology
        if "topo" in network_data and network_data["topo"]:
            topo = network_data["topo"]
            links = []
            for link in topo.get("links", []):
                links.append(LinkConfig(
                    id=link.get("id", f"link-{len(links)+1}"),
                    agent1_id=link["a1"],
                    interface1=link["i1"],
                    agent2_id=link["a2"],
                    interface2=link["i2"],
                    link_type=link.get("t", "ethernet"),
                    cost=link.get("c", 10)
                ))
            session.topology = TopologyConfig(links=links, auto_generate=False)

        # Set step to final review
        session.step = 6

        return {
            "status": "ok",
            "imported": {
                "agents": len(session.agents),
                "links": len(session.topology.links) if session.topology else 0,
                "docker_network": session.docker_config.name if session.docker_config else None
            }
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")


@router.get("/mcps/default")
async def get_default_mcps():
    """Get default MCP configurations"""
    mcps = create_default_mcps()
    return [m.to_dict() for m in mcps]


@router.post("/session/create")
async def create_wizard_session():
    """Create a new wizard session"""
    import uuid
    session_id = str(uuid.uuid4())[:8]
    _wizard_sessions[session_id] = WizardState()
    return {"session_id": session_id, "state": _wizard_sessions[session_id].dict()}


@router.get("/session/{session_id}")
async def get_wizard_session(session_id: str):
    """Get wizard session state"""
    if session_id not in _wizard_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return _wizard_sessions[session_id].dict()


@router.delete("/session/{session_id}")
async def delete_wizard_session(session_id: str):
    """Delete wizard session"""
    if session_id in _wizard_sessions:
        del _wizard_sessions[session_id]
    return {"status": "deleted"}


# Step 1: Docker Network Configuration

@router.post("/session/{session_id}/step1")
async def wizard_step1(session_id: str, config: DockerNetworkConfig):
    """Configure Docker network (Step 1)"""
    if session_id not in _wizard_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _wizard_sessions[session_id]
    session.docker_config = config
    session.step = 2

    return {"status": "ok", "step": 2, "config": config.dict()}


# Step 2: MCP Server Selection

@router.post("/session/{session_id}/step2")
async def wizard_step2(session_id: str, selection: MCPSelection):
    """Select MCP servers (Step 2)"""
    if session_id not in _wizard_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _wizard_sessions[session_id]
    session.mcp_selection = selection
    session.step = 3

    return {"status": "ok", "step": 3, "selection": selection.dict()}


# Step 3: Agent Builder

@router.post("/session/{session_id}/step3/agent")
async def wizard_step3_add_agent(session_id: str, agent: AgentConfig):
    """Add agent to wizard (Step 3)"""
    if session_id not in _wizard_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _wizard_sessions[session_id]

    # Check for duplicate ID
    for existing in session.agents:
        if existing.id == agent.id:
            raise HTTPException(status_code=400, detail=f"Agent ID {agent.id} already exists")

    session.agents.append(agent)

    return {"status": "ok", "agents": [a.dict() for a in session.agents]}


@router.delete("/session/{session_id}/step3/agent/{agent_id}")
async def wizard_step3_remove_agent(session_id: str, agent_id: str):
    """Remove agent from wizard (Step 3)"""
    if session_id not in _wizard_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _wizard_sessions[session_id]
    session.agents = [a for a in session.agents if a.id != agent_id]

    return {"status": "ok", "agents": [a.dict() for a in session.agents]}


@router.post("/session/{session_id}/step3/complete")
async def wizard_step3_complete(session_id: str):
    """Complete agent configuration (Step 3)"""
    if session_id not in _wizard_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _wizard_sessions[session_id]

    if not session.agents:
        raise HTTPException(status_code=400, detail="At least one agent required")

    session.step = 4
    return {"status": "ok", "step": 4}


@router.post("/session/{session_id}/step3/from-template")
async def wizard_step3_from_template(session_id: str, template_id: str, new_id: str, new_name: Optional[str] = None):
    """Create agent from template (Step 3)"""
    if session_id not in _wizard_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    # Load template
    template = load_agent(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")

    # Create agent config from template
    agent_config = AgentConfig(
        id=new_id,
        name=new_name or f"{template.n} (Copy)",
        router_id=template.r,
        protocol=template.protos[0].p if template.protos else "ospf",
        interfaces=[i.to_dict() for i in template.ifs],
        protocol_config=template.protos[0].to_dict() if template.protos else {},
        from_template=template_id
    )

    session = _wizard_sessions[session_id]
    session.agents.append(agent_config)

    return {"status": "ok", "agent": agent_config.dict()}


@router.post("/session/{session_id}/nl-to-agent")
async def wizard_nl_to_agent(session_id: str, request: NLAgentRequest):
    """Convert natural language description to agent configuration"""
    import re

    if session_id not in _wizard_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    description = request.description.lower()

    # Parse protocol type
    protocol = "ospf"  # default
    if any(kw in description for kw in ["ebgp", "external bgp", "e-bgp"]):
        protocol = "ebgp"
    elif any(kw in description for kw in ["ibgp", "internal bgp", "i-bgp"]):
        protocol = "ibgp"
    elif any(kw in description for kw in ["bgp", "as ", "asn", "autonomous system"]):
        # Check if there's mention of different AS numbers for peers
        as_pattern = r'(?:as|asn)\s*(?:number)?\s*(\d+)'
        as_matches = re.findall(as_pattern, description)
        if len(as_matches) >= 2 and as_matches[0] != as_matches[1]:
            protocol = "ebgp"
        else:
            protocol = "ibgp"
    elif "ospfv3" in description or "ipv6" in description:
        protocol = "ospfv3"
    elif any(kw in description for kw in ["isis", "is-is", "intermediate system"]):
        protocol = "isis"
    elif any(kw in description for kw in ["mpls", "label switch", "label distribution"]):
        protocol = "mpls"
    elif any(kw in description for kw in ["ldp", "label distribution protocol"]):
        protocol = "ldp"
    elif any(kw in description for kw in ["vxlan", "vtep", "virtual extensible"]):
        protocol = "vxlan"
    elif any(kw in description for kw in ["evpn", "ethernet vpn", "mac-vrf"]):
        protocol = "evpn"
    elif any(kw in description for kw in ["dhcp server", "dhcp pool", "ip assignment"]):
        protocol = "dhcp"
    elif any(kw in description for kw in ["dns server", "name server", "dns zone"]):
        protocol = "dns"

    # Parse router ID
    router_id = None
    rid_patterns = [
        r'router[- ]?id\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})',
        r'router[- ]?id\s*[:=]\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})',
        r'rid\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
    ]
    for pattern in rid_patterns:
        match = re.search(pattern, description)
        if match:
            router_id = match.group(1)
            break

    # If no explicit router ID, try to extract from loopback or first IP mentioned
    if not router_id:
        ip_pattern = r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?:/\d{1,2})?'
        ip_matches = re.findall(ip_pattern, description)
        if ip_matches:
            # Prefer loopback-style IPs (x.x.x.x where last octet matches pattern)
            for ip in ip_matches:
                octets = ip.split('.')
                if octets[0] == '10' or octets[0] == '192':
                    router_id = ip
                    break
            if not router_id:
                router_id = ip_matches[0]

    if not router_id:
        router_id = "1.1.1.1"  # Default

    # Parse protocol-specific config
    protocol_config = {}

    if protocol in ["ospf", "ospfv3"]:
        # Parse OSPF area
        area_patterns = [
            r'area\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})',
            r'area\s+(\d+)',
            r'backbone\s+area'
        ]
        area = "0.0.0.0"  # default
        for pattern in area_patterns:
            match = re.search(pattern, description)
            if match:
                if "backbone" in pattern:
                    area = "0.0.0.0"
                else:
                    area_val = match.group(1)
                    # Convert single number to dotted notation if needed
                    if '.' not in area_val:
                        area = f"0.0.0.{area_val}"
                    else:
                        area = area_val
                break
        protocol_config["a"] = area

    elif protocol == "isis":
        # Parse IS-IS specific config
        # System ID
        system_id_match = re.search(r'system[- ]?id\s+([0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})', description, re.I)
        if system_id_match:
            protocol_config["system_id"] = system_id_match.group(1)

        # Area address
        area_match = re.search(r'area\s+(\d+\.?\d*)', description)
        if area_match:
            protocol_config["area"] = area_match.group(1)
        else:
            protocol_config["area"] = "49.0001"  # Default

        # Level
        level_match = re.search(r'level[- ]?(\d)', description)
        if level_match:
            protocol_config["level"] = int(level_match.group(1))
        else:
            protocol_config["level"] = 3  # L1/L2 default

        # Metric
        metric_match = re.search(r'metric\s+(\d+)', description)
        if metric_match:
            protocol_config["metric"] = int(metric_match.group(1))

    elif protocol in ["mpls", "ldp"]:
        # Parse MPLS/LDP specific config
        # Label range
        label_start_match = re.search(r'label[- ]?range[- ]?start\s+(\d+)', description)
        if label_start_match:
            protocol_config["label_range_start"] = int(label_start_match.group(1))

        # LDP neighbors
        neighbor_pattern = r'neighbor\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        neighbors = re.findall(neighbor_pattern, description)
        if neighbors:
            protocol_config["neighbors"] = neighbors

    elif protocol == "vxlan":
        # Parse VXLAN specific config
        # VNI
        vni_matches = re.findall(r'vni\s+(\d+)', description)
        if vni_matches:
            protocol_config["vnis"] = [int(v) for v in vni_matches]
        else:
            protocol_config["vnis"] = [100]  # Default VNI

        # Remote VTEPs
        vtep_pattern = r'(?:remote[- ]?)?vtep\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        remote_vteps = re.findall(vtep_pattern, description)
        if remote_vteps:
            protocol_config["remote_vteps"] = remote_vteps

    elif protocol == "evpn":
        # Parse EVPN specific config
        # Route Distinguisher
        rd_match = re.search(r'rd\s+(\d+:\d+)', description)
        if rd_match:
            protocol_config["rd"] = rd_match.group(1)

        # Route Targets
        rt_matches = re.findall(r'rt\s+(\d+:\d+)', description)
        if rt_matches:
            protocol_config["rts"] = rt_matches

        # VNIs for EVPN
        vni_matches = re.findall(r'vni\s+(\d+)', description)
        if vni_matches:
            protocol_config["vnis"] = [int(v) for v in vni_matches]

    elif protocol == "dhcp":
        # Parse DHCP server config
        protocol_config["enabled"] = True

        # Pool range
        pool_match = re.search(r'pool\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})[- ]+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', description)
        if pool_match:
            protocol_config["pool_start"] = pool_match.group(1)
            protocol_config["pool_end"] = pool_match.group(2)

        # Gateway
        gw_match = re.search(r'gateway\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', description)
        if gw_match:
            protocol_config["gateway"] = gw_match.group(1)

        # DNS servers
        dns_matches = re.findall(r'dns\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', description)
        if dns_matches:
            protocol_config["dns_servers"] = dns_matches

        # Lease time
        lease_match = re.search(r'lease[- ]?time\s+(\d+)', description)
        if lease_match:
            protocol_config["lease_time"] = int(lease_match.group(1))

    elif protocol == "dns":
        # Parse DNS server config
        protocol_config["enabled"] = True

        # Zone
        zone_match = re.search(r'zone\s+([a-z0-9][a-z0-9\-\.]+[a-z0-9])', description, re.I)
        if zone_match:
            protocol_config["zone"] = zone_match.group(1)

        # Forwarders
        forwarder_matches = re.findall(r'forwarder\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', description)
        if forwarder_matches:
            protocol_config["forwarders"] = forwarder_matches

    elif protocol in ["ibgp", "ebgp"]:
        # Parse AS number
        as_pattern = r'(?:as|asn|autonomous system)\s*(?:number)?\s*[:=]?\s*(\d+)'
        as_match = re.search(as_pattern, description)
        if as_match:
            protocol_config["asn"] = int(as_match.group(1))
        else:
            protocol_config["asn"] = 65001  # default

        # Parse networks to advertise
        networks = []
        network_patterns = [
            r'advertise[s]?\s+(?:the\s+)?(?:network\s+)?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})',
            r'network[s]?\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})',
            r'announce[s]?\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})'
        ]
        for pattern in network_patterns:
            matches = re.findall(pattern, description)
            networks.extend(matches)

        if networks:
            protocol_config["nets"] = list(set(networks))

        # Parse BGP peers
        peers = []
        peer_patterns = [
            r'peer[s]?\s+(?:with\s+)?(?:neighbor\s+)?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+(?:in\s+)?(?:as|asn)\s*(\d+)',
            r'neighbor\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+(?:remote-as|as)\s*(\d+)'
        ]
        for pattern in peer_patterns:
            matches = re.findall(pattern, description)
            for peer_ip, peer_as in matches:
                peers.append({"ip": peer_ip, "asn": int(peer_as)})

        if peers:
            protocol_config["peers"] = peers

    # Generate agent name if not provided
    agent_name = request.agent_name
    if not agent_name:
        proto_name = protocol.upper()
        agent_name = f"{proto_name} Router {request.agent_id}"

    # Build agent config
    agent_config = {
        "id": request.agent_id,
        "name": agent_name,
        "router_id": router_id,
        "protocol": protocol,
        "interfaces": [],
        "protocol_config": protocol_config
    }

    return {
        "status": "ok",
        "agent": agent_config,
        "parsed_info": {
            "protocol": protocol,
            "router_id": router_id,
            "protocol_config": protocol_config
        }
    }


# Step 4: Network Type & Configuration

@router.post("/session/{session_id}/step4")
async def wizard_step4(session_id: str, config: NetworkTypeConfig):
    """Configure network type (Step 4)"""
    if session_id not in _wizard_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _wizard_sessions[session_id]
    session.network_type = config
    session.step = 5

    return {"status": "ok", "step": 5, "config": config.dict()}


# Step 5: Topology & Links

@router.post("/session/{session_id}/step5")
async def wizard_step5(session_id: str, topology: TopologyConfig):
    """Configure topology (Step 5)"""
    if session_id not in _wizard_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _wizard_sessions[session_id]

    # Auto-generate links if requested
    if topology.auto_generate and not topology.links:
        topology.links = _auto_generate_links(session.agents)

    session.topology = topology
    session.step = 6

    return {"status": "ok", "step": 6, "topology": topology.dict()}


def _auto_generate_links(agents: List[AgentConfig]) -> List[LinkConfig]:
    """Auto-generate links between agents (linear topology)"""
    links = []
    for i in range(len(agents) - 1):
        links.append(LinkConfig(
            id=f"link-{i+1}",
            agent1_id=agents[i].id,
            interface1="eth0",
            agent2_id=agents[i+1].id,
            interface2="eth0"
        ))
    return links


# Step 6: LLM Provider Configuration

@router.post("/session/{session_id}/step6")
async def wizard_step6(session_id: str, config: LLMConfig):
    """Configure LLM provider (Step 6)"""
    if session_id not in _wizard_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _wizard_sessions[session_id]
    session.llm_config = config

    return {"status": "ok", "complete": True}


@router.post("/session/{session_id}/validate-api-key")
async def validate_api_key(session_id: str, config: LLMConfig):
    """Validate LLM API key"""
    # TODO: Implement actual API key validation
    # For now, just check if key is provided
    if not config.api_key:
        return {"valid": False, "message": "No API key provided"}

    # Basic format validation
    if config.provider == "claude" and not config.api_key.startswith("sk-ant-"):
        return {"valid": False, "message": "Invalid Claude API key format"}

    return {"valid": True, "message": "API key format valid"}


# Preview and Launch

@router.get("/session/{session_id}/preview")
async def wizard_preview(session_id: str):
    """Get preview of configured network"""
    if session_id not in _wizard_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _wizard_sessions[session_id]

    # Build network object
    network = _build_network_from_session(session)

    return {
        "network": network.to_dict(),
        "agent_count": len(network.agents),
        "link_count": len(network.topo.links) if network.topo else 0,
        "mcp_count": len(network.mcps),
        "estimated_containers": len(network.agents)
    }


@router.post("/session/{session_id}/save")
async def wizard_save(session_id: str):
    """Save configured network to persistence"""
    if session_id not in _wizard_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _wizard_sessions[session_id]
    network = _build_network_from_session(session)

    # Save network
    path = save_network(network)

    return {"status": "ok", "network_id": network.id, "path": str(path)}


@router.post("/session/{session_id}/launch")
async def wizard_launch(session_id: str, request: LaunchRequest):
    """Launch the configured network"""
    if session_id not in _wizard_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = _wizard_sessions[session_id]

    # Check Docker
    available, message = check_docker_available()
    if not available:
        raise HTTPException(status_code=503, detail=f"Docker not available: {message}")

    # Build and save network
    network = _build_network_from_session(session)
    save_network(network)

    # Build network foundation dict from session config
    network_foundation = None
    if session.network_foundation:
        network_foundation = {
            "underlay_protocol": session.network_foundation.underlay_protocol,
            "overlay": {
                "enabled": session.network_foundation.overlay.enabled,
                "subnet": session.network_foundation.overlay.subnet,
                "enable_nd": session.network_foundation.overlay.enable_nd,
                "enable_routes": session.network_foundation.overlay.enable_routes
            },
            "docker_ipv6": {
                "enabled": session.network_foundation.docker_ipv6.enabled,
                "subnet": session.network_foundation.docker_ipv6.subnet,
                "gateway": session.network_foundation.docker_ipv6.gateway
            }
        }

    # Launch network with 3-layer architecture settings
    orchestrator = get_orchestrator()
    deployment = await orchestrator.launch(
        network=network,
        api_keys=request.api_keys,
        network_foundation=network_foundation
    )

    return {
        "status": deployment.status,
        "network_id": network.id,
        "docker_network": deployment.docker_network,
        "subnet": deployment.subnet,
        "agents": {
            agent_id: {
                "status": agent.status,
                "ip_address": agent.ip_address,
                "ipv6_overlay": agent.ipv6_overlay,  # Layer 2: ASI Overlay address
                "webui_port": agent.webui_port,
                "error": agent.error_message
            }
            for agent_id, agent in deployment.agents.items()
        }
    }


def _build_network_from_session(session: WizardState) -> TOONNetwork:
    """Build TOONNetwork from wizard session"""
    # Docker config
    docker_config = None
    if session.docker_config:
        docker_config = TOONDockerConfig(
            n=session.docker_config.name,
            driver=session.docker_config.driver,
            subnet=session.docker_config.subnet,
            gw=session.docker_config.gateway
        )

    # MCPs - Always include mandatory MCPs, then add user selections
    mcps = []
    mcp_ids_added = set()

    # First, add all mandatory MCPs (GAIT, pyATS, RFC, Markmap)
    mandatory_mcps = get_mandatory_mcps()
    for mcp in mandatory_mcps:
        mcps.append(mcp)
        mcp_ids_added.add(mcp.id)

    # Then add user-selected MCPs (skip if already added as mandatory)
    if session.mcp_selection:
        default_mcps = {m.id: m for m in create_default_mcps()}

        # Build a map of custom configs by MCP id
        custom_configs = {}
        for custom in session.mcp_selection.custom:
            if isinstance(custom, dict) and "id" in custom:
                custom_configs[custom["id"]] = custom.get("config", {})

        for mcp_id in session.mcp_selection.selected:
            if mcp_id not in mcp_ids_added and mcp_id in default_mcps:
                mcp = default_mcps[mcp_id]
                # Apply custom config if available
                if mcp_id in custom_configs:
                    # Merge user config into MCP's config
                    user_config = custom_configs[mcp_id]
                    merged_config = {**mcp.c, **user_config}
                    mcp = TOONMCPConfig(
                        id=mcp.id,
                        t=mcp.t,
                        n=mcp.n,
                        d=mcp.d,
                        url=mcp.url,
                        c=merged_config,
                        e=True  # Enable since user configured it
                    )
                mcps.append(mcp)
                mcp_ids_added.add(mcp_id)

        # Add fully custom MCPs (user-imported, not from defaults)
        for custom in session.mcp_selection.custom:
            if isinstance(custom, dict) and custom.get("id") not in default_mcps:
                custom_mcp = TOONMCPConfig.from_dict(custom)
                if custom_mcp.id not in mcp_ids_added:
                    mcps.append(custom_mcp)
                    mcp_ids_added.add(custom_mcp.id)

    # Agents
    agents = []
    for agent_config in session.agents:
        # Interfaces
        interfaces = [
            TOONInterface.from_dict(i) for i in agent_config.interfaces
        ] if agent_config.interfaces else [
            TOONInterface(id="eth0", n="eth0", t="eth", a=[]),
            TOONInterface(id="lo0", n="lo0", t="lo", a=[f"{agent_config.router_id}/32"])
        ]

        # Protocols - support both multi-protocol and single protocol format
        protos = []
        if agent_config.protocols:
            # New multi-protocol format
            for proto_data in agent_config.protocols:
                protos.append(TOONProtocolConfig(
                    p=proto_data.get("p", "ospf"),
                    r=proto_data.get("r", agent_config.router_id),
                    a=proto_data.get("a", "0.0.0.0"),
                    asn=proto_data.get("asn"),
                    peers=proto_data.get("peers", []),
                    nets=proto_data.get("nets", [])
                ))
        else:
            # Backwards compatibility: single protocol format
            protos.append(TOONProtocolConfig(
                p=agent_config.protocol,
                r=agent_config.router_id,
                a=agent_config.protocol_config.get("a", "0.0.0.0"),
                asn=agent_config.protocol_config.get("asn"),
                peers=agent_config.protocol_config.get("peers", []),
                nets=agent_config.protocol_config.get("nets", [])
            ))

        agents.append(TOONAgent(
            id=agent_config.id,
            n=agent_config.name,
            r=agent_config.router_id,
            ifs=interfaces,
            protos=protos,
            mcps=mcps.copy()  # Each agent gets MCPs
        ))

    # Topology
    topo = None
    if session.topology and session.topology.links:
        links = [
            TOONLink(
                id=l.id,
                a1=l.agent1_id,
                i1=l.interface1,
                a2=l.agent2_id,
                i2=l.interface2,
                t=l.link_type,
                c=l.cost
            )
            for l in session.topology.links
        ]
        topo = TOONTopology(links=links)

    # Network ID from Docker config
    network_id = session.docker_config.name if session.docker_config else f"network-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    return TOONNetwork(
        id=network_id,
        n=session.docker_config.name if session.docker_config else "New Network",
        docker=docker_config,
        agents=agents,
        topo=topo,
        mcps=mcps
    )


# Network Management Endpoints

@router.get("/networks")
async def list_deployed_networks():
    """List all deployed networks - includes discovered running containers"""
    orchestrator = get_orchestrator()
    deployments = orchestrator.list_deployments()

    # If no deployments tracked, try to discover running ASI containers
    if not deployments:
        discovered = await discover_running_agents()
        if discovered:
            return discovered

    return [
        {
            "network_id": d.network_id,
            "name": d.network_name,
            "status": d.status,
            "docker_network": d.docker_network,
            "agent_count": len(d.agents),
            "started_at": d.started_at
        }
        for d in deployments
    ]


@router.get("/networks/discover")
async def discover_networks():
    """Discover running ASI agent containers from Docker"""
    return await discover_running_agents()


async def discover_running_agents():
    """
    Discover ASI agent containers directly from Docker.
    This works even if the wizard was restarted and lost deployment tracking.
    Includes stopped containers so users can see their networks even if crashed.
    """
    try:
        # Use the existing DockerManager which handles SDK availability gracefully
        docker_mgr = DockerManager()
        if not docker_mgr.available:
            logger.warning(f"Docker not available for discovery: {docker_mgr.error_message}")
            return []

        # Use DockerManager's list_containers with ASI filter
        # Include ALL containers (running + stopped) so we show crashed networks too
        containers = docker_mgr.list_containers(asi_only=True, all=True)

        # Group containers by network name
        networks = {}

        for container in containers:
            name = container.name
            labels = container.labels or {}
            ports = container.ports or {}

            # Extract network name from labels or container name
            # Check multiple label formats that might be used
            network_id = labels.get("asi.network_id") or labels.get("asi.network")
            if not network_id:
                # Try to extract from container name (e.g., "springfield-ospf-router")
                network_id = name.split("-")[0] if "-" in name else name

            if network_id not in networks:
                networks[network_id] = {
                    "network_id": network_id,
                    "name": network_id,
                    "status": "running",
                    "docker_network": labels.get("asi.docker_network", container.network or network_id),
                    "agents": [],
                    "discovered": True  # Flag that this was auto-discovered
                }

            # Extract port mappings from ContainerInfo.ports dict
            webui_port = None
            api_port = None
            for container_port, host_bindings in ports.items():
                if host_bindings:
                    # host_bindings can be list of dicts or None
                    if isinstance(host_bindings, list) and len(host_bindings) > 0:
                        host_port = host_bindings[0].get("HostPort") if isinstance(host_bindings[0], dict) else None
                        if host_port:
                            if "8888" in str(container_port):
                                webui_port = host_port
                            elif "8080" in str(container_port):
                                api_port = host_port

            # Get agent info from labels
            agent_id = labels.get("asi.agent_id") or name
            agent_name = labels.get("asi.agent_name") or name
            overlay_ipv6 = labels.get("asi.overlay_ipv6")

            networks[network_id]["agents"].append({
                "id": agent_id,
                "name": agent_name,
                "container_name": name,
                "container_id": container.id,
                "status": container.status,
                "webui_port": webui_port,
                "api_port": api_port,
                "ip_address": container.ip_address,
                "ip_address_v6": container.ip_address_v6,
                "overlay_ipv6": overlay_ipv6
            })

        # Convert to list, add agent counts, and calculate network status
        result = []
        for network_id, network_data in networks.items():
            network_data["agent_count"] = len(network_data["agents"])

            # Determine overall network status based on agent statuses
            agent_statuses = [a["status"] for a in network_data["agents"]]
            if not agent_statuses:
                network_data["status"] = "unknown"
            elif all(s == "running" for s in agent_statuses):
                network_data["status"] = "running"
            elif any(s == "running" for s in agent_statuses):
                network_data["status"] = "partial"  # Some running, some stopped
            elif any("exited" in s.lower() for s in agent_statuses):
                network_data["status"] = "stopped"
            else:
                network_data["status"] = "unknown"

            result.append(network_data)

        return result

    except Exception as e:
        logger.error(f"Error discovering containers: {e}")
        return []


@router.get("/networks/discover/{network_id}/status")
async def get_discovered_network_status(network_id: str):
    """Get status for a discovered (not wizard-tracked) network"""
    discovered = await discover_running_agents()

    for network in discovered:
        if network["network_id"] == network_id:
            # Build agents_info dict compatible with topology3d
            agents_info = {}
            for agent in network.get("agents", []):
                agents_info[agent["id"]] = {
                    "status": agent["status"],
                    "webui_port": agent.get("webui_port"),
                    "ip_address": agent.get("ip_address"),
                    "ip_address_v6": agent.get("ip_address_v6"),
                    "ipv6_overlay": agent.get("overlay_ipv6"),
                    "container_name": agent.get("container_name"),
                    "config": {"n": agent["name"]}
                }

            return {
                "network_id": network_id,
                "name": network.get("name", network_id),
                "status": network.get("status", "unknown"),  # Use calculated status
                "agents": agents_info
            }

    raise HTTPException(status_code=404, detail="Network not found")


@router.get("/networks/{network_id}/status")
async def get_deployed_network_status(network_id: str):
    """Get status of deployed network including 3-layer network info and live protocol stats"""
    import aiohttp
    import asyncio

    orchestrator = get_orchestrator()
    deployment = orchestrator.get_status(network_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Network not found")

    # Build agent info with all 3 layers
    agents_info = {}

    async def fetch_agent_status(agent_id, agent):
        """Fetch live status from agent's API"""
        config = getattr(agent, 'config', None)

        # Extract underlay protocol info from config
        underlay_info = None
        protos = []
        if config:
            if hasattr(config, 'protos') and config.protos:
                for p in config.protos:
                    if hasattr(p, 'p'):
                        protos.append(p.p)
            if protos:
                underlay_info = ', '.join(protos)

        # Base agent info
        agent_info = {
            "status": agent.status,
            "container_id": agent.container_id,
            # Layer 1: Docker Network
            "ip_address": agent.ip_address,
            "docker_ip": agent.ip_address,
            # Layer 2: ASI IPv6 Overlay
            "ipv6_overlay": getattr(agent, 'ipv6_overlay', None),
            # Layer 3: Underlay protocols
            "underlay_info": underlay_info,
            "webui_port": agent.webui_port,
            "error": agent.error_message,
            "config": config,
            # Initialize protocol stats to 0
            "ospf_neighbors": 0,
            "ospf_full_neighbors": 0,
            "ospf_routes": 0,
            "bgp_peers": 0,
            "bgp_established_peers": 0,
            "bgp_routes": 0,
            "isis_adjacencies": 0,
            "isis_routes": 0,
            "routes": 0
        }

        # Try to fetch live stats from agent's API
        if agent.status == "running" and agent.webui_port:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                    url = f"http://localhost:{agent.webui_port}/api/status"
                    async with session.get(url) as response:
                        if response.status == 200:
                            status_data = await response.json()
                            # Extract OSPF stats
                            if 'ospf' in status_data:
                                ospf = status_data['ospf']
                                agent_info["ospf_neighbors"] = ospf.get('neighbors', 0)
                                agent_info["ospf_full_neighbors"] = ospf.get('full_neighbors', 0)
                                agent_info["ospf_routes"] = ospf.get('routes', 0)
                            # Extract BGP stats
                            if 'bgp' in status_data:
                                bgp = status_data['bgp']
                                agent_info["bgp_peers"] = bgp.get('total_peers', 0)
                                agent_info["bgp_established_peers"] = bgp.get('established_peers', 0)
                                agent_info["bgp_routes"] = bgp.get('loc_rib_routes', 0)
                            # Extract IS-IS stats
                            if 'isis' in status_data:
                                isis = status_data['isis']
                                agent_info["isis_adjacencies"] = isis.get('adjacencies', 0)
                                agent_info["isis_routes"] = isis.get('routes', 0)
                            # Total routes
                            agent_info["routes"] = status_data.get('total_routes', 0)
            except Exception as e:
                # Silently fail - agent might be starting up
                pass

        return agent_id, agent_info

    # Fetch all agent statuses concurrently
    tasks = [fetch_agent_status(agent_id, agent) for agent_id, agent in deployment.agents.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, tuple):
            agent_id, agent_info = result
            agents_info[agent_id] = agent_info

    return {
        "network_id": deployment.network_id,
        "name": deployment.network_name,
        "status": deployment.status,
        "docker_network": deployment.docker_network,
        "subnet": deployment.subnet,
        # Include Docker IPv6 config if available
        "subnet6": getattr(deployment, 'subnet6', None),
        "agents": agents_info,
        "started_at": deployment.started_at
    }


@router.post("/networks/{network_id}/stop")
async def stop_deployed_network(network_id: str, save_state: bool = True):
    """Stop a deployed network"""
    orchestrator = get_orchestrator()
    success = await orchestrator.stop(network_id, save_state=save_state)
    if not success:
        raise HTTPException(status_code=404, detail="Network not found or already stopped")

    return {"status": "stopped", "network_id": network_id}


@router.get("/networks/{network_id}/agents/{agent_id}/logs")
async def get_agent_logs(network_id: str, agent_id: str, tail: int = 100):
    """Get logs from an agent"""
    orchestrator = get_orchestrator()
    logs = orchestrator.get_agent_logs(network_id, agent_id, tail)
    if logs is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    return {"agent_id": agent_id, "logs": logs}


@router.get("/networks/{network_id}/health")
async def get_network_health(network_id: str):
    """Get network health check"""
    orchestrator = get_orchestrator()
    health = await orchestrator.health_check(network_id)
    return health


# =============================================================================
# Optional MCP Configuration API
# =============================================================================

@router.get("/mcps/optional")
async def get_optional_mcp_list():
    """
    Get list of optional MCPs that can be configured.

    Returns list of optional MCPs with their configuration requirements.
    """
    optional = get_optional_mcps()
    return {
        "optional_mcps": [
            {
                "id": mcp.id,
                "type": mcp.t,
                "name": mcp.n,
                "description": mcp.d,
                "url": mcp.url,
                "config_fields": mcp.c.get("_config_fields", []),
                "requires_config": mcp.c.get("_requires_config", False)
            }
            for mcp in optional
        ],
        "available_types": list(OPTIONAL_MCP_TYPES)
    }


@router.get("/mcps/mandatory")
async def get_mandatory_mcp_list():
    """
    Get list of mandatory MCPs that every agent must have.

    These MCPs are automatically added to all agents.
    """
    mandatory = get_mandatory_mcps()
    return {
        "mandatory_mcps": [
            {
                "id": mcp.id,
                "type": mcp.t,
                "name": mcp.n,
                "description": mcp.d,
                "url": mcp.url,
                "always_enabled": True
            }
            for mcp in mandatory
        ],
        "required_types": list(MANDATORY_MCP_TYPES)
    }


@router.get("/mcps/{mcp_type}/config-fields")
async def get_mcp_configuration_fields(mcp_type: str):
    """
    Get configuration fields for a specific MCP type.

    Args:
        mcp_type: MCP type (servicenow, netbox, slack, github)

    Returns configuration field definitions including labels, types, and hints.
    """
    if mcp_type not in OPTIONAL_MCP_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid MCP type: {mcp_type}. Valid types: {list(OPTIONAL_MCP_TYPES)}"
        )

    fields = get_mcp_config_fields(mcp_type)
    return {
        "mcp_type": mcp_type,
        "config_fields": fields,
        "requires_config": len(fields) > 0
    }


class MCPConfigRequest(BaseModel):
    """Request model for MCP configuration"""
    config: Dict[str, Any] = Field(default_factory=dict)
    enable: bool = True


@router.post("/agents/{agent_id}/mcps/{mcp_type}/configure")
async def configure_agent_mcp(agent_id: str, mcp_type: str, request: MCPConfigRequest):
    """
    Configure an optional MCP for an agent.

    Args:
        agent_id: Agent ID
        mcp_type: MCP type (servicenow, netbox, slack, github)
        request: Configuration values and enable flag

    Returns updated MCP status for the agent.
    """
    if mcp_type not in OPTIONAL_MCP_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid MCP type: {mcp_type}. Valid types: {list(OPTIONAL_MCP_TYPES)}"
        )

    # Load agent
    agent = load_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    # Configure MCP
    try:
        agent = configure_optional_mcp(agent, mcp_type, request.config, request.enable)
        save_agent(agent)

        return {
            "status": "ok",
            "agent_id": agent_id,
            "mcp_type": mcp_type,
            "enabled": request.enable,
            "mcp_status": get_agent_mcp_status(agent)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/agents/{agent_id}/mcps/{mcp_type}/enable")
async def enable_agent_mcp(agent_id: str, mcp_type: str):
    """Enable an optional MCP for an agent."""
    if mcp_type not in OPTIONAL_MCP_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid MCP type: {mcp_type}. Valid types: {list(OPTIONAL_MCP_TYPES)}"
        )

    agent = load_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    agent = enable_optional_mcp(agent, mcp_type)
    save_agent(agent)

    return {
        "status": "ok",
        "agent_id": agent_id,
        "mcp_type": mcp_type,
        "enabled": True
    }


@router.post("/agents/{agent_id}/mcps/{mcp_type}/disable")
async def disable_agent_mcp(agent_id: str, mcp_type: str):
    """Disable an optional MCP for an agent."""
    if mcp_type not in OPTIONAL_MCP_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid MCP type: {mcp_type}. Valid types: {list(OPTIONAL_MCP_TYPES)}"
        )

    agent = load_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    agent = disable_optional_mcp(agent, mcp_type)
    save_agent(agent)

    return {
        "status": "ok",
        "agent_id": agent_id,
        "mcp_type": mcp_type,
        "enabled": False
    }


@router.get("/agents/{agent_id}/mcps/status")
async def get_agent_mcp_info(agent_id: str):
    """
    Get MCP status for an agent.

    Returns detailed information about mandatory and optional MCPs.
    """
    agent = load_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    return {
        "agent_id": agent_id,
        "mcp_status": get_agent_mcp_status(agent)
    }


# =============================================================================
# NetBox MCP Integration API
# =============================================================================

class NetBoxTestRequest(BaseModel):
    """Request model for testing NetBox connection"""
    netbox_url: str = Field(..., min_length=1)
    api_token: str = Field(..., min_length=1)


@router.post("/mcps/netbox/test")
async def test_netbox_connection(request: NetBoxTestRequest):
    """
    Test connection to NetBox instance.

    Returns connection status and NetBox version info.
    """
    try:
        from agentic.mcp.netbox_mcp import NetBoxClient, NetBoxConfig

        config = NetBoxConfig(
            url=request.netbox_url,
            api_token=request.api_token
        )
        client = NetBoxClient(config)

        result = await client.test_connection()
        await client.close()

        return {
            "status": "ok" if result.get("connected") else "error",
            **result
        }
    except ImportError as e:
        return {
            "status": "error",
            "error": f"NetBox MCP not available: {e}",
            "hint": "Install httpx: pip install httpx"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


class NetBoxRegisterRequest(BaseModel):
    """Request model for registering agent in NetBox"""
    netbox_url: str = Field(..., min_length=1)
    api_token: str = Field(..., min_length=1)
    site_name: str = Field(..., min_length=1)


@router.post("/agents/{agent_id}/mcps/netbox/register")
async def register_agent_in_netbox(agent_id: str, request: NetBoxRegisterRequest):
    """
    Register an agent as a device in NetBox with full configuration.

    Creates:
    - Device (Name, Site, Role=Router, Type=ASI Agent, Manufacturer=Agentic)
    - All interfaces from agent config
    - IP addresses assigned to interfaces
    - Services for protocols (BGP port 179, OSPF, etc.)
    - Sets primary IP on device

    Args:
        agent_id: Agent ID
        request: NetBox URL, API token, and site name

    Returns:
        Registration result with created objects
    """
    agent = load_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    try:
        from agentic.mcp.netbox_mcp import (
            NetBoxClient, NetBoxConfig, configure_netbox, auto_register_agent
        )

        # Configure client with site and auto_register enabled
        config = NetBoxConfig(
            url=request.netbox_url,
            api_token=request.api_token,
            site_name=request.site_name,
            auto_register=True
        )
        configure_netbox(config)

        # Build agent config dict from agent object
        agent_config = {
            "router_id": agent.router_id,
            "interfaces": [],
            "protocols": []
        }

        # Convert interfaces
        if agent.interfaces:
            for iface in agent.interfaces:
                agent_config["interfaces"].append({
                    "name": iface.n if hasattr(iface, 'n') else str(iface),
                    "type": iface.t if hasattr(iface, 't') else "ethernet",
                    "ip": iface.ip if hasattr(iface, 'ip') else "",
                    "enabled": iface.e if hasattr(iface, 'e') else True,
                    "mac": getattr(iface, 'mac', None),
                })

        # Convert protocols
        if agent.protos:
            for proto in agent.protos:
                proto_dict = {
                    "type": proto.t if hasattr(proto, 't') else str(proto),
                }
                # Add protocol-specific fields
                if hasattr(proto, 'area'):
                    proto_dict["area"] = proto.area
                if hasattr(proto, 'asn'):
                    proto_dict["local_as"] = proto.asn
                if hasattr(proto, 'peers'):
                    proto_dict["peers"] = proto.peers
                agent_config["protocols"].append(proto_dict)

        # Register the agent with full config
        agent_name = agent.name or agent_id
        result = await auto_register_agent(agent_name, agent_config)

        # Close client
        from agentic.mcp.netbox_mcp import get_netbox_client
        client = get_netbox_client()
        if client:
            await client.close()

        return {
            "status": "ok" if result.get("success") else "error",
            "agent_id": agent_id,
            "agent_name": agent_name,
            **result
        }

    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"NetBox MCP not available: {e}. Install httpx: pip install httpx"
        )
    except Exception as e:
        logger.error(f"NetBox registration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mcps/netbox/sites")
async def list_netbox_sites(netbox_url: str, api_token: str):
    """
    Get list of sites from NetBox.

    Useful for populating site dropdown in the wizard.
    """
    try:
        from agentic.mcp.netbox_mcp import NetBoxClient, NetBoxConfig

        config = NetBoxConfig(url=netbox_url, api_token=api_token)
        client = NetBoxClient(config)

        sites = await client.list_sites()
        await client.close()

        return {
            "status": "ok",
            "sites": [{"id": s["id"], "name": s["name"], "slug": s["slug"]} for s in sites]
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "sites": []}


@router.get("/mcps/netbox/device-roles")
async def list_netbox_device_roles(netbox_url: str, api_token: str):
    """
    Get list of device roles from NetBox.

    Useful for populating role dropdown in the wizard.
    """
    try:
        from agentic.mcp.netbox_mcp import NetBoxClient, NetBoxConfig

        config = NetBoxConfig(url=netbox_url, api_token=api_token)
        client = NetBoxClient(config)

        roles = await client.list_device_roles()
        await client.close()

        return {
            "status": "ok",
            "roles": [{"id": r["id"], "name": r["name"], "slug": r["slug"]} for r in roles]
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "roles": []}


@router.get("/mcps/netbox/devices")
async def list_netbox_devices(netbox_url: str, api_token: str,
                               site: Optional[str] = None,
                               role: Optional[str] = None):
    """
    Get list of devices from NetBox.

    Used for importing existing devices as agents.

    Args:
        netbox_url: NetBox instance URL
        api_token: NetBox API token
        site: Optional site filter
        role: Optional role filter

    Returns:
        List of devices with basic info for selection
    """
    try:
        from agentic.mcp.netbox_mcp import NetBoxClient, NetBoxConfig

        config = NetBoxConfig(url=netbox_url, api_token=api_token)
        client = NetBoxClient(config)

        devices = await client.list_devices(site=site, role=role)
        await client.close()

        return {
            "status": "ok",
            "devices": [
                {
                    "id": d["id"],
                    "name": d["name"],
                    "site": d.get("site", {}).get("name", ""),
                    "role": d.get("role", {}).get("name", ""),
                    "device_type": d.get("device_type", {}).get("model", ""),
                    "manufacturer": d.get("device_type", {}).get("manufacturer", {}).get("name", ""),
                    "status": d.get("status", {}).get("value", ""),
                    "primary_ip": d.get("primary_ip4", {}).get("address", "").split("/")[0] if d.get("primary_ip4") else "",
                    "url": d.get("url", "")
                }
                for d in devices
            ]
        }
    except Exception as e:
        logger.error(f"Error listing NetBox devices: {e}")
        return {"status": "error", "error": str(e), "devices": []}


@router.get("/mcps/netbox/devices/{device_id}/import")
async def import_netbox_device(device_id: int, netbox_url: str, api_token: str):
    """
    Import a device from NetBox and convert to agent configuration.

    Fetches full device details including interfaces and IPs,
    then maps them to the wizard's agent configuration format.

    Args:
        device_id: NetBox device ID
        netbox_url: NetBox instance URL
        api_token: NetBox API token

    Returns:
        Agent configuration ready to populate the wizard
    """
    try:
        from agentic.mcp.netbox_mcp import NetBoxClient, NetBoxConfig

        config = NetBoxConfig(url=netbox_url, api_token=api_token)
        client = NetBoxClient(config)

        agent_config = await client.import_device_as_agent_config(device_id)
        await client.close()

        if "error" in agent_config:
            return {"status": "error", "error": agent_config["error"]}

        return {
            "status": "ok",
            "agent_config": agent_config,
            "message": f"Imported device '{agent_config.get('name')}' from NetBox"
        }
    except Exception as e:
        logger.error(f"Error importing NetBox device: {e}")
        return {"status": "error", "error": str(e)}


# =============================================================================
# Custom MCP Import API (Quality Gate 9)
# =============================================================================

class CustomMCPRequest(BaseModel):
    """Request model for custom MCP import"""
    id: str = Field(..., min_length=1, max_length=64)
    name: Optional[str] = None
    description: Optional[str] = None
    url: str = Field(..., min_length=1)
    config: Dict[str, Any] = Field(default_factory=dict)
    config_fields: List[Dict[str, Any]] = Field(default_factory=list)
    enabled: bool = True


@router.post("/mcps/validate")
async def validate_custom_mcp(request: CustomMCPRequest):
    """
    Validate custom MCP JSON before import.

    Returns validation result with any errors found.
    """
    json_data = {
        "id": request.id,
        "name": request.name or request.id,
        "description": request.description or "",
        "url": request.url,
        "config": request.config,
        "config_fields": request.config_fields,
        "enabled": request.enabled
    }

    result = validate_custom_mcp_json(json_data)
    return result


@router.post("/agents/{agent_id}/mcps/custom")
async def import_custom_mcp_to_agent(agent_id: str, request: CustomMCPRequest):
    """
    Import a custom MCP to an agent.

    Args:
        agent_id: Agent ID
        request: Custom MCP configuration

    Returns the imported MCP and updated agent status.
    """
    agent = load_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    json_data = {
        "id": request.id,
        "name": request.name or request.id,
        "description": request.description or "",
        "url": request.url,
        "config": request.config,
        "config_fields": request.config_fields,
        "enabled": request.enabled
    }

    try:
        agent = add_custom_mcp_to_agent(agent, json_data)
        save_agent(agent)

        return {
            "status": "ok",
            "agent_id": agent_id,
            "imported_mcp": {
                "id": request.id,
                "name": request.name or request.id,
                "url": request.url,
                "enabled": request.enabled
            },
            "mcp_status": get_agent_mcp_status(agent)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/agents/{agent_id}/mcps/custom/{mcp_id}")
async def remove_custom_mcp(agent_id: str, mcp_id: str):
    """
    Remove a custom MCP from an agent.

    Only custom MCPs can be removed. Mandatory MCPs cannot be removed.
    """
    agent = load_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    try:
        agent = remove_custom_mcp_from_agent(agent, mcp_id)
        save_agent(agent)

        return {
            "status": "ok",
            "agent_id": agent_id,
            "removed_mcp_id": mcp_id,
            "mcp_status": get_agent_mcp_status(agent)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/agents/{agent_id}/mcps/custom")
async def list_agent_custom_mcps(agent_id: str):
    """
    List all custom MCPs on an agent.
    """
    agent = load_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    return {
        "agent_id": agent_id,
        "custom_mcps": list_custom_mcps(agent)
    }


@router.post("/mcps/custom/from-json")
async def import_mcp_from_json_string(json_string: str):
    """
    Import a custom MCP from a raw JSON string.

    Useful for pasting MCP configurations from external sources.
    """
    import json as json_module

    try:
        json_data = json_module.loads(json_string)
    except json_module.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    validation = validate_custom_mcp_json(json_data)
    if not validation["valid"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid MCP JSON: {'; '.join(validation['errors'])}"
        )

    return {
        "status": "ok",
        "validated": True,
        "normalized": validation["normalized"]
    }


# =============================================================================
# Topology Templates API
# =============================================================================

@router.get("/templates")
async def list_templates():
    """List all available topology templates"""
    try:
        from templates import get_all_templates
        return {"templates": get_all_templates()}
    except ImportError as e:
        logger.error(f"Failed to import templates: {e}")
        return {"templates": [], "error": "Templates module not available"}


@router.get("/templates/{template_id}")
async def get_template(template_id: str):
    """Get a specific template by ID"""
    try:
        from templates import get_template as get_tpl, get_all_templates
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Templates module not available: {e}")

    # Validate template ID
    valid_ids = [t["id"] for t in get_all_templates()]
    if template_id not in valid_ids:
        raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")

    template = get_tpl(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Failed to load template: {template_id}")

    return {"template": template.to_dict()}


@router.post("/session/{session_id}/load-template/{template_id}")
async def load_template_to_session(session_id: str, template_id: str):
    """
    Load a topology template into a wizard session.
    This populates all wizard steps from the template.
    """
    if session_id not in _wizard_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        from templates import get_template as get_tpl, get_all_templates
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Templates module not available: {e}")

    # Validate template ID
    valid_ids = [t["id"] for t in get_all_templates()]
    if template_id not in valid_ids:
        raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")

    template = get_tpl(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Failed to load template: {template_id}")

    session = _wizard_sessions[session_id]

    # Populate session from template
    # Docker config
    if template.docker:
        session.docker_config = DockerNetworkConfig(
            name=template.docker.n,
            subnet=template.docker.subnet,
            gateway=template.docker.gw,
            driver=template.docker.driver
        )

    # MCPs
    session.mcp_selection = MCPSelection(
        selected=[mcp.id for mcp in template.mcps]
    )

    # Agents
    session.agents = []
    for agent in template.agents:
        protocols = []
        for proto in agent.protos:
            protocols.append(proto.to_dict())

        interfaces = [iface.to_dict() for iface in agent.ifs]

        session.agents.append(AgentConfig(
            id=agent.id,
            name=agent.n,
            router_id=agent.r,
            protocol=agent.protos[0].p if agent.protos else "ospf",
            protocols=protocols,
            interfaces=interfaces,
            protocol_config=agent.protos[0].to_dict() if agent.protos else {}
        ))

    # Topology
    if template.topo and template.topo.links:
        session.topology = TopologyConfig(
            links=[
                LinkConfig(
                    id=link.id,
                    agent1_id=link.a1,
                    interface1=link.i1,
                    agent2_id=link.a2,
                    interface2=link.i2,
                    link_type=link.t,
                    cost=link.c
                )
                for link in template.topo.links
            ]
        )

    return {
        "status": "ok",
        "template_id": template_id,
        "template_name": template.n,
        "agent_count": len(session.agents),
        "link_count": len(session.topology.links) if session.topology else 0,
        "mcp_count": len(session.mcp_selection.selected) if session.mcp_selection else 0
    }


# =============================================================================
# Builder Shutdown API
# =============================================================================

@router.get("/debug/containers")
async def debug_list_containers():
    """
    Debug endpoint: List all running ASI containers with their ports.
    Useful for diagnosing port assignment issues.
    """
    try:
        import docker
        client = docker.from_env()

        containers = []
        for container in client.containers.list(all=True):
            labels = container.labels or {}
            # Check if this is an ASI container
            if any(key.startswith('asi') for key in labels):
                ports = container.ports or {}
                port_mappings = {}
                for internal, bindings in ports.items():
                    if bindings:
                        for binding in bindings:
                            port_mappings[internal] = f"{binding.get('HostIp', '0.0.0.0')}:{binding.get('HostPort', '?')}"

                containers.append({
                    "name": container.name,
                    "id": container.short_id,
                    "status": container.status,
                    "labels": labels,
                    "ports": port_mappings,
                    "image": container.image.tags[0] if container.image.tags else "unknown"
                })

        return {
            "container_count": len(containers),
            "containers": containers
        }
    except Exception as e:
        logger.error(f"Debug containers error: {e}")
        return {"error": str(e)}


@router.get("/debug/orchestrator")
async def debug_orchestrator_state():
    """
    Debug endpoint: Show orchestrator internal state.
    """
    orchestrator = get_orchestrator()
    deployments = []

    for network_id, deployment in orchestrator._deployments.items():
        agents = {}
        for agent_id, agent in deployment.agents.items():
            agents[agent_id] = {
                "status": agent.status,
                "container_id": agent.container_id,
                "container_name": agent.container_name,
                "ip_address": agent.ip_address,
                "webui_port": agent.webui_port,
                "api_port": agent.api_port,
                "error": agent.error_message
            }

        deployments.append({
            "network_id": network_id,
            "network_name": deployment.network_name,
            "status": deployment.status,
            "docker_network": deployment.docker_network,
            "agents": agents
        })

    return {
        "deployment_count": len(deployments),
        "deployments": deployments,
        "launcher_port_counter": orchestrator.launcher._port_counter
    }


@router.post("/shutdown")
async def shutdown_builder():
    """
    Gracefully shutdown the Network Builder server.
    Deployed agents will continue running.
    """
    logger.info("Shutdown requested via API")

    # Schedule shutdown after sending response
    async def delayed_shutdown():
        await asyncio.sleep(0.5)  # Let response complete
        logger.info("Initiating graceful shutdown...")
        # Send SIGTERM to self to trigger graceful shutdown
        os.kill(os.getpid(), signal.SIGTERM)

    asyncio.create_task(delayed_shutdown())

    return {
        "status": "ok",
        "message": "Builder shutdown initiated. Deployed agents will continue running."
    }
