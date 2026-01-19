"""
Example usage of Multi-Agent Coordination

Demonstrates gossip protocol and consensus between Ralph instances.
"""

import asyncio
from .gossip import GossipProtocol, MessageType
from .consensus import ConsensusEngine, ConsensusType, VoteType


async def example_gossip_protocol():
    """Example: Set up gossip network between Ralph instances"""
    print("=" * 60)
    print("Gossip Protocol Example")
    print("=" * 60)

    # Create three Ralph instances
    ralph1 = GossipProtocol(ralph_id="ralph-1", fanout=2, gossip_interval=2.0)
    ralph2 = GossipProtocol(ralph_id="ralph-2", fanout=2, gossip_interval=2.0)
    ralph3 = GossipProtocol(ralph_id="ralph-3", fanout=2, gossip_interval=2.0)

    # Register peers
    ralph1.register_peer("ralph-2", "192.168.1.2")
    ralph1.register_peer("ralph-3", "192.168.1.3")

    ralph2.register_peer("ralph-1", "192.168.1.1")
    ralph2.register_peer("ralph-3", "192.168.1.3")

    ralph3.register_peer("ralph-1", "192.168.1.1")
    ralph3.register_peer("ralph-2", "192.168.1.2")

    # Register message handlers
    async def handle_state_update(message):
        print(f"[{ralph2.ralph_id}] Received state update from {message.sender_id}")

    ralph2.register_handler(MessageType.STATE_UPDATE, handle_state_update)

    # Start gossip protocols
    await ralph1.start()
    await ralph2.start()
    await ralph3.start()

    # Ralph1 broadcasts state update
    message = ralph1.create_message(
        MessageType.STATE_UPDATE,
        payload={
            "ospf_neighbors": 3,
            "bgp_peers": 2,
            "health_score": 95.5
        }
    )

    print(f"\n[ralph-1] Broadcasting state update...")
    await ralph1.broadcast(message)

    # Let gossip propagate
    await asyncio.sleep(1)

    # Check statistics
    print(f"\n[ralph-1] Stats: {ralph1.get_statistics()}")
    print(f"[ralph-2] Stats: {ralph2.get_statistics()}")
    print(f"[ralph-3] Stats: {ralph3.get_statistics()}")

    # Stop gossip
    await ralph1.stop()
    await ralph2.stop()
    await ralph3.stop()


async def example_consensus():
    """Example: Distributed consensus voting"""
    print("\n" + "=" * 60)
    print("Consensus Engine Example")
    print("=" * 60)

    # Create gossip network
    gossip1 = GossipProtocol(ralph_id="ralph-1")
    gossip2 = GossipProtocol(ralph_id="ralph-2")
    gossip3 = GossipProtocol(ralph_id="ralph-3")

    # Create consensus engines
    consensus1 = ConsensusEngine(ralph_id="ralph-1", gossip_protocol=gossip1)
    consensus2 = ConsensusEngine(ralph_id="ralph-2", gossip_protocol=gossip2)
    consensus3 = ConsensusEngine(ralph_id="ralph-3", gossip_protocol=gossip3)

    # Ralph1 creates proposal
    proposal = consensus1.create_proposal(
        consensus_type=ConsensusType.METRIC_ADJUSTMENT,
        description="Increase OSPF cost on eth0 from 10 to 15",
        parameters={
            "interface": "eth0",
            "current_metric": 10,
            "proposed_metric": 15
        },
        required_votes=2
    )

    print(f"\n[ralph-1] Created proposal: {proposal.proposal_id}")
    print(f"Description: {proposal.description}")

    # Other Ralphs receive proposal
    consensus2.receive_proposal(proposal.to_dict())
    consensus3.receive_proposal(proposal.to_dict())

    print("\n[ralph-2] Received proposal")
    print("[ralph-3] Received proposal")

    # Vote on proposal
    consensus1.vote(proposal.proposal_id, VoteType.APPROVE, "Proposer auto-approve")
    consensus2.vote(proposal.proposal_id, VoteType.APPROVE, "Reasonable metric change")
    consensus3.vote(proposal.proposal_id, VoteType.APPROVE, "Looks good")

    print("\n[ralph-1] Voted: APPROVE")
    print("[ralph-2] Voted: APPROVE")
    print("[ralph-3] Voted: APPROVE")

    # Propagate votes
    consensus1.receive_vote(proposal.proposal_id, "ralph-2", "approve")
    consensus1.receive_vote(proposal.proposal_id, "ralph-3", "approve")

    # Check status
    status = consensus1.get_proposal_status(proposal.proposal_id)
    print(f"\nProposal Status: {status['status']}")
    print(f"Vote Counts: {status['vote_counts']}")

    if status['status'] == 'approved':
        print("\n✓ Consensus reached! Action can proceed.")


