# BGP Protocol Analysis (RFC 4271)

## Overview
Border Gateway Protocol version 4 (BGP-4) is the inter-autonomous system routing protocol for the Internet. This document analyzes the core protocol components required for implementation.

## 1. BGP Finite State Machine (RFC 4271 Section 8)

### States
1. **Idle (0)**: Refuse all incoming connections. Start on ManualStart event.
2. **Connect (1)**: Waiting for TCP connection to complete.
3. **Active (2)**: Failed to establish TCP, trying again.
4. **OpenSent (3)**: TCP established, OPEN sent, waiting for peer OPEN.
5. **OpenConfirm (4)**: OPEN received and validated, waiting for KEEPALIVE or NOTIFICATION.
6. **Established (5)**: Peering is up, exchanging UPDATE, KEEPALIVE, ROUTE-REFRESH messages.

### Critical Events
- ManualStart / AutomaticStart: Idle → Connect
- TcpConnectionConfirmed: Connect → OpenSent (send OPEN)
- BGPOpen (valid): OpenSent → OpenConfirm (send KEEPALIVE)
- BGPHeaderErr / BGPOpenMsgErr: Any → Idle (send NOTIFICATION)
- KeepAliveMsg: OpenConfirm → Established
- UpdateMsg / KeepAliveMsg: Established → Established
- HoldTimer_Expires: Any non-Idle → Idle (send NOTIFICATION)
- NotifMsg: Any → Idle

### Timers
- **ConnectRetryTimer**: 120s default, retry TCP connection
- **HoldTimer**: Negotiated (min of local/peer), typically 90s or 180s
- **KeepaliveTimer**: HoldTime / 3, typically 30s or 60s

## 2. Message Types (RFC 4271 Section 4)

### Message Header (19 bytes)
```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                            Marker (16 bytes)                  |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          Length (2)           |   Type (1)    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```
- Marker: All 1s (0xFF * 16) for no authentication
- Length: Total message length (19-4096 bytes)
- Type: 1=OPEN, 2=UPDATE, 3=NOTIFICATION, 4=KEEPALIVE, 5=ROUTE-REFRESH

### OPEN (Type 1)
```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    Version (1)|  My AS (2)    |      Hold Time (2)            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       BGP Identifier (4)                      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Opt Parm Len  |  Optional Parameters (variable)
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```
- Version: 4
- My AS: Autonomous System Number (2 bytes, or AS_TRANS 23456 if using 4-byte AS)
- Hold Time: Proposed hold time (0 or >= 3 seconds)
- BGP Identifier: Router ID (IPv4 address format)
- Optional Parameters: Capabilities (Type 2)

### UPDATE (Type 2) - RFC 4271 Section 4.3
```
+-----------------------------------------------------+
|   Withdrawn Routes Length (2 octets)                |
+-----------------------------------------------------+
|   Withdrawn Routes (variable)                       |
+-----------------------------------------------------+
|   Total Path Attribute Length (2 octets)            |
+-----------------------------------------------------+
|   Path Attributes (variable)                        |
+-----------------------------------------------------+
|   Network Layer Reachability Information (variable) |
+-----------------------------------------------------+
```
- Withdrawn Routes: Prefixes to remove from routing table
- Path Attributes: ORIGIN, AS_PATH, NEXT_HOP, MED, LOCAL_PREF, etc.
- NLRI: Prefixes to add/update

### KEEPALIVE (Type 4)
- Only 19-byte header (no data)
- Sent periodically to maintain session

### NOTIFICATION (Type 3)
```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Error code (1)|Error subcode(1)|   Data (variable)
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```
- Error Code: 1=Header, 2=OPEN, 3=UPDATE, 4=Hold Timer, 5=FSM, 6=Cease
- Error Subcode: Specific error within code
- Terminates session immediately

## 3. Path Attributes (RFC 4271 Section 5)

