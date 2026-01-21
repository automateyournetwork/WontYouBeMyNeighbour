# WAN Hub-and-Spoke Topology

## Overview
Enterprise WAN connecting headquarters to branch offices using GRE tunnels over the Internet with iBGP for route exchange.

## Architecture
- **Dual Hubs**: Hub-1 (Primary) and Hub-2 (Backup) at HQ/DR
- **Branch Spokes**: Each branch has dual tunnels to both hubs
- **Routing**: iBGP over tunnels for dynamic failover

## Features
- Primary/Backup tunnel failover via BGP local preference
- DHCP on each branch for user connectivity
- Scalable design - add new spokes easily
