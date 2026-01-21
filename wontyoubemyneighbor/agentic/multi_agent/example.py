"""
Example usage of Multi-Agent Coordination

Demonstrates gossip protocol and consensus between RubberBand instances.
"""

import asyncio
from .gossip import GossipProtocol, MessageType
from .consensus import ConsensusEngine, ConsensusType, VoteType


async def example_gossip_protocol():
    """Example: Set up gossip network between RubberBand instances"""
    print("=" * 60)
    print("Gossip Protocol Example")
    print("=" * 60)

    # Create three RubberBand instances
    rubberband1 = GossipProtocol(rubberband_id="rubberband-1", fanout=2, gossip_interval=2.0)
    rubberband2 = GossipProtocol(rubberband_id="rubberband-2", fanout=2, gossip_interval=2.0)
    rubberband3 = GossipProtocol(rubberband_id="rubberband-3", fanout=2, gossip_interval=2.0)

    # Register peers
    rubberband1.register_peer("rubberband-2", "192.168.1.2")
    rubberband1.register_peer("rubberband-3", "192.168.1.3")

    rubberband2.register_peer("rubberband-1", "192.168.1.1")
    rubberband2.register_peer("rubberband-3", "192.168.1.3")

    rubberband3.register_peer("rubberband-1", "192.168.1.1")
    rubberband3.register_peer("rubberband-2", "192.168.1.2")

    # Register message handlers
    async def handle_state_update(message):
        print(f"[{rubberband2.rubberband_id}] Received state update from {message.sender_id}")

    rubberband2.register_handler(MessageType.STATE_UPDATE, handle_state_update)

    # Start gossip protocols
    await rubberband1.start()
    await rubberband2.start()
    await rubberband3.start()

    # RubberBand1 broadcasts state update
    message = rubberband1.create_message(
        MessageType.STATE_UPDATE,
        payload={
            "ospf_neighbors": 3,
            "bgp_peers": 2,
            "health_score": 95.5
        }
    )

    print(f"\n[rubberband-1] Broadcasting state update...")
    await rubberband1.broadcast(message)

    # Let gossip propagate
    await asyncio.sleep(1)

    # Check statistics
    print(f"\n[rubberband-1] Stats: {rubberband1.get_statistics()}")
    print(f"[rubberband-2] Stats: {rubberband2.get_statistics()}")
    print(f"[rubberband-3] Stats: {rubberband3.get_statistics()}")

    # Stop gossip
    await rubberband1.stop()
    await rubberband2.stop()
    await rubberband3.stop()


async def example_consensus():
    """Example: Distributed consensus voting"""
    print("\n" + "=" * 60)
    print("Consensus Engine Example")
    print("=" * 60)

    # Create gossip network
    gossip1 = GossipProtocol(rubberband_id="rubberband-1")
    gossip2 = GossipProtocol(rubberband_id="rubberband-2")
    gossip3 = GossipProtocol(rubberband_id="rubberband-3")

    # Create consensus engines
    consensus1 = ConsensusEngine(rubberband_id="rubberband-1", gossip_protocol=gossip1)
    consensus2 = ConsensusEngine(rubberband_id="rubberband-2", gossip_protocol=gossip2)
    consensus3 = ConsensusEngine(rubberband_id="rubberband-3", gossip_protocol=gossip3)

    # RubberBand1 creates proposal
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

    print(f"\n[rubberband-1] Created proposal: {proposal.proposal_id}")
    print(f"Description: {proposal.description}")

    # Other RubberBands receive proposal
    consensus2.receive_proposal(proposal.to_dict())
    consensus3.receive_proposal(proposal.to_dict())

    print("\n[rubberband-2] Received proposal")
    print("[rubberband-3] Received proposal")

    # Vote on proposal
    consensus1.vote(proposal.proposal_id, VoteType.APPROVE, "Proposer auto-approve")
    consensus2.vote(proposal.proposal_id, VoteType.APPROVE, "Reasonable metric change")
    consensus3.vote(proposal.proposal_id, VoteType.APPROVE, "Looks good")

    print("\n[rubberband-1] Voted: APPROVE")
    print("[rubberband-2] Voted: APPROVE")
    print("[rubberband-3] Voted: APPROVE")

    # Propagate votes
    consensus1.receive_vote(proposal.proposal_id, "rubberband-2", "approve")
    consensus1.receive_vote(proposal.proposal_id, "rubberband-3", "approve")

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

    consensus1 = ConsensusEngine(rubberband_id="rubberband-1")
    consensus2 = ConsensusEngine(rubberband_id="rubberband-2")
    consensus3 = ConsensusEngine(rubberband_id="rubberband-3")

    # Create dangerous proposal
    proposal = consensus1.create_proposal(
        consensus_type=ConsensusType.GRACEFUL_SHUTDOWN,
        description="Shut down all BGP sessions",
        parameters={"protocol": "bgp", "scope": "all"},
        required_votes=3
    )

    print(f"\n[rubberband-1] Created proposal: {proposal.description}")

    # Distribute to others
    consensus2.receive_proposal(proposal.to_dict())
    consensus3.receive_proposal(proposal.to_dict())

    # Votes
    consensus1.vote(proposal.proposal_id, VoteType.APPROVE, "Proposer")
    consensus2.vote(proposal.proposal_id, VoteType.REJECT, "Too dangerous without human approval")
    consensus3.vote(proposal.proposal_id, VoteType.REJECT, "Network disruption risk")

    # Propagate
    consensus1.receive_vote(proposal.proposal_id, "rubberband-2", "reject")
    consensus1.receive_vote(proposal.proposal_id, "rubberband-3", "reject")

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

    consensus1 = ConsensusEngine(rubberband_id="rubberband-1")
    consensus2 = ConsensusEngine(rubberband_id="rubberband-2")

    # Enable auto-vote on rubberband2
    consensus2.enable_auto_vote()
    print("[rubberband-2] Auto-vote enabled")

    # Create proposal
    proposal = consensus1.create_proposal(
        consensus_type=ConsensusType.ANOMALY_RESPONSE,
        description="Increase metric on flapping interface",
        parameters={"interface": "eth0", "proposed_metric": 100},
        required_votes=2
    )

    print(f"\n[rubberband-1] Created proposal: {proposal.description}")

    # RubberBand2 receives and auto-votes
    received_proposal = consensus2.receive_proposal(proposal.to_dict())
    print(f"[rubberband-2] Auto-voted on proposal")

    # Check rubberband2's vote
    votes = received_proposal.votes
    if "rubberband-2" in votes:
        print(f"[rubberband-2] Vote: {votes['rubberband-2'].value}")


async def example_consensus_statistics():
    """Example: Consensus engine statistics"""
    print("\n" + "=" * 60)
    print("Consensus Statistics")
    print("=" * 60)

    consensus = ConsensusEngine(rubberband_id="rubberband-1")

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
    print(f"\nRubberBand ID: {stats['rubberband_id']}")
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
