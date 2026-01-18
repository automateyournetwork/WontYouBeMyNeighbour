# RFC 4271 - BGP-4 Core Protocol Analysis

## Overview
**Title:** A Border Gateway Protocol 4 (BGP-4)
**Status:** Standards Track
**Date:** January 2006

## Implementation Status

### 1. Message Format (Section 4)

#### 4.1 Message Header (19 bytes)
- ✅ Marker: 16 bytes of 0xFF
- ✅ Length: 2 bytes (19-4096)
- ✅ Type: 1 byte (OPEN, UPDATE, NOTIFICATION, KEEPALIVE)
- **Implementation:** `messages.py:BGPMessage._build_header()`

#### 4.2 OPEN Message (Type 1)
- ✅ Version: BGP-4 (4)
- ✅ My AS: 2 bytes (or AS_TRANS for 4-byte AS)
- ✅ Hold Time: 2 bytes (0 or >= 3 seconds)
- ✅ BGP Identifier: 4 bytes (router ID)
- ✅ Optional Parameters: Capabilities
- **Implementation:** `messages.py:BGPOpen`

#### 4.3 UPDATE Message (Type 2)
- ✅ Withdrawn Routes Length: 2 bytes
- ✅ Withdrawn Routes: Variable (prefix/length pairs)
- ✅ Path Attributes Length: 2 bytes
- ✅ Path Attributes: Variable (see Section 5)
- ✅ NLRI: Variable (announced prefixes)
- **Implementation:** `messages.py:BGPUpdate`

#### 4.4 KEEPALIVE Message (Type 4)
- ✅ Header only (19 bytes)
- **Implementation:** `messages.py:BGPKeepalive`

#### 4.5 NOTIFICATION Message (Type 3)
- ✅ Error Code: 1 byte
- ✅ Error Subcode: 1 byte
- ✅ Data: Variable
- **Implementation:** `messages.py:BGPNotification`

### 2. Path Attributes (Section 5)

#### Well-Known Mandatory Attributes
- ✅ ORIGIN (Type 1): IGP, EGP, INCOMPLETE
- ✅ AS_PATH (Type 2): AS_SEQUENCE, AS_SET
- ✅ NEXT_HOP (Type 3): IPv4 address

#### Well-Known Discretionary Attributes
- ✅ LOCAL_PREF (Type 5): 32-bit preference (iBGP only)
- ✅ ATOMIC_AGGREGATE (Type 6): Flag

#### Optional Transitive Attributes
- ✅ AGGREGATOR (Type 7): AS + IP address
- ✅ COMMUNITIES (Type 8): RFC 1997

#### Optional Non-Transitive Attributes
- ✅ MULTI_EXIT_DISC (Type 4): 32-bit metric

**Implementation:** `attributes.py` with full attribute classes

### 3. BGP Finite State Machine (Section 8)

#### 3.1 States (8.2.2)
- ✅ Idle (0): Initial state
- ✅ Connect (1): Waiting for TCP
- ✅ Active (2): TCP retry
- ✅ OpenSent (3): OPEN sent
- ✅ OpenConfirm (4): OPEN received
- ✅ Established (5): Peering up

**Implementation:** `fsm.py:BGPFSM`

#### 3.2 Events (8.1)
- ✅ Administrative: ManualStart, ManualStop
- ✅ Timer: ConnectRetryTimer, HoldTimer, KeepaliveTimer
- ✅ TCP: Connection events
- ✅ BGP Message: OPEN, UPDATE, KEEPALIVE, NOTIFICATION

**Implementation:** `fsm.py:BGPEvent` enum

#### 3.3 Timers
- ✅ ConnectRetryTimer: Default 120s
- ✅ HoldTimer: Negotiated (default 90s, min 3s)
- ✅ KeepaliveTimer: HoldTime / 3

**Implementation:** `fsm.py` async timer management

### 4. UPDATE Message Handling (Section 6)

