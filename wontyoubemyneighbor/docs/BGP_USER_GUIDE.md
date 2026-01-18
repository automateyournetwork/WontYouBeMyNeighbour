# BGP User Guide

## Overview

This BGP implementation provides a production-grade BGP-4 speaker supporting:

- **eBGP and iBGP** sessions with multiple peers
- **Route reflection** (RFC 4456) to reduce iBGP mesh requirements
- **BGP communities** (RFC 1997) for route tagging and policy
- **IPv4 and IPv6** address families (RFC 4760)
- **Policy engine** for import/export filtering and attribute manipulation
- **Capabilities negotiation** (RFC 5492) including 4-byte AS, route refresh, multiprotocol
- **Best path selection** per RFC 4271 Section 9.1

## Quick Start

### Simple eBGP Peer

```bash
python3 wontyoubemyneighbor.py \\
    --router-id 192.0.2.1 \\
    --bgp-local-as 65001 \\
    --bgp-peer 192.0.2.2 \\
    --bgp-peer-as 65002
```

### iBGP with Route Reflection

```bash
# Route reflector
python3 wontyoubemyneighbor.py \\
    --router-id 192.0.2.1 \\
    --bgp-local-as 65001 \\
    --bgp-route-reflector \\
    --bgp-peer 192.0.2.2 --bgp-peer-as 65001 --bgp-rr-client 192.0.2.2 \\
    --bgp-peer 192.0.2.3 --bgp-peer-as 65001 --bgp-rr-client 192.0.2.3
```

## Architecture

### Components

```
BGPSpeaker (High-level API)
    │
    ├── BGPAgent (Orchestrator)
    │   ├── Multiple BGPSession objects (one per peer)
    │   ├── Shared Loc-RIB (best routes)
    │   ├── BestPathSelector (RFC 4271 decision process)
    │   ├── PolicyEngine (import/export policies)
    │   └── RouteReflector (optional, RFC 4456)
    │
    ├── BGPSession (Per-peer management)
    │   ├── BGPFSM (6-state finite state machine)
    │   ├── TCP transport (asyncio-based)
    │   ├── Adj-RIB-In (received routes)
    │   ├── Adj-RIB-Out (advertised routes)
    │   └── CapabilityManager (RFC 5492)
    │
    └── Supporting modules
        ├── Messages (OPEN, UPDATE, KEEPALIVE, NOTIFICATION, ROUTE-REFRESH)
        ├── Attributes (ORIGIN, AS_PATH, NEXT_HOP, MED, LOCAL_PREF, etc.)
        ├── Communities (standard and well-known)
        └── Address families (IPv4/IPv6 support)
```

### Three RIBs

1. **Adj-RIB-In**: Routes received from each peer (before policy)
2. **Loc-RIB**: Best routes after best path selection
3. **Adj-RIB-Out**: Routes advertised to each peer (after policy)

### BGP FSM States

1. **Idle**: Initial state, waiting to start
2. **Connect**: Attempting TCP connection
3. **Active**: TCP connection failed, will retry
4. **OpenSent**: TCP connected, OPEN message sent
5. **OpenConfirm**: OPEN received, waiting for KEEPALIVE
6. **Established**: Session established, exchanging routes

## Usage Examples

### Example 1: Simple eBGP Peer

```python
from bgp import BGPSpeaker
import asyncio

async def main():
    speaker = BGPSpeaker(local_as=65001, router_id="192.0.2.1")

    # Add eBGP peer
    speaker.add_peer(peer_ip="192.0.2.2", peer_as=65002)

    # Start speaker
    await speaker.run()

asyncio.run(main())
```

### Example 2: Route Reflector

