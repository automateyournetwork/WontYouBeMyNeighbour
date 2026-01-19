"""
Example usage of Network State Manager and Analytics

Demonstrates state tracking, snapshot management, and analytics.
"""

import asyncio
from datetime import datetime
from .state_manager import NetworkStateManager
from .analytics import NetworkAnalytics


async def example_state_tracking():
    """Example: Track network state over time"""
    print("=" * 60)
    print("Network State Tracking")
    print("=" * 60)

    state_mgr = NetworkStateManager(snapshot_retention=50)

    # Simulate network state updates
    print("\nSimulating network state updates...")

    for i in range(5):
        # Simulate state
        state_mgr._current_ospf_state = {
            "router_id": "1.1.1.1",
            "area_id": "0.0.0.0",
            "interface_name": "eth0",
            "neighbors": [
                {
                    "neighbor_id": "2.2.2.2",
                    "state": "Full",
                    "address": "192.168.1.2",
                    "priority": 1,
                    "dr": "0.0.0.0",
                    "bdr": "0.0.0.0",
                    "state_changes": i  # Simulate increasing instability
                },
                {
                    "neighbor_id": "3.3.3.3",
                    "state": "Full" if i % 2 == 0 else "ExStart",  # Flapping
                    "address": "192.168.1.3",
                    "priority": 1,
                    "dr": "0.0.0.0",
                    "bdr": "0.0.0.0",
                    "state_changes": i * 2
                }
            ],
            "neighbor_count": 2,
            "full_neighbors": 2 if i % 2 == 0 else 1,
            "lsdb": {"total_lsas": 10 + i, "router_lsas": 5, "network_lsas": 3}
        }

        state_mgr._current_bgp_state = {
            "local_as": 65001,
            "router_id": "1.1.1.1",
            "peers": [
                {
                    "peer": "192.168.1.2",
                    "peer_as": 65002,
                    "state": "Established",
                    "is_ibgp": False,
                    "uptime": i * 60
                }
            ],
            "peer_count": 1,
            "established_peers": 1,
            "rib_stats": {"total_routes": 100 + i * 10, "ipv4_routes": 100 + i * 10}
        }

        state_mgr._current_routing_table = [
            {"network": "10.0.0.0/24", "next_hop": "192.168.1.2", "protocol": "bgp"},
            {"network": "172.16.0.0/16", "next_hop": "192.168.1.3", "protocol": "ospf"}
        ]

        # Create snapshot
        snapshot = state_mgr.create_snapshot()
        print(f"Snapshot {i+1}: {snapshot.timestamp.strftime('%H:%M:%S')}")

        await asyncio.sleep(0.1)

    print(f"\nCreated {len(state_mgr.snapshots)} snapshots")


async def example_state_summary():
    """Example: Get state summary"""
    print("\n" + "=" * 60)
    print("State Summary")
    print("=" * 60)

    state_mgr = NetworkStateManager()

    # Set some state
    state_mgr._current_ospf_state = {
        "router_id": "1.1.1.1",
        "neighbor_count": 3,
        "full_neighbors": 3,
        "lsdb": {"total_lsas": 25}
    }

    state_mgr._current_bgp_state = {
        "local_as": 65001,
        "peer_count": 2,
        "established_peers": 2,
        "rib_stats": {"total_routes": 150}
    }

    print(state_mgr.get_state_summary())


async def example_llm_context():
    """Example: Get LLM context"""
    print("\n" + "=" * 60)
    print("LLM Context Generation")
    print("=" * 60)

    state_mgr = NetworkStateManager()

    state_mgr._current_ospf_state = {
        "router_id": "1.1.1.1",
        "neighbors": [{"neighbor_id": "2.2.2.2", "state": "Full"}]
    }

    context = state_mgr.get_llm_context()
    print("\nContext for LLM injection:")
    import json
    print(json.dumps(context, indent=2))


