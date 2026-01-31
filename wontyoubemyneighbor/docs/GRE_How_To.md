# GRE Tunnel How-To Guide

## Overview

GRE (Generic Routing Encapsulation) enables Agentic network agents to interconnect with external networks such as Cisco CML, Containerlab, EVE-NG, GNS3, or real hardware. Once a GRE tunnel is established, you can run routing protocols (OSPF, BGP) over the tunnel to exchange routes with external networks.

**RFC Compliance:** RFC 2784 (Base GRE), RFC 2890 (Key and Sequence Extensions)

## Table of Contents

1. [Architecture](#architecture)
2. [Use Cases](#use-cases)
3. [Configuration Methods](#configuration-methods)
4. [Example: Connect to Cisco CML](#example-connect-to-cisco-cml)
5. [Example: Connect to Containerlab](#example-connect-to-containerlab)
6. [Example: Multi-Site Mesh](#example-multi-site-mesh)
7. [API Reference](#api-reference)
8. [Troubleshooting](#troubleshooting)

---

## Architecture

### GRE Packet Structure

```
┌──────────────────────────────────────────────────────────┐
│                    Outer IP Header                        │
│  (Source: Agent IP, Dest: Remote IP, Protocol: 47)       │
├──────────────────────────────────────────────────────────┤
│                     GRE Header                            │
│  ┌─────┬─────┬─────┬─────────────┬───────────────────┐   │
│  │  C  │  K  │  S  │  Reserved   │   Protocol Type   │   │
│  ├─────┴─────┴─────┴─────────────┴───────────────────┤   │
│  │            Checksum (optional)                     │   │
│  ├───────────────────────────────────────────────────┤   │
│  │              Key (optional)                        │   │
│  ├───────────────────────────────────────────────────┤   │
│  │        Sequence Number (optional)                  │   │
│  └───────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────┤
│                   Inner IP Packet                         │
│            (Original packet being tunneled)               │
└──────────────────────────────────────────────────────────┘
```

### Key Specifications

| Item | Value |
|------|-------|
| IP Protocol Number | 47 |
| Minimum Header Size | 4 bytes |
| Maximum Header Size | 16 bytes (with all options) |
| MTU Overhead | 24-36 bytes |
| Default Tunnel MTU | 1400 bytes |

---

## Use Cases

### 1. Lab Integration
Connect Agentic agents to virtual lab environments (CML, Containerlab, EVE-NG, GNS3).

### 2. Hybrid Testing
Mix virtual agents with real network hardware for realistic testing.

### 3. Multi-Vendor Peering
Peer agents with Cisco, Juniper, Arista, FRRouting, and other GRE-capable devices.

### 4. Remote Site Connectivity
Connect geographically distributed agents over IP networks.

### 5. Route Learning
Agents learn external routes via OSPF/BGP running over the tunnel.

---

## Configuration Methods

### Method 1: Agent Builder Wizard (Recommended)

1. Navigate to the **Agent Builder** wizard
2. Click **Add Interface**
3. Select **GRE Tunnel** from the Overlay/Tunnel group
4. Configure:
   - **Local Endpoint IP**: Your agent's physical interface IP
   - **Remote Endpoint IP**: The external router's IP (CML, CLAB, etc.)
   - **Tunnel IP**: IP address for the tunnel interface (e.g., `10.255.0.1/30`)
   - **GRE Key**: Optional traffic identifier (must match both ends)
   - **Keepalive Interval**: Health check interval in seconds
5. Click **Add Interface**
6. Add **OSPF** or **BGP** protocol to peer over the tunnel
7. **Launch** the agent

### Method 2: REST API

```bash
# Create a GRE tunnel
curl -X POST http://localhost:8080/api/gre/tunnel \
  -H "Content-Type: application/json" \
  -d '{
    "name": "gre-to-cml",
    "remote_ip": "192.168.100.50",
    "tunnel_ip": "10.255.0.1/30",
    "key": 100,
    "keepalive_interval": 10
  }'
```

### Method 3: TOON Configuration

```json
{
  "interfaces": [
    {
      "id": "gre0",
      "n": "gre0",
      "t": "gre",
      "a": ["10.255.0.1/30"],
      "mtu": 1400,
      "tun": {
        "tt": "gre",
        "src": "192.168.1.10",
        "dst": "192.168.100.50",
        "key": 100,
        "ka": 10
      }
    }
  ]
}
```

---

## Example: Connect to Cisco CML

### Network Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  ┌─────────────┐         GRE Tunnel          ┌─────────────────────────┐   │
│  │  Agent A    │◄───────────────────────────►│     Cisco CML Lab       │   │
│  │ 172.20.1.1  │    Tunnel: 10.255.0.1/30    │     CSR1000v            │   │
│  │             │         OSPF Area 0          │     10.255.0.2/30       │   │
│  │  OSPF ✓    │                              │                         │   │
│  │  BGP  ✓    │                              │  Learns Agent routes!   │   │
│  └─────────────┘                              └─────────────────────────┘   │
│        │                                                   │                │
│        │ OSPF                                              │ OSPF           │
│        ▼                                                   ▼                │
│  ┌─────────────┐                              ┌─────────────────────────┐   │
│  │  Agent B    │                              │  CML Internal Network   │   │
│  │ 172.20.2.1  │                              │  10.0.0.0/8            │   │
│  └─────────────┘                              └─────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Step 1: Create GRE Tunnel on Agent

**Via API:**
```bash
curl -X POST http://localhost:8080/api/gre/tunnel \
  -H "Content-Type: application/json" \
  -d '{
    "name": "gre-to-cml",
    "remote_ip": "192.168.100.50",
    "tunnel_ip": "10.255.0.1/30",
    "key": 100,
    "keepalive_interval": 10
  }'
```

**Via Wizard:**
- Interface Type: GRE Tunnel
- Remote Endpoint IP: `192.168.100.50`
- Tunnel IP: `10.255.0.1/30`
- GRE Key: `100`

### Step 2: Configure CML Router (CSR1000v)

```cisco
! Configure the GRE tunnel interface
interface Tunnel0
 description GRE to Agentic Network
 ip address 10.255.0.2 255.255.255.252
 tunnel source GigabitEthernet1
 tunnel destination 192.168.100.10
 tunnel key 100
 ip ospf network point-to-point
 ip ospf 1 area 0
!
! Enable OSPF
router ospf 1
 router-id 2.2.2.2
 network 10.0.0.0 0.255.255.255 area 0
 network 10.255.0.0 0.0.0.3 area 0
```

### Step 3: Enable OSPF on Agent

Add OSPF protocol in the wizard or ensure the agent's OSPF configuration includes the tunnel network.

### Step 4: Verify Connectivity

**On Agent (via API):**
```bash
# Check tunnel status
curl http://localhost:8080/api/gre/tunnel/gre-to-cml

# Check OSPF neighbors
curl http://localhost:8080/api/ospf/neighbors
```

**On CML Router:**
```cisco
show ip ospf neighbor
show ip route ospf
show interface tunnel0
```

**Expected Results:**
- OSPF neighbor state: FULL
- Routes learned from agent network
- Tunnel interface UP/UP

---

## Example: Connect to Containerlab

### Network Diagram

```
┌──────────────────┐                    ┌──────────────────┐
│  Agentic Agent   │      GRE over      │   Containerlab   │
│    "atlanta"     │◄──────────────────►│   FRRouting      │
│   192.168.1.10   │    Docker Bridge   │   192.168.1.20   │
│                  │                    │                  │
│  Tunnel IP:      │                    │  Tunnel IP:      │
│  10.0.0.1/30     │                    │  10.0.0.2/30     │
│                  │                    │                  │
│  iBGP AS 65000   │◄──── BGP Peer ────►│  iBGP AS 65000   │
└──────────────────┘                    └──────────────────┘
```

### Step 1: Create Containerlab Topology

```yaml
# clab-topology.yml
name: gre-peering
topology:
  nodes:
    frr1:
      kind: linux
      image: frrouting/frr:latest
      binds:
        - frr.conf:/etc/frr/frr.conf
```

### Step 2: Configure FRRouting

```
# frr.conf
frr version 8.4
frr defaults traditional
hostname frr1
!
interface gre1
 ip address 10.0.0.2/30
!
interface lo
 ip address 2.2.2.2/32
!
router bgp 65000
 bgp router-id 2.2.2.2
 neighbor 10.0.0.1 remote-as 65000
 !
 address-family ipv4 unicast
  network 2.2.2.2/32
 exit-address-family
!
```

### Step 3: Create GRE Tunnel in FRR Container

```bash
# Inside the FRR container
ip tunnel add gre1 mode gre remote 192.168.1.10 local 192.168.1.20 ttl 255
ip addr add 10.0.0.2/30 dev gre1
ip link set gre1 up
```

### Step 4: Create Tunnel on Agent

```bash
curl -X POST http://localhost:8080/api/gre/tunnel \
  -d '{
    "name": "gre-to-clab",
    "remote_ip": "192.168.1.20",
    "tunnel_ip": "10.0.0.1/30"
  }'
```

---

## Example: Multi-Site Mesh

### Network Diagram

```
                         INTERNET / WAN
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │  Site A     │     │  Site B     │     │  Site C     │
   │  Agent      │     │  Agent      │     │  Cisco ISR  │
   │ 10.1.0.1    │     │ 10.2.0.1    │     │ 10.3.0.1    │
   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘
          │                   │                   │
          └─────────GRE───────┴─────────GRE───────┘
                    Full Mesh Tunnels

   Tunnel IPs:
   A ↔ B: 10.255.1.0/30
   A ↔ C: 10.255.2.0/30
   B ↔ C: 10.255.3.0/30
```

### Configuration

**Site A Agent:**
```bash
# Tunnel to Site B
curl -X POST http://localhost:8080/api/gre/tunnel \
  -d '{"name": "gre-to-b", "remote_ip": "10.2.0.1", "tunnel_ip": "10.255.1.1/30"}'

# Tunnel to Site C
curl -X POST http://localhost:8080/api/gre/tunnel \
  -d '{"name": "gre-to-c", "remote_ip": "10.3.0.1", "tunnel_ip": "10.255.2.1/30"}'
```

---

## API Reference

### Get GRE Manager Status

```
GET /api/gre/status
```

**Response:**
```json
{
  "enabled": true,
  "agent_id": "atlanta",
  "local_ip": "192.168.1.10",
  "running": true,
  "tunnel_count": 2,
  "tunnels_up": 2,
  "passive_enabled": true
}
```

### List All Tunnels

```
GET /api/gre/tunnels
```

**Response:**
```json
{
  "tunnels": [
    {
      "name": "gre-to-cml",
      "state": "up",
      "local_ip": "192.168.1.10",
      "remote_ip": "192.168.100.50",
      "tunnel_ip": "10.255.0.1/30",
      "statistics": {
        "packets_tx": 1523,
        "packets_rx": 1489,
        "bytes_tx": 152300,
        "bytes_rx": 148900
      }
    }
  ],
  "count": 1
}
```

### Create Tunnel

```
POST /api/gre/tunnel
```

**Request Body:**
```json
{
  "name": "gre-to-cml",
  "remote_ip": "192.168.100.50",
  "tunnel_ip": "10.255.0.1/30",
  "local_ip": "192.168.1.10",
  "key": 100,
  "use_checksum": false,
  "use_sequence": false,
  "mtu": 1400,
  "keepalive_interval": 10,
  "description": "Tunnel to CML lab"
}
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| name | Yes | Tunnel interface name |
| remote_ip | Yes | Remote endpoint IP |
| tunnel_ip | No | Tunnel interface IP (CIDR) |
| local_ip | No | Local endpoint IP (auto-detected) |
| key | No | GRE key (32-bit) |
| use_checksum | No | Enable checksums (default: false) |
| use_sequence | No | Enable sequence numbers (default: false) |
| mtu | No | Tunnel MTU (default: 1400) |
| keepalive_interval | No | Keepalive interval in seconds (default: 10, 0 to disable) |

### Delete Tunnel

```
DELETE /api/gre/tunnel/{name}
```

### Get Tunnel Statistics

```
GET /api/gre/statistics
```

### Add Allowed Source (Passive Mode)

```
POST /api/gre/allowed-source?ip=192.168.100.50
```

---

## Troubleshooting

### Tunnel Not Coming Up

1. **Check IP Connectivity:**
   ```bash
   ping <remote_ip>
   ```

2. **Verify GRE Protocol (47) is Allowed:**
   - Check firewalls between endpoints
   - GRE uses IP protocol 47, not TCP/UDP

3. **Check Key Mismatch:**
   - If using keyed GRE, keys must match on both ends

4. **Verify MTU:**
   - Ensure path MTU supports GRE overhead (24+ bytes)

### OSPF Neighbor Not Forming

1. **Check Tunnel State:**
   ```bash
   curl http://localhost:8080/api/gre/tunnel/<name>
   ```

2. **Verify OSPF Configuration:**
   - Both ends must be in the same area
   - Hello/Dead timers must match
   - Network types should match (point-to-point recommended)

3. **Check MTU Match:**
   - OSPF MTU mismatch prevents adjacency
   - Use `ip ospf mtu-ignore` on Cisco if needed

### Packet Loss Over Tunnel

1. **Check for Fragmentation:**
   - Reduce tunnel MTU if seeing fragmentation
   - Recommended: 1400 bytes

2. **Verify Keepalives:**
   - Ensure keepalives are enabled and responding

3. **Check Statistics:**
   ```bash
   curl http://localhost:8080/api/gre/statistics
   ```

### Permission Denied Errors

GRE uses raw sockets which require root/admin privileges:
- Run agent with `sudo` or as root
- Or use appropriate capabilities: `CAP_NET_RAW`

---

## Quick Reference

### GRE Header Flags

| Flag | Bit | Description |
|------|-----|-------------|
| C | 0 | Checksum present |
| K | 2 | Key present |
| S | 3 | Sequence number present |

### Common Protocol Types (Ethertypes)

| Protocol | Value |
|----------|-------|
| IPv4 | 0x0800 |
| IPv6 | 0x86DD |
| ARP | 0x0806 |
| MPLS | 0x8847 |

### MTU Calculation

```
Tunnel MTU = Physical MTU - IP Header (20) - GRE Header (4-16)

Example:
  1500 (Ethernet) - 20 (IP) - 4 (GRE base) = 1476 bytes

Recommended safe MTU: 1400 bytes (allows for all GRE options)
```

---

## See Also

- [BGP User Guide](BGP_USER_GUIDE.md)
- [OSPF Protocol Analysis](ospf_protocol_analysis.md)
- [RFC 2784 - Generic Routing Encapsulation](https://datatracker.ietf.org/doc/html/rfc2784)
- [RFC 2890 - Key and Sequence Number Extensions to GRE](https://datatracker.ietf.org/doc/html/rfc2890)
