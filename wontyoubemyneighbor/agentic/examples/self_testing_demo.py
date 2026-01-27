"""
Self-Testing Network Demo

Demonstrates how network agents can autonomously:
1. Generate pyATS AEtest scripts based on their configuration
2. Execute tests via pyATS MCP server
3. Interpret results and take corrective actions

This is the core of the "Self-Testing Network" concept where
each agent is both the test subject AND the test author.

Usage:
    python -m wontyoubemyneighbor.agentic.examples.self_testing_demo
"""

import asyncio
import json
from datetime import datetime

# Import self-testing components
from wontyoubemyneighbor.agentic.tests import (
    DynamicTestGenerator,
    SelfTestingAgent,
    TestCategory,
    TestTrigger,
)
from wontyoubemyneighbor.agentic.mcp import (
    PyATSMCPClient,
    init_pyats_for_agent,
)


# Example TOON configuration for a router agent
EXAMPLE_AGENT_CONFIG = {
    "id": "core-router-1",
    "n": "Core Router 1",
    "v": "1.0",
    "r": "10.255.255.1",  # Router ID

    "ifs": [
        {
            "id": "eth0",
            "n": "GigabitEthernet0/0",
            "t": "eth",
            "a": ["172.16.0.1/30"],
            "s": "up",
            "mtu": 1500,
            "description": "Link to Distribution-1",
            "l1": {
                "peer_agent": "dist-router-1",
                "peer_if": "GigabitEthernet0/0",
                "subnet": "172.16.0.0/30",
            }
        },
        {
            "id": "eth1",
            "n": "GigabitEthernet0/1",
            "t": "eth",
            "a": ["172.16.0.5/30"],
            "s": "up",
            "mtu": 1500,
            "description": "Link to Distribution-2",
            "l1": {
                "peer_agent": "dist-router-2",
                "peer_if": "GigabitEthernet0/0",
                "subnet": "172.16.0.4/30",
            }
        },
        {
            "id": "lo0",
            "n": "Loopback0",
            "t": "lo",
            "a": ["10.255.255.1/32"],
            "s": "up",
            "description": "Router Loopback",
        }
    ],

    "protos": [
        {
            "p": "ospf",
            "r": "10.255.255.1",
            "a": "0.0.0.0",
            "neighbors": [
                {"router_id": "10.255.255.2", "interface": "GigabitEthernet0/0"},
                {"router_id": "10.255.255.3", "interface": "GigabitEthernet0/1"},
            ],
            "opts": {
                "hello_interval": 10,
                "dead_interval": 40,
            }
        },
        {
            "p": "ibgp",
            "r": "10.255.255.1",
            "asn": 65001,
            "peers": [
                {"ip": "10.255.255.10", "asn": 65001, "description": "Route Reflector"},
            ],
            "opts": {
                "next_hop_self": True,
            }
        }
    ],
}


