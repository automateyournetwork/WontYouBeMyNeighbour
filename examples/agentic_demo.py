"""
End-to-End Agentic Network Router Demo

Demonstrates complete integration of Ralph with OSPF and BGP protocols.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wontyoubemyneighbor.agentic.integration.bridge import AgenticBridge
from wontyoubemyneighbor.agentic.integration.ospf_connector import OSPFConnector
from wontyoubemyneighbor.agentic.integration.bgp_connector import BGPConnector


class DemoOSPFInterface:
    """Mock OSPF interface for demonstration"""

    def __init__(self, router_id="1.1.1.1", interface_name="eth0"):
        self.router_id = router_id
        self.interface_name = interface_name
        self.area_id = "0.0.0.0"
        self.cost = 10
        self.hello_interval = 10
        self.dead_interval = 40
        self.state = "DR"

        # Simulated neighbors
        self.neighbors = {
            "2.2.2.2": type('Neighbor', (), {
                'neighbor_id': "2.2.2.2",
                'state': "Full",
                'address': "fe80::2",
                'priority': 1,
                'dr': "0.0.0.0",
                'bdr': "0.0.0.0"
            }),
            "3.3.3.3": type('Neighbor', (), {
                'neighbor_id': "3.3.3.3",
                'state': "Full",
                'address': "fe80::3",
                'priority': 1,
                'dr': "0.0.0.0",
                'bdr': "0.0.0.0"
            })
        }

        # Simulated LSDB
        self.lsdb = {
            ("2.2.2.2", 0x2001): {
                'type': 0x2001,
                'advertising_router': "2.2.2.2",
                'ls_id': "2.2.2.2",
                'sequence': 0x80000001,
                'age': 120
            },
            ("3.3.3.3", 0x2001): {
                'type': 0x2001,
                'advertising_router': "3.3.3.3",
                'ls_id': "3.3.3.3",
                'sequence': 0x80000002,
                'age': 95
            }
        }


class DemoBGPSpeaker:
    """Mock BGP speaker for demonstration"""

    def __init__(self, local_as=65001, router_id="1.1.1.1"):
        self.local_as = local_as
        self.router_id = router_id

        # Simulated peers
        self.peers = {
            "192.168.1.2": type('Peer', (), {
                'peer_addr': "192.168.1.2",
                'peer_as': 65002,
                'state': "Established",
                'local_addr': "192.168.1.1",
                'uptime': 3600,
                'prefixes_received': 42,
                'prefixes_sent': 15
            }),
            "192.168.1.3": type('Peer', (), {
                'peer_addr': "192.168.1.3",
                'peer_as': 65001,  # iBGP
                'state': "Established",
                'local_addr': "192.168.1.1",
                'uptime': 7200,
                'prefixes_received': 100,
                'prefixes_sent': 50
            })
        }

        # Simulated RIB
        self.rib = {
            ("10.0.0.0", 24, 1, 1): {
                'next_hop': "192.168.1.2",
                'as_path': [65002, 65003],
                'local_pref': 100,
                'med': 50,
                'origin': 'igp'
            },
            ("172.16.0.0", 16, 1, 1): {
                'next_hop': "192.168.1.3",
                'as_path': [65001],
                'local_pref': 120,
                'med': 0,
                'origin': 'igp'
            },
            ("192.168.0.0", 16, 1, 1): {
                'next_hop': "192.168.1.2",
                'as_path': [65002],
                'local_pref': 100,
                'med': 100,
                'origin': 'igp'
            }
        }


async def demo_basic_queries(bridge):
    """Demo: Basic natural language queries"""
    print("\n" + "=" * 70)
    print("DEMO 1: Basic Natural Language Queries")
    print("=" * 70)

    queries = [
        "Show me my OSPF neighbors",
        "What's my network status?",
        "Show me my BGP peers",
        "How many routes do I have?",
    ]

    for query in queries:
        print(f"\n>>> User: {query}")
        print("Ralph: ", end="", flush=True)

        response = await bridge.query(query)
        print(response)

        await asyncio.sleep(0.5)


async def demo_state_inspection(bridge):
    """Demo: State inspection and analytics"""
    print("\n" + "=" * 70)
    print("DEMO 2: State Inspection and Analytics")
    print("=" * 70)

    # Update state
    await bridge.state_manager.update_state()

    # Show summary
    print("\n>>> Network State Summary:")
    summary = bridge.state_manager.get_state_summary()
    print(summary)

    # Create snapshot
    snapshot = bridge.state_manager.create_snapshot()
    print(f"\n✓ Snapshot created: {snapshot.timestamp.strftime('%H:%M:%S')}")

    # Get metrics
    metrics = bridge.state_manager._compute_metrics()
    print(f"\n>>> Network Metrics:")
    print(f"  Health Score: {metrics['health_score']:.1f}/100")
    print(f"  OSPF Stability: {metrics['ospf_neighbor_stability']*100:.0f}%")
    print(f"  BGP Stability: {metrics['bgp_peer_stability']*100:.0f}%")


async def demo_anomaly_detection(bridge):
    """Demo: Anomaly detection"""
    print("\n" + "=" * 70)
    print("DEMO 3: Anomaly Detection")
    print("=" * 70)

    print("\n>>> User: Are there any network issues?")
    print("Ralph: ", end="", flush=True)

    response = await bridge.query("Are there any network issues?")
    print(response)


async def demo_decision_making(bridge):
    """Demo: Intelligent decision making"""
    print("\n" + "=" * 70)
    print("DEMO 4: Intelligent Route Decision")
    print("=" * 70)

    # Simulate route selection
    candidates = [
        {
            "next_hop": "192.168.1.2",
            "as_path": [65002, 65003],
            "med": 50,
            "local_pref": 100,
            "ibgp": False,
            "metric": 20
        },
        {
            "next_hop": "192.168.1.3",
            "as_path": [65001],
            "med": 0,
            "local_pref": 120,
            "ibgp": True,
            "metric": 10
        }
    ]

    print("\n>>> Selecting best route to 10.0.0.0/24...")
    print("Candidates:")
    for i, route in enumerate(candidates, 1):
        print(f"  {i}. via {route['next_hop']}")
        print(f"     AS Path: {route['as_path']}")
        print(f"     MED: {route['med']}, Local Pref: {route['local_pref']}")

    best_route, decision = await bridge.decision_engine.select_best_route(
        destination="10.0.0.0/24",
        candidates=candidates
    )

    print(f"\n✓ Selected: via {best_route['next_hop']}")
    print(f"\nRationale:")
    print(decision.rationale)


async def demo_safe_actions(bridge):
    """Demo: Safe autonomous actions"""
    print("\n" + "=" * 70)
    print("DEMO 5: Safe Action Execution")
    print("=" * 70)

    # Enable autonomous mode for demo
    bridge.safety.set_autonomous_mode(True)
    print("\n✓ Autonomous mode enabled")

    # Safe action: small metric change
    print("\n>>> User: Increase OSPF cost on eth0 to 12")
    print("Ralph: ", end="", flush=True)

    result = await bridge.executor.execute_action(
        "metric_adjustment",
        {
            "interface": "eth0",
            "current_metric": 10,
            "proposed_metric": 12
        }
    )

    if result.status.value == "completed":
        print(f"✓ Successfully adjusted OSPF cost on eth0 to 12")
        print(f"  (Execution time: {result.execution_time_ms:.1f}ms)")
    else:
        print(f"Action status: {result.status.value}")

    # Unsafe action: large change
    print("\n>>> Attempting large metric change (requires approval)...")

    bridge.safety.set_autonomous_mode(False)  # Disable autonomous

    result = await bridge.executor.execute_action(
        "metric_adjustment",
        {
            "interface": "eth0",
            "current_metric": 10,
            "proposed_metric": 100
        }
    )

    print(f"  Status: {result.status.value}")
    if result.error:
        print(f"  {result.error}")


async def demo_multi_agent(bridge):
    """Demo: Multi-agent coordination"""
    print("\n" + "=" * 70)
    print("DEMO 6: Multi-Agent Coordination")
    print("=" * 70)

    # Create consensus proposal
    print("\n>>> Creating consensus proposal...")

    from wontyoubemyneighbor.agentic.multi_agent.consensus import ConsensusType, VoteType

    proposal = bridge.consensus.create_proposal(
        consensus_type=ConsensusType.METRIC_ADJUSTMENT,
        description="Increase OSPF cost on eth0 to 20",
        parameters={"interface": "eth0", "proposed_metric": 20},
        required_votes=2
    )

    print(f"  Proposal ID: {proposal.proposal_id}")
    print(f"  Type: {proposal.consensus_type.value}")
    print(f"  Description: {proposal.description}")

    # Vote on proposal
    print("\n>>> Voting on proposal...")
    bridge.consensus.vote(proposal.proposal_id, VoteType.APPROVE, "Looks reasonable")

    # Simulate vote from another Ralph
    bridge.consensus.receive_vote(proposal.proposal_id, "ralph-2", "approve")

    # Check status
    status = bridge.consensus.get_proposal_status(proposal.proposal_id)
    print(f"\n  Status: {status['status']}")
    print(f"  Votes: {status['vote_counts']}")

    if status['status'] == 'approved':
        print("\n  ✓ Consensus reached! Action approved by distributed vote.")


async def demo_statistics(bridge):
    """Demo: Statistics and monitoring"""
    print("\n" + "=" * 70)
    print("DEMO 7: Statistics and Monitoring")
    print("=" * 70)

    stats = bridge.get_statistics()

    print("\n>>> Ralph Statistics:")
    print(f"\nLLM Interface:")
    print(f"  Conversation Turns: {stats['llm']['turns']}/{stats['llm']['max_turns']}")
    print(f"  Active Providers: {stats['llm']['providers']}")

    print(f"\nNetwork State:")
    print(f"  Snapshots Collected: {stats['state']['snapshots']}")
    print(f"  Health Score: {stats['state']['metrics']['health_score']:.1f}/100")

    print(f"\nAction Execution:")
    print(f"  Completed Actions: {stats['actions']['completed']}")
    print(f"  Pending Approval: {stats['actions']['pending']}")

    print(f"\nGossip Protocol:")
    print(f"  Known Peers: {stats['gossip']['peers']}")
    print(f"  Messages Seen: {stats['gossip']['messages_seen']}")

    print(f"\nConsensus Engine:")
    print(f"  Active Proposals: {stats['consensus']['active_proposals']}")
    print(f"  Completed Proposals: {stats['consensus']['completed_proposals']}")


async def main():
    """Run complete demo"""
    print("=" * 70)
    print("           Ralph: Agentic Network Router Demo")
    print("=" * 70)
    print("\nThis demo shows Ralph's capabilities without requiring real")
    print("network equipment or LLM API keys.")
    print("\nNote: Natural language queries are simulated (no actual LLM calls)")

    # Create mock protocols
    ospf_interface = DemoOSPFInterface(router_id="1.1.1.1")
    bgp_speaker = DemoBGPSpeaker(local_as=65001)

    # Create agentic bridge (without LLM for demo)
    print("\n>>> Initializing Ralph...")
    bridge = AgenticBridge(
        ralph_id="ralph-demo",
        autonomous_mode=False
    )

    # Connect protocols
    ospf_connector = OSPFConnector(ospf_interface)
    bgp_connector = BGPConnector(bgp_speaker)

    bridge.set_ospf_connector(ospf_connector)
    bridge.set_bgp_connector(bgp_connector)

    print("✓ Ralph initialized")
    print(f"  OSPF: {ospf_interface.router_id} on {ospf_interface.interface_name}")
    print(f"  BGP: AS{bgp_speaker.local_as}, Router ID {bgp_speaker.router_id}")

    # Start bridge
    await bridge.start()

    try:
        # Run demos
        await demo_basic_queries(bridge)
        await demo_state_inspection(bridge)
        await demo_anomaly_detection(bridge)
        await demo_decision_making(bridge)
        await demo_safe_actions(bridge)
        await demo_multi_agent(bridge)
        await demo_statistics(bridge)

        print("\n" + "=" * 70)
        print("                    Demo Complete!")
        print("=" * 70)
        print("\nNext Steps:")
        print("  1. Set up LLM API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY)")
        print("  2. Connect to real OSPF/BGP instances")
        print("  3. Run the CLI: python -m wontyoubemyneighbor.agentic.cli.chat")
        print("  4. Or start API: python -m wontyoubemyneighbor.agentic.api.run_server")
        print("\nDocumentation: wontyoubemyneighbor/agentic/README.md")

    finally:
        # Cleanup
        await bridge.stop()


if __name__ == "__main__":
    asyncio.run(main())
