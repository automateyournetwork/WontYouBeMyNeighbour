# GRE External Peering Lab

This template demonstrates GRE tunnel connectivity between the Agentic network and an external FRRouting router running in Docker.

## Network Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           AGENTIC NETWORK                                        │
│                                                                                 │
│  ┌─────────────┐     172.20.0.0/24     ┌─────────────┐     172.20.1.0/24     ┌─────────────┐
│  │ Edge Router │◄─────────────────────►│ Core Router │◄─────────────────────►│  Internal   │
│  │ 10.255.255.1│      OSPF Area 0      │10.255.255.99│      OSPF Area 0      │   Router    │
│  │             │                       │             │                       │ 10.255.255.2│
│  └─────────────┘                       └──────┬──────┘                       └─────────────┘
│                                               │
│                                               │ eth2: 192.168.100.10
│                                               │
│  ════════════════════════════════════════════╪═════════════════════════════════
│                                               │
│                                        GRE Tunnel
│                                     10.255.0.0/30
│                                        Key: 100
│                                               │
│  ════════════════════════════════════════════╪═════════════════════════════════
│                                               │
└───────────────────────────────────────────────┼─────────────────────────────────┘
                                                │
┌───────────────────────────────────────────────┼─────────────────────────────────┐
│                        EXTERNAL FRR (Docker)  │                                 │
│                                               │                                 │
│                                        192.168.100.20                           │
│                                               │                                 │
│                                        ┌──────┴──────┐                          │
│                                        │ External    │                          │
│                                        │ FRR Router  │                          │
│                                        │10.255.255.100                          │
│                                        │             │                          │
│                                        │ OSPF Area 0 │                          │
│                                        └──────┬──────┘                          │
│                                               │                                 │
│                                        10.100.0.0/24                            │
│                                    (Simulated External Net)                     │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## IP Addressing

| Device | Interface | IP Address | Description |
|--------|-----------|------------|-------------|
| Edge Router | eth0 | 172.20.0.10/24 | Link to Core |
| Edge Router | lo0 | 10.255.255.1/32 | Loopback |
| Core Router | eth0 | 172.20.0.99/24 | Link to Edge |
| Core Router | eth1 | 172.20.1.99/24 | Link to Internal |
| Core Router | eth2 | 192.168.100.10/24 | GRE underlay |
| Core Router | gre0 | 10.255.0.1/30 | GRE tunnel |
| Core Router | lo0 | 10.255.255.99/32 | Loopback |
| Internal Router | eth0 | 172.20.1.2/24 | Link to Core |
| Internal Router | lo0 | 10.255.255.2/32 | Loopback |
| External FRR | eth0 | 192.168.100.20/24 | GRE underlay |
| External FRR | gre1 | 10.255.0.2/30 | GRE tunnel |
| External FRR | lo | 10.255.255.100/32 | Loopback |
| External FRR | ext-net | 10.100.0.1/24 | External network |

## GRE Tunnel Details

| Parameter | Agentic Side | FRR Side |
|-----------|--------------|----------|
| Local IP | 192.168.100.10 | 192.168.100.20 |
| Remote IP | 192.168.100.20 | 192.168.100.10 |
| Tunnel IP | 10.255.0.1/30 | 10.255.0.2/30 |
| GRE Key | 100 | 100 |
| MTU | 1400 | 1400 |

## Quick Start

### Step 1: Start External FRR Router

```bash
cd templates/topology_templates/gre-external-peering/external-frr

# Make setup script executable
chmod +x setup-gre.sh

# Start FRR container
docker-compose up -d

# Verify it's running
docker ps | grep external-frr

# Check GRE tunnel on FRR side
docker exec -it external-frr ip tunnel show
```

### Step 2: Launch Agentic Network

Use the wizard to load this template, or via API:

