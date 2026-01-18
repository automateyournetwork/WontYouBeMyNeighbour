# BGP Implementation Architecture

## Design Principles

1. **Modular Design**: Separate concerns (messages, FSM, RIB, path selection, policy)
2. **Async I/O**: Use asyncio for non-blocking TCP and timers
3. **RFC Compliance**: Cite RFC sections in code, follow standards strictly
4. **Type Safety**: Type hints on all functions
5. **Testability**: Unit tests for each component
6. **OSPF Coexistence**: Share interface with OSPF agent, run both protocols simultaneously

## Component Architecture

```
wontyoubemyneighbor/
├── bgp/
│   ├── __init__.py              # Package exports
│   ├── constants.py             # Protocol constants from RFCs
│   ├── messages.py              # Message encode/decode
│   ├── attributes.py            # Path attribute classes
│   ├── fsm.py                   # BGP Finite State Machine
│   ├── session.py               # TCP session management
│   ├── rib.py                   # RIB data structures
│   ├── path_selection.py        # Best path algorithm
│   ├── communities.py           # Community utilities
│   ├── route_reflection.py      # Route reflector logic
│   ├── policy.py                # Import/export policy engine
│   ├── address_family.py        # IPv4/IPv6 support
│   ├── capabilities.py          # Capability negotiation
│   └── graceful_restart.py      # Graceful restart (RFC 4486)
└── wontyoubemyneighbor.py       # Unified OSPF+BGP agent
```

## Module Responsibilities

### constants.py
- BGP version, port (179), header size (19), max message size (4096)
- Message types: OPEN=1, UPDATE=2, NOTIFICATION=3, KEEPALIVE=4, ROUTE_REFRESH=5
- FSM states: Idle=0, Connect=1, Active=2, OpenSent=3, OpenConfirm=4, Established=5
- Path attribute type codes
- Attribute flags
- Well-known communities
- AFI/SAFI values
- Capability codes
- Error codes and subcodes

### messages.py
**Classes:**
- `BGPMessage`: Base class with header parsing
- `BGPOpen`: OPEN message (version, AS, hold time, BGP ID, capabilities)
- `BGPUpdate`: UPDATE message (withdrawn routes, path attributes, NLRI)
- `BGPKeepalive`: KEEPALIVE message (header only)
- `BGPNotification`: NOTIFICATION message (error code, subcode, data)
- `BGPRouteRefresh`: ROUTE-REFRESH message (AFI/SAFI)

**Methods:**
- `encode() → bytes`: Serialize to wire format
- `decode(data: bytes) → BGPMessage`: Parse from wire format
- `validate() → bool`: Validate message fields

### attributes.py
**Base Class:**
- `PathAttribute`: Abstract base with flags, type, value

**Implementations:**
- `OriginAttribute` (Type 1): IGP/EGP/INCOMPLETE
- `ASPathAttribute` (Type 2): AS_SEQUENCE/AS_SET, prepend(), length()
- `NextHopAttribute` (Type 3): IPv4 next hop
- `MEDAttribute` (Type 4): 32-bit metric
- `LocalPrefAttribute` (Type 5): 32-bit preference (iBGP only)
- `AtomicAggregateAttribute` (Type 6): Flag
- `AggregatorAttribute` (Type 7): AS + Router ID
- `CommunitiesAttribute` (Type 8): List of 32-bit values
- `OriginatorIDAttribute` (Type 9): Route reflector originator
- `ClusterListAttribute` (Type 10): Route reflector cluster IDs
- `MPReachNLRIAttribute` (Type 14): IPv6 reachability
- `MPUnreachNLRIAttribute` (Type 15): IPv6 withdrawals
- `ExtendedCommunitiesAttribute` (Type 16): Extended communities

**Factory:**
- `AttributeFactory.decode(data) → PathAttribute`

### fsm.py
**Enums:**
- `BGPState`: Idle, Connect, Active, OpenSent, OpenConfirm, Established
- `BGPEvent`: ManualStart, ManualStop, TcpConnectionConfirmed, BGPOpen, KeepAliveMsg, UpdateMsg, HoldTimer_Expires, etc.

**Class: BGPFSM**
- `state: BGPState`
- `timers: Dict[str, asyncio.Task]`
- `hold_time: int`
- `keepalive_time: int`
- `connect_retry_time: int`