#### 4.1 Decision Process (9.1)
**Phase 1: Calculate Degree of Preference**
1. ✅ If NEXT_HOP unreachable → exclude
2. ✅ Calculate degree of preference (LOCAL_PREF or default)

**Phase 2: Route Selection (9.1.2)**
1. ✅ Highest LOCAL_PREF
2. ✅ Shortest AS_PATH
3. ✅ Lowest ORIGIN (IGP < EGP < INCOMPLETE)
4. ✅ Lowest MED (same neighbor AS)
5. ✅ eBGP over iBGP
6. ✅ Lowest IGP metric to NEXT_HOP
7. ✅ Oldest route
8. ✅ Lowest BGP Identifier
9. ✅ Lowest peer IP

**Implementation:** `path_selection.py:BestPathSelector`

**Phase 3: Route Dissemination (9.1.3)**
- ✅ Advertise best routes to peers
- ✅ Apply export policy
- ✅ iBGP split-horizon (don't advertise iBGP→iBGP without RR)

**Implementation:** `agent.py:_decision_process()`

### 5. Error Handling (Section 6)

#### Error Codes
- ✅ Message Header Error (1)
- ✅ OPEN Message Error (2)
- ✅ UPDATE Message Error (3)
- ✅ Hold Timer Expired (4)
- ✅ FSM Error (5)
- ✅ Cease (6)

**Implementation:** `constants.py` + `errors.py` + `messages.py:BGPNotification`

### 6. BGP Identifiers (Section 1.1)

- ✅ Router ID: 32-bit IPv4 address format
- ✅ Uniqueness within AS required
- ✅ Used in best path tie-breaking

### 7. Transport Protocol (Section 3)

- ✅ TCP port 179
- ✅ Passive connection acceptance
- ✅ Active connection initiation
- ✅ Connection collision detection

**Implementation:** `session.py:BGPSession`

### 8. Capabilities (RFC 5492)

- ✅ Multiprotocol Extensions (RFC 4760)
- ✅ Route Refresh (RFC 2918)
- ✅ 4-byte AS Numbers (RFC 6793)
- ✅ Graceful Restart (RFC 4724)

**Implementation:** `capabilities.py`

## RFC 4271 Compliance Summary

### Fully Implemented ✅
- Message encoding/decoding (Section 4)
- All mandatory path attributes (Section 5)
- BGP FSM with all states (Section 8)
- Best path selection (Section 9.1.2)
- Error handling (Section 6)
- TCP session management (Section 3)
- Timer management (Section 8)

### Enhancements Beyond RFC 4271
- ✅ Route Reflection (RFC 4456)
- ✅ Communities (RFC 1997)
- ✅ IPv6 Support (RFC 4760)
- ✅ Policy Engine (RFC 8212)
- ✅ 4-byte AS (RFC 6793)

### Testing Needed
- [ ] Multi-peer scenarios
- [ ] BGP message fuzzing
- [ ] Timer edge cases
- [ ] Route flap damping scenarios
- [ ] Large routing table handling (100k+ routes)

## Key RFC Sections Referenced in Code

| File | RFC Section | Description |
|------|-------------|-------------|
| constants.py | 4.1, 5.1, 8.1 | All protocol constants |
| messages.py | 4.1-4.5 | Message encoding/decoding |
| attributes.py | 5.1 | Path attributes |
| fsm.py | 8.2.2 | FSM states and transitions |
| path_selection.py | 9.1.2 | Best path algorithm |
| rib.py | 3.2 | RIB management |
| session.py | 3, 8 | TCP and FSM integration |
| agent.py | 9 | Decision process orchestration |

## Next Steps

1. Build comprehensive test suite covering:
   - All message types
   - FSM state transitions
   - Best path selection scenarios
   - Multi-peer route exchange

2. Performance testing:
   - Session establishment time
   - Route processing throughput
   - Memory usage with large RIBs

3. Interoperability testing:
   - Test against FRRouting
   - Test against Cisco IOS-XR
   - Test against BIRD

4. Documentation:
   - Configuration examples
   - Troubleshooting guide
   - Architecture diagrams
