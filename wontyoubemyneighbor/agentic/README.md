# RubberBand: Agentic Network Router

Transform wontyoubemyneighbor into an intelligent, conversational network router that understands natural language while maintaining native OSPF and BGP protocol participation.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Natural Language                      │
│                 "Show me my OSPF neighbors"              │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  LLM Interface Layer                     │
│  • OpenAI GPT-4  • Anthropic Claude  • Google Gemini    │
│  • 75-turn conversation • Context injection             │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  Reasoning Engine                        │
│  • Intent Parser (NL → Structured Intents)              │
│  • Decision Engine (Explainable Route Decisions)        │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                 Action Executor                          │
│  • Safety Constraints  • Human Approval Workflow        │
│  • Audit Logging      • Rate Limiting                   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│              Knowledge Management                        │
│  • State Manager (OSPF/BGP State Tracking)              │
│  • Analytics (Time-series, Trends, Predictions)         │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│           Multi-Agent Coordination                       │
│  • Gossip Protocol (RubberBand-to-RubberBand)                     │
│  • Consensus Engine (Distributed Voting)                │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│              Protocol Integration                        │
│  • OSPF Connector  • BGP Connector                      │
│  • wontyoubemyneighbor.ospfv3  • wontyoubemyneighbor.bgp │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r wontyoubemyneighbor/agentic/requirements.txt
```

### 2. Set API Keys

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export GOOGLE_API_KEY="..."
```

### 3. Run CLI Interface

```bash
python -m wontyoubemyneighbor.agentic.cli.chat --claude-key $ANTHROPIC_API_KEY
```

### 4. Or Run REST API Server

```bash
python -m wontyoubemyneighbor.agentic.api.run_server --port 8080
```

Then query via HTTP:
```bash
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Show me my OSPF neighbors"}'
```

## Features

### 🤖 Multi-Provider LLM Support
- OpenAI GPT-4
- Anthropic Claude (recommended)
- Google Gemini
- Automatic fallback between providers
- 75-turn conversation management

### 🧠 Intelligent Reasoning
- **Intent Parser**: Maps natural language to 15+ structured intent types
- **Decision Engine**: Explainable routing decisions with multi-criteria scoring
- **Anomaly Detection**: Neighbor flapping, peer down, route instability
- **Predictive Analytics**: Failure prediction, trend analysis

### ✅ Safe Autonomous Actions
- **Safety Constraints**: Metric ranges, critical interfaces, rate limiting
- **Human Approval Workflow**: Dangerous actions require approval
- **Action Types**:
  - ✓ Metric adjustment
  - ✓ Route injection/withdrawal
  - ✓ BGP policy changes
  - ✓ Graceful shutdown

### 📊 Network Knowledge
- **State Tracking**: Real-time OSPF/BGP state
- **Snapshot Management**: Time-series analysis
- **Analytics**: Stability scoring, route churn, health trends
- **LLM Context**: Automatic network state injection

### 🤝 Multi-Agent Coordination
- **Gossip Protocol**: Epidemic-style RubberBand-to-RubberBand communication
- **Consensus Engine**: Distributed voting for critical actions
- **Automatic Coordination**: Alert propagation, state sharing

### 🌐 REST API
- 20+ HTTP endpoints
- Natural language query endpoint
- State inspection (OSPF, BGP, routes)
- Action execution and approval
- Consensus proposal and voting
- Auto-generated OpenAPI docs at `/docs`

### 💬 Interactive CLI
- Natural language conversations
- Command history (with readline)
- Special commands (`/help`, `/stats`, `/quit`)
- Batch mode for demos

## Usage Examples

### Natural Language Queries

```python
from wontyoubemyneighbor.agentic.integration.bridge import AgenticBridge

# Create agentic bridge
bridge = AgenticBridge(
    rubberband_id="rubberband-1",
    claude_key="sk-ant-...",
    autonomous_mode=False
)

await bridge.initialize()
await bridge.start()

# Ask questions in natural language
response = await bridge.query("Show me my OSPF neighbors")
print(response)

response = await bridge.query("Are there any network issues?")
print(response)

response = await bridge.query("How do I reach 10.0.0.1?")
print(response)
```

### Direct Actions

```python
# Execute action with safety checks
result = await bridge.executor.execute_action(
    "metric_adjustment",
    {
        "interface": "eth0",
        "current_metric": 10,
        "proposed_metric": 15
    }
)

if result.status == "completed":
    print("✓ Metric adjusted successfully")
elif result.status == "blocked":
    print(f"✗ Blocked: {result.error}")
```

### Multi-Agent Consensus

