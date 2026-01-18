# BGP Agent Test Plan

## Overview

Comprehensive testing plan for wontyoubemyneighbor BGP implementation using FRRouting (FRR) as test peers.

**Test Environment:**
- Agent: wontyoubemyneighbor BGP implementation
- Peers: FRRouting (FRR) BGP routers
- Network: Private lab network with sample prefixes

---

## Phase 1: iBGP Basic Peering with FRR

### Objective
Establish basic iBGP session between agent and FRR router, exchange stub routes.

### Topology
```
┌─────────────┐         iBGP (AS 65001)        ┌─────────────┐
│   FRR-1     │◄───────────────────────────────►│    Agent    │
│ 10.0.1.1    │      TCP 179, passive           │  10.0.1.2   │
│             │                                  │             │
│ Advertises: │                                  │ Advertises: │
│ 10.1.1.1/32 │                                  │ 10.2.2.2/32 │
│ 10.1.2.0/24 │                                  │             │
└─────────────┘                                  └─────────────┘
```

### FRR-1 Configuration

```bash
# File: /etc/frr/frr.conf

# Enable BGP daemon
bgpd=yes

# BGP Configuration
router bgp 65001
  bgp router-id 10.0.1.1

  # iBGP neighbor (Agent)
  neighbor 10.0.1.2 remote-as 65001
  neighbor 10.0.1.2 description "wontyoubemyneighbor-agent"
  neighbor 10.0.1.2 update-source 10.0.1.1

  # Advertise stub /32 route
  network 10.1.1.1/32

  # Optional: advertise test subnet
  network 10.1.2.0/24

  # Keep session up
  neighbor 10.0.1.2 timers 10 30
  neighbor 10.0.1.2 timers connect 10

# Static route for /32 (stub, points to null)
ip route 10.1.1.1/32 blackhole

exit
```

### Agent Configuration

```bash
# Start agent in iBGP mode (BGP only)
python3 wontyoubemyneighbor.py \
    --router-id 10.0.1.2 \
    --bgp-local-as 65001 \
    --bgp-peer 10.0.1.1 \
    --bgp-peer-as 65001 \
    --log-level DEBUG
```

### Manual Route Advertisement (Agent)

Since the agent doesn't have static route injection yet, we'll need to add this capability for testing:

**Option A**: Create test script `tests/manual/inject_routes.py`:
```python
#!/usr/bin/env python3
"""Inject test routes into BGP agent"""
import sys
sys.path.insert(0, '.')

from bgp import BGPRoute
from bgp.attributes import OriginAttribute, ASPathAttribute, NextHopAttribute
from bgp.constants import ORIGIN_IGP, AS_SEQUENCE

# Create test route
route = BGPRoute(
    prefix="10.2.2.2/32",
    prefix_len=32,
    path_attributes={
        1: OriginAttribute(ORIGIN_IGP),
        2: ASPathAttribute([(AS_SEQUENCE, [])]),  # Empty AS_PATH for iBGP
        3: NextHopAttribute("10.0.1.2")
    },
    peer_id="local",
    peer_ip="10.0.1.2"
)

# Insert into agent's Loc-RIB
# (This requires modifying agent to accept local routes)
```

**Option B**: For Phase 1, just verify route **reception** from FRR:
```bash
# Agent receives routes from FRR
# Verify with logs or statistics
```

### Validation Steps

1. **Session Establishment**
   ```bash
   # On FRR
   sudo vtysh -c "show bgp summary"
   # Should show: 10.0.1.2, State: Established

   # On Agent (check logs)
   # Should see: "BGP session ESTABLISHED with 10.0.1.1"
   ```

2. **Route Reception (Agent)**
   ```python
   # In Python or via agent stats
   routes = speaker.get_routes()
   assert any(r.prefix == "10.1.1.1/32" for r in routes)
   assert any(r.prefix == "10.1.2.0/24" for r in routes)
   ```

3. **Route Reception (FRR)**
   ```bash
   sudo vtysh -c "show bgp ipv4 unicast"
   # Should show routes from Agent (if agent advertises any)
   ```

4. **Capabilities Negotiation**
   ```bash
   # On FRR
   sudo vtysh -c "show bgp neighbor 10.0.1.2"
   # Check: Multiprotocol, Route Refresh, 4-byte AS
   ```

