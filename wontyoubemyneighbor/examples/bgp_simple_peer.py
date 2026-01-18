#!/usr/bin/env python3
"""
Simple BGP Peer Example

Demonstrates how to create a basic BGP speaker with a single peer.

Usage:
    python3 bgp_simple_peer.py
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bgp import BGPSpeaker


async def main():
    """Run simple BGP speaker"""

    print("=" * 60)
    print("BGP Simple Peer Example")
    print("=" * 60)

    # Configuration
    LOCAL_AS = 65001
    LOCAL_ROUTER_ID = "192.0.2.1"
    PEER_IP = "192.0.2.2"
    PEER_AS = 65002

    print(f"\nConfiguration:")
    print(f"  Local AS:  {LOCAL_AS}")
    print(f"  Router ID: {LOCAL_ROUTER_ID}")
    print(f"  Peer IP:   {PEER_IP}")
    print(f"  Peer AS:   {PEER_AS}")
    print()

    # Create BGP speaker
    speaker = BGPSpeaker(
        local_as=LOCAL_AS,
        router_id=LOCAL_ROUTER_ID,
        log_level="INFO"
    )

    # Add peer
    speaker.add_peer(
        peer_ip=PEER_IP,
        peer_as=PEER_AS
    )

    print("BGP speaker created with 1 peer")
    print("Starting speaker...")
    print()

    # Start speaker
    await speaker.start()

    print("BGP speaker started!")
    print("Press Ctrl+C to stop")
    print()

    try:
        # Keep running and print statistics every 10 seconds
        while True:
            await asyncio.sleep(10)

            stats = speaker.get_statistics()
            print(f"\nStatistics:")
            print(f"  Total Peers:       {stats['total_peers']}")
            print(f"  Established Peers: {stats['established_peers']}")
            print(f"  Loc-RIB Routes:    {stats['loc_rib_routes']}")

            # Show peer status
            peer_status = speaker.get_peer_status(PEER_IP)
            if peer_status:
                print(f"\n  Peer {PEER_IP}:")
                print(f"    State:             {peer_status['fsm_state']}")
                print(f"    Messages Sent:     {peer_status['messages_sent']}")
                print(f"    Messages Received: {peer_status['messages_received']}")
                print(f"    Routes Received:   {peer_status['routes_received']}")

    except KeyboardInterrupt:
        print("\n\nShutting down...")
        await speaker.stop()
        print("BGP speaker stopped")


if __name__ == '__main__':
    asyncio.run(main())
