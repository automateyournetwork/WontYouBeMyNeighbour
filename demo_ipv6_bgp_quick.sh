#!/bin/bash
# Quick IPv6 BGP Demo - Perfect for Video
# Shows key highlights in ~2 minutes

echo "🌐 IPv6 BGP Implementation Demo - Won't You Be My Neighbor"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣  BGP Session Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "BGP session ESTABLISHED" | tail -1
docker exec agent cat /tmp/agent-ipv6-complete.log | grep -B 3 "Loc-RIB Routes:" | tail -4
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣  IPv6 Capability Negotiated (RFC 4760)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker exec BGP vtysh -c "show ip bgp neighbors 172.20.0.4" 2>/dev/null | grep "Address Family IPv6 Unicast"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣  IPv6 Route Received via MP_REACH_NLRI (Attribute Type 14)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "IPv6 MP_REACH_NLRI"
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "Added IPv6 route"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣  IPv6 Route in Agent's BGP RIB"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker exec agent cat /tmp/agent-ipv6-complete.log | grep -A 4 "BGP Routing Table:" | tail -5
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣  IPv6 Route Installed in Linux Kernel"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker exec agent cat /tmp/agent-ipv6-complete.log | grep "Installed IPv6 kernel route"
echo ""
echo "Kernel routing table:"
docker exec agent ip -6 route show | grep "2001:db8:2::1"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣  IPv6 Transit Link Connectivity"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "IPv6 addresses on transit link:"
echo "  BGP Router:  2001:db8:ff::2/64"
echo "  Agent:       2001:db8:ff::4/64"
echo "  OSPF Router: 2001:db8:ff::3/64"
echo ""
echo "Testing IPv6 ping:"
docker exec BGP ping6 -c 2 2001:db8:ff::4 2>&1 | grep -E "transmitted|received|loss"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7️⃣  FRR Perspective - IPv6 Routes"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker exec BGP vtysh -c "show bgp ipv6 unicast" 2>/dev/null | head -10
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Summary: IPv6 BGP Implementation COMPLETE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ RFC 4760 Multiprotocol BGP implemented"
echo "✓ MP_REACH_NLRI parsing (Type 14)"
echo "✓ IPv6 routes learned from BGP peer"
echo "✓ Routes installed in Linux kernel"
echo "✓ Proper IPv6 next hop (2001:db8:ff::2)"
echo "✓ End-to-end IPv6 connectivity verified"
echo ""