### Expected Results

- ✅ TCP connection established (port 179)
- ✅ OPEN messages exchanged
- ✅ FSM reaches ESTABLISHED state
- ✅ KEEPALIVE messages sent every 10 seconds
- ✅ Agent receives 10.1.1.1/32 and 10.1.2.0/24 from FRR
- ✅ Capabilities negotiated (multiprotocol, route refresh)
- ✅ No NOTIFICATION errors

### Troubleshooting

**Issue**: Session stuck in Active/Connect
- Check: Firewall rules (allow TCP 179)
- Check: IP connectivity (ping 10.0.1.1)
- Check: FRR is listening: `netstat -tlnp | grep 179`

**Issue**: Session drops after OPEN
- Check: AS numbers match (65001)
- Check: Router IDs are unique
- Check: Hold time acceptable (>= 3 seconds)

---

## Phase 2: eBGP Scenarios

### Phase 2A: eBGP with Private AS (Local Testing)

#### Topology
```
┌─────────────┐         eBGP                    ┌─────────────┐
│   FRR-2     │◄───────────────────────────────►│    Agent    │
│ 10.0.2.1    │      AS 65002 ←→ AS 65001       │  10.0.2.2   │
│  AS 65002   │                                  │  AS 65001   │
│             │                                  │             │
│ Advertises: │                                  │ Receives &  │
│ 192.168.1.0/24                                 │ Processes   │
│ 192.168.2.0/24                                 │             │
└─────────────┘                                  └─────────────┘
```

#### FRR-2 Configuration

```bash
router bgp 65002
  bgp router-id 10.0.2.1

  # eBGP neighbor (Agent)
  neighbor 10.0.2.2 remote-as 65001
  neighbor 10.0.2.2 description "wontyoubemyneighbor-agent-ebgp"
  neighbor 10.0.2.2 ebgp-multihop 1

  # Advertise test networks
  network 192.168.1.0/24
  network 192.168.2.0/24

  # Optional: Prepend AS path for testing
  route-map PREPEND permit 10
    set as-path prepend 65002 65002

  neighbor 10.0.2.2 route-map PREPEND out

exit
```

#### Agent Configuration

```bash
python3 wontyoubemyneighbor.py \
    --router-id 10.0.2.2 \
    --bgp-local-as 65001 \
    --bgp-peer 10.0.2.1 \
    --bgp-peer-as 65002 \
    --log-level INFO
```

#### Validation

1. **AS_PATH should have 65002**
   ```python
   routes = speaker.get_routes()
   route = next(r for r in routes if r.prefix == "192.168.1.0/24")
   as_path = route.get_attribute(2)  # AS_PATH
   assert 65002 in as_path.segments[0][1]
   ```

2. **Best path selection (eBGP preferred over iBGP)**
   - If same prefix advertised from both iBGP (Phase 1) and eBGP (Phase 2)
   - Agent should prefer eBGP route (step 5 of best path)

### Phase 2B: Simulated Internet Participation

#### Option 1: Route Server Peering (Recommended)

Use a public route server for testing (NO actual internet traffic, just BGP):

```bash
# Peer with Route Views Route Server (READ-ONLY)
# Route Server: route-views.routeviews.org AS 6447

python3 wontyoubemyneighbor.py \
    --router-id 10.0.2.2 \
    --bgp-local-as 65001 \
    --bgp-peer 128.223.51.103 \
    --bgp-peer-as 6447 \
    --bgp-passive 128.223.51.103 \
    --log-level INFO
```

**Benefits:**
- Receive real internet routing table (~900k routes)
- Test scalability of Adj-RIB-In
- Test best path selection with diverse AS paths
- **Safe**: Route server only sends routes, doesn't accept your routes

**Limitations:**
- May not accept connections from all IPs
- One-way: You receive routes but can't advertise

#### Option 2: BGP Looking Glass Testing

Connect to public looking glass servers that accept peering:
- Hurricane Electric Looking Glass
- PCH Route Collectors

#### Option 3: Virtual ISP Simulation (Best for full testing)

Set up 3 FRR routers simulating ISP topology:

