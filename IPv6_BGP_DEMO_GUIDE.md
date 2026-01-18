# IPv6 BGP Implementation - Video Demonstration Guide

**Project**: Won't You Be My Neighbor - BGP Agent
**Feature**: IPv6 Support with RFC 4760 Multiprotocol BGP
**Date**: 2026-01-18
**Author**: John Capobianco

---

## Quick Start - Run the Demo

Two demo scripts are available:

### Option 1: Quick Demo (2 minutes)
```bash
./demo_ipv6_bgp_quick.sh
```

### Option 2: Full Demo (5 minutes)
```bash
./demo_ipv6_bgp.sh
```

---

## Manual Demonstration Commands

For a hands-on video demonstration, use these commands:

### 1. Show Network Topology

```bash
echo "Network Topology:"
echo "OSPF (172.20.0.3) ←→ Agent (172.20.0.4) ←→ BGP (172.20.0.2)"
echo "IPv6: 2001:db8:ff::3/64 ←→ 2001:db8:ff::4/64 ←→ 2001:db8:ff::2/64"
```

### 2. Verify BGP Session is ESTABLISHED

```bash
# Agent perspective
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "BGP session ESTABLISHED"
```

**Expected Output:**
```
[INFO] BGPSession[172.20.0.2]: BGP session ESTABLISHED with 172.20.0.2
```

### 3. Verify IPv6 Capability Negotiation

```bash
# Agent advertises IPv6 capability
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "Configured.*capabilities"

# FRR recognizes agent's IPv6 capability
docker exec BGP vtysh -c "show ip bgp neighbors 172.20.0.4" 2>/dev/null | grep "Address Family IPv6"
```

**Expected Output:**
```
[INFO] BGPSession[172.20.0.2]: Configured 3 capabilities: [1, 65, 2]
  Address Family IPv6 Unicast: advertised and received
```

**Capability Breakdown:**
- **Capability 1**: Multiprotocol Extensions (includes IPv4 + IPv6 unicast)
- **Capability 65**: 4-Byte AS Numbers (RFC 6793)
- **Capability 2**: Route Refresh (RFC 2918)

### 4. Verify IPv6 Route Learning via MP_REACH_NLRI

```bash
# Agent receives IPv6 UPDATE with MP_REACH_NLRI (RFC 4760 Attribute Type 14)
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "IPv6 MP_REACH_NLRI"
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "Added IPv6 route"
```

**Expected Output:**
```
[INFO] BGPSession[172.20.0.2]: IPv6 MP_REACH_NLRI: 1 routes, next_hop=2001:db8:ff::2
[INFO] BGPSession[172.20.0.2]: Added IPv6 route: 2001:db8:2::1/128 via 2001:db8:ff::2
```

**Key Point:** Next hop is **2001:db8:ff::2** (proper IPv6), NOT **::ffff:172.20.0.2** (IPv4-mapped)

### 5. Verify IPv6 Routes in Agent's Loc-RIB

```bash
# Show BGP statistics
docker exec agent cat /tmp/agent-ipv6-complete.log | grep -B 3 "Loc-RIB Routes:" | tail -4

# Show BGP routing table
docker exec agent cat /tmp/agent-ipv6-complete.log | grep -A 4 "BGP Routing Table:" | tail -5
```

**Expected Output:**
```
BGP Statistics:
  Total Peers:       1
  Established Peers: 1
  Loc-RIB Routes:    1

BGP Routing Table:
Network              Next Hop         Path                 Source
----------------------------------------------------------------------
2001:db8:2::1/128    N/A                                   peer
```

### 6. Verify IPv6 Route Installed in Linux Kernel

```bash
# Show kernel installation log
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "Installed IPv6 kernel route"

# Show kernel routing table
docker exec agent ip -6 route show | grep "2001:db8:2::1"
```

**Expected Output:**
```
[INFO] KernelRoutes: ✓ Installed IPv6 kernel route: 2001:db8:2::1/128 via 2001:db8:ff::2 (bgp)
2001:db8:2::1 via 2001:db8:ff::2 dev eth0 metric 100 pref medium
```

### 7. Verify IPv6 Transit Link Connectivity

```bash
# Show IPv6 addresses
docker exec BGP ip -6 addr show eth0 | grep "inet6 2001:db8:ff"
docker exec agent ip -6 addr show eth0 | grep "inet6 2001:db8:ff"
docker exec OSPF ip -6 addr show eth0 | grep "inet6 2001:db8:ff"

# Test IPv6 ping
docker exec BGP ping6 -c 3 2001:db8:ff::4
```

**Expected Output:**
```
    inet6 2001:db8:ff::2/64 scope global
    inet6 2001:db8:ff::4/64 scope global
    inet6 2001:db8:ff::3/64 scope global

PING 2001:db8:ff::4 (2001:db8:ff::4): 56 data bytes
64 bytes from 2001:db8:ff::4: seq=0 ttl=64 time=0.157 ms
64 bytes from 2001:db8:ff::4: seq=1 ttl=64 time=0.391 ms
64 bytes from 2001:db8:ff::4: seq=2 ttl=64 time=0.446 ms

--- 2001:db8:ff::4 ping statistics ---
3 packets transmitted, 3 packets received, 0% packet loss
```

### 8. FRR Perspective - IPv6 Routes

