# MPLS Service Provider Core Topology

## Overview

Service provider MPLS backbone network supporting L3VPN services for multiple customers. Uses LDP for label distribution and MP-BGP for VPN route exchange.

## Architecture

```
Customer-A              Customer-B
   │                       │
   CE                      CE
   │                       │
┌──┴──┐               ┌────┴───┐
│PE-1 │               │  PE-3  │
│VRF-A│               │ VRF-B  │
└──┬──┘               └───┬────┘
   │                      │
┌──┴───────────────────────┴──┐
│           P-1               │
│       (Core LSR)            │
└──────────┬──────────────────┘
           │
┌──────────┴──────────────────┐
│           P-2               │
│       (Core LSR)            │
└──┬───────────────────────┬──┘
   │                       │
┌──┴──┐               ┌────┴───┐
│PE-2 │               │  PE-4  │
│VRF-A│               │ VRF-B  │
└──┬──┘               └───┬────┘
   │                      │
   CE                     CE
   │                      │
Customer-A             Customer-B
```

## Components

### PE Routers (4 devices)
- Customer-facing with VRF support
- MP-BGP VPNv4 for VPN routes
- eBGP peering with customer CEs
- LDP for core label distribution

### P Routers (2 devices)
- Core label switching only
- No VPN awareness
- OSPF and LDP only
- High-speed label forwarding

## VRF Configuration

| VRF | Route Distinguisher | RT Import | RT Export | Customers |
|-----|-------------------|-----------|-----------|-----------|
| VRF-A | 65000:100 | 65000:100 | 65000:100 | PE-1, PE-2 |
| VRF-B | 65000:200 | 65000:200 | 65000:200 | PE-3, PE-4 |

## Protocols

### IGP (OSPF)
- All routers in Area 0
- Loopback reachability for LDP
- Fast convergence

### LDP
- All core-facing interfaces
- Label distribution for /32 loopbacks
- PHP (Penultimate Hop Popping)

### MP-BGP
- VPNv4 address family
- iBGP full mesh between PEs
- Route reflector optional for scale

## Use Cases

- **ISP Backbone**: Carrier-grade core network
- **Enterprise MPLS**: Multi-site WAN connectivity
- **Managed VPN Service**: Customer VPN hosting
- **Wholesale Transit**: L3VPN resale services