```
        ISP-1 (AS 65100)
           / \
          /   \
         /     \
    ISP-2       ISP-3
  (AS 65200)  (AS 65300)
        \       /
         \     /
          \   /
          Agent
       (AS 65001)
```

Each ISP advertises different prefixes:
- ISP-1: 203.0.113.0/24, 198.51.100.0/24
- ISP-2: 192.0.2.0/24
- ISP-3: 198.18.0.0/15

This tests:
- Multi-AS path comparison
- MED comparison from different ASes
- AS_PATH length tiebreaker
- Best path selection under realistic conditions

#### Validation for Phase 2B

1. **Route Table Size**
   ```python
   stats = speaker.get_statistics()
   print(f"Received {stats['loc_rib_routes']} routes")
   # With route server: expect 100k-900k routes
   # With ISP simulation: expect 5-10 routes
   ```

2. **Decision Process Performance**
   ```python
   # Monitor decision process time in logs
   # Should complete in < 1 second for 10k routes
   ```

3. **Memory Usage**
   ```bash
   # Monitor Python process
   ps aux | grep wontyoubemyneighbor
   # With 100k routes: expect 200-500 MB
   ```

---

## Phase 3: OSPF-BGP Redistribution Bridge

### Objective
Use agent as redistribution point between OSPF and BGP domains.

### Topology
```
┌─────────────┐      OSPF Area 0       ┌─────────────┐      iBGP        ┌─────────────┐
│   FRR-3     │◄──────────────────────►│    Agent    │◄────────────────►│   FRR-4     │
│ 10.0.3.1    │    (wontyoubemyneighbor│  10.0.3.2   │                  │  10.0.4.1   │
│             │     OSPF module)        │  10.0.4.2   │                  │             │
│ OSPF Routes:│                         │             │     BGP Routes:  │             │
│ 172.16.0.0/24                         │ Bridge:     │     192.168.0.0/24             │
│ 172.16.1.0/24                         │ OSPF↔BGP    │     192.168.1.0/24             │
└─────────────┘                         └─────────────┘                  └─────────────┘

Goal: Ping 172.16.0.1 → 192.168.0.1 (OSPF network → BGP network)
```

### Agent Requirements

**New Feature Needed**: Route redistribution module

```python
# wontyoubemyneighbor/redistribution.py
class RouteRedistributor:
    """Redistribute routes between OSPF and BGP"""

    def __init__(self, ospf_agent, bgp_speaker):
        self.ospf = ospf_agent
        self.bgp = bgp_speaker

    def ospf_to_bgp(self, ospf_routes):
        """Import OSPF routes into BGP"""
        for route in ospf_routes:
            bgp_route = self._convert_ospf_to_bgp(route)
            self.bgp.agent.loc_rib.install_route(bgp_route)

    def bgp_to_ospf(self, bgp_routes):
        """Import BGP routes into OSPF"""
        for route in bgp_routes:
            ospf_lsa = self._convert_bgp_to_ospf(route)
            self.ospf.lsdb.install_lsa(ospf_lsa)
```

### FRR-3 Configuration (OSPF side)

```bash
# OSPF configuration
router ospf
  ospf router-id 10.0.3.1
  network 10.0.3.0/24 area 0
  network 172.16.0.0/24 area 0
  network 172.16.1.0/24 area 0

# Interfaces
interface eth0
  ip address 10.0.3.1/24
  ip ospf area 0
```

### FRR-4 Configuration (BGP side)

```bash
router bgp 65001
  bgp router-id 10.0.4.1

  neighbor 10.0.4.2 remote-as 65001
  neighbor 10.0.4.2 description "agent-bgp-side"

  network 192.168.0.0/24
  network 192.168.1.0/24
```

### Agent Configuration (Bridge Mode)

```bash
# Run both OSPF and BGP in the same process with the unified agent
python3 wontyoubemyneighbor.py \
    --router-id 10.0.3.2 \
    --area 0.0.0.0 \
    --interface eth0 \
    --source-ip 10.0.3.2 \
    --bgp-local-as 65001 \
    --bgp-peer 10.0.4.1 \
    --bgp-peer-as 65001

# Note: Redistribution between OSPF and BGP requires implementing
# the redistribution module (wontyoubemyneighbor/redistribution.py)
# to automatically exchange routes between the two protocols.
```