def demonstrate_test_generation():
    """
    Demonstrate how agents generate tests from their configuration.

    This shows the test SCRIPT generation - no execution yet.
    """
    print("=" * 70)
    print("SELF-TESTING NETWORK DEMO: Dynamic Test Generation")
    print("=" * 70)

    # Create generator from agent config
    generator = DynamicTestGenerator(EXAMPLE_AGENT_CONFIG)

    print(f"\nAgent: {generator.agent_id}")
    print(f"Router ID: {generator.router_id}")
    print(f"Interfaces: {len(generator.interfaces)}")
    print(f"Protocols: {[p.get('p') for p in generator.protocols]}")

    # 1. Generate neighbor reachability test
    print("\n" + "-" * 50)
    print("1. GENERATING: Neighbor Reachability Test")
    print("-" * 50)

    neighbor_test = generator.generate_neighbor_reachability_test(
        trigger=TestTrigger.SELF_ASSESSMENT
    )

    print(f"Test ID: {neighbor_test.test_id}")
    print(f"Category: {neighbor_test.category.value}")
    print(f"Trigger: {neighbor_test.trigger.value}")
    print(f"Description: {neighbor_test.description}")
    print(f"Expected Outcomes: {neighbor_test.expected_outcomes}")
    print(f"\nGenerated TEST_DATA:")
    print(json.dumps(neighbor_test.test_data, indent=2))

    # 2. Generate OSPF neighbor state test
    print("\n" + "-" * 50)
    print("2. GENERATING: OSPF Neighbor State Test")
    print("-" * 50)

    ospf_test = generator.generate_ospf_neighbor_test(
        trigger=TestTrigger.STATE_CHANGE
    )

    print(f"Test ID: {ospf_test.test_id}")
    print(f"Description: {ospf_test.description}")
    print(f"\nGenerated TEST_DATA:")
    print(json.dumps(ospf_test.test_data, indent=2))

    # 3. Generate BGP peer state test
    print("\n" + "-" * 50)
    print("3. GENERATING: BGP Peer State Test")
    print("-" * 50)

    bgp_test = generator.generate_bgp_peer_test(
        trigger=TestTrigger.STATE_CHANGE
    )

    print(f"Test ID: {bgp_test.test_id}")
    print(f"Description: {bgp_test.description}")
    print(f"\nGenerated TEST_DATA:")
    print(json.dumps(bgp_test.test_data, indent=2))

    # 4. Generate comprehensive self-test
    print("\n" + "-" * 50)
    print("4. GENERATING: Comprehensive Self-Assessment")
    print("-" * 50)

    full_test = generator.generate_comprehensive_self_test()

    print(f"Test ID: {full_test.test_id}")
    print(f"Description: {full_test.description}")
    print(f"Expected Outcomes:")
    for outcome in full_test.expected_outcomes:
        print(f"  - {outcome}")
    print(f"\nGenerated TEST_DATA:")
    print(json.dumps(full_test.test_data, indent=2))

    # Show the actual generated script (truncated)
    print("\n" + "-" * 50)
    print("5. SAMPLE GENERATED AETEST SCRIPT (first 50 lines)")
    print("-" * 50)
    script_lines = full_test.script.split('\n')[:50]
    for i, line in enumerate(script_lines, 1):
        print(f"{i:3}: {line}")
    print("... (script continues)")

    return generator, full_test


async def demonstrate_execution_flow():
    """
    Demonstrate the full execution flow (simulated without real pyATS).

    In production, this would connect to real devices via pyATS MCP.
    """
    print("\n" + "=" * 70)
    print("SELF-TESTING NETWORK DEMO: Execution Flow (Simulated)")
    print("=" * 70)

    generator = DynamicTestGenerator(EXAMPLE_AGENT_CONFIG)

    # Simulate different test scenarios
    scenarios = [
        {
            "name": "Scheduled Self-Assessment",
            "trigger": TestTrigger.SCHEDULED,
            "action": "Run comprehensive self-test on schedule",
        },
        {
            "name": "Neighbor Down Detection",
            "trigger": TestTrigger.STATE_CHANGE,
            "action": "OSPF neighbor 10.255.255.2 went down - testing connectivity",
        },
        {
            "name": "Human Request",
            "trigger": TestTrigger.HUMAN_REQUEST,
            "action": "Operator requested BGP peer validation",
        },
        {
            "name": "Anomaly Response",
            "trigger": TestTrigger.ANOMALY,
            "action": "Detected route flapping - testing path stability",
        },
    ]

    for scenario in scenarios:
        print(f"\n--- Scenario: {scenario['name']} ---")
        print(f"Trigger: {scenario['trigger'].value}")
        print(f"Action: {scenario['action']}")

        # Generate appropriate test
        if scenario['trigger'] == TestTrigger.SCHEDULED:
            test = generator.generate_comprehensive_self_test(
                trigger=scenario['trigger']
            )
        elif "OSPF" in scenario['action']:
            test = generator.generate_ospf_neighbor_test(
                trigger=scenario['trigger']
            )
        elif "BGP" in scenario['action']:
            test = generator.generate_bgp_peer_test(
                trigger=scenario['trigger']
            )
        else:
            test = generator.generate_neighbor_reachability_test(
                trigger=scenario['trigger']
            )

        print(f"Generated Test: {test.test_name}")
        print(f"Test ID: {test.test_id}")

        # In production: result = await self_tester.execute_test(test)
        # Simulated result:
        print("Status: [Would execute via pyATS MCP]")