**Methods:**
- `process_event(event: BGPEvent) → None`: Main FSM dispatcher
- `_start_connect_retry_timer() → None`
- `_start_hold_timer() → None`
- `_start_keepalive_timer() → None`
- `_stop_all_timers() → None`
- Callbacks: `on_state_change`, `on_established`, `on_send_open`, `on_send_keepalive`

### rib.py
**Class: BGPRoute**
```python
@dataclass
class BGPRoute:
    prefix: str                          # "203.0.113.0/24"
    prefix_len: int
    path_attributes: Dict[int, PathAttribute]
    peer_id: str                         # Peer router ID
    peer_ip: str
    timestamp: float
    best: bool = False                   # Best path selected
    stale: bool = False                  # Stale route (graceful restart)
    afi: int = 1                         # 1=IPv4, 2=IPv6
    safi: int = 1                        # 1=Unicast
```

**Class: AdjRIBIn**
- `routes: Dict[str, List[BGPRoute]]`  # Key: prefix, Value: routes from peers
- `add_route(route: BGPRoute) → None`
- `remove_route(prefix: str, peer_id: str) → None`
- `get_routes(prefix: str) → List[BGPRoute]`
- `get_all_routes() → List[BGPRoute]`

**Class: LocRIB**
- `routes: Dict[str, BGPRoute]`  # Key: prefix, Value: best route
- `install_route(route: BGPRoute) → None`
- `remove_route(prefix: str) → None`
- `lookup(prefix: str) → Optional[BGPRoute]`
- `get_all_routes() → List[BGPRoute]`

**Class: AdjRIBOut**
- `routes: Dict[str, Dict[str, BGPRoute]]`  # Key: peer_id, Value: {prefix: route}
- `add_route(peer_id: str, route: BGPRoute) → None`
- `remove_route(peer_id: str, prefix: str) → None`
- `get_routes_for_peer(peer_id: str) → List[BGPRoute]`

### path_selection.py
**Class: BestPathSelector**
```python
def select_best(routes: List[BGPRoute]) → Optional[BGPRoute]:
    """
    RFC 4271 Section 9.1.2 Decision Process
    1. Highest LOCAL_PREF
    2. Shortest AS_PATH
    3. Lowest ORIGIN (IGP < EGP < INCOMPLETE)
    4. Lowest MED (same neighbor AS only)
    5. eBGP > iBGP
    6. Lowest IGP cost to NEXT_HOP
    7. Oldest route
    8. Lowest Router ID
    9. Lowest peer IP
    """

def compare(route_a: BGPRoute, route_b: BGPRoute) → int:
    """Returns -1 if a is better, 1 if b is better, 0 if equal"""
```

### communities.py
**Functions:**
```python
def parse_community(s: str) → int:
    """Parse "65001:100" → 0xFDE90064"""

def format_community(val: int) → str:
    """Format 0xFDE90064 → "65001:100\""""

def is_well_known(val: int) → bool:
    """Check if community is NO_EXPORT, NO_ADVERTISE, etc."""

def matches_regex(community: int, pattern: str) → bool:
    """Match community against pattern like "65001:*\""""
```

### route_reflection.py
**Class: RouteReflector**
```python
class RouteReflector:
    cluster_id: str                    # Cluster ID (router ID or configured)
    clients: Set[str]                  # Client peer IDs
    non_clients: Set[str]              # Non-client iBGP peer IDs

    def should_reflect(route: BGPRoute, from_peer: str, to_peer: str) → bool:
        """Determine if route should be reflected to to_peer"""

    def prepare_for_reflection(route: BGPRoute) → BGPRoute:
        """Add ORIGINATOR_ID, prepend CLUSTER_LIST"""

    def check_loop(route: BGPRoute) → bool:
        """Check ORIGINATOR_ID and CLUSTER_LIST for loops"""
```

### policy.py
**Match Conditions:**
- `PrefixMatch`: exact, prefix-list, range
- `ASPathMatch`: regex, length
- `CommunityMatch`: exact, any, regex
- `NextHopMatch`: IP or range
- `LocalPrefMatch`, `MEDMatch`, `OriginMatch`: value comparisons

**Actions:**
- `AcceptAction`, `RejectAction`
- `SetLocalPref(value)`, `SetMED(value)`, `SetNextHop(ip)`
- `PrependASPath(asn, count)`
- `AddCommunity(community)`, `RemoveCommunity(community)`, `SetCommunity(communities)`