```bash
# Load the template
curl -X POST http://localhost:8080/api/wizard/templates/load \
  -H "Content-Type: application/json" \
  -d '{"template_id": "gre-external-peering"}'

# Launch the agents
curl -X POST http://localhost:8080/api/wizard/launch
```

Or manually create with the wizard:
1. Open the Agent Builder
2. Select "Load Template" → "GRE External Peering Lab"
3. Click "Launch All"

### Step 3: Verify Connectivity

**From Agentic (via API):**
```bash
# Check GRE tunnel status
curl http://localhost:8080/api/gre/tunnels

# Check OSPF neighbors
curl http://localhost:8080/api/ospf/neighbors

# Should see neighbor 10.255.255.100 (External FRR)
```

**From External FRR:**
```bash
# Enter FRR shell
docker exec -it external-frr vtysh

# Check OSPF neighbors
show ip ospf neighbor

# Check routes learned from Agentic
show ip route ospf

# Ping Agentic Core Router through tunnel
ping 10.255.0.1
```

### Step 4: Verify Route Exchange

**On External FRR, you should see routes to:**
- 172.20.0.0/24 (Agentic Edge-Core link)
- 172.20.1.0/24 (Agentic Core-Internal link)
- 10.255.255.1/32 (Edge Router loopback)
- 10.255.255.2/32 (Internal Router loopback)
- 10.255.255.99/32 (Core Router loopback)

**On Agentic Core Router, you should see routes to:**
- 10.100.0.0/24 (External simulated network)
- 10.255.255.100/32 (External FRR loopback)

## Troubleshooting

### GRE Tunnel Not Up

1. **Check IP connectivity (underlay):**
   ```bash
   # From FRR container
   docker exec -it external-frr ping 192.168.100.10
   ```

2. **Check GRE tunnel interface:**
   ```bash
   docker exec -it external-frr ip tunnel show gre1
   docker exec -it external-frr ip addr show gre1
   ```

3. **Verify GRE key matches:**
   - Agentic: `key: 100` in gre0 config
   - FRR: `key 100` in setup-gre.sh

### OSPF Neighbor Not Forming

1. **Check OSPF is running on both sides:**
   ```bash
   # FRR
   docker exec -it external-frr vtysh -c "show ip ospf interface"

   # Agentic
   curl http://localhost:8080/api/ospf/interfaces
   ```

2. **Verify Area matches:** Both should be Area 0

3. **Check hello/dead timers:** Must match on both ends

4. **MTU issues:** Ensure both sides have matching MTU (1400)

### Docker Network Issues

1. **Check container is on correct network:**
   ```bash
   docker network inspect gre-external-peering_gre-underlay
   ```

2. **Verify IP address:**
   ```bash
   docker exec -it external-frr ip addr show eth0
   ```

## Customization

### Change GRE Key

**In Agentic (agents.json):**
```json
"tun": {
  "key": 200
}
```

**In FRR (setup-gre.sh):**
```bash
GRE_KEY="200"
```

### Add BGP Peering Over GRE

**FRR config addition:**
```
router bgp 65100
 bgp router-id 10.255.255.100
 neighbor 10.255.0.1 remote-as 65001
 !
 address-family ipv4 unicast
  network 10.100.0.0/24
 exit-address-family
```

**Agentic Core Router protocol addition:**
```json
{"p": "ebgp", "r": "10.255.255.99", "asn": 65001, "peers": [{"ip": "10.255.0.2", "asn": 65100}]}
```

## Cleanup

```bash
# Stop FRR container
cd external-frr
docker-compose down

# Remove network
docker network rm gre-external-peering_gre-underlay
```

## Files

```
gre-external-peering/
├── README.md           # This file
├── metadata.json       # Template metadata
├── agents.json         # Agentic agent definitions
├── links.json          # Internal links
└── external-frr/
    ├── docker-compose.yml  # Docker setup for FRR
    ├── frr.conf           # FRR configuration
    ├── daemons            # FRR daemon enablement
    └── setup-gre.sh       # GRE tunnel setup script
```
