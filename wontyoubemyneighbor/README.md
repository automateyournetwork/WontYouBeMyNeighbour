# Won't You Be My Neighbor

## Agent System Interconnect (ASI) Platform

**A production-ready multi-agent network platform where intelligent agents self-configure, self-test, and communicate using real routing protocols.**

[![RFC 2328](https://img.shields.io/badge/RFC-2328-blue)](https://datatracker.ietf.org/doc/html/rfc2328)
[![RFC 4271](https://img.shields.io/badge/RFC-4271-purple)](https://datatracker.ietf.org/doc/html/rfc4271)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-required-blue.svg)](https://www.docker.com/)

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [Using Templates](#using-templates)
6. [Web Interface](#web-interface)
7. [API Reference](#api-reference)
8. [Agent Dashboards](#agent-dashboards)
9. [3D Topology Visualization](#3d-topology-visualization)
10. [Protocol Support](#protocol-support)
11. [LLM Integration](#llm-integration)
12. [Troubleshooting](#troubleshooting)

---

## Overview

Won't You Be My Neighbor implements a revolutionary **3-layer Agent System Interconnect (ASI)** architecture:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 3: Protocol Underlay                                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐               │
│  │  OSPF   │  │   BGP   │  │  IS-IS  │  │  MPLS   │               │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘               │
│       └────────────┴────────────┴────────────┘                     │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 2: ASI Agent IPv6 Overlay Mesh                               │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  fd00:a510::/48 - Agent-to-Agent Direct Communication        │  │
│  │  Self-organizing mesh for visibility and coordination        │  │
│  └──────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 1: Docker Container Network                                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Isolated containers with IPv4/IPv6 dual-stack               │  │
│  │  Each agent runs in its own protected environment            │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Capabilities

- **Real Protocol Participation**: Agents speak actual OSPF, BGP, IS-IS, MPLS - not simulations
- **Multi-Agent Orchestration**: Deploy networks of 10 to 1000+ agents via web wizard
- **LLM-Powered Intelligence**: Each agent has an AI brain (Claude, GPT-4, Gemini, or Llama)
- **3D Topology Visualization**: Interactive Three.js visualization of all three network layers
- **Self-Testing**: Built-in pyATS test framework for network validation
- **Conversation Tracking**: GAIT integration for complete audit trails

---

## Architecture

```
wontyoubemyneighbor/
├── wontyoubemyneighbor.py    # Main agent (single-agent mode)
├── orchestrator/              # Multi-agent deployment
│   ├── network_orchestrator.py
│   └── agent_launcher.py
├── webui/                     # Web interface
│   ├── server.py             # FastAPI server
│   ├── wizard_api.py         # Network wizard API
│   └── static/               # Frontend assets
├── ospf/                      # OSPF protocol implementation
├── bgp/                       # BGP protocol implementation
├── isis/                      # IS-IS protocol implementation
├── mpls/                      # MPLS/LDP implementation
├── agentic/                   # AI/LLM integration
│   ├── llm/                  # Claude, OpenAI, Gemini providers
│   ├── knowledge/            # State management
│   └── metrics/              # Performance tracking
├── templates/                 # Network topology templates
│   └── topology_templates/
└── tests/                     # Test suites
```

---

## Installation

### Prerequisites

- **Operating System**: Linux or macOS (Windows with WSL2)
- **Python**: 3.8 or higher
- **Docker**: Required for multi-agent deployment
- **Root/sudo access**: Required for raw sockets (single-agent OSPF mode)

### Step 1: Clone the Repository

```bash
git clone https://github.com/yourusername/wontyoubemyneighbor.git
cd wontyoubemyneighbor
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate

# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# On Windows (CMD):
venv\Scripts\activate.bat
```

### Step 3: Install Dependencies

```bash
# Upgrade pip first
pip install --upgrade pip

# Install all requirements
pip install -r requirements.txt
```

### Step 4: Set Up LLM API Keys (Optional but Recommended)

Create environment variables for LLM providers:

```bash
# For Claude (Anthropic)
export ANTHROPIC_API_KEY="your-api-key-here"

# For OpenAI
export OPENAI_API_KEY="your-api-key-here"

# For Google Gemini
export GOOGLE_API_KEY="your-api-key-here"
```

Or create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=your-api-key-here
OPENAI_API_KEY=your-api-key-here
GOOGLE_API_KEY=your-api-key-here
```

### Step 5: Verify Docker is Running

```bash
# Check Docker is available
docker --version
docker ps

# Ensure Docker daemon is running
# On Linux: sudo systemctl start docker
# On macOS: Open Docker Desktop
```

---

## Quick Start

### Option A: Launch Web Interface (Recommended)

The easiest way to get started is via the web wizard:

```bash
# Activate virtual environment
source venv/bin/activate

# Start the web server
python3 -m webui.server
```

Then open your browser to: **http://localhost:8000**

You'll see:
- **/** - Chat interface for single-agent interaction
- **/wizard** - Network deployment wizard
- **/monitor** - Network topology monitor
- **/dashboard** - Agent dashboard with protocol tabs
- **/topology3d** - 3D network visualization

### Option B: Single Agent Mode (CLI)

For direct OSPF participation with a real router:

```bash
# Requires sudo for raw sockets
sudo python3 wontyoubemyneighbor.py \
    --router-id 10.255.255.99 \
    --area 0.0.0.0 \
    --interface eth0
```

---

## Using Templates

Templates provide pre-configured network topologies. The **ospf-core-bgp** template is perfect for getting started.

### Available Templates

| Template | Agents | Protocols | Description |
|----------|--------|-----------|-------------|
| `ospf-core-bgp` | 3 | OSPF, iBGP, eBGP | Simple OSPF core with BGP edge |
| `spine-leaf-datacenter` | 6 | eBGP, VXLAN, EVPN | Modern datacenter fabric |
| `three-tier-enterprise` | 8 | OSPF, iBGP, DHCP | Classic enterprise network |
| `mpls-service-provider` | 6 | OSPF, MPLS, LDP, iBGP | SP backbone with L3VPN |
| `campus-network` | 8 | OSPF, VRRP, DHCP | Multi-building campus |
| `wan-hub-spoke` | 5 | iBGP, OSPF, DHCP | Enterprise WAN |
| `bgp-anycast` | 4 | eBGP | Anycast DNS/CDN |

### Example: Deploy ospf-core-bgp Template

#### Via Web Wizard

1. Open **http://localhost:8000/wizard**
2. Click "Load Template" button
3. Select **ospf-core-bgp** from the dropdown
4. Review the topology (3 agents):
   - **OSPF Router** (10.255.255.1) - Pure OSPF speaker
   - **Core Router** (10.255.255.99) - OSPF + iBGP
   - **eBGP Router** (10.255.255.2) - iBGP + eBGP to ISP
5. Configure network settings:
   - Network Name: `my-first-network`
   - Docker Subnet: `172.20.0.0/16` or IPv6
   - LLM Provider: Claude, OpenAI, Gemini, or Llama
6. Click **Deploy Network**
7. Watch agents launch and protocols converge

#### Via API

```bash
# Load template
curl -X POST http://localhost:8000/api/wizard/load-template \
  -H "Content-Type: application/json" \
  -d '{"template_id": "ospf-core-bgp"}'

# Deploy network
curl -X POST http://localhost:8000/api/wizard/deploy \
  -H "Content-Type: application/json" \
  -d '{
    "network_name": "my-network",
    "subnet": "172.20.0.0/16",
    "llm_provider": "claude"
  }'
```

### Template File Structure

Templates are stored in `templates/topology_templates/<template-name>/`:

```
ospf-core-bgp/
├── all_agents.json     # Agent definitions with interfaces & protocols
└── first_topology.json # Link definitions between agents
```

**all_agents.json** example:
```json
[
  {
    "id": "ospf-router",
    "n": "OSPF Router",
    "r": "10.255.255.1",
    "ifs": [
      {"id": "eth0", "t": "eth", "a": ["172.20.0.10/24"], "s": "up"},
      {"id": "lo0", "t": "lo", "a": ["10.255.255.1/32"], "s": "up"}
    ],
    "protos": [
      {"p": "ospf", "r": "10.255.255.1", "a": "0.0.0.0", "nets": ["172.20.0.0/24"]}
    ]
  }
]
```

---

## Web Interface

### Main Pages

| URL | Page | Description |
|-----|------|-------------|
| `/` | Chat | Single-agent chat interface |
| `/wizard` | Network Wizard | Deploy multi-agent networks |
| `/monitor` | Network Monitor | View deployed networks and agents |
| `/dashboard` | Agent Dashboard | Protocol-specific metrics and chat |
| `/topology3d` | 3D Topology | Interactive 3D network visualization |

### Network Wizard Features

The wizard at `/wizard` provides:

1. **Template Library**: Load pre-built topologies
2. **Visual Topology Editor**: Drag-and-drop agent placement
3. **Protocol Configuration**: OSPF, BGP, IS-IS, MPLS, DHCP, DNS
4. **Network Settings**:
   - IPv4 or IPv6 subnets
   - Dual-stack support
   - LLM provider selection
5. **Deployment Progress**: Real-time agent launch status
6. **Direct Links**: Jump to agent dashboards after deployment

---

## API Reference

### Base URL: `http://localhost:8000`

### Wizard API

```
POST /api/wizard/load-template
  Body: {"template_id": "ospf-core-bgp"}
  Response: Agent and link configurations

POST /api/wizard/deploy
  Body: {
    "network_name": "string",
    "subnet": "172.20.0.0/16",
    "llm_provider": "claude|openai|gemini|llama",
    "agents": [...],
    "links": [...]
  }
  Response: {"network_id": "uuid", "status": "deploying"}

GET /api/wizard/templates
  Response: List of available templates

GET /api/wizard/status/{network_id}
  Response: Deployment status and agent info
```

### Network API

```
GET /api/networks
  Response: List of deployed networks

GET /api/networks/{network_id}/status
  Response: Detailed network status with all 3 layers

POST /api/networks/{network_id}/stop
  Response: Stop all agents in network

DELETE /api/networks/{network_id}
  Response: Remove network and cleanup
```

### Agent API

```
GET /api/agents/{agent_id}/status
  Response: Agent status, protocols, neighbors

POST /api/chat
  Body: {"message": "How many OSPF neighbors do I have?"}
  Response: {"response": "You have 2 OSPF neighbors in FULL state..."}

GET /api/agents/{agent_id}/routes
  Response: Routing table (OSPF + BGP combined)
```

### WebSocket

```
ws://localhost:8000/ws
  Messages:
    - {"type": "get_status"}
    - {"type": "get_routes"}
    - {"type": "run_tests", "suites": ["ospf", "bgp"]}
```

---

## Agent Dashboards

Access agent-specific dashboards at `/dashboard?agent_id=<agent-id>` or `/dashboard` for the local agent.

### Dashboard Tabs

| Tab | Description |
|-----|-------------|
| **Chat** | Conversational interface to ask about routing |
| **Interfaces** | Interface status, IPs, MTU, up/down |
| **OSPF** | Neighbors, LSDB size, routes, adjacency states |
| **BGP** | Peers, established sessions, prefixes in/out |
| **IS-IS** | Adjacencies, LSP count, area info |
| **MPLS** | LFIB entries, LDP sessions, labels |
| **DHCP** | Pools, leases, available IPs |
| **DNS** | Zones, records, query statistics |
| **Testing** | pyATS test suites and results |
| **GAIT** | Conversation history and audit trail |
| **Markmap** | Mind map visualization of agent state |

### Chat Interface

The Chat tab allows natural language interaction:

```
You: "How many BGP neighbors do I have?"
Agent: "You have 2 BGP peers configured. 1 is in Established state
        (peer 172.20.1.2 AS65001). 1 is in Idle state."

You: "Show me the OSPF routing table"
Agent: "OSPF has learned 5 routes:
        - 10.255.255.1/32 via 172.20.0.10 (cost 10)
        - 172.20.0.0/24 directly connected
        ..."
```

---

## 3D Topology Visualization

Access at `/topology3d` or `/topology3d?network_id=<id>` for specific networks.

### Three-Layer View

The 3D visualization shows all three ASI layers:

1. **Docker Network (Bottom)**: Container connectivity, IPv4 addresses
2. **ASI Overlay (Middle)**: IPv6 mesh, agent-to-agent links
3. **Protocol Underlay (Top)**: OSPF/BGP adjacencies, logical topology

### Controls

| Control | Action |
|---------|--------|
| Mouse drag | Rotate view |
| Scroll | Zoom in/out |
| Click agent | Show details panel |
| Layer toggles | Show/hide individual layers |
| Label toggles | Show/hide IP addresses |

### Label Types

- **Docker IPs**: Container IPv4 addresses (e.g., 172.20.0.10)
- **Overlay IPs**: ASI IPv6 addresses (e.g., fd00:a510:0:1::1)
- **Interface Names**: eth0, lo0, etc.

---

## Protocol Support

### OSPF (RFC 2328)

- Full neighbor state machine (8 states)
- Hello/DBD/LSR/LSU/LSAck packet types
- Router LSA (Type 1) generation
- LSDB synchronization
- SPF calculation (Dijkstra)
- Point-to-point and broadcast networks

### BGP (RFC 4271)

- iBGP and eBGP support
- Full FSM (Idle through Established)
- UPDATE/KEEPALIVE/NOTIFICATION messages
- Loc-RIB, Adj-RIB-In, Adj-RIB-Out
- Path selection algorithm
- AS-path, next-hop, local-pref attributes
- Route advertisement and withdrawal

### IS-IS

- Level 1 and Level 2 adjacencies
- Hello packets
- LSP flooding
- SPF calculation

### MPLS/LDP

- Label distribution protocol
- LFIB management
- Label binding/release

### Services

- **DHCP**: Pool management, lease tracking
- **DNS**: Zone management, record types

---

## LLM Integration

Each agent can be powered by an LLM for intelligent responses:

### Supported Providers

| Provider | Model | API Key Variable |
|----------|-------|------------------|
| Anthropic | Claude Sonnet/Opus | `ANTHROPIC_API_KEY` |
| OpenAI | GPT-4o/GPT-4 Turbo | `OPENAI_API_KEY` |
| Google | Gemini 1.5 Pro | `GOOGLE_API_KEY` |
| Local | Llama (via Ollama) | N/A |

### Agent Context

The LLM receives context including:
- Current OSPF neighbor states
- BGP peer sessions
- Routing table
- Interface status
- Recent state changes
- Health metrics

### Example Queries

- "Why is my BGP session to 10.1.1.1 not establishing?"
- "What prefixes am I advertising to my eBGP peers?"
- "Explain the current OSPF LSDB"
- "Compare the cost of routes to 10.0.0.0/8"

---

## Troubleshooting

### Common Issues

#### Docker not running
```
Error: Cannot connect to Docker daemon
Solution: Start Docker
  - Linux: sudo systemctl start docker
  - macOS: Open Docker Desktop
```

#### Port already in use
```
Error: Address already in use :8000
Solution: Kill existing process or use different port
  lsof -i :8000
  kill -9 <PID>
  # Or start on different port:
  python3 -m webui.server --port 8001
```

#### Permission denied (raw sockets)
```
Error: Operation not permitted
Solution: Run with sudo for single-agent OSPF mode
  sudo python3 wontyoubemyneighbor.py ...
```

#### LLM API errors
```
Error: Invalid API key
Solution: Check environment variables
  echo $ANTHROPIC_API_KEY
  export ANTHROPIC_API_KEY="sk-ant-..."
```

### Debug Mode

Enable verbose logging:

```bash
# Single agent
sudo python3 wontyoubemyneighbor.py --log-level DEBUG ...

# Web server
LOG_LEVEL=DEBUG python3 -m webui.server
```

### Verify Protocol Traffic

```bash
# Capture OSPF traffic
sudo tcpdump -i docker0 proto 89 -n -v

# Capture BGP traffic
sudo tcpdump -i docker0 port 179 -n -v
```

---

## Development

### Running Tests

```bash
# Activate venv
source venv/bin/activate

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/bgp/test_session.py -v

# Run with coverage
pytest tests/ --cov=.
```

### Project Structure

```
Key modules:
- wontyoubemyneighbor.py: Main entry point
- webui/server.py: FastAPI application
- orchestrator/network_orchestrator.py: Multi-agent deployment
- agentic/llm/interface.py: LLM conversation management
- ospf/: OSPF protocol stack
- bgp/: BGP protocol stack
```

---

## License

MIT License - See [LICENSE](LICENSE) file.

---

## Acknowledgments

- **RFC 2328**: John Moy's OSPF specification
- **RFC 4271**: BGP-4 specification
- **Scapy**: Packet crafting library
- **NetworkX**: Graph algorithms (Dijkstra SPF)
- **Three.js**: 3D visualization
- **FastAPI**: Web framework

---

## References

- [RFC 2328: OSPF Version 2](https://datatracker.ietf.org/doc/html/rfc2328)
- [RFC 4271: BGP-4](https://datatracker.ietf.org/doc/html/rfc4271)
- [ASI Architecture Overview](docs/architecture_design.md)
- [BGP Implementation Guide](docs/BGP_USER_GUIDE.md)

---

**Won't You Be My Neighbor?**

Welcome to the Agent System Interconnect. Your network agents are ready to meet their neighbors.