### Attribute Header
```
 0                   1
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Flags (1)    | Type Code (1) | Length (1 or 2) | Value (var)
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

Flags:
- Bit 0: Optional (1) / Well-known (0)
- Bit 1: Transitive (1) / Non-transitive (0)
- Bit 2: Partial (1) / Complete (0)
- Bit 3: Extended Length (1=2 bytes) / Normal (0=1 byte)

### Well-Known Mandatory Attributes
1. **ORIGIN (Type 1)**: IGP (0), EGP (1), INCOMPLETE (2)
2. **AS_PATH (Type 2)**: AS_SET (1) or AS_SEQUENCE (2) segments
3. **NEXT_HOP (Type 3)**: IPv4 address of next hop

### Well-Known Discretionary Attributes
4. **LOCAL_PREF (Type 5)**: 32-bit preference (iBGP only, higher is better)
5. **ATOMIC_AGGREGATE (Type 6)**: Flag indicating route aggregation

### Optional Transitive Attributes
6. **AGGREGATOR (Type 7)**: AS and Router ID of aggregator
7. **COMMUNITIES (Type 8)**: 32-bit community values (RFC 1997)

### Optional Non-Transitive Attributes
8. **MED (Type 4)**: Multi-Exit Discriminator (32-bit metric, lower is better)
9. **ORIGINATOR_ID (Type 9)**: RFC 4456 route reflection
10. **CLUSTER_LIST (Type 10)**: RFC 4456 route reflection loop prevention

### Multiprotocol Extensions (RFC 4760)
14. **MP_REACH_NLRI (Type 14)**: IPv6 and other AFI/SAFI
15. **MP_UNREACH_NLRI (Type 15)**: Withdrawn IPv6 routes

## 4. Best Path Selection Algorithm (RFC 4271 Section 9.1)

### Decision Process (in order)
1. **Highest LOCAL_PREF** (iBGP only, well-known discretionary)
2. **Shortest AS_PATH** (fewer AS hops)
3. **Lowest ORIGIN** (IGP=0 < EGP=1 < INCOMPLETE=2)
4. **Lowest MED** (if from same neighboring AS)
5. **eBGP > iBGP** (prefer external routes)
6. **Lowest IGP metric** to NEXT_HOP
7. **Oldest route** (route stability)
8. **Lowest Router ID** (tiebreaker)
9. **Lowest peer IP** (final tiebreaker)

### Special Cases
- Routes with ATOMIC_AGGREGATE cannot be de-aggregated
- Routes with NO_EXPORT community must not be advertised to eBGP peers
- Routes with NO_ADVERTISE must not be advertised to any peer

## 5. Route Reflection (RFC 4456)

### Topology
- **Route Reflector (RR)**: Central router reflecting routes
- **Clients**: Peers marked as route-reflector-client
- **Non-clients**: Regular iBGP peers

### Reflection Rules
1. Route from **client** → Reflect to all clients + all non-clients + all eBGP
2. Route from **non-client** → Reflect to clients only (not to other non-clients)
3. Route from **eBGP** → Reflect to all clients + all non-clients

### Loop Prevention
- **ORIGINATOR_ID (Type 9)**: Added by RR, contains original router ID. Reject if matches self.
- **CLUSTER_LIST (Type 10)**: Prepended with RR's cluster ID. Reject if cluster ID already present.

### Attribute Modification
- Set ORIGINATOR_ID if not already set
- Prepend cluster ID to CLUSTER_LIST

## 6. Communities (RFC 1997)

### Format
32-bit value: `<AS:Value>` = `(AS << 16) | Value`
Example: 65001:100 = 0xFDE90064

### Well-Known Communities
- **NO_EXPORT (0xFFFFFF01)**: Do not advertise to eBGP peers
- **NO_ADVERTISE (0xFFFFFF02)**: Do not advertise to any peer
- **NO_EXPORT_SUBCONFED (0xFFFFFF03)**: Do not advertise outside confederation

### Usage in Policy
- Match routes with community 65001:100
- Set community 65001:200 on routes to customer
- Remove community 65001:999 from routes to peer

## 7. Capabilities (RFC 5492)

### Capability Format (in OPEN Optional Parameters)
```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Parm Type=2   | Parm Length   | Cap Code      | Cap Length    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Capability Value (variable)
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### Common Capabilities
- **Multiprotocol (Code 1)**: AFI/SAFI support (IPv4, IPv6)
- **Route Refresh (Code 2)**: RFC 2918 route refresh support
- **4-byte AS (Code 65)**: RFC 6793 support for AS > 65535
- **Graceful Restart (Code 64)**: RFC 4724 graceful restart
- **ADD-PATH (Code 69)**: RFC 7911 multiple paths per prefix