### Validation

1. **OSPF Routes in BGP**
   ```bash
   # On FRR-4 (BGP side)
   sudo vtysh -c "show bgp ipv4 unicast"
   # Should see: 172.16.0.0/24, 172.16.1.0/24 (from Agent)
   ```

2. **BGP Routes in OSPF**
   ```bash
   # On FRR-3 (OSPF side)
   sudo vtysh -c "show ip route"
   # Should see: 192.168.0.0/24, 192.168.1.0/24 (O E2 - OSPF External Type 2)
   ```

3. **End-to-End Connectivity**
   ```bash
   # From FRR-3
   ping 192.168.0.1
   # Should succeed (OSPF → Agent → BGP)

   # From FRR-4
   ping 172.16.0.1
   # Should succeed (BGP → Agent → OSPF)
   ```

4. **Trace Route**
   ```bash
   # From FRR-3
   traceroute 192.168.0.1
   # Should show: FRR-3 → Agent(10.0.3.2) → Agent(10.0.4.2) → FRR-4
   ```

### Expected Results

- ✅ OSPF routes appear in BGP Loc-RIB
- ✅ BGP routes appear in OSPF LSDB as Type-5 LSAs
- ✅ Routes have correct metrics (OSPF cost vs BGP MED)
- ✅ Next-hop rewritten to agent's IP
- ✅ End-to-end ping succeeds

---

## Phase 4: Advanced Testing

### Test 4.1: Route Reflection Topology

**Objective**: Test route reflector with multiple clients

```
     ┌──────────┐
     │  Agent   │ (Route Reflector, AS 65001)
     │ 10.0.5.1 │
     └────┬─────┘
          │ iBGP
    ┌─────┼─────┬─────┐
    │     │     │     │
┌───▼─┐ ┌─▼──┐ ┌▼───┐ ┌▼────┐
│FRR-5│ │FRR-6│ │FRR-7│ │FRR-8│
│Client│ │Client│ │Client│ │Non-│
│     │ │     │ │     │ │Client│
└─────┘ └─────┘ └─────┘ └─────┘
```

**Test**: Route from FRR-5 should be reflected to FRR-6, FRR-7, FRR-8

**Validation**:
```bash
# On FRR-6
show bgp ipv4 unicast 10.5.5.5/32
# Should have ORIGINATOR_ID = FRR-5
# Should have CLUSTER_LIST = [Agent]
```

### Test 4.2: Policy-Based Filtering

**Objective**: Test import/export policies

**Scenario**: Accept only specific prefixes from peer

```python
# Policy: Only accept 203.0.113.0/24
from bgp.policy import Policy, PolicyRule, PrefixMatch, AcceptAction, RejectAction

policy = Policy(
    name="strict-filter",
    rules=[
        PolicyRule(
            name="accept-203.0.113.0",
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

speaker.set_import_policy("10.0.2.1", policy)
```

**Validation**:
- FRR advertises 203.0.113.0/24 and 198.51.100.0/24
- Agent should only install 203.0.113.0/24 in Loc-RIB
- Verify: `len(speaker.get_routes()) == 1`

### Test 4.3: Community-Based Actions

**Objective**: Test community matching and LOCAL_PREF setting

**FRR Configuration**:
```bash
router bgp 65002
  neighbor 10.0.2.2 remote-as 65001
  neighbor 10.0.2.2 send-community

  route-map ADD-COMMUNITY permit 10
    set community 65002:100

  neighbor 10.0.2.2 route-map ADD-COMMUNITY out
```

**Agent Policy**:
```python
from bgp.policy import CommunityMatch, SetLocalPrefAction

policy = Policy(
    name="community-pref",
    rules=[
        PolicyRule(
            name="high-pref-for-65002:100",
            matches=[CommunityMatch(community="65002:100")],
            actions=[SetLocalPrefAction(200), AcceptAction()]
        )
    ]
)
```

**Validation**:
- Route should have LOCAL_PREF = 200
- Check: `route.get_attribute(5).local_pref == 200`

### Test 4.4: AS_PATH Prepending

**Objective**: Verify AS_PATH manipulation