```python
from bgp import BGPSpeaker

async def main():
    speaker = BGPSpeaker(local_as=65001, router_id="192.0.2.1")

    # Enable route reflection
    speaker.enable_route_reflection(cluster_id="192.0.2.1")

    # Add route reflector clients (iBGP)
    speaker.add_peer(
        peer_ip="192.0.2.2",
        peer_as=65001,  # Same AS = iBGP
        route_reflector_client=True,
        passive=True  # Wait for them to connect
    )

    speaker.add_peer(
        peer_ip="192.0.2.3",
        peer_as=65001,
        route_reflector_client=True,
        passive=True
    )

    await speaker.run()

asyncio.run(main())
```

### Example 3: Policy-Based Filtering

```python
from bgp import BGPSpeaker, Policy, PolicyRule
from bgp.policy import PrefixMatch, SetLocalPrefAction, AcceptAction, RejectAction

async def main():
    speaker = BGPSpeaker(local_as=65001, router_id="192.0.2.1")

    # Define import policy
    import_policy = Policy(
        name="import-filter",
        rules=[
            PolicyRule(
                name="prefer-specific-prefix",
                matches=[PrefixMatch(prefix="203.0.113.0/24", exact=True)],
                actions=[
                    SetLocalPrefAction(value=200),
                    AcceptAction()
                ]
            ),
            PolicyRule(
                name="reject-default",
                matches=[],
                actions=[RejectAction()]
            )
        ],
        default_accept=False
    )

    # Add peer with policy
    speaker.add_peer(
        peer_ip="192.0.2.2",
        peer_as=65002,
        import_policy=import_policy
    )

    await speaker.run()

asyncio.run(main())
```

## Configuration

### Command-Line Arguments

| Argument | Description | Default | Required |
|----------|-------------|---------|----------|
| `--router-id` | Router ID (IPv4 format) | - | Yes |
| `--bgp-local-as` | Local AS number | - | Yes (for BGP) |
| `--bgp-peer` | Peer IP address (can be repeated) | - | Yes (for BGP) |
| `--bgp-peer-as` | Peer AS number (can be repeated) | local-as | No |
| `--bgp-route-reflector` | Enable route reflection | False | No |
| `--bgp-rr-client` | Mark peer as RR client (can be repeated) | - | No |
| `--bgp-passive` | Passive peer IP (can be repeated) | - | No |
| `--bgp-hold-time` | Hold time (seconds) | 180 | No |
| `--bgp-connect-retry` | Connect retry time (seconds) | 120 | No |
| `--bgp-listen-ip` | Listen IP address | 0.0.0.0 | No |
| `--bgp-listen-port` | Listen TCP port | 179 | No |
| `--log-level` | Logging level | INFO | No |

**Note**: The unified agent supports both OSPF and BGP. Use `--interface` for OSPF or `--bgp-local-as` for BGP (or both for running both protocols).

### Environment Variables

- `BGP_ROUTER_ID`: Default router ID
- `BGP_LOCAL_AS`: Default local AS
- `BGP_LOG_LEVEL`: Default log level

## Policy Engine

### Match Conditions

- **PrefixMatch**: Match route prefix (with exact, ge, le)
- **ASPathMatch**: Match AS_PATH (regex, length)
- **CommunityMatch**: Match BGP communities
- **NextHopMatch**: Match NEXT_HOP attribute
- **LocalPrefMatch**: Match LOCAL_PREF value
- **MEDMatch**: Match MED value
- **OriginMatch**: Match ORIGIN attribute

### Actions

- **AcceptAction**: Accept route
- **RejectAction**: Reject route
- **SetLocalPrefAction**: Set LOCAL_PREF
- **SetMEDAction**: Set MED
- **SetNextHopAction**: Set NEXT_HOP
- **PrependASPathAction**: Prepend AS to AS_PATH
- **AddCommunityAction**: Add community
- **RemoveCommunityAction**: Remove community
- **SetCommunityAction**: Set communities (replace)

### Policy Evaluation

1. Rules are evaluated in order
2. First matching rule applies its actions
3. If no rules match, default action applies
4. Rejected routes are not installed in Loc-RIB