## 8. Session Establishment Flow

```
Idle
  |
  | ManualStart / AutomaticStart
  v
Connect (initiate TCP to peer:179)
  |
  | TCP connection established
  v
OpenSent (send OPEN message)
  |
  | Receive valid OPEN
  v
OpenConfirm (send KEEPALIVE)
  |
  | Receive KEEPALIVE
  v
Established (exchange UPDATE, KEEPALIVE, ROUTE-REFRESH)
```

### Collision Detection (RFC 4271 Section 6.8)
If both peers simultaneously open TCP connections:
- Keep connection from peer with **higher Router ID**
- Close connection from peer with lower Router ID

## 9. Error Handling (RFC 7606)

### Treat-as-withdraw Errors
For UPDATE message errors that don't warrant session reset:
- Malformed path attributes → Treat as implicit withdraw
- Missing well-known mandatory attribute → Treat as withdraw
- Invalid NEXT_HOP → Treat as withdraw

### Session Reset Errors
- Invalid message header
- Unsupported version in OPEN
- Hold Time < 3 and not 0
- Unacceptable AS number

## 10. IPv6 Support (RFC 4760 Multiprotocol Extensions)

### Address Families
- AFI 1 = IPv4
- AFI 2 = IPv6
- SAFI 1 = Unicast
- SAFI 2 = Multicast

### MP_REACH_NLRI (Type 14)
```
+---------------------------------------------------------+
| AFI (2)          | SAFI (1)        | NH Length (1)     |
+---------------------------------------------------------+
| Next Hop (variable, 4 or 16 or 32 bytes for IPv6)      |
+---------------------------------------------------------+
| Reserved (1)     | NLRI (variable)                     |
+---------------------------------------------------------+
```

### MP_UNREACH_NLRI (Type 15)
```
+---------------------------------------------------------+
| AFI (2)          | SAFI (1)        | Withdrawn (var)   |
+---------------------------------------------------------+
```

## Implementation Priority

1. **Phase 1**: Message encoding/decoding (OPEN, UPDATE, KEEPALIVE, NOTIFICATION)
2. **Phase 2**: Path attributes (ORIGIN, AS_PATH, NEXT_HOP, LOCAL_PREF, MED, COMMUNITIES)
3. **Phase 3**: BGP FSM with timers
4. **Phase 4**: RIB management (Adj-RIB-In, Loc-RIB, Adj-RIB-Out)
5. **Phase 5**: Best path selection algorithm
6. **Phase 6**: Route reflection (ORIGINATOR_ID, CLUSTER_LIST)
7. **Phase 7**: Policy engine (import/export filters, attribute manipulation)
8. **Phase 8**: IPv6 support (MP_REACH_NLRI, MP_UNREACH_NLRI)
9. **Phase 9**: Session management (TCP, collision detection, error handling)
10. **Phase 10**: Capabilities negotiation and advanced features

## References

- RFC 4271: A Border Gateway Protocol 4 (BGP-4)
- RFC 4456: BGP Route Reflection
- RFC 1997: BGP Communities Attribute
- RFC 4760: Multiprotocol Extensions for BGP-4
- RFC 5492: Capabilities Advertisement with BGP-4
- RFC 2918: Route Refresh Capability for BGP-4
- RFC 4486: Subcodes for BGP Cease Notification Message
- RFC 7606: Revised Error Handling for BGP UPDATE Messages
- RFC 7911: Advertisement of Multiple Paths in BGP