async def example_analytics():
    """Example: Network analytics"""
    print("\n" + "=" * 60)
    print("Network Analytics")
    print("=" * 60)

    state_mgr = NetworkStateManager(snapshot_retention=100)

    # Create snapshots with changing state
    for i in range(20):
        state_mgr._current_ospf_state = {
            "router_id": "1.1.1.1",
            "neighbors": [
                {
                    "neighbor_id": "2.2.2.2",
                    "state": "Full" if i % 3 != 0 else "ExStart",  # Flapping
                    "state_changes": i
                },
                {
                    "neighbor_id": "3.3.3.3",
                    "state": "Full",
                    "state_changes": 1
                }
            ]
        }

        state_mgr._current_bgp_state = {
            "local_as": 65001,
            "peers": [
                {
                    "peer": "192.168.1.2",
                    "state": "Established"
                }
            ]
        }

        state_mgr._current_routing_table = [
            {"network": f"10.{i}.0.0/24", "next_hop": "192.168.1.2"}
            for j in range(100 + i)  # Route count increasing
        ]

        state_mgr.create_snapshot()
        await asyncio.sleep(0.01)

    # Run analytics
    analytics = NetworkAnalytics(state_mgr)

    print("\n--- OSPF Neighbor Stability ---")
    ospf_analysis = analytics.analyze_neighbor_stability(protocol="ospf")
    print(f"Total neighbors: {ospf_analysis['total_neighbors']}")
    print(f"Stable: {ospf_analysis['stable_neighbors']}")
    print(f"Flapping: {len(ospf_analysis['flapping_neighbors'])}")
    print(f"Stability score: {ospf_analysis['stability_score']*100:.1f}%")

    print("\n--- Route Churn Analysis ---")
    churn = analytics.analyze_route_churn()
    print(f"Current routes: {churn['current_routes']}")
    print(f"Avg churn: {churn['avg_churn_per_snapshot']:.1f}")
    print(f"Stability: {churn['stability']}")

    print("\n--- Health Trend ---")
    health = analytics.analyze_health_trend()
    print(f"Current health: {health['current_health']:.1f}/100")
    print(f"Trend: {health['trend']}")
    print(f"Predicted next: {health['predicted_next']:.1f}/100")


async def example_change_detection():
    """Example: Detect state changes"""
    print("\n" + "=" * 60)
    print("State Change Detection")
    print("=" * 60)

    state_mgr = NetworkStateManager()

    # First snapshot
    state_mgr._current_ospf_state = {
        "neighbors": [
            {"neighbor_id": "2.2.2.2", "state": "Full"},
            {"neighbor_id": "3.3.3.3", "state": "Full"}
        ]
    }
    state_mgr._current_bgp_state = {"peers": []}
    state_mgr._current_routing_table = [{"network": "10.0.0.0/24"}] * 100

    state_mgr.create_snapshot()

    # Second snapshot with changes
    state_mgr._current_ospf_state = {
        "neighbors": [
            {"neighbor_id": "2.2.2.2", "state": "Full"},
            # 3.3.3.3 lost
            {"neighbor_id": "4.4.4.4", "state": "Full"}  # New neighbor
        ]
    }
    state_mgr._current_routing_table = [{"network": "10.0.0.0/24"}] * 125  # 25 more routes

    state_mgr.create_snapshot()

    # Detect changes
    changes = state_mgr.detect_state_changes()
    print("\nDetected changes:")
    for change in changes:
        print(f"  - {change}")


async def example_analytics_report():
    """Example: Generate full analytics report"""
    print("\n" + "=" * 60)
    print("Full Analytics Report")
    print("=" * 60)

    state_mgr = NetworkStateManager(snapshot_retention=100)

    # Create snapshots
    for i in range(30):
        state_mgr._current_ospf_state = {
            "router_id": "1.1.1.1",
            "neighbors": [
                {"neighbor_id": "2.2.2.2", "state": "Full", "state_changes": 1},
                {"neighbor_id": "3.3.3.3", "state": "Full", "state_changes": 1}
            ]
        }
        state_mgr._current_bgp_state = {
            "local_as": 65001,
            "peers": [
                {"peer": "192.168.1.2", "state": "Established"}
            ]
        }
        state_mgr._current_routing_table = [{"network": "10.0.0.0/24"}] * 100
        state_mgr.create_snapshot()

    analytics = NetworkAnalytics(state_mgr)
    report = analytics.generate_report()
    print("\n" + report)


async def main():
    """Run all examples"""
    await example_state_tracking()
    await example_state_summary()
    await example_llm_context()
    await example_analytics()
    await example_change_detection()
    await example_analytics_report()

    print("\n" + "=" * 60)
    print("Examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
