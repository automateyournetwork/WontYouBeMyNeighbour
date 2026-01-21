"""
Example usage of LLM Interface

Demonstrates how to use the multi-provider LLM interface with network context.
"""

import asyncio
from .interface import LLMInterface, LLMProvider


async def example_usage():
    """Example: Query LLM with network state context"""

    # Initialize LLM interface with preferred provider
    llm = LLMInterface(
        max_turns=75,
        preferred_provider=LLMProvider.CLAUDE,
        # API keys from environment or passed directly
        # openai_key="sk-...",
        # claude_key="sk-ant-...",
        # gemini_key="...",
    )

    # Initialize providers
    await llm.initialize_providers()

    # Update network context (would come from actual OSPF/BGP state)
    llm.update_network_context({
        "ospf": {
            "router_id": "1.1.1.1",
            "neighbors": [
                {"neighbor_id": "2.2.2.2", "state": "Full", "interface": "eth0"}
            ],
            "lsa_count": 15
        },
        "bgp": {
            "local_as": 65001,
            "peers": [
                {"peer": "192.168.1.2", "as": 65002, "state": "Established"}
            ],
            "route_count": 42
        },
        "routes": [
            {"network": "10.0.0.0/24", "next_hop": "192.168.1.2", "protocol": "bgp"},
            {"network": "172.16.0.0/16", "next_hop": "fe80::1", "protocol": "ospf"}
        ]
    })

    # Example queries
    queries = [
        "What is the current state of my OSPF neighbors?",
        "How many BGP routes do I have?",
        "Is there any routing issue I should be aware of?",
        "Explain the path for traffic to 10.0.0.0/24"
    ]

    for query in queries:
        print(f"\n{'=' * 60}")
        print(f"Query: {query}")
        print(f"{'=' * 60}")

        response = await llm.query(query)
        if response:
            print(f"\nRubberBand: {response}")
        else:
            print("\nNo response received.")

    # Save conversation history
    llm.save_conversation("/tmp/rubberband_conversation.json")
    print(f"\n\nConversation saved. Turns used: {llm.current_turn}/{llm.max_turns}")


if __name__ == "__main__":
    asyncio.run(example_usage())
