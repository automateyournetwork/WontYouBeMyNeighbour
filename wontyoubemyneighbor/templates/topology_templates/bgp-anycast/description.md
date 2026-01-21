# BGP Anycast DNS/CDN Topology

## Overview
Global anycast deployment where multiple sites advertise the same IP prefix (192.0.2.1/32) via BGP. Users are automatically routed to the nearest site based on Internet routing.

## Architecture
- **4 Geographically Distributed Sites**: US-East, US-West, EU-West, APAC
- **Single Anycast IP**: 192.0.2.1/32 announced from all sites
- **Independent Transit**: Each site has its own ISP connection

## How It Works
1. All sites announce 192.0.2.1/32 to their transit providers
2. Internet routing naturally directs users to closest site
3. If a site fails, BGP withdraws the route and traffic shifts automatically

## Use Cases
- DNS authoritative servers
- CDN edge nodes
- DDoS scrubbing centers
- Global service endpoints
