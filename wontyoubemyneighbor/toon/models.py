"""
TOON Models - Core data structures for Token Oriented Object Notation

These dataclasses define the structure for agents, networks, and state
with token-efficient field names for LLM consumption.

Key Naming Convention (Token Efficiency):
- id: identifier
- n: name
- t: type
- v: value/version
- c: config/count
- s: state/status
- i: interface/index
- p: protocol/port/prefix
- m: mcp/metric/mask
- a: address/area
- r: router/route/rib
- l: link/lsdb
- ts: timestamp
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
from datetime import datetime
from enum import Enum
import json


class ProtocolType(Enum):
    """Supported routing protocols"""
    OSPF = "ospf"
    OSPFV3 = "ospfv3"
    IBGP = "ibgp"
    EBGP = "ebgp"


class InterfaceType(Enum):
    """Network interface types"""
    ETHERNET = "eth"
    LOOPBACK = "lo"
    VLAN = "vlan"
    TUNNEL = "tun"
    GRE = "gre"  # GRE tunnel (RFC 2784/2890)


class TunnelType(Enum):
    """Tunnel encapsulation types"""
    GRE = "gre"           # Generic Routing Encapsulation (RFC 2784)
    GRE_TAP = "gretap"    # GRE with Ethernet (L2)
    IPIP = "ipip"         # IP-in-IP encapsulation
    VXLAN = "vxlan"       # VXLAN overlay
    SIT = "sit"           # IPv6-in-IPv4 tunnel


class MCPType(Enum):
    """Supported MCP servers"""
    GAIT = "gait"
    MARKMAP = "markmap"
    PYATS = "pyats"
    SERVICENOW = "servicenow"
    NETBOX = "netbox"
    RFC = "rfc"
    SLACK = "slack"
    GITHUB = "github"
    CUSTOM = "custom"


@dataclass
class TOONInterface:
    """
    Network interface definition

    Token-efficient keys:
    - id: interface identifier
    - n: name (e.g., eth0)
    - t: type (ethernet, loopback, etc.)
    - a: addresses (list of IP/prefix)
    - m: mac address
    - s: state (up/down)
    - mtu: maximum transmission unit
    - tun: tunnel config (for tunnel interfaces)
    """
    id: str
    n: str  # name
    t: str = "eth"  # type
    a: List[str] = field(default_factory=list)  # addresses
    m: Optional[str] = None  # mac
    s: str = "up"  # state
    mtu: int = 1500
    tun: Optional[Dict[str, Any]] = None  # tunnel config

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TOONInterface":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TOONTunnelConfig:
    """
    GRE/Tunnel interface configuration

    Token-efficient keys:
    - tt: tunnel type (gre, gretap, ipip, vxlan)
    - src: source/local IP (physical interface)
    - dst: destination/remote IP
    - key: GRE key (optional, for traffic identification)
    - csum: enable checksum
    - seq: enable sequence numbers
    - ka: keepalive interval (seconds, 0 to disable)
    - ttl: TTL for outer packets
    - tos: TOS/DSCP for outer packets
    - desc: description
    """
    tt: str = "gre"  # tunnel type
    src: str = ""  # source/local IP
    dst: str = ""  # destination/remote IP
    key: Optional[int] = None  # GRE key
    csum: bool = False  # checksum
    seq: bool = False  # sequence numbers
    ka: int = 10  # keepalive interval
    ttl: int = 255  # outer TTL
    tos: int = 192  # outer TOS (CS6 for network control)
    desc: str = ""  # description

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TOONTunnelConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TOONProtocolConfig:
    """
    Protocol-specific configuration

    Token-efficient keys:
    - p: protocol type (ospf, ibgp, ebgp)
    - r: router-id
    - a: area (for OSPF)
    - asn: AS number (for BGP)
    - peers: list of peer configs
    - nets: networks to advertise
    - opts: additional options
    """
    p: str  # protocol
    r: str  # router-id
    a: Optional[str] = None  # area
    asn: Optional[int] = None  # AS number
    peers: List[Dict[str, Any]] = field(default_factory=list)
    nets: List[str] = field(default_factory=list)  # networks
    opts: Dict[str, Any] = field(default_factory=dict)  # options

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None and v != []}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TOONProtocolConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TOONMCPConfig:
    """
    MCP Server configuration

    Token-efficient keys:
    - id: MCP identifier
    - t: type (gait, markmap, pyats, etc.)
    - n: display name
    - d: description
    - url: server URL or repo
    - c: configuration dict
    - e: enabled flag
    """
    id: str
    t: str  # type
    url: str
    n: str = ""  # display name
    d: str = ""  # description
    c: Dict[str, Any] = field(default_factory=dict)  # config
    e: bool = True  # enabled

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TOONMCPConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TOONRuntimeState:
    """
    Agent runtime state (RIB, LSDB, protocol state)

    Token-efficient keys:
    - ts: timestamp
    - rib: routing information base
    - lsdb: link state database
    - nbrs: neighbors
    - peers: BGP peers state
    - metrics: performance metrics
    """
    ts: str  # timestamp ISO format
    rib: List[Dict[str, Any]] = field(default_factory=list)
    lsdb: List[Dict[str, Any]] = field(default_factory=list)
    nbrs: List[Dict[str, Any]] = field(default_factory=list)  # OSPF neighbors
    peers: List[Dict[str, Any]] = field(default_factory=list)  # BGP peers
    metrics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TOONRuntimeState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def capture_now(cls) -> "TOONRuntimeState":
        """Create a new runtime state with current timestamp"""
        return cls(ts=datetime.now().isoformat())


@dataclass
class TOONAgent:
    """
    Complete agent definition with config and optional runtime state

    Token-efficient keys:
    - id: unique agent identifier
    - n: display name
    - v: version
    - r: router-id
    - ifs: interfaces list
    - protos: protocol configs
    - mcps: MCP server configs
    - state: runtime state (optional)
    - meta: metadata
    """
    id: str
    n: str  # name
    r: str  # router-id
    v: str = "1.0"  # version
    ifs: List[TOONInterface] = field(default_factory=list)  # interfaces
    protos: List[TOONProtocolConfig] = field(default_factory=list)  # protocols
    mcps: List[TOONMCPConfig] = field(default_factory=list)  # MCPs
    state: Optional[TOONRuntimeState] = None  # runtime state
    meta: Dict[str, Any] = field(default_factory=dict)  # metadata

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "n": self.n,
            "v": self.v,
            "r": self.r,
            "ifs": [i.to_dict() for i in self.ifs],
            "protos": [p.to_dict() for p in self.protos],
            "mcps": [m.to_dict() for m in self.mcps],
            "meta": self.meta
        }
        if self.state:
            result["state"] = self.state.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TOONAgent":
        return cls(
            id=data["id"],
            n=data["n"],
            r=data["r"],
            v=data.get("v", "1.0"),
            ifs=[TOONInterface.from_dict(i) for i in data.get("ifs", [])],
            protos=[TOONProtocolConfig.from_dict(p) for p in data.get("protos", [])],
            mcps=[TOONMCPConfig.from_dict(m) for m in data.get("mcps", [])],
            state=TOONRuntimeState.from_dict(data["state"]) if data.get("state") else None,
            meta=data.get("meta", {})
        )

    def to_toon(self) -> str:
        """Serialize to TOON format string"""
        from .format import serialize
        return serialize(self)

    @classmethod
    def from_toon(cls, toon_str: str) -> "TOONAgent":
        """Deserialize from TOON format string"""
        from .format import deserialize
        return deserialize(toon_str, cls)


@dataclass
class TOONLink:
    """
    Network link between two agents

    Token-efficient keys:
    - id: link identifier
    - a1: agent 1 ID
    - i1: interface 1 ID
    - a2: agent 2 ID
    - i2: interface 2 ID
    - t: link type
    - c: cost/metric
    """
    id: str
    a1: str  # agent 1
    i1: str  # interface 1
    a2: str  # agent 2
    i2: str  # interface 2
    t: str = "ethernet"  # type
    c: int = 10  # cost

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TOONLink":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TOONTopology:
    """
    Network topology definition

    Token-efficient keys:
    - links: list of links
    - layout: visual layout hints
    """
    links: List[TOONLink] = field(default_factory=list)
    layout: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "links": [l.to_dict() for l in self.links],
            "layout": self.layout
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TOONTopology":
        return cls(
            links=[TOONLink.from_dict(l) for l in data.get("links", [])],
            layout=data.get("layout", {})
        )


@dataclass
class TOONDockerConfig:
    """
    Docker network configuration

    Token-efficient keys:
    - n: network name
    - driver: network driver
    - subnet: CIDR subnet
    - gw: gateway
    - opts: additional options
    """
    n: str  # name
    driver: str = "bridge"
    subnet: Optional[str] = None
    gw: Optional[str] = None  # gateway
    opts: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TOONDockerConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TOONNetwork:
    """
    Complete network definition with agents and topology

    Token-efficient keys:
    - id: unique network identifier
    - n: display name
    - v: version
    - created: creation timestamp
    - modified: last modified timestamp
    - docker: Docker network config
    - agents: list of agents
    - topo: topology
    - mcps: global MCP configs
    - meta: metadata
    """
    id: str
    n: str  # name
    v: str = "1.0"  # version
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    modified: str = field(default_factory=lambda: datetime.now().isoformat())
    docker: Optional[TOONDockerConfig] = None
    agents: List[TOONAgent] = field(default_factory=list)
    topo: Optional[TOONTopology] = None
    mcps: List[TOONMCPConfig] = field(default_factory=list)  # global MCPs
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "n": self.n,
            "v": self.v,
            "created": self.created,
            "modified": self.modified,
            "agents": [a.to_dict() for a in self.agents],
            "mcps": [m.to_dict() for m in self.mcps],
            "meta": self.meta
        }
        if self.docker:
            result["docker"] = self.docker.to_dict()
        if self.topo:
            result["topo"] = self.topo.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TOONNetwork":
        return cls(
            id=data["id"],
            n=data["n"],
            v=data.get("v", "1.0"),
            created=data.get("created", datetime.now().isoformat()),
            modified=data.get("modified", datetime.now().isoformat()),
            docker=TOONDockerConfig.from_dict(data["docker"]) if data.get("docker") else None,
            agents=[TOONAgent.from_dict(a) for a in data.get("agents", [])],
            topo=TOONTopology.from_dict(data["topo"]) if data.get("topo") else None,
            mcps=[TOONMCPConfig.from_dict(m) for m in data.get("mcps", [])],
            meta=data.get("meta", {})
        )

    def to_toon(self) -> str:
        """Serialize to TOON format string"""
        from .format import serialize
        return serialize(self)

    @classmethod
    def from_toon(cls, toon_str: str) -> "TOONNetwork":
        """Deserialize from TOON format string"""
        from .format import deserialize
        return deserialize(toon_str, cls)

    def update_modified(self):
        """Update the modified timestamp"""
        self.modified = datetime.now().isoformat()

    def get_agent(self, agent_id: str) -> Optional[TOONAgent]:
        """Get agent by ID"""
        for agent in self.agents:
            if agent.id == agent_id:
                return agent
        return None

    def add_agent(self, agent: TOONAgent):
        """Add an agent to the network"""
        self.agents.append(agent)
        self.update_modified()

    def remove_agent(self, agent_id: str) -> bool:
        """Remove an agent by ID"""
        for i, agent in enumerate(self.agents):
            if agent.id == agent_id:
                del self.agents[i]
                self.update_modified()
                return True
        return False
