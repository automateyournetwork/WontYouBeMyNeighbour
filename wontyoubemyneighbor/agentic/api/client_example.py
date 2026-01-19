"""
Ralph API Client Examples

Demonstrates how to interact with Ralph via REST API.
"""

import asyncio
import json

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False


class RalphClient:
    """Simple client for Ralph REST API"""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url.rstrip("/")

    async def query(self, query: str) -> dict:
        """Send natural language query"""
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp not installed")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/query",
                json={"query": query}
            ) as response:
                return await response.json()

    async def get_state(self) -> dict:
        """Get network state"""
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp not installed")

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/api/state") as response:
                return await response.json()

    async def get_statistics(self) -> dict:
        """Get statistics"""
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp not installed")

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/api/statistics") as response:
                return await response.json()

    async def execute_action(self, action_type: str, parameters: dict) -> dict:
        """Execute action"""
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp not installed")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/action",
                json={
                    "action_type": action_type,
                    "parameters": parameters
                }
            ) as response:
                return await response.json()

    async def detect_anomalies(self) -> dict:
        """Detect anomalies"""
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp not installed")

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/api/analytics/anomalies") as response:
                return await response.json()

    async def create_proposal(self, consensus_type: str, description: str, parameters: dict) -> dict:
        """Create consensus proposal"""
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp not installed")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/proposals",
                json={
                    "consensus_type": consensus_type,
                    "description": description,
                    "parameters": parameters,
                    "required_votes": 2
                }
            ) as response:
                return await response.json()

    async def vote_on_proposal(self, proposal_id: str, vote: str, reason: str = None) -> dict:
        """Vote on proposal"""
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp not installed")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/proposals/{proposal_id}/vote",
                json={"proposal_id": proposal_id, "vote": vote, "reason": reason}
            ) as response:
                return await response.json()


async def example_basic_queries():
    """Example: Basic queries via API"""
    print("=" * 60)
    print("Basic API Queries Example")
    print("=" * 60)

    client = RalphClient()

    queries = [
        "Show me my OSPF neighbors",
        "What's the network status?",
        "Are there any issues?",
    ]

    print("\nExample API calls (requires running server):\n")

    for query in queries:
        print(f"POST /api/query")
        print(f"Body: {json.dumps({'query': query}, indent=2)}")
        print()

    print("Response format:")
    print(json.dumps({
        "response": "OSPF Neighbors:\n  • Neighbor 2.2.2.2\n    State: Full",
        "intent_type": "query_neighbor",
        "confidence": 0.95,
        "execution_time_ms": 234.5
    }, indent=2))


async def example_state_inspection():
    """Example: State inspection via API"""
    print("\n" + "=" * 60)
    print("State Inspection Example")
    print("=" * 60)

    print("\nGET /api/state")
    print("Returns: Network state summary and context")

    print("\nGET /api/state/ospf")
    print("Returns: OSPF-specific state")

    print("\nGET /api/state/bgp")
    print("Returns: BGP-specific state")

    print("\nGET /api/state/routes")
    print("Returns: Routing table")


async def example_action_execution():
    """Example: Execute actions via API"""
    print("\n" + "=" * 60)
    print("Action Execution Example")
    print("=" * 60)

    print("\nPOST /api/action")
    print(f"Body: {json.dumps({
        'action_type': 'metric_adjustment',
        'parameters': {
            'interface': 'eth0',
            'current_metric': 10,
            'proposed_metric': 15
        }
    }, indent=2)}")

    print("\nResponse:")
    print(json.dumps({
        "action_id": "action_0001",
        "status": "completed",
        "result": {
            "interface": "eth0",
            "old_metric": 10,
            "new_metric": 15
        }
    }, indent=2))


async def example_consensus():
    """Example: Consensus via API"""
    print("\n" + "=" * 60)
    print("Consensus Example")
    print("=" * 60)

    print("\n1. Create proposal:")
    print("POST /api/proposals")
    print(json.dumps({
        "consensus_type": "metric_adjustment",
        "description": "Increase cost on eth0",
        "parameters": {"interface": "eth0", "proposed_metric": 20},
        "required_votes": 2
    }, indent=2))

    print("\n2. Vote on proposal:")
    print("POST /api/proposals/{proposal_id}/vote")
    print(json.dumps({
        "proposal_id": "abc123",
        "vote": "approve",
        "reason": "Looks reasonable"
    }, indent=2))

    print("\n3. Check proposal status:")
    print("GET /api/proposals/{proposal_id}")


async def example_monitoring():
    """Example: Monitoring and analytics"""
    print("\n" + "=" * 60)
    print("Monitoring and Analytics Example")
    print("=" * 60)

    endpoints = {
        "/api/statistics": "Comprehensive statistics",
        "/api/analytics/report": "Full analytics report",
        "/api/analytics/anomalies": "Detected anomalies",
        "/api/actions/history": "Action execution history",
        "/api/actions/pending": "Actions awaiting approval",
        "/api/conversation/history": "LLM conversation history"
    }

    print("\nMonitoring endpoints:")
    for endpoint, description in endpoints.items():
        print(f"  GET {endpoint}")
        print(f"      {description}")


async def example_curl_commands():
    """Example: curl commands"""
    print("\n" + "=" * 60)
    print("Example curl Commands")
    print("=" * 60)

    commands = [
        ('Health check', 'curl http://localhost:8080/health'),
        ('Query Ralph', '''curl -X POST http://localhost:8080/api/query \\
  -H "Content-Type: application/json" \\
  -d '{"query": "Show me my OSPF neighbors"}' '''),
        ('Get state', 'curl http://localhost:8080/api/state'),
        ('Get statistics', 'curl http://localhost:8080/api/statistics'),
        ('Detect anomalies', 'curl http://localhost:8080/api/analytics/anomalies'),
    ]

    for name, command in commands:
        print(f"\n{name}:")
        print(f"  {command}")


async def main():
    """Run all examples"""
    await example_basic_queries()
    await example_state_inspection()
    await example_action_execution()
    await example_consensus()
    await example_monitoring()
    await example_curl_commands()

    print("\n" + "=" * 60)
    print("API Examples Complete!")
    print("=" * 60)
    print("\nTo start the server:")
    print("  python -m wontyoubemyneighbor.agentic.api.run_server")
    print("\nAPI Documentation:")
    print("  http://localhost:8080/docs")


if __name__ == "__main__":
    asyncio.run(main())
