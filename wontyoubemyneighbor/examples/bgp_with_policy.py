#!/usr/bin/env python3
"""
BGP with Policy Example

Demonstrates import/export policy for route filtering and modification.

Example policies:
- Import: Accept only 203.0.113.0/24, set LOCAL_PREF to 200
- Export: Prepend AS path 3 times for all routes

Usage:
    python3 bgp_with_policy.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bgp import (
    BGPSpeaker,
    Policy, PolicyRule,
    PrefixMatch, AcceptAction, RejectAction,
    SetLocalPrefAction, PrependASPathAction
)


async def main():
    """Run BGP speaker with policies"""

    print("=" * 60)
    print("BGP with Policy Example")
    print("=" * 60)

    # Configuration
    LOCAL_AS = 65001
    LOCAL_ROUTER_ID = "192.0.2.1"
    PEER_IP = "192.0.2.2"
    PEER_AS = 65002

    print(f"\nConfiguration:")
    print(f"  Local AS:  {LOCAL_AS}")
    print(f"  Router ID: {LOCAL_ROUTER_ID}")
    print(f"  Peer:      {PEER_IP} (AS {PEER_AS})")
    print()

    # Create BGP speaker
    speaker = BGPSpeaker(
        local_as=LOCAL_AS,
        router_id=LOCAL_ROUTER_ID,
        log_level="INFO"
    )

    # Define import policy
    print("Creating import policy:")
    print("  - Accept only 203.0.113.0/24")
    print("  - Set LOCAL_PREF to 200")
    print()

    import_policy = Policy(
        name="import-policy-1",
        rules=[
            PolicyRule(
                name="accept-specific-prefix",
                matches=[
                    PrefixMatch(prefix="203.0.113.0/24", exact=True)
                ],
                actions=[
                    SetLocalPrefAction(value=200),
                    AcceptAction()
                ]
            ),
            PolicyRule(
                name="reject-all-others",
                matches=[],  # Matches all
                actions=[
                    RejectAction()
                ]
            )
        ],
        default_accept=False  # Reject by default
    )

    # Define export policy
    print("Creating export policy:")
    print("  - Prepend AS path 3 times for all routes")
    print()

    export_policy = Policy(
        name="export-policy-1",
        rules=[
            PolicyRule(
                name="prepend-as-path",
                matches=[],  # Matches all
                actions=[
                    PrependASPathAction(asn=LOCAL_AS, count=3),
                    AcceptAction()
                ]
            )
        ],
        default_accept=True
    )

    # Add peer with policies
    speaker.add_peer(
        peer_ip=PEER_IP,
        peer_as=PEER_AS,
        import_policy=import_policy,
        export_policy=export_policy
    )

    print(f"Peer added: {PEER_IP}")
    print("  - Import policy: accept 203.0.113.0/24, set LOCAL_PREF=200")
    print("  - Export policy: prepend AS path 3 times")
    print()

    # Start speaker
    print("Starting BGP speaker...")
    await speaker.start()

    print("BGP speaker started!")
    print("Press Ctrl+C to stop")
    print()

    try:
        # Monitor routes
        while True:
            await asyncio.sleep(10)

            stats = speaker.get_statistics()
            print(f"\nStatistics:")
            print(f"  Established Peers: {stats['established_peers']}")
            print(f"  Loc-RIB Routes:    {stats['loc_rib_routes']}")

            # Show received routes
            routes = speaker.get_routes()
            if routes:
                print(f"\n  Received Routes (after import policy):")
                for route in routes[:5]:  # Show first 5
                    local_pref = "N/A"
                    if route.has_attribute(5):  # ATTR_LOCAL_PREF
                        attr = route.get_attribute(5)
                        local_pref = attr.local_pref

                    print(f"    {route.prefix} - LOCAL_PREF: {local_pref} - "
                          f"from {route.peer_id}")

            # Show peer routes (before policy)
            peer_routes = speaker.get_peer_routes(PEER_IP)
            if peer_routes:
                accepted = len(routes)
                received = len(peer_routes)
                rejected = received - accepted
                print(f"\n  Policy Results:")
                print(f"    Received:  {received} routes")
                print(f"    Accepted:  {accepted} routes")
                print(f"    Rejected:  {rejected} routes")

    except KeyboardInterrupt:
        print("\n\nShutting down...")
        await speaker.stop()
        print("BGP speaker stopped")


if __name__ == '__main__':
    asyncio.run(main())
