"""
Example usage of Intent Parser and Decision Engine

Demonstrates natural language intent parsing and intelligent decision-making.
"""

import asyncio
from .intent_parser import IntentParser, IntentType
from .decision_engine import DecisionEngine


async def example_intent_parsing():
    """Example: Parse natural language into intents"""
    print("=" * 60)
    print("Intent Parser Examples")
    print("=" * 60)

    parser = IntentParser()  # Without LLM for pattern matching

    # Example queries
    queries = [
        "Show me my OSPF neighbors",
        "How do I reach 10.0.0.1?",
        "What's the status of BGP peer 192.168.1.2?",
        "Are there any network issues?",
        "Increase the OSPF cost on eth0",
        "Show me the routing table",
    ]

    for query in queries:
        print(f"\nQuery: {query}")
        intent = await parser.parse(query)
        print(f"Intent Type: {intent.intent_type.value}")
        print(f"Confidence: {intent.confidence:.2f}")
        print(f"Parameters: {intent.parameters}")
        print(f"Requires Approval: {intent.requires_approval()}")


async def example_route_selection():
    """Example: Intelligent route selection with explanation"""
    print("\n" + "=" * 60)
    print("Decision Engine: Route Selection")
    print("=" * 60)

    engine = DecisionEngine()

    # Candidate routes to 10.0.0.0/24
    candidates = [
        {
            "next_hop": "192.168.1.2",
            "as_path": [65001, 65002, 65003],
            "med": 100,
            "local_pref": 100,
            "ibgp": False,
            "metric": 20
        },
        {
            "next_hop": "192.168.1.3",
            "as_path": [65001, 65002],  # Shorter AS path
            "med": 150,
            "local_pref": 100,
            "ibgp": False,
            "metric": 30
        },
        {
            "next_hop": "192.168.1.4",
            "as_path": [65001, 65002, 65003],
            "med": 80,  # Lower MED
            "local_pref": 120,  # Higher local pref
            "ibgp": True,
            "metric": 10
        }
    ]

    best_route, decision = await engine.select_best_route(
        destination="10.0.0.0/24",
        candidates=candidates
    )

    print(f"\nSelected Route: {best_route['next_hop']}")
    print(f"\nDecision Rationale:")
    print(decision.rationale)
    print(f"\nAlternatives:")
    for alt in decision.alternatives:
        print(f"  {alt}")


async def example_anomaly_detection():
    """Example: Detect network anomalies"""
    print("\n" + "=" * 60)
    print("Decision Engine: Anomaly Detection")
    print("=" * 60)

    engine = DecisionEngine()

    # Simulated network state with anomalies
    network_state = {
        "ospf": {
            "router_id": "1.1.1.1",
            "neighbors": [
                {
                    "neighbor_id": "2.2.2.2",
                    "state": "Full",
                    "state_changes": 12  # Flapping!
                },
                {
                    "neighbor_id": "3.3.3.3",
                    "state": "Full",
                    "state_changes": 2
                }
            ]
        },
        "bgp": {
            "local_as": 65001,
            "peers": [
                {
                    "peer": "192.168.1.2",
                    "as": 65002,
                    "state": "Idle",  # Down!
                },
                {
                    "peer": "192.168.1.3",
                    "as": 65003,
                    "state": "Established",
                    "prefix_count": 15000  # High!
                }
            ]
        }
    }

    anomalies = await engine.detect_anomalies(network_state)

    print(f"\nDetected {len(anomalies)} anomalies:\n")
    for i, anomaly in enumerate(anomalies, 1):
        print(f"{i}. [{anomaly['severity'].upper()}] {anomaly['type']}")
        print(f"   Protocol: {anomaly.get('protocol', 'N/A')}")
        print(f"   {anomaly['description']}")
        print(f"   Recommendation: {anomaly['recommendation']}")
        print()


async def example_metric_adjustment():
    """Example: Suggest OSPF metric adjustment"""
    print("=" * 60)
    print("Decision Engine: Metric Adjustment")
    print("=" * 60)

    engine = DecisionEngine()

    # High utilization interface
    decision = await engine.suggest_metric_adjustment(
        interface="eth0",
        current_metric=10,
        utilization=0.92,  # 92% utilized
        network_state={}
    )

    print(f"\nDecision: {decision.action}")
    print(f"Confidence: {decision.confidence*100:.0f}%")
    print(f"\n{decision.rationale}")


async def main():
    """Run all examples"""
    await example_intent_parsing()
    await example_route_selection()
    await example_anomaly_detection()
    await example_metric_adjustment()

    print("\n" + "=" * 60)
    print("Examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