```python
# Create consensus proposal
proposal = bridge.consensus.create_proposal(
    consensus_type=ConsensusType.METRIC_ADJUSTMENT,
    description="Increase OSPF cost on eth0",
    parameters={"interface": "eth0", "proposed_metric": 20},
    required_votes=2
)

# Other RubberBand instances vote
bridge.consensus.vote(proposal.proposal_id, VoteType.APPROVE)

# Check status
status = bridge.consensus.get_proposal_status(proposal.proposal_id)
if status['status'] == 'approved':
    # Execute action
    pass
```

## Configuration

### Safety Constraints

```python
# Configure safety
bridge.safety.add_critical_interface("eth0")  # Requires approval
bridge.safety.set_autonomous_mode(True)        # Allow safe autonomous actions

# Adjust limits
bridge.safety.config["max_route_injections"] = 100
bridge.safety.config["min_change_interval"] = 60  # seconds
```

### LLM Configuration

```python
# Choose preferred provider
bridge.llm.preferred_provider = LLMProvider.CLAUDE

# Adjust conversation limits
bridge.llm.max_turns = 75

# Reset conversation
bridge.llm.reset_conversation()
```

## Intent Types

RubberBand understands these natural language intents:

### Query Intents
- `QUERY_STATUS` - "What is the status?"
- `QUERY_NEIGHBOR` - "Show me my neighbors"
- `QUERY_ROUTE` - "How do I reach 10.0.0.1?"
- `QUERY_LSA` - "Show me LSAs from router X"
- `QUERY_BGP_PEER` - "What's the state of BGP peer X?"
- `QUERY_RIB` - "Show me the routing table"

### Analysis Intents
- `ANALYZE_TOPOLOGY` - "Analyze the network topology"
- `ANALYZE_PATH` - "Why is traffic going through X?"
- `DETECT_ANOMALY` - "Are there any issues?"
- `EXPLAIN_DECISION` - "Why did you choose this route?"

### Action Intents (Require Approval)
- `ACTION_ADJUST_METRIC` - "Increase OSPF cost on eth0"
- `ACTION_INJECT_ROUTE` - "Advertise 10.0.0.0/24"
- `ACTION_MODIFY_PREFERENCE` - "Prefer routes from AS 65001"
- `ACTION_GRACEFUL_SHUTDOWN` - "Gracefully shut down BGP"

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/query` | POST | Natural language query |
| `/api/action` | POST | Execute action |
| `/api/state` | GET | Network state summary |
| `/api/state/ospf` | GET | OSPF state |
| `/api/state/bgp` | GET | BGP state |
| `/api/state/routes` | GET | Routing table |
| `/api/statistics` | GET | Comprehensive statistics |
| `/api/analytics/report` | GET | Analytics report |
| `/api/analytics/anomalies` | GET | Detect anomalies |
| `/api/proposals` | POST | Create consensus proposal |
| `/api/proposals` | GET | List proposals |
| `/api/proposals/{id}/vote` | POST | Vote on proposal |
| `/api/actions/history` | GET | Action history |
| `/api/actions/pending` | GET | Pending actions |
| `/api/actions/{id}/approve` | POST | Approve action |
| `/api/conversation/history` | GET | Conversation history |

## Directory Structure

```
wontyoubemyneighbor/agentic/
├── llm/                    # LLM provider interfaces
│   ├── interface.py       # Unified LLM interface
│   ├── openai_provider.py
│   ├── claude_provider.py
│   └── gemini_provider.py
├── reasoning/             # Intent parsing and decisions
│   ├── intent_parser.py
│   └── decision_engine.py
├── actions/               # Action execution
│   ├── safety.py
│   └── executor.py
├── knowledge/             # State management
│   ├── state_manager.py
│   └── analytics.py
├── multi_agent/           # Multi-agent coordination
│   ├── gossip.py
│   └── consensus.py
├── integration/           # Protocol connectors
│   ├── bridge.py
│   ├── ospf_connector.py
│   └── bgp_connector.py
├── api/                   # REST API
│   ├── server.py
│   └── run_server.py
└── cli/                   # CLI interface
    └── chat.py
```

## Testing

Run examples to verify installation:

```bash
# LLM interface
python wontyoubemyneighbor/agentic/llm/example.py

# Reasoning engine
python wontyoubemyneighbor/agentic/reasoning/example.py

# Action executor
python wontyoubemyneighbor/agentic/actions/example.py

# State manager
python wontyoubemyneighbor/agentic/knowledge/example.py

# Multi-agent
python wontyoubemyneighbor/agentic/multi_agent/example.py

# Integration
python wontyoubemyneighbor/agentic/integration/example.py

# API client
python wontyoubemyneighbor/agentic/api/client_example.py
```

## Contributing

RubberBand is part of the wontyoubemyneighbor project. See main project README for contribution guidelines.

## License

Same as wontyoubemyneighbor project.