def demonstrate_agent_reasoning():
    """
    Demonstrate how agents reason about WHAT to test.

    The agent analyzes its state and decides which tests to generate.
    """
    print("\n" + "=" * 70)
    print("SELF-TESTING NETWORK DEMO: Agent Test Selection Reasoning")
    print("=" * 70)

    generator = DynamicTestGenerator(EXAMPLE_AGENT_CONFIG)

    print(f"\nAgent {generator.agent_id} reasoning about what to test...")

    # Analyze configuration
    has_ospf = any(p.get('p') in ['ospf', 'ospfv3'] for p in generator.protocols)
    has_bgp = any(p.get('p') in ['ibgp', 'ebgp'] for p in generator.protocols)
    num_interfaces = len([i for i in generator.interfaces if i.get('t') != 'lo'])

    print(f"\nConfiguration Analysis:")
    print(f"  - OSPF enabled: {has_ospf}")
    print(f"  - BGP enabled: {has_bgp}")
    print(f"  - Physical interfaces: {num_interfaces}")

    print(f"\nAgent decides to generate:")

    tests_to_generate = []

    # Always test basic connectivity
    tests_to_generate.append("Neighbor Reachability Test")
    print(f"  1. Neighbor Reachability Test (always)")

    # Protocol-specific tests
    if has_ospf:
        tests_to_generate.append("OSPF Neighbor State Test")
        print(f"  2. OSPF Neighbor State Test (OSPF is configured)")

    if has_bgp:
        tests_to_generate.append("BGP Peer State Test")
        print(f"  3. BGP Peer State Test (BGP is configured)")

    # Interface tests if we have interfaces
    if num_interfaces > 0:
        tests_to_generate.append("Interface State Test")
        print(f"  4. Interface State Test ({num_interfaces} interfaces)")

    print(f"\nTotal tests to generate: {len(tests_to_generate)}")

    # Generate all decided tests
    print(f"\nGenerating test scripts...")
    generated = []

    generated.append(generator.generate_neighbor_reachability_test())
    if has_ospf:
        generated.append(generator.generate_ospf_neighbor_test())
    if has_bgp:
        generated.append(generator.generate_bgp_peer_test())
    if num_interfaces > 0:
        generated.append(generator.generate_interface_state_test())

    for test in generated:
        print(f"  - {test.test_name}: {test.test_id}")

    return generated


def main():
    """Run all demonstrations"""
    print("\n" + "#" * 70)
    print("#  SELF-TESTING NETWORK: Agent-Generated pyATS Tests")
    print("#" * 70)
    print("""
    The Self-Testing Network concept enables network agents to:

    1. ANALYZE their own configuration (TOON format)
    2. GENERATE appropriate pyATS AEtest scripts
    3. EXECUTE tests via pyATS MCP server
    4. INTERPRET results and take action

    This creates a network that continuously validates itself,
    with each agent responsible for testing its own health.
    """)

    # Demo 1: Test generation
    generator, test = demonstrate_test_generation()

    # Demo 2: Agent reasoning
    tests = demonstrate_agent_reasoning()

    # Demo 3: Execution flow (simulated)
    asyncio.run(demonstrate_execution_flow())

    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print("""
    To run with real pyATS MCP:

    1. Start pyATS MCP server:
       python3 /path/to/pyats_mcp_server.py

    2. Configure testbed.yaml with your devices

    3. In your agent code:
       from wontyoubemyneighbor.agentic.integration.bridge import AgenticBridge

       bridge = AgenticBridge(asi_id="core-router-1")
       await bridge.enable_self_testing(
           pyats_server_path="/path/to/pyats_mcp_server.py",
           testbed_path="/path/to/testbed.yaml"
       )
       bridge.set_agent_config(AGENT_CONFIG)

       # Run self-assessment
       result = await bridge.run_self_assessment()

       # Or test on state change
       result = await bridge.test_on_state_change(
           'neighbor_down',
           {'neighbor_id': '10.255.255.2'}
       )
    """)


if __name__ == "__main__":
    main()
