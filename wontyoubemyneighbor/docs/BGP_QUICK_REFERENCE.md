# BGP Quick Reference

## Command-Line Usage

### Simple eBGP
```bash
python3 wontyoubemyneighbor.py --router-id 192.0.2.1 \\
    --bgp-local-as 65001 --bgp-peer 192.0.2.2 --bgp-peer-as 65002
```

### Multiple Peers
```bash
python3 wontyoubemyneighbor.py --router-id 192.0.2.1 \\
    --bgp-local-as 65001 \\
    --bgp-peer 192.0.2.2 --bgp-peer-as 65002 \\
    --bgp-peer 192.0.2.3 --bgp-peer-as 65003 \\
    --bgp-peer 192.0.2.4 --bgp-peer-as 65001  # iBGP
```

### Route Reflector
```bash
python3 wontyoubemyneighbor.py --router-id 192.0.2.1 \\
    --bgp-local-as 65001 --bgp-route-reflector \\
    --bgp-cluster-id 192.0.2.1 \\
    --bgp-peer 192.0.2.2 --bgp-peer-as 65001 \\
    --bgp-rr-client 192.0.2.2 --bgp-passive 192.0.2.2 \\
    --bgp-peer 192.0.2.3 --bgp-peer-as 65001 \\
    --bgp-rr-client 192.0.2.3 --bgp-passive 192.0.2.3
```

## Python API

### Basic Speaker
```python
from bgp import BGPSpeaker
import asyncio

async def main():
    speaker = BGPSpeaker(local_as=65001, router_id="192.0.2.1")
    speaker.add_peer(peer_ip="192.0.2.2", peer_as=65002)
    await speaker.run()

asyncio.run(main())
```

### With Policy
```python
from bgp import BGPSpeaker, Policy, PolicyRule
from bgp.policy import PrefixMatch, SetLocalPrefAction, AcceptAction

policy = Policy(
    name="my-policy",
    rules=[
        PolicyRule(
            name="prefer-customer-routes",
            matches=[PrefixMatch(prefix="203.0.113.0/24")],
            actions=[SetLocalPrefAction(200), AcceptAction()]
        )
    ]
)

speaker = BGPSpeaker(local_as=65001, router_id="192.0.2.1")
speaker.add_peer(peer_ip="192.0.2.2", peer_as=65002, import_policy=policy)
await speaker.run()
```

## Configuration Reference

### Timers
- **Hold Time**: 180s (default) - Session timeout
- **Keepalive**: 60s (default) - Hold time / 3
- **ConnectRetry**: 120s (default) - Retry interval

### Well-Known Communities
- `NO_EXPORT` (0xFFFFFF01) - Do not advertise to eBGP
- `NO_ADVERTISE` (0xFFFFFF02) - Do not advertise to any peer
- `NO_EXPORT_SUBCONFED` (0xFFFFFF03) - Do not export outside sub-confederation

### Attribute Type Codes
- `1` - ORIGIN
- `2` - AS_PATH
- `3` - NEXT_HOP
- `4` - MULTI_EXIT_DISC (MED)
- `5` - LOCAL_PREF
- `6` - ATOMIC_AGGREGATE
- `7` - AGGREGATOR
- `8` - COMMUNITIES
- `9` - ORIGINATOR_ID
- `10` - CLUSTER_LIST
- `14` - MP_REACH_NLRI
- `15` - MP_UNREACH_NLRI

## FSM States

| State | Code | Description |
|-------|------|-------------|
| Idle | 0 | Initial state |
| Connect | 1 | TCP connecting |
| Active | 2 | TCP failed, will retry |
| OpenSent | 3 | OPEN sent |
| OpenConfirm | 4 | OPEN received |
| Established | 5 | Session up |

## Best Path Selection

1. Highest LOCAL_PREF (default: 100)
2. Shortest AS_PATH
3. Lowest ORIGIN (IGP=0 < EGP=1 < INCOMPLETE=2)
4. Lowest MED (if same neighbor AS)
5. eBGP over iBGP
6. Lowest IGP metric (not implemented)
7. Oldest route
8. Lowest router ID
9. Lowest peer IP

## Policy Actions