**Policy Structure:**
```python
@dataclass
class PolicyRule:
    match: List[MatchCondition]
    actions: List[Action]

class Policy:
    rules: List[PolicyRule]
    default_action: Action  # Accept or Reject

    def apply(route: BGPRoute) → Optional[BGPRoute]:
        """Apply policy, return modified route or None if rejected"""
```

**PolicyEngine:**
```python
class PolicyEngine:
    import_policies: Dict[str, Policy]   # Key: peer_id
    export_policies: Dict[str, Policy]   # Key: peer_id

    def apply_import_policy(route: BGPRoute, peer_id: str) → Optional[BGPRoute]:
        """Apply import policy for peer"""

    def apply_export_policy(route: BGPRoute, peer_id: str) → Optional[BGPRoute]:
        """Apply export policy for peer"""
```

### session.py
**Class: BGPSession**
```python
class BGPSession:
    peer_ip: str
    peer_as: int
    peer_id: Optional[str]             # Learned from OPEN
    local_as: int
    local_id: str
    hold_time: int
    capabilities: List[Capability]

    fsm: BGPFSM
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter

    async def connect() → bool:
        """Initiate TCP connection to peer"""

    async def accept(reader, writer) → None:
        """Accept incoming TCP connection"""

    async def send_message(msg: BGPMessage) → None:
        """Send BGP message"""

    async def receive_message() → Optional[BGPMessage]:
        """Receive and parse BGP message"""

    async def run() → None:
        """Main session loop"""
```

**Class: BGPSessionManager**
```python
class BGPSessionManager:
    sessions: Dict[str, BGPSession]     # Key: peer_id
    listen_port: int = 179

    async def start() → None:
        """Start listening for connections"""

    async def add_peer(peer_ip: str, peer_as: int) → BGPSession:
        """Add configured peer"""

    def get_session(peer_id: str) → Optional[BGPSession]:
        """Get session by peer ID"""
```

### capabilities.py
**Class: Capability**
```python
@dataclass
class Capability:
    code: int
    value: bytes

    @staticmethod
    def encode_multiprotocol(afi: int, safi: int) → Capability:
        """Encode multiprotocol capability"""

    @staticmethod
    def encode_route_refresh() → Capability:
        """Encode route refresh capability"""

    @staticmethod
    def encode_4byte_as(asn: int) → Capability:
        """Encode 4-byte AS capability"""

    @staticmethod
    def decode(data: bytes) → Capability:
        """Decode capability TLV"""
```

### address_family.py
**Class: AddressFamily**
```python
class AddressFamily:
    AFI_IPV4 = 1
    AFI_IPV6 = 2
    SAFI_UNICAST = 1
    SAFI_MULTICAST = 2

    @staticmethod
    def encode_prefix(prefix: str, afi: int) → bytes:
        """Encode IPv4/IPv6 prefix for NLRI"""

    @staticmethod
    def decode_prefix(data: bytes, afi: int) → Tuple[str, int]:
        """Decode NLRI prefix, return (prefix, bytes_consumed)"""

    @staticmethod
    def encode_next_hop(ip: str, afi: int) → bytes:
        """Encode next hop (4 bytes for IPv4, 16 or 32 for IPv6)"""

    @staticmethod
    def decode_next_hop(data: bytes, afi: int) → str:
        """Decode next hop"""
```

## BGPAgent Main Class

```python
class BGPAgent:
    """Main BGP Agent orchestrating all components"""

    router_id: str
    local_as: int

    session_mgr: BGPSessionManager
    adj_rib_in: AdjRIBIn
    loc_rib: LocRIB
    adj_rib_out: AdjRIBOut
    best_path_selector: BestPathSelector
    route_reflector: Optional[RouteReflector]
    policy_engine: PolicyEngine

    async def start() → None:
        """Start BGP agent"""

    async def stop() → None:
        """Stop BGP agent"""

    async def add_peer(peer_ip: str, peer_as: int, **kwargs) → None:
        """Add BGP peer"""

    async def advertise_prefix(prefix: str, next_hop: str, **attrs) → None:
        """Advertise a prefix to peers"""

    async def withdraw_prefix(prefix: str) → None:
        """Withdraw a prefix from peers"""

    def _process_update(update: BGPUpdate, peer_id: str) → None:
        """Process UPDATE message from peer"""

    def _run_decision_process() → None:
        """Run best path selection for all prefixes"""

    def _advertise_to_peers() → None:
        """Advertise Loc-RIB routes to peers"""
```

