# Spine-Leaf Data Center Topology

## Overview

This template implements a modern spine-leaf data center architecture with VXLAN/EVPN overlay for multi-tenant environments. The topology provides high availability, scalability, and tenant isolation.

## Architecture

```
                    ┌─────────┐      ┌─────────┐
                    │ Spine-1 │      │ Spine-2 │
                    │ AS65000 │      │ AS65000 │
                    └────┬────┘      └────┬────┘
          ┌──────┬──────┼──────┬─────────┼──────┬──────┐
          │      │      │      │         │      │      │
     ┌────┴─┐ ┌──┴──┐ ┌─┴───┐ ┌┴────┐ ┌──┴──┐ ┌─┴───┐ │
     │Leaf-1│ │Leaf-2│ │Leaf-3│ │Leaf-4│
     │AS65001│ │AS65002│ │AS65003│ │AS65004│
     └──────┘ └──────┘ └──────┘ └──────┘
         │        │        │        │
      Tenant   Tenant   Tenant   Tenant
      Networks Networks Networks Networks
```

## Components

### Spine Layer (2 devices)
- **Spine-1, Spine-2**: Route servers in AS 65000
- eBGP peering to all leaf switches
- No overlay termination (underlay only)

### Leaf Layer (4 devices)
- **Leaf-1 through Leaf-4**: ToR switches with unique ASNs (65001-65004)
- VXLAN VTEP functionality
- EVPN route-target configuration
- Multi-tenant VNI support

## Protocols

### Underlay (IP Fabric)
- **eBGP**: Each leaf peers with both spines using point-to-point links
- /30 subnets for inter-switch links
- Loopback-based VTEP addressing

### Overlay (VXLAN/EVPN)
- **VXLAN**: Layer 2 extension over Layer 3 fabric
- **EVPN**: BGP-based control plane for MAC/IP learning
- VNI to VLAN mapping for tenant isolation

## VNI Assignments

| VNI   | VLAN | Tenant   | Leaves        |
|-------|------|----------|---------------|
| 10010 | 10   | Tenant-A | Leaf-1, Leaf-2|
| 10011 | 11   | Tenant-B | Leaf-1, Leaf-3|
| 10020 | 20   | Tenant-C | Leaf-2, Leaf-4|
| 10030 | 30   | Tenant-D | Leaf-3, Leaf-4|

## IP Addressing

### Loopbacks
- Spines: 10.0.0.x/32
- Leaves: 10.0.1.x/32

### Underlay Links
- Spine-1 to Leaves: 172.16.1-4.0/30
- Spine-2 to Leaves: 172.16.5-8.0/30

## Scaling

To add more leaf switches:
1. Add new leaf with unique ASN
2. Connect to both spines
3. Configure eBGP peering
4. Add VTEP and desired VNIs

## Use Cases

- **Cloud Infrastructure**: Multi-tenant IaaS/PaaS
- **Container Platforms**: Kubernetes/OpenShift underlay
- **Private Cloud**: Enterprise data center fabric
- **Colocation**: Multi-tenant hosting environments
