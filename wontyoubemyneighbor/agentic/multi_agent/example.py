"""
Example usage of Multi-Agent Coordination

Demonstrates gossip protocol and consensus between ASI instances.
"""

import asyncio
from .gossip import GossipProtocol, MessageType
from .consensus import ConsensusEngine, ConsensusType, VoteType


async def example_gossip_protocol():
    """Example: Set up gossip network between ASI instances"""
    print("=" * 60)
    print("Gossip Protocol Example")
    print("=" * 60)

    # Create three ASI instances
    asi1 = GossipProtocol(asi_id="asi-1", fanout=2, gossip_interval=2.0)
    asi2 = GossipProtocol(asi_id="asi-2", fanout=2, gossip_interval=2.0)
    asi3 = GossipProtocol(asi_id="asi-3", fanout=2, gossip_interval=2.0)

    # Register peers
    asi1.register_peer("asi-2", "192.168.1.2")
    asi1.register_peer("asi-3", "192.168.1.3")

    asi2.register_peer("asi-1", "192.168.1.1")
    asi2.register_peer("asi-3", "192.168.1.3")

    asi3.register_peer("asi-1", "192.168.1.1")
    asi3.register_peer("asi-2", "192.168.1.2")

    # Register message handlers
    async def handle_state_update(message):
        print(f"[{asi2.asi_id}] Received state update from {message.sender_id}")

    asi2.register_handler(MessageType.STATE_UPDATE, handle_state_update)

    # Start gossip protocols
    await asi1.start()
    await asi2.start()
    await asi3.start()

    # ASI1 broadcasts state update
    message = asi1.create_message(
        MessageType.STATE_UPDATE,
        payload={
            "ospf_neighbors": 3,
            "bgp_peers": 2,
            "health_score": 95.5
        }
    )

    print(f"\n[asi-1] Broadcasting state update...")
    await asi1.broadcast(message)

    # Let gossip propagate
    await asyncio.sleep(1)

    # Check statistics
    print(f"\n[asi-1] Stats: {asi1.get_statistics()}")
    print(f"[asi-2] Stats: {asi2.get_statistics()}")
    print(f"[asi-3] Stats: {asi3.get_statistics()}")

    # Stop gossip
    await asi1.stop()
    await asi2.stop()
    await asi3.stop()


async def example_consensus():
    """Example: Distributed consensus voting"""
    print("\n" + "=" * 60)
    print("Consensus Engine Example")
    print("=" * 60)

    # Create gossip network
    gossip1 = GossipProtocol(asi_id="asi-1")
    gossip2 = GossipProtocol(asi_id="asi-2")
    gossip3 = GossipProtocol(asi_id="asi-3")

    # Create consensus engines
    consensus1 = ConsensusEngine(asi_id="asi-1", gossip_protocol=gossip1)
    consensus2 = ConsensusEngine(asi_id="asi-2", gossip_protocol=gossip2)
    consensus3 = ConsensusEngine(asi_id="asi-3", gossip_protocol=gossip3)

    # ASI1 creates proposal
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

    print(f"\n[asi-1] Created proposal: {proposal.proposal_id}")
    print(f"Description: {proposal.description}")

    # Other ASIs receive proposal
    consensus2.receive_proposal(proposal.to_dict())
    consensus3.receive_proposal(proposal.to_dict())

    print("\n[asi-2] Received proposal")
    print("[asi-3] Received proposal")

    # Vote on proposal
    consensus1.vote(proposal.proposal_id, VoteType.APPROVE, "Proposer auto-approve")
    consensus2.vote(proposal.proposal_id, VoteType.APPROVE, "Reasonable metric change")
    consensus3.vote(proposal.proposal_id, VoteType.APPROVE, "Looks good")

    print("\n[asi-1] Voted: APPROVE")
    print("[asi-2] Voted: APPROVE")
    print("[asi-3] Voted: APPROVE")

    # Propagate votes
    consensus1.receive_vote(proposal.proposal_id, "asi-2", "approve")
    consensus1.receive_vote(proposal.proposal_id, "asi-3", "approve")

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

    consensus1 = ConsensusEngine(asi_id="asi-1")
    consensus2 = ConsensusEngine(asi_id="asi-2")
    consensus3 = ConsensusEngine(asi_id="asi-3")

    # Create dangerous proposal
    proposal = consensus1.create_proposal(
        consensus_type=ConsensusType.GRACEFUL_SHUTDOWN,
        description="Shut down all BGP sessions",
        parameters={"protocol": "bgp", "scope": "all"},
        required_votes=3
    )

    print(f"\n[asi-1] Created proposal: {proposal.description}")

    # Distribute to others
    consensus2.receive_proposal(proposal.to_dict())
    consensus3.receive_proposal(proposal.to_dict())

    # Votes
    consensus1.vote(proposal.proposal_id, VoteType.APPROVE, "Proposer")
    consensus2.vote(proposal.proposal_id, VoteType.REJECT, "Too dangerous without human approval")
    consensus3.vote(proposal.proposal_id, VoteType.REJECT, "Network disruption risk")

    # Propagate
    consensus1.receive_vote(proposal.proposal_id, "asi-2", "reject")
    consensus1.receive_vote(proposal.proposal_id, "asi-3", "reject")

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

    consensus1 = ConsensusEngine(asi_id="asi-1")
    consensus2 = ConsensusEngine(asi_id="asi-2")

    # Enable auto-vote on asi2
    consensus2.enable_auto_vote()
    print("[asi-2] Auto-vote enabled")

    # Create proposal
    proposal = consensus1.create_proposal(
        consensus_type=ConsensusType.ANOMALY_RESPONSE,
        description="Increase metric on flapping interface",
        parameters={"interface": "eth0", "proposed_metric": 100},
        required_votes=2
    )

    print(f"\n[asi-1] Created proposal: {proposal.description}")

    # ASI2 receives and auto-votes
    received_proposal = consensus2.receive_proposal(proposal.to_dict())
    print(f"[asi-2] Auto-voted on proposal")

    # Check asi2's vote
    votes = received_proposal.votes
    if "asi-2" in votes:
        print(f"[asi-2] Vote: {votes['asi-2'].value}")


async def example_consensus_statistics():
    """Example: Consensus engine statistics"""
    print("\n" + "=" * 60)
    print("Consensus Statistics")
    print("=" * 60)

    consensus = ConsensusEngine(asi_id="asi-1")

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
    print(f"\nASI ID: {stats['asi_id']}")
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