**FRR Configuration**:
```bash
route-map PREPEND permit 10
  set as-path prepend 65002 65002 65002

neighbor 10.0.2.2 route-map PREPEND out
```

**Validation**:
- AS_PATH should be: [65002, 65002, 65002]
- Agent should count AS_PATH length correctly in best path selection

### Test 4.5: Graceful Session Teardown

**Objective**: Test NOTIFICATION handling

**Test**:
```bash
# On FRR, shutdown neighbor
sudo vtysh
conf t
router bgp 65002
no neighbor 10.0.2.2
```

**Expected**:
- Agent receives NOTIFICATION (Cease)
- FSM transitions: Established → Idle
- Adj-RIB-In cleared
- Routes withdrawn from Loc-RIB

### Test 4.6: Keepalive Timeout

**Objective**: Test hold timer expiration

**Test**:
```bash
# Block traffic between FRR and Agent
sudo iptables -A INPUT -s 10.0.2.1 -j DROP
sudo iptables -A OUTPUT -d 10.0.2.1 -j DROP

# Wait for hold timer (default 180s)
```

**Expected**:
- After 180 seconds, agent detects hold timer expiration
- FSM transitions to Idle
- Routes withdrawn

### Test 4.7: Rapid Route Updates (Convergence)

**Objective**: Test decision process under load

**Test**:
```bash
# On FRR, flap routes rapidly
for i in {1..100}; do
  vtysh -c "conf t" -c "router bgp 65002" -c "no network 192.168.$i.0/24"
  sleep 0.1
  vtysh -c "conf t" -c "router bgp 65002" -c "network 192.168.$i.0/24"
  sleep 0.1
done
```

**Validation**:
- Agent should handle all updates
- No NOTIFICATION errors
- Final Loc-RIB should have all 100 routes
- Check decision process time in logs

### Test 4.8: IPv6 Routing

**Objective**: Test multiprotocol IPv6 support

**FRR Configuration**:
```bash
router bgp 65002
  address-family ipv6 unicast
    neighbor 2001:db8::2 remote-as 65001
    network 2001:db8:1::/48
    network 2001:db8:2::/48
  exit-address-family
```

**Agent**:
```bash
# Ensure IPv6 multiprotocol capability enabled (default)
python3 wontyoubemyneighbor.py \
    --router-id 10.0.2.2 \
    --bgp-local-as 65001 \
    --bgp-peer 2001:db8::1 \
    --bgp-peer-as 65002
```

**Validation**:
- Capability negotiation includes Multiprotocol (AFI=2, SAFI=1)
- IPv6 routes received via MP_REACH_NLRI
- Check: `route.afi == 2` (AFI_IPV6)

### Test 4.9: Maximum Prefix Limit (Future)

**Objective**: Test max-prefix handling (when implemented)

**Expected behavior**:
- When peer exceeds configured limit (e.g., 1000 routes)
- Agent should send NOTIFICATION (Cease, max-prefix-reached)
- Session tears down

### Test 4.10: Route Refresh

**Objective**: Test ROUTE-REFRESH message

**Test**:
```python
# Send ROUTE-REFRESH to peer
from bgp.messages import BGPRouteRefresh

refresh_msg = BGPRouteRefresh(afi=1, safi=1)
session._send_message(refresh_msg)
```

**Expected**:
- Peer re-sends all routes
- Agent processes UPDATE messages
- Loc-RIB updated with fresh routes

---

## Test Execution Checklist

### Prerequisites

- [ ] FRR installed and running
- [ ] Python 3.9+ with dependencies installed
- [ ] Network connectivity between test nodes
- [ ] Firewall rules allow TCP 179
- [ ] Root/sudo access for FRR configuration

### Phase 1 Checklist

- [ ] FRR-1 configured with iBGP
- [ ] Agent starts without errors
- [ ] TCP connection established
- [ ] Session reaches Established
- [ ] Routes received from FRR
- [ ] KEEPALIVE messages exchanged
- [ ] No NOTIFICATION errors

### Phase 2 Checklist

- [ ] FRR-2 configured with eBGP
- [ ] AS_PATH contains remote AS
- [ ] eBGP routes preferred over iBGP
- [ ] (Optional) Route server peering works
- [ ] Decision process handles multiple routes

### Phase 3 Checklist

