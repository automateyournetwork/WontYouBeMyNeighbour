# Three-Tier Enterprise Topology

## Overview

Classic hierarchical enterprise network design with Core, Distribution, and Access layers. Uses OSPF for internal routing and BGP for WAN/Internet connectivity.

## Architecture

```
                     ISP (AS 65200)
                          │
           ┌──────────────┴──────────────┐
           │                             │
      ┌────┴────┐                  ┌─────┴────┐
      │ Core-1  │──────────────────│  Core-2  │
      │ OSPF+BGP│                  │ OSPF+BGP │
      └────┬────┘                  └────┬─────┘
      ┌────┴─────────────────────────────┴────┐
      │                                       │
 ┌────┴────┐                            ┌─────┴────┐
 │ Dist-1  │                            │  Dist-2  │
 │  OSPF   │                            │   OSPF   │
 └────┬────┘                            └────┬─────┘
   ┌──┴──┐                                ┌──┴──┐
   │     │                                │     │
┌──┴──┐ ┌┴────┐                       ┌───┴─┐ ┌─┴───┐
│Acc-1│ │Acc-2│                       │Acc-3│ │Acc-4│
│DHCP │ │     │                       │DHCP │ │     │
└─────┘ └─────┘                       └─────┘ └─────┘
  │       │                             │       │
Users  Servers                       Guests  Mgmt
```

## Layers

### Core Layer (2 devices)
- **Core-1, Core-2**: High-performance routing
- OSPF Area 0 backbone
- iBGP between cores
- eBGP to ISP (Core-1 only)

### Distribution Layer (2 devices)
- **Dist-1, Dist-2**: Route aggregation and policy
- OSPF for internal routing
- Dual uplinks to both cores
- VLAN termination

### Access Layer (4 devices)
- **Access-1 through Access-4**: End-user connectivity
- OSPF for routing
- DHCP services (Access-1 and Access-3)
- Per-VLAN segmentation

## VLANs and Subnets

| Access Switch | VLAN | Subnet | Purpose |
|--------------|------|--------|---------|
| Access-1 | 10 | 192.168.10.0/24 | Users |
| Access-2 | 20 | 192.168.20.0/24 | Servers |
| Access-3 | 30 | 192.168.30.0/24 | Guests |
| Access-4 | 40 | 192.168.40.0/24 | Management |

## DHCP Configuration

### Access-1 (Users)
- Pool: 192.168.10.100 - 192.168.10.200
- Gateway: 192.168.10.1
- DNS: 8.8.8.8

### Access-3 (Guests)
- Pool: 192.168.30.100 - 192.168.30.200
- Gateway: 192.168.30.1
- DNS: 8.8.8.8

## Routing

### OSPF
- All devices in Area 0
- Point-to-point links on /30 subnets
- User networks advertised

### BGP
- AS 65100 (Enterprise)
- iBGP full mesh between cores
- eBGP to ISP (AS 65200)
- Default route from ISP

## Use Cases

- **Corporate HQ**: Multiple departments and zones
- **Campus Network**: Buildings connected via distribution
- **Branch Office**: Scaled-down version possible
- **Data Center Edge**: Server farm connectivity
