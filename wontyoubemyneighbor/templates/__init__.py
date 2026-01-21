"""
Preloaded Topology Templates

7 production-ready network topology templates per spec:
1. Small Office - 3 routers with OSPF
2. Enterprise Campus - Core-distribution-access with OSPF areas
3. Datacenter Fabric - Spine-leaf with BGP-EVPN
4. Service Provider - Multi-AS with iBGP/eBGP and MPLS
5. Campus Dual-Stack - IPv4/IPv6 with OSPFv2/v3
6. Multi-Region WAN - Geographically distributed with BGP
7. Internet Exchange Point - Route server with multiple peers
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from toon.models import (
    TOONNetwork, TOONAgent, TOONInterface, TOONProtocolConfig,
    TOONTopology, TOONLink, TOONDockerConfig
)
from persistence.manager import create_default_mcps, get_mandatory_mcps


def get_all_templates() -> List[Dict[str, Any]]:
    """
    Get metadata for all available templates.

    Returns:
        List of template metadata dicts
    """
    return [
        {
            "id": "small_office",
            "name": "Small Office",
            "description": "3 routers with OSPF backbone",
            "agent_count": 3,
            "protocols": ["OSPF"],
            "use_case": "Small branch office or lab"
        },
        {
            "id": "enterprise_campus",
            "name": "Enterprise Campus",
            "description": "Core-distribution-access with OSPF areas",
            "agent_count": 5,
            "protocols": ["OSPF"],
            "use_case": "Corporate campus network"
        },
        {
            "id": "datacenter_fabric",
            "name": "Datacenter Fabric",
            "description": "Spine-leaf topology with BGP-EVPN",
            "agent_count": 6,
            "protocols": ["BGP", "VXLAN", "EVPN"],
            "use_case": "Modern datacenter"
        },
        {
            "id": "service_provider",
            "name": "Service Provider",
            "description": "Multi-AS network with iBGP/eBGP and MPLS",
            "agent_count": 6,
            "protocols": ["BGP", "OSPF", "MPLS"],
            "use_case": "ISP backbone"
        },
        {
            "id": "campus_dual_stack",
            "name": "Campus Dual-Stack",
            "description": "IPv4/IPv6 with OSPFv2 and OSPFv3",
            "agent_count": 4,
            "protocols": ["OSPF", "OSPFv3"],
            "use_case": "IPv6-ready campus"
        },
        {
            "id": "multi_region_wan",
            "name": "Multi-Region WAN",
            "description": "Geographically distributed with BGP",
            "agent_count": 6,
            "protocols": ["BGP", "OSPF"],
            "use_case": "Global enterprise WAN"
        },
        {
            "id": "internet_exchange",
            "name": "Internet Exchange Point",
            "description": "Route server with multiple ASN peers",
            "agent_count": 5,
            "protocols": ["BGP"],
            "use_case": "IXP peering fabric"
        }
    ]


def get_template(template_id: str) -> Optional[TOONNetwork]:
    """
    Get a specific template by ID.

    Args:
        template_id: Template identifier

    Returns:
        TOONNetwork template or None if not found
    """
    templates = {
        "small_office": create_small_office_template,
        "enterprise_campus": create_enterprise_campus_template,
        "datacenter_fabric": create_datacenter_fabric_template,
        "service_provider": create_service_provider_template,
        "campus_dual_stack": create_campus_dual_stack_template,
        "multi_region_wan": create_multi_region_wan_template,
        "internet_exchange": create_internet_exchange_template
    }

    creator = templates.get(template_id)
    if creator:
        return creator()
    return None


def _create_agent(
    agent_id: str,
    name: str,
    router_id: str,
    interfaces: List[Dict[str, Any]],
    protocols: List[Dict[str, Any]]
) -> TOONAgent:
    """Helper to create a TOONAgent with mandatory MCPs."""
    return TOONAgent(
        id=agent_id,
        n=name,
        r=router_id,
        ifs=[TOONInterface.from_dict(i) for i in interfaces],
        protos=[TOONProtocolConfig.from_dict(p) for p in protocols],
        mcps=get_mandatory_mcps(),
        meta={"template": True, "created": datetime.now().isoformat()}
    )


# =============================================================================
# Template 1: Small Office (3 routers, OSPF)
# =============================================================================

def create_small_office_template() -> TOONNetwork:
    """
    Small Office: 3 routers with OSPF backbone

    Topology:
        R1 (HQ) --- R2 (Branch1) --- R3 (Branch2)
    """
    agents = [
        _create_agent(
            agent_id="r1-hq",
            name="Headquarters Router",
            router_id="10.0.0.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.20.1.1/24"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.20.2.1/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.0.0.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.0.0.1", "a": "0.0.0.0"}
            ]
        ),
        _create_agent(
            agent_id="r2-branch1",
            name="Branch 1 Router",
            router_id="10.0.0.2",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.20.1.2/24"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.20.3.1/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.0.0.2/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.0.0.2", "a": "0.0.0.0"}
            ]
        ),
        _create_agent(
            agent_id="r3-branch2",
            name="Branch 2 Router",
            router_id="10.0.0.3",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.20.2.2/24"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.20.3.2/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.0.0.3/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.0.0.3", "a": "0.0.0.0"}
            ]
        )
    ]

    links = [
        TOONLink(id="link1", a1="r1-hq", i1="eth0", a2="r2-branch1", i2="eth0", t="ethernet", c=10),
        TOONLink(id="link2", a1="r1-hq", i1="eth1", a2="r3-branch2", i2="eth0", t="ethernet", c=10),
        TOONLink(id="link3", a1="r2-branch1", i1="eth1", a2="r3-branch2", i2="eth1", t="ethernet", c=20)
    ]

    return TOONNetwork(
        id="small-office",
        n="Small Office Network",
        docker=TOONDockerConfig(n="small-office", driver="bridge", subnet="172.20.0.0/16"),
        agents=agents,
        topo=TOONTopology(links=links),
        mcps=get_mandatory_mcps(),
        meta={
            "template": "small_office",
            "description": "3 routers with OSPF backbone",
            "use_case": "Small branch office or lab"
        }
    )


# =============================================================================
# Template 2: Enterprise Campus (5 routers, OSPF areas)
# =============================================================================

def create_enterprise_campus_template() -> TOONNetwork:
    """
    Enterprise Campus: Core-Distribution-Access with OSPF areas

    Topology:
        Core1 (Area 0) --- Core2 (Area 0)
           |                   |
        Dist1 (Area 1)    Dist2 (Area 2)
           |                   |
        Access1           Access2
    """
    agents = [
        _create_agent(
            agent_id="core1",
            name="Core Switch 1",
            router_id="10.1.0.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.21.0.1/24"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.21.1.1/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.1.0.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.1.0.1", "a": "0.0.0.0"}
            ]
        ),
        _create_agent(
            agent_id="core2",
            name="Core Switch 2",
            router_id="10.1.0.2",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.21.0.2/24"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.21.2.1/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.1.0.2/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.1.0.2", "a": "0.0.0.0"}
            ]
        ),
        _create_agent(
            agent_id="dist1",
            name="Distribution Switch 1",
            router_id="10.1.1.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.21.1.2/24"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.21.10.1/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.1.1.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.1.1.1", "a": "0.0.0.1"}
            ]
        ),
        _create_agent(
            agent_id="dist2",
            name="Distribution Switch 2",
            router_id="10.1.2.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.21.2.2/24"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.21.20.1/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.1.2.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.1.2.1", "a": "0.0.0.2"}
            ]
        ),
        _create_agent(
            agent_id="access1",
            name="Access Switch 1",
            router_id="10.1.10.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.21.10.2/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.1.10.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.1.10.1", "a": "0.0.0.1"}
            ]
        )
    ]

    links = [
        TOONLink(id="core-core", a1="core1", i1="eth0", a2="core2", i2="eth0", t="ethernet", c=10),
        TOONLink(id="core1-dist1", a1="core1", i1="eth1", a2="dist1", i2="eth0", t="ethernet", c=10),
        TOONLink(id="core2-dist2", a1="core2", i1="eth1", a2="dist2", i2="eth0", t="ethernet", c=10),
        TOONLink(id="dist1-access1", a1="dist1", i1="eth1", a2="access1", i2="eth0", t="ethernet", c=10)
    ]

    return TOONNetwork(
        id="enterprise-campus",
        n="Enterprise Campus Network",
        docker=TOONDockerConfig(n="enterprise-campus", driver="bridge", subnet="172.21.0.0/16"),
        agents=agents,
        topo=TOONTopology(links=links),
        mcps=get_mandatory_mcps(),
        meta={
            "template": "enterprise_campus",
            "description": "Core-distribution-access with OSPF areas",
            "use_case": "Corporate campus network"
        }
    )


# =============================================================================
# Template 3: Datacenter Fabric (6 routers, spine-leaf with BGP)
# =============================================================================

def create_datacenter_fabric_template() -> TOONNetwork:
    """
    Datacenter Fabric: Spine-Leaf with BGP-EVPN

    Topology:
        Spine1 (AS 65000) --- Spine2 (AS 65000)
         /   \\               /   \\
       Leaf1  Leaf2       Leaf3  Leaf4
    """
    agents = [
        _create_agent(
            agent_id="spine1",
            name="Spine Switch 1",
            router_id="10.2.0.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.22.0.1/24"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.22.1.1/24"], "s": "up"},
                {"id": "eth2", "n": "eth2", "t": "eth", "a": ["172.22.2.1/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.2.0.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ibgp", "r": "10.2.0.1", "asn": 65000, "peers": [
                    {"ip": "10.2.0.2", "asn": 65000}
                ]},
                {"p": "evpn", "r": "10.2.0.1"}
            ]
        ),
        _create_agent(
            agent_id="spine2",
            name="Spine Switch 2",
            router_id="10.2.0.2",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.22.0.2/24"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.22.3.1/24"], "s": "up"},
                {"id": "eth2", "n": "eth2", "t": "eth", "a": ["172.22.4.1/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.2.0.2/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ibgp", "r": "10.2.0.2", "asn": 65000, "peers": [
                    {"ip": "10.2.0.1", "asn": 65000}
                ]},
                {"p": "evpn", "r": "10.2.0.2"}
            ]
        ),
        _create_agent(
            agent_id="leaf1",
            name="Leaf Switch 1",
            router_id="10.2.1.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.22.1.2/24"], "s": "up"},
                {"id": "vxlan0", "n": "vxlan0", "t": "vxlan", "a": [], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.2.1.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ibgp", "r": "10.2.1.1", "asn": 65000, "peers": [
                    {"ip": "10.2.0.1", "asn": 65000}
                ]},
                {"p": "vxlan", "r": "10.2.1.1", "vnis": [100, 200]},
                {"p": "evpn", "r": "10.2.1.1"}
            ]
        ),
        _create_agent(
            agent_id="leaf2",
            name="Leaf Switch 2",
            router_id="10.2.1.2",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.22.2.2/24"], "s": "up"},
                {"id": "vxlan0", "n": "vxlan0", "t": "vxlan", "a": [], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.2.1.2/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ibgp", "r": "10.2.1.2", "asn": 65000, "peers": [
                    {"ip": "10.2.0.1", "asn": 65000}
                ]},
                {"p": "vxlan", "r": "10.2.1.2", "vnis": [100, 200]},
                {"p": "evpn", "r": "10.2.1.2"}
            ]
        ),
        _create_agent(
            agent_id="leaf3",
            name="Leaf Switch 3",
            router_id="10.2.1.3",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.22.3.2/24"], "s": "up"},
                {"id": "vxlan0", "n": "vxlan0", "t": "vxlan", "a": [], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.2.1.3/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ibgp", "r": "10.2.1.3", "asn": 65000, "peers": [
                    {"ip": "10.2.0.2", "asn": 65000}
                ]},
                {"p": "vxlan", "r": "10.2.1.3", "vnis": [100, 200]},
                {"p": "evpn", "r": "10.2.1.3"}
            ]
        ),
        _create_agent(
            agent_id="leaf4",
            name="Leaf Switch 4",
            router_id="10.2.1.4",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.22.4.2/24"], "s": "up"},
                {"id": "vxlan0", "n": "vxlan0", "t": "vxlan", "a": [], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.2.1.4/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ibgp", "r": "10.2.1.4", "asn": 65000, "peers": [
                    {"ip": "10.2.0.2", "asn": 65000}
                ]},
                {"p": "vxlan", "r": "10.2.1.4", "vnis": [100, 200]},
                {"p": "evpn", "r": "10.2.1.4"}
            ]
        )
    ]

    links = [
        TOONLink(id="spine-spine", a1="spine1", i1="eth0", a2="spine2", i2="eth0", t="ethernet", c=10),
        TOONLink(id="spine1-leaf1", a1="spine1", i1="eth1", a2="leaf1", i2="eth0", t="ethernet", c=10),
        TOONLink(id="spine1-leaf2", a1="spine1", i1="eth2", a2="leaf2", i2="eth0", t="ethernet", c=10),
        TOONLink(id="spine2-leaf3", a1="spine2", i1="eth1", a2="leaf3", i2="eth0", t="ethernet", c=10),
        TOONLink(id="spine2-leaf4", a1="spine2", i1="eth2", a2="leaf4", i2="eth0", t="ethernet", c=10)
    ]

    return TOONNetwork(
        id="datacenter-fabric",
        n="Datacenter Fabric Network",
        docker=TOONDockerConfig(n="datacenter-fabric", driver="bridge", subnet="172.22.0.0/16"),
        agents=agents,
        topo=TOONTopology(links=links),
        mcps=get_mandatory_mcps(),
        meta={
            "template": "datacenter_fabric",
            "description": "Spine-leaf topology with BGP-EVPN",
            "use_case": "Modern datacenter"
        }
    )


# =============================================================================
# Template 4: Service Provider (6 routers, multi-AS with MPLS)
# =============================================================================

def create_service_provider_template() -> TOONNetwork:
    """
    Service Provider: Multi-AS with iBGP/eBGP and MPLS

    Topology:
        PE1 (AS 65001) --- P1 --- P2 --- PE2 (AS 65001)
                           |      |
                          CE1    CE2
                       (AS 65100) (AS 65200)
    """
    agents = [
        _create_agent(
            agent_id="pe1",
            name="Provider Edge 1",
            router_id="10.3.0.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.23.1.1/24"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.23.10.1/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.3.0.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.3.0.1", "a": "0.0.0.0"},
                {"p": "ibgp", "r": "10.3.0.1", "asn": 65001, "peers": [
                    {"ip": "10.3.0.4", "asn": 65001}
                ]},
                {"p": "mpls", "r": "10.3.0.1"},
                {"p": "ldp", "r": "10.3.0.1"}
            ]
        ),
        _create_agent(
            agent_id="p1",
            name="Provider Core 1",
            router_id="10.3.0.2",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.23.1.2/24"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.23.2.1/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.3.0.2/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.3.0.2", "a": "0.0.0.0"},
                {"p": "mpls", "r": "10.3.0.2"},
                {"p": "ldp", "r": "10.3.0.2"}
            ]
        ),
        _create_agent(
            agent_id="p2",
            name="Provider Core 2",
            router_id="10.3.0.3",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.23.2.2/24"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.23.3.1/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.3.0.3/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.3.0.3", "a": "0.0.0.0"},
                {"p": "mpls", "r": "10.3.0.3"},
                {"p": "ldp", "r": "10.3.0.3"}
            ]
        ),
        _create_agent(
            agent_id="pe2",
            name="Provider Edge 2",
            router_id="10.3.0.4",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.23.3.2/24"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.23.20.1/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.3.0.4/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.3.0.4", "a": "0.0.0.0"},
                {"p": "ibgp", "r": "10.3.0.4", "asn": 65001, "peers": [
                    {"ip": "10.3.0.1", "asn": 65001}
                ]},
                {"p": "mpls", "r": "10.3.0.4"},
                {"p": "ldp", "r": "10.3.0.4"}
            ]
        ),
        _create_agent(
            agent_id="ce1",
            name="Customer Edge 1",
            router_id="10.3.100.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.23.10.2/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.3.100.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ebgp", "r": "10.3.100.1", "asn": 65100, "peers": [
                    {"ip": "172.23.10.1", "asn": 65001}
                ], "nets": ["192.168.100.0/24"]}
            ]
        ),
        _create_agent(
            agent_id="ce2",
            name="Customer Edge 2",
            router_id="10.3.200.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.23.20.2/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.3.200.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ebgp", "r": "10.3.200.1", "asn": 65200, "peers": [
                    {"ip": "172.23.20.1", "asn": 65001}
                ], "nets": ["192.168.200.0/24"]}
            ]
        )
    ]

    links = [
        TOONLink(id="pe1-p1", a1="pe1", i1="eth0", a2="p1", i2="eth0", t="ethernet", c=10),
        TOONLink(id="p1-p2", a1="p1", i1="eth1", a2="p2", i2="eth0", t="ethernet", c=10),
        TOONLink(id="p2-pe2", a1="p2", i1="eth1", a2="pe2", i2="eth0", t="ethernet", c=10),
        TOONLink(id="pe1-ce1", a1="pe1", i1="eth1", a2="ce1", i2="eth0", t="ethernet", c=10),
        TOONLink(id="pe2-ce2", a1="pe2", i1="eth1", a2="ce2", i2="eth0", t="ethernet", c=10)
    ]

    return TOONNetwork(
        id="service-provider",
        n="Service Provider Network",
        docker=TOONDockerConfig(n="service-provider", driver="bridge", subnet="172.23.0.0/16"),
        agents=agents,
        topo=TOONTopology(links=links),
        mcps=get_mandatory_mcps(),
        meta={
            "template": "service_provider",
            "description": "Multi-AS network with iBGP/eBGP and MPLS",
            "use_case": "ISP backbone"
        }
    )


# =============================================================================
# Template 5: Campus Dual-Stack (4 routers, IPv4/IPv6)
# =============================================================================

def create_campus_dual_stack_template() -> TOONNetwork:
    """
    Campus Dual-Stack: IPv4/IPv6 with OSPFv2 and OSPFv3

    Topology:
        Core1 --- Core2
         |   \\   /   |
        Acc1  \\ /   Acc2
    """
    agents = [
        _create_agent(
            agent_id="core1-ds",
            name="Core Router 1 (Dual-Stack)",
            router_id="10.4.0.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.24.0.1/24", "2001:db8:1::1/64"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.24.1.1/24", "2001:db8:2::1/64"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.4.0.1/32", "2001:db8::1/128"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.4.0.1", "a": "0.0.0.0"},
                {"p": "ospfv3", "r": "10.4.0.1", "a": "0.0.0.0"}
            ]
        ),
        _create_agent(
            agent_id="core2-ds",
            name="Core Router 2 (Dual-Stack)",
            router_id="10.4.0.2",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.24.0.2/24", "2001:db8:1::2/64"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.24.2.1/24", "2001:db8:3::1/64"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.4.0.2/32", "2001:db8::2/128"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.4.0.2", "a": "0.0.0.0"},
                {"p": "ospfv3", "r": "10.4.0.2", "a": "0.0.0.0"}
            ]
        ),
        _create_agent(
            agent_id="acc1-ds",
            name="Access Router 1 (Dual-Stack)",
            router_id="10.4.1.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.24.1.2/24", "2001:db8:2::2/64"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.4.1.1/32", "2001:db8:100::1/128"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.4.1.1", "a": "0.0.0.0"},
                {"p": "ospfv3", "r": "10.4.1.1", "a": "0.0.0.0"}
            ]
        ),
        _create_agent(
            agent_id="acc2-ds",
            name="Access Router 2 (Dual-Stack)",
            router_id="10.4.1.2",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.24.2.2/24", "2001:db8:3::2/64"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.4.1.2/32", "2001:db8:200::1/128"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.4.1.2", "a": "0.0.0.0"},
                {"p": "ospfv3", "r": "10.4.1.2", "a": "0.0.0.0"}
            ]
        )
    ]

    links = [
        TOONLink(id="core-core", a1="core1-ds", i1="eth0", a2="core2-ds", i2="eth0", t="ethernet", c=10),
        TOONLink(id="core1-acc1", a1="core1-ds", i1="eth1", a2="acc1-ds", i2="eth0", t="ethernet", c=10),
        TOONLink(id="core2-acc2", a1="core2-ds", i1="eth1", a2="acc2-ds", i2="eth0", t="ethernet", c=10)
    ]

    return TOONNetwork(
        id="campus-dual-stack",
        n="Campus Dual-Stack Network",
        docker=TOONDockerConfig(n="campus-dual-stack", driver="bridge", subnet="172.24.0.0/16"),
        agents=agents,
        topo=TOONTopology(links=links),
        mcps=get_mandatory_mcps(),
        meta={
            "template": "campus_dual_stack",
            "description": "IPv4/IPv6 with OSPFv2 and OSPFv3",
            "use_case": "IPv6-ready campus"
        }
    )


# =============================================================================
# Template 6: Multi-Region WAN (6 routers, geographically distributed)
# =============================================================================

def create_multi_region_wan_template() -> TOONNetwork:
    """
    Multi-Region WAN: Geographically distributed with BGP

    Topology:
        Region A          Region B          Region C
        [HQ-East]   ---   [HQ-West]   ---   [HQ-EMEA]
           |                 |                 |
        [Branch-A1]      [Branch-B1]      [Branch-C1]
    """
    agents = [
        _create_agent(
            agent_id="hq-east",
            name="HQ East Router",
            router_id="10.5.1.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.25.1.1/24"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.25.10.1/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.5.1.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.5.1.1", "a": "0.0.0.1"},
                {"p": "ibgp", "r": "10.5.1.1", "asn": 65010, "peers": [
                    {"ip": "10.5.2.1", "asn": 65010},
                    {"ip": "10.5.3.1", "asn": 65010}
                ]}
            ]
        ),
        _create_agent(
            agent_id="hq-west",
            name="HQ West Router",
            router_id="10.5.2.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.25.1.2/24"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.25.2.1/24"], "s": "up"},
                {"id": "eth2", "n": "eth2", "t": "eth", "a": ["172.25.20.1/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.5.2.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.5.2.1", "a": "0.0.0.2"},
                {"p": "ibgp", "r": "10.5.2.1", "asn": 65010, "peers": [
                    {"ip": "10.5.1.1", "asn": 65010},
                    {"ip": "10.5.3.1", "asn": 65010}
                ]}
            ]
        ),
        _create_agent(
            agent_id="hq-emea",
            name="HQ EMEA Router",
            router_id="10.5.3.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.25.2.2/24"], "s": "up"},
                {"id": "eth1", "n": "eth1", "t": "eth", "a": ["172.25.30.1/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.5.3.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.5.3.1", "a": "0.0.0.3"},
                {"p": "ibgp", "r": "10.5.3.1", "asn": 65010, "peers": [
                    {"ip": "10.5.1.1", "asn": 65010},
                    {"ip": "10.5.2.1", "asn": 65010}
                ]}
            ]
        ),
        _create_agent(
            agent_id="branch-a1",
            name="Branch A1 Router",
            router_id="10.5.10.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.25.10.2/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.5.10.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.5.10.1", "a": "0.0.0.1"}
            ]
        ),
        _create_agent(
            agent_id="branch-b1",
            name="Branch B1 Router",
            router_id="10.5.20.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.25.20.2/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.5.20.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.5.20.1", "a": "0.0.0.2"}
            ]
        ),
        _create_agent(
            agent_id="branch-c1",
            name="Branch C1 Router",
            router_id="10.5.30.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.25.30.2/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.5.30.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ospf", "r": "10.5.30.1", "a": "0.0.0.3"}
            ]
        )
    ]

    links = [
        TOONLink(id="east-west", a1="hq-east", i1="eth0", a2="hq-west", i2="eth0", t="ethernet", c=100),
        TOONLink(id="west-emea", a1="hq-west", i1="eth1", a2="hq-emea", i2="eth0", t="ethernet", c=200),
        TOONLink(id="east-branch-a1", a1="hq-east", i1="eth1", a2="branch-a1", i2="eth0", t="ethernet", c=10),
        TOONLink(id="west-branch-b1", a1="hq-west", i1="eth2", a2="branch-b1", i2="eth0", t="ethernet", c=10),
        TOONLink(id="emea-branch-c1", a1="hq-emea", i1="eth1", a2="branch-c1", i2="eth0", t="ethernet", c=10)
    ]

    return TOONNetwork(
        id="multi-region-wan",
        n="Multi-Region WAN Network",
        docker=TOONDockerConfig(n="multi-region-wan", driver="bridge", subnet="172.25.0.0/16"),
        agents=agents,
        topo=TOONTopology(links=links),
        mcps=get_mandatory_mcps(),
        meta={
            "template": "multi_region_wan",
            "description": "Geographically distributed with BGP",
            "use_case": "Global enterprise WAN"
        }
    )


# =============================================================================
# Template 7: Internet Exchange Point (5 routers, route server + peers)
# =============================================================================

def create_internet_exchange_template() -> TOONNetwork:
    """
    Internet Exchange Point: Route server with multiple ASN peers

    Topology:
              Route Server (RS)
             /    |    |    \\
           ISP1  ISP2  ISP3  ISP4
    """
    agents = [
        _create_agent(
            agent_id="rs",
            name="Route Server",
            router_id="10.6.0.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.26.0.1/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.6.0.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ebgp", "r": "10.6.0.1", "asn": 65000, "peers": [
                    {"ip": "172.26.0.11", "asn": 65001},
                    {"ip": "172.26.0.12", "asn": 65002},
                    {"ip": "172.26.0.13", "asn": 65003},
                    {"ip": "172.26.0.14", "asn": 65004}
                ]}
            ]
        ),
        _create_agent(
            agent_id="isp1",
            name="ISP 1 (AS 65001)",
            router_id="10.6.1.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.26.0.11/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.6.1.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ebgp", "r": "10.6.1.1", "asn": 65001, "peers": [
                    {"ip": "172.26.0.1", "asn": 65000}
                ], "nets": ["203.0.113.0/24"]}
            ]
        ),
        _create_agent(
            agent_id="isp2",
            name="ISP 2 (AS 65002)",
            router_id="10.6.2.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.26.0.12/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.6.2.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ebgp", "r": "10.6.2.1", "asn": 65002, "peers": [
                    {"ip": "172.26.0.1", "asn": 65000}
                ], "nets": ["198.51.100.0/24"]}
            ]
        ),
        _create_agent(
            agent_id="isp3",
            name="ISP 3 (AS 65003)",
            router_id="10.6.3.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.26.0.13/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.6.3.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ebgp", "r": "10.6.3.1", "asn": 65003, "peers": [
                    {"ip": "172.26.0.1", "asn": 65000}
                ], "nets": ["192.0.2.0/24"]}
            ]
        ),
        _create_agent(
            agent_id="isp4",
            name="ISP 4 (AS 65004)",
            router_id="10.6.4.1",
            interfaces=[
                {"id": "eth0", "n": "eth0", "t": "eth", "a": ["172.26.0.14/24"], "s": "up"},
                {"id": "lo0", "n": "lo0", "t": "lo", "a": ["10.6.4.1/32"], "s": "up"}
            ],
            protocols=[
                {"p": "ebgp", "r": "10.6.4.1", "asn": 65004, "peers": [
                    {"ip": "172.26.0.1", "asn": 65000}
                ], "nets": ["100.64.0.0/16"]}
            ]
        )
    ]

    links = [
        TOONLink(id="rs-isp1", a1="rs", i1="eth0", a2="isp1", i2="eth0", t="ethernet", c=10),
        TOONLink(id="rs-isp2", a1="rs", i1="eth0", a2="isp2", i2="eth0", t="ethernet", c=10),
        TOONLink(id="rs-isp3", a1="rs", i1="eth0", a2="isp3", i2="eth0", t="ethernet", c=10),
        TOONLink(id="rs-isp4", a1="rs", i1="eth0", a2="isp4", i2="eth0", t="ethernet", c=10)
    ]

    return TOONNetwork(
        id="internet-exchange",
        n="Internet Exchange Point",
        docker=TOONDockerConfig(n="internet-exchange", driver="bridge", subnet="172.26.0.0/16"),
        agents=agents,
        topo=TOONTopology(links=links),
        mcps=get_mandatory_mcps(),
        meta={
            "template": "internet_exchange",
            "description": "Route server with multiple ASN peers",
            "use_case": "IXP peering fabric"
        }
    )
