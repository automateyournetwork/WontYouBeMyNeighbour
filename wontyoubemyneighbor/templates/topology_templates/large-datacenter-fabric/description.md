# Large Datacenter Fabric (Multi-Pod) Topology

## Overview
Hyperscale datacenter fabric with super-spine layer connecting multiple pods. Each pod has its own spine-leaf architecture with VXLAN/EVPN overlay.

## Architecture
```
            [Super-Spine-1]  [Super-Spine-2]
                   |              |
      +------------+----+----+----+------------+
      |            |    |    |    |            |
   [Spine-1a] [Spine-1b]   [Spine-2a] [Spine-2b]
      |    \    /    |        |    \    /    |
      |     \  /     |        |     \  /     |
   [Leaf-1a] [Leaf-1b]     [Leaf-2a] [Leaf-2b]
      |         |             |         |
    Pod 1       Pod 1       Pod 2       Pod 2
```

## Layers
- **Super-Spine**: Cross-pod connectivity (AS 65000)
- **Pod Spines**: Intra-pod aggregation (AS 65001, 65002)
- **Leaves**: Server connectivity (AS 650xx)

## Features
- 10 agents across 2 pods
- Dual super-spines for cross-pod redundancy
- VXLAN/EVPN for overlay
- eBGP underlay at every layer