async def example_rejected_proposal():
    """Example: Rejected consensus proposal"""
    print("\n" + "=" * 60)
    print("Rejected Proposal Example")
    print("=" * 60)

    consensus1 = ConsensusEngine(ralph_id="ralph-1")
    consensus2 = ConsensusEngine(ralph_id="ralph-2")
    consensus3 = ConsensusEngine(ralph_id="ralph-3")

    # Create dangerous proposal
    proposal = consensus1.create_proposal(
        consensus_type=ConsensusType.GRACEFUL_SHUTDOWN,
        description="Shut down all BGP sessions",
        parameters={"protocol": "bgp", "scope": "all"},
        required_votes=3
    )

    print(f"\n[ralph-1] Created proposal: {proposal.description}")

    # Distribute to others
    consensus2.receive_proposal(proposal.to_dict())
    consensus3.receive_proposal(proposal.to_dict())

    # Votes
    consensus1.vote(proposal.proposal_id, VoteType.APPROVE, "Proposer")
    consensus2.vote(proposal.proposal_id, VoteType.REJECT, "Too dangerous without human approval")
    consensus3.vote(proposal.proposal_id, VoteType.REJECT, "Network disruption risk")

    # Propagate
    consensus1.receive_vote(proposal.proposal_id, "ralph-2", "reject")
    consensus1.receive_vote(proposal.proposal_id, "ralph-3", "reject")

    status = consensus1.get_proposal_status(proposal.proposal_id)
    print(f"\nProposal Status: {status['status']}")
    print(f"Vote Counts: {status['vote_counts']}")

    if status['status'] == 'rejected':
        print("\n✗ Proposal rejected. Action blocked.")


async def example_auto_vote():
    """Example: Automatic voting based on rules"""
    print("\n" + "=" * 60)
    print("Auto-Vote Example")
    print("=" * 60)

    consensus1 = ConsensusEngine(ralph_id="ralph-1")
    consensus2 = ConsensusEngine(ralph_id="ralph-2")

    # Enable auto-vote on ralph2
    consensus2.enable_auto_vote()
    print("[ralph-2] Auto-vote enabled")

    # Create proposal
    proposal = consensus1.create_proposal(
        consensus_type=ConsensusType.ANOMALY_RESPONSE,
        description="Increase metric on flapping interface",
        parameters={"interface": "eth0", "proposed_metric": 100},
        required_votes=2
    )

    print(f"\n[ralph-1] Created proposal: {proposal.description}")

    # Ralph2 receives and auto-votes
    received_proposal = consensus2.receive_proposal(proposal.to_dict())
    print(f"[ralph-2] Auto-voted on proposal")

    # Check ralph2's vote
    votes = received_proposal.votes
    if "ralph-2" in votes:
        print(f"[ralph-2] Vote: {votes['ralph-2'].value}")


async def example_consensus_statistics():
    """Example: Consensus engine statistics"""
    print("\n" + "=" * 60)
    print("Consensus Statistics")
    print("=" * 60)

    consensus = ConsensusEngine(ralph_id="ralph-1")

    # Create several proposals
    for i in range(5):
        consensus.create_proposal(
            consensus_type=ConsensusType.METRIC_ADJUSTMENT,
            description=f"Proposal {i+1}",
            parameters={"metric": 10 + i},
            required_votes=2
        )

    # Vote on some
    proposals = list(consensus.proposals.keys())
    consensus.vote(proposals[0], VoteType.APPROVE)
    consensus.vote(proposals[1], VoteType.APPROVE)

    # Get statistics
    stats = consensus.get_statistics()
    print(f"\nRalph ID: {stats['ralph_id']}")
    print(f"Active Proposals: {stats['active_proposals']}")
    print(f"Completed Proposals: {stats['completed_proposals']}")

    # Get active proposals
    active = consensus.get_active_proposals()
    print(f"\nActive proposal details:")
    for proposal in active[:3]:  # Show first 3
        print(f"  - {proposal['description']}")
        print(f"    Status: {proposal['status']}")
        print(f"    Votes: {proposal['vote_counts']}")


async def main():
    """Run all examples"""
    await example_gossip_protocol()
    await example_consensus()
    await example_rejected_proposal()
    await example_auto_vote()
    await example_consensus_statistics()

    print("\n" + "=" * 60)
    print("Multi-Agent Examples Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