### Match Conditions
```python
PrefixMatch(prefix="203.0.113.0/24", exact=True)
PrefixMatch(prefix="203.0.113.0/24", ge=25, le=32)
ASPathMatch(regex="^65001")
ASPathMatch(length_le=5)
CommunityMatch(community="65001:100")
CommunityMatch(any_of=["65001:100", "65001:200"])
LocalPrefMatch(value=100)
LocalPrefMatch(ge=100, le=200)
MEDMatch(value=0)
NextHopMatch(next_hop="192.0.2.1")
OriginMatch(origin=0)  # IGP
```

### Actions
```python
AcceptAction()
RejectAction()
SetLocalPrefAction(value=200)
SetMEDAction(value=100)
SetNextHopAction(next_hop="192.0.2.1")
PrependASPathAction(asn=65001, count=3)
AddCommunityAction(community="65001:100")
RemoveCommunityAction(community="65001:*")  # Wildcards supported
SetCommunityAction(communities=["65001:100", "65001:200"])
```

## Error Codes

### Message Header Errors (1)
- 1.1: Connection Not Synchronized
- 1.2: Bad Message Length
- 1.3: Bad Message Type

### OPEN Message Errors (2)
- 2.1: Unsupported Version Number
- 2.2: Bad Peer AS
- 2.3: Bad BGP Identifier
- 2.6: Unacceptable Hold Time

### UPDATE Message Errors (3)
- 3.1: Malformed Attribute List
- 3.2: Unrecognized Well-known Attribute
- 3.3: Missing Well-known Attribute
- 3.6: Invalid ORIGIN Attribute
- 3.8: Invalid NEXT_HOP Attribute

### Cease (6)
- 6.2: Administrative Shutdown
- 6.3: Peer De-configured
- 6.4: Administrative Reset

## Statistics

```python
stats = speaker.get_statistics()
# {
#   'total_peers': 2,
#   'established_peers': 1,
#   'loc_rib_routes': 100,
#   'peers': {
#     '192.0.2.2': {
#       'fsm_state': 'ESTABLISHED',
#       'messages_sent': 50,
#       'messages_received': 45,
#       'routes_received': 100,
#       'routes_advertised': 50,
#       'updates_sent': 10,
#       'updates_received': 8
#     }
#   }
# }
```

## Troubleshooting

### Check Session State
```python
status = speaker.get_peer_status("192.0.2.2")
print(status['fsm_state'])  # Should be 'ESTABLISHED'
```

### Check Routes
```python
# All routes
routes = speaker.get_routes()

# Specific prefix
route = speaker.get_route("203.0.113.0/24")

# Routes from specific peer
peer_routes = speaker.get_peer_routes("192.0.2.2")
```

### Check Capabilities
```python
session = speaker.agent.sessions["192.0.2.2"]
caps = session.capabilities.get_statistics()
# {
#   'ipv4_unicast': True,
#   'ipv6_unicast': False,
#   'route_refresh': True,
#   'four_octet_as': True
# }
```

## Performance Tuning

### Reduce Decision Process Frequency
```python
speaker.agent.decision_process_interval = 10.0  # seconds
```

### Limit Routes per Peer (Future)
```python
# Not yet implemented
speaker.add_peer(
    peer_ip="192.0.2.2",
    peer_as=65002,
    max_prefixes=10000
)
```

## Common Patterns

### Accept Only Specific Prefixes
```python
policy = Policy(
    name="whitelist",
    rules=[
        PolicyRule(
            name="accept-whitelist",
            matches=[PrefixMatch(prefix="203.0.113.0/24", exact=True)],
            actions=[AcceptAction()]
        ),
        PolicyRule(
            name="reject-all",
            matches=[],
            actions=[RejectAction()]
        )
    ],
    default_accept=False
)
```

### AS Path Filtering
```python
policy = Policy(
    name="as-filter",
    rules=[
        PolicyRule(
            name="block-long-paths",
            matches=[ASPathMatch(length_ge=10)],
            actions=[RejectAction()]
        )
    ],
    default_accept=True
)
```

### Community-Based Actions
```python
policy = Policy(
    name="community-policy",
    rules=[
        PolicyRule(
            name="customer-routes",
            matches=[CommunityMatch(community="65001:100")],
            actions=[SetLocalPrefAction(200), AcceptAction()]
        ),
        PolicyRule(
            name="peer-routes",
            matches=[CommunityMatch(community="65001:200")],
            actions=[SetLocalPrefAction(150), AcceptAction()]
        )
    ],
    default_accept=True
)
```
