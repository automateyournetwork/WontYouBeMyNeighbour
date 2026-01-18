# Multi-Protocol Routing Through Agent - Test Plan

## Summary of Fixes

### OSPF Fixes ✅
1. Fixed duplicate FSM transition (Exchange → Full) in `ospf/neighbor.py`
2. Fixed premature exchange_done() call in `ospf/adjacency.py`
3. Fixed ls_request_list population timing in `wontyoubemyneighbor.py`

### BGP Fixes ✅
1. Removed duplicate KEEPALIVE send in `bgp/session.py`
2. Fixed hold timer restart in OpenConfirm state in `bgp/fsm.py`
3. **NEW**: Added `next_hop` property to BGPRoute class in `bgp/rib.py` for kernel route installation

## Current Status

### OSPF ✅
- **State**: Full (agent side)
- **Route Learned**: 10.10.10.1/32 via 172.20.0.3
- **Kernel Route**: Installed successfully
- **Loopback**: Configured on OSPF router

### BGP ✅
- **State**: Established
- **Route Advertised**: 20.20.20.1/32 from BGP router
- **Kernel Route**: Not yet installed (needs agent restart with next_hop property fix)
- **Loopback**: Configured on BGP router

## Topology

```
OSPF Router (172.20.0.3)                 BGP Router (172.20.0.2)
  Loopback: 10.10.10.1/32                  Loopback: 20.20.20.1/32
  Protocol: OSPF Area 0.0.0.0              Protocol: BGP AS 65002
         |                                        |
         |                                        |
         +----------------> Agent <---------------+
                        (172.20.0.4)
                        AS 65001

                    Route Translation:
                    OSPF ←→ Kernel ←→ BGP
```

## Network Details

### OSPF Router
- **Container**: OSPF
- **Router ID**: 10.0.1.3 (likely)
- **Interface IP**: 172.20.0.3
- **Loopback**: 10.10.10.1/32
- **OSPF Area**: 0.0.0.0
- **Network Type**: Point-to-Point

### BGP Router
- **Container**: BGP
- **Router ID**: 10.0.1.1
- **AS Number**: 65002
- **Interface IP**: 172.20.0.2
- **Loopback**: 20.20.20.1/32
- **Neighbor**: 172.20.0.4 (agent)
- **Timers**: 10s keepalive, 30s hold time

### Agent
- **Container**: agent
- **Router ID**: 10.0.1.2
- **Interface IP**: 172.20.0.4
- **OSPF**: Area 0.0.0.0, Point-to-Point
- **BGP**: AS 65001, Passive mode

## Next Steps

### 1. Restart Agent (Required)
The agent needs to be restarted to load the BGPRoute.next_hop property fix:

```bash
# Restart the agent container
docker restart agent

# Wait a few seconds for protocols to establish
sleep 10
```

### 2. Verify Protocol States

```bash
# Check OSPF neighbor status
docker exec OSPF vtysh -c "show ip ospf neighbor"
# Expected: State = Full

# Check BGP session status
docker exec BGP vtysh -c "show ip bgp summary"
# Expected: State = Established

# Check agent logs for protocol states
docker logs agent --tail 50 | grep -E "(OSPF|BGP|Full|Established)"
```

### 3. Verify Route Learning

```bash
# Check OSPF routes on OSPF router
docker exec OSPF vtysh -c "show ip ospf route"
# Should show: 10.10.10.1/32 directly attached

# Check BGP routes on BGP router
docker exec BGP vtysh -c "show ip bgp" | grep "20.20.20.1"
# Should show: *> 20.20.20.1/32 with next hop 0.0.0.0 (local)

# Check agent kernel routes
docker exec agent ip route show
# Expected routes:
# - 10.10.10.1 via 172.20.0.3 dev eth0 metric 10 (OSPF)
# - 20.20.20.1 via 172.20.0.2 dev eth0 metric 20 (BGP)
```

### 4. Test Connectivity: OSPF → BGP

```bash
# Ping from OSPF loopback to BGP loopback
docker exec OSPF ping -c 3 -I 10.10.10.1 20.20.20.1

# Expected output:
# 3 packets transmitted, 3 received, 0% packet loss
#
# Routing path:
# 10.10.10.1 (OSPF loopback)
#   → 172.20.0.3 (OSPF eth0)
#   → 172.20.0.4 (Agent eth0)
#   → 172.20.0.2 (BGP eth0)
#   → 20.20.20.1 (BGP loopback)
```

### 5. Test Connectivity: BGP → OSPF

```bash
# Ping from BGP loopback to OSPF loopback
docker exec BGP ping -c 3 -I 20.20.20.1 10.10.10.1

# Expected output:
# 3 packets transmitted, 3 received, 0% packet loss
#
# Routing path:
# 20.20.20.1 (BGP loopback)
#   → 172.20.0.2 (BGP eth0)
#   → 172.20.0.4 (Agent eth0)
#   → 172.20.0.3 (OSPF eth0)
#   → 10.10.10.1 (OSPF loopback)
```

## Expected Agent Routes

After restart, the agent should have these routes in its kernel:

```
10.10.10.1 via 172.20.0.3 dev eth0 metric 10       # OSPF route
20.20.20.1 via 172.20.0.2 dev eth0 metric 20       # BGP route
172.20.0.0/20 dev eth0 scope link src 172.20.0.4   # Connected
```

## Troubleshooting

### If OSPF neighbor not Full:
```bash
docker exec OSPF vtysh -c "show ip ospf neighbor detail"
docker logs agent | grep OSPF | tail -50
```

### If BGP not Established:
```bash
docker exec BGP vtysh -c "show ip bgp neighbors 172.20.0.4"
docker logs agent | grep BGP | tail -50
```

### If routes not learned:
```bash
# Check agent decision process
docker logs agent | grep -E "(decision|route|Route)" | tail -30

# Check for errors
docker logs agent | grep -E "(error|Error|ERROR)" | tail -20
```

### If ping fails:
```bash
# Verify loopbacks are up
docker exec OSPF ip addr show lo
docker exec BGP ip addr show lo

# Verify routing tables
docker exec OSPF ip route get 20.20.20.1 from 10.10.10.1
docker exec BGP ip route get 10.10.10.1 from 20.20.20.1
docker exec agent ip route show

# Check if agent is forwarding
docker exec agent cat /proc/sys/net/ipv4/ip_forward
# Should be: 1
```

## Success Criteria

1. ✅ OSPF neighbor reaches Full state
2. ✅ BGP session reaches Established state
3. ✅ Agent learns 10.10.10.1/32 via OSPF
4. ⏳ Agent learns 20.20.20.1/32 via BGP (pending restart)
5. ⏳ Agent installs both routes in kernel (pending restart)
6. ⏳ Ping from OSPF loopback to BGP loopback succeeds (pending restart)
7. ⏳ Ping from BGP loopback to OSPF loopback succeeds (pending restart)