## Best Path Selection

BGP decision process (RFC 4271 Section 9.1.2):

1. **Highest LOCAL_PREF** (well-known discretionary)
2. **Shortest AS_PATH** (well-known mandatory)
3. **Lowest ORIGIN** (IGP < EGP < INCOMPLETE)
4. **Lowest MED** (if from same neighbor AS)
5. **eBGP > iBGP** (prefer external routes)
6. **Lowest IGP metric to NEXT_HOP** (not implemented)
7. **Oldest route** (route stability)
8. **Lowest Router ID** (deterministic tiebreaker)
9. **Lowest peer IP** (final tiebreaker)

## Route Reflection

### Rules (RFC 4456 Section 8)

- **Route from client** → Reflect to all other clients + all non-clients
- **Route from non-client** → Reflect to clients only
- **Route from eBGP** → Reflect to all iBGP peers (clients + non-clients)

### Loop Prevention (RFC 4456 Section 9)

- **ORIGINATOR_ID**: Router ID of route originator, reject if matches self
- **CLUSTER_LIST**: List of cluster IDs, reject if own cluster_id present

### Configuration

```python
speaker.enable_route_reflection(cluster_id="192.0.2.1")

speaker.add_peer(
    peer_ip="192.0.2.2",
    peer_as=65001,  # Must be iBGP (same AS)
    route_reflector_client=True
)
```

## Troubleshooting

### Session Not Establishing

1. Check FSM state: `speaker.get_peer_status(peer_ip)`
2. Verify TCP connectivity (port 179)
3. Check router IDs don't match
4. Verify AS numbers are correct
5. Check for firewall rules

### No Routes Received

1. Verify session is established
2. Check import policy (may be rejecting routes)
3. Check peer is advertising routes
4. Verify address family support (IPv4/IPv6)

### Routes Not Being Advertised

1. Check export policy
2. Verify routes are in Loc-RIB
3. Check iBGP split horizon (routes from iBGP not sent to other iBGP without RR)
4. Verify best path selection chose this route

### High CPU Usage

1. Reduce decision process interval (default: 5s)
2. Limit number of peers
3. Use route filtering to reduce Adj-RIB-In size

## Performance Considerations

- **Asyncio-based**: Single-threaded event loop, efficient for I/O
- **Decision process**: Runs every 5 seconds by default
- **Memory**: ~1KB per route, ~10KB per session
- **CPU**: Minimal when stable, spikes during route changes
- **Scalability**: Tested with 10 peers, 1000 routes each

## Security

- **TCP MD5 authentication**: Not yet implemented (RFC 2385)
- **TTL security**: Not yet implemented (RFC 5082)
- **Max prefix limit**: Not yet implemented
- **Input validation**: All messages validated before processing
- **Error handling**: NOTIFICATION sent for invalid messages

## Monitoring

### Statistics

```python
stats = speaker.get_statistics()
# Returns:
# {
#     'local_as': 65001,
#     'router_id': '192.0.2.1',
#     'total_peers': 2,
#     'established_peers': 1,
#     'loc_rib_routes': 100,
#     'peers': {
#         '192.0.2.2': {
#             'fsm_state': 'ESTABLISHED',
#             'messages_sent': 50,
#             'messages_received': 45,
#             'routes_received': 100,
#             ...
#         }
#     }
# }
```

### Logging

- **DEBUG**: All messages, state changes, route processing
- **INFO**: Session establishment, major events
- **WARNING**: Errors, NOTIFICATION messages
- **ERROR**: Fatal errors

## Future Enhancements

- TCP MD5 authentication (RFC 2385)
- Graceful restart (RFC 4724)
- ADD-PATH capability (RFC 7911)
- BGP monitoring protocol (BMP, RFC 7854)
- Route flap damping (RFC 2439)
- Confederations (RFC 5065)
- AS path prepending policies
- Route refresh on demand
