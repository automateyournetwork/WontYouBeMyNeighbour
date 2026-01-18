#!/usr/bin/env python3
"""
BGP Route Reflector Example

Demonstrates route reflection with clients and non-clients.

Topology:
    RR (This router, AS 65001, 192.0.2.1)
     ├── Client 1 (192.0.2.2, AS 65001)
     ├── Client 2 (192.0.2.3, AS 65001)
     └── Non-client (192.0.2.4, AS 65001)

Usage:
    python3 bgp_route_reflector.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bgp import BGPSpeaker


async def main():
    """Run BGP route reflector"""

    print("=" * 60)
    print("BGP Route Reflector Example")
    print("=" * 60)

    # Configuration
    LOCAL_AS = 65001
    LOCAL_ROUTER_ID = "192.0.2.1"
    CLUSTER_ID = "192.0.2.1"

    print(f"\nConfiguration:")
    print(f"  Local AS:   {LOCAL_AS}")
    print(f"  Router ID:  {LOCAL_ROUTER_ID}")
    print(f"  Cluster ID: {CLUSTER_ID}")
    print()

    # Create BGP speaker
    speaker = BGPSpeaker(
        local_as=LOCAL_AS,
        router_id=LOCAL_ROUTER_ID,
        log_level="INFO"
    )

    # Enable route reflection
    speaker.enable_route_reflection(cluster_id=CLUSTER_ID)
    print("Route reflection enabled")

    # Add route reflector clients
    print("\nAdding route reflector clients:")

    speaker.add_peer(
        peer_ip="192.0.2.2",
        peer_as=LOCAL_AS,  # iBGP
        route_reflector_client=True,
        passive=True  # Wait for them to connect
    )
    print("  - Client 1: 192.0.2.2")

    speaker.add_peer(
        peer_ip="192.0.2.3",
        peer_as=LOCAL_AS,  # iBGP
        route_reflector_client=True,
        passive=True
    )
    print("  - Client 2: 192.0.2.3")

    # Add non-client iBGP peer
    speaker.add_peer(
        peer_ip="192.0.2.4",
        peer_as=LOCAL_AS,  # iBGP
        route_reflector_client=False,  # Not a client
        passive=True
    )
    print("  - Non-client: 192.0.2.4")

    print(f"\nTotal peers: {len(speaker.get_all_peers())}")
    print()

    # Start speaker
    print("Starting BGP speaker...")
    await speaker.start()

    print("BGP route reflector started!")
    print("Listening for connections on port 179")
    print("Press Ctrl+C to stop")
    print()

    try:
        # Monitor status
        while True:
            await asyncio.sleep(15)

            stats = speaker.get_statistics()
            print(f"\n{'='*60}")
            print(f"Route Reflector Statistics:")
            print(f"  Total Peers:       {stats['total_peers']}")
            print(f"  Established Peers: {stats['established_peers']}")
            print(f"  Loc-RIB Routes:    {stats['loc_rib_routes']}")

            # Show route reflector stats
            if 'route_reflector' in stats:
                rr_stats = stats['route_reflector']
                print(f"\n  Route Reflector:")
                print(f"    Cluster ID:  {rr_stats['cluster_id']}")
                print(f"    Clients:     {rr_stats['clients']}")
                print(f"    Non-clients: {rr_stats['non_clients']}")

            # Show per-peer status
            print(f"\n  Peer Status:")
            for peer_ip in speaker.get_all_peers():
                peer_stats = speaker.get_peer_status(peer_ip)
                if peer_stats:
                    role = "Client" if peer_ip in ["192.0.2.2", "192.0.2.3"] else "Non-client"
                    print(f"    {peer_ip} ({role}): {peer_stats['fsm_state']} - "
                          f"{peer_stats['routes_received']} routes")

    except KeyboardInterrupt:
        print("\n\nShutting down...")
        await speaker.stop()
        print("BGP route reflector stopped")


if __name__ == '__main__':
    asyncio.run(main())
