"""
Tutorial Module - Tutorial definitions and management

Provides:
- Tutorial data structures
- Step-by-step learning paths
- Tutorial library with networking topics
- Category and difficulty management
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger("TutorialManager")


class TutorialCategory(str, Enum):
    """Tutorial categories"""
    FUNDAMENTALS = "fundamentals"
    OSPF = "ospf"
    BGP = "bgp"
    ISIS = "isis"
    MPLS = "mpls"
    VXLAN = "vxlan"
    EVPN = "evpn"
    DHCP = "dhcp"
    DNS = "dns"
    SECURITY = "security"
    AUTOMATION = "automation"
    TROUBLESHOOTING = "troubleshooting"
    DESIGN = "design"
    CERTIFICATION = "certification"


class TutorialDifficulty(str, Enum):
    """Tutorial difficulty levels"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class StepType(str, Enum):
    """Types of tutorial steps"""
    INFO = "info"              # Informational content
    TASK = "task"              # User action required
    QUIZ = "quiz"              # Knowledge check
    CONFIG = "config"          # Configuration exercise
    VERIFY = "verify"          # Verification step
    DEMO = "demo"              # Demonstration
    VIDEO = "video"            # Video content
    INTERACTIVE = "interactive"  # Interactive simulation


@dataclass
class TutorialStep:
    """
    A single step in a tutorial

    Attributes:
        id: Unique step identifier
        title: Step title
        step_type: Type of step
        content: Main content (markdown)
        instructions: Step-by-step instructions
        expected_outcome: What should happen
        validation: How to validate completion
        hints: Help hints
        resources: Related resources
        order: Step order in tutorial
    """
    id: str
    title: str
    step_type: StepType
    content: str
    instructions: List[str] = field(default_factory=list)
    expected_outcome: str = ""
    validation: Dict[str, Any] = field(default_factory=dict)
    hints: List[str] = field(default_factory=list)
    resources: List[Dict[str, str]] = field(default_factory=list)
    order: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "step_type": self.step_type.value,
            "content": self.content,
            "instructions": self.instructions,
            "expected_outcome": self.expected_outcome,
            "validation": self.validation,
            "hints": self.hints,
            "resources": self.resources,
            "order": self.order
        }


@dataclass
class Tutorial:
    """
    A complete tutorial

    Attributes:
        id: Unique tutorial identifier
        title: Tutorial title
        description: Brief description
        category: Tutorial category
        difficulty: Difficulty level
        duration_minutes: Estimated completion time
        steps: List of tutorial steps
        prerequisites: Required tutorials
        objectives: Learning objectives
        tags: Searchable tags
        author: Tutorial author
        version: Tutorial version
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    id: str
    title: str
    description: str
    category: TutorialCategory
    difficulty: TutorialDifficulty
    duration_minutes: int
    steps: List[TutorialStep] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)
    objectives: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    author: str = "ADN Platform"
    version: str = "1.0"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def get_step(self, step_id: str) -> Optional[TutorialStep]:
        """Get step by ID"""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_step_by_order(self, order: int) -> Optional[TutorialStep]:
        """Get step by order number"""
        for step in self.steps:
            if step.order == order:
                return step
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "difficulty": self.difficulty.value,
            "duration_minutes": self.duration_minutes,
            "steps": [s.to_dict() for s in self.steps],
            "prerequisites": self.prerequisites,
            "objectives": self.objectives,
            "tags": self.tags,
            "author": self.author,
            "version": self.version,
            "step_count": self.step_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

    def to_summary(self) -> Dict[str, Any]:
        """Get summary without steps"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "difficulty": self.difficulty.value,
            "duration_minutes": self.duration_minutes,
            "step_count": self.step_count,
            "prerequisites": self.prerequisites,
            "objectives": self.objectives,
            "tags": self.tags
        }


