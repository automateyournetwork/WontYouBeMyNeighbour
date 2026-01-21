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

from toon.models import (
    TOONNetwork, TOONAgent, TOONInterface, TOONProtocolConfig,
    TOONMCPConfig, TOONTopology, TOONLink, TOONDockerConfig
)
from persistence.manager import (
    PersistenceManager, list_agents, list_networks,
    save_agent, load_agent, save_network, load_network,
    create_agent_template, create_network_template, create_default_mcps
)
from orchestrator.docker_manager import check_docker_available, DockerManager
from orchestrator.network_orchestrator import NetworkOrchestrator

logger = logging.getLogger("WizardAPI")

# Create router
router = APIRouter(prefix="/api/wizard", tags=["wizard"])

# Pydantic models for API requests/responses

class DockerNetworkConfig(BaseModel):
    """Docker network configuration"""
    name: str = Field(..., min_length=1, max_length=64)
    subnet: Optional[str] = Field(None, pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$")
    gateway: Optional[str] = None
    driver: str = "bridge"


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


class WizardState(BaseModel):
    """Complete wizard state"""
    step: int = 1
    docker_config: Optional[DockerNetworkConfig] = None
    mcp_selection: Optional[MCPSelection] = None
    agents: List[AgentConfig] = Field(default_factory=list)
    network_type: Optional[NetworkTypeConfig] = None
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


# In-memory wizard sessions
_wizard_sessions: Dict[str, WizardState] = {}


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

    # Launch network
    orchestrator = NetworkOrchestrator()
    deployment = await orchestrator.launch(
        network=network,
        api_keys=request.api_keys
    )

    return {
        "status": deployment.status,
        "network_id": network.id,
        "docker_network": deployment.docker_network,
        "agents": {
            agent_id: {
                "status": agent.status,
                "ip_address": agent.ip_address,
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

    # MCPs
    mcps = []
    if session.mcp_selection:
        default_mcps = {m.id: m for m in create_default_mcps()}
        for mcp_id in session.mcp_selection.selected:
            if mcp_id in default_mcps:
                mcps.append(default_mcps[mcp_id])

        # Add custom MCPs
        for custom in session.mcp_selection.custom:
            mcps.append(TOONMCPConfig.from_dict(custom))

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
    """List all deployed networks"""
    orchestrator = NetworkOrchestrator()
    deployments = orchestrator.list_deployments()
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


@router.get("/networks/{network_id}/status")
async def get_deployed_network_status(network_id: str):
    """Get status of deployed network"""
    orchestrator = NetworkOrchestrator()
    deployment = orchestrator.get_status(network_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Network not found")

    return {
        "network_id": deployment.network_id,
        "name": deployment.network_name,
        "status": deployment.status,
        "docker_network": deployment.docker_network,
        "subnet": deployment.subnet,
        "agents": {
            agent_id: {
                "status": agent.status,
                "container_id": agent.container_id,
                "ip_address": agent.ip_address,
                "webui_port": agent.webui_port,
                "error": agent.error_message
            }
            for agent_id, agent in deployment.agents.items()
        },
        "started_at": deployment.started_at
    }


@router.post("/networks/{network_id}/stop")
async def stop_deployed_network(network_id: str, save_state: bool = True):
    """Stop a deployed network"""
    orchestrator = NetworkOrchestrator()
    success = await orchestrator.stop(network_id, save_state=save_state)
    if not success:
        raise HTTPException(status_code=404, detail="Network not found or already stopped")

    return {"status": "stopped", "network_id": network_id}


@router.get("/networks/{network_id}/agents/{agent_id}/logs")
async def get_agent_logs(network_id: str, agent_id: str, tail: int = 100):
    """Get logs from an agent"""
    orchestrator = NetworkOrchestrator()
    logs = orchestrator.get_agent_logs(network_id, agent_id, tail)
    if logs is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    return {"agent_id": agent_id, "logs": logs}


@router.get("/networks/{network_id}/health")
async def get_network_health(network_id: str):
    """Get network health check"""
    orchestrator = NetworkOrchestrator()
    health = await orchestrator.health_check(network_id)
    return health