- [ ] Redistribution module implemented
- [ ] OSPF routes appear in BGP
- [ ] BGP routes appear in OSPF
- [ ] End-to-end ping succeeds
- [ ] Traceroute shows correct path

### Phase 4 Checklist

- [ ] Route reflection tested with 3+ clients
- [ ] Policy filtering works correctly
- [ ] Community matching functional
- [ ] AS_PATH prepending validated
- [ ] Graceful shutdown handled
- [ ] Hold timer expiration tested
- [ ] Rapid updates handled without errors
- [ ] IPv6 routes exchanged

---

## Performance Benchmarks

### Metrics to Capture

1. **Session Establishment Time**
   - Target: < 5 seconds from TCP connect to Established

2. **Route Processing Rate**
   - Target: 1000 routes/second (UPDATE processing)

3. **Decision Process Time**
   - Target: < 100ms for 1000 routes

4. **Memory Usage**
   - Target: < 1 MB per 1000 routes

5. **CPU Usage**
   - Target: < 10% steady state
   - Target: < 50% during convergence

### Benchmark Test

```python
import time

# Measure route installation time
start = time.time()
# FRR advertises 1000 routes
# Wait for all routes to be in Loc-RIB
while len(speaker.get_routes()) < 1000:
    time.sleep(0.1)
end = time.time()

print(f"Installed 1000 routes in {end - start:.2f} seconds")
print(f"Rate: {1000 / (end - start):.0f} routes/second")
```

---

## Known Issues & Workarounds

### Issue 1: Agent doesn't advertise local routes

**Workaround**: For Phase 1 testing, focus on route reception. To test advertisement, manually inject routes into Loc-RIB (requires code modification).

**Future**: Implement static route configuration or connected route advertisement.

### Issue 2: No route redistribution module

**Workaround**: Phase 3 requires implementing `redistribution.py` module first.

**Estimated effort**: 2-4 hours of development.

### Issue 3: No max-prefix limit

**Workaround**: Monitor memory usage manually. Phase 2B (route server) may be impractical without this feature.

**Future**: Implement max-prefix configuration.

---

## Success Criteria

### Minimum Viable Test (Phase 1)
- ✅ Session established with FRR
- ✅ Routes received and installed in Loc-RIB
- ✅ No crashes or NOTIFICATION errors
- ✅ KEEPALIVE exchanges for 5+ minutes

### Full Test Suite (All Phases)
- ✅ All Phase 1-3 tests passing
- ✅ At least 5 of 10 Phase 4 advanced tests passing
- ✅ Performance benchmarks met
- ✅ No memory leaks (stable memory over 30 minutes)
- ✅ End-to-end connectivity (Phase 3)

---

## Troubleshooting Guide

### Debug Logging

Enable verbose logging:
```bash
python3 wontyoubemyneighbor.py --router-id <ROUTER_ID> --bgp-local-as <AS> --log-level DEBUG ...
```

Watch logs:
```bash
tail -f /tmp/wontyoubemyneighbor.log
```

### Packet Capture

Capture BGP messages:
```bash
sudo tcpdump -i eth0 -w bgp.pcap port 179
wireshark bgp.pcap
```

### FRR Debug

Enable BGP debugging:
```bash
sudo vtysh
debug bgp updates
debug bgp keepalives
debug bgp neighbor-events
```

### Common Errors

**"Connection refused"**
- Check FRR is running: `systemctl status frr`
- Check BGP daemon enabled: `grep bgpd /etc/frr/daemons`

**"AS mismatch"**
- Verify AS numbers in configuration
- iBGP: AS numbers must match
- eBGP: AS numbers must differ

**"Hold timer expired"**
- Check network connectivity
- Verify KEEPALIVE are being sent
- Check hold time (default 180s)

---

## Next Steps After Testing

1. **Document Results**: Create TEST_RESULTS.md with findings
2. **Fix Bugs**: Address any issues found during testing
3. **Performance Tuning**: Optimize based on benchmarks
4. **Interoperability**: Test with BIRD, Cisco, Juniper (if available)
5. **Production Readiness**: Security audit, code review, load testing

---

**Document Version**: 1.0
**Last Updated**: 2026-01-17
**Author**: Claude (wontyoubemyneighbor project)