```bash
# Show BGP IPv6 summary
docker exec BGP vtysh -c "show bgp ipv6 unicast summary" 2>/dev/null

# Show BGP IPv6 routes
docker exec BGP vtysh -c "show bgp ipv6 unicast" 2>/dev/null

# Show routes advertised to agent
docker exec BGP vtysh -c "show bgp ipv6 unicast neighbors 172.20.0.4 advertised-routes" 2>/dev/null
```

**Expected Output:**
```
Neighbor        V         AS   MsgRcvd   MsgSent   TblVer  InQ OutQ  Up/Down State/PfxRcd   PfxSnt
172.20.0.4      4      65001      1167      1863        0    0    0 00:05:13            0        1

BGP routing table entry for 2001:db8:2::1/128
*> 2001:db8:2::1/128
                    ::                       0         32768 i
```

---

## Key Technical Points to Highlight in Video

### 1. RFC 4760 Implementation
- **MP_REACH_NLRI** (Attribute Type 14) - Advertise IPv6 routes
- **MP_UNREACH_NLRI** (Attribute Type 15) - Withdraw IPv6 routes
- **AFI = 2** (IPv6), **SAFI = 1** (Unicast)

### 2. Proper IPv6 Next Hops
- Before: `::ffff:172.20.0.2` (IPv4-mapped IPv6 address)
- After: `2001:db8:ff::2` (proper IPv6 address on transit link)
- Required configuring route-map on FRR to set IPv6 next hop

### 3. BGP Routing Information Bases (RIBs)
- **Adj-RIB-In**: Stores routes received from peers (before policy)
- **Loc-RIB**: Stores best routes selected (one per prefix)
- **Adj-RIB-Out**: Stores routes to advertise to peers (after policy)

### 4. Kernel Route Installation
- Uses `ip -6 route add` command
- Requires IPv6 enabled on interfaces
- Requires proper IPv6 next hop (not IPv4-mapped)

---

## Implementation Statistics

### Files Modified: 4
1. **wontyoubemyneighbor/bgp/attributes.py** (~250 lines added)
   - `MPReachNLRIAttribute` class
   - `MPUnreachNLRIAttribute` class
   - IPv6 NLRI encoding/decoding

2. **wontyoubemyneighbor/bgp/session.py** (~40 lines modified)
   - IPv6 route processing in `_process_update()`
   - MP_REACH_NLRI and MP_UNREACH_NLRI handling

3. **wontyoubemyneighbor/bgp/rib.py** (~10 lines modified)
   - Enhanced `next_hop` property for IPv6

4. **wontyoubemyneighbor/lib/kernel_routes.py** (~20 lines modified)
   - IPv6 route installation with `ip -6 route`
   - IPv4-mapped IPv6 address handling

### Total Lines of Code: ~320 lines

### Development Time: ~12 hours
- MP_REACH_NLRI/MP_UNREACH_NLRI implementation: 4 hours
- UPDATE message processing: 2 hours
- Kernel route installation: 2 hours
- Testing and debugging: 4 hours

---

## Comparison: Before vs After

### Before IPv6 Implementation
```
BGP Statistics:
  Established Peers: 1
  Loc-RIB Routes:    0  ❌

Issue: Agent couldn't process IPv6 UPDATE messages
```

### After IPv6 Implementation
```
BGP Statistics:
  Established Peers: 1
  Loc-RIB Routes:    1  ✅

BGP Routing Table:
2001:db8:2::1/128    N/A              peer

Kernel:
2001:db8:2::1 via 2001:db8:ff::2 dev eth0  ✅
```

---

## Video Script Outline

### Introduction (30 seconds)
"Today I'm demonstrating IPv6 BGP support in my 'Won't You Be My Neighbor' agent - a Python implementation of BGP and OSPF routing protocols."

### Architecture (30 seconds)
"The agent sits between an OSPF router and a BGP router, learning routes from both protocols. I've just implemented full IPv6 support using RFC 4760 Multiprotocol BGP."

### Demonstration (3 minutes)
1. Show BGP session is ESTABLISHED
2. Show IPv6 capability negotiation
3. Show IPv6 routes received via MP_REACH_NLRI
4. Show routes in agent's RIB
5. Show routes installed in kernel
6. Show FRR's perspective
7. Test IPv6 connectivity

### Technical Highlights (1 minute)
"The implementation includes MP_REACH_NLRI and MP_UNREACH_NLRI attribute parsing, proper IPv6 next hop resolution, and kernel route installation using the `ip -6 route` command."

### Conclusion (30 seconds)
"This demonstrates a fully functional IPv6 BGP implementation that can learn routes from production BGP routers like FRRouting and install them in the Linux kernel."

---

## Troubleshooting

### If BGP session not established:
```bash
docker exec agent cat /tmp/agent-ipv6-complete.log | grep -i "error\|failed"
docker exec BGP vtysh -c "show bgp ipv6 unicast summary"
```

### If IPv6 routes not appearing:
```bash
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "MP_REACH_NLRI"
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "Loc-RIB"
```

### If kernel routes not installed:
```bash
docker exec agent ip -6 route show
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "kernel route"
```

---

## Additional Resources

- **RFC 4760**: Multiprotocol Extensions for BGP-4
- **RFC 4271**: A Border Gateway Protocol 4 (BGP-4)
- **BGP Message Format**: RFC 4271 Section 4
- **Path Attributes**: RFC 4271 Section 5

---

## Contact

For questions or feedback:
- GitHub: https://github.com/john.capobianco/WontYouBeMyNeighbour
- Email: john.capobianco@example.com

**License**: MIT