class TutorialManager:
    """
    Manages tutorial library
    """

    def __init__(self):
        """Initialize with built-in tutorials"""
        self._tutorials: Dict[str, Tutorial] = {}
        self._load_builtin_tutorials()

    def _load_builtin_tutorials(self):
        """Load built-in tutorial library"""
        # OSPF Fundamentals
        self._tutorials["ospf-fundamentals"] = Tutorial(
            id="ospf-fundamentals",
            title="OSPF Fundamentals",
            description="Learn the basics of OSPF routing protocol including neighbor relationships, LSA types, and SPF calculation.",
            category=TutorialCategory.OSPF,
            difficulty=TutorialDifficulty.BEGINNER,
            duration_minutes=45,
            objectives=[
                "Understand OSPF neighbor states",
                "Configure basic OSPF on a router",
                "Verify OSPF adjacencies",
                "Understand LSA types and flooding"
            ],
            tags=["ospf", "routing", "igp", "link-state"],
            steps=[
                TutorialStep(
                    id="ospf-intro",
                    title="Introduction to OSPF",
                    step_type=StepType.INFO,
                    content="""
# What is OSPF?

OSPF (Open Shortest Path First) is a link-state routing protocol defined in RFC 2328.

## Key Characteristics:
- **Link-state protocol**: Each router maintains a complete topology map
- **Dijkstra's algorithm**: Used for SPF (Shortest Path First) calculation
- **Fast convergence**: Reacts quickly to network changes
- **Scalable**: Supports hierarchical design with areas
- **Classless**: Supports VLSM and CIDR

## OSPF vs Distance Vector:
| Feature | OSPF | RIP |
|---------|------|-----|
| Type | Link-state | Distance vector |
| Metric | Cost (bandwidth) | Hop count |
| Convergence | Fast | Slow |
| Scalability | High | Low |
                    """,
                    order=1,
                    resources=[
                        {"title": "RFC 2328 - OSPF Version 2", "url": "https://tools.ietf.org/html/rfc2328"}
                    ]
                ),
                TutorialStep(
                    id="ospf-neighbors",
                    title="OSPF Neighbor States",
                    step_type=StepType.INFO,
                    content="""
# OSPF Neighbor State Machine

OSPF routers go through several states to form adjacencies:

## States:
1. **Down**: No hello received
2. **Attempt**: (NBMA only) Actively trying
3. **Init**: Hello received, but 2-way not confirmed
4. **2-Way**: Bidirectional communication established
5. **ExStart**: Master/slave negotiation
6. **Exchange**: Database description exchange
7. **Loading**: LSA request/response
8. **Full**: Fully adjacent

## Key Timers:
- **Hello interval**: 10 seconds (broadcast), 30 seconds (NBMA)
- **Dead interval**: 4x hello interval
- **Wait timer**: Equal to dead interval
                    """,
                    order=2
                ),
                TutorialStep(
                    id="ospf-config-task",
                    title="Configure Basic OSPF",
                    step_type=StepType.TASK,
                    content="Configure OSPF on a router to establish neighbor relationships.",
                    instructions=[
                        "Create a new agent with OSPF enabled",
                        "Set the router ID to a unique value",
                        "Add an interface to OSPF area 0",
                        "Verify the OSPF configuration"
                    ],
                    expected_outcome="OSPF process running with correct area assignment",
                    hints=[
                        "Router ID should be a valid IPv4 address",
                        "Use loopback for stable router ID",
                        "Area 0 is the backbone area"
                    ],
                    order=3
                ),
                TutorialStep(
                    id="ospf-verify",
                    title="Verify OSPF Operation",
                    step_type=StepType.VERIFY,
                    content="Verify that OSPF is working correctly.",
                    instructions=[
                        "Check OSPF neighbor table",
                        "Verify neighbor state is FULL",
                        "Check the LSDB for LSAs",
                        "Verify routes in routing table"
                    ],
                    validation={
                        "check_neighbors": True,
                        "expected_state": "FULL"
                    },
                    order=4
                ),
                TutorialStep(
                    id="ospf-quiz",
                    title="Knowledge Check",
                    step_type=StepType.QUIZ,
                    content="Test your understanding of OSPF fundamentals.",
                    validation={
                        "assessment_id": "ospf-fundamentals-quiz"
                    },
                    order=5
                )
            ]
        )

        # BGP Fundamentals
        self._tutorials["bgp-fundamentals"] = Tutorial(
            id="bgp-fundamentals",
            title="BGP Fundamentals",
            description="Learn the basics of BGP (Border Gateway Protocol) including peer relationships, path selection, and route advertisement.",
            category=TutorialCategory.BGP,
            difficulty=TutorialDifficulty.INTERMEDIATE,
            duration_minutes=60,
            prerequisites=["ospf-fundamentals"],
            objectives=[
                "Understand BGP peer types (iBGP vs eBGP)",
                "Configure basic BGP peering",
                "Understand BGP path attributes",
                "Verify BGP neighbor relationships"
            ],
            tags=["bgp", "routing", "egp", "as-path"],
            steps=[
                TutorialStep(
                    id="bgp-intro",
                    title="Introduction to BGP",
                    step_type=StepType.INFO,
                    content="""
# What is BGP?

BGP (Border Gateway Protocol) is the routing protocol that makes the Internet work.

## Key Characteristics:
- **Path-vector protocol**: Tracks the full AS path
- **Policy-based**: Rich route manipulation capabilities
- **TCP-based**: Uses TCP port 179
- **Scalable**: Routes the entire Internet
- **Slow convergence by design**: Stability over speed

## BGP Peer Types:
- **eBGP**: Between different AS (external)
- **iBGP**: Within the same AS (internal)

## Key Concepts:
- Autonomous System (AS)
- AS Path
- Next-hop
- Local preference
- MED (Multi-Exit Discriminator)
                    """,
                    order=1,
                    resources=[
                        {"title": "RFC 4271 - BGP-4", "url": "https://tools.ietf.org/html/rfc4271"}
                    ]
                ),
                TutorialStep(
                    id="bgp-fsm",
                    title="BGP Finite State Machine",
                    step_type=StepType.INFO,
                    content="""
# BGP FSM States

## States:
1. **Idle**: Initial state, no resources allocated
2. **Connect**: Waiting for TCP connection
3. **Active**: Attempting to initiate TCP
4. **OpenSent**: TCP up, OPEN message sent
5. **OpenConfirm**: Waiting for KEEPALIVE
6. **Established**: Fully operational

## Timers:
- **Hold timer**: 90 seconds default
- **Keepalive**: 30 seconds default
- **Connect retry**: 120 seconds
                    """,
                    order=2
                ),
                TutorialStep(
                    id="bgp-config-task",
                    title="Configure eBGP Peering",
                    step_type=StepType.TASK,
                    content="Configure an eBGP peer relationship between two routers.",
                    instructions=[
                        "Create two agents in different ASNs",
                        "Configure BGP on both agents",
                        "Add the remote peer configuration",
                        "Advertise a prefix from each agent"
                    ],
                    expected_outcome="BGP session established between peers",
                    hints=[
                        "eBGP peers must be directly connected by default",
                        "Use update-source for non-directly connected peers",
                        "Verify TCP connectivity first"
                    ],
                    order=3
                ),
                TutorialStep(
                    id="bgp-path-selection",
                    title="BGP Path Selection",
                    step_type=StepType.INFO,
                    content="""
# BGP Best Path Selection

BGP selects the best path using these criteria (in order):

1. Highest **Weight** (Cisco-specific)
2. Highest **Local Preference**
3. Locally originated routes
4. Shortest **AS Path**
5. Lowest **Origin** type (i > e > ?)
6. Lowest **MED**
7. **eBGP** over iBGP
8. Lowest **IGP metric** to next-hop
9. Oldest route (stability)
10. Lowest **Router ID**
11. Lowest **neighbor IP**
                    """,
                    order=4
                ),
                TutorialStep(
                    id="bgp-verify",
                    title="Verify BGP Operation",
                    step_type=StepType.VERIFY,
                    content="Verify that BGP is working correctly.",
                    instructions=[
                        "Check BGP neighbor table",
                        "Verify neighbor state is Established",
                        "Check received prefixes",
                        "Verify best path selection"
                    ],
                    validation={
                        "check_neighbors": True,
                        "expected_state": "Established"
                    },
                    order=5
                ),
                TutorialStep(
                    id="bgp-quiz",
                    title="Knowledge Check",
                    step_type=StepType.QUIZ,
                    content="Test your understanding of BGP fundamentals.",
                    validation={
                        "assessment_id": "bgp-fundamentals-quiz"
                    },
                    order=6
                )
            ]
        )

        # Network Troubleshooting
        self._tutorials["troubleshooting-basics"] = Tutorial(
            id="troubleshooting-basics",
            title="Network Troubleshooting Basics",
            description="Learn systematic approaches to troubleshooting network connectivity issues.",
            category=TutorialCategory.TROUBLESHOOTING,
            difficulty=TutorialDifficulty.BEGINNER,
            duration_minutes=30,
            objectives=[
                "Apply OSI model to troubleshooting",
                "Use ping and traceroute effectively",
                "Identify common connectivity issues",
                "Document troubleshooting steps"
            ],
            tags=["troubleshooting", "connectivity", "diagnostics"],
            steps=[
                TutorialStep(
                    id="ts-intro",
                    title="Systematic Troubleshooting",
                    step_type=StepType.INFO,
                    content="""
# Systematic Troubleshooting Approach

## The OSI Model Approach:
Start from Layer 1 and work up:

1. **Physical**: Cables, ports, power
2. **Data Link**: MAC addresses, VLANs, ARP
3. **Network**: IP addressing, routing
4. **Transport**: TCP/UDP, ports, firewalls
5. **Application**: DNS, HTTP, services

## Divide and Conquer:
- Start in the middle (Layer 3)
- Work up or down based on results
- More efficient for experienced engineers
                    """,
                    order=1
                ),
                TutorialStep(
                    id="ts-ping",
                    title="Using Ping",
                    step_type=StepType.INFO,
                    content="""
# The Ping Command

## Basic Usage:
```
ping <destination>
```

## Interpreting Results:
- **Reply**: Connectivity works
- **Timeout**: No response (many causes)
- **Unreachable**: Explicit failure message

## ICMP Message Types:
- Type 0: Echo Reply
- Type 3: Destination Unreachable
- Type 8: Echo Request
- Type 11: Time Exceeded
                    """,
                    order=2
                ),
                TutorialStep(
                    id="ts-task",
                    title="Troubleshoot Connectivity",
                    step_type=StepType.TASK,
                    content="Practice troubleshooting a connectivity issue.",
                    instructions=[
                        "Identify the source and destination",
                        "Ping the default gateway",
                        "Ping the remote gateway",
                        "Ping the destination",
                        "Trace the route to destination"
                    ],
                    expected_outcome="Identify where connectivity fails",
                    order=3
                )
            ]
        )

        # VXLAN/EVPN Tutorial
        self._tutorials["vxlan-evpn-intro"] = Tutorial(
            id="vxlan-evpn-intro",
            title="Introduction to VXLAN/EVPN",
            description="Learn about VXLAN overlay networks and EVPN control plane for modern data centers.",
            category=TutorialCategory.VXLAN,
            difficulty=TutorialDifficulty.ADVANCED,
            duration_minutes=90,
            prerequisites=["bgp-fundamentals"],
            objectives=[
                "Understand VXLAN encapsulation",
                "Configure VTEPs",
                "Understand EVPN route types",
                "Configure L2/L3 VNIs"
            ],
            tags=["vxlan", "evpn", "datacenter", "overlay"],
            steps=[
                TutorialStep(
                    id="vxlan-intro",
                    title="VXLAN Overview",
                    step_type=StepType.INFO,
                    content="""
# What is VXLAN?

VXLAN (Virtual Extensible LAN) extends Layer 2 networks over Layer 3.

## Key Concepts:
- **VNI**: VXLAN Network Identifier (24-bit = 16 million VLANs)
- **VTEP**: VXLAN Tunnel Endpoint
- **NVE**: Network Virtualization Edge

## Benefits:
- Overcome 4096 VLAN limit
- Enable VM mobility across L3 boundaries
- Multi-tenancy support
- DC interconnect
                    """,
                    order=1,
                    resources=[
                        {"title": "RFC 7348 - VXLAN", "url": "https://tools.ietf.org/html/rfc7348"}
                    ]
                ),
                TutorialStep(
                    id="evpn-intro",
                    title="EVPN Control Plane",
                    step_type=StepType.INFO,
                    content="""
# EVPN Control Plane

EVPN uses BGP to distribute MAC/IP information.

## Route Types:
- **Type 1**: Ethernet Auto-discovery
- **Type 2**: MAC/IP Advertisement
- **Type 3**: Inclusive Multicast
- **Type 4**: Ethernet Segment
- **Type 5**: IP Prefix

## Benefits over Flood-and-Learn:
- Control plane learning
- Faster convergence
- Multihoming support
- ARP suppression
                    """,
                    order=2,
                    resources=[
                        {"title": "RFC 7432 - EVPN", "url": "https://tools.ietf.org/html/rfc7432"}
                    ]
                )
            ]
        )

        # Network Design Tutorial
        self._tutorials["network-design-basics"] = Tutorial(
            id="network-design-basics",
            title="Network Design Fundamentals",
            description="Learn the principles of designing scalable and resilient networks.",
            category=TutorialCategory.DESIGN,
            difficulty=TutorialDifficulty.INTERMEDIATE,
            duration_minutes=60,
            prerequisites=["ospf-fundamentals", "bgp-fundamentals"],
            objectives=[
                "Understand hierarchical network design",
                "Design redundant topologies",
                "Plan IP addressing schemes",
                "Choose appropriate routing protocols"
            ],
            tags=["design", "architecture", "planning"],
            steps=[
                TutorialStep(
                    id="design-hierarchy",
                    title="Hierarchical Design Model",
                    step_type=StepType.INFO,
                    content="""
# The Three-Tier Model

## Layers:
1. **Core**: High-speed backbone
   - Fast switching
   - Minimal processing
   - High availability

2. **Distribution**: Policy enforcement
   - Route summarization
   - Access control
   - QoS marking

3. **Access**: End-user connectivity
   - Port security
   - VLAN assignment
   - PoE
                    """,
                    order=1
                ),
                TutorialStep(
                    id="design-redundancy",
                    title="Designing for Redundancy",
                    step_type=StepType.INFO,
                    content="""
# Redundancy Strategies

## Link Redundancy:
- Dual links between tiers
- LACP/Port-channel
- ECMP routing

## Device Redundancy:
- Dual core/distribution
- VRRP/HSRP
- Stacking

## Path Redundancy:
- Multiple routing paths
- Fast failover (< 50ms)
- BFD for detection
                    """,
                    order=2
                )
            ]
        )

        # IS-IS Tutorial
        self._tutorials["isis-fundamentals"] = Tutorial(
            id="isis-fundamentals",
            title="IS-IS Fundamentals",
            description="Learn the basics of IS-IS routing protocol used in service provider networks.",
            category=TutorialCategory.ISIS,
            difficulty=TutorialDifficulty.ADVANCED,
            duration_minutes=60,
            prerequisites=["ospf-fundamentals"],
            objectives=[
                "Understand IS-IS terminology",
                "Configure IS-IS areas",
                "Verify IS-IS adjacencies",
                "Compare IS-IS to OSPF"
            ],
            tags=["isis", "routing", "igp", "link-state", "service-provider"],
            steps=[
                TutorialStep(
                    id="isis-intro",
                    title="Introduction to IS-IS",
                    step_type=StepType.INFO,
                    content="""
# What is IS-IS?

IS-IS (Intermediate System to Intermediate System) is a link-state routing protocol.

## IS-IS vs OSPF:
| Feature | IS-IS | OSPF |
|---------|-------|------|
| Layer | L2 (CLNS) | L3 (IP) |
| Areas | L1/L2 | Backbone + stub |
| Scalability | Excellent | Good |
| Usage | SP networks | Enterprise |

## Key Terms:
- **IS**: Router (Intermediate System)
- **ES**: End System
- **NET**: Network Entity Title
- **TLV**: Type-Length-Value
                    """,
                    order=1,
                    resources=[
                        {"title": "RFC 1195 - IS-IS for IP", "url": "https://tools.ietf.org/html/rfc1195"}
                    ]
                )
            ]
        )

        # MPLS Tutorial
        self._tutorials["mpls-basics"] = Tutorial(
            id="mpls-basics",
            title="MPLS and LDP Basics",
            description="Learn the fundamentals of MPLS label switching and LDP protocol.",
            category=TutorialCategory.MPLS,
            difficulty=TutorialDifficulty.ADVANCED,
            duration_minutes=75,
            prerequisites=["ospf-fundamentals"],
            objectives=[
                "Understand MPLS label operations",
                "Configure LDP",
                "Verify MPLS forwarding",
                "Understand LSP establishment"
            ],
            tags=["mpls", "ldp", "label-switching", "service-provider"],
            steps=[
                TutorialStep(
                    id="mpls-intro",
                    title="Introduction to MPLS",
                    step_type=StepType.INFO,
                    content="""
# What is MPLS?

MPLS (Multi-Protocol Label Switching) forwards packets using labels instead of IP lookups.

## Key Concepts:
- **Label**: 20-bit identifier
- **LSR**: Label Switching Router
- **LSP**: Label Switched Path
- **FEC**: Forwarding Equivalence Class

## Label Operations:
- **Push**: Add label (ingress)
- **Swap**: Change label (transit)
- **Pop**: Remove label (egress)

## Benefits:
- Fast forwarding (label lookup vs IP lookup)
- Traffic engineering
- VPN services
                    """,
                    order=1,
                    resources=[
                        {"title": "RFC 3031 - MPLS Architecture", "url": "https://tools.ietf.org/html/rfc3031"}
                    ]
                )
            ]
        )

        # Automation Tutorial
        self._tutorials["network-automation-intro"] = Tutorial(
            id="network-automation-intro",
            title="Introduction to Network Automation",
            description="Learn the basics of automating network configuration and operations.",
            category=TutorialCategory.AUTOMATION,
            difficulty=TutorialDifficulty.INTERMEDIATE,
            duration_minutes=45,
            objectives=[
                "Understand automation benefits",
                "Use REST APIs",
                "Understand data formats (JSON, YAML)",
                "Introduction to intent-based networking"
            ],
            tags=["automation", "api", "devops", "netdevops"],
            steps=[
                TutorialStep(
                    id="auto-intro",
                    title="Why Automate?",
                    step_type=StepType.INFO,
                    content="""
# Network Automation Benefits

## Manual vs Automated:
| Aspect | Manual | Automated |
|--------|--------|-----------|
| Speed | Slow | Fast |
| Errors | Human error | Consistent |
| Scale | Limited | Unlimited |
| Audit | Difficult | Built-in |

## Automation Use Cases:
- Configuration deployment
- Compliance checking
- Backup/restore
- Monitoring
- Reporting
- Self-healing
                    """,
                    order=1
                ),
                TutorialStep(
                    id="auto-api",
                    title="Using REST APIs",
                    step_type=StepType.INFO,
                    content="""
# REST API Basics

## HTTP Methods:
- **GET**: Retrieve data
- **POST**: Create resource
- **PUT**: Update resource
- **DELETE**: Remove resource

## Response Codes:
- **200**: Success
- **201**: Created
- **400**: Bad request
- **401**: Unauthorized
- **404**: Not found
- **500**: Server error

## Data Formats:
- JSON (most common)
- XML (legacy)
- YAML (config files)
                    """,
                    order=2
                )
            ]
        )

        logger.info(f"Loaded {len(self._tutorials)} built-in tutorials")

    def get_tutorial(self, tutorial_id: str) -> Optional[Tutorial]:
        """Get tutorial by ID"""
        return self._tutorials.get(tutorial_id)

    def list_tutorials(
        self,
        category: Optional[TutorialCategory] = None,
        difficulty: Optional[TutorialDifficulty] = None,
        tags: Optional[List[str]] = None
    ) -> List[Tutorial]:
        """List tutorials with optional filters"""
        tutorials = list(self._tutorials.values())

        if category:
            tutorials = [t for t in tutorials if t.category == category]

        if difficulty:
            tutorials = [t for t in tutorials if t.difficulty == difficulty]

        if tags:
            tutorials = [
                t for t in tutorials
                if any(tag in t.tags for tag in tags)
            ]

        return tutorials

    def search_tutorials(self, query: str) -> List[Tutorial]:
        """Search tutorials by title, description, or tags"""
        query = query.lower()
        results = []

        for tutorial in self._tutorials.values():
            if (query in tutorial.title.lower() or
                query in tutorial.description.lower() or
                any(query in tag for tag in tutorial.tags)):
                results.append(tutorial)

        return results

    def get_categories(self) -> List[Dict[str, Any]]:
        """Get all categories with counts"""
        categories = {}
        for tutorial in self._tutorials.values():
            cat = tutorial.category.value
            if cat not in categories:
                categories[cat] = {"name": cat, "count": 0, "tutorials": []}
            categories[cat]["count"] += 1
            categories[cat]["tutorials"].append(tutorial.id)

        return list(categories.values())

    def get_difficulties(self) -> List[Dict[str, Any]]:
        """Get all difficulty levels with counts"""
        difficulties = {}
        for tutorial in self._tutorials.values():
            diff = tutorial.difficulty.value
            if diff not in difficulties:
                difficulties[diff] = {"level": diff, "count": 0}
            difficulties[diff]["count"] += 1

        return list(difficulties.values())

    def add_tutorial(self, tutorial: Tutorial) -> bool:
        """Add a custom tutorial"""
        if tutorial.id in self._tutorials:
            logger.warning(f"Tutorial already exists: {tutorial.id}")
            return False

        self._tutorials[tutorial.id] = tutorial
        logger.info(f"Added tutorial: {tutorial.id}")
        return True

    def get_statistics(self) -> Dict[str, Any]:
        """Get tutorial statistics"""
        total = len(self._tutorials)
        by_category = {}
        by_difficulty = {}
        total_duration = 0

        for tutorial in self._tutorials.values():
            cat = tutorial.category.value
            diff = tutorial.difficulty.value

            by_category[cat] = by_category.get(cat, 0) + 1
            by_difficulty[diff] = by_difficulty.get(diff, 0) + 1
            total_duration += tutorial.duration_minutes

        return {
            "total_tutorials": total,
            "by_category": by_category,
            "by_difficulty": by_difficulty,
            "total_duration_minutes": total_duration,
            "average_duration_minutes": total_duration / total if total > 0 else 0
        }


# Global tutorial manager instance
_global_manager: Optional[TutorialManager] = None


def get_tutorial_manager() -> TutorialManager:
    """Get or create the global tutorial manager"""
    global _global_manager
    if _global_manager is None:
        _global_manager = TutorialManager()
    return _global_manager
