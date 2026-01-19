"""
Example: Full Agentic Integration

Demonstrates complete integration of agentic layer with OSPF/BGP protocols.
"""

import asyncio
from .bridge import AgenticBridge
from .ospf_connector import OSPFConnector
from .bgp_connector import BGPConnector


async def example_basic_queries():
    """Example: Basic natural language queries"""
    print("=" * 60)
    print("Basic Agentic Queries")
    print("=" * 60)

    # Create agentic bridge
    bridge = AgenticBridge(
        ralph_id="ralph-demo",
        autonomous_mode=False  # Require approval for actions
    )

    # Initialize (would initialize LLM providers with real API keys)
    # await bridge.initialize()

    # Simulate some queries (without actual LLM/protocols for demo)
    queries = [
        "Show me my OSPF neighbors",
        "What's the status of my network?",
        "Are there any issues?",
        "How do I reach 10.0.0.1?",
        "Show me my BGP peers"
    ]

    print("\nExample queries:")
    for query in queries:
        print(f"\nUser: {query}")
        print("Ralph: [Would process via LLM and return structured response]")


async def example_with_ospf():
    """Example: Integration with OSPF"""
    print("\n" + "=" * 60)
    print("OSPF Integration Example")
    print("=" * 60)

    # Mock OSPF interface
    class MockOSPFInterface:
        def __init__(self):
            self.interface_name = "eth0"
            self.router_id = "1.1.1.1"
            self.area_id = "0.0.0.0"
            self.cost = 10
            self.neighbors = {}

    ospf_interface = MockOSPFInterface()

    # Create connector
    ospf_connector = OSPFConnector(ospf_interface)

    # Get interface info
    info = ospf_connector.get_interface_info()
    print("\nOSPF Interface Info:")
    for key, value in info.items():
        print(f"  {key}: {value}")

    # Adjust cost
    result = await ospf_connector.adjust_interface_cost(20)
    print(f"\nCost adjustment: {result}")


async def example_with_bgp():
    """Example: Integration with BGP"""
    print("\n" + "=" * 60)
    print("BGP Integration Example")
    print("=" * 60)

    # Mock BGP speaker
    class MockBGPSpeaker:
        def __init__(self):
            self.local_as = 65001
            self.router_id = "1.1.1.1"
            self.peers = {}
            self.rib = {}

    bgp_speaker = MockBGPSpeaker()

    # Create connector
    bgp_connector = BGPConnector(bgp_speaker)

    # Get speaker info
    info = bgp_connector.get_speaker_info()
    print("\nBGP Speaker Info:")
    for key, value in info.items():
        print(f"  {key}: {value}")

    # Inject route
    result = await bgp_connector.inject_route(
        network="10.0.0.0/24",
        next_hop="192.168.1.2",
        as_path=[65001, 65002]
    )
    print(f"\nRoute injection: {result}")

    # Get RIB
    rib = await bgp_connector.get_rib()
    print(f"\nBGP RIB ({len(rib)} routes):")
    for route in rib:
        print(f"  {route['network']} via {route['next_hop']}")


async def example_full_integration():
    """Example: Full integration with both protocols"""
    print("\n" + "=" * 60)
    print("Full Integration Example")
    print("=" * 60)

    # Create mock protocols
    class MockOSPFInterface:
        def __init__(self):
            self.interface_name = "eth0"
            self.router_id = "1.1.1.1"
            self.neighbors = {}

    class MockBGPSpeaker:
        def __init__(self):
            self.local_as = 65001
            self.router_id = "1.1.1.1"
            self.peers = {}
            self.rib = {}

    # Create agentic bridge
    bridge = AgenticBridge(ralph_id="ralph-full-demo")

    # Create connectors
    ospf_conn = OSPFConnector(MockOSPFInterface())
    bgp_conn = BGPConnector(MockBGPSpeaker())

    # Inject connectors
    bridge.set_ospf_connector(ospf_conn)
    bridge.set_bgp_connector(bgp_conn)

    print("\n✓ Agentic bridge configured with OSPF and BGP connectors")

    # Get statistics
    stats = bridge.get_statistics()
    print("\nBridge Statistics:")
    print(f"  Ralph ID: {stats['ralph_id']}")
    print(f"  LLM Turns: {stats['llm']['turns']}/{stats['llm']['max_turns']}")
    print(f"  State Snapshots: {stats['state']['snapshots']}")
    print(f"  Completed Actions: {stats['actions']['completed']}")


async def example_autonomous_decision():
    """Example: Autonomous decision-making"""
    print("\n" + "=" * 60)
    print("Autonomous Decision Example")
    print("=" * 60)

    bridge = AgenticBridge(
        ralph_id="ralph-auto",
        autonomous_mode=True  # Allow autonomous actions
    )

    print("\n✓ Autonomous mode enabled")
    print("\nRalph can now make safe decisions autonomously:")
    print("  ✓ Small metric adjustments")
    print("  ✓ Anomaly detection and alerting")
    print("  ✓ Route analytics and recommendations")
    print("\nDangerous actions still require human approval:")
    print("  ⚠ Large metric changes (>50%)")
    print("  ⚠ Route injection")
    print("  ⚠ Graceful shutdown")


async def example_multi_ralph():
    """Example: Multiple Ralph instances with coordination"""
    print("\n" + "=" * 60)
    print("Multi-Ralph Coordination Example")
    print("=" * 60)

    # Create three Ralph instances
    ralph1 = AgenticBridge(ralph_id="ralph-1")
    ralph2 = AgenticBridge(ralph_id="ralph-2")
    ralph3 = AgenticBridge(ralph_id="ralph-3")

    # Register as gossip peers
    ralph1.gossip.register_peer("ralph-2", "192.168.1.2")
    ralph1.gossip.register_peer("ralph-3", "192.168.1.3")

    ralph2.gossip.register_peer("ralph-1", "192.168.1.1")
    ralph2.gossip.register_peer("ralph-3", "192.168.1.3")

    ralph3.gossip.register_peer("ralph-1", "192.168.1.1")
    ralph3.gossip.register_peer("ralph-2", "192.168.1.2")

    print("\n✓ Three Ralph instances configured")
    print("✓ Gossip protocol mesh established")
    print("\nRalphs can now:")
    print("  • Share network state via gossip")
    print("  • Coordinate decisions via consensus")
    print("  • Alert each other of anomalies")
    print("  • Reach distributed agreement on actions")


async def main():
    """Run all examples"""
    await example_basic_queries()
    await example_with_ospf()
    await example_with_bgp()
    await example_full_integration()
    await example_autonomous_decision()
    await example_multi_ralph()

    print("\n" + "=" * 60)
    print("Integration Examples Complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Configure LLM API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY)")
    print("  2. Connect to real OSPF/BGP instances")
    print("  3. Start the agentic bridge")
    print("  4. Query Ralph via natural language!")


if __name__ == "__main__":
    asyncio.run(main())
