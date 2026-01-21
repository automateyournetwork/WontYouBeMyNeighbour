# Campus Network Topology

## Overview
Multi-building campus network using OSPF multi-area design for scalability and VRRP for gateway redundancy.

## Architecture
- **Core Layer**: Dual core switches (Area 0) with VRRP
- **Building Distribution**: Per-building distribution switches (Area 1, 2)
- **Access Layer**: Floor-level switches with DHCP

## OSPF Areas
- Area 0: Core backbone (core-1, core-2)
- Area 1: Building A (bldg-a-1, bldg-a-acc1, bldg-a-acc2)
- Area 2: Building B (bldg-b-1, bldg-b-acc1, bldg-b-acc2)

## Features
- VRRP for default gateway failover
- DHCP on access switches
- Multi-area OSPF for route summarization
- Dual uplinks from each building