## Integration with OSPF Agent

### Unified CLI
```python
# wontyoubemyneighbor.py
def main():
    parser.add_argument("--protocol", choices=["ospf", "bgp", "ospf,bgp"])
    parser.add_argument("--local-as", type=int, help="BGP AS number")
    parser.add_argument("--peer", action="append", help="BGP peer IP")
    parser.add_argument("--peer-as", action="append", type=int, help="BGP peer AS")
    parser.add_argument("--advertise", action="append", help="BGP prefix to advertise")

    # Start OSPF and/or BGP
    if "ospf" in protocols:
        ospf_agent = OSPFAgent(...)
        tasks.append(ospf_agent.start())

    if "bgp" in protocols:
        bgp_agent = BGPAgent(...)
        tasks.append(bgp_agent.start())

    await asyncio.gather(*tasks)
```

### Example Usage
```bash
# BGP only
python wontyoubemyneighbor.py \
  --protocol bgp \
  --router-id 192.0.2.99 \
  --local-as 65001 \
  --peer 192.0.2.1 --peer-as 65000 \
  --advertise 203.0.113.0/24

# OSPF + BGP
sudo python wontyoubemyneighbor.py \
  --protocol ospf,bgp \
  --router-id 10.255.255.99 \
  --interface eth0 \
  --local-as 65001 \
  --peer 192.0.2.1 --peer-as 65000
```

## Data Flow

### Receiving Routes (Import)
```
Peer → BGPSession.receive_message()
    → BGPUpdate message
    → PolicyEngine.apply_import_policy()
    → AdjRIBIn.add_route()
    → BestPathSelector.select_best()
    → LocRIB.install_route()
    → (if best changed) AdjRIBOut update + advertise to peers
```

### Advertising Routes (Export)
```
LocRIB route
    → For each peer:
        → RouteReflector.should_reflect() (if RR)
        → PolicyEngine.apply_export_policy()
        → AdjRIBOut.add_route()
        → Build BGPUpdate message
        → BGPSession.send_message()
```

### Best Path Selection Trigger Events
- New route received from peer
- Route withdrawn from peer
- Peer session goes down (remove all routes from that peer)
- Policy change
- Manual trigger (route refresh)

## Concurrency Model

- **asyncio** for all I/O and timers
- Each BGPSession runs in its own coroutine
- FSM timers use `asyncio.create_task()`
- RIB operations are synchronous (no locking needed in single-threaded asyncio)
- Decision process runs after RIB updates (not in separate thread)

## Testing Strategy

### Unit Tests
- `test_messages.py`: Encode/decode for all message types
- `test_attributes.py`: Encode/decode for all path attributes
- `test_fsm.py`: State transitions, timer handling
- `test_rib.py`: RIB operations
- `test_best_path.py`: Decision process tiebreakers
- `test_communities.py`: Community parsing and matching
- `test_route_reflection.py`: RR logic, loop prevention
- `test_policy.py`: Policy matching and actions

### Integration Tests
- Full session establishment (Idle → Established)
- Route advertisement and reception
- Best path selection with multiple routes
- Route reflection scenarios
- Policy application
- IPv6 routes
- Graceful restart

### Interoperability Tests
- Test against real BGP speakers (BIRD, FRRouting, Cisco, Juniper)
- eBGP peering
- iBGP peering
- Route reflection
- Community propagation

## Performance Considerations

- **Incremental updates**: Only recalculate best path for affected prefixes
- **Efficient lookups**: Use dict for O(1) prefix lookup in RIBs
- **Minimal copying**: Pass routes by reference where possible
- **Batching**: Send multiple NLRI in single UPDATE message
- **Timer efficiency**: Use single timer per session, not per route

## Security Considerations

- **MD5 authentication**: Not implemented initially (deprecated by RFC)
- **TCP AO**: Future enhancement
- **GTSM (RFC 5082)**: Generalized TTL Security Mechanism
- **Max prefix limits**: Protect against route explosion
- **AS_PATH loop detection**: Reject routes with our AS in AS_PATH (eBGP)
- **Route flap damping**: Future enhancement

## Future Enhancements

- BGP FlowSpec (RFC 5575)
- BGP Monitoring Protocol (BMP, RFC 7854)
- BGP-LS (Link State, RFC 7752)
- RPKI validation (RFC 6811)
- Confederations (RFC 5065)
- Route dampening
- BGP Large Communities (RFC 8092)
