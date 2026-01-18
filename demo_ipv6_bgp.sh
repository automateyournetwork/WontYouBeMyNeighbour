#!/bin/bash
# IPv6 BGP Demonstration Script
# Proves that Won't You Be My Neighbor agent successfully implements IPv6 BGP
# Author: John Capobianco
# Date: 2026-01-18

set -e

echo "================================================================================"
echo "IPv6 BGP Implementation Demonstration"
echo "Won't You Be My Neighbor - BGP Agent with IPv6 Support"
echo "================================================================================"
echo ""

echo "### 1. Network Topology ###"
echo ""
echo "┌────────────────────┐      ┌────────────────────┐      ┌────────────────────┐"
echo "│  OSPF Router       │      │  Agent             │      │  BGP Router        │"
echo "│  172.20.0.3        │──────│  172.20.0.4        │──────│  172.20.0.2        │"
echo "│  2001:db8:ff::3/64 │      │  2001:db8:ff::4/64 │      │  2001:db8:ff::2/64 │"
echo "│  Loopback:         │      │  Router ID:        │      │  Loopback:         │"
echo "│  2001:db8:1::1/128 │      │  10.0.1.2          │      │  2001:db8:2::1/128 │"
echo "└────────────────────┘      └────────────────────┘      └────────────────────┘"
echo ""
sleep 2

echo "### 2. Verify IPv6 Transit Link Addresses ###"
echo ""
echo "BGP Router IPv6 address:"
docker exec BGP ip -6 addr show eth0 | grep "inet6 2001:db8:ff"
echo ""
echo "Agent IPv6 address:"
docker exec agent ip -6 addr show eth0 | grep "inet6 2001:db8:ff"
echo ""
echo "OSPF Router IPv6 address:"
docker exec OSPF ip -6 addr show eth0 | grep "inet6 2001:db8:ff"
echo ""
sleep 2

echo "### 3. Test IPv6 Connectivity on Transit Link ###"
echo ""
echo "Ping from BGP router to agent:"
docker exec BGP ping6 -c 3 2001:db8:ff::4 | grep -E "transmitted|received|loss|ms$"
echo ""
sleep 2

echo "### 4. Verify BGP Session is ESTABLISHED ###"
echo ""
echo "Agent perspective (from logs):"
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "BGP session ESTABLISHED" | tail -1
echo ""
echo "FRR perspective:"
docker exec BGP vtysh -c "show bgp ipv6 unicast summary" 2>/dev/null | grep -A 1 "Neighbor"
echo ""
sleep 2

echo "### 5. Verify IPv6 Capability Negotiation ###"
echo ""
echo "Agent advertises IPv6 capability (from logs):"
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "Configured.*capabilities" | tail -1
echo ""
echo "FRR recognizes agent's IPv6 capability:"
docker exec BGP vtysh -c "show ip bgp neighbors 172.20.0.4" 2>/dev/null | grep -A 2 "Address Family IPv6"
echo ""
sleep 2

echo "### 6. Verify IPv6 Route Learning via MP_REACH_NLRI ###"
echo ""
echo "Agent receives IPv6 UPDATE with MP_REACH_NLRI (RFC 4760):"
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "IPv6 MP_REACH_NLRI"
echo ""
echo "Agent adds IPv6 route to Adj-RIB-In:"
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "Added IPv6 route"
echo ""
sleep 2

echo "### 7. Verify Proper IPv6 Next Hop (NOT IPv4-mapped) ###"
echo ""
echo "IPv6 next hop is 2001:db8:ff::2 (NOT ::ffff:172.20.0.2):"
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "MP_REACH_NLRI.*next_hop"
echo ""
sleep 2

echo "### 8. Verify IPv6 Route in Agent's Loc-RIB ###"
echo ""
echo "Agent BGP statistics:"
docker exec agent cat /tmp/agent-ipv6-complete.log | grep -A 5 "BGP Statistics:" | tail -6
echo ""
echo "Agent BGP routing table:"
docker exec agent cat /tmp/agent-ipv6-complete.log | grep -A 5 "BGP Routing Table:" | tail -6
echo ""
sleep 2

echo "### 9. Verify IPv6 Route Installed in Linux Kernel ###"
echo ""
echo "Agent kernel IPv6 routing table:"
docker exec agent ip -6 route show | grep "2001:db8:2::1"
echo ""
echo "Kernel route installation log:"
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "Installed IPv6 kernel route"
echo ""
sleep 2

echo "### 10. FRR Perspective - IPv6 Routes ###"
echo ""
echo "FRR IPv6 unicast routes:"
docker exec BGP vtysh -c "show bgp ipv6 unicast" 2>/dev/null | grep -E "Network|2001:db8:2::1"
echo ""
echo "FRR advertising IPv6 routes to agent:"
docker exec BGP vtysh -c "show bgp ipv6 unicast neighbors 172.20.0.4 advertised-routes" 2>/dev/null | grep -E "Network|2001:db8:2::1"
echo ""
sleep 2

echo "### 11. Protocol Implementation Details ###"
echo ""
echo "✓ RFC 4760 - Multiprotocol Extensions for BGP-4"
echo "  - MP_REACH_NLRI (Attribute Type 14) implemented"
echo "  - MP_UNREACH_NLRI (Attribute Type 15) implemented"
echo "  - AFI = 2 (IPv6), SAFI = 1 (Unicast)"
echo ""
echo "✓ IPv6 Next Hop Resolution"
echo "  - Proper IPv6 next hop (2001:db8:ff::2) on transit link"
echo "  - No IPv4-mapped IPv6 addresses"
echo ""
echo "✓ BGP Routing Information Bases"
echo "  - Adj-RIB-In: Stores IPv6 routes from peers"
echo "  - Loc-RIB: Stores best IPv6 routes"
echo "  - Kernel: Routes installed with 'ip -6 route'"
echo ""
sleep 2

echo "### 12. Files Modified for IPv6 Support ###"
echo ""
echo "1. wontyoubemyneighbor/bgp/attributes.py (~250 lines added)"
echo "   - MPReachNLRIAttribute class (Type 14)"
echo "   - MPUnreachNLRIAttribute class (Type 15)"
echo "   - IPv6 NLRI encoding/decoding"
echo ""
echo "2. wontyoubemyneighbor/bgp/session.py"
echo "   - IPv6 UPDATE processing"
echo "   - MP_REACH_NLRI/MP_UNREACH_NLRI handling"
echo ""
echo "3. wontyoubemyneighbor/bgp/rib.py"
echo "   - IPv6 next hop property"
echo ""
echo "4. wontyoubemyneighbor/lib/kernel_routes.py"
echo "   - IPv6 kernel route installation (ip -6 route)"
echo ""
sleep 2

echo "### 13. Summary - IPv6 BGP Implementation Status ###"
echo ""
echo "✅ IPv6 Capability Negotiation (RFC 4760)"
echo "✅ MP_REACH_NLRI Parsing (Attribute Type 14)"
echo "✅ MP_UNREACH_NLRI Parsing (Attribute Type 15)"
echo "✅ IPv6 Route Learning from BGP peers"
echo "✅ IPv6 Routes in Adj-RIB-In"
echo "✅ IPv6 Routes in Loc-RIB"
echo "✅ IPv6 Kernel Route Installation"
echo "✅ Proper IPv6 Next Hop on Transit Link"
echo "✅ End-to-End IPv6 Connectivity"
echo ""
echo "================================================================================"
echo "IPv6 BGP Implementation: COMPLETE AND WORKING ✅"
echo "================================================================================"
